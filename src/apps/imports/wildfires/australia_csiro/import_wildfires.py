#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Australian historical bushfire extents.

Reads the file geodatabase the Digital Atlas of Australia distributes — two feature
classes, 347,834 polygons, 155.8 million vertices — and writes
:class:`~src.data_model.wildfire.Wildfire` and
:class:`~src.providers.australia_csiro.wildfire.CsiroWildfire`.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \\
         -g /data/incendis-forestals/oceania/australia/perimetres-gdb
   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \\
         -g perimetres-gdb --layer nt --year 2025 --dry-run

Import the OCHA boundaries and the time zone areas first, so fires get a country and
a local start time. Re-importing replaces the years it reads, one at a time.

One transaction per year, and per feature class
------------------------------------------------

**This archive is not published a year at a time and is imported as though it
were.** NBAC arrives as one zipped shapefile per year and the Chilean reports as one
per season, so those imports inherit their unit of work; this one is a single 860 MB
geodatabase holding 128 years, and 155.8 million vertices of polygon. Transformed in
one statement it would hold every lock it takes for the length of the run, roll back
an hour's work on one bad row, and give no sign of progress in between.

So the run is a loop:

#. stage one feature class with ``ogr2ogr``, once;
#. resolve the published attributes into normalised columns, once;
#. ask the staged data which years it holds;
#. for each year — delete that year, transform it, commit, log what happened.

A year is therefore the unit that is replaced, which is why
:attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.year` is ``NOT NULL``
and indexed. Nothing outside the year in hand is touched, a failure costs one year,
and the log names the year before and after each step.

The largest year in the archive is 2021 with 16,363 published features, against
345,345 in the class as a whole. That is the size of the biggest statement this
import ever runs.

Nothing is merged
-----------------

One published feature is one row. The import does **not** dissolve the patches of a
burn into a fire, and :mod:`src.providers.australia_csiro` gives the measurements
that decided it: grouping on ``(source_layer, state_code, fire_id, ignition_date)``
— the tightest key the archive offers — merges features up to **2,403 km apart**,
because Western Australia's small fire numbers are district sequences reused across
the state.

That also makes the year loop trivially safe. With nothing to group, a year can be
read, written and committed in complete ignorance of every other year, and the rows
it produces do not depend on which years were imported before it.

What the run reports
--------------------

Every step, and every year: how many features were staged, how many the resolution
could not date, which years were found, and then per year the features read, the rows
written, how many were prescribed burns and how long it took. At the end, over the
whole run: the date sources, the implausible dates, and how many fires matched no
time zone area or no country.

The geodatabase has to be named ``.gdb``
-----------------------------------------

GDAL identifies a file geodatabase by the suffix on its directory, and the archive
as distributed has none. Rather than make the user rename the data,
:func:`geodatabase` puts a ``.gdb`` symlink to it in a temporary directory and hands
GDAL that.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import tempfile
import time
import typing

from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports import common
from src.providers import australia_csiro
from src.providers.australia_csiro import CAPTURE_METHOD_NORMALISATIONS
from src.providers.australia_csiro import CAUSE_NORMALISATIONS
from src.providers.australia_csiro import EPOCH_DATES
from src.providers.australia_csiro import FIRE_ID_SENTINELS
from src.providers.australia_csiro import FIRE_TYPE_NORMALISATIONS
from src.providers.australia_csiro import STATE_NORMALISATIONS
from src.providers.australia_csiro import STATE_TIME_ZONES

#: How every log line is laid out. The same format as the sibling imports.
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"

#: Default name of the staging table ``ogr2ogr`` loads a feature class into.
DEFAULT_STAGING_TABLE = "csiro_extents"

#: The serial key GDAL puts on the staging table.
#:
#: Loaded with ``-preserve_fid``, so it holds the geodatabase's own ``OBJECTID``
#: rather than a number PostgreSQL made up. Unlike the shapefile imports, this one
#: **stores** it: see
#: :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.object_id`.
STAGING_FID_COLUMN = "object_id"

#: The published attributes, with the type each is read as.
#:
#: Both feature classes publish the same twelve, in the same spellings, with one
#: difference this import has to absorb: ``capture_date`` is a ``String`` in the
#: national class and a ``Date`` in the Northern Territory one, so it is read from
#: whichever of the two GDAL lands (see :data:`CAPTURE_DATE_SQL`).
PUBLISHED_COLUMNS = ("fire_id", "fire_name", "ignition_date", "capture_date",
                     "extinguish_date", "fire_type", "ignition_cause", "capt_method",
                     "area_ha", "perim_km", "state", "agency")

