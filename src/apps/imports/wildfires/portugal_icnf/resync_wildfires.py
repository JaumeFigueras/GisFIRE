#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resync the ICNF wildfires against the WFS the archives were exported from.

The bulk import reads ``SHAPE-ZIP`` archives, and a shapefile's DBF has no
datetime type: ``DH_Inicio``, ``DH_1Interv``, ``DH_Fim`` and ``Edicao`` are
``xsd:dateTime`` at the source and arrive **truncated to dates**. A fire the WFS
reports as starting at ``2024-01-31T20:03:00Z`` is in the archive as
``2024-01-31``, which the import stores as local midnight and marks
:data:`~src.providers.portugal_icnf.PRECISION_DAY` — twenty hours out, and honestly
labelled as such.

This application goes back to the WFS and replaces what the export lost. While it
is there it refreshes every other attribute too: the archives are a snapshot and
the ICNF revises records, so the cause, the burnt-area splits, the locality and
the ANEPC code are all re-read. It costs nothing extra — they arrive in the same
response.

Run it after the import::

    python3 -m src.apps.imports.wildfires.portugal_icnf.resync_wildfires

The times really are UTC
------------------------

The WFS returns ``2025-01-02T20:16:00Z``, and a ``Z`` cannot be taken on trust —
GeoServer will happily stamp one onto a local wall-clock reading. It was checked
against the dates the archives published, for the 55 fires of 2025 where the two
readings fall on different calendar days (near midnight in summer, when Lisbon is
UTC+1):

============================================================  ==========
Reading                                                       Agreement
============================================================  ==========
published date == local date, treating ``Z`` as real UTC      2084/2084
published date == the date of the ``Z`` string as written     2029/2084
============================================================  ==========

So the values are genuine instants and are stored **unchanged**. This is the one
place in the project where a published datetime needs no conversion, and it is
why the SQL below has none of the ``AT TIME ZONE`` the import needs.

:attr:`~src.data_model.wildfire.Wildfire.time_zone` is left alone. Nothing is
derived from it any more, but it is still what turns a stored instant back into
the wall-clock time the ICNF would print.

One request per layer
---------------------

The server is GeoServer with ``ImplementsResultPaging``, ``CQL_FILTER`` and
``application/json``, and asking for :data:`PROPERTIES` drops the geometry from
the response. A whole year then fits in one request — 2025 is 2 084 features in
350 KB — so the twelve layers that carry dates cost about a dozen requests.

The geometry is deliberately **not** re-read. It would multiply the payload many
times over to rewrite perimeters that no attribute of this application depends
on; the archives' geometry is what the import stored and it stays.

Layers are walked newest first, and within a layer features come back sorted by
start date descending, so the most recent data is corrected first and an
interrupted run has done the most useful part.

Fires with no identifier are not asked for
------------------------------------------

901 of the 20 475 fires in the dated layers are polygons the ICNF could not match
to a record in its fire database. They carry no ``Cod_SGIF`` and no ``Cod_ANEPC``,
so nothing can be matched to them — and there is nothing to match: the WFS holds
``Ano``, ``AreaHaSIG`` and, for seven of them, a ``DH_Inicio`` that is already
local midnight, which is exactly what the database has. They are excluded at the
server with ``CQL_FILTER`` rather than fetched and discarded.

Being polite to the server
--------------------------

Nothing is known about the ICNF's rate limits, so requests are spaced by
:data:`DEFAULT_DELAY` seconds and never overlap. A failed request is retried with
exponential backoff, honouring ``Retry-After`` when the server sends one; a layer
that still fails is reported and the run moves on to the next, so one bad layer
does not cost the other eleven.

Each layer is committed on its own, which is what makes the application
restartable: a run that dies half way leaves whole layers done, and re-running is
harmless because every write is idempotent — a row already carrying the WFS's
values is not written again.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from typing import Any
from typing import Iterator

import requests

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.wildfires.portugal_icnf.import_wildfires import upsert_causes
from src.providers import portugal_icnf

