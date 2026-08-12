#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Canadian National Burned Area Composite perimeters.

One command over the directory of yearly archives::

    python3 -m src.apps.imports.wildfires.canada_nbac.import_wildfires -d /path/to/nbac/

53 zipped shapefiles, one per year, 1973 to 2025. **52,276 published polygons**
that dissolve to **51,818 fire events** and 132.7 million hectares of mapped burn —
GisFIRE's first source outside Europe and its largest polygon archive after GWIS and
GFA.

The zips are read without ever being unpacked, through GDAL's ``/vsizip/``, exactly
as the ICNF and GWIS imports read theirs.

A fire is a GID, not a polygon
-------------------------------

The published features are cut at provincial, territorial and national park
boundaries, so a fire that crossed one arrives as several polygons sharing a
``GID``. The import dissolves them — one row per ``GID``, the geometry unioned —
and keeps what the union cannot say by itself:

* ``part_count``, how many polygons became this row;
* ``crosses_admin``, whether they lay in different administrations;
* ``admin_name`` and ``admin_div``, joined with
  :data:`~src.providers.canada_nbac.ADMIN_SEPARATOR` when there is more than one;
* ``area_ha_polygon`` and ``area_ha_adjusted``, **summed**, because each published
  piece carries the area of its own piece.

458 of the 52,276 polygons are such pieces, so this affects a little under one
percent of the archive — but the one percent includes some of the largest fires in
it, which is where a boundary is most likely to be in the way.

Where the parts disagree
^^^^^^^^^^^^^^^^^^^^^^^^

Two pieces of one fire should agree about its cause, its version and how it was
mapped, and where they do not the import takes the alphabetically first and
**counts the disagreement** rather than resolving it silently. The dates are the
exception and are not a disagreement at all: NBAC's own documentation says that for
a cross-border fire it keeps the earliest agency start and the latest agency end, so
this takes ``min`` and ``max`` of each pair for exactly the same reason.

Which date a fire starts on
----------------------------

The dataset publishes two independent date pairs — satellite hotspots and
agency-reported — and for some fires neither. The import resolves the start in a
fixed order and records both what it used and how much of it is real:

======================  ===========================  ==========================
``date_source``         From                         ``date_time_precision``
======================  ===========================  ==========================
``agency``              ``AG_SDATE``                 ``day``
``hotspot``             ``HS_SDATE``                 ``day``
``year``                1 January of ``YEAR``        ``year``
======================  ===========================  ==========================

**102 of 1980's 530 fires and 39 of 2023's 2,244 publish no date at all**, and they
are imported rather than dropped: a fire with a year is still a fire, and
``date_time_precision`` is what stops anyone reading its 1 January as a date.

The end is ``AG_EDATE`` and nothing else. The last hotspot is deliberately not used
to fill it — a satellite losing sight of a fire is not an agency declaring it out,
and a column that mixed the two would make every burning duration a mixture of two
definitions.

The CRS is asserted, not read
------------------------------

The published ``.prj`` is a bare ``Canada_Lambert_Conformal_Conic`` with **no EPSG
identifier**, whose parameters are exactly EPSG:3978's. ``ogr2ogr`` is therefore
given ``-t_srs EPSG:3978``, which is a null transform if the file is what its
parameters say and a correcting one if it ever stops being — and
:func:`check_extent` then tests the staged geometry against Canada's real bounds on
that grid, so a transform that moved the archive is caught here rather than in a
map three months later.

One transaction per year
------------------------

A year is loaded, dissolved, deleted and re-inserted in one transaction, so an
interrupted run leaves the years it finished and the year it was in the middle of
exactly as it found them. **Re-importing replaces the years it reads**, which is
what makes a re-run of a revised publication supersede rather than double.

``--dry-run`` does all the work and rolls it back, including the delete, so the
numbers reported are the ones a real run would produce.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.providers import canada_nbac

#: Default name of the staging table ``ogr2ogr`` loads a year into.
DEFAULT_STAGING_TABLE = "nbac_perimeters"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The serial key GDAL puts on the staging table. Not ``fid``, for the reason the
#: Andalusian import renames it: a published attribute of that name makes GDAL
#: complain on every run.
STAGING_FID_COLUMN = "ogc_fid"

