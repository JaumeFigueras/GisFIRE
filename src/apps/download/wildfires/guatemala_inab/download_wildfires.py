#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download Guatemalan fire data from INAB's ArcGIS server.

Fetches the fire datasets of the *Sistema Integral de Información para la Gestión
del Fuego* — the layers behind INAB's *Monitoreo de Incendios* viewer — to
GeoJSON files on disk. It writes files and touches no database; loading them is a
separate job, and for the fire reports that job is
:mod:`src.apps.imports.wildfires.guatemala_inab.import_wildfires`.

Three modes, and the first is the one to run first::

    # what is there, and how much of it, per year
    python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires years

    # one year
    python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires year \\
        --year 2025 --output-dir ~/data/guatemala

    # the whole dataset, one file
    python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires all \\
        --output-dir ~/data/guatemala

``--dataset`` picks which layer; the default is the fire reports. ``--delay`` sets
the seconds between requests, and it is the setting to raise if anything about the
run looks unwelcome.

There is no WFS
---------------

The platform is ArcGIS Enterprise 11.3 and **none of the fire services has the OGC
WFS interface enabled** — one unrelated cloud-forest service on the whole server
does. What the fire layers do have is the ArcGIS REST API, readable without a
token, which is what this application speaks. If INAB ever enables the OGC
extension, ``ogr2ogr`` against the WFS would replace this program entirely; until
then a paged REST client is what getting a complete copy takes.

What is actually published
--------------------------

Five fire datasets, and they are not what their names suggest. Counts are from
2026-08-07:

``fire-reports``
    4,615 points, 2023-2026, dated to the minute. 0.9 MB.
``fire-report-updates``
    5,812 points, 2023-2026, dated to the minute. 3 MB.
``burn-scars``
    1,217 polygons, **2025 only**. 312 MB — see the page-size warning below.
``burn-scars-table``
    1,337 rows, no geometry, **2025 only**. 0.6 MB.
``burn-scars-2024``
    1,405 polygons, **no year field at all**.

**The burn-scar layers are not a historical archive.** ``burn-scars`` carries a
``fecha_ano`` and every one of its 1,217 rows says 2025; ``burn-scars-2024`` has no
date field of any kind, and what its name says about May 2024 is all there is to
go on. Anything wanting a multi-year Guatemalan burnt-area series will not find one
here.

:data:`DATASETS` is the whole registry, and adding a sixth layer is a line in it.

The fire reports are the interesting ones
------------------------------------------

``fire-reports`` (``datos_generales``) is one row per fire reported to INAB: who
called it in and how, the department, municipality, *aldea* and *finca*, the
coordinates as given and the projection they were given in, the altitude, whether
it is inside a protected area, and — the part the burn scars lack —
``fecha_hora_incendio``, **the date and time the report came in**, to the minute.

``fire-report-updates`` (``informes``) is the follow-up: when the first ground and
air crews arrived, when the fire was controlled and when it was extinguished,
whether it was a forest fire at all, and the terrain. More rows than there are
fires, because one fire can be reported on several times.

That pairing is why both are downloadable here and why neither is the default's
only job: a fire's start comes from the first and its end from the second.

.. warning::

   **These layers are hosted *views*, published with no metadata, no lineage and
   no licence statement.** INAB can republish or reindex them, and the ``objectid``
   is a view artefact rather than a stable identifier — it is not safe to treat as
   a key across two downloads.

   Every run therefore writes a ``.meta.json`` beside its data recording the exact
   URL, the query, the server's own field list and the download timestamp. That
   sidecar is the provenance the source does not supply, and it is what makes a
   figure in a thesis reproducible. Ask INAB's SIG unit for a citation and use
   statement in writing before publishing anything derived from this.

Being a polite client
---------------------

The server's limits are undocumented, so this program assumes they are tight:

* **No bulk download.** The two monitoring layers advertise
  ``maxRecordCount`` 50,000 — the whole dataset in one request — and this
  deliberately does not ask for it. ``--page-size`` defaults to
  :attr:`Dataset.default_page_size`, 500 for the point layers and **50** for the
  polygon ones, and is capped at the layer's own limit so a typo cannot turn into a
  demand for more than the service offers. The ``Extract`` capability some of these
  services expose, which would hand over a whole file at once, is never touched.
* **A delay between requests**, ``--delay``, enforced between the *start* of one
  request and the next so that a slow response does not shorten the gap. One second
  by default.
* **Retries with exponential backoff**, honouring ``Retry-After`` up to
  :data:`MAX_RETRY_AFTER`. A 400 or a 404 is not retried: the server will refuse it
  just as fast the second time.