# The plumbing every importer shares, re-exported so this module reads as one
# application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import database_url  # noqa: F401
from src.apps.imports.common import resolve_database_settings  # noqa: F401

#: The WFS the archives are an export of, from :mod:`src.providers.portugal_icnf`.
DEFAULT_URL = portugal_icnf.PROVIDER_URL

#: WFS version. 2.0.0 is what brings ``count``/``startIndex`` paging; the 1.0.0
#: the archives' ``wfsrequest.txt`` uses has only ``maxFeatures``.
WFS_VERSION = "2.0.0"

#: GeoServer's JSON output. Parsing GML for twenty scalar fields would be work for
#: nothing.
OUTPUT_FORMAT = "application/json"

#: The attributes read back, in the order the model wants them. ``Shape`` is
#: absent on purpose — see the module docstring — and asking for a property list
#: at all is what makes the response small enough to take a year at a time.
PROPERTIES = (
    "Cod_SGIF", "Cod_ANEPC", "Ano", "DH_Inicio", "DH_1Interv", "DH_Fim", "Duracao_m",
    "PI_DICOFRE", "PI_NUTS3", "PI_Distrit", "PI_Conc", "PI_Freg", "PI_Local",
    "Causa_Cod", "Causa_Tipo", "Causa_Desc",
    "AreaHaSIG", "AreaHaSGIF", "AreaHaPov", "AreaHaMato", "AreaHaAgri", "Edicao",
)

#: Leaves the unidentifiable fires on the server. See the module docstring.
CQL_FILTER = "Cod_SGIF IS NOT NULL"

#: Features per request. A layer fits in one page at this size — the largest is
#: 2 838 features — so paging is a safety net rather than the normal path, but it
#: has to work: a layer that grows past it must not be silently truncated.
DEFAULT_PAGE_SIZE = 5000

#: Seconds between requests. Two seconds because a whole layer comes back in one
#: of them, so the run is a dozen requests over half a minute either way and there
#: is nothing to gain by pressing harder on a server whose limits are unknown.
DEFAULT_DELAY = 2.0

#: How many times a failing request is retried before its layer is given up on.
DEFAULT_RETRIES = 4

#: Seconds before the first retry; doubled each time.
BACKOFF_BASE = 2.0

#: Longest a ``Retry-After`` is waited for. A server asking for more than this is
#: capped rather than obeyed: the retry budget then runs out, the layer is
#: reported as failed and the run moves on instead of sitting idle for an hour.
MAX_RETRY_AFTER = 120.0

#: Seconds to wait for a response.
DEFAULT_TIMEOUT = 120.0

#: Status codes worth retrying: the server is overloaded or briefly broken, not
#: refusing the request. A 400 or a 404 would fail identically however often it is
#: sent, and retrying it only delays the report.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: The layers to resync and how many fires each has to offer, newest first.
#:
#: Data-driven rather than a hard-coded list of years: a layer is worth querying
#: exactly when it holds a fire with an identifier to match on, which is the same
#: thing as its era publishing dates at all. The 1975-2013 layers have no
#: ``Cod_SGIF`` anywhere and so never appear.
LAYERS_SQL = """
SELECT source_layer, count(*) AS identified
FROM icnf_wildfire
WHERE sgif_code IS NOT NULL
GROUP BY source_layer
ORDER BY source_layer DESC
"""

#: Holds one layer's features for the length of its transaction.
#:
#: Column names match the published attributes lower-cased, which is what
#: :func:`~src.apps.imports.wildfires.portugal_icnf.import_wildfires.upsert_causes`
#: reads, so the cause handling is shared with the import rather than written
#: twice.
STAGING_DDL = """
CREATE TEMPORARY TABLE icnf_wfs_resync (
    cod_sgif text PRIMARY KEY,
    cod_anepc text,
    ano integer,
    dh_inicio timestamptz,
    dh_1interv timestamptz,
    dh_fim timestamptz,
    duracao_m integer,
    pi_dicofre text,
    pi_nuts3 text,
    pi_distrit text,
    pi_conc text,
    pi_freg text,
    pi_local text,
    causa_cod text,
    causa_tipo text,
    causa_desc text,
    areahasig double precision,
    areahasgif double precision,
    areahapov double precision,
    areahamato double precision,
    areahaagri double precision,
    edicao timestamptz
) ON COMMIT DROP
"""

