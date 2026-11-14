#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download the lightning strokes of the Finnish Meteorological Institute.

Fetches every stroke FMI's open-data WFS serves for the years asked for, over the
whole area it serves (Northern Europe, 49.7-73.1 N, 2.3-35.7 E), and writes one
file per UTC month. It touches no database::

    # one year
    python3 -m src.apps.download.lightnings.finland_fmi.download_lightnings \\
        --from-year 2018 --output-dir ~/data/fmi

    # several years, both included
    python3 -m src.apps.download.lightnings.finland_fmi.download_lightnings \\
        --from-year 1998 --to-year 2025 --output-dir ~/data/fmi

See :mod:`src.providers.finland_fmi` for the dataset and the fields.

What it asks for
----------------

The stored query :data:`~src.providers.finland_fmi.STORED_QUERY`, the compact
coverage encoding, with all sixteen fields named in ``parameters``
(:data:`~src.providers.finland_fmi.PARAMETERS`) — without them the service sends
only four. No ``bbox``: the whole served area.

The service takes an interval ``[starttime, endtime)`` — the end is excluded — of
**at most 168 hours**, and refuses a longer one. Each month is therefore cut into
windows of at most 168 hours that end exactly at the month's end
(:func:`month_windows`): consecutive windows neither overlap nor leave a gap, and
no window crosses into the next month. A 31-day month is five requests.

What it writes
--------------

For each month, in ``--output-dir``:

``fmi_lightning_YYYY-MM.csv.gz``
    A header, then one row per stroke: ``unixtime``, ``latitude``, ``longitude``
    and the sixteen fields, **every value the text the service sent** — nothing is
    converted, rounded or reordered within a window. Latitude comes first, as the
    service sends it (the axis order of EPSG:4258).
``fmi_lightning_YYYY-MM.meta.json``
    Where the data came from: the endpoint, the query, every window with its
    stroke count and the server's timestamp, the download time, the licence and
    the attribution, and whether the month was **complete**.

The data file is written to a ``.part`` and renamed only when every window of
the month has arrived and passed the checks, and the sidecar is written after
it. A month with both files and a sidecar saying it is complete is skipped by
the next run (``--overwrite`` fetches it again), so an interrupted run resumes
where it stopped. The data is taken as final: a complete month is never fetched
again unless asked.

The month in progress
---------------------

A month counts as complete one day after it ends (:data:`SETTLE`), so that the
last strokes have reached the archive. The year in progress therefore stops at
the last complete month. ``--include-current`` adds the months not yet complete,
up to now; their sidecar says ``"complete": false`` and the next run fetches them
again.

What is checked
---------------

Each response before anything of it is written: that it is XML; that it is not
an ``ExceptionReport`` (the service's answer to a bad request, reported with its
text); that it holds at most one coverage; that its field list is
:data:`~src.providers.finland_fmi.PARAMETERS` in that order; that its positions
are ETRS89 with a Unix time; that there are as many value tuples as positions,
three numbers per position and sixteen per tuple; and that every stroke falls
inside its window. A window with no stroke is an empty collection, which is
fine.

Being a polite client
---------------------

A delay between the *start* of one request and the next (``--delay``, default one
second: the service allows 600 requests every five minutes and 20,000 a day);
retries with exponential backoff, for transient failures only; a ``User-Agent``
that says who is calling. From 1998 to now is about 1,750 requests.

.. note::

   FMI open data is licensed **CC BY 4.0**: attribution required
   (:data:`~src.providers.finland_fmi.ATTRIBUTION`). The sidecar records it.

Requires ``requests``. No database.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import logging
import os
import sys
import time
import xml.etree.ElementTree as ElementTree

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

import requests

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.providers import finland_fmi

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

UTC = datetime.timezone.utc

#: Identifies this client to whoever reads the server's access log.
USER_AGENT = "GisFIRE/1.0 (research data download; +https://github.com/JaumeFigueras/GisFIRE)"

#: The first year of the archive (its first stroke is on 8 January 1998).
FIRST_YEAR = 1998

#: Seconds between the *start* of one request and the next.
DEFAULT_DELAY = 1.0

#: How many times a failing request is retried before the run gives up.
DEFAULT_RETRIES = 4

#: Seconds before the first retry; doubled each time.
BACKOFF_BASE = 2.0

#: Seconds to wait for a response. A busy summer week is 42 MB and about twenty
#: seconds; this leaves room for a slow day.
DEFAULT_TIMEOUT = 300.0

