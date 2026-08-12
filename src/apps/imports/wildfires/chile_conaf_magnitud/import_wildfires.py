#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import CONAF's Chilean *incendio de magnitud* perimeters.

Reads the published *incendios forestales de magnitud* shapefiles — 13 archives,
781 features, the twelve seasons 2013-2014 to 2024-2025 plus one Easter Island fire
— dissolves them into 743 fires and writes
:class:`~src.data_model.wildfire.Wildfire` and
:class:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire`.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires \\
         -d /data/incendis-forestals/america/xile/perimetres
   $ python3 -m src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires \\
         -s if_magnitud_2022_2023.rar -y 2022 --dry-run

Run
:mod:`src.apps.imports.wildfires.chile_conaf.import_wildfires` **first**, then this,
then :mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires`.
Nothing enforces that order — the perimeters import perfectly well on their own —
but a perimeter with no report to bind to is a layer with half its attributes
missing, and the cause catalogue is much richer when the reports have built it.

A fire is several features
---------------------------

There is no ``GID`` in this archive. A fire mapped in pieces is published as several
features sharing a season and a name — ``668 - CANIHUAL VII`` of 2018-2019 is
thirteen of them — so the import dissolves on
:data:`~src.providers.chile_conaf_magnitud.DISSOLVE_KEY` and records
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.part_count`.
781 features become 743 fires.

Every group of more than one is reported, so that a future archive naming two real
fires the same in one season is visible rather than silently merged.

The area comes from the union, not from the column
----------------------------------------------------

``SUPERFICIE`` is each feature's own polygon area, so summing it over overlapping
parts double-counts: ``37_TIL TIL`` of 2016-2017 is six features each declaring the
same 327.50 ha of one 328 ha fire. ``area_ha_mapped`` is therefore measured on the
dissolved geometry and ``area_ha_published`` keeps the sum beside it.

77 of the 781 published polygons are invalid, so everything is repaired with
``ST_MakeValid`` before it is measured or stored — which is also why one 2014-2015
fire ends up with a mapped area six times its declared one.

Dates, causes and the number in the name
------------------------------------------

The same three Python-side resolutions the report import makes, for the same
reasons: :func:`~src.providers.chile_conaf.parse_published_datetime` for the four
date formats,
:func:`~src.providers.chile_conaf.fire_cause.resolve_published_cause` for the single
``CAUSA`` column, and
:func:`~src.providers.chile_conaf_magnitud.published_number` for the ``'402 - SAN
GUILLERMO'`` prefix six of the thirteen archives write.

Splitting that prefix off is what makes the binder work: ``'402 - SAN GUILLERMO'``
here and ``'SAN GUILLERMO'`` in the report archive are one fire, and the number is
the strongest signal there is for finding it.
"""

from __future__ import annotations

import argparse
import logging
import sys
import typing
import zlib

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.apps.imports import common
from src.apps.imports.wildfires.chile_conaf import archives
from src.apps.imports.wildfires.chile_conaf import import_wildfires as reports
from src.providers import chile_conaf
from src.providers import chile_conaf_magnitud
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.fire_cause import resolve_published_cause

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"

#: Where the published rows are staged before being mapped onto the model.
DEFAULT_STAGING_TABLE = "conaf_perimeters"

#: First half of the advisory lock key :func:`exclusive_run` takes. ``"CNFM"`` —
#: a different namespace from the report import's ``"CONF"``, so the two can run at
#: the same time even against the default staging table names.
STAGING_LOCK_NAMESPACE = 0x434E464D

#: Name of the serial key ``ogr2ogr`` puts on the staging table. Not ``fid``,
#: because ten of the thirteen layers publish an ``id`` attribute of their own.
STAGING_FID_COLUMN = "staging_fid"

#: ``PRECISION=NO``, for the reason the report import gives.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]

#: Every published spelling of each attribute this import reads.
#:
#: Less drift than the report archive has, but the same kinds: ``FECHA_INI`` becomes
#: ``FH_INICIO`` in 2023-2024, ``FECHA_TER`` becomes ``FH_EXTINC``, and
#: ``SUPERFICIE`` is also published as ``SUP`` on the layer that publishes both.
#:
#: ``sup`` is second in the ``superficie`` list and that matters:
#: ``if_magnitud_2023_2024`` publishes **both** ``SUPERFICIE`` and ``sup``, and it is
#: ``SUPERFICIE`` that carries the polygon's own area.
COLUMN_ALIASES = {
    "temporada": ("temporada",),
    "nom_incen": ("nom_incen", "nombre"),
    "numero_reg": ("numero_reg", "numero_re"),
    "causa": ("causa",),
    "superficie": ("superficie", "sup"),
    "region": ("region",),
    "provincia": ("provincia",),
    "comuna": ("comuna",),
    "codreg": ("codreg",),
    "codprov": ("codprov",),
    "codcom": ("codcom",),
    "fecha_ini": ("fecha_ini", "fh_inicio"),
    "fecha_ter": ("fecha_ter", "fh_extinc", "fh_extinci"),
}

#: The attributes every one of the thirteen published layers carries.
#:
#: ``numero_reg`` is not among them — only 2022-2023 and 2023-2024 publish it, and
#: the other eleven archives carry the number in ``NOM_INCEN`` or not at all.
REQUIRED_COLUMNS = ("temporada", "nom_incen", "causa", "superficie", "codreg")

#: The type each canonical column is read as.
STAGING_COLUMNS = {
    "temporada": "text",
    "nom_incen": "text",
    "numero_reg": "text",
    "causa": "text",
    "superficie": "double precision",
    "region": "text",
    "provincia": "text",
    "comuna": "text",
    "codreg": "text",
    "codprov": "text",
    "codcom": "text",
    "fecha_ini": "text",
    "fecha_ter": "text",
}

#: Columns the import adds to the staging table and fills itself.
#:
#: ``name_key`` is the dissolve key's second half: the
#: :func:`~src.providers.chile_conaf.normalise` d name with any number prefix already
#: removed. It is resolved in Python rather than folded in SQL so that the binder and
#: the import agree on what "the same name" means without an ``unaccent`` extension
#: and a second copy of the rule.
RESOLVED_COLUMNS = {
    "season_start_year": "integer",
    "number": "integer",
    "name_clean": "text",
    "name_key": "text",
    "start_at": "timestamp without time zone",
    "end_at": "timestamp without time zone",
    "start_precision": "text",
    "cause_id": "integer",
}

#: The characters trimmed off every published text attribute before it is read.
TRIMMED_CHARS = reports.TRIMMED_CHARS

#: The distinct ``(NOM_INCEN, NUMERO_REG)`` pairs of the staged archive, for
#: :func:`resolve_names`.
NAME_PAIRS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce(nom_incen, ''), {trimmed}), '') AS name,
                NULLIF(btrim(coalesce(numero_reg, ''), {trimmed}), '') AS number
FROM {staging_table}
"""

#: The distinct published ``CAUSA`` values of the staged archive.
CAUSE_STRINGS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce(causa, ''), {trimmed}), '') AS cause
FROM {staging_table}
"""

#: The distinct seasons the staged archive publishes.
SEASON_STRINGS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce(temporada, ''), {trimmed}), '') AS season_text
FROM {staging_table}
"""

#: The seasons the staged archive holds features in, after ``--season``.
STAGED_SEASONS_SQL = """
SELECT DISTINCT season_start_year
FROM {staging_table}
WHERE season_start_year IS NOT NULL
  AND geom IS NOT NULL
  AND ({season_filter})
ORDER BY season_start_year
"""

#: The dissolve groups holding more than one published feature, for the log.
#:
#: Reported at every run rather than checked once, because the grouping is the
#: import's decision and not a published key: a future archive naming two real fires
#: the same in one season would be merged by it, and the only thing standing between
#: that and going unnoticed is this line.
MULTIPART_SQL = """
SELECT season_start_year, name_key, number, count(*) AS parts
FROM {staging_table}
WHERE season_start_year = ANY(:seasons) AND geom IS NOT NULL
GROUP BY season_start_year, name_key, number
HAVING count(*) > 1
ORDER BY parts DESC, name_key
"""

#: Removes the perimeters of one season *of one territory*.
#:
#: Grid-scoped for the reason the report import's delete is: the mainland and Easter
#: Island are published as separate archives for the same season, and 2024-2025 has
#: one of each.
#:
#: Simpler than the report import's, because a perimeter owns no ignition: two
#: tables, not four.
DELETE_SEASONS_SQL = """
WITH doomed AS (
    SELECT id FROM conaf_magnitud_wildfire
    WHERE season_start_year = ANY(:seasons)
      AND {grid_filter}
),
removed_child AS (
    DELETE FROM conaf_magnitud_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Which grid column a perimeter has to be on to belong to the territory being
#: imported. See :data:`src.apps.imports.wildfires.chile_conaf.import_wildfires.
#: GRID_FILTER_SQL`.
GRID_FILTER_SQL = ("perimeter_utm19s IS NOT NULL", "perimeter_utm12s IS NOT NULL")