STAGING_INSERT = """
INSERT INTO icnf_wfs_resync VALUES (
    :cod_sgif, :cod_anepc, :ano, :dh_inicio, :dh_1interv, :dh_fim, :duracao_m,
    :pi_dicofre, :pi_nuts3, :pi_distrit, :pi_conc, :pi_freg, :pi_local,
    :causa_cod, :causa_tipo, :causa_desc,
    :areahasig, :areahasgif, :areahapov, :areahamato, :areahaagri, :edicao
)
ON CONFLICT (cod_sgif) DO NOTHING
"""

#: Fires whose **date** the ICNF has changed, as opposed to the time of day the
#: export threw away. Counted before the update, because afterwards there is
#: nothing left to compare against.
#:
#: The comparison is between local dates, not instants: every stored start is
#: local midnight on the published day, so comparing instants would report all
#: 19 568 as changed.
REVISED_DATES_SQL = """
SELECT count(*)
FROM icnf_wildfire AS fire
JOIN wildfire AS parent ON parent.id = fire.id
JOIN icnf_wfs_resync AS wfs ON wfs.cod_sgif = fire.sgif_code
WHERE fire.source_layer = :source_layer
  AND wfs.dh_inicio IS NOT NULL
  AND (parent.start_date_time AT TIME ZONE parent.time_zone)::date
      IS DISTINCT FROM (wfs.dh_inicio AT TIME ZONE parent.time_zone)::date
"""

#: Starts that land exactly on local midnight once corrected.
#:
#: The WFS publishes a ``dateTime``, so the row is marked
#: :data:`~src.providers.portugal_icnf.PRECISION_MINUTE` — but midnight is also what a
#: record with no time of day looks like, and the two cannot be told apart. The
#: count is reported so the claim is visible rather than implied.
MIDNIGHT_SQL = """
SELECT count(*)
FROM icnf_wildfire AS fire
JOIN wildfire AS parent ON parent.id = fire.id
JOIN icnf_wfs_resync AS wfs ON wfs.cod_sgif = fire.sgif_code
WHERE fire.source_layer = :source_layer
  AND wfs.dh_inicio IS NOT NULL
  AND (wfs.dh_inicio AT TIME ZONE parent.time_zone)::time = TIME '00:00'
"""

#: The instants, onto the parent table.
#:
#: Stored as they arrive: the WFS publishes UTC and the column is ``timestamptz``,
#: which *is* an instant, so there is nothing to convert. Contrast the import,
#: which has to read a naive date as local midnight.
#:
#: ``IS DISTINCT FROM`` on the whole row is what makes the application idempotent
#: and the count honest: a fire already carrying these values is not written, so
#: ``updated_at`` moves only for a fire that really changed and the row count is
#: the number of changes rather than the number of rows looked at.
UPDATE_PARENT_SQL = """
UPDATE wildfire AS parent
SET start_date_time = COALESCE(wfs.dh_inicio, parent.start_date_time),
    end_date_time = wfs.dh_fim
FROM icnf_wildfire AS fire, icnf_wfs_resync AS wfs
WHERE parent.id = fire.id
  AND wfs.cod_sgif = fire.sgif_code
  AND fire.source_layer = :source_layer
  AND (parent.start_date_time, parent.end_date_time)
      IS DISTINCT FROM (COALESCE(wfs.dh_inicio, parent.start_date_time), wfs.dh_fim)
RETURNING parent.id
"""