#: The columns :func:`resolve_staging_columns` adds to the staging table, with the
#: type each is given.
#:
#: Resolved once per feature class, before any year is written, so that the
#: per-year transform is a projection of columns that already exist rather than
#: twelve ``CASE`` expressions run again for every year.
RESOLVED_COLUMNS = {
    "state_code": "text",
    "fire_type_norm": "text",
    "cause_norm": "text",
    "capture_method_norm": "text",
    "fire_id_is_sentinel": "boolean",
    "ignition_d": "date",
    "extinguish_d": "date",
    "capture_d": "date",
    "resolved_start": "date",
    "date_source": "text",
    "dates_plausible": "boolean",
    "fire_year": "integer",
}

#: The characters trimmed off every published text attribute before it is read. The
#: same set the sibling imports trim, and no NUL among them: PostgreSQL will not
#: accept one inside a text literal, so a string that contained one could not be
#: written here anyway.
TRIMMED_CHARS = r"E' \t\r\n'"


def _case(column: str, mapping: dict[str, str], default: str = "NULL") -> str:
    """A ``CASE`` mapping a published value to its normalised one.

    The vocabularies live in :mod:`src.providers.australia_csiro` and the SQL is
    built from them here, so that the mapping the import applies and the mapping the
    provider module documents cannot drift apart — the argument
    :func:`src.apps.imports.wildfires.chile_conaf.import_wildfires.mark_corrupt`
    makes for applying :func:`~src.providers.chile_conaf.is_corrupt` in SQL.
    """
    whens = "\n".join(
        f"        WHEN '{published}' THEN '{normalised}'"
        for published, normalised in mapping.items()
    )
    return (f"CASE lower(btrim(coalesce({column}, ''), {TRIMMED_CHARS}))\n"
            f"{whens}\n        ELSE {default} END")


#: Reads ``capture_date`` whichever way the feature class published it.
#:
#: ``YYYYMMDD`` text in the national class — 1,976 features of 345,345, all in New
#: South Wales and the ACT — and a date column in the Northern Territory one, where
#: it is the same value on every row. Cast to text first so that one expression
#: reads both: a date cast to text begins with ``YYYY-MM-DD``, which the second
#: branch takes, and the eight-digit form has no separators, which the first does.
CAPTURE_DATE_SQL = """
CASE WHEN btrim(coalesce(capture_date::text, ''), {trimmed}) ~ '^[0-9]{{8}}$'
          THEN to_date(btrim(capture_date::text, {trimmed}), 'YYYYMMDD')
     WHEN btrim(coalesce(capture_date::text, ''), {trimmed}) ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          THEN substring(btrim(capture_date::text, {trimmed}) from 1 for 10)::date
     ELSE NULL END
"""

#: Fills :data:`RESOLVED_COLUMNS` for every staged feature.
#:
#: One ``UPDATE`` over the class, run once. The three published dates are read here
#: because the start, the plausibility flag and the year are all derived from them by
#: :data:`RESOLVE_DERIVED_SQL` immediately afterwards.
RESOLVE_SQL = """
UPDATE {staging_table} SET
    state_code = {state_case},
    fire_type_norm = {fire_type_case},
    cause_norm = {cause_case},
    capture_method_norm = {capture_method_case},
    fire_id_is_sentinel = (
        btrim(coalesce(fire_id, ''), {trimmed}) = ''
        OR btrim(coalesce(fire_id, ''), {trimmed}) IN {sentinels}
    ),
    ignition_d = substring(ignition_date::text from 1 for 10)::date,
    extinguish_d = substring(extinguish_date::text from 1 for 10)::date,
    capture_d = {capture_date}
"""

#: Second pass: the start, its source, the plausibility flag, the year and the key.
#:
#: A statement of its own because every one of them reads a column the first pass
#: has just written, and PostgreSQL evaluates an ``UPDATE``'s assignments against
#: the row as it was before the statement.
RESOLVE_DERIVED_SQL = """
UPDATE {staging_table} SET
    resolved_start = COALESCE(ignition_d, extinguish_d, capture_d),
    date_source = CASE WHEN ignition_d IS NOT NULL THEN :source_ignition
                       WHEN extinguish_d IS NOT NULL THEN :source_extinguish
                       WHEN capture_d IS NOT NULL THEN :source_capture
                       ELSE NULL END,
    -- COALESCE, and it is load-bearing: a comparison against a missing date is NULL,
    -- NULL propagates through the OR chain, and dates_plausible is NOT NULL on the
    -- model. A fire that publishes no date has nothing to disbelieve, which is what
    -- :func:`~src.providers.australia_csiro.dates_are_plausible` says too.
    dates_plausible = NOT COALESCE(
        ignition_d = ANY(:epoch_dates)
        OR extinguish_d = ANY(:epoch_dates)
        OR ignition_d < :earliest OR ignition_d > :latest
        OR extinguish_d < :earliest OR extinguish_d > :latest
        OR extinguish_d < ignition_d
    , FALSE),
    fire_year = EXTRACT(YEAR FROM COALESCE(ignition_d, extinguish_d, capture_d))::integer
"""