#: Maps **one season** of the staged archive onto the two tables of the model.
#:
#: The CTEs, in order:
#:
#: ``cleaned``
#:     Every text attribute trimmed, the codes padded, the season filter applied, and
#:     the geometry flattened to 2D and repaired. 273 features are already
#:     ``MULTIPOLYGON`` and two archives publish 3D polygons, so both
#:     ``ST_Force2D`` and ``ST_CollectionExtract(ST_MakeValid(...), 3)`` are load
#:     bearing: 77 of the 781 polygons are invalid and would otherwise fail
#:     ``ST_Union`` or measure wrong.
#: ``dissolved``
#:     One row per fire. ``ST_Union`` over the parts, ``count(*)`` for
#:     ``part_count``, ``sum()`` for the published area, and ``min()`` over the dates
#:     and the attributes — which is arbitrary between parts and does not matter,
#:     because every multi-part group in the archive agrees on all of them.
#: ``dated``
#:     ``start_date_time`` resolved: the parsed instant where there is one, the first
#:     instant of the season where there is not.
#: ``numbered``
#:     One key per fire from the ``wildfire`` sequence. ``MATERIALIZED``, for the
#:     ``nextval`` reason.
#: ``zoned``
#:     Zone and country from a point on the perimeter. ``ST_PointOnSurface`` and not
#:     ``ST_Centroid``: a centroid can fall outside a concave burn, and a fire on the
#:     Aysén coast whose centroid lands in the Pacific would get no zone at all.
#: ``ins_wildfire`` / ``written``
#:     The fire, with its perimeter in EPSG:4326 on the generic row and on its
#:     published grid on the provider one.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT staging.season_start_year AS season_start_year,
           NULLIF(btrim(staging.temporada, {trimmed}), '') AS season,
           staging.number AS number,
           staging.name_clean AS name,
           COALESCE(staging.name_key, 'staging:' || staging.{fid_column}::text) AS name_key,
           NULLIF(btrim(staging.region, {trimmed}), '') AS region,
           NULLIF(btrim(staging.provincia, {trimmed}), '') AS province,
           NULLIF(btrim(staging.comuna, {trimmed}), '') AS commune,
           {region_code} AS region_code,
           {province_code} AS province_code,
           {commune_code} AS commune_code,
           NULLIF(btrim(staging.causa, {trimmed}), '') AS cause_published,
           staging.cause_id AS cause_id,
           staging.superficie AS area_ha_published,
           staging.start_at AS start_at,
           staging.end_at AS end_at,
           staging.start_precision AS start_precision,
           ST_CollectionExtract(ST_MakeValid(ST_Force2D(staging.geom)), 3) AS geom
    FROM {staging_table} AS staging
    WHERE staging.season_start_year IS NOT NULL
      AND staging.geom IS NOT NULL
      AND ({season_filter})
),
dissolved AS MATERIALIZED (
    SELECT cleaned.season_start_year AS season_start_year,
           cleaned.name_key AS name_key,
           count(*) AS part_count,
           cleaned.number AS number,
           min(cleaned.season) AS season,
           min(cleaned.name) AS name,
           min(cleaned.region) AS region,
           min(cleaned.province) AS province,
           min(cleaned.commune) AS commune,
           min(cleaned.region_code) AS region_code,
           min(cleaned.province_code) AS province_code,
           min(cleaned.commune_code) AS commune_code,
           min(cleaned.cause_published) AS cause_published,
           min(cleaned.cause_id) AS cause_id,
           sum(cleaned.area_ha_published) AS area_ha_published,
           min(cleaned.start_at) AS start_at,
           max(cleaned.end_at) AS end_at,
           min(cleaned.start_precision) AS start_precision,
           ST_Multi(ST_Union(cleaned.geom)) AS geom
    FROM cleaned
    GROUP BY cleaned.season_start_year, cleaned.name_key, cleaned.number
),
dated AS MATERIALIZED (
    SELECT dissolved.*,
           COALESCE(dissolved.start_at,
                    make_timestamp(dissolved.season_start_year, :season_start_month,
                                   1, 0, 0, 0)) AS resolved_start,
           COALESCE(dissolved.start_precision, :precision_season) AS date_time_precision,
           ST_Area(dissolved.geom) / 10000.0 AS area_ha_mapped
    FROM dissolved
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           dated.*
    FROM dated
),
zoned AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(numbered.geom, 4326) AS perimeter_4326,
           ST_PointOnSurface(ST_Transform(numbered.geom, 4326)) AS point_4326,
           zone.name AS time_zone,
           country.id AS admin_boundary_id
    FROM numbered
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry,
                          ST_PointOnSurface(ST_Transform(numbered.geom, 4326)))
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry,
                          ST_PointOnSurface(ST_Transform(numbered.geom, 4326)))
        LIMIT 1
    ) AS country ON TRUE
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT zoned.wildfire_id,
           'conaf_magnitud_wildfire',
           :provider_id,
           zoned.resolved_start AT TIME ZONE COALESCE(zoned.time_zone,
                                                      :fallback_time_zone),
           CASE WHEN zoned.end_at IS NULL THEN NULL
                ELSE zoned.end_at AT TIME ZONE COALESCE(zoned.time_zone,
                                                        :fallback_time_zone)
           END,
           zoned.time_zone,
           zoned.perimeter_4326,
           zoned.admin_boundary_id
    FROM zoned
    RETURNING id
),
written AS (
    INSERT INTO conaf_magnitud_wildfire (id, season, season_start_year, number, name,
                                         region, province, commune, region_code,
                                         province_code, commune_code, cause_published,
                                         cause_id, area_ha_mapped, area_ha_published,
                                         part_count, date_time_precision,
                                         perimeter_utm19s, perimeter_utm12s)
    SELECT zoned.wildfire_id, COALESCE(zoned.season, :season_label),
           zoned.season_start_year, zoned.number, zoned.name, zoned.region,
           zoned.province, zoned.commune, zoned.region_code, zoned.province_code,
           zoned.commune_code, zoned.cause_published, zoned.cause_id,
           zoned.area_ha_mapped, zoned.area_ha_published, zoned.part_count,
           zoned.date_time_precision,
           CASE WHEN :source_srid = {mainland_srid} THEN zoned.geom ELSE NULL END,
           CASE WHEN :source_srid = {easter_srid} THEN zoned.geom ELSE NULL END
    FROM zoned
    JOIN ins_wildfire ON ins_wildfire.id = zoned.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS features,
       (SELECT count(*) FROM cleaned WHERE ST_IsEmpty(geom)) AS empty_geometry,
       (SELECT count(*) FROM dissolved) AS fires,
       (SELECT count(*) FROM dissolved WHERE part_count > 1) AS multipart,
       (SELECT count(*) FROM dated WHERE date_time_precision = :precision_season)
           AS season_only,
       (SELECT count(*) FROM dated WHERE end_at IS NOT NULL) AS with_end,
       (SELECT count(*) FROM dated WHERE number IS NOT NULL) AS with_number,
       (SELECT count(*) FROM dated WHERE cause_id IS NULL) AS no_cause,
       (SELECT count(*) FROM dated
        WHERE area_ha_published > 0
          AND abs(area_ha_mapped - area_ha_published) > 0.05 * area_ha_published)
           AS area_disagrees,
       (SELECT count(*) FROM written) AS written
"""


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.LoggerAdapter) -> None:
    """Rename the staged columns to one canonical set, and type them usably.

    The perimeter half of
    :func:`src.apps.imports.wildfires.chile_conaf.import_wildfires.
    normalise_staging_columns`, and the same rules: an attribute this layer does not
    publish is added as an empty column, and only :data:`REQUIRED_COLUMNS` stops the
    import.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = {
        name: data_type
        for name, data_type in session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table"
        ), {"schema": schema or "public", "table": table}).all()
    }

    absent = []
    for canonical, spellings in COLUMN_ALIASES.items():
        present = next((name for name in spellings if name in loaded), None)
        if present is None:
            absent.append(canonical)
            continue
        if present != canonical:
            logger.debug("Renaming staged %s to %s", present, canonical)
            session.execute(text(
                f"ALTER TABLE {staging_table} RENAME COLUMN {present} TO {canonical}"))
            loaded[canonical] = loaded.pop(present)

    unusable = sorted(set(absent) & set(REQUIRED_COLUMNS))
    if unusable:
        raise RuntimeError(
            f"the staged layer publishes no {', '.join(unusable)}: this is not a CONAF "
            f"incendios de magnitud layer, or its attributes have been renamed again"
        )
    if absent:
        logger.info("This layer publishes no %s; those columns are stored empty",
                    ", ".join(sorted(absent)))
        for name in absent:
            session.execute(text(
                f"ALTER TABLE {staging_table} ADD COLUMN {name} {STAGING_COLUMNS[name]}"))
            loaded[name] = STAGING_COLUMNS[name]

    for name, wanted in STAGING_COLUMNS.items():
        if loaded[name] in reports.COMPATIBLE_TYPES.get(wanted, {wanted}):
            continue
        logger.debug("Converting staged %s from %s to %s", name, loaded[name], wanted)
        session.execute(text(
            f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {wanted} "
            f"USING NULLIF(btrim({name}::text), '')::{wanted}"))

    for name, data_type in RESOLVED_COLUMNS.items():
        session.execute(text(
            f"ALTER TABLE {staging_table} ADD COLUMN IF NOT EXISTS {name} {data_type}"))