#: Everything else, onto the provider table.
#:
#: ``date_time_precision`` becomes :data:`~src.providers.portugal_icnf.PRECISION_MINUTE`
#: only where a start actually arrived; a fire the WFS still has no date for keeps
#: whatever it had, which for these layers means ``year``.
#:
#: The cause joins on the whole ``(code, type, description)`` triple for the same
#: reason the import does: four codes name two classifications each, and joining
#: on the code alone would give a fire the meaning its code had in another year.
UPDATE_FIRE_SQL = """
UPDATE icnf_wildfire AS fire
SET anepc_code = wfs.cod_anepc,
    year = COALESCE(wfs.ano, fire.year),
    date_time_precision = CASE WHEN wfs.dh_inicio IS NOT NULL
                               THEN :precision_minute ELSE fire.date_time_precision END,
    first_response_date_time = wfs.dh_1interv,
    duration_minutes = wfs.duracao_m,
    dicofre_code = wfs.pi_dicofre,
    nuts3_name = wfs.pi_nuts3,
    district_name = wfs.pi_distrit,
    municipality_name = wfs.pi_conc,
    parish_name = wfs.pi_freg,
    place_name = wfs.pi_local,
    cause_id = cause.id,
    area_ha_gis = COALESCE(wfs.areahasig, fire.area_ha_gis),
    area_ha_sgif = wfs.areahasgif,
    area_ha_forest_stand = wfs.areahapov,
    area_ha_shrubland = wfs.areahamato,
    area_ha_agricultural = wfs.areahaagri,
    edition_date_time = wfs.edicao
FROM icnf_wfs_resync AS wfs
LEFT JOIN icnf_fire_cause AS cause
       ON cause.code = wfs.causa_cod
      AND cause.type = wfs.causa_tipo
      AND cause.description = wfs.causa_desc
WHERE wfs.cod_sgif = fire.sgif_code
  AND fire.source_layer = :source_layer
  AND (fire.anepc_code, fire.year, fire.date_time_precision, fire.first_response_date_time,
       fire.duration_minutes, fire.dicofre_code, fire.nuts3_name, fire.district_name,
       fire.municipality_name, fire.parish_name, fire.place_name, fire.cause_id,
       fire.area_ha_gis, fire.area_ha_sgif, fire.area_ha_forest_stand,
       fire.area_ha_shrubland, fire.area_ha_agricultural, fire.edition_date_time)
      IS DISTINCT FROM
      (wfs.cod_anepc, COALESCE(wfs.ano, fire.year),
       CASE WHEN wfs.dh_inicio IS NOT NULL THEN :precision_minute
            ELSE fire.date_time_precision END,
       wfs.dh_1interv, wfs.duracao_m, wfs.pi_dicofre, wfs.pi_nuts3, wfs.pi_distrit,
       wfs.pi_conc, wfs.pi_freg, wfs.pi_local, cause.id,
       COALESCE(wfs.areahasig, fire.area_ha_gis), wfs.areahasgif, wfs.areahapov,
       wfs.areahamato, wfs.areahaagri, wfs.edicao)
RETURNING fire.id
"""

#: Fires the database has and the WFS did not return. Either the ICNF has
#: withdrawn the record or it has renumbered it; both are worth knowing and
#: neither is something this application should guess about.
MISSING_SQL = """
SELECT count(*)
FROM icnf_wildfire AS fire
WHERE fire.source_layer = :source_layer
  AND fire.sgif_code IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM icnf_wfs_resync AS wfs WHERE wfs.cod_sgif = fire.sgif_code)
"""

#: Features the WFS returned whose identifier is in no row of this layer — a fire
#: the ICNF has added since the archive was exported. Reported, not inserted:
#: this application corrects what the import stored, and a new fire has no
#: geometry here to attach itself to.
UNKNOWN_SQL = """
SELECT count(*)
FROM icnf_wfs_resync AS wfs
WHERE NOT EXISTS (
    SELECT 1 FROM icnf_wildfire AS fire
    WHERE fire.sgif_code = wfs.cod_sgif AND fire.source_layer = :source_layer
)
"""


class WfsError(RuntimeError):
    """A WFS request that could not be completed after every retry."""