#: HTTP statuses worth retrying: the server failed, not the request. The service
#: answers a bad request with a 400 and an ``ExceptionReport``, which no retry
#: changes.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: How long after its end a month counts as complete.
SETTLE = datetime.timedelta(days=1)

#: The longest interval one request may cover.
WINDOW = datetime.timedelta(hours=finland_fmi.MAX_REQUEST_HOURS)

#: The columns of a monthly file, in order (shared with the importer).
COLUMNS = finland_fmi.FILE_COLUMNS

#: The XML namespaces of the responses.
NAMESPACES = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "gmlcov": "http://www.opengis.net/gmlcov/1.0",
    "swe": "http://www.opengis.net/swe/2.0",
    "ows": "http://www.opengis.net/ows/1.1",
}


class DownloadError(RuntimeError):
    """A request that could not be completed, or a response that does not add up."""


def iso(moment: datetime.datetime) -> str:
    """An instant as the service writes it, ``YYYY-MM-DDTHH:MM:SSZ``."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Month:
    """A UTC calendar month."""

    year: int
    month: int

    @property
    def start(self) -> datetime.datetime:
        """Its first instant."""
        return datetime.datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime.datetime:
        """The first instant of the next month: the month is ``[start, end)``."""
        if self.month == 12:
            return datetime.datetime(self.year + 1, 1, 1, tzinfo=UTC)
        return datetime.datetime(self.year, self.month + 1, 1, tzinfo=UTC)

    @property
    def label(self) -> str:
        """``YYYY-MM``."""
        return f"{self.year:04d}-{self.month:02d}"


def month_windows(start: datetime.datetime,
                  end: datetime.datetime) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """``[start, end)`` cut into consecutive windows of at most :data:`WINDOW`.

    The last window is the short one, and ends exactly at ``end``.
    """
    windows = []
    window_start = start
    while window_start < end:
        window_end = min(window_start + WINDOW, end)
        windows.append((window_start, window_end))
        window_start = window_end
    return windows


def months_to_download(from_year: int, to_year: int, now: datetime.datetime,
                       include_current: bool) -> list[tuple[Month, bool]]:
    """The months of the years asked for, each with whether it is complete.

    A month that has not started is left out. One that has not been over for
    :data:`SETTLE` is incomplete, and left out unless ``include_current``.
    """
    months = []
    for year in range(from_year, to_year + 1):
        for number in range(1, 13):
            month = Month(year, number)
            if month.start >= now:
                return months
            complete = month.end + SETTLE <= now
            if complete or include_current:
                months.append((month, complete))
    return months


def query(start: datetime.datetime, end: datetime.datetime) -> dict[str, str]:
    """The parameters of the request for ``[start, end)``."""
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "getFeature",
        "storedquery_id": finland_fmi.STORED_QUERY,
        "starttime": iso(start),
        "endtime": iso(end),
        "parameters": ",".join(finland_fmi.PARAMETERS),
    }


def exception_text(content: bytes) -> str | None:
    """The message of an ``ExceptionReport``, or ``None`` if ``content`` is not one.

    The service repeats the request URI as the last line of the report; it is
    left out, since the caller knows what it asked for.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return None
    if root.tag != f"{{{NAMESPACES['ows']}}}ExceptionReport":
        return None
    texts = [(element.text or "").strip()
             for element in root.iterfind("ows:Exception/ows:ExceptionText", NAMESPACES)]
    return " ".join(text for text in texts if text and not text.startswith("URI:"))