* **A ``User-Agent`` that says who is calling**, so that an administrator looking at
  a log can tell this apart from a scraper and knows what they are looking at.

The fire reports come down in about ten requests and ten seconds. The burn scars
take twenty-seven requests and three minutes, because they are **312 MB** of
polygon: they are traced around raster cells, so a single scar of half a hectare
carries thousands of vertices.

.. warning::

   **This server truncates an over-large response instead of refusing it.** Asking
   for 500 burn-scar polygons produces a body of well over 100 MB that arrives cut
   off in the middle of a JSON string — not an error, not a 500, just a body that
   will not parse. It was measured doing exactly that at 32 MB in.

   That is why the page size is per-dataset rather than one number, and why a body
   that fails to parse is reported as *"the response was cut off, retry with a
   smaller --page-size"* rather than as corruption. It is not retried
   automatically: the same request would be cut off at the same place.

How paging is ended, and why not by ``exceededTransferLimit``
--------------------------------------------------------------

ArcGIS reports "there is more" in a flag whose *position moves*: in the GeoJSON of
a feature layer it is absent, and in the GeoJSON of a table it is nested under
``properties``. Trusting it would work on four of these five datasets and silently
truncate the fifth.

So :func:`fetch_page` ends a run on a **short page** — fewer features than were
asked for — which is true of every ArcGIS version and both response shapes. And
because a short page could also be a truncated response, the expected count is
fetched *first* with ``returnCountOnly`` and compared against what arrived;
a mismatch is reported at ``ERROR`` and sets the exit status.

Ordering is explicit (``orderByFields=objectid ASC``) because paging without a
sort is undefined: the server may return rows in any order, and two pages of an
unordered result can overlap or skip.

Dates come back as epoch milliseconds
--------------------------------------

ArcGIS serialises a date field as milliseconds since 1970-01-01 UTC, in GeoJSON as
in its own format. That is what the server said, so it is what gets written.

``--iso-dates`` rewrites those fields to ISO 8601 UTC on the way out, which is
worth having if the files are going to be read by a person or loaded somewhere
without a conversion step. The fields to convert are read from the layer's own
metadata rather than named here, so a field INAB adds is handled without an edit.

Requires ``requests``. No ``ogr2ogr``, no database, no credentials.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import requests

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Root of INAB's ArcGIS REST catalogue. Every dataset below hangs off it.
DEFAULT_ROOT = "https://sig.inab.gob.gt/server/rest/services"

#: The folder the fire services live in on that server.
FOLDER = "Hosted"

#: Identifies this client to whoever reads the server's access log.
#:
#: A downloader that does not say what it is looks exactly like a scraper, and the
#: reasonable response to a scraper is a block. This is cheap insurance.
USER_AGENT = "GisFIRE/1.0 (research data download; +https://github.com/JaumeFigueras/GisFIRE)"

#: Features per request, for a dataset that does not set its own.
#:
#: Deliberately far below what the server offers — the monitoring layers advertise
#: ``maxRecordCount`` 50,000, which would fetch everything in one shot. See the
#: module docstring: the limits are undocumented, the whole job is a few dozen
#: requests either way, and a small page is the difference between a program that
#: can be left running and one that gets a research group banned.
#:
#: Every dataset in :data:`DATASETS` overrides this with a
#: :attr:`Dataset.default_page_size` of its own, because the ceiling is on
#: *response bytes* and a burn-scar polygon is a thousand times a fire report.
DEFAULT_PAGE_SIZE = 500

#: Seconds between the *start* of one request and the next.
DEFAULT_DELAY = 1.0

#: How many times a failing request is retried before the run gives up.
DEFAULT_RETRIES = 4

#: Seconds before the first retry; doubled each time.
BACKOFF_BASE = 2.0

#: Longest a ``Retry-After`` is waited for. A server asking for more than this is
#: capped rather than obeyed: the retry budget then runs out and the run reports a
#: failure instead of sitting idle for an hour.
MAX_RETRY_AFTER = 120.0

#: Seconds to wait for a response.
DEFAULT_TIMEOUT = 120.0

#: Status codes worth retrying: the server is overloaded or briefly broken, not
#: refusing the request. A 400 or a 404 would fail identically however often it is
#: sent, and retrying it only delays the report.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: The CRS every dataset is requested in. All five are already EPSG:4326; asking
#: for it anyway means a layer republished on another grid arrives usable rather
#: than silently in metres.
OUTPUT_SRID = 4326

#: The ArcGIS field type that carries a date, and so the fields ``--iso-dates``
#: rewrites. Read from the layer metadata, never hard-coded — see the module
#: docstring.
DATE_FIELD_TYPE = "esriFieldTypeDate"

