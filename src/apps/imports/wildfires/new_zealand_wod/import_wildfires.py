#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the New Zealand Wildfire Occurrence Database.

One command over the published shapefile folder::

    python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \\
        -s /path/to/WOD_shp_1931-2025

The folder holds two shapefiles in NZTM2000, ``WOD_points`` and ``WOD_polygons`` —
**125,931 points and 2,089 perimeters, 128,020 records over 1931-2025**, no record in
both. Each record becomes four rows: a
:class:`~src.providers.new_zealand_wod.wildfire.WodWildfire`, a
:class:`~src.providers.new_zealand_wod.ignition.WodIgnition`, a
:class:`~src.providers.new_zealand_wod.terrain.WodTerrain` and a
:class:`~src.providers.new_zealand_wod.weather.WodWeather`. See
:mod:`src.providers.new_zealand_wod` for the dataset.

Nothing is refused
------------------

Unlike the NFDB import, no record in scope is dropped. The paper says every record
has a date and a location, the published data bears that out, and the decisions
taken about its dirt are all *keep and correct*:

* ``-9999``, ``NA:NA`` and ``Null`` are read as ``NULL``;
* ``WOD1e+05`` is stored as ``WOD100000`` (:func:`~src.providers.new_zealand_wod.wod_id`);
* the one negative area is stored as 0;
* invalid perimeters are repaired with ``ST_MakeValid``;
* the points in the sea — 15 of them on a placeholder coordinate — are stored as
  published, with no administrative boundary;
