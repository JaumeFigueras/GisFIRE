#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download the South Korean wildfire history from the Safemap open API.

Fetches *산불발생이력* (wildfire occurrence history), the Korea Forest Service
(산림청) record of every wildfire, as republished by the Ministry of the Interior
and Safety's *생활안전지도* (Safemap) open API as service ``IF_0088``. It writes a
GeoJSON file on disk and touches no database.

Two modes::

    # how many records there are — one request, downloads nothing
    python3 -m src.apps.download.wildfires.south_korea_kfs.download_wildfires count

    # the whole dataset, one file
    python3 -m src.apps.download.wildfires.south_korea_kfs.download_wildfires all \\
        --output-dir ~/data/south_korea

The service key
---------------

Every request needs a Safemap service key (인증키), read from ``--service-key`` or,
better, from the ``SAFEMAP_SERVICE_KEY`` environment variable (``.env`` works), so
that it stays out of the shell history. The key never reaches the log or the
sidecar: every URL and error message written anywhere has it replaced by ``***``.

**Being issued a key is not enough.** Safemap authorises a key *per API*: after
the key is issued, the dataset page itself has a 사용신청 (usage application)
button, and until that application is approved the key is answered with result
code 30, ``SERVICE_KEY_IS_NOT_REGISTERED_ERROR`` — exactly what a made-up key
gets. This program reports that case in those words rather than as a generic
failure.

What the API offers, and what it does not
-----------------------------------------

The record endpoint takes ``serviceKey``, ``pageNo``, ``numOfRows`` and
``returnType`` and **nothing else**: no year, no region, no sort order. A
partial download cannot be asked for, so there is no ``year`` mode; the whole
history comes down and :func:`counts_by_year` reports its spread at the end. The
dataset is a few thousand rows, a dozen or so requests.

Each record is all strings, and is kept that way:

``occu_date`` / ``occu_year`` / ``occu_mt`` / ``occu_de`` / ``occu_tm`` / ``occu_day``
    Ignition date (``YYYYMMDD``), its parts, the time as ``HHMM`` and the weekday
    in Korean. The parts are zero-padded in some years and not in others
    (``04`` and ``4``), which is why ``occu_date`` is the one to parse.
``end_year`` / ``end_mt`` / ``end_de`` / ``end_tm``
    When the fire was put out. There is no ``end_date``.
``adres`` / ``rn_adres``
    Lot-number address and road-name address.
``resn``
    The cause, as free Korean text (``입산자 실화``: careless hiker, ``쓰레기
    소각``: rubbish burning, ``기타(직접입력)``: other).
``ar`` / ``amount``
    Burnt area in hectares and damage in won.
``ctprvn_cd`` / ``sgg_cd`` / ``emd_cd``
    Province, municipality and neighbourhood codes (2, 5 and 8 digits).
``x`` / ``y``
    The location, in **EPSG:3857** (Web Mercator metres), although the page
    does not say so. :func:`to_feature` keeps them verbatim and adds a WGS84
    point geometry, converted exactly by the spherical Mercator inverse.
``objt_id``
    The serial number, which is what duplicates are checked against.

Errors come back as HTTP 500
----------------------------

The service answers an application error — a bad key, a missing parameter — with
HTTP **500** and a normal body whose ``header.resultCode`` says what went wrong.
:meth:`SafemapClient.get` therefore reads the body *before* it looks at the status,
and decides whether to retry from the result code (:data:`RETRYABLE_CODES`), not
from the 500, which would otherwise retry a refused key four times.

Being a polite client
---------------------

* ``--page-size`` defaults to :data:`DEFAULT_PAGE_SIZE`. The service documents no
  ceiling, so the size of every page is checked: if the server hands back fewer
  rows than were asked for while more remain, it is clamping, ``pageNo``
  arithmetic would skip records, and the run stops and says so.
* A delay between the *start* of one request and the next, ``--delay``.
* Retries with exponential backoff for transient failures only.
* A ``User-Agent`` that says who is calling.

Every download is checked against ``totalCount`` and for duplicate ``objt_id``
before the file is written, and a ``.meta.json`` sidecar records the request, the
counts and the download time.

.. warning::

   The data is licensed **KOGL Type 4** (공공누리 제4유형): attribution required,
   **no commercial use, no derivative works**. Research use with attribution is
   fine; publishing a modified version of the dataset is not. The sidecar records
   this.