#: How many staged features could not be dated at all, and therefore cannot be
#: stored: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is ``NOT NULL``
#: and this dataset publishes nothing else to put in it. 120 of the 347,834.
UNDATED_SQL = """
SELECT count(*) FROM {staging_table} WHERE resolved_start IS NULL
"""

#: How many staged features carry a state this import does not know.
#:
#: Zero on the archive as distributed. Asked because ``state_code`` is ``NOT NULL``
#: and constrained on the model, so a new spelling has to stop the run with a
#: sentence rather than a constraint violation inside the transform.
UNKNOWN_STATE_SQL = """
SELECT DISTINCT btrim(coalesce(state, ''), {trimmed}) AS state
FROM {staging_table}
WHERE state_code IS NULL
"""

#: The years the staged class holds fires in, after ``--year`` has been applied.
#:
#: The steps of the loop, and the years the run replaces. Read from the resolved
#: date and never from anything else — the geodatabase publishes no year column.
STAGED_YEARS_SQL = """
SELECT DISTINCT fire_year
FROM {staging_table}
WHERE resolved_start IS NOT NULL
  AND ({year_filter})
ORDER BY fire_year
"""

#: Removes the fires of one year of one feature class.
#:
#: One statement, for the reason the sibling imports give: ``csiro_wildfire.id``
#: references ``wildfire``, so no order of separate statements is safe, while inside
#: one statement the foreign keys are checked once at the end against a consistent
#: final state. Nothing outside these two tables points at what is deleted — this
#: provider has no ignition, no cause catalogue and no binding to another dataset.
DELETE_YEAR_SQL = """
WITH doomed AS (
    SELECT id FROM csiro_wildfire
    WHERE source_layer = :source_layer AND year = :year
),
removed_child AS (
    DELETE FROM csiro_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Maps **one year of one feature class** onto the two tables.
#:
#: One statement and one year's features, run once per year. ``MATERIALIZED`` is not
#: negotiable on ``numbered``: it calls ``nextval`` once per row, and a CTE the
#: planner is free to inline could call it again for every reference, handing one
#: fire two different keys.
#:
#: The CTEs, in order:
#:
#: ``cleaned``
#:     This year's staged features, undated ones excluded, every text attribute
#:     trimmed and an all-whitespace value made ``NULL``.
#: ``repaired`` / ``usable``
#:     ``ST_MakeValid`` and the polygonal part of the result, then the features that
#:     still have one. The archive holds self-intersecting rings — 155.8 million
#:     vertices digitised by nine agencies over thirty years — and a geometry that
#:     repairs to nothing is in no row.
#: ``numbered`` / ``located``
#:     A key from the sequence, then the zone and the country from a point on the
#:     feature's own surface.
#: ``ins_wildfire`` / ``written``
#:     The generic row and the provider row, one of each per published feature.
#:
#: There is no grouping anywhere in it. See the module docstring.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT staging.{fid_column} AS object_id,
           staging.fire_year AS fire_year,
           NULLIF(btrim(coalesce(staging.fire_id, ''), {trimmed}), '') AS fire_id,
           staging.fire_id_is_sentinel AS fire_id_is_sentinel,
           NULLIF(btrim(coalesce(staging.fire_name, ''), {trimmed}), '') AS fire_name,
           NULLIF(btrim(coalesce(staging.state, ''), {trimmed}), '') AS state_published,
           staging.state_code AS state_code,
           NULLIF(btrim(coalesce(staging.agency, ''), {trimmed}), '') AS agency,
           NULLIF(btrim(coalesce(staging.fire_type, ''), {trimmed}), '')
               AS fire_type_published,
           staging.fire_type_norm AS fire_type,
           NULLIF(btrim(coalesce(staging.ignition_cause, ''), {trimmed}), '')
               AS cause_published,
           staging.cause_norm AS cause,
           NULLIF(btrim(coalesce(staging.capt_method, ''), {trimmed}), '')
               AS capture_method_published,
           staging.capture_method_norm AS capture_method,
           staging.ignition_d AS ignition_date,
           staging.extinguish_d AS extinguish_date,
           staging.capture_d AS capture_date,
           staging.resolved_start AS resolved_start,
           staging.date_source AS date_source,
           staging.dates_plausible AS dates_plausible,
           staging.area_ha AS area_ha,
           staging.perim_km AS perim_km,
           staging.geom AS geom
    FROM {staging_table} AS staging
    WHERE staging.fire_year = :year
      AND staging.resolved_start IS NOT NULL
      AND staging.geom IS NOT NULL
),
repaired AS MATERIALIZED (
    SELECT cleaned.*,
           ST_CollectionExtract(ST_MakeValid(ST_Force2D(cleaned.geom)), 3) AS part
    FROM cleaned
),
usable AS MATERIALIZED (
    SELECT * FROM repaired WHERE NOT ST_IsEmpty(repaired.part)
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           usable.*,
           ST_Multi(usable.part) AS perimeter,
           ST_PointOnSurface(usable.part) AS locator
    FROM usable
),
located AS MATERIALIZED (
    SELECT numbered.*,
           zone.name AS time_zone,
           country.id AS admin_boundary_id
    FROM numbered
    LEFT JOIN LATERAL (
        SELECT part.name
        FROM {time_zone_parts} AS part
        WHERE ST_Intersects(part.geometry, numbered.locator)
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT part.admin_boundary_id AS id
        FROM {boundary_parts} AS part
        WHERE ST_Intersects(part.geometry, numbered.locator)
        LIMIT 1
    ) AS country ON TRUE
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT located.wildfire_id,
           'csiro_wildfire',
           :provider_id,
           (located.resolved_start::timestamp)
               AT TIME ZONE COALESCE(located.time_zone,
                                     {state_zone_case},
                                     :fallback_time_zone),
           -- The published extinction, and only when it is one: an end before its
           -- start or in the year 2525 is stored on the provider row as published
           -- and kept out of the instant every cross-provider query reads.
           CASE WHEN located.extinguish_date IS NULL OR NOT located.dates_plausible
                THEN NULL
                ELSE (located.extinguish_date::timestamp)
                         AT TIME ZONE COALESCE(located.time_zone,
                                               {state_zone_case},
                                               :fallback_time_zone)
           END,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO csiro_wildfire (id, source_layer, object_id, year, fire_id,
                                fire_id_is_sentinel, fire_name, state_published,
                                state_code, agency, fire_type_published, fire_type,
                                cause_published, cause, capture_method_published,
                                capture_method, ignition_date, extinguish_date,
                                capture_date, date_source, date_time_precision,
                                dates_plausible, area_ha, perim_km)
    SELECT located.wildfire_id,
           :source_layer,
           located.object_id,
           located.fire_year,
           located.fire_id,
           located.fire_id_is_sentinel,
           located.fire_name,
           located.state_published,
           located.state_code,
           located.agency,
           located.fire_type_published,
           located.fire_type,
           located.cause_published,
           located.cause,
           located.capture_method_published,
           located.capture_method,
           located.ignition_date,
           located.extinguish_date,
           located.capture_date,
           located.date_source,
           :precision_day,
           located.dates_plausible,
           located.area_ha,
           located.perim_km
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS features,
       (SELECT count(*) FROM cleaned) - (SELECT count(*) FROM usable) AS empty_geometry,
       (SELECT count(*) FROM located WHERE date_source = :source_extinguish)
           AS from_extinguish,
       (SELECT count(*) FROM located WHERE date_source = :source_capture) AS from_capture,
       (SELECT count(*) FROM located WHERE NOT dates_plausible) AS implausible,
       (SELECT count(*) FROM located WHERE fire_type = :type_prescribed) AS prescribed,
       (SELECT count(*) FROM located WHERE time_zone IS NULL) AS no_time_zone,
       (SELECT count(*) FROM located WHERE admin_boundary_id IS NULL) AS no_boundary,
       (SELECT count(*) FROM written) AS written
"""