class Wfs:
    """A rate-limited, retrying client for one WFS endpoint.

    Parameters
    ----------
    url : str
        The endpoint, e.g. ``https://si.icnf.pt/geoserverplinia/BDG/ows``.
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

    def __init__(self, url: str = DEFAULT_URL, delay: float = DEFAULT_DELAY,
                 retries: int = DEFAULT_RETRIES, timeout: float = DEFAULT_TIMEOUT,
                 session: requests.Session | None = None) -> None:
        self.url = url
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self.requests_made = 0
        self._last_request_at: float | None = None

    def _wait(self) -> None:
        """Sleep until :attr:`delay` seconds have passed since the last request."""
        if self._last_request_at is not None:
            remaining = self.delay - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def get(self, parameters: dict[str, Any], logger: logging.Logger) -> dict:
        """Make one request and return the decoded JSON.

        Retries a connection error, a timeout and the status codes in
        :data:`RETRYABLE_STATUS`, backing off exponentially from
        :data:`BACKOFF_BASE` and honouring a ``Retry-After`` header up to
        :data:`MAX_RETRY_AFTER`. A status the server will keep refusing — a 400,
        a 404 — is not retried.

        Raises
        ------
        WfsError
            If every attempt failed, or the response was not JSON.
        """
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
                    try:
                        return response.json()
                    except ValueError as error:
                        # GeoServer reports a rejected request as an XML
                        # ows:ExceptionReport with status 200, so a body that will
                        # not parse is the server saying no rather than a truncated
                        # download — retrying it would only repeat the refusal.
                        raise WfsError(
                            f"the server returned a 200 that is not JSON, which is how "
                            f"GeoServer reports a rejected request: {error}. "
                            f"Body starts: {response.text[:200]!r}"
                        ) from error

                reason = f"HTTP {response.status_code}"
                retryable = response.status_code in RETRYABLE_STATUS
                requested = self._retry_after(response)
                if requested is not None:
                    # The server has said how long to wait; that beats guessing.
                    backoff = requested
                    reason = f"{reason}, Retry-After {requested:.0f}s"

            if not retryable or attempt == self.retries:
                raise WfsError(f"request failed after {attempt + 1} attempt(s): {reason}")

            logger.warning("WFS request failed (%s), retrying in %.0fs [%d/%d]",
                           reason, backoff, attempt + 1, self.retries)
            time.sleep(backoff)

        raise WfsError("unreachable")  # pragma: no cover

    @staticmethod
    def _retry_after(response: Any) -> float | None:
        """Return the ``Retry-After`` wait in seconds, capped, or ``None``.

        Only the delta-seconds form is read. The HTTP-date form is legal but
        GeoServer does not send it, and a half-implemented parse that silently
        returns ``None`` for a date is no worse than not trying.
        """
        header = getattr(response, "headers", {}).get("Retry-After")
        if header is None:
            return None
        try:
            return min(float(header), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            return None


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Resync the imported ICNF wildfires against the ICNF WFS, recovering "
                    "the times the shapefile export truncated and refreshing every other "
                    "published attribute.",
        epilog="Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"WFS endpoint (default: {DEFAULT_URL})")
    parser.add_argument("-l", "--layer", action="append", dest="layers",
                        help="resync only this layer, e.g. ardida_2024. Repeatable; "
                             "without it every layer that has identified fires is done, "
                             "newest first")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"minimum seconds between requests (default: {DEFAULT_DELAY})")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        help=f"features per request (default: {DEFAULT_PAGE_SIZE})")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"retries per failed request (default: {DEFAULT_RETRIES})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds to wait for a response (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and report what would change, then roll back")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def layers_to_resync(session: Session, wanted: list[str] | None,
                     logger: logging.Logger) -> list[str]:
    """Return the layers to work through, newest first.

    Raises
    ------
    RuntimeError
        If a layer was asked for by name and no fire of it is stored, which is a
        typo far more often than it is an empty layer.
    """
    available = {layer: count for layer, count in session.execute(text(LAYERS_SQL)).all()}
    if not available:
        raise RuntimeError(
            "No ICNF fire with an identifier is stored, so there is nothing to resync. "
            "Import the archives first with "
            "src.apps.imports.wildfires.portugal_icnf.import_wildfires."
        )

    if wanted is None:
        logger.info("Resyncing %d layer(s), %d identified fire(s)",
                    len(available), sum(available.values()))
        return list(available)

    unknown = [layer for layer in wanted if layer not in available]
    if unknown:
        raise RuntimeError(
            f"No identified fire is stored for layer(s) {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(available))}."
        )
    return sorted(wanted, reverse=True)


def fetch_layer(wfs: Wfs, layer: str, page_size: int, logger: logging.Logger) -> list[dict]:
    """Return every identified feature of one layer, following the paging.

    Sorted by start date descending, so the newest fires are seen first and a run
    stopped early has done the most useful part of the layer.
    """
    features: list[dict] = []
    start_index = 0
    while True:
        page = wfs.get({
            "service": "WFS",
            "version": WFS_VERSION,
            "request": "GetFeature",
            "typeName": f"BDG:{layer}",
            "outputFormat": OUTPUT_FORMAT,
            "propertyName": ",".join(PROPERTIES),
            "CQL_FILTER": CQL_FILTER,
            "sortBy": "DH_Inicio D",
            "count": page_size,
            "startIndex": start_index,
        }, logger)
        batch = page.get("features", [])
        features.extend(batch)
        # ``numberMatched`` is what the whole filtered set holds; a short page is
        # the other, older way of saying the same thing. Either ends the loop.
        if len(batch) < page_size:
            break
        start_index += len(batch)
        if start_index >= (page.get("numberMatched") or page.get("totalFeatures") or 0):
            break
    logger.debug("%s: %d feature(s) fetched", layer, len(features))
    return features


def staging_rows(features: list[dict]) -> Iterator[dict]:
    """Turn WFS features into rows for the staging table.

    Datetimes are passed through as the strings the server sent — PostgreSQL reads
    ``2025-01-02T20:16:00Z`` into a ``timestamptz`` correctly, and doing it there
    rather than in Python keeps the one place that interprets them in the same
    place that stores them.

    Features with no ``Cod_SGIF`` are skipped. The server is asked not to send
    them, so this only matters if the filter is ever changed or the server ignores
    it — but the staging table's primary key would fail on the second such row and
    take the whole layer down with it.
    """
    for feature in features:
        properties = feature.get("properties") or {}
        code = properties.get("Cod_SGIF")
        if not code:
            continue
        yield {
            "cod_sgif": code,
            "cod_anepc": properties.get("Cod_ANEPC"),
            "ano": properties.get("Ano"),
            "dh_inicio": properties.get("DH_Inicio"),
            "dh_1interv": properties.get("DH_1Interv"),
            "dh_fim": properties.get("DH_Fim"),
            "duracao_m": properties.get("Duracao_m"),
            "pi_dicofre": properties.get("PI_DICOFRE"),
            "pi_nuts3": properties.get("PI_NUTS3"),
            "pi_distrit": properties.get("PI_Distrit"),
            "pi_conc": properties.get("PI_Conc"),
            "pi_freg": properties.get("PI_Freg"),
            "pi_local": properties.get("PI_Local"),
            "causa_cod": properties.get("Causa_Cod"),
            "causa_tipo": properties.get("Causa_Tipo"),
            "causa_desc": properties.get("Causa_Desc"),
            "areahasig": properties.get("AreaHaSIG"),
            "areahasgif": properties.get("AreaHaSGIF"),
            "areahapov": properties.get("AreaHaPov"),
            "areahamato": properties.get("AreaHaMato"),
            "areahaagri": properties.get("AreaHaAgri"),
            "edicao": properties.get("Edicao"),
        }


def stage(session: Session, features: list[dict]) -> int:
    """Load one layer's features into the temporary table, returning how many."""
    session.execute(text(STAGING_DDL))
    rows = list(staging_rows(features))
    if rows:
        session.execute(text(STAGING_INSERT), rows)
    return len(rows)