#: The label a year bucket gets when the record carries no date at all.
UNDATED_LABEL = "undated"


@dataclass(frozen=True)
class Dataset:
    """One downloadable layer.

    Attributes
    ----------
    key : str
        What ``--dataset`` takes.
    service : str
        The ArcGIS service name inside :data:`FOLDER`.
    layer : int
        The layer or table id within the service. Not always 0: the burn scars are
        layer 2 of their service and the scar table is 12 of its own, which is what
        a hosted view of a numbered source layer looks like.
    title : str
        One line for the ``years`` listing and the log.
    year_field : str or None
        The field a year is taken from, or ``None`` for a layer that publishes no
        year at all — ``burn-scars-2024``, where the modes needing a year say so
        rather than failing obscurely.
    year_is_date : bool
        Whether :attr:`year_field` is a date (so the year needs ``EXTRACT``) or is
        already an integer year. Both shapes occur here.
    max_record_count : int
        The layer's own advertised limit, and the cap on ``--page-size``. Recorded
        rather than fetched so that a bad ``--page-size`` is refused before any
        request is made.
    default_page_size : int
        What ``--page-size`` defaults to for *this* layer, and the reason that
        option is not one number for the whole program.

        The limit that matters is the size of the **response**, not the record
        count, and these layers differ by three orders of magnitude in bytes per
        record. A fire report is a point and a few dozen short strings; a burn scar
        is a polygon traced around raster cells and runs to about 260 kB on its
        own. Asking for 500 of the latter produces a response of well over 100 MB,
        and this server **truncates it mid-JSON** rather than refusing it — a
        failure that looks like corruption, not like a limit. See the module
        docstring.
    has_geometry : bool
        ``False`` for ``burn-scars-table``, which is an ArcGIS *table*. It still
        answers ``f=geojson``, with features that have a ``null`` geometry, so
        nothing downstream needs to special-case it.
    """

    key: str
    service: str
    layer: int
    title: str
    year_field: str | None
    year_is_date: bool
    max_record_count: int
    default_page_size: int
    has_geometry: bool = True

    def url(self, root: str = DEFAULT_ROOT) -> str:
        """The layer's REST endpoint."""
        return f"{root}/{FOLDER}/{self.service}/FeatureServer/{self.layer}"

    def query_url(self, root: str = DEFAULT_ROOT) -> str:
        """The layer's query endpoint, which is what every request here uses."""
        return f"{self.url(root)}/query"


#: Every fire dataset on the server, keyed by what ``--dataset`` takes.
#:
#: The record counts and spans in the module docstring were measured against this
#: registry on 2026-08-07. Two facts in here are the ones worth not forgetting:
#: the burn-scar layers are a single season rather than an archive, and the two
#: monitoring layers are the only ones with a real date.
DATASETS: dict[str, Dataset] = {
    "fire-reports": Dataset(
        key="fire-reports",
        service="Monitoreo_de_Incendios_Forestales_resultados",
        layer=0,
        title="Fire reports (datos_generales) — one row per fire reported to INAB",
        year_field="fecha_hora_incendio",
        year_is_date=True,
        max_record_count=50_000,
        default_page_size=500,
    ),
    "fire-report-updates": Dataset(
        key="fire-report-updates",
        service="Monitoreo_de_Incendios_Forestales_resultados",
        layer=1,
        title="Fire report updates (informes) — arrival, control and extinction times",
        year_field="fecha_hora_incendio_i",
        year_is_date=True,
        max_record_count=50_000,
        default_page_size=500,
    ),
    "burn-scars": Dataset(
        key="burn-scars",
        service="Cicatrices_Fuego_INAB_CONAP_CONRED_VECTOR_vista",
        layer=2,
        title="Burn scars (polygons) — 2025 only, not a historical archive",
        year_field="fecha_ano",
        year_is_date=False,
        max_record_count=1_000,
        # ~260 kB per polygon: 50 is a 5 MB response and 100 already times out.
        default_page_size=50,
    ),
    "burn-scars-table": Dataset(
        key="burn-scars-table",
        service="Cicatrices_fuego_table",
        layer=12,
        title="Burn scar attributes (table, no geometry) — 2025 only",
        year_field="fecha_ano",
        year_is_date=False,
        max_record_count=2_000,
        default_page_size=500,
        has_geometry=False,
    ),
    "burn-scars-2024": Dataset(
        key="burn-scars-2024",
        service="Cicatries_May2024_V1_muni_sigap_usoTierraMaga_vista",
        layer=1,
        title="Burn scars crossed with municipality / protected area / land use "
              "(May 2024, no year field)",
        year_field=None,
        year_is_date=False,
        max_record_count=1_000,
        # Polygons from the same raster tracing as burn-scars; same byte budget.
        default_page_size=50,
    ),
}