def resolve_names(session: Session, staging_table: str,
                  logger: logging.LoggerAdapter) -> int:
    """Split the number off each published name, returning how many carry one.

    Notes
    -----
    :func:`~src.providers.chile_conaf_magnitud.published_number` is the splitter, and
    what it produces is three things the rest of the import needs: ``number``, the
    office's running number for the fire; ``name_clean``, the name **without** the
    prefix, which is what the report archive calls the same fire; and ``name_key``,
    that name :func:`~src.providers.chile_conaf.normalise` d, which is the second half
    of the dissolve key and what the binder compares.

    Resolved in Python rather than folded in SQL because ``normalise`` strips accents
    and soft hyphens, and doing that in PostgreSQL means either the ``unaccent``
    extension or a second copy of the rule that can drift from the first.
    """
    rows = session.execute(text(NAME_PAIRS_SQL.format(
        staging_table=staging_table, trimmed=TRIMMED_CHARS))).all()

    published, numbers, names, keys = [], [], [], []
    for row in rows:
        number, name = chile_conaf_magnitud.published_number(row.name, row.number)
        published.append((row.name, row.number))
        numbers.append(number)
        names.append(name)
        keys.append(chile_conaf.normalise(name) or None)

    if published:
        session.execute(text(
            f"UPDATE {staging_table} AS staging "
            f"SET number = mapping.number, name_clean = mapping.name, "
            f"    name_key = mapping.key "
            f"FROM (SELECT * FROM unnest(:names ::text[], :raw_numbers ::text[], "
            f"                           :numbers ::integer[], :clean ::text[], "
            f"                           :keys ::text[])) "
            f"AS mapping(published_name, published_number, number, name, key) "
            f"WHERE NULLIF(btrim(coalesce(staging.nom_incen, ''), {TRIMMED_CHARS}), '') "
            f"      IS NOT DISTINCT FROM mapping.published_name "
            f"  AND NULLIF(btrim(coalesce(staging.numero_reg, ''), {TRIMMED_CHARS}), '') "
            f"      IS NOT DISTINCT FROM mapping.published_number"),
            {"names": [pair[0] for pair in published],
             "raw_numbers": [pair[1] for pair in published],
             "numbers": numbers, "clean": names, "keys": keys},
        )

    with_number = sum(1 for number in numbers if number is not None)
    logger.debug("Read a report number off %d of %d distinct published name(s)",
                 with_number, len(published))
    return with_number