#: Layer creation options passed to ``ogr2ogr`` on top of the shared ones.
#:
#: ``PRECISION=NO`` stops GDAL turning a shapefile's declared field width into a
#: ``NUMERIC(width, scale)``. This archive needs it: ``POLY_HA`` is declared
#: ``Real (19.11)``, and ``numeric(19,11)`` has eight digits before the point where
#: the 2023 Quebec fires have six-figure hectares — 1,000,000 ha would fit, but the
#: declared scale leaves no room to spare and the widths are fiction throughout.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]

#: Every attribute the mapping reads, with the PostgreSQL type it needs, named as
#: ``ogr2ogr`` lands it — lower-cased, which is what its ``LAUNDER`` default does.
#:
#: All nineteen are published by every one of the 53 yearly archives, which is
#: unusual enough among this project's sources to be worth saying: unlike the
#: Andalusian and Greek ones, NBAC does not rename or re-spell its columns from year
#: to year. The v20240228 publication replaced numeric codes with descriptive text
#: across the whole series at once, so a re-download is consistent even where an old
#: file is not.
STAGING_COLUMNS = {
    "year": "integer",
    "nfireid": "integer",
    "gid": "text",
    "basrc": "text",
    "firemaps": "text",
    "firemapm": "text",
    "firecaus": "text",
    "hs_sdate": "date",
    "hs_edate": "date",
    "ag_sdate": "date",
    "ag_edate": "date",
    "capdate": "date",
    "poly_ha": "double precision",
    "adj_ha": "double precision",
    "adj_flag": "text",
    "admin_name": "text",
    "admin_div": "text",
    "prescribed": "text",
    "version": "text",
}

#: The loaded types each declared type will accept without a conversion, by
#: ``information_schema.data_type`` name.
#:
#: **``integer`` is tighter here than in the ICNF, DARPA and REDIAM imports**, which
#: accept a ``double precision`` as an integer because they only ever read the value.
#: This one does arithmetic with it: ``YEAR`` is published as ``Real (19.11)`` and
#: goes into ``make_date``, which has no ``double precision`` overload and fails
#: outright. Accepting the loaded type would leave that error to appear inside a
#: 400-line statement, so the column is converted instead.
COMPATIBLE_TYPES = {
    "integer": {"integer", "bigint", "smallint"},
    "double precision": {"double precision", "real", "numeric", "integer", "bigint",
                         "smallint"},
    "date": {"date", "timestamp without time zone", "timestamp with time zone"},
    "text": {"text", "character varying", "character"},
}

#: The characters trimmed off every published text attribute before it is read.
TRIMMED_CHARS = r"E' \t\r\n'"

#: What the published ``ADJ_FLAG`` and ``PRESCRIBED`` say when they mean yes. Both
#: are documented as taking the single value ``true``; the comparison is
#: case-insensitive and trimmed anyway, because a flag that started arriving as
#: ``TRUE`` should not silently become false.
FLAG_TRUE = "true"

#: Canada's real extent on EPSG:3978, in metres, widened by a margin.
#:
#: What :func:`check_extent` tests the staged geometry against. Not a tight fit: the
#: point is to catch a transform that put the archive in the wrong place or the wrong
#: units, which misses by thousands of kilometres, not to police the coastline.
PLAUSIBLE_EXTENT = (-2_600_000.0, -1_100_000.0, 3_200_000.0, 4_400_000.0)

#: The extent of what was staged, for :func:`check_extent`.
EXTENT_SQL = """
SELECT min(ST_XMin(staging.geom)) AS min_x, min(ST_YMin(staging.geom)) AS min_y,
       max(ST_XMax(staging.geom)) AS max_x, max(ST_YMax(staging.geom)) AS max_y,
       count(*) FILTER (WHERE staging.geom IS NOT NULL) AS with_geometry
FROM {staging_table} AS staging
"""

#: The years the staged archive holds fires in, after ``--year`` has been applied.
#:
#: Asked before the transform, because these are the years the import replaces. Read
#: from the **data** and never from the file name: a yearly archive is named for its
#: year, but nothing enforces that its contents agree, and 2004's publication history
#: includes fires moved between years.
STAGED_YEARS_SQL = """
SELECT DISTINCT staging.year AS year
FROM {staging_table} AS staging
WHERE staging.year IS NOT NULL AND ({year_filter})
ORDER BY year
"""