#: How finely the boundary and time zone polygons are cut before the lookup.
#:
#: The Chilean import's number and the PostGIS recipe's, for the same reason: the
#: Australian OCHA boundary is one polygon of hundreds of thousands of vertices and
#: ``ST_Contains`` against the whole of it, once per fire, is about 100 ms — a
#: fortnight of CPU over an archive this size. Cut into pieces it is microseconds.
SUBDIVIDE_VERTICES = 256

#: The countries the staged features could be in, cut into pieces small enough to
#: test a point against. See :func:`build_lookup_parts`.
BOUNDARY_PARTS_SQL = """
CREATE TABLE {parts_table} AS
SELECT boundary.id AS admin_boundary_id,
       ST_Subdivide(boundary.geometry, {max_vertices}) AS geometry
FROM admin_boundary AS boundary
WHERE boundary.level = 0
  AND boundary.data_provider_id = :boundary_provider_id
  AND boundary.geometry && ST_GeomFromText(:extent, 4326)
"""

#: The time zone areas the staged features could be in, cut the same way. Australia
#: spans five of them, so this is a real lookup and not a formality.
TIME_ZONE_PARTS_SQL = """
CREATE TABLE {parts_table} AS
SELECT time_zone.name AS name,
       ST_Subdivide(time_zone.geometry, {max_vertices}) AS geometry
FROM time_zone
WHERE time_zone.geometry && ST_GeomFromText(:extent, 4326)
"""

#: The index that is the whole point of the two tables above.
PARTS_INDEX_SQL = "CREATE INDEX ON {parts_table} USING gist (geometry)"