Requires ``requests``. No database, no ``ogr2ogr``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
import os
import sys
import time

from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import requests

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The record endpoint. ``http://`` is redirected here, so it is asked for directly.
DEFAULT_URL = "https://www.safemap.go.kr/openapi2/IF_0088"

#: The dataset page, recorded in the sidecar as the human-readable source.
SOURCE_PAGE = "https://www.safemap.go.kr/opna/data/dataViewRenew.do?objtId=207"

#: The environment variable the service key is read from.
SERVICE_KEY_VARIABLE = "SAFEMAP_SERVICE_KEY"

#: Identifies this client to whoever reads the server's access log.
USER_AGENT = "GisFIRE/1.0 (research data download; +https://github.com/JaumeFigueras/GisFIRE)"

#: Records per request. The service documents no ceiling; this is well below the
#: 1,000 that Korean government APIs usually allow, and the run checks that every
#: page is as long as it should be.
DEFAULT_PAGE_SIZE = 500

#: Seconds between the *start* of one request and the next.
DEFAULT_DELAY = 1.0

#: How many times a failing request is retried before the run gives up.
DEFAULT_RETRIES = 4

#: Seconds before the first retry; doubled each time.
BACKOFF_BASE = 2.0

#: Seconds to wait for a response.
DEFAULT_TIMEOUT = 60.0

#: The result code of a successful call.
OK_CODE = "00"

#: The result code for "no data", which is an empty result rather than a failure.
NO_DATA_CODE = "03"

#: Result codes worth retrying: the service failed, not the request. These are the
#: Korean public-data-portal codes 01 (application error), 02 (database error),
#: 04 (HTTP error) and 05 (service timeout).
RETRYABLE_CODES = frozenset({"01", "02", "04", "05"})

#: What to tell the user for the result codes that need a person to act.
CODE_ADVICE = {
    "20": "access to this service is denied for the key",
    "21": "the key has been temporarily disabled",
    "22": "the daily request quota for the key is exhausted; try again tomorrow",
    "30": "the key is not registered for this API. Being issued a key is not "
          "enough: apply for this dataset with the 사용신청 button on "
          f"{SOURCE_PAGE} and wait for the approval",
    "31": "the key's usage period has expired; renew it on Safemap",
    "32": "the calling IP address is not registered for the key",
    "33": f"no service key was sent; pass --service-key or set {SERVICE_KEY_VARIABLE}",
}

#: HTTP statuses retried when the body carries no result code to go by.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Radius of the sphere EPSG:3857 projects from, in metres.
WEB_MERCATOR_RADIUS = 6378137.0

#: A generous box around South Korea, (west, south, east, north) in degrees. A
#: point outside it is still written, but counted and reported: it means either a
#: bad coordinate or that the service has changed its coordinate system.
SOUTH_KOREA_BOUNDS = (124.0, 32.5, 132.0, 39.0)

#: The year bucket for a record without a usable ``occu_year``.
UNDATED_LABEL = "undated"

LICENCE = ("KOGL Type 4 (공공누리 제4유형): attribution required, no commercial use, "
           "no derivative works")


class DownloadError(RuntimeError):
    """A request that could not be completed, or a download that does not add up."""


def redact(text: str, secret: str | None) -> str:
    """``text`` with ``secret`` replaced by ``***``, and its URL-encoded form too."""
    if not secret:
        return text
    encoded = requests.utils.quote(secret, safe="")
    return text.replace(secret, "***").replace(encoded, "***")