* a DOC record without a time starts at local midnight, its
  :attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.report_time` left
  ``NULL``.

Each of these is **counted and reported**. What the import does refuse is a
*release* it does not understand: before anything is deleted it checks the staged
records against what the model can hold — identifiers, causes, dates, coordinates,
the published vocabularies — and stops, listing the offending values, if any fails.
An unmapped cause in particular stops the run: a new release's new cause has to be
classified in :data:`~src.providers.new_zealand_wod.CAUSE_MAP` by a person, because
a new lightning spelling silently counted as *unknown* is the mistake the cause
classes exist to prevent.

The rules are Python's, applied in SQL
--------------------------------------

The identifier repair and the cause classification are defined once, in
:mod:`src.providers.new_zealand_wod`. The import reads the distinct published values
from the staged table, runs them through those functions, and hands the results to
the transform as arrays — so the SQL applies exactly the Python rule and nothing is
written twice.

The year cut, and the whole archive
------------------------------------

By default only records from :data:`~src.providers.new_zealand_wod.FIRST_YEAR`
(1998) are imported: before that the WOD is DOC alone and, in the paper's words,
does not provide good overall coverage. ``--all-years`` imports from 1931;
``--from-year`` moves the cut anywhere.

A year is the unit, and the step
---------------------------------

The staged archive is transformed one year per statement, each in a transaction of
its own, as the NFDB import does and for its reason: a statement over the whole
archive materialises the row set several times over, and a run that finishes slower
is worth any number that do not finish. Replacing a year deletes its fires — and any
fire elsewhere whose ``wod_id`` the year now carries, so a record a new release moved
to another year cannot collide with its old copy — and writes the staged ones, in
one transaction. ``--year`` re-imports one year; ``--dry-run`` rolls every year back.

A run holds an advisory lock on the staging table for its whole length, so a second
run against the same table is refused rather than allowed to reload it underneath
the first.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import typing
import zlib

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import Float
from sqlalchemy import SmallInteger
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.providers import new_zealand_wod
from src.providers.new_zealand_wod.terrain import WodTerrain
from src.providers.new_zealand_wod.weather import WodWeather

#: Default name of the staging table both shapefiles are loaded into.
DEFAULT_STAGING_TABLE = "wod_records"

#: The two published layers, in the order they are loaded.
POINTS_LAYER = "WOD_points"
POLYGONS_LAYER = "WOD_polygons"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The serial key GDAL puts on the staging table. Not ``fid``, which is GDAL's
#: default, nor ``id``, which is the published WOD identifier.
STAGING_FID_COLUMN = "ogc_fid"

#: Index built on the staged ``year`` before the per-year loop starts.
STAGING_YEAR_INDEX = "ix_staging_wod_records_year"

#: Namespace for the advisory lock one run holds against another.
STAGING_LOCK_NAMESPACE = 0x574F4400  # "WOD\0"

#: ``PRECISION=NO``: every Real is declared ``(24.15)``, and the PostgreSQL driver
#: would otherwise make each a ``numeric(24,15)``.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]


def staged_name(column: str) -> str:
    """The staged column a model column is read from.

    ``ogr2ogr`` lower-cases the published field names, and the model's names are the
    published ones in snake case — ``TempMax8B`` is ``temp_max_8b``, ``LandCvr2`` is
    ``land_cvr_2`` — so dropping the underscores gives the staged name back.
    """
    return column.replace("_", "")


#: The columns of the side tables, in table order, without their key.
TERRAIN_COLUMNS = [column for column in WodTerrain.__table__.columns if column.name != "id"]
WEATHER_COLUMNS = [column for column in WodWeather.__table__.columns if column.name != "id"]

#: Every attribute the mapping reads, with the PostgreSQL type it needs, named as
#: ``ogr2ogr`` lands it.
#:
#: Several numeric attributes are published as **text** — ``WS``, every ``FDC*``,
#: ``HFI*`` and ``ROS*`` — and are converted here, once, rather than cast wherever
#: they are read. ``Lat``/``Lon``, ``Hour``/``Minute`` and ``EndFY``/``FY`` are not
#: read: each is derivable from a column that is.
STAGING_COLUMNS: dict[str, str] = {
    "id": "text",
    "source": "text",
    "orgid": "text",
    "x": "double precision",
    "y": "double precision",
    "day": "integer",
    "month": "integer",
    "year": "integer",
    "time": "text",
    "season": "text",
    "startfy": "double precision",
    "areaha": "double precision",
    "areacat": "text",
    "orgveg": "text",
    "ignsource": "text",
    "fenzdist": "text",
    "orgiddrop": "text",
    **{staged_name(column.name): ("text" if column.type.python_type is str
                                  else "double precision")
       for column in TERRAIN_COLUMNS + WEATHER_COLUMNS},
}

#: The loaded types each declared type accepts without a conversion.
#:
#: ``integer`` accepts only itself: the WOD publishes ``Day``, ``Month`` and ``Year``
#: as ``Integer64``, which lands as ``bigint``, and ``make_date`` takes ``integer``.
COMPATIBLE_TYPES = {
    "integer": {"integer"},
    "double precision": {"double precision", "real", "numeric", "integer", "bigint",
                         "smallint"},
    "text": {"text", "character varying", "character"},
}


def clean_text(expression: str) -> str:
    """SQL reading a published text attribute: trimmed, and ``NULL`` for no value."""
    spellings = ", ".join(f"'{value}'" for value in sorted(new_zealand_wod.NO_DATA_TEXTS))
    return (f"CASE WHEN btrim({expression}) IN ('', {spellings}) THEN NULL "
            f"ELSE btrim({expression}) END")


def clean_number(expression: str) -> str:
    """SQL reading a published number: ``NULL`` for the ``-9999`` sentinel."""
    return f"NULLIF({expression}, {new_zealand_wod.NO_DATA})"


def side_table_value(column) -> str:
    """SQL reading the staged value of one terrain or weather column."""
    source = f"staging.{staged_name(column.name)}"
    if column.type.python_type is str:
        return clean_text(source)
    if isinstance(column.type, SmallInteger):
        return f"CAST({clean_number(source)} AS smallint)"
    assert isinstance(column.type, Float), column
    return clean_number(source)


#: The ``WHERE`` that puts a staged row in scope: the year cut and ``--year``.
SCOPE_SQL = "staging.year >= :from_year AND ({year_filter})"

#: The published identifier as stored: repaired where :data:`IDS_SQL` found it needed.
WOD_ID_SQL = "COALESCE(ids.repaired, btrim(staging.id))"

#: Joins the identifier repairs onto a staged row.
IDS_JOIN_SQL = """
LEFT JOIN unnest(CAST(:id_published AS text[]), CAST(:id_repaired AS text[]))
    AS ids(published, repaired) ON ids.published = btrim(staging.id)
"""

#: Joins the cause classification onto a staged row. Matched on the value exactly as
#: staged, so the Python rule — which strips and normalises — is the only rule.
CAUSES_JOIN_SQL = """
LEFT JOIN unnest(CAST(:cause_published AS text[]), CAST(:cause_stored AS text[]),
                 CAST(:cause_class AS text[]))
    AS causes(published, stored, class) ON causes.published = staging.ignsource
"""

#: The distinct identifiers that are not plain ``WOD<n>``, for
#: :func:`~src.providers.new_zealand_wod.wod_id` to repair. One, in the 2025 release.
IDS_SQL = """
SELECT DISTINCT staging.id FROM {staging_table} AS staging
WHERE {scope} AND (staging.id IS NULL OR btrim(staging.id) !~ '^WOD[0-9]+$')
"""

#: The distinct published causes, for :func:`~src.providers.new_zealand_wod.fire_cause`.
CAUSES_SQL = """
SELECT DISTINCT staging.ignsource FROM {staging_table} AS staging
WHERE {scope} AND staging.ignsource IS NOT NULL
"""

#: Identifiers that two staged records would share once repaired.
DUPLICATE_IDS_SQL = """
SELECT {wod_id} AS wod_id FROM {staging_table} AS staging
{ids_join}
WHERE {scope}
GROUP BY 1 HAVING count(*) > 1
ORDER BY 1 LIMIT 10
"""

#: A record with no year. Checked over the whole staged table, not the scope: the
#: scope is a condition on the year, so such a record would otherwise fall out of
#: every year silently.
NO_YEAR_SQL = """
SELECT staging.id FROM {staging_table} AS staging WHERE staging.year IS NULL LIMIT 10
"""

#: A local date that does not exist, or a part of one that is missing.
BAD_DATES_SQL = """
SELECT staging.id || ': ' || coalesce(staging.year::text, '?') || '-'
       || coalesce(staging.month::text, '?') || '-' || coalesce(staging.day::text, '?')
FROM {staging_table} AS staging
WHERE {scope}
  AND (staging.month IS NULL OR staging.day IS NULL
       OR staging.month NOT BETWEEN 1 AND 12
       OR staging.day NOT BETWEEN 1 AND
          extract(DAY FROM make_date(staging.year, staging.month, 1)
                           + interval '1 month - 1 day'))
LIMIT 10
"""

#: A published ``Time`` that is neither ``HH:MM`` nor the no-time ``NA:NA``.
BAD_TIMES_SQL = """
SELECT DISTINCT staging.time FROM {staging_table} AS staging
WHERE {scope}
  AND staging.time IS NOT NULL
  AND btrim(staging.time) <> :no_time
  AND btrim(staging.time) !~ '^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
LIMIT 10
"""

#: A record with no coordinate, which the paper says cannot happen.
NO_LOCATION_SQL = """
SELECT staging.id FROM {staging_table} AS staging
WHERE {scope}
  AND (staging.x IS NULL OR staging.y IS NULL
       OR staging.x = :no_data OR staging.y = :no_data)
LIMIT 10
"""

#: A fire year that is not the calendar year or the one before.
BAD_FINANCIAL_YEARS_SQL = """
SELECT staging.id || ': ' || coalesce(staging.startfy::text, 'none') || ' for '
       || staging.year
FROM {staging_table} AS staging
WHERE {scope}
  AND (staging.startfy IS NULL
       OR staging.startfy NOT IN (staging.year - 1, staging.year))
LIMIT 10
"""

#: Published values outside a vocabulary the model constrains. ``{required}`` makes
#: a missing value an offence too, for the columns that are ``NOT NULL``.
VOCABULARY_SQL = """
SELECT DISTINCT coalesce({value}, '(none)') FROM {staging_table} AS staging
WHERE {scope}
  AND ({value} IS NULL AND {required} OR {value} <> ALL(:allowed))
LIMIT 10
"""

#: A fire danger class that is not a whole number from 1 to 5.
BAD_FIRE_DANGER_CLASS_SQL = """
SELECT DISTINCT {value} FROM {staging_table} AS staging
WHERE {scope}
  AND {value} IS NOT NULL
  AND ({value} <> round({value}) OR {value} NOT BETWEEN :low AND :high)
LIMIT 10
"""

#: Published facts worth a line in the log and not a refusal: counted over every
#: staged record in scope, because both cross years.
OBSERVATIONS_SQL = """
SELECT
    (SELECT count(*) FROM (
        SELECT 1 FROM {staging_table} AS staging
        WHERE {scope} AND {org_id} IS NOT NULL
        GROUP BY staging.source, {org_id} HAVING count(*) > 1) AS d)
        AS duplicated_org_ids,
    (SELECT count(*) FROM {staging_table} AS staging
     WHERE {scope} AND ST_GeometryType(staging.geom) LIKE '%Polygon'
       AND {org_id} IN (SELECT {org_id} FROM {staging_table} AS staging
                        WHERE {scope} AND ST_GeometryType(staging.geom) = 'ST_Point'))
        AS polygon_org_ids_in_points,
    (SELECT count(*) FROM {staging_table} AS staging
     WHERE {scope} AND {dropped} IS NOT NULL) AS dropped_fenz_records
"""

#: The years the staged archive holds records in, after the year cut and ``--year``.
STAGED_YEARS_SQL = """
SELECT DISTINCT staging.year AS year
FROM {staging_table} AS staging
WHERE {scope}
ORDER BY year
"""

#: Removes the fires of the years about to be re-imported, with their points, their
#: terrain and their weather (those two by ``ON DELETE CASCADE``).
#:
#: Also removes, wherever it is, any fire whose ``wod_id`` a staged record of these
#: years carries: the identifier is unique and stable, so a record a new release has
#: moved to another year would otherwise collide with its own old copy.
DELETE_YEARS_SQL = """
WITH doomed AS (
    SELECT id, ignition_id FROM wod_wildfire
    WHERE year = ANY(:years)
       OR wod_id IN (SELECT {wod_id} FROM {staging_table} AS staging
                     {ids_join}
                     WHERE staging.year = ANY(:years))
),
removed_child AS (
    DELETE FROM wod_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM wod_ignition WHERE id IN (SELECT ignition_id FROM doomed) RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: Maps **one year** of the staged archive onto the six tables of the model.
#:
#: The CTEs, in order:
#:
#: ``cleaned``
#:     Every published attribute the fire needs, ``-9999`` and ``NA:NA`` read as
#:     ``NULL``, the identifier repaired and the cause classified by the arrays the
#:     Python rules produced. The point is built from the published ``X``/``Y`` for
#:     every record, polygon records included — that is the record's location, and
#:     for a point record it is exactly the staged geometry (counted where not).
#: ``prepared``
#:     The area clamped at 0 and the perimeter made valid.
#: ``numbered``
#:     Keys drawn from both sequences up front; ``MATERIALIZED`` so that ``nextval``
#:     runs once per row.
#: ``zoned``
#:     Zone and country from the point. A point no time zone area contains — at sea,
#:     or with no areas imported — falls back to the Chatham zone for the Chatham
#:     district and the mainland zone otherwise.
#: ``timed``
#:     The local report time, midnight where none was published, and the instant it
#:     is in its zone.
#: ``ins_*`` / ``written``
#:     The point, the fire, its terrain and its weather. The last two read their
#:     columns from the staged row again by its key, so that the eighty-odd of them
#:     are not carried through every CTE above.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT staging.{fid} AS fid,
           {wod_id} AS wod_id,
           {wod_id} <> btrim(staging.id) AS id_repaired,
           {source} AS source,
           {org_id} AS org_id,
           {dropped} AS dropped_fenz_org_id,
           staging.year AS year,
           make_date(staging.year, staging.month, staging.day) AS report_date,
           CASE WHEN btrim(staging.time) = :no_time THEN NULL
                ELSE CAST(btrim(staging.time) AS time) END AS report_time,
           {season} AS season,
           CAST(staging.startfy AS integer) AS financial_year,
           {area} AS published_area,
           {area_category} AS area_category,
           causes.stored AS ignition_source,
           COALESCE(causes.class, :cause_unknown) AS fire_cause,
           {vegetation} AS original_vegetation,
           {district} AS fenz_district,
           staging.x AS x,
           staging.y AS y,
           ST_SetSRID(ST_MakePoint(staging.x, staging.y), :srid) AS point,
           ST_GeometryType(staging.geom) LIKE '%Polygon' AS has_polygon,
           ST_Force2D(staging.geom) AS geom
    FROM {staging_table} AS staging
    {ids_join}
    {causes_join}
    WHERE {scope}
),
prepared AS MATERIALIZED (
    SELECT cleaned.*,
           CASE WHEN cleaned.published_area < 0 THEN 0
                ELSE cleaned.published_area END AS area_ha,
           cleaned.has_polygon AND NOT ST_IsValid(cleaned.geom) AS perimeter_repaired,
           CASE WHEN cleaned.has_polygon THEN repaired.geometry END AS perimeter_nztm,
           NOT cleaned.has_polygon
               AND NOT ST_Equals(cleaned.geom, cleaned.point) AS point_disagrees
    FROM cleaned
    LEFT JOIN LATERAL (
        SELECT CASE WHEN ST_IsEmpty(made.geometry) THEN NULL ELSE made.geometry END
                   AS geometry
        FROM (SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(cleaned.geom), 3))
                  AS geometry) AS made
        WHERE cleaned.has_polygon
    ) AS repaired ON TRUE
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           nextval(pg_get_serial_sequence('ignition', 'id')) AS ignition_id,
           prepared.*
    FROM prepared
),
zoned AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(numbered.point, 4326) AS point_4326,
           ST_Transform(numbered.perimeter_nztm, 4326) AS perimeter_4326,
           COALESCE(zone.name,
                    CASE WHEN numbered.fenz_district = :chatham_district
                         THEN :chatham_time_zone ELSE :default_time_zone END)
               AS time_zone,
           zone.name IS NULL AS zone_fallback,
           country.id AS admin_boundary_id
    FROM numbered
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry, ST_Transform(numbered.point, 4326))
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry, ST_Transform(numbered.point, 4326))
        LIMIT 1
    ) AS country ON TRUE
),
timed AS MATERIALIZED (
    SELECT zoned.*,
           zoned.report_date + COALESCE(zoned.report_time, time '00:00') AS local_start,
           (zoned.report_date + COALESCE(zoned.report_time, time '00:00'))
               AT TIME ZONE zoned.time_zone AS start_instant
    FROM zoned
),
ins_ignition AS (
    INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                          admin_boundary_id)
    SELECT timed.ignition_id, 'wod_ignition', :provider_id, timed.point_4326,
           timed.start_instant, timed.time_zone, timed.admin_boundary_id
    FROM timed
    RETURNING id
),
ins_wod_ignition AS (
    INSERT INTO wod_ignition (id, wod_id, year, source, geometry_nztm)
    SELECT timed.ignition_id, timed.wod_id, timed.year, timed.source, timed.point
    FROM timed
    JOIN ins_ignition ON ins_ignition.id = timed.ignition_id
    RETURNING id
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT timed.wildfire_id, 'wod_wildfire', :provider_id, timed.start_instant, NULL,
           timed.time_zone, timed.perimeter_4326, timed.admin_boundary_id
    FROM timed
    RETURNING id
),
written AS (
    INSERT INTO wod_wildfire (id, wod_id, source, org_id, dropped_fenz_org_id, year,
                              report_date, report_time, season, financial_year,
                              area_ha, area_category, ignition_source, fire_cause,
                              original_vegetation, fenz_district, perimeter_nztm,
                              ignition_id)
    SELECT timed.wildfire_id, timed.wod_id, timed.source, timed.org_id,
           timed.dropped_fenz_org_id, timed.year, timed.report_date, timed.report_time,
           timed.season, timed.financial_year, timed.area_ha, timed.area_category,
           timed.ignition_source, timed.fire_cause, timed.original_vegetation,
           timed.fenz_district, timed.perimeter_nztm, timed.ignition_id
    FROM timed
    JOIN ins_wildfire ON ins_wildfire.id = timed.wildfire_id
    JOIN ins_wod_ignition ON ins_wod_ignition.id = timed.ignition_id
    RETURNING id
),
ins_terrain AS (
    INSERT INTO wod_terrain (id, {terrain_columns})
    SELECT written.id, {terrain_values}
    FROM written
    JOIN timed ON timed.wildfire_id = written.id
    JOIN {staging_table} AS staging ON staging.{fid} = timed.fid
    RETURNING id
),
ins_weather AS (
    INSERT INTO wod_weather (id, {weather_columns})
    SELECT written.id, {weather_values}
    FROM written
    JOIN timed ON timed.wildfire_id = written.id
    JOIN {staging_table} AS staging ON staging.{fid} = timed.fid
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS in_scope,
       (SELECT count(*) FROM written) AS written,
       (SELECT count(*) FROM ins_terrain) AS with_terrain,
       (SELECT count(*) FROM ins_weather) AS with_weather,
       (SELECT count(*) FROM cleaned WHERE id_repaired) AS ids_repaired,
       (SELECT count(*) FROM cleaned WHERE report_time IS NULL) AS without_time,
       (SELECT count(*) FROM cleaned WHERE published_area < 0) AS areas_clamped,
       (SELECT count(*) FROM cleaned WHERE has_polygon) AS with_polygon,
       (SELECT count(*) FROM prepared WHERE perimeter_repaired) AS perimeters_repaired,
       (SELECT count(*) FROM prepared
        WHERE has_polygon AND perimeter_nztm IS NULL) AS perimeters_empty,
       (SELECT count(*) FROM prepared WHERE point_disagrees) AS points_disagreeing,
       (SELECT count(*) FROM cleaned WHERE fenz_district IS NULL) AS without_district,
       (SELECT count(*) FROM cleaned
        WHERE x = :placeholder_x AND y = :placeholder_y) AS placeholder_points,
       (SELECT count(*) FROM zoned WHERE zone_fallback) AS zone_fallbacks,
       (SELECT count(*) FROM zoned WHERE time_zone = :chatham_time_zone) AS chatham,
       (SELECT count(*) FROM zoned WHERE admin_boundary_id IS NULL) AS without_country,
       (SELECT count(*) FROM timed
        WHERE report_time IS NOT NULL
          AND (start_instant AT TIME ZONE time_zone) <> local_start) AS dst_gaps,
       (SELECT count(*) FROM timed
        WHERE report_time IS NOT NULL
          AND (((start_instant + interval '1 hour') AT TIME ZONE time_zone) = local_start
               OR ((start_instant - interval '1 hour') AT TIME ZONE time_zone)
                  = local_start)) AS dst_overlaps,
       (SELECT count(*) FROM cleaned WHERE fire_cause = :cause_lightning) AS lightning,
       (SELECT count(*) FROM cleaned WHERE fire_cause = :cause_natural) AS "natural",
       (SELECT count(*) FROM cleaned WHERE fire_cause = :cause_human) AS human,
       (SELECT count(*) FROM cleaned WHERE fire_cause = :cause_unknown) AS unknown
"""


# --------------------------------------------------------------------------
# The rules, as SQL parameters
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """The Python rules, evaluated over the staged values, for the SQL to apply.

    Attributes
    ----------
    id_published, id_repaired : list of str
        Each staged identifier that is not plain ``WOD<n>``, and what
        :func:`~src.providers.new_zealand_wod.wod_id` makes of it.
    cause_published, cause_stored, cause_class : list
        Each distinct staged ``IgnSource``, what
        :func:`~src.providers.new_zealand_wod.published_ignition_source` stores for it
        and what :func:`~src.providers.new_zealand_wod.fire_cause` classifies it as.
    """

    id_published: list[str]
    id_repaired: list[str]
    cause_published: list[str]
    cause_stored: list[str | None]
    cause_class: list[str]

    def parameters(self) -> dict[str, object]:
        return {
            "id_published": self.id_published, "id_repaired": self.id_repaired,
            "cause_published": self.cause_published, "cause_stored": self.cause_stored,
            "cause_class": self.cause_class,
        }


def scope_parameters(from_year: int, years: list[int] | None) -> dict[str, object]:
    """The parameters :data:`SCOPE_SQL` reads."""
    parameters: dict[str, object] = {"from_year": from_year}
    if years:
        parameters["years"] = years
    return parameters


def year_filter(years: list[int] | None) -> str:
    """The ``WHERE`` fragment applying ``--year``, or one that is always true."""
    if not years:
        return "TRUE"
    return "staging.year = ANY(:years)"


def scope(years: list[int] | None) -> str:
    """:data:`SCOPE_SQL` for ``years``."""
    return SCOPE_SQL.format(year_filter=year_filter(years))


def build_rules(session: Session, staging_table: str, from_year: int,
                years: list[int] | None) -> Rules:
    """Run the identifier and cause rules over the distinct staged values.

    Raises
    ------
    RuntimeError
        Listing **every** identifier that is not one and **every** cause that
        :data:`~src.providers.new_zealand_wod.CAUSE_MAP` does not classify, so that
        one run says everything that has to be fixed rather than the first thing.
    """
    parameters = scope_parameters(from_year, years)
    where = scope(years)

    id_published, id_repaired, bad_ids = [], [], []
    for published in session.scalars(text(
            IDS_SQL.format(staging_table=staging_table, scope=where)), parameters):
        try:
            id_repaired.append(new_zealand_wod.wod_id(published or ""))
            id_published.append(published.strip())
        except ValueError:
            bad_ids.append(repr(published))

    cause_published, cause_stored, cause_class, unmapped = [], [], [], []
    for published in session.scalars(text(
            CAUSES_SQL.format(staging_table=staging_table, scope=where)), parameters):
        try:
            cause_class.append(new_zealand_wod.fire_cause(published))
        except new_zealand_wod.UnmappedCauseError:
            unmapped.append(repr(published))
            continue
        cause_published.append(published)
        cause_stored.append(new_zealand_wod.published_ignition_source(published))

    problems = []
    if bad_ids:
        problems.append(f"{len(bad_ids)} identifier(s) that are not WOD identifiers: "
                        f"{', '.join(sorted(bad_ids)[:10])}")
    if unmapped:
        problems.append(f"{len(unmapped)} ignition source(s) not classified by "
                        f"src.providers.new_zealand_wod.CAUSE_MAP — add them there: "
                        f"{', '.join(sorted(unmapped))}")
    if problems:
        raise RuntimeError("the staged release has " + "; and ".join(problems))
    return Rules(id_published, id_repaired, cause_published, cause_stored, cause_class)


# --------------------------------------------------------------------------
# Staging checks
# --------------------------------------------------------------------------

def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.LoggerAdapter) -> None:
    """Make sure the staged table has every attribute the mapping reads, typed usably.

    Text that holds numbers is converted with blanks read as ``NULL``, which is what
    an empty DBF cell is.

    Raises
    ------
    RuntimeError
        If the staged layers publish none of an attribute the mapping needs.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = dict(session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema or "public", "table": table}).all())

    missing = [name for name in STAGING_COLUMNS if name not in loaded]
    if missing:
        raise RuntimeError(
            f"the staged layers publish no {', '.join(missing)}: this is not the WOD, "
            f"or its attributes have been renamed"
        )

    for name, wanted in STAGING_COLUMNS.items():
        if loaded[name] in COMPATIBLE_TYPES[wanted]:
            continue
        logger.debug("Converting staged %s from %s to %s", name, loaded[name], wanted)
        source = (f"NULLIF(btrim({name}), '')" if loaded[name] in COMPATIBLE_TYPES["text"]
                  else name)
        session.execute(text(
            f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {wanted} "
            f"USING CAST({source} AS {wanted})"
        ))


#: The constrained vocabularies the release is checked against: the staged column,
#: the values allowed, and whether a missing value is an offence too.
VOCABULARIES = [
    ("source", new_zealand_wod.SOURCES, True),
    ("season", new_zealand_wod.SEASONS, True),
    ("areacat", new_zealand_wod.AREA_CATEGORIES, False),
    ("enso", new_zealand_wod.ENSO_PHASES, False),
]


def check_release(session: Session, staging_table: str, rules: Rules, from_year: int,
                  years: list[int] | None) -> None:
    """Refuse a staged release the model cannot hold, before anything is deleted.

    Each check is one the model would otherwise enforce by failing a constraint
    halfway through the run — with some years already replaced — or one the paper
    says cannot fail. All are run, and all failures reported together.

    Raises
    ------
    RuntimeError
        Naming each failed check and up to ten of its offending values.
    """
    where = scope(years)
    parameters = {**scope_parameters(from_year, years), **rules.parameters(),
                  "no_time": new_zealand_wod.NO_TIME, "no_data": new_zealand_wod.NO_DATA}

    def offending(statement: str, **placeholders) -> list[str]:
        formatted = statement.format(staging_table=staging_table, scope=where,
                                     **placeholders)
        return [str(value) for value in session.scalars(text(formatted), parameters)]

    problems: list[str] = []

    def check(label: str, values: list[str]) -> None:
        if values:
            problems.append(f"{label}: {', '.join(values)}")

    check("identifiers shared by two records once repaired",
          offending(DUPLICATE_IDS_SQL, wod_id=WOD_ID_SQL, ids_join=IDS_JOIN_SQL))
    check("records with no year", [str(value) for value in session.scalars(
        text(NO_YEAR_SQL.format(staging_table=staging_table)))])
    check("dates that do not exist", offending(BAD_DATES_SQL))
    check("times that are neither HH:MM nor NA:NA", offending(BAD_TIMES_SQL))
    check("records with no location", offending(NO_LOCATION_SQL))
    check("fire years that are not the year or the one before",
          offending(BAD_FINANCIAL_YEARS_SQL))

    for column, allowed, required in VOCABULARIES:
        statement = VOCABULARY_SQL.format(
            staging_table=staging_table, scope=where,
            value=clean_text(f"staging.{column}"), required="TRUE" if required else "FALSE")
        values = session.scalars(text(statement),
                                 {**parameters, "allowed": list(allowed)}).all()
        check(f"{column} values outside {list(allowed)}", [str(v) for v in values])

    low, high = new_zealand_wod.FIRE_DANGER_CLASS_RANGE
    for column in WEATHER_COLUMNS:
        if not isinstance(column.type, SmallInteger):
            continue
        statement = BAD_FIRE_DANGER_CLASS_SQL.format(
            staging_table=staging_table, scope=where,
            value=clean_number(f"staging.{staged_name(column.name)}"))
        values = session.scalars(text(statement),
                                 {**parameters, "low": low, "high": high}).all()
        check(f"{staged_name(column.name)} values that are not a class from {low} to "
              f"{high}", [str(v) for v in values])

    if problems:
        raise RuntimeError("the staged release cannot be imported as it is — "
                           + "; ".join(problems))


@dataclass(frozen=True)
class Observations:
    """Facts about the release worth reporting, that cross years.

    Attributes
    ----------
    duplicated_org_ids : int
        Agency numbers used by more than one record of the same source.
    polygon_org_ids_in_points : int
        Polygon records whose agency number a point record also carries.
    dropped_fenz_records : int
        DOC records that replaced a FENZ record of the same fire.
    """

    duplicated_org_ids: int
    polygon_org_ids_in_points: int
    dropped_fenz_records: int


def observe(session: Session, staging_table: str, from_year: int,
            years: list[int] | None) -> Observations:
    """Count the :class:`Observations` over the staged records in scope."""
    statement = OBSERVATIONS_SQL.format(
        staging_table=staging_table, scope=scope(years),
        org_id=clean_text("staging.orgid"), dropped=clean_text("staging.orgiddrop"))
    row = session.execute(text(statement), scope_parameters(from_year, years)).one()
    return Observations(row.duplicated_org_ids, row.polygon_org_ids_in_points,
                        row.dropped_fenz_records)


# --------------------------------------------------------------------------
# The years
# --------------------------------------------------------------------------

def staged_years(session: Session, staging_table: str, from_year: int,
                 years: list[int] | None) -> list[int]:
    """The years the staged archive holds records in — the steps the import walks."""
    statement = STAGED_YEARS_SQL.format(staging_table=staging_table, scope=scope(years))
    return list(session.scalars(text(statement), scope_parameters(from_year, years)).all())


def summarise_years(years: list[int]) -> str:
    """``1998-2000, 2003`` — a list of years compressed to its ranges."""
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


def delete_years(session: Session, staging_table: str, rules: Rules,
                 years: list[int]) -> None:
    """Remove the fires of the years about to be re-imported. See :data:`DELETE_YEARS_SQL`."""
    statement = DELETE_YEARS_SQL.format(staging_table=staging_table, wod_id=WOD_ID_SQL,
                                        ids_join=IDS_JOIN_SQL)
    session.execute(text(statement), {"years": years, "id_published": rules.id_published,
                                      "id_repaired": rules.id_repaired})


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Audit:
    """What the transform did, for the summary lines.

    Every field is a count over a partition of the staged records — one year at a
    time — so the years' audits add up to what one pass would have reported.
    :meth:`__add__` is what adds them.

    Attributes
    ----------
    in_scope, written : int
        Records the year cut let through, and fires stored. Equal, unless something
        is badly wrong: nothing in scope is refused.
    with_terrain, with_weather : int
        Terrain and weather rows stored: one each per fire.
    ids_repaired : int
        Identifiers written in scientific notation and repaired.
    without_time : int
        Records with no report time, dated to local midnight.
    areas_clamped : int
        Negative published areas stored as 0.
    with_polygon, perimeters_repaired, perimeters_empty : int
        Polygon records, those whose polygon was invalid and was made valid, and those
        whose polygon was nothing once valid (stored without a perimeter).
    points_disagreeing : int
        Point records whose geometry is not their published ``X``/``Y``. The ``X``/``Y``
        is what is stored. None in the 2025 release.
    without_district, placeholder_points : int
        Records with no FENZ district — their point is in the sea — and those of them
        on the placeholder coordinate.
    zone_fallbacks, chatham : int
        Records no time zone area contains, and records dated in the Chatham zone.
    without_country : int
        Records no country boundary contains.
    dst_gaps, dst_overlaps : int
        Report times that do not exist in their zone (the spring-forward hour) or
        exist twice (the fall-back hour). PostgreSQL resolves both; they are counted
        because each is an hour of uncertainty.
    lightning, natural, human, unknown : int
        Records per cause class.
    """

    in_scope: int = 0
    written: int = 0
    with_terrain: int = 0
    with_weather: int = 0
    ids_repaired: int = 0
    without_time: int = 0
    areas_clamped: int = 0
    with_polygon: int = 0
    perimeters_repaired: int = 0
    perimeters_empty: int = 0
    points_disagreeing: int = 0
    without_district: int = 0
    placeholder_points: int = 0
    zone_fallbacks: int = 0
    chatham: int = 0
    without_country: int = 0
    dst_gaps: int = 0
    dst_overlaps: int = 0
    lightning: int = 0
    natural: int = 0
    human: int = 0
    unknown: int = 0

    @classmethod
    def from_row(cls, row) -> Audit:
        """The audit the transform's one row reports."""
        return cls(**{field.name: getattr(row, field.name) for field in fields(cls)})

    def __add__(self, other: Audit) -> Audit:
        """The two years' counts, summed field by field."""
        return Audit(**{field.name: getattr(self, field.name) + getattr(other, field.name)
                        for field in fields(self)})


def transform_statement(staging_table: str, years: list[int] | None) -> str:
    """:data:`TRANSFORM_SQL`, formatted for ``staging_table`` and ``years``."""
    return TRANSFORM_SQL.format(
        staging_table=staging_table,
        fid=STAGING_FID_COLUMN,
        scope=scope(years),
        wod_id=WOD_ID_SQL,
        ids_join=IDS_JOIN_SQL,
        causes_join=CAUSES_JOIN_SQL,
        source=clean_text("staging.source"),
        org_id=clean_text("staging.orgid"),
        dropped=clean_text("staging.orgiddrop"),
        season=clean_text("staging.season"),
        area=clean_number("staging.areaha"),
        area_category=clean_text("staging.areacat"),
        vegetation=clean_text("staging.orgveg"),
        district=clean_text("staging.fenzdist"),
        terrain_columns=", ".join(column.name for column in TERRAIN_COLUMNS),
        terrain_values=", ".join(side_table_value(column) for column in TERRAIN_COLUMNS),
        weather_columns=", ".join(column.name for column in WEATHER_COLUMNS),
        weather_values=", ".join(side_table_value(column) for column in WEATHER_COLUMNS),
    )


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, rules: Rules, from_year: int,
              years: list[int] | None) -> Audit:
    """Map the staged records of ``years`` onto the model."""
    parameters: dict[str, object] = {
        **scope_parameters(from_year, years),
        **rules.parameters(),
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "srid": new_zealand_wod.SOURCE_SRID,
        "no_time": new_zealand_wod.NO_TIME,
        "default_time_zone": new_zealand_wod.DEFAULT_TIME_ZONE,
        "chatham_time_zone": new_zealand_wod.CHATHAM_TIME_ZONE,
        "chatham_district": new_zealand_wod.CHATHAM_DISTRICT,
        "placeholder_x": new_zealand_wod.PLACEHOLDER_X,
        "placeholder_y": new_zealand_wod.PLACEHOLDER_Y,
        "cause_lightning": new_zealand_wod.CAUSE_LIGHTNING,
        "cause_natural": new_zealand_wod.CAUSE_NATURAL,
        "cause_human": new_zealand_wod.CAUSE_HUMAN,
        "cause_unknown": new_zealand_wod.CAUSE_UNKNOWN,
    }
    statement = transform_statement(staging_table, years)
    return Audit.from_row(session.execute(text(statement), parameters).one())


# --------------------------------------------------------------------------
# Importing the release
# --------------------------------------------------------------------------

def layer_paths(folder: Path) -> tuple[Path, Path]:
    """The two published shapefiles in ``folder``.

    Raises
    ------
    RuntimeError
        If either is missing: a WOD release is both layers, and importing one would
        replace every year with half its records.
    """
    points = folder / f"{POINTS_LAYER}.shp"
    polygons = folder / f"{POLYGONS_LAYER}.shp"
    missing = [path.name for path in (points, polygons) if not path.exists()]
    if missing:
        raise RuntimeError(f"{folder} holds no {' or '.join(missing)}: pass the "
                           f"WOD_shp_* folder of the release")
    return points, polygons


def load_release(folder: Path, staging_table: str, args: argparse.Namespace,
                 logger: logging.LoggerAdapter) -> None:
    """Stage both layers into one table, in NZTM2000, points first."""
    settings = common.resolve_database_settings(args)
    for index, path in enumerate(layer_paths(folder)):
        datasource, layer = common.shapefile_datasource(path)
        common.load_staging_table(
            datasource, layer, staging_table, args, settings, logger,
            geometry_type="GEOMETRY",
            target_srs=f"EPSG:{new_zealand_wod.SOURCE_SRID}",
            append=index > 0,
            fid_column=STAGING_FID_COLUMN,
            creation_options=STAGING_CREATION_OPTIONS,
        )


@contextmanager
def exclusive_run(engine: Engine, staging_table: str,
                  log: logging.LoggerAdapter) -> typing.Iterator[None]:
    """Hold the staging table against a second run, for the whole import.

    ``ogr2ogr -overwrite`` replaces the staged table outside any transaction, so two
    runs on one table destroy each other; see the NFDB import, where it happened. A
    PostgreSQL advisory lock, released when the connection closes.

    Raises
    ------
    RuntimeError
        If another import already holds it.
    """
    key = zlib.crc32(staging_table.encode("utf-8")) % 2**31
    with engine.connect() as connection:
        held = connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :key)"),
            {"namespace": STAGING_LOCK_NAMESPACE, "key": key},
        ).scalar()
        if not held:
            raise RuntimeError(
                f"another import is already running against {staging_table}. Wait for "
                f"it to finish, or pass --staging-table to give this run one of its own."
            )
        log.debug("Holding the staging lock on %s", staging_table)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": STAGING_LOCK_NAMESPACE, "key": key},
            )


def assert_year_survived(year: int, audit: Audit, staging_table: str) -> None:
    """Refuse to commit a year the staged table stopped holding records for.

    The year was listed by reading the staged table, with the condition the transform
    applies, so zero records in scope means the table changed underneath the run.
    Raising rolls back the delete that emptied the year.
    """
    if audit.in_scope:
        return
    raise RuntimeError(
        f"{year} was listed as staged and then had no records: {staging_table} changed "
        f"while this run was reading it. Nothing has been committed for {year}, but "
        f"earlier years of this run have already been replaced. Re-run this import alone."
    )


def prepare_staging(session: Session, staging_table: str, args: argparse.Namespace,
                    log: logging.LoggerAdapter) -> tuple[list[int], Rules]:
    """Ready the staged table, check the release and say which years it holds."""
    normalise_staging_columns(session, staging_table, log)
    session.execute(text(
        f"CREATE INDEX IF NOT EXISTS {STAGING_YEAR_INDEX} ON {staging_table} (year)"
    ))
    session.execute(text(f"ANALYZE {staging_table}"))

    rules = build_rules(session, staging_table, args.from_year, args.year)
    check_release(session, staging_table, rules, args.from_year, args.year)

    observations = observe(session, staging_table, args.from_year, args.year)
    if observations.duplicated_org_ids:
        log.info("%d agency number(s) are used by more than one record of the same "
                 "source; records are identified by their WOD ID, so all are kept",
                 observations.duplicated_org_ids)
    if observations.polygon_org_ids_in_points:
        log.info("%d polygon record(s) share an agency number with a point record; "
                 "both are kept", observations.polygon_org_ids_in_points)
    if observations.dropped_fenz_records:
        log.info("%d DOC record(s) replaced a FENZ record of the same fire (OrgIDDrop)",
                 observations.dropped_fenz_records)

    return staged_years(session, staging_table, args.from_year, args.year), rules


def drop_staging(engine: Engine, staging_table: str, args: argparse.Namespace,
                 log: logging.LoggerAdapter) -> None:
    """Drop the staged table, unless asked to keep it or under ``--dry-run``."""
    if args.keep_staging or args.dry_run:
        return
    with Session(engine) as session:
        common.drop_staging_table(session, staging_table, log)
        session.commit()


def import_year(engine: Engine, args: argparse.Namespace, provider_id: int,
                boundary_provider_id: int | None, staging_table: str, rules: Rules,
                year: int) -> Audit:
    """Replace one year, in a transaction of its own."""
    with Session(engine) as session:
        delete_years(session, staging_table, rules, [year])
        audit = transform(session, provider_id, boundary_provider_id, staging_table,
                          rules, args.from_year, [year])
        assert_year_survived(year, audit, staging_table)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    return audit


def report(audit: Audit, years: list[int], started: float, dry_run: bool,
           log: logging.LoggerAdapter) -> None:
    """The summary lines: every correction counted, every oddity named."""
    if audit.written != audit.in_scope:  # pragma: no cover - nothing in scope is refused
        log.warning("%d record(s) in scope were not stored", audit.in_scope - audit.written)
    if audit.ids_repaired:
        log.info("%d identifier(s) written in scientific notation were repaired",
                 audit.ids_repaired)
    if audit.without_time:
        log.info("%d record(s) publish no report time and start at local midnight",
                 audit.without_time)
    if audit.areas_clamped:
        log.warning("%d negative area(s) were stored as 0", audit.areas_clamped)
    if audit.perimeters_repaired:
        log.info("%d invalid perimeter(s) were made valid", audit.perimeters_repaired)
    if audit.perimeters_empty:
        log.warning("%d perimeter(s) were empty once made valid and were not stored",
                    audit.perimeters_empty)
    if audit.points_disagreeing:
        log.warning("%d point record(s) have a geometry other than their published X/Y; "
                    "the X/Y was stored", audit.points_disagreeing)
    if audit.without_district:
        log.info("%d record(s) have no FENZ district — their point is in the sea — and "
                 "were stored as published, %d of them on the placeholder coordinate",
                 audit.without_district, audit.placeholder_points)
    if audit.zone_fallbacks:
        log.info("%d record(s) are in no time zone area and were dated in %s (%s for "
                 "the Chatham Islands)", audit.zone_fallbacks,
                 new_zealand_wod.DEFAULT_TIME_ZONE, new_zealand_wod.CHATHAM_TIME_ZONE)
    if audit.dst_gaps or audit.dst_overlaps:
        log.info("%d report time(s) fall in a daylight-saving gap and %d in an overlap",
                 audit.dst_gaps, audit.dst_overlaps)
    if audit.without_country:
        log.info("%d fire(s) have no country", audit.without_country)
    if audit.written:
        log.info("%s%d fire(s) over %s in %.0fs: %d with a perimeter, %d lightning, "
                 "%d natural, %d human, %d unknown",
                 "would have imported " if dry_run else "imported ",
                 audit.written, summarise_years(years), time.monotonic() - started,
                 audit.with_polygon - audit.perimeters_empty, audit.lightning,
                 audit.natural, audit.human, audit.unknown)


def import_release(folder: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> Audit:
    """Stage the release once, check it, then import it a year at a time."""
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    log = ArchiveLogger(logger, {"archive": folder.name})

    with exclusive_run(engine, staging_table, log):
        started = time.monotonic()
        load_release(folder, staging_table, args, log)

        with Session(engine) as session:
            years, rules = prepare_staging(session, staging_table, args, log)
            session.commit()

        if not years:
            log.warning("No record in scope: the release holds nothing for the year(s) "
                        "asked for")
            drop_staging(engine, staging_table, args, log)
            return Audit()

        log.info("%d year(s) to import: %s", len(years), summarise_years(years))
        audit = Audit()
        for index, year in enumerate(years, start=1):
            year_started = time.monotonic()
            measured = import_year(engine, args, provider_id, boundary_provider_id,
                                   staging_table, rules, year)
            audit += measured
            log.info("[%d/%d] %d: %s%d fire(s) in %.0fs", index, len(years), year,
                     "would have imported " if args.dry_run else "imported ",
                     measured.written, time.monotonic() - year_started)

        drop_staging(engine, staging_table, args, log)
        report(audit, years, started, args.dry_run, log)
        return audit


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the New Zealand Wildfire Occurrence Database into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a zone from their point. Re-importing replaces the "
               "years it reads. Database settings not given here are read from the "
               "environment (.env).",
    )
    parser.add_argument("-s", "--source-dir", type=Path, required=True,
                        help="the release's WOD_shp_* folder, holding WOD_points.shp "
                             "and WOD_polygons.shp")

    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year; may be repeated")
    cut = parser.add_mutually_exclusive_group()
    cut.add_argument("--from-year", type=int, default=new_zealand_wod.FIRST_YEAR,
                     metavar="YEAR",
                     help=f"ignore records before this year (default "
                          f"{new_zealand_wod.FIRST_YEAR}, when the FENZ records start)")
    cut.add_argument("--all-years", action="store_true",
                     help=f"import the whole release, from "
                          f"{new_zealand_wod.PUBLISHED_FIRST_YEAR}")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would "
                             "have been imported")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    args = parser.parse_args(argv)
    if args.all_years:
        args.from_year = new_zealand_wod.PUBLISHED_FIRST_YEAR
    return args


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> Audit:
    """Import the release against ``engine``, returning the audit."""
    common.require_tables(engine, ["wildfire", "ignition", "wod_wildfire", "wod_ignition",
                                   "wod_terrain", "wod_weather", "admin_boundary",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, new_zealand_wod.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, new_zealand_wod.PROVIDER_NAME, new_zealand_wod.PROVIDER_PRODUCT,
            new_zealand_wod.PROVIDER_FULL_NAME, new_zealand_wod.PROVIDER_URL, logger,
        )
        # The paper and the licence, which the shared helper has no argument for.
        provider.description = new_zealand_wod.PROVIDER_DESCRIPTION
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    return import_release(args.source_dir, engine, args, provider_id,
                          boundary_provider_id, logger)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("wod-import")

    try:
        layer_paths(args.source_dir)
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