#: The box the staged features cover, rounded out to whole degrees with a degree of
#: margin. Australia and its neighbours, and stable between the two feature classes
#: so the pieces are cut once for a run over both.
STAGED_EXTENT_SQL = """
SELECT ST_AsText(ST_MakeEnvelope(
           GREATEST(floor(ST_XMin(box)) - 1, -180), GREATEST(floor(ST_YMin(box)) - 1, -90),
           LEAST(ceil(ST_XMax(box)) + 1, 180), LEAST(ceil(ST_YMax(box)) + 1, 90),
           4326)) AS extent
FROM (SELECT ST_Extent(geom)::geometry AS box FROM {staging_table}) AS staged
WHERE box IS NOT NULL
"""

#: Whether pieces cut for ``:covered`` can answer for points inside ``:extent``.
EXTENT_COVERED_SQL = """
SELECT ST_Contains(ST_GeomFromText(:covered, 4326), ST_GeomFromText(:extent, 4326))
"""

#: The box holding both, for a rebuild that will not have to be done again.
EXTENT_UNION_SQL = """
SELECT ST_AsText(ST_Envelope(ST_Collect(ST_GeomFromText(:covered, 4326),
                                        ST_GeomFromText(:extent, 4326))))
"""


# --------------------------------------------------------------------------
# The geodatabase
# --------------------------------------------------------------------------

@contextlib.contextmanager
def geodatabase(path: Path, logger: logging.Logger) -> typing.Iterator[str]:
    """Yield a path GDAL will open the geodatabase at.

    GDAL identifies a file geodatabase by the ``.gdb`` suffix on its directory, and
    the archive as distributed has none — ``ogrinfo`` on it fails with *not
    recognized as being in a supported file format*. A directory that already ends
    in ``.gdb`` is handed straight back; anything else is given a symlink of that
    name in a temporary directory, which costs nothing and leaves the data where the
    user put it.

    Parameters
    ----------
    path : pathlib.Path
        The geodatabase directory, with or without the suffix.
    logger : logging.Logger
        Where the substitution is reported.

    Yields
    ------
    str
        The path to open, as a string for ``ogr2ogr``.
    """
    resolved = path.resolve()
    if resolved.suffix.lower() == ".gdb":
        yield str(resolved)
        return
    with tempfile.TemporaryDirectory(prefix="csiro-") as directory:
        link = Path(directory) / f"{resolved.name}.gdb"
        link.symlink_to(resolved, target_is_directory=True)
        logger.info("Opening %s through %s: GDAL reads a geodatabase by its suffix",
                    resolved, link)
        yield str(link)


def layer_name(source_layer: str) -> str:
    """The feature class :data:`~src.providers.australia_csiro.SOURCE_LAYERS` names."""
    return australia_csiro.LAYER_FEATURE_CLASSES[source_layer]


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def add_resolved_columns(session: Session, staging_table: str,
                         logger: logging.Logger) -> None:
    """Add :data:`RESOLVED_COLUMNS` to the freshly staged table."""
    for column, sql_type in RESOLVED_COLUMNS.items():
        session.execute(text(
            f"ALTER TABLE {staging_table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"
        ))
    logger.debug("Added %d resolved column(s) to %s", len(RESOLVED_COLUMNS), staging_table)


def resolve_staging_columns(session: Session, staging_table: str,
                            logger: logging.Logger) -> None:
    """Normalise the published attributes, in place, once per feature class."""
    sentinels = "(" + ", ".join(f"'{value}'" for value in FIRE_ID_SENTINELS) + ")"

    session.execute(text(RESOLVE_SQL.format(
        staging_table=staging_table,
        trimmed=TRIMMED_CHARS,
        sentinels=sentinels,
        state_case=_case("state", STATE_NORMALISATIONS),
        fire_type_case=_case("fire_type", FIRE_TYPE_NORMALISATIONS,
                             default=f"'{australia_csiro.FIRE_TYPE_UNKNOWN}'"),
        cause_case=_case("ignition_cause", CAUSE_NORMALISATIONS),
        capture_method_case=_case("capt_method", CAPTURE_METHOD_NORMALISATIONS),
        capture_date=CAPTURE_DATE_SQL.format(trimmed=TRIMMED_CHARS),
    )))
    session.execute(text(RESOLVE_DERIVED_SQL.format(
        staging_table=staging_table,
    )), {
        "source_ignition": australia_csiro.SOURCE_IGNITION,
        "source_extinguish": australia_csiro.SOURCE_EXTINGUISH,
        "source_capture": australia_csiro.SOURCE_CAPTURE,
        "epoch_dates": list(EPOCH_DATES),
        "earliest": australia_csiro.EARLIEST_PLAUSIBLE_DATE,
        "latest": australia_csiro.LATEST_PLAUSIBLE_DATE,
    })
    session.execute(text(f"ANALYZE {staging_table}"))
    logger.info("Resolved the published attributes into normalised columns")