#: Removes the fires of the years about to be re-imported.
#:
#: One statement, for the reason revision e9e992e02a11 gives for the Andalusian one:
#: ``nbac_wildfire.id`` references ``wildfire``, so no order of separate statements
#: is safe while inside one statement the foreign keys are checked once at the end.
#:
#: There is no ignition to remove — NBAC publishes none — and the link to NFDB goes
#: the other way, so nothing outside these two tables points at what is deleted.
DELETE_YEARS_SQL = """
WITH doomed AS (
    SELECT id FROM nbac_wildfire WHERE year = ANY(:years)
),
removed_child AS (
    DELETE FROM nbac_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: How many of the fires about to be replaced carry a link to an NFDB report.
#:
#: Nothing writes that link yet, so this is zero on every run today. It is asked
#: because it will not always be: once the binding application exists, replacing a
#: year silently discards its work, and a re-import that did that without saying so
#: would be the kind of loss nobody notices until the report is wrong.
LINKED_SQL = """
SELECT count(*) FROM nbac_wildfire
WHERE year = ANY(:years) AND nfdb_wildfire_id IS NOT NULL
"""

#: Maps one staged year onto the two tables of the model in a single statement,
#: dissolving the boundary-split polygons into one fire as it goes.
#:
#: The CTEs, in order, and what each is for:
#:
#: ``cleaned``
#:     The text attributes trimmed of padding and of any stray line ending, an
#:     all-whitespace value becoming ``NULL``, the two flags read, and ``--year``
#:     applied. First, because everything below reads these.
#: ``valid``
#:     Everything that can be stored: a geometry, a ``GID``, an ``NFIREID`` and a
#:     year. Counted rather than assumed — nothing in the published archive fails
#:     this, and a future publication that does should say so rather than quietly
#:     import fewer fires.
#: ``repaired``
#:     One feature, flattened to 2D and repaired, **before** the union so that one
#:     bad ring cannot fail a whole fire. ``ST_CollectionExtract(..., 3)`` flattens
#:     what ``ST_MakeValid`` can leave as a ``GEOMETRYCOLLECTION`` back to polygons.
#: ``dissolved``
#:     The fire. One row per ``GID``, the pieces unioned, the areas summed, the
#:     administrations joined and the count kept. ``min`` on the attributes that
#:     should not differ between pieces, with ``attr_conflict`` counting the times
#:     they do; ``min``/``max`` on the dates, which is what NBAC itself does for a
#:     cross-border fire.
#: ``numbered``
#:     Primary keys drawn from the sequence up front, because the child insert has to
#:     know its parent's id and ``RETURNING`` would come too late. One id per *fire*.
#: ``resolved``
#:     The start date, its source and its precision, by the fixed fallback order.
#: ``located``
#:     Zone and country from a point *on* the perimeter (``ST_PointOnSurface``, which
#:     unlike a centroid is guaranteed to be inside it). Both ``LEFT JOIN``\\ s: a
#:     fire outside every imported boundary keeps its date and its geometry.
#:
#: The final ``SELECT`` returns the whole audit rather than a count, because every
#: CTE above it is a filter or a fold and a number that only said how many rows
#: landed would leave the user to guess what happened to the rest.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT staging.year AS year,
           staging.nfireid AS nfireid,
           NULLIF(btrim(staging.gid, {trimmed}), '') AS gid,
           NULLIF(btrim(staging.basrc, {trimmed}), '') AS ba_source,
           NULLIF(btrim(staging.firemaps, {trimmed}), '') AS detection_source,
           NULLIF(btrim(staging.firemapm, {trimmed}), '') AS mapping_method,
           NULLIF(btrim(staging.firecaus, {trimmed}), '') AS fire_cause,
           staging.hs_sdate AS hotspot_start_date,
           staging.hs_edate AS hotspot_end_date,
           staging.ag_sdate AS agency_start_date,
           staging.ag_edate AS agency_end_date,
           staging.capdate AS capture_date,
           staging.poly_ha AS area_ha_polygon,
           staging.adj_ha AS area_ha_adjusted,
           (lower(btrim(coalesce(staging.adj_flag, ''), {trimmed})) = :flag_true)
               AS area_adjusted,
           NULLIF(btrim(staging.admin_name, {trimmed}), '') AS admin_name,
           NULLIF(btrim(staging.admin_div, {trimmed}), '') AS admin_div,
           (lower(btrim(coalesce(staging.prescribed, ''), {trimmed})) = :flag_true)
               AS prescribed,
           NULLIF(btrim(staging.version, {trimmed}), '') AS version,
           staging.geom AS geom
    FROM {staging_table} AS staging
    WHERE {year_filter}
),
valid AS MATERIALIZED (
    SELECT * FROM cleaned
    WHERE cleaned.geom IS NOT NULL
      AND cleaned.gid IS NOT NULL
      AND cleaned.nfireid IS NOT NULL
      AND cleaned.year IS NOT NULL
),
repaired AS MATERIALIZED (
    SELECT valid.*,
           ST_CollectionExtract(ST_MakeValid(ST_Force2D(valid.geom)), 3) AS part
    FROM valid
),
dissolved AS MATERIALIZED (
    SELECT repaired.gid,
           min(repaired.year) AS year,
           min(repaired.nfireid) AS nfireid,
           count(*) AS part_count,
           (count(DISTINCT repaired.admin_name) > 1) AS crosses_admin,
           string_agg(DISTINCT repaired.admin_name, :admin_separator
                      ORDER BY repaired.admin_name) AS admin_name,
           string_agg(DISTINCT repaired.admin_div, :admin_separator
                      ORDER BY repaired.admin_div) AS admin_div,
           min(repaired.fire_cause) AS fire_cause,
           min(repaired.ba_source) AS ba_source,
           min(repaired.detection_source) AS detection_source,
           min(repaired.mapping_method) AS mapping_method,
           min(repaired.version) AS version,
           -- The earliest start and the latest end over the pieces, which is what
           -- NBAC itself does for a fire that crossed a border.
           min(repaired.hotspot_start_date) AS hotspot_start_date,
           max(repaired.hotspot_end_date) AS hotspot_end_date,
           min(repaired.agency_start_date) AS agency_start_date,
           max(repaired.agency_end_date) AS agency_end_date,
           max(repaired.capture_date) AS capture_date,
           -- Summed: each published piece carries the area of its own piece.
           sum(repaired.area_ha_polygon) AS area_ha_polygon,
           sum(repaired.area_ha_adjusted) AS area_ha_adjusted,
           bool_or(repaired.area_adjusted) AS area_adjusted,
           bool_or(repaired.prescribed) AS prescribed,
           -- Non-zero only where the pieces of one fire disagree about something
           -- they should not. Counted rather than resolved in silence.
           (count(DISTINCT repaired.fire_cause) > 1
            OR count(DISTINCT repaired.ba_source) > 1
            OR count(DISTINCT repaired.mapping_method) > 1) AS attr_conflict,
           ST_Multi(ST_CollectionExtract(ST_Union(repaired.part), 3)) AS perimeter_source
    FROM repaired
    WHERE NOT ST_IsEmpty(repaired.part)
    GROUP BY repaired.gid
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id, dissolved.*
    FROM dissolved
    WHERE NOT ST_IsEmpty(dissolved.perimeter_source)
),
resolved AS MATERIALIZED (
    SELECT numbered.*,
           COALESCE(numbered.agency_start_date,
                    numbered.hotspot_start_date,
                    make_date(numbered.year, 1, 1)) AS start_date,
           CASE WHEN numbered.agency_start_date IS NOT NULL THEN :source_agency
                WHEN numbered.hotspot_start_date IS NOT NULL THEN :source_hotspot
                ELSE :source_year END AS date_source,
           CASE WHEN numbered.agency_start_date IS NOT NULL
                  OR numbered.hotspot_start_date IS NOT NULL THEN :precision_day
                ELSE :precision_year END AS date_time_precision
    FROM numbered
),
projected AS MATERIALIZED (
    SELECT resolved.*,
           ST_Transform(resolved.perimeter_source, 4326) AS perimeter,
           ST_PointOnSurface(ST_Transform(resolved.perimeter_source, 4326)) AS locator
    FROM resolved
),
located AS MATERIALIZED (
    SELECT projected.*, zone.name AS time_zone, country.id AS admin_boundary_id
    FROM projected
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry, projected.locator)
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry, projected.locator)
        LIMIT 1
    ) AS country ON TRUE
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT located.wildfire_id,
           'nbac_wildfire',
           :provider_id,
           (located.start_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           -- AG_EDATE and nothing else. The last hotspot is a different event; see
           -- the module docstring.
           CASE WHEN located.agency_end_date IS NULL THEN NULL
                ELSE (located.agency_end_date::timestamp)
                         AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone)
           END,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO nbac_wildfire (id, gid, nfireid, year, part_count, crosses_admin,
                               admin_name, admin_div, fire_cause, ba_source,
                               detection_source, mapping_method,
                               hotspot_start_date, hotspot_end_date,
                               agency_start_date, agency_end_date, capture_date,
                               date_source, date_time_precision,
                               area_ha_polygon, area_ha_adjusted, area_adjusted,
                               prescribed, version,
                               nfdb_wildfire_id, match_method, match_confidence,
                               matched_at, perimeter_lambert)
    SELECT located.wildfire_id,
           located.gid,
           located.nfireid,
           located.year,
           located.part_count,
           located.crosses_admin,
           located.admin_name,
           located.admin_div,
           located.fire_cause,
           located.ba_source,
           located.detection_source,
           located.mapping_method,
           located.hotspot_start_date,
           located.hotspot_end_date,
           located.agency_start_date,
           located.agency_end_date,
           located.capture_date,
           located.date_source,
           located.date_time_precision,
           located.area_ha_polygon,
           located.area_ha_adjusted,
           located.area_adjusted,
           located.prescribed,
           located.version,
           -- Never set here. The link to the NFDB report is another application's
           -- to fill; see src/providers/canada_nbac/__init__.py.
           NULL, NULL, NULL, NULL,
           located.perimeter_source
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS features,
       (SELECT count(*) FROM valid) AS valid,
       (SELECT count(*) FROM dissolved) AS fires,
       (SELECT count(*) FROM dissolved WHERE crosses_admin) AS cross_border,
       (SELECT count(*) FROM dissolved WHERE attr_conflict) AS attr_conflicts,
       (SELECT count(*) FROM resolved WHERE date_source = :source_hotspot) AS from_hotspot,
       (SELECT count(*) FROM resolved WHERE date_source = :source_year) AS from_year,
       (SELECT count(*) FROM written) AS written
"""