@dataclass
class FmiClient:
    """A rate-limited, retrying client for FMI's lightning stored query.

    Parameters
    ----------
    url : str
        The WFS endpoint.
    delay : float
        Minimum seconds between the *start* of one request and the next.
    retries : int
        How many times a retryable failure is tried again before giving up.
    timeout : float
        Seconds to wait for a response.
    session : requests.Session or None
        The HTTP session to use; a fresh one when omitted. Passing one is how the
        tests drive this class without a network.

    Attributes
    ----------
    requests_made : int
        HTTP requests issued, retries included.
    """

    url: str = finland_fmi.WFS_URL
    delay: float = DEFAULT_DELAY
    retries: int = DEFAULT_RETRIES
    timeout: float = DEFAULT_TIMEOUT
    session: requests.Session | None = None
    requests_made: int = dataclass_field(default=0, init=False)
    _last_request_at: float | None = dataclass_field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        # Assigned, not set by default: a requests.Session already carries a
        # "python-requests/x.y" User-Agent, which setdefault would leave in place.
        self.session.headers["User-Agent"] = USER_AGENT

    def _wait(self) -> None:
        """Sleep until :attr:`delay` seconds have passed since the last request."""
        if self._last_request_at is not None:
            remaining = self.delay - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def get(self, start: datetime.datetime, end: datetime.datetime,
            logger: logging.Logger) -> bytes:
        """The response to the request for ``[start, end)``, as bytes.

        Raises
        ------
        DownloadError
            If every attempt failed, or the service refused the request in a way
            no retry will change (a 400 with an ``ExceptionReport``, whose text is
            in the message).
        """
        parameters = query(start, end)
        for attempt in range(self.retries + 1):
            self._wait()
            self.requests_made += 1
            backoff = BACKOFF_BASE * (2 ** attempt)

            try:
                response = self.session.get(self.url, params=parameters, timeout=self.timeout)
            except requests.RequestException as error:
                reason = f"{type(error).__name__}: {error}"
                retryable = True
            else:
                if response.status_code == 200:
                    return response.content
                message = exception_text(response.content)
                reason = f"HTTP {response.status_code}" + (f": {message}" if message else "")
                retryable = response.status_code in RETRYABLE_STATUS

            if not retryable or attempt == self.retries:
                raise DownloadError(
                    f"request for {iso(start)} to {iso(end)} failed after {attempt + 1} "
                    f"attempt(s): {reason}")

            logger.warning("Request failed (%s), retrying in %.0fs [%d/%d]",
                           reason, backoff, attempt + 1, self.retries)
            time.sleep(backoff)

        raise DownloadError("unreachable")  # pragma: no cover


@dataclass(frozen=True)
class Window:
    """What one response holds.

    Attributes
    ----------
    rows : list of str
        One CSV row per stroke, without the newline: the Unix time, latitude,
        longitude and the sixteen fields, as the service wrote them.
    timestamp : str or None
        The response's ``timeStamp``: when the server answered.
    """

    rows: list[str]
    timestamp: str | None


def parse_response(content: bytes, start: datetime.datetime,
                   end: datetime.datetime) -> Window:
    """The strokes of one response for ``[start, end)``, checked.

    Raises
    ------
    DownloadError
        If the response is not what the service sends for this query: see the
        module docstring for every check.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise DownloadError(f"the response is not XML ({error}); it starts "
                            f"{content[:120]!r}") from None

    if root.tag == f"{{{NAMESPACES['ows']}}}ExceptionReport":
        raise DownloadError(f"the service refused the request: {exception_text(content)}")
    if root.tag != f"{{{NAMESPACES['wfs']}}}FeatureCollection":
        raise DownloadError(f"the response is a {root.tag}, not a WFS FeatureCollection")
    timestamp = root.get("timeStamp")

    members = root.findall("wfs:member", NAMESPACES)
    if not members:
        return Window(rows=[], timestamp=timestamp)
    if len(members) > 1:
        raise DownloadError(f"the response holds {len(members)} coverages where one was "
                            f"expected; the service has changed how it answers")

    coverage = members[0].find(".//gmlcov:MultiPointCoverage", NAMESPACES)
    if coverage is None:
        raise DownloadError("the response holds no MultiPointCoverage")

    fields = tuple(element.get("name") for element in
                   coverage.iterfind("gmlcov:rangeType/swe:DataRecord/swe:field", NAMESPACES))
    if fields != finland_fmi.PARAMETERS:
        raise DownloadError(f"the response's fields are {list(fields)}, not the "
                            f"{len(finland_fmi.PARAMETERS)} asked for in their order")

    points = coverage.find("gml:domainSet/gmlcov:SimpleMultiPoint", NAMESPACES)
    reference = points.get("srsName", "") if points is not None else ""
    if "crs=4258" not in reference or "time=unixtime" not in reference:
        raise DownloadError(f"the positions are not ETRS89 with a Unix time "
                            f"(srsName {reference!r})")

    positions = [line for line in
                 (points.findtext("gmlcov:positions", "", NAMESPACES)).splitlines()
                 if line.strip()]
    tuples = [line for line in
              coverage.findtext("gml:rangeSet/gml:DataBlock/gml:doubleOrNilReasonTupleList",
                                "", NAMESPACES).splitlines()
              if line.strip()]
    if len(positions) != len(tuples):
        raise DownloadError(f"{len(positions)} position(s) but {len(tuples)} value tuple(s)")

    first, last = int(start.timestamp()), int(end.timestamp())
    rows = []
    for number, (position, values) in enumerate(zip(positions, tuples), start=1):
        point = position.split()
        fields_of_stroke = values.split()
        if len(point) != 3 or len(fields_of_stroke) != len(finland_fmi.PARAMETERS):
            raise DownloadError(f"stroke {number} has {len(point)} coordinate(s) and "
                                f"{len(fields_of_stroke)} value(s), not 3 and "
                                f"{len(finland_fmi.PARAMETERS)}")
        latitude, longitude, unixtime = point
        try:
            seconds = int(unixtime)
        except ValueError:
            raise DownloadError(f"stroke {number} has the time {unixtime!r}") from None
        if not first <= seconds < last:
            raise DownloadError(f"stroke {number} at {unixtime} is outside "
                                f"[{iso(start)}, {iso(end)})")
        row = [unixtime, latitude, longitude, *fields_of_stroke]
        if any("," in value for value in row):
            raise DownloadError(f"stroke {number} has a comma in a value: {values!r}")
        rows.append(",".join(row))
    return Window(rows=rows, timestamp=timestamp)


def output_paths(output_dir: Path, month: Month) -> tuple[Path, Path]:
    """Where a month's data and sidecar go."""
    stem = f"{finland_fmi.FILE_STEM}_{month.label}"
    return output_dir / f"{stem}.csv.gz", output_dir / f"{stem}.meta.json"