def upsert_causes(session: Session, staging_table: str,
                  logger: logging.LoggerAdapter) -> int:
    """Store this archive's cause classifications and link the staged rows.

    Notes
    -----
    :func:`~src.providers.chile_conaf.fire_cause.resolve_published_cause` decides
    which half of the classification each published ``CAUSA`` is — a three-part code
    is a *causa específica*, anything else a *causa general* — and the row it
    produces has the other half ``NULL``.

    ``ON CONFLICT DO NOTHING`` on the matching partial index, which is
    ``uq_conaf_fire_cause_specific_only`` or ``uq_conaf_fire_cause_cause_only``
    depending on which half was filled. A perimeter's classification is a genuine
    catalogue entry and is deliberately **not** merged with a report's
    ``(cause, specific_cause)`` pair that happens to contain the same string: the
    pair says which general cause that specific one was filed under, and this
    archive does not say.
    """
    rows = session.execute(text(CAUSE_STRINGS_SQL.format(
        staging_table=staging_table, trimmed=TRIMMED_CHARS))).all()
    resolved = {row.cause: resolve_published_cause(row.cause) for row in rows}
    values = [entry for entry in resolved.values() if entry is not None]
    if not values:
        return 0

    unreconciled = sorted({entry["cause"] for entry in values
                           if entry["cause"] is not None
                           and entry["cause_normalised"] is None})
    if unreconciled:
        logger.info("%d published cause(s) have no canonical form and are stored "
                    "unreconciled: %s", len(unreconciled),
                    ", ".join(repr(term[:50]) for term in unreconciled))

    general = [entry for entry in values if entry["cause"] is not None]
    specific = [entry for entry in values if entry["cause"] is None]
    for batch, elements, where in (
            (general, ["cause"], "cause IS NOT NULL AND specific_cause IS NULL"),
            (specific, ["specific_cause"],
             "cause IS NULL AND specific_cause IS NOT NULL"),
    ):
        if batch:
            session.execute(
                pg_insert(ConafFireCause.__table__).values(batch)
                .on_conflict_do_nothing(index_elements=elements,
                                        index_where=text(where))
            )

    session.execute(text(
        f"UPDATE {staging_table} AS staging SET cause_id = fire_cause.id "
        f"FROM conaf_fire_cause AS fire_cause "
        f"WHERE ((fire_cause.specific_cause IS NULL "
        f"        AND fire_cause.cause = NULLIF(btrim(coalesce(staging.causa, ''), "
        f"                                            {TRIMMED_CHARS}), '')) "
        f"    OR (fire_cause.cause IS NULL "
        f"        AND fire_cause.specific_cause = NULLIF(btrim(coalesce(staging.causa, "
        f"                                               ''), {TRIMMED_CHARS}), '')))"
    ))
    logger.debug("Catalogued %d cause classification(s) for this archive", len(values))
    return len(values)


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------