def check_states(session: Session, staging_table: str, logger: logging.Logger) -> None:
    """Refuse to import a state spelling this project does not know.

    Raises
    ------
    RuntimeError
        If any staged feature has a ``state`` that
        :data:`~src.providers.australia_csiro.STATE_NORMALISATIONS` does not map.
        ``state_code`` is ``NOT NULL`` and constrained on the model, so the
        alternative is a constraint violation from inside a 200-line statement.
    """
    unknown = [row.state for row in session.execute(text(
        UNKNOWN_STATE_SQL.format(staging_table=staging_table, trimmed=TRIMMED_CHARS)
    ))]
    if unknown:
        raise RuntimeError(
            "state(s) with no known code: " + ", ".join(repr(value) for value in unknown)
            + ". Add them to src.providers.australia_csiro.STATE_NORMALISATIONS"
        )
    logger.debug("Every staged feature has a known state")


def report_undated(session: Session, staging_table: str, logger: logging.Logger) -> int:
    """Warn about the features that cannot be stored, and return how many."""
    undated = session.scalar(text(UNDATED_SQL.format(staging_table=staging_table))) or 0
    if undated:
        logger.warning("%d staged feature(s) publish no ignition, extinguish or capture "
                       "date and cannot be stored: start_date_time is NOT NULL and this "
                       "dataset offers nothing else to put in it", undated)
    return undated


def staged_years(session: Session, staging_table: str,
                 years: list[int] | None) -> list[int]:
    """The years the staged class holds datable features in, in order."""
    statement = STAGED_YEARS_SQL.format(
        staging_table=staging_table,
        year_filter="fire_year = ANY(:years)" if years else "TRUE",
    )
    parameters = {"years": years} if years else {}
    return list(session.scalars(text(statement), parameters).all())


def summarise_years(years: list[int]) -> str:
    """``1898, 1899, …`` for a log line, contracted when there are many."""
    if not years:
        return "none"
    if len(years) <= 3:
        return ", ".join(str(year) for year in years)
    return f"{years[0]} to {years[-1]} ({len(years)} years)"


# --------------------------------------------------------------------------
# The boundary and time zone lookups
# --------------------------------------------------------------------------

@dataclass
class LookupParts:
    """Where :func:`build_lookup_parts` leaves the two subdivided lookup tables.

    One of these is made per run and shared by both feature classes: the pieces are
    cut for a box round the staged data, and the Northern Territory is inside the box
    the national class already needed.
    """

    boundary: str
    time_zone: str
    #: The box the pieces answer for, as WKT in EPSG:4326, or ``None`` before the
    #: first build.
    covered: str | None = None

    @classmethod
    def beside(cls, staging_table: str) -> LookupParts:
        """The names to use next to ``staging_table``."""
        return cls(boundary=f"{staging_table}_boundary_parts",
                   time_zone=f"{staging_table}_time_zone_parts")

    def __iter__(self) -> typing.Iterator[str]:
        """The two table names, for dropping them."""
        return iter((self.boundary, self.time_zone))


def build_lookup_parts(session: Session, staging_table: str, parts: LookupParts,
                       boundary_provider_id: int | None,
                       logger: logging.Logger) -> None:
    """Cut the countries and zones the staged features could be in into small pieces.

    Called once per feature class, before any year is written, and does the work only
    when the pieces it already has cannot answer for what has just been staged.

    345,345 perimeters each need a country and a zone, and the Australian OCHA
    boundary is a single polygon of hundreds of thousands of vertices: tested whole,
    that lookup is about 100 ms a fire and the run never finishes. See
    :data:`SUBDIVIDE_VERTICES`.
    """
    extent = session.scalar(text(STAGED_EXTENT_SQL.format(staging_table=staging_table)))
    if extent is None:
        logger.debug("Nothing staged to look up; leaving the lookup tables alone")
        if parts.covered is not None:
            return
        extent = "POLYGON EMPTY"

    if parts.covered is not None:
        if session.scalar(text(EXTENT_COVERED_SQL),
                          {"covered": parts.covered, "extent": extent}):
            logger.info("Reusing the lookup pieces already cut for %s", parts.covered)
            return
        extent = session.scalar(text(EXTENT_UNION_SQL),
                                {"covered": parts.covered, "extent": extent})

    started = time.monotonic()
    for name in parts:
        session.execute(text(f"DROP TABLE IF EXISTS {name}"))
    session.execute(text(BOUNDARY_PARTS_SQL.format(
        parts_table=parts.boundary, max_vertices=SUBDIVIDE_VERTICES,
    )), {"boundary_provider_id": boundary_provider_id, "extent": extent})
    session.execute(text(TIME_ZONE_PARTS_SQL.format(
        parts_table=parts.time_zone, max_vertices=SUBDIVIDE_VERTICES,
    )), {"extent": extent})
    for name in parts:
        session.execute(text(PARTS_INDEX_SQL.format(parts_table=name)))
        session.execute(text(f"ANALYZE {name}"))
    parts.covered = extent

    logger.info("Cut %d boundary piece(s) and %d time zone piece(s) for %s in %.1fs",
                session.scalar(text(f"SELECT count(*) FROM {parts.boundary}")),
                session.scalar(text(f"SELECT count(*) FROM {parts.time_zone}")),
                extent, time.monotonic() - started)