# --------------------------------------------------------------------------
# Staging checks
# --------------------------------------------------------------------------

def normalise_staging_columns(session: Session, staging_table: str,
                              columns: dict[str, str],
                              logger: logging.LoggerAdapter) -> None:
    """Make sure the staged table has the attributes the mapping reads, typed usably.

    A missing column is fatal — the mapping would fail on it anyway, and failing here
    names it — and a column whose loaded type the mapping cannot read is converted
    rather than refused, because GDAL's choice of type depends on the shapefile's
    declared field widths and those are fiction throughout this archive.

    Raises
    ------
    RuntimeError
        If the staged layer publishes none of an attribute the mapping needs.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = {
        name: data_type
        for name, data_type in session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table"
        ), {"schema": schema or "public", "table": table}).all()
    }

    missing = [name for name in columns if name not in loaded]
    if missing:
        raise RuntimeError(
            f"the staged layer publishes no {', '.join(missing)}: this is not an NBAC "
            f"yearly archive, or its attributes have been renamed"
        )

    for name, wanted in columns.items():
        if loaded[name] in COMPATIBLE_TYPES.get(wanted, {wanted}):
            continue
        logger.debug("Converting staged %s from %s to %s", name, loaded[name], wanted)
        session.execute(text(
            f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {wanted} "
            f"USING {name}::{wanted}"
        ))


def check_extent(session: Session, staging_table: str,
                 logger: logging.LoggerAdapter) -> None:
    """Verify the staged geometry landed where Canada is on EPSG:3978.

    This is the assertion behind *the CRS is asserted, not read*. The published
    ``.prj`` names no EPSG code, so ``ogr2ogr`` was told to produce 3978 and this
    checks that the result is plausible — a transform that misread the source would
    put the archive thousands of kilometres away, or in degrees, and either is
    obvious against :data:`PLAUSIBLE_EXTENT`.

    A warning and not an error: a single stray polygon should not stop a year, and
    the number that matters is in the message.
    """
    row = session.execute(text(EXTENT_SQL.format(staging_table=staging_table))).one()
    if not row.with_geometry:
        return
    min_x, min_y, max_x, max_y = PLAUSIBLE_EXTENT
    if (row.min_x < min_x or row.min_y < min_y
            or row.max_x > max_x or row.max_y > max_y):
        logger.warning(
            "The staged geometry extends to (%.0f, %.0f)-(%.0f, %.0f), outside Canada "
            "on EPSG:%d. The published .prj names no EPSG code, so this may mean the "
            "projection was read wrongly; the perimeters are imported anyway",
            row.min_x, row.min_y, row.max_x, row.max_y, canada_nbac.SOURCE_SRID,
        )
    else:
        logger.debug("Staged geometry extent (%.0f, %.0f)-(%.0f, %.0f) is inside Canada",
                     row.min_x, row.min_y, row.max_x, row.max_y)


# --------------------------------------------------------------------------
# The years
# --------------------------------------------------------------------------

def year_filter(years: list[int] | None) -> str:
    """The ``WHERE`` fragment applying ``--year``, or one that is always true."""
    if not years:
        return "TRUE"
    return "staging.year = ANY(:years)"


def staged_years(session: Session, staging_table: str,
                 years: list[int] | None) -> list[int]:
    """The years the staged archive holds fires in, after ``--year``."""
    statement = STAGED_YEARS_SQL.format(staging_table=staging_table,
                                        year_filter=year_filter(years))
    parameters = {"years": years} if years else {}
    return list(session.scalars(text(statement), parameters).all())


def summarise_years(years: list[int]) -> str:
    """``1973-1975, 1980`` — a list of years compressed to its ranges."""
    if not years:
        return "no year"
    ranges: list[tuple[int, int]] = []
    start = previous = years[0]
    for year in years[1:]:
        if year == previous + 1:
            previous = year
        else:
            ranges.append((start, previous))
            start = previous = year
    ranges.append((start, previous))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def delete_years(session: Session, years: list[int],
                 logger: logging.LoggerAdapter) -> None:
    """Remove the fires of the years about to be re-imported."""
    linked = session.scalar(text(LINKED_SQL), {"years": years}) or 0
    if linked:
        logger.warning(
            "%d fire(s) of the year(s) being replaced carry a link to an NFDB report; "
            "re-importing discards those links and the binding has to be run again",
            linked,
        )
    session.execute(text(DELETE_YEARS_SQL), {"years": years})


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

class Audit:
    """What one year's transform did, for the summary lines."""

    def __init__(self, row) -> None:
        self.features = row.features
        self.valid = row.valid
        self.fires = row.fires
        self.cross_border = row.cross_border
        self.attr_conflicts = row.attr_conflicts
        self.from_hotspot = row.from_hotspot
        self.from_year = row.from_year
        self.written = row.written


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, years: list[int] | None) -> Audit:
    """Map the staged year onto the model, dissolving as it goes."""
    statement = TRANSFORM_SQL.format(staging_table=staging_table,
                                     trimmed=TRIMMED_CHARS,
                                     year_filter=year_filter(years))
    parameters = {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "fallback_time_zone": canada_nbac.DEFAULT_TIME_ZONE,
        "admin_separator": canada_nbac.ADMIN_SEPARATOR,
        "flag_true": FLAG_TRUE,
        "source_agency": canada_nbac.SOURCE_AGENCY,
        "source_hotspot": canada_nbac.SOURCE_HOTSPOT,
        "source_year": canada_nbac.SOURCE_YEAR,
        "precision_day": canada_nbac.PRECISION_DAY,
        "precision_year": canada_nbac.PRECISION_YEAR,
    }
    if years:
        parameters["years"] = years
    return Audit(session.execute(text(statement), parameters).one())