def is_downloaded(output_dir: Path, month: Month) -> bool:
    """Whether the month is on disk whole: both files, and a sidecar saying so."""
    data_path, meta_path = output_paths(output_dir, month)
    if not (data_path.exists() and meta_path.exists()):
        return False
    try:
        sidecar = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return sidecar.get("month") == month.label and sidecar.get("complete") is True


def write_sidecar(meta_path: Path, month: Month, complete: bool, url: str,
                  windows: list[dict], strokes: int) -> None:
    """Write the provenance sidecar, through a ``.part`` like the data."""
    sidecar = {
        "month": month.label,
        "complete": complete,
        "strokes": strokes,
        "downloaded_at": datetime.datetime.now(UTC).isoformat(),
        "source": {
            "provider": finland_fmi.PROVIDER_FULL_NAME,
            "dataset": finland_fmi.PROVIDER_PRODUCT,
            "endpoint": url,
            "stored_query": finland_fmi.STORED_QUERY,
            "licence": finland_fmi.LICENCE,
            "attribution": finland_fmi.ATTRIBUTION,
        },
        "query": {
            "parameters": ",".join(finland_fmi.PARAMETERS),
            "interval": f"[starttime, endtime), at most {finland_fmi.MAX_REQUEST_HOURS} hours",
            "bbox": None,
        },
        "columns": list(COLUMNS),
        "coordinates": {
            "latitude, longitude": "ETRS89 (EPSG:4258) degrees, latitude first, as served",
            "unixtime": "UTC seconds since 1970-01-01, whole seconds, as served",
        },
        "values": "every value is the text the service sent; nothing is converted",
        "windows": windows,
    }
    part = meta_path.with_name(meta_path.name + ".part")
    part.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    part.replace(meta_path)


def download_month(client: FmiClient, month: Month, complete: bool, now: datetime.datetime,
                   output_dir: Path, logger: logging.Logger) -> int:
    """Download one month, returning its number of strokes.

    A complete month is fetched up to its end; an incomplete one up to ``now``.
    Nothing is left on disk if any window fails: the ``.part`` is removed and the
    previous files, if any, stay as they were.
    """
    data_path, meta_path = output_paths(output_dir, month)
    output_dir.mkdir(parents=True, exist_ok=True)
    end = month.end if complete else min(month.end, now.replace(microsecond=0))
    windows = month_windows(month.start, end)

    part = data_path.with_name(data_path.name + ".part")
    records = []
    strokes = 0
    try:
        with part.open("wb") as raw, \
                gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write((",".join(COLUMNS) + "\n").encode("utf-8"))
            for number, (start, stop) in enumerate(windows, start=1):
                window = parse_response(client.get(start, stop, logger), start, stop)
                if window.rows:
                    compressed.write(("\n".join(window.rows) + "\n").encode("utf-8"))
                records.append({"start": iso(start), "end": iso(stop),
                                "strokes": len(window.rows),
                                "server_timestamp": window.timestamp})
                strokes += len(window.rows)
                logger.info("  %s window %d/%d, %s to %s: %s stroke(s)", month.label, number,
                            len(windows), iso(start), iso(stop), f"{len(window.rows):,}")
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    # The old sidecar goes first: data without a sidecar is fetched again, so a
    # crash between the two writes cannot leave a stale "complete" behind.
    meta_path.unlink(missing_ok=True)
    part.replace(data_path)
    write_sidecar(meta_path, month, complete, client.url, records, strokes)
    logger.info("Wrote %s (%s strokes%s) and %s", data_path.name, f"{strokes:,}",
                "" if complete else ", month not complete", meta_path.name)
    return strokes