# --------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Audit:
    """What the transform did, for the summary lines.

    Attributes
    ----------
    features : int
        Staged features the year filter let through, undated and geometry-less ones
        already excluded.
    empty_geometry : int
        Features whose geometry was empty once repaired, and which are therefore in
        no row.
    from_extinguish, from_capture : int
        Fires whose start had to be taken from the extinction or the capture date,
        no ignition date being published.
    implausible : int
        Fires whose published dates fail
        :func:`~src.providers.australia_csiro.dates_are_plausible`.
    prescribed : int
        Fires published as prescribed burns. Reported every year because it is
        usually most of them.
    no_time_zone, no_boundary : int
        Fires whose perimeter matched no time zone area, and no country.
    written : int
        Rows actually stored.

    Notes
    -----
    Every field is a count over a partition of the staged features: the transform
    runs once per year and no feature is in two years, so adding the years' audits
    gives exactly what one pass over the class would have reported. That is what
    :meth:`__add__` is for.
    """

    features: int = 0
    empty_geometry: int = 0
    from_extinguish: int = 0
    from_capture: int = 0
    implausible: int = 0
    prescribed: int = 0
    no_time_zone: int = 0
    no_boundary: int = 0
    written: int = 0

    @classmethod
    def from_row(cls, row) -> Audit:
        """The audit the transform's one row reports."""
        return cls(**{field.name: getattr(row, field.name) for field in fields(cls)})

    def __add__(self, other: Audit) -> Audit:
        """The two years' counts, summed field by field."""
        return Audit(**{field.name: getattr(self, field.name) + getattr(other, field.name)
                        for field in fields(self)})


# --------------------------------------------------------------------------
# One year
# --------------------------------------------------------------------------

def delete_year(session: Session, source_layer: str, year: int) -> int:
    """Remove the stored fires of one year of one feature class."""
    result = session.execute(text(DELETE_YEAR_SQL),
                             {"source_layer": source_layer, "year": year})
    return result.rowcount or 0


def transform_year(session: Session, provider_id: int, parts: LookupParts,
                   staging_table: str, source_layer: str, year: int) -> Audit:
    """Map one year of one staged feature class onto the model."""
    state_zone_case = "CASE located.state_code\n" + "\n".join(
        f"                WHEN '{code}' THEN '{zone}'"
        for code, zone in STATE_TIME_ZONES.items()
    ) + "\n                ELSE NULL END"

    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        fid_column=STAGING_FID_COLUMN,
        trimmed=TRIMMED_CHARS,
        boundary_parts=parts.boundary,
        time_zone_parts=parts.time_zone,
        state_zone_case=state_zone_case,
    )
    parameters = {
        "year": year,
        "provider_id": provider_id,
        "source_layer": source_layer,
        "fallback_time_zone": australia_csiro.DEFAULT_TIME_ZONE,
        "precision_day": australia_csiro.PRECISION_DAY,
        "source_extinguish": australia_csiro.SOURCE_EXTINGUISH,
        "source_capture": australia_csiro.SOURCE_CAPTURE,
        "type_prescribed": australia_csiro.FIRE_TYPE_PRESCRIBED_BURN,
    }
    return Audit.from_row(session.execute(text(statement), parameters).one())


def import_year(engine: Engine, args: argparse.Namespace, provider_id: int,
                parts: LookupParts, staging_table: str, source_layer: str, year: int,
                logger: logging.Logger) -> Audit:
    """Replace one year of one feature class, in a transaction of its own.

    The whole of this application's unit of work: delete the year, write it, commit,
    and say what happened. A failure here rolls back this year alone — the years
    before it stay written and the run reports which one stopped it.
    """
    started = time.monotonic()
    with Session(engine) as session:
        removed = delete_year(session, source_layer, year)
        if removed:
            logger.info("%d: removed %d fire(s) already stored", year, removed)
        audit = transform_year(session, provider_id, parts, staging_table,
                               source_layer, year)
        if args.dry_run:
            session.rollback()
            verb = "would write"
        else:
            session.commit()
            verb = "wrote"
        logger.info("%d: read %d feature(s), %s %d fire(s) "
                    "(%d prescribed) in %.1fs",
                    year, audit.features, verb, audit.written,
                    audit.prescribed, time.monotonic() - started)
    return audit


# --------------------------------------------------------------------------
# One feature class
# --------------------------------------------------------------------------