#: The default dataset: the fire reports, which are what the viewer the user sees
#: is built on and the only layer with a per-fire date.
DEFAULT_DATASET = "fire-reports"


class DownloadError(RuntimeError):
    """A request that could not be completed after every retry."""


@dataclass
class ArcGisClient:
    """A rate-limited, retrying client for one ArcGIS REST server.

    Parameters
    ----------
    delay : float
        Minimum seconds between the *start* of one request and the next. Enforced
        by :meth:`get`, so callers cannot forget it.
    retries : int
        How many times a retryable failure is tried again before giving up.
    timeout : float
        Seconds to wait for a response.
    session : requests.Session or None
        The HTTP session to use. A fresh one is created when omitted; passing one
        is how the tests drive this class without a network.

    Attributes
    ----------
    requests_made : int
        How many HTTP requests were issued, retries included. Reported at the end
        of a run so the load put on the server is visible.
    """

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

    @staticmethod
    def _retry_after(response: Any) -> float | None:
        """The ``Retry-After`` header in seconds, capped, or ``None``."""
        header = getattr(response, "headers", {}).get("Retry-After")
        if not header:
            return None
        try:
            return min(float(header), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            # The header may be an HTTP date rather than a number. Falling back to
            # the normal backoff is better than parsing two formats for a value
            # that is only ever advisory.
            return None

    def get(self, url: str, parameters: dict[str, Any], logger: logging.Logger) -> dict:
        """Make one request and return the decoded JSON.

        Retries a connection error, a timeout and the status codes in
        :data:`RETRYABLE_STATUS`, backing off exponentially from
        :data:`BACKOFF_BASE` and honouring a ``Retry-After`` up to
        :data:`MAX_RETRY_AFTER`. A status the server will keep refusing — a 400, a
        404 — is not retried.

        Raises
        ------
        DownloadError
            If every attempt failed, if the response was not JSON, or if the body
            was an ArcGIS error document.
        """
        for attempt in range(self.retries + 1):
            self._wait()
            self.requests_made += 1
            backoff = BACKOFF_BASE * (2 ** attempt)

            try:
                response = self.session.get(url, params=parameters, timeout=self.timeout)
            except requests.RequestException as error:
                reason = f"{type(error).__name__}: {error}"
                retryable = True
            else:
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError as error:
                        # Nearly always a truncated body rather than a rejection:
                        # this server cuts a large response off mid-JSON instead of
                        # refusing it, so the fix is a smaller page and the message
                        # has to say so. Not retried — the same request would be cut
                        # off at the same place.
                        raise DownloadError(
                            f"the server returned a 200 that is not valid JSON, which "
                            f"on this server means the response was cut off: {error}. "
                            f"Retry with a smaller --page-size. Body was "
                            f"{len(response.text):,} bytes and starts: "
                            f"{response.text[:120]!r}"
                        ) from error
                    # ArcGIS reports a rejected query as HTTP 200 with an "error"
                    # object in the body. Left unchecked it would look like an
                    # empty result set and a run would report success having
                    # downloaded nothing.
                    if isinstance(payload, dict) and "error" in payload:
                        detail = payload["error"]
                        raise DownloadError(
                            f"the server rejected the query: "
                            f"{detail.get('message', detail)} "
                            f"{'; '.join(detail.get('details', []))}".strip()
                        )
                    return payload

                reason = f"HTTP {response.status_code}"
                retryable = response.status_code in RETRYABLE_STATUS
                requested = self._retry_after(response)
                if requested is not None:
                    # The server has said how long to wait; that beats guessing.
                    backoff = requested
                    reason = f"{reason}, Retry-After {requested:.0f}s"

            if not retryable or attempt == self.retries:
                raise DownloadError(f"request failed after {attempt + 1} attempt(s): {reason}")

            logger.warning("Request failed (%s), retrying in %.0fs [%d/%d]",
                           reason, backoff, attempt + 1, self.retries)
            time.sleep(backoff)

        raise DownloadError("unreachable")  # pragma: no cover


def year_filter(dataset: Dataset, year: int | None) -> str:
    """The ``where`` clause selecting one year, or everything.

    Parameters
    ----------
    dataset : Dataset
        The layer being queried.
    year : int or None
        The year to select. ``None`` selects every record, including those whose
        date field is empty.

    Returns
    -------
    str
        An ArcGIS SQL ``where`` clause.

    Raises
    ------
    ValueError
        If a year is asked for on a dataset that publishes none.

    Notes
    -----
    ``EXTRACT(YEAR FROM ...)`` for a date field rather than a ``TIMESTAMP`` range,
    because the range form needs a literal syntax that differs between ArcGIS data
    stores while ``EXTRACT`` is standard SQL the server evaluates itself. It is
    verified against this server: the fire reports return 187 for 2023 either way.

    ``1=1`` rather than an empty string for "everything": an empty ``where`` is
    rejected by some ArcGIS versions, and ``1=1`` is what every ArcGIS client
    sends.
    """
    if year is None:
        return "1=1"
    if dataset.year_field is None:
        raise ValueError(
            f"{dataset.key} publishes no year field, so a year cannot be selected "
            f"from it; download it whole with the 'all' mode"
        )
    if dataset.year_is_date:
        return f"EXTRACT(YEAR FROM {dataset.year_field}) = {year:d}"
    return f"{dataset.year_field} = {year:d}"


def feature_count(client: ArcGisClient, dataset: Dataset, where: str,
                  logger: logging.Logger, root: str = DEFAULT_ROOT) -> int:
    """How many records match, asked before anything is downloaded.

    This is what makes a short page trustworthy as an end-of-data signal: the
    total is known in advance, so a page that ends the loop early can be caught
    rather than believed. See the module docstring.
    """
    payload = client.get(dataset.query_url(root),
                         {"where": where, "returnCountOnly": "true", "f": "json"},
                         logger)
    count = payload.get("count")
    if count is None:
        raise DownloadError(
            f"the server did not return a count for {dataset.key}; "
            f"got keys {sorted(payload)[:8]}"
        )
    return int(count)


def counts_by_year(client: ArcGisClient, dataset: Dataset, logger: logging.Logger,
                   root: str = DEFAULT_ROOT) -> dict[str, int]:
    """How many records the dataset holds per year.

    Returns
    -------
    dict
        Year as a string mapped to a count, oldest first, with a final
        :data:`UNDATED_LABEL` entry when any record's date field is empty.

    Notes
    -----
    One request, using the server's own ``groupByFieldsForStatistics`` rather than
    a count query per year. It is both far cheaper and complete: a per-year loop
    has to be told which years to try, and would therefore never discover the year
    that has just started.

    A record whose date is ``NULL`` groups under ``NULL`` and is reported as
    :data:`UNDATED_LABEL` rather than being dropped or folded into a year. There
    are four such fire reports and five such updates, and they exist — they are
    simply unreachable by the ``year`` mode, which is exactly what the label is
    there to say.
    """
    if dataset.year_field is None:
        raise ValueError(
            f"{dataset.key} publishes no year field, so there is nothing to count "
            f"per year; its record total is what the 'all' mode reports"
        )

    group = (f"EXTRACT(YEAR FROM {dataset.year_field})" if dataset.year_is_date
             else dataset.year_field)
    payload = client.get(dataset.query_url(root), {
        "where": "1=1",
        "groupByFieldsForStatistics": group,
        "outStatistics": json.dumps([{
            "statisticType": "count",
            "onStatisticField": "objectid",
            "outStatisticFieldName": "n",
        }]),
        "f": "json",
    }, logger)

    counts: dict[str, int] = {}
    undated = 0
    for feature in payload.get("features", []):
        attributes = feature.get("attributes", {})
        number = int(attributes.get("n") or 0)
        # The grouped column comes back under the field's own name for a plain
        # field and under a generated "EXPR_n" for an expression, so it is found
        # by elimination rather than by name.
        raw = next((value for key, value in attributes.items() if key != "n"), None)
        if raw is None:
            undated += number
        else:
            counts[str(int(raw))] = number

    ordered = {year: counts[year] for year in sorted(counts)}
    if undated:
        ordered[UNDATED_LABEL] = undated
    return ordered


def fetch_page(client: ArcGisClient, dataset: Dataset, where: str, offset: int,
               page_size: int, logger: logging.Logger,
               root: str = DEFAULT_ROOT) -> list[dict]:
    """One page of features, as GeoJSON feature dicts.

    Notes
    -----
    ``orderByFields=objectid ASC`` is not decoration: paging an unordered result is
    undefined, and two pages of one can overlap or skip records. ``objectid`` is
    the layer's own key and is always present.

    ``outSR`` is sent even though every one of these layers is already EPSG:4326 —
    see :data:`OUTPUT_SRID`.
    """
    payload = client.get(dataset.query_url(root), {
        "where": where,
        "outFields": "*",
        "outSR": OUTPUT_SRID,
        "orderByFields": "objectid ASC",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "returnGeometry": "true" if dataset.has_geometry else "false",
        "f": "geojson",
    }, logger)
    return payload.get("features") or []


def fetch_features(client: ArcGisClient, dataset: Dataset, where: str, page_size: int,
                   logger: logging.Logger, root: str = DEFAULT_ROOT,
                   expected: int | None = None) -> list[dict]:
    """Every feature matching ``where``, a page at a time.

    Parameters
    ----------
    expected : int, optional
        The count from :func:`feature_count`. Used to report progress and to
        verify the result; pass ``None`` to skip both.

    Returns
    -------
    list of dict
        The GeoJSON features, in ``objectid`` order.

    Notes
    -----
    The loop ends on a **short page**, which is the only end-of-data signal that
    works across ArcGIS versions and both response shapes — see the module
    docstring on ``exceededTransferLimit``.

    A short page is also what a truncated response looks like, which is why
    ``expected`` exists: the caller compares the two and reports a mismatch rather
    than writing a quietly incomplete file.
    """
    features: list[dict] = []
    offset = 0
    while True:
        page = fetch_page(client, dataset, where, offset, page_size, logger, root)
        features.extend(page)
        if expected:
            logger.info("  %d/%d features", len(features), expected)
        else:
            logger.info("  %d features", len(features))
        if len(page) < page_size:
            break
        offset += len(page)
        # Belt and braces: a server that ignored resultOffset would otherwise page
        # for ever, returning the same full page each time.
        if expected is not None and len(features) >= expected:
            break
    return features


def date_fields(client: ArcGisClient, dataset: Dataset, logger: logging.Logger,
                root: str = DEFAULT_ROOT) -> tuple[list[str], dict]:
    """The layer's date fields, and its full metadata document.

    Returns
    -------
    tuple of (list of str, dict)
        The names of every ``esriFieldTypeDate`` field, and the layer metadata the
        sidecar records.

    Notes
    -----
    Read from the server rather than listed here, so that ``--iso-dates`` keeps
    working when INAB adds a field and so that the sidecar's field list is the
    server's own rather than this program's idea of it.
    """
    metadata = client.get(dataset.url(root), {"f": "json"}, logger)
    names = [f["name"] for f in metadata.get("fields", [])
             if f.get("type") == DATE_FIELD_TYPE]
    return names, metadata


def to_iso(features: list[dict], fields: list[str]) -> int:
    """Rewrite epoch-millisecond date fields to ISO 8601 UTC, in place.

    Parameters
    ----------
    features : list of dict
        GeoJSON features, modified in place.
    fields : list of str
        The date fields, from :func:`date_fields`.

    Returns
    -------
    int
        How many values were rewritten.

    Notes
    -----
    ArcGIS date values are milliseconds since the Unix epoch, **UTC**, so the
    conversion needs no zone from anywhere else and cannot be ambiguous.

    A value that is not a number is left exactly as it is: a field already written
    as a string by some other tool must not be mangled by a second pass, and a
    download that changed data it did not understand would be worse than one that
    left it alone.
    """
    rewritten = 0
    for feature in features:
        properties = feature.get("properties") or {}
        for name in fields:
            value = properties.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            properties[name] = datetime.datetime.fromtimestamp(
                value / 1000.0, datetime.timezone.utc).isoformat()
            rewritten += 1
    return rewritten


def output_paths(output_dir: Path, dataset: Dataset, year: int | None) -> tuple[Path, Path]:
    """Where one download's data and sidecar go.

    Notes
    -----
    The dataset key and the year are both in the name, so a directory of these is
    self-describing and two datasets cannot overwrite each other.
    """
    stem = f"guatemala_inab_{dataset.key}_{year if year is not None else 'all'}"
    return output_dir / f"{stem}.geojson", output_dir / f"{stem}.meta.json"


def write_download(features: list[dict], data_path: Path, meta_path: Path,
                   dataset: Dataset, where: str, expected: int, metadata: dict,
                   iso_dates: bool, root: str, logger: logging.Logger) -> None:
    """Write the GeoJSON and the provenance sidecar.

    Notes
    -----
    The sidecar is not optional bookkeeping. These layers are hosted views with no
    published metadata, no lineage and no licence, and their ``objectid`` is not
    stable across republications — so what a file *is* cannot be recovered from the
    file later unless it was written down at the time. See the module docstring.
    """
    data_path.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": features}
    data_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")

    sidecar = {
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": {
            "root": root,
            "folder": FOLDER,
            "service": dataset.service,
            "layer": dataset.layer,
            "endpoint": dataset.query_url(root),
            "title": dataset.title,
        },
        "query": {
            "where": where,
            "outSR": OUTPUT_SRID,
            "orderByFields": "objectid ASC",
            "outFields": "*",
            "f": "geojson",
        },
        "records": {"expected": expected, "written": len(features)},
        "dates": {
            "format": "ISO 8601 UTC" if iso_dates else "epoch milliseconds UTC",
            "converted": iso_dates,
            "fields": [f["name"] for f in metadata.get("fields", [])
                       if f.get("type") == DATE_FIELD_TYPE],
        },
        "layer_metadata": {
            "name": metadata.get("name"),
            "type": metadata.get("type"),
            "geometryType": metadata.get("geometryType"),
            "objectIdField": metadata.get("objectIdField"),
            "maxRecordCount": metadata.get("maxRecordCount"),
            "fields": metadata.get("fields", []),
        },
        "caveats": [
            "Hosted view: INAB may republish or reindex it; objectid is not a "
            "stable identifier across downloads.",
            "The service publishes no metadata, lineage or licence statement. "
            "Request a citation and use statement from INAB's SIG unit.",
        ],
    }
    meta_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %s (%d features) and %s", data_path, len(features), meta_path.name)