def resync_layer(session: Session, wfs: Wfs, layer: str, args: argparse.Namespace,
                 logger: logging.Logger) -> dict[str, int]:
    """Fetch one layer and apply it, returning what changed.

    Returns
    -------
    dict
        ``fetched``, ``dates`` (fires whose instants changed), ``attributes``
        (fires whose other columns changed), ``revised`` (fires the ICNF moved to
        another *day*, as opposed to a time the export had truncated),
        ``midnight``, ``missing`` and ``unknown``.
    """
    features = fetch_layer(wfs, layer, args.page_size, logger)
    fetched = stage(session, features)

    parameters = {"source_layer": layer}
    revised = session.scalar(text(REVISED_DATES_SQL), parameters)
    midnight = session.scalar(text(MIDNIGHT_SQL), parameters)

    upsert_causes(session, "icnf_wfs_resync", logger)

    dates = len(session.execute(text(UPDATE_PARENT_SQL), parameters).all())
    attributes = len(session.execute(
        text(UPDATE_FIRE_SQL),
        {**parameters, "precision_minute": portugal_icnf.PRECISION_MINUTE},
    ).all())

    missing = session.scalar(text(MISSING_SQL), parameters)
    unknown = session.scalar(text(UNKNOWN_SQL), parameters)

    logger.info(
        "%s: %d fetched, %d date(s) corrected, %d attribute row(s) changed, "
        "%d moved to another day, %d start(s) at local midnight, %d not returned, %d unknown",
        layer, fetched, dates, attributes, revised, midnight, missing, unknown,
    )
    if revised:
        logger.warning("%s: %d fire(s) start on a different day than the archive published; "
                       "the WFS value has been taken", layer, revised)
    if missing:
        logger.warning("%s: %d stored fire(s) were not returned by the WFS — withdrawn or "
                       "renumbered at the source, left untouched", layer, missing)
    if unknown:
        logger.info("%s: %d fire(s) the WFS has and the database does not; this application "
                    "corrects, it does not insert", layer, unknown)

    return {"fetched": fetched, "dates": dates, "attributes": attributes, "revised": revised,
            "midnight": midnight, "missing": missing, "unknown": unknown}