def import_layer(source: str, source_layer: str, engine: Engine,
                 args: argparse.Namespace, provider_id: int,
                 boundary_provider_id: int | None, parts: LookupParts,
                 logger: logging.Logger) -> Audit:
    """Stage one feature class and write the years it holds, one at a time."""
    log = common.ArchiveLogger(logger, {"archive": source_layer})
    settings = common.resolve_database_settings(args)
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    total = Audit()

    log.info("Staging %s", layer_name(source_layer))
    common.load_staging_table(
        source, layer_name(source_layer), staging_table, args, settings, log,
        geometry_type="MULTIPOLYGON",
        target_srs="EPSG:4326",
        fid_column=STAGING_FID_COLUMN,
        preserve_fid=True,
    )

    with Session(engine) as session:
        staged = session.scalar(text(f"SELECT count(*) FROM {staging_table}")) or 0
        log.info("Staged %d feature(s)", staged)
        add_resolved_columns(session, staging_table, log)
        resolve_staging_columns(session, staging_table, log)
        check_states(session, staging_table, log)
        report_undated(session, staging_table, log)
        build_lookup_parts(session, staging_table, parts, boundary_provider_id, log)
        years = staged_years(session, staging_table, args.year)
        session.commit()

    if not years:
        log.warning("No year in this feature class matches the filter; nothing to do")
        return total

    log.info("Importing %s, one transaction each", summarise_years(years))
    for index, year in enumerate(years, start=1):
        log.info("Year %d of %d: %d", index, len(years), year)
        total = total + import_year(engine, args, provider_id, parts, staging_table,
                                    source_layer, year, log)

    log.info("Finished: %d feature(s) read, %d fire(s) written over %d year(s)",
             total.features, total.written, len(years))
    return total


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def report(total: Audit, logger: logging.Logger) -> None:
    """Log what the run did, in the order a reader wants to know it."""
    logger.info("Read %d published feature(s), wrote %d fire(s)",
                total.features, total.written)
    logger.info("One row per published polygon: nothing was merged, so a row count is "
                "a count of mapped polygons and not of fires")
    logger.info("Fire types: %d prescribed burn(s) of %d fire(s) written — filter on "
                "fire_type before counting wildfires", total.prescribed, total.written)
    logger.info("Start dates: %d from the extinction date, %d from the capture date, "
                "the rest from the published ignition date",
                total.from_extinguish, total.from_capture)
    if total.implausible:
        logger.warning("%d fire(s) publish dates that cannot be believed — an epoch "
                       "sentinel, a year outside 1900-2100, or an end before its start. "
                       "Stored as published with dates_plausible false", total.implausible)
    if total.empty_geometry:
        logger.warning("%d feature(s) had an empty geometry once repaired and are in no "
                       "row", total.empty_geometry)
    if total.no_time_zone:
        logger.warning("%d fire(s) matched no time zone area and are dated against their "
                       "state's zone", total.no_time_zone)
    if total.no_boundary:
        logger.warning("%d fire(s) matched no country and have no admin_boundary_id",
                       total.no_boundary)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Australian historical bushfire extents into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Re-importing replaces the years it "
               "reads, one transaction each. Database settings not given here are read "
               "from the environment (.env).",
    )
    parser.add_argument("-g", "--geodatabase", type=Path, required=True, metavar="PATH",
                        help="the file geodatabase, with or without a .gdb suffix")
    parser.add_argument("--layer", action="append",
                        choices=list(australia_csiro.SOURCE_LAYERS), metavar="LAYER",
                        help="import only this feature class: "
                             + " or ".join(australia_csiro.SOURCE_LAYERS)
                             + "; may be repeated (default: both)")
    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year, read from the resolved start date; "
                             "may be repeated")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll each year back, reporting what "
                             "would have been imported")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> Audit:
    """Import the geodatabase against ``engine``, returning the totals."""
    common.require_tables(engine, ["wildfire", "csiro_wildfire", "admin_boundary",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, australia_csiro.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, australia_csiro.PROVIDER_NAME, australia_csiro.PROVIDER_PRODUCT,
            australia_csiro.PROVIDER_FULL_NAME, australia_csiro.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    layers = args.layer or list(australia_csiro.SOURCE_LAYERS)
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    parts = LookupParts.beside(staging_table)
    total = Audit()

    try:
        with geodatabase(args.geodatabase, logger) as source:
            logger.info("Importing %d feature class(es): %s",
                        len(layers), ", ".join(layer_name(layer) for layer in layers))
            for source_layer in layers:
                total = total + import_layer(source, source_layer, engine, args,
                                             provider_id, boundary_provider_id, parts,
                                             logger)
    finally:
        if not args.keep_staging:
            with Session(engine) as session:
                common.drop_staging_table(session, staging_table, logger)
                for name in parts:
                    common.drop_staging_table(session, name, logger)
                session.commit()

    report(total, logger)
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("csiro-import")

    if not args.geodatabase.exists():
        logger.error("Not found: %s", args.geodatabase)
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