@dataclass
class SafemapClient:
    """A rate-limited, retrying client for the Safemap open API.

    Parameters
    ----------
    service_key : str
        The Safemap key, sent as ``serviceKey`` with every request and redacted from
        every message this class produces.
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

    service_key: str
    delay: float = DEFAULT_DELAY
    retries: int = DEFAULT_RETRIES
    timeout: float = DEFAULT_TIMEOUT
    session: requests.Session | None = None
    requests_made: int = dataclass_field(default=0, init=False)
    _last_request_at: float | None = dataclass_field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def _wait(self) -> None:
        """Sleep until :attr:`delay` seconds have passed since the last request."""
        if self._last_request_at is not None:
            remaining = self.delay - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def get(self, url: str, page: int, page_size: int, logger: logging.Logger) -> dict:
        """Fetch one page and return its ``body``.

        Raises
        ------
        DownloadError
            If every attempt failed, if the response was not JSON, or if the service
            refused the request with a result code no retry will change.
        """
        parameters = {"serviceKey": self.service_key, "pageNo": page,
                      "numOfRows": page_size, "returnType": "json"}
        for attempt in range(self.retries + 1):
            self._wait()
            self.requests_made += 1
            backoff = BACKOFF_BASE * (2 ** attempt)

            try:
                response = self.session.get(url, params=parameters, timeout=self.timeout)
            except requests.RequestException as error:
                # requests puts the full URL, key included, in its messages.
                reason = redact(f"{type(error).__name__}: {error}", self.service_key)
                retryable = True
            else:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                header = payload.get("header") if isinstance(payload, dict) else None
                code = str(header.get("resultCode", "")) if isinstance(header, dict) else ""

                if code in (OK_CODE, NO_DATA_CODE):
                    return payload.get("body") or {}
                if code:
                    # Read before the HTTP status: this service sends every
                    # application error as a 500, and only the code says whether
                    # trying again can help.
                    message = header.get("resultMsg", "")
                    reason = f"result code {code} {message}".strip()
                    if code not in RETRYABLE_CODES:
                        advice = CODE_ADVICE.get(code)
                        raise DownloadError(
                            f"the service refused the request ({reason})"
                            + (f": {advice}" if advice else "")
                        )
                    retryable = True
                elif response.status_code == 200:
                    raise DownloadError(
                        "the service returned a 200 without a result code; body starts "
                        + repr(redact(getattr(response, "text", "")[:200], self.service_key))
                    )
                else:
                    reason = f"HTTP {response.status_code}"
                    retryable = response.status_code in RETRYABLE_STATUS

            if not retryable or attempt == self.retries:
                raise DownloadError(f"request failed after {attempt + 1} attempt(s): {reason}")

            logger.warning("Request failed (%s), retrying in %.0fs [%d/%d]",
                           reason, backoff, attempt + 1, self.retries)
            time.sleep(backoff)

        raise DownloadError("unreachable")  # pragma: no cover


def page_items(body: dict) -> list[dict]:
    """The records of one page, whatever shape the service wrapped them in.

    Notes
    -----
    The usual Korean public-API envelope is ``body.items.item``, and ``item`` is a
    list — except that serialisers of this family turn a one-element list into a
    bare object and an empty one into ``{}`` or ``""``. All of them are handled, as
    is ``items`` being the list itself.
    """
    items = body.get("items")
    if isinstance(items, list):
        return items
    if not isinstance(items, dict):
        return []
    item = items.get("item")
    if isinstance(item, list):
        return item
    if isinstance(item, dict):
        return [item]
    return []


def total_count(client: SafemapClient, url: str, logger: logging.Logger) -> int:
    """How many records the service holds, from one single-row request."""
    body = client.get(url, 1, 1, logger)
    count = body.get("totalCount")
    if count is None:
        raise DownloadError(f"the service did not return a totalCount; got keys {sorted(body)}")
    return int(count)


def fetch_records(client: SafemapClient, url: str, page_size: int,
                  logger: logging.Logger) -> tuple[list[dict], int]:
    """Every record, a page at a time.

    Returns
    -------
    tuple of (list of dict, int)
        The records, and the ``totalCount`` the service reported with the first
        page.

    Raises
    ------
    DownloadError
        If a page comes back shorter than asked for while records remain — the
        server is clamping ``numOfRows`` and paging by ``pageNo`` would skip rows —
        or if a page comes back empty before the total is reached.
    """
    records: list[dict] = []
    expected: int | None = None
    page = 1
    while expected is None or len(records) < expected:
        body = client.get(url, page, page_size, logger)
        if expected is None:
            expected = int(body.get("totalCount") or 0)
        items = page_items(body)
        records.extend(items)
        logger.info("  page %d: %d/%d records", page, len(records), expected)

        remaining = expected - (len(records) - len(items))
        if len(items) < min(page_size, remaining):
            raise DownloadError(
                f"page {page} held {len(items)} record(s) where {min(page_size, remaining)} "
                f"were expected. The service is probably capping the page size, which "
                f"makes paging skip records; retry with a smaller --page-size"
            )
        page += 1
    return records, expected or 0


def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Longitude and latitude, in degrees, of an EPSG:3857 point.

    The inverse of the spherical Mercator, which is exact for EPSG:3857 by
    definition, so no projection library is needed.
    """
    longitude = math.degrees(x / WEB_MERCATOR_RADIUS)
    latitude = math.degrees(math.atan(math.sinh(y / WEB_MERCATOR_RADIUS)))
    return longitude, latitude