def season_filter(seasons: list[int] | None) -> str:
    """The ``WHERE`` fragment restricting to ``--season``."""
    return "staging.season_start_year = ANY(:seasons)" if seasons else "TRUE"


def staged_seasons(session: Session, staging_table: str,
                   seasons: list[int] | None) -> list[int]:
    """The seasons the staged archive holds features in, in order."""
    statement = STAGED_SEASONS_SQL.format(
        staging_table=staging_table,
        season_filter=season_filter(seasons).replace("staging.", ""),
    )
    return list(session.scalars(text(statement),
                                {"seasons": seasons} if seasons else {}).all())


def grid_filter(source_srid: int) -> str:
    """The ``WHERE`` fragment picking out the territory ``source_srid`` is the grid of."""
    mainland, easter = GRID_FILTER_SQL
    return mainland if source_srid == chile_conaf.SOURCE_SRID_MAINLAND else easter


def delete_seasons(session: Session, seasons: list[int], source_srid: int) -> None:
    """Remove one territory's perimeters for these seasons.

    No ``check_not_linked`` counterpart, and none is needed: nothing in the schema
    points *at* a perimeter. The link runs the other way, from here to the report,
    so deleting a perimeter costs at most a binding that the binder will make again.
    """
    session.execute(
        text(DELETE_SEASONS_SQL.format(grid_filter=grid_filter(source_srid))),
        {"seasons": seasons},
    )