# --------------------------------------------------------------------------
# Importing one archive
# --------------------------------------------------------------------------

def load_archive(archive: Path, staging_table: str, args: argparse.Namespace,
                 logger: logging.LoggerAdapter) -> None:
    """Stage one published archive, in the CRS it was published in.

    EPSG:3978 and not whatever GDAL decides to call the unnamed projection in the
    ``.prj``. See the module docstring, and :func:`check_extent` for the check that
    goes with this decision.
    """
    datasource, layer = common.shapefile_datasource(archive)
    common.load_staging_table(
        datasource, layer, staging_table, args, common.resolve_database_settings(args),
        logger,
        target_srs=f"EPSG:{canada_nbac.SOURCE_SRID}",
        fid_column=STAGING_FID_COLUMN,
        creation_options=STAGING_CREATION_OPTIONS,
    )


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> int:
    """Import one yearly archive in its own transaction, returning the fires stored."""
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    log = ArchiveLogger(logger, {"archive": archive.name})

    started = time.monotonic()
    load_archive(archive, staging_table, args, log)

    with Session(engine) as session:
        normalise_staging_columns(session, staging_table, STAGING_COLUMNS, log)
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes it as if it held a handful of rows and picks nested loops
        # over the spatial joins.
        session.execute(text(f"ANALYZE {staging_table}"))
        check_extent(session, staging_table, log)

        years = staged_years(session, staging_table, args.year)
        if not years:
            log.warning("No fire in scope: the archive holds nothing for the year(s) "
                        "asked for")
            if not args.keep_staging:
                common.drop_staging_table(session, staging_table, log)
            session.rollback()
            return 0
        delete_years(session, years, log)

        audit = transform(session, provider_id, boundary_provider_id, staging_table,
                          args.year)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    unusable = audit.features - audit.valid
    if unusable:
        log.warning("%d of %d feature(s) publish no geometry, GID, NFIREID or year and "
                    "were dropped", unusable, audit.features)
    if audit.cross_border:
        log.info("%d fire(s) were published as several polygons in different "
                 "administrations and were dissolved into one row each",
                 audit.cross_border)
    if audit.attr_conflicts:
        log.warning("%d fire(s) have pieces that disagree about their cause, source or "
                    "mapping method; the first of each was stored",
                    audit.attr_conflicts)
    if audit.from_hotspot:
        log.info("%d fire(s) publish no agency date and were dated from the first "
                 "satellite hotspot", audit.from_hotspot)
    if audit.from_year:
        log.warning("%d fire(s) publish no date at all and were dated 1 January of "
                    "their year, with date_time_precision = '%s'",
                    audit.from_year, canada_nbac.PRECISION_YEAR)
    if audit.fires != audit.written:
        log.warning("%d of %d fire(s) were not stored: a dissolved perimeter that the "
                    "repair reduced to nothing cannot be",
                    audit.fires - audit.written, audit.fires)
    if audit.written:
        log.info("%s%d fire(s) from %d feature(s) over %s in %.0fs",
                 "would have imported " if args.dry_run else "imported ",
                 audit.written, audit.valid, summarise_years(years),
                 time.monotonic() - started)
    return audit.written


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import NBAC burned area perimeters for Canada into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. One archive per year; re-importing "
               "replaces the years it reads. Database settings not given here are read "
               "from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the yearly archives; every NBAC_*.zip is "
                             "imported in year order")
    source.add_argument("-s", "--shapefile", type=Path, nargs="+",
                        help="one or more .zip, .shp or directories to import instead of "
                             "the whole set")

    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year; may be repeated. The published YEAR "
                             "attribute, read from the data and not from the file name")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would have "
                             "been imported. Nothing is written, including the replacement "
                             "of years already in the database")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def find_archives(args: argparse.Namespace) -> list[Path]:
    """The archives to import, in name order — which for this archive is year order.

    Raises
    ------
    RuntimeError
        If nothing was found, which is far more likely a wrong path than an empty
        download.
    """
    if args.directory is not None:
        archives = sorted(args.directory.glob("*.zip"))
        if not archives:
            raise RuntimeError(f"{args.directory} holds no .zip archive")
        return archives
    return sorted(args.shapefile)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Import every archive against ``engine``, returning the fires written."""
    archives = find_archives(args)

    common.require_tables(engine, ["wildfire", "nbac_wildfire", "nfdb_wildfire",
                                   "admin_boundary", "time_zone", "data_provider"],
                          logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, canada_nbac.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, canada_nbac.PROVIDER_NAME, canada_nbac.PROVIDER_PRODUCT,
            canada_nbac.PROVIDER_FULL_NAME, canada_nbac.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    started = time.monotonic()
    written = 0
    logger.info("%d archive(s) to import", len(archives))
    for index, archive in enumerate(archives, start=1):
        logger.info("[%d/%d] %s", index, len(archives), archive.name)
        written += import_archive(archive, engine, args, provider_id,
                                  boundary_provider_id, logger)

    logger.info("%s%d fire(s) from %d archive(s) in %.0fs",
                "Would have imported " if args.dry_run else "Imported ",
                written, len(archives), time.monotonic() - started)
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("nbac-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.shapefile or []:
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        import_wildfires(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