def download(client: ArcGisClient, dataset: Dataset, year: int | None,
             args: argparse.Namespace, logger: logging.Logger) -> int:
    """Download one year, or the whole dataset, returning the features written.

    Returns
    -------
    int
        How many features were written, or ``-1`` if the file already existed and
        was left alone.

    Notes
    -----
    An existing file is **skipped** rather than refetched, so a run interrupted
    half way through the years resumes by being run again. ``--overwrite`` is what
    forces a refetch, which is what to use when INAB republishes a year.
    """
    data_path, meta_path = output_paths(args.output_dir, dataset, year)
    if data_path.exists() and not args.overwrite:
        logger.info("%s already exists; skipping (pass --overwrite to fetch it again)",
                    data_path.name)
        return -1

    where = year_filter(dataset, year)
    expected = feature_count(client, dataset, where, logger, args.root)
    label = f"{dataset.key} {year if year is not None else 'all years'}"
    if not expected:
        logger.warning("%s: the server reports 0 records; nothing to download", label)
        return 0

    logger.info("%s: %d record(s), %d per request", label, expected, args.page_size)
    fields, metadata = date_fields(client, dataset, logger, args.root)
    features = fetch_features(client, dataset, where, args.page_size, logger,
                              args.root, expected)

    if len(features) != expected:
        raise DownloadError(
            f"{label}: the server said {expected} record(s) and {len(features)} "
            f"arrived. The file has NOT been written. This is either a truncated "
            f"response or the layer changing underneath the run; try again, and "
            f"raise --delay if it repeats"
        )

    if args.iso_dates and fields:
        rewritten = to_iso(features, fields)
        logger.debug("Converted %d date value(s) in %s", rewritten, ", ".join(fields))

    write_download(features, data_path, meta_path, dataset, where, expected,
                   metadata, args.iso_dates, args.root, logger)
    return len(features)