def report_multipart(session: Session, staging_table: str, seasons: list[int],
                     logger: logging.LoggerAdapter) -> None:
    """Log every dissolve group holding more than one published feature."""
    groups = session.execute(text(MULTIPART_SQL.format(staging_table=staging_table)),
                             {"seasons": seasons}).all()
    for group in groups:
        logger.info("%d-%d: %d features dissolved into one fire, %r number %s",
                    group.season_start_year, group.season_start_year + 1,
                    group.parts, group.name_key, group.number)


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Audit:
    """What the transform did, for the summary lines.

    Attributes
    ----------
    features : int
        Published features the season filter let through.
    empty_geometry : int
        Features whose polygon was empty after repair. None in the archive as
        published, which is what makes one worth noticing.
    fires : int
        Rows after the dissolve.
    multipart : int
        Fires published as more than one feature.
    season_only : int
        Fires with no published start, dated to 1 July of their season.
    with_end : int
        Fires with a published end.
    with_number : int
        Fires carrying the office's running number, from the column or the name
        prefix. This is what the binder's strongest rule needs.
    no_cause : int
        Fires whose published ``CAUSA`` was empty or the null token.
    area_disagrees : int
        Fires whose dissolved area differs from their published ``SUPERFICIE`` sum by
        more than 5%. Every one is either overlapping parts or a polygon whose
        declared area was wrong; see the module docstring.
    written : int
        Fires actually stored.
    """

    features: int = 0
    empty_geometry: int = 0
    fires: int = 0
    multipart: int = 0
    season_only: int = 0
    with_end: int = 0
    with_number: int = 0
    no_cause: int = 0
    area_disagrees: int = 0
    written: int = 0

    @classmethod
    def from_row(cls, row) -> Audit:
        """The audit the transform's one row reports."""
        return cls(**{field.name: getattr(row, field.name) for field in fields(cls)})

    def __add__(self, other: Audit) -> Audit:
        """The two seasons' counts, summed field by field."""
        return Audit(**{field.name: getattr(self, field.name) + getattr(other, field.name)
                        for field in fields(self)})


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, source_srid: int, season: int) -> Audit:
    """Map the staged features of one season onto the model."""
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        fid_column=STAGING_FID_COLUMN,
        trimmed=TRIMMED_CHARS,
        season_filter=season_filter([season]),
        region_code=reports.ADMIN_CODE_SQL.format(column="codreg", width=2,
                                                  trimmed=TRIMMED_CHARS),
        province_code=reports.ADMIN_CODE_SQL.format(column="codprov", width=3,
                                                    trimmed=TRIMMED_CHARS),
        commune_code=reports.ADMIN_CODE_SQL.format(column="codcom", width=5,
                                                   trimmed=TRIMMED_CHARS),
        mainland_srid=chile_conaf.SOURCE_SRID_MAINLAND,
        easter_srid=chile_conaf.SOURCE_SRID_EASTER,
    )
    parameters = {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "fallback_time_zone": chile_conaf.DEFAULT_TIME_ZONE,
        "seasons": [season],
        "season_label": f"{season}-{season + 1}",
        "season_start_month": chile_conaf.SEASON_START_MONTH,
        "source_srid": source_srid,
        "precision_season": chile_conaf.PRECISION_SEASON,
    }
    return Audit.from_row(session.execute(text(statement), parameters).one())