def to_feature(record: dict) -> dict:
    """A GeoJSON feature for one record.

    The record becomes the properties unchanged, ``x`` and ``y`` included; the
    geometry is the WGS84 point, rounded to 7 decimals (about 1 cm), or ``null``
    when the coordinates are missing or not numbers.
    """
    geometry = None
    try:
        x, y = float(record["x"]), float(record["y"])
    except (KeyError, TypeError, ValueError):
        pass
    else:
        if math.isfinite(x) and math.isfinite(y):
            longitude, latitude = web_mercator_to_wgs84(x, y)
            geometry = {"type": "Point",
                        "coordinates": [round(longitude, 7), round(latitude, 7)]}
    return {"type": "Feature", "geometry": geometry, "properties": dict(record)}


def outside_bounds(features: list[dict]) -> int:
    """How many located features fall outside :data:`SOUTH_KOREA_BOUNDS`."""
    west, south, east, north = SOUTH_KOREA_BOUNDS
    count = 0
    for feature in features:
        if feature["geometry"] is None:
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        if not (west <= longitude <= east and south <= latitude <= north):
            count += 1
    return count


def duplicate_ids(records: list[dict]) -> list[str]:
    """The ``objt_id`` values that occur more than once."""
    counts = Counter(str(record.get("objt_id")) for record in records
                     if record.get("objt_id") not in (None, ""))
    return sorted(key for key, number in counts.items() if number > 1)


def counts_by_year(records: list[dict]) -> dict[str, int]:
    """Records per ``occu_year``, oldest first, then :data:`UNDATED_LABEL` if any."""
    counts: Counter[str] = Counter()
    for record in records:
        year = str(record.get("occu_year") or "").strip()
        counts[year if year.isdigit() else UNDATED_LABEL] += 1
    ordered = {year: counts[year] for year in sorted(k for k in counts if k != UNDATED_LABEL)}
    if counts[UNDATED_LABEL]:
        ordered[UNDATED_LABEL] = counts[UNDATED_LABEL]
    return ordered


def output_paths(output_dir: Path) -> tuple[Path, Path]:
    """Where the data and the sidecar go."""
    stem = "south_korea_kfs_wildfires_all"
    return output_dir / f"{stem}.geojson", output_dir / f"{stem}.meta.json"


def write_download(features: list[dict], data_path: Path, meta_path: Path, url: str,
                   page_size: int, expected: int, years: dict[str, int],
                   logger: logging.Logger) -> None:
    """Write the GeoJSON and the provenance sidecar. The key is in neither."""
    data_path.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": features}
    data_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")

    sidecar = {
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": {
            "endpoint": url,
            "service": "IF_0088",
            "title": "산불발생이력 (wildfire occurrence history)",
            "provider": "산림청 (Korea Forest Service), 산불방지과",
            "distributor": "생활안전지도 (Safemap), Ministry of the Interior and Safety",
            "page": SOURCE_PAGE,
            "licence": LICENCE,
        },
        "query": {"numOfRows": page_size, "returnType": "json"},
        "records": {
            "expected": expected,
            "written": len(features),
            "without_geometry": sum(1 for f in features if f["geometry"] is None),
            "by_year": years,
        },
        "coordinates": {
            "geometry": "EPSG:4326, converted from x/y",
            "x_y": "EPSG:3857, as served, kept in the properties",
        },
    }
    meta_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %s (%d features) and %s", data_path, len(features), meta_path.name)