def print_months(counts: dict[str, int | None]) -> None:
    """Print the strokes-per-month table; ``None`` is a month already on disk."""
    print(f"\n  {'Month':<9} {'Strokes':>12}")
    print(f"  {'-' * 9} {'-' * 12}")
    for label, number in counts.items():
        print(f"  {label:<9} {'on disk' if number is None else f'{number:,}':>12}")
    print(f"  {'-' * 9} {'-' * 12}")
    downloaded = [number for number in counts.values() if number is not None]
    print(f"  {'Fetched':<9} {sum(downloaded):>12,}\n")


def run(args: argparse.Namespace, client: FmiClient, logger: logging.Logger,
        now: datetime.datetime) -> int:
    """Download the months asked for, returning a process exit status."""
    plan = months_to_download(args.from_year, args.to_year, now, args.include_current)
    if not plan:
        logger.warning("No month of %d-%d is complete yet; --include-current fetches the "
                       "month in progress", args.from_year, args.to_year)
        return 0

    counts: dict[str, int | None] = {}
    for month, complete in plan:
        if complete and not args.overwrite and is_downloaded(args.output_dir, month):
            logger.info("%s is already on disk; skipping (pass --overwrite to fetch it again)",
                        month.label)
            counts[month.label] = None
            continue
        counts[month.label] = download_month(client, month, complete, now, args.output_dir,
                                             logger)
    print_months(counts)
    return 0


def parse_arguments(argv: list[str] | None = None,
                    now: datetime.datetime | None = None) -> argparse.Namespace:
    """Parse the command line. ``now`` is the current instant, for the year checks."""
    current_year = (now or datetime.datetime.now(UTC)).year
    parser = argparse.ArgumentParser(
        prog="download_lightnings",
        description="Download the lightning strokes of the Finnish Meteorological Institute "
                    "from its open-data WFS, one file per UTC month.",
        epilog=f"Every stroke of the served area is fetched. FMI open data is licensed CC BY "
               f"4.0; credit it as: {finland_fmi.ATTRIBUTION}.",
    )
    parser.add_argument("--from-year", type=int, required=True, metavar="YEAR",
                        help=f"first year to download (from {FIRST_YEAR})")
    parser.add_argument("--to-year", type=int, metavar="YEAR",
                        help="last year to download, included (default: --from-year)")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."),
                        help="directory to write the monthly files into "
                             "(default: the current directory)")
    parser.add_argument("--overwrite", action="store_true",
                        help="fetch again the months already on disk")
    parser.add_argument("--include-current", action="store_true",
                        help="also fetch the months not complete yet, up to now; the next "
                             "run fetches them again")

    polite = parser.add_argument_group(
        "politeness", "the service allows 600 requests every five minutes and 20,000 a day")
    polite.add_argument("--delay", type=float, default=DEFAULT_DELAY, metavar="SECONDS",
                        help=f"seconds between requests (default: {DEFAULT_DELAY})")
    polite.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"retries per failing request (default: {DEFAULT_RETRIES})")
    polite.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                        help=f"seconds to wait for a response (default: {DEFAULT_TIMEOUT})")

    parser.add_argument("--url", default=finland_fmi.WFS_URL,
                        help=f"the WFS endpoint (default: {finland_fmi.WFS_URL})")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")

    arguments = parser.parse_args(argv)
    if arguments.to_year is None:
        arguments.to_year = arguments.from_year
    if arguments.from_year < FIRST_YEAR:
        parser.error(f"the archive starts in {FIRST_YEAR}")
    if arguments.to_year < arguments.from_year:
        parser.error("--to-year cannot be before --from-year")
    if arguments.to_year > current_year:
        parser.error(f"{arguments.to_year} has not started")
    if arguments.delay < 0:
        parser.error("--delay cannot be negative")
    if arguments.retries < 0:
        parser.error("--retries cannot be negative")
    return arguments


def main(argv: list[str] | None = None) -> int:
    now = datetime.datetime.now(UTC)
    args = parse_arguments(argv, now)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("fmi-download")

    client = FmiClient(url=args.url, delay=args.delay, retries=args.retries,
                       timeout=args.timeout)
    started = time.monotonic()
    try:
        return run(args, client, logger, now)
    except DownloadError as error:
        logger.error("%s", error)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        logger.warning("Interrupted; the month in progress was not written")
        return 130
    finally:
        logger.info("%d request(s) in %.0fs", client.requests_made,
                    time.monotonic() - started)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