# --------------------------------------------------------------------------
# Importing an archive
# --------------------------------------------------------------------------

@contextmanager
def exclusive_run(engine: Engine, staging_table: str,
                  logger: logging.LoggerAdapter) -> typing.Iterator[None]:
    """Hold the staging table against a second run, for one archive.

    The same guard, and the same reasoning, as
    :func:`src.apps.imports.wildfires.chile_conaf.import_wildfires.exclusive_run`.
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
                f"it to finish, or pass --staging-table to give this run one of its own"
            )
        logger.debug("Holding the staging lock on %s", staging_table)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": STAGING_LOCK_NAMESPACE, "key": key},
            )


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> Audit:
    """Stage one published archive and write the seasons it holds."""
    log = common.ArchiveLogger(logger, {"archive": archive.name})
    settings = common.resolve_database_settings(args)
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    total = Audit()

    with archives.archive_datasource(archive, log) as (datasource, layer, shapefile):
        source_srid = archives.archive_grid(shapefile, log)
        with exclusive_run(engine, staging_table, log):
            common.load_staging_table(
                datasource, layer, staging_table, args, settings, log,
                geometry_type="MULTIPOLYGON",
                target_srs=f"EPSG:{source_srid}",
                fid_column=STAGING_FID_COLUMN,
                creation_options=STAGING_CREATION_OPTIONS,
            )

            with Session(engine) as session:
                normalise_staging_columns(session, staging_table, log)
                session.execute(text(f"ANALYZE {staging_table}"))
                reports.resolve_seasons(session, staging_table,
                                        reports.archive_season(archive), log)
                reports.resolve_dates(session, staging_table, log,
                                      start_column="fecha_ini", end_column="fecha_ter")
                resolve_names(session, staging_table, log)
                upsert_causes(session, staging_table, log)
                archives.check_extent(session, staging_table, source_srid, log)
                seasons = staged_seasons(session, staging_table, args.season)
                if seasons:
                    report_multipart(session, staging_table, seasons, log)
                session.commit()

            if not seasons:
                log.warning("No season in this archive matches the filter; nothing to do")
            else:
                log.info("Staged %s", reports.summarise_seasons(seasons))

            for season in seasons:
                with Session(engine) as session:
                    delete_seasons(session, [season], source_srid)
                    audit = transform(session, provider_id, boundary_provider_id,
                                      staging_table, source_srid, season)
                    if audit.features == 0 and audit.written == 0:
                        raise RuntimeError(
                            f"season {season}-{season + 1} was staged but "
                            f"{staging_table} held no features for it by the time it "
                            f"was read; nothing has been committed for this season")
                    if args.dry_run:
                        session.rollback()
                        log.info("%d-%d: would write %d fire(s) from %d feature(s) "
                                 "(dry run)", season, season + 1, audit.written,
                                 audit.features)
                    else:
                        session.commit()
                        log.info("%d-%d: wrote %d fire(s) from %d feature(s)",
                                 season, season + 1, audit.written, audit.features)
                    total = total + audit

            with Session(engine) as session:
                if not args.keep_staging:
                    common.drop_staging_table(session, staging_table, log)
                session.commit()

    return total


def report(total: Audit, logger: logging.Logger) -> None:
    """Log what the run did."""
    logger.info("Read %d published feature(s), dissolved to %d fire(s), wrote %d",
                total.features, total.fires, total.written)
    if total.multipart:
        logger.info("%d fire(s) were published as more than one feature",
                    total.multipart)
    if total.empty_geometry:
        logger.warning("%d feature(s) had an empty polygon after repair and are not "
                       "stored", total.empty_geometry)
    logger.info("%d fire(s) carry the office's report number; %d have a published end "
                "date", total.with_number, total.with_end)
    if total.season_only:
        logger.warning("%d fire(s) have no published start and are dated to 1 July of "
                       "their season", total.season_only)
    if total.area_disagrees:
        logger.info("%d fire(s) have a mapped area more than 5%% from their published "
                    "SUPERFICIE: overlapping parts, or a polygon whose declared area "
                    "was wrong. Both areas are stored", total.area_disagrees)
    if total.no_cause:
        logger.info("%d fire(s) publish no usable CAUSA", total.no_cause)


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import CONAF Chilean incendio de magnitud perimeters into GisFIRE.",
        epilog="Import the seasonal reports first, then these, then bind them with "
               "src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires. "
               "Re-importing replaces the seasons it reads. Database settings not given "
               "here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path, metavar="DIR",
                        help="import every archive in this directory, in name order")
    source.add_argument("-s", "--shapefile", type=Path, nargs="+", metavar="PATH",
                        help="import these archives: a .rar, a .zip, a directory or a .shp")

    parser.add_argument("-y", "--season", type=int, action="append", metavar="YEAR",
                        help="import only this season, named by its first year (2022 for "
                             "2022-2023); may be repeated")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would "
                             "have been imported")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> Audit:
    """Import the archives against ``engine``, returning the totals."""
    common.require_tables(engine, ["wildfire", "conaf_magnitud_wildfire",
                                   "conaf_wildfire", "conaf_fire_cause",
                                   "admin_boundary", "time_zone", "data_provider"],
                          logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, chile_conaf.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, chile_conaf_magnitud.PROVIDER_NAME,
            chile_conaf_magnitud.PROVIDER_PRODUCT,
            chile_conaf_magnitud.PROVIDER_FULL_NAME, chile_conaf_magnitud.PROVIDER_URL,
            logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        reported = session.scalar(text("SELECT count(*) FROM conaf_wildfire"))
        if not reported:
            logger.warning(
                "No CONAF seasonal reports imported: these perimeters will have nothing "
                "to bind to. Import them first with "
                "src.apps.imports.wildfires.chile_conaf.import_wildfires")
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    archive_paths = (reports.find_archives(args.directory) if args.directory
                     else list(args.shapefile))
    if not archive_paths:
        raise RuntimeError(f"no archive found in {args.directory}")
    logger.info("Importing %d archive(s)", len(archive_paths))

    total = Audit()
    for archive in archive_paths:
        total = total + import_archive(archive, engine, args, provider_id,
                                       boundary_provider_id, logger)
    report(total, logger)
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("conaf-magnitud-import")

    for path in ([args.directory] if args.directory else args.shapefile):
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