def download(client: SafemapClient, args: argparse.Namespace, logger: logging.Logger) -> int:
    """Download the whole history, returning the features written.

    Returns
    -------
    int
        How many features were written, or ``-1`` if the file already existed and
        was left alone.
    """
    data_path, meta_path = output_paths(args.output_dir)
    if data_path.exists() and not args.overwrite:
        logger.info("%s already exists; skipping (pass --overwrite to fetch it again)",
                    data_path.name)
        return -1

    records, expected = fetch_records(client, args.url, args.page_size, logger)
    if len(records) != expected:
        raise DownloadError(
            f"the service said {expected} record(s) and {len(records)} arrived. The "
            f"file has NOT been written; try again"
        )
    duplicates = duplicate_ids(records)
    if duplicates:
        # Without a sort order, a dataset that changed during the run can shift
        # rows across page boundaries, repeating some and therefore losing others.
        raise DownloadError(
            f"{len(duplicates)} objt_id value(s) arrived more than once "
            f"({', '.join(duplicates[:5])}{', ...' if len(duplicates) > 5 else ''}). "
            f"The dataset probably changed during the run. The file has NOT been "
            f"written; try again"
        )

    features = [to_feature(record) for record in records]
    unlocated = sum(1 for f in features if f["geometry"] is None)
    if unlocated:
        logger.warning("%d record(s) have no usable x/y and are written without geometry",
                       unlocated)
    outside = outside_bounds(features)
    if outside:
        logger.warning("%d point(s) fall outside South Korea once read as EPSG:3857; "
                       "check whether the service has changed its coordinate system",
                       outside)

    years = counts_by_year(records)
    write_download(features, data_path, meta_path, args.url, args.page_size, expected,
                   years, logger)
    print_years(years)
    return len(features)


def print_years(years: dict[str, int]) -> None:
    """Print the records-per-year table."""
    print(f"\n  {'Year':<10} {'Records':>9}")
    print(f"  {'-' * 10} {'-' * 9}")
    for year, number in years.items():
        print(f"  {year:<10} {number:>9,}")
    print(f"  {'-' * 10} {'-' * 9}")
    print(f"  {'Total':<10} {sum(years.values()):>9,}\n")


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog="download_wildfires",
        description="Download the Korea Forest Service wildfire history (산불발생이력) "
                    "from the Safemap open API.",
        epilog=f"The service key comes from --service-key or ${SERVICE_KEY_VARIABLE}, "
               f"and has to be approved for this dataset (사용신청 on {SOURCE_PAGE}) "
               f"before it works.",
    )
    parser.add_argument("mode", choices=("count", "all"),
                        help="'count' reports how many records there are and downloads "
                             "nothing; 'all' downloads the whole history in one file")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."),
                        help="directory to write the .geojson and .meta.json into "
                             "(default: the current directory)")
    parser.add_argument("--overwrite", action="store_true",
                        help="fetch again even if the file is already there")
    parser.add_argument("--service-key", default=os.getenv(SERVICE_KEY_VARIABLE),
                        help=f"the Safemap service key (env: {SERVICE_KEY_VARIABLE}, "
                             f"which keeps it out of the shell history)")

    polite = parser.add_argument_group(
        "politeness", "the service's limits are undocumented; these default to cautious")
    polite.add_argument("--delay", type=float, default=DEFAULT_DELAY, metavar="SECONDS",
                        help=f"seconds between requests (default: {DEFAULT_DELAY})")
    polite.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, metavar="N",
                        help=f"records per request (default: {DEFAULT_PAGE_SIZE})")
    polite.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"retries per failing request (default: {DEFAULT_RETRIES})")
    polite.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                        help=f"seconds to wait for a response (default: {DEFAULT_TIMEOUT})")

    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"the IF_0088 endpoint (default: {DEFAULT_URL})")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")

    arguments = parser.parse_args(argv)
    if not arguments.service_key:
        parser.error(f"a service key is required: set {SERVICE_KEY_VARIABLE} (in .env or "
                     f"the environment) or pass --service-key")
    if arguments.delay < 0:
        parser.error("--delay cannot be negative")
    if arguments.page_size < 1:
        parser.error("--page-size must be at least 1")
    return arguments


def run(args: argparse.Namespace, client: SafemapClient, logger: logging.Logger) -> int:
    """Do whichever mode was asked for, returning a process exit status."""
    if args.mode == "count":
        count = total_count(client, args.url, logger)
        print(f"\n  IF_0088 산불발생이력: {count:,} record(s)\n")
        return 0
    download(client, args, logger)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("kfs-download")

    client = SafemapClient(service_key=args.service_key, delay=args.delay,
                           retries=args.retries, timeout=args.timeout)
    started = time.monotonic()
    try:
        return run(args, client, logger)
    except DownloadError as error:
        logger.error("%s", redact(str(error), args.service_key))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        logger.warning("Interrupted; nothing partial has been written")
        return 130
    finally:
        logger.info("%d request(s) in %.0fs", client.requests_made,
                    time.monotonic() - started)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