def resync(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> dict[str, int]:
    """Work through every layer, returning the totals.

    Each layer is committed on its own — or rolled back, under ``--dry-run`` — so
    an interrupted run leaves whole layers done and a layer that cannot be fetched
    costs only itself.
    """
    common.require_tables(engine, ["wildfire", "icnf_wildfire", "icnf_fire_cause"], logger)

    wfs = Wfs(url=args.url, delay=args.delay, retries=args.retries, timeout=args.timeout)
    totals = {"layers": 0, "failed": 0, "fetched": 0, "dates": 0, "attributes": 0,
              "revised": 0, "midnight": 0, "missing": 0, "unknown": 0}

    with Session(engine) as session:
        layers = layers_to_resync(session, args.layers, logger)

    for index, layer in enumerate(layers, start=1):
        logger.info("[%d/%d] %s", index, len(layers), layer)
        with Session(engine) as session:
            try:
                counts = resync_layer(session, wfs, layer, args, logger)
            except WfsError as error:
                # One layer's failure must not cost the other eleven, and the
                # transaction is rolled back so the layer is untouched rather than
                # half done.
                session.rollback()
                logger.error("%s: giving up on this layer: %s", layer, error)
                totals["failed"] += 1
                continue

            if args.dry_run:
                session.rollback()
            else:
                session.commit()

        totals["layers"] += 1
        for key, value in counts.items():
            totals[key] += value

    logger.info(
        "%s%d layer(s), %d fetched, %d date(s) corrected, %d attribute row(s) changed, "
        "%d request(s) made",
        "DRY RUN: " if args.dry_run else "",
        totals["layers"], totals["fetched"], totals["dates"], totals["attributes"],
        wfs.requests_made,
    )
    if totals["failed"]:
        logger.warning("%d layer(s) could not be fetched and were left untouched",
                       totals["failed"])
    return totals


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("icnf-resync")

    try:
        settings = resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        totals = resync(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Resync failed: %s", error)
        return 1
    finally:
        engine.dispose()
    # A layer that could not be fetched is not a crash, but it is not a success
    # either: the caller has to be able to tell without reading the log.
    return 1 if totals["failed"] else 0


if __name__ == "__main__":  # pragma nocover
    sys.exit(main())