def report_years(client: ArcGisClient, dataset: Dataset, args: argparse.Namespace,
                 logger: logging.Logger) -> dict[str, int]:
    """Print how many records the dataset holds per year."""
    counts = counts_by_year(client, dataset, logger, args.root)
    total = sum(counts.values())

    print(f"\n{dataset.key} — {dataset.title}")
    print(f"{dataset.query_url(args.root)}\n")
    print(f"  {'Year':<10} {'Records':>9}")
    print(f"  {'-' * 10} {'-' * 9}")
    for year, number in counts.items():
        print(f"  {year:<10} {number:>9,}")
    print(f"  {'-' * 10} {'-' * 9}")
    print(f"  {'Total':<10} {total:>9,}\n")

    if UNDATED_LABEL in counts:
        print(f"  Note: {counts[UNDATED_LABEL]} record(s) have no date and cannot be\n"
              f"  fetched by the 'year' mode. The 'all' mode includes them.\n")
    return counts


def downloadable_years(counts: dict[str, int]) -> list[int]:
    """The years of a count listing, dropping the undated bucket."""
    return sorted(int(year) for year in counts if year != UNDATED_LABEL)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog="download_wildfires",
        description="Download Guatemalan fire data from INAB's ArcGIS REST server.",
        epilog="Run the 'years' mode first: the burn-scar layers turn out to hold one "
               "season rather than an archive, which is worth knowing before "
               "downloading them. The server has no WFS and no bulk endpoint is used; "
               "everything is paged politely.",
    )
    # Optional only so that --list-datasets can be run on its own; a mode is
    # required for everything else, and the check below says so in those words
    # rather than argparse's "the following arguments are required".
    parser.add_argument("mode", nargs="?", choices=("years", "year", "all"),
                        help="'years' reports how many records exist per year and "
                             "downloads nothing; 'year' downloads one year (needs "
                             "--year); 'all' downloads the whole dataset in one file, "
                             "undated records included")
    parser.add_argument("-y", "--year", type=int,
                        help="the year to download, for the 'year' mode")
    parser.add_argument("-d", "--dataset", default=DEFAULT_DATASET, choices=sorted(DATASETS),
                        help=f"which layer to work on (default: {DEFAULT_DATASET})")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."),
                        help="directory to write the .geojson and .meta.json into "
                             "(default: the current directory)")
    parser.add_argument("--overwrite", action="store_true",
                        help="fetch a year again even if its file is already there; "
                             "without it an existing file is left alone, so an "
                             "interrupted run resumes by being run again")
    parser.add_argument("--iso-dates", action="store_true",
                        help="rewrite date fields from epoch milliseconds to ISO 8601 "
                             "UTC. Off by default: what the server sent is what gets "
                             "written")
    parser.add_argument("--list-datasets", action="store_true",
                        help="print the datasets this can download, and exit")

    polite = parser.add_argument_group(
        "politeness", "the server's limits are undocumented; these default to cautious")
    polite.add_argument("--delay", type=float, default=DEFAULT_DELAY, metavar="SECONDS",
                        help=f"seconds between requests (default: {DEFAULT_DELAY}). "
                             f"Raise it if anything about the run looks unwelcome")
    polite.add_argument("--page-size", type=int, default=None, metavar="N",
                        help="features per request. Defaults to a per-dataset value "
                             "(500 for the point layers, 50 for the polygon ones, "
                             "whose features are ~110 kB each). Capped at the layer's "
                             "own maxRecordCount; no bulk download is ever requested")
    polite.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"retries per failing request (default: {DEFAULT_RETRIES})")
    polite.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                        help=f"seconds to wait for a response (default: {DEFAULT_TIMEOUT})")

    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help=f"ArcGIS REST catalogue root (default: {DEFAULT_ROOT})")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")

    arguments = parser.parse_args(argv)

    if arguments.list_datasets:
        return arguments
    if arguments.mode is None:
        parser.error("a mode is required: 'years' to see what is there, 'year' to "
                     "download one, 'all' to download the lot. Or --list-datasets to "
                     "see which layers can be downloaded")
    if arguments.mode == "year" and arguments.year is None:
        parser.error("the 'year' mode needs --year; run the 'years' mode to see which "
                     "years the dataset holds")
    if arguments.mode != "year" and arguments.year is not None:
        parser.error(f"--year only applies to the 'year' mode, not '{arguments.mode}'")
    if arguments.delay < 0:
        parser.error("--delay cannot be negative")

    # Resolved before it is validated: the default is the dataset's, not one
    # number, so there is nothing to check until the dataset is known.
    dataset = DATASETS[arguments.dataset]
    if arguments.page_size is None:
        arguments.page_size = dataset.default_page_size
    if arguments.page_size < 1:
        parser.error("--page-size must be at least 1")

    limit = dataset.max_record_count
    if arguments.page_size > limit:
        # Capped rather than refused: the intent is obvious and the server would
        # silently clamp it anyway, which would leave the run's own paging
        # arithmetic disagreeing with what it actually received.
        parser.error(
            f"--page-size {arguments.page_size} is above the {arguments.dataset} "
            f"layer's maxRecordCount of {limit}; the server would clamp it and the "
            f"paging would then be wrong. Use {limit} or less"
        )
    return arguments


def run(args: argparse.Namespace, client: ArcGisClient, logger: logging.Logger) -> int:
    """Do whichever mode was asked for, returning a process exit status."""
    dataset = DATASETS[args.dataset]

    if args.mode == "years":
        if dataset.year_field is None:
            logger.error("%s publishes no year field, so there is nothing to count per "
                         "year. Use the 'all' mode to download it whole.", dataset.key)
            return 1
        report_years(client, dataset, args, logger)
        return 0

    if args.mode == "year":
        download(client, dataset, args.year, args, logger)
        return 0

    download(client, dataset, None, args, logger)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("inab-download")

    if args.list_datasets:
        print()
        for dataset in DATASETS.values():
            year = dataset.year_field or "none"
            print(f"  {dataset.key:<22} {dataset.title}")
            print(f"  {'':<22} year field: {year}, max page {dataset.max_record_count:,}")
        print()
        return 0

    client = ArcGisClient(delay=args.delay, retries=args.retries, timeout=args.timeout)
    started = time.monotonic()
    try:
        status = run(args, client, logger)
    except (DownloadError, ValueError) as error:
        logger.error("%s", error)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        logger.warning("Interrupted; files already written are complete and a re-run "
                       "will skip them")
        return 130
    finally:
        logger.info("%d request(s) in %.0fs", client.requests_made,
                    time.monotonic() - started)
    return status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
