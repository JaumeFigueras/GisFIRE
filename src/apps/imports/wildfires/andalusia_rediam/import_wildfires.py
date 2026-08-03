#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import REDIAM burnt area perimeters for Andalusia.

Loads the published *perímetros de incendios forestales* into
:class:`~src.providers.andalusia_rediam.wildfire.RediamWildfire` rows — the generic
columns in ``wildfire``, the Andalusian ones in ``rediam_wildfire`` — and the
published ignition points into
:class:`~src.providers.andalusia_rediam.ignition.RediamIgnition`.

Point it at the directory the download was unpacked into::

    python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \\
        -d /path/to/andalusia/InfGeografica/InfVectorial/Shapes/

or at one file::

    python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \\
        -s PERIMETROS_COR_2008_2025.shp

and ``--year`` narrows either to the years asked for::

    python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \\
        -d /path/to/Shapes/ --year 2024 --year 2025

``--dry-run`` does the whole of the work and rolls it back, which is the way to see
what a directory would produce without writing anything.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency, not a
Python package.

Two kinds of file, and both are read
-------------------------------------

The published set is one shapefile per year **and** one holding the whole series, and
this import reads both — for different things.

``PERIMETROS_COR_2008_2025``
    The combined layer, and the source of every **perimeter**. It is the file the
    service republishes as the archive grows, its attribute names are spelled one
    way, and reading one layer cannot half-import a series.

``PERIMETROS_COR_2021`` … ``PERIMETROS_COR_2024``
    Read for one thing the combined layer does not carry: ``X_INIC`` and ``Y_INIC``,
    the **ignition point**. 201 fires of the 907 have one, in those four years and
    nowhere else — not in 2025, and not in the combined file.

The other yearly layers are skipped, and the log says so: their fires are already in
the combined layer, and importing both would import the year twice.

.. note::

   ``--skip-ignitions`` leaves the yearly files alone, which makes the import one
   layer and one transaction. Useful when only the perimeters have changed.

What a re-import replaces: the years, not the file
---------------------------------------------------

The name of the combined layer carries the range it covers, so next year's
publication is ``PERIMETROS_COR_2008_2026`` rather than a new edition of this file
name. An import that replaced *the layer it is re-importing* would therefore add a
second copy of every fire the first time the range grew, and nothing downstream would
notice: the codes and the polygons would be the same.

So this import replaces **the years it finds inside the layer it is reading**. The
staged data is asked which years it holds, every stored fire of those years is
deleted, and the layer is loaded in one transaction.
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.source_layer` records
which file a fire came from and is not what anything keys on.

One consequence worth stating: importing ``PERIMETROS_COR_2022`` on its own after the
combined layer replaces 2022 with what that file says, which is the same 58 fires. It
is a supported thing to do, not an accident waiting to happen.

.. warning::

   Replacing a year discards any
   :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`
   already bound for it, because the rows themselves go. The import counts the bound
   rows before deleting them and says so at ``WARNING``; re-running the binding
   application afterwards is what puts them back.

962 features are 907 fires
---------------------------

55 codes are published **twice** — 2 in 2024, 53 in 2025 — always with the same date,
and in 54 of the 55 with the same areas and the same footprint too, differing only in
the case of the municipality and province names. Those are duplicate records, not two
parts of one fire.

The mapping groups on ``(CODIGO, FECHA_INC)`` and dissolves, keeping the count in
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.part_count`. For 54 of
them the union is the shape either row already had, so nothing is merged that was not
already the same polygon; for ``IIFF2025210122`` the two rows are genuinely different
mappings — 363.8 ha and 517.4 ha — and the union is 527.5 ha. Either way no fire is
summed twice, which is what would happen to every 2025 total if the rows were stored
as published.

Where a group's rows disagree, the mapping has to choose, and what it does depends on
the column:

* **the names** are taken with ``min``, which is deterministic and nothing more. The
  duplicated 2025 rows really do disagree here (``LUBRIN`` beside ``Lubrín``) and
  neither spelling is more published than the other.
* **the three areas** are taken with ``max``, and a group whose rows disagree is
  **counted and reported at WARNING**. Two do — ``IIFF2025210122`` and
  ``IIFF2025230060``, by 0.9 ha of scrub and 0.8 ha of grassland — and that is a fact
  about the publication rather than about duplicate bookkeeping, so it should not pass
  in silence.

  ``max`` is not a claim that the larger figure is the right one. It is deterministic,
  it is reported, and the alternative — refusing to import a fire the service has
  published twice — would be worse.

The geometry is stored twice
----------------------------

``ogr2ogr`` loads the polygons in the CRS they were published in, EPSG:25830, and the
mapping keeps them: the dissolved polygon goes into
``rediam_wildfire.perimeter_etrs89_utm30n`` and its ``ST_Transform`` to EPSG:4326 into
``wildfire.perimeter``. Deriving the second from the first, rather than loading each
separately, is what guarantees the two are the same geometry.

71 of the 962 published features have a self-intersecting ring, so every feature goes
through ``ST_MakeValid`` **before** the union — a bad ring would otherwise fail a
whole fire rather than one feature — and ``ST_Force2D`` first, which costs nothing and
means a 3D layer (the GeoPackage's 2015 one is 3D) cannot surprise the union later.

EPSG:25830, and not the 3042 in the ``.prj``
---------------------------------------------

The published ``.prj`` is an ESRI string with no EPSG code, and GDAL resolves it to
**EPSG:3042** — ETRS89 / UTM 30N declared *northing-easting*, while the coordinates in
the files are easting-northing, as GDAL itself reports
(``Data axis to CRS axis mapping: 2,1``).

The load therefore forces :data:`~src.providers.andalusia_rediam.SOURCE_SRID`, 25830:
the same projection with the conventional axis order, which is what the data follows
and what QGIS and PostGIS use for the Spanish peninsular grid. Storing 3042 would
store a declaration the geometry does not obey and invite PROJ to swap the axes on the
next transform.

The ignition point is a second pass
------------------------------------

After the perimeters, each ignition-bearing yearly layer is staged and mapped in a
transaction of its own. A point is stored when its ``(CODIGO, FECHA_INC)`` matches a
perimeter already imported; one that matches nothing is counted and reported, because
it means the two files disagree about which fires exist.

The published easting and northing are kept as published on
:class:`~src.providers.andalusia_rediam.ignition.RediamIgnition`, and the EPSG:4326
point is built from them in SQL — the same rule as the perimeter, for the same reason.

.. warning::

   **The point is not checked against the perimeter, and it does not agree with it.**
   Only 88 of the 201 published points fall inside their own fire; the rest are
   outside by a metre to three kilometres, and one 2022 point is 19.5 km away. That is
   a disagreement between two observations, not an error to repair, and the import
   stores both and reports how many are inside.

The encoding
------------

Every ``.dbf`` here carries a ``.cpg``, and the DBF language driver byte is ``0x00``
throughout — so GDAL reads the sidecar and gets it right. The import passes no
``ENCODING`` open option and checks the staged names for the two signatures of a
mangling afterwards, exactly as the Catalan import does: the rule is one small file
deep, and that is worth asserting rather than trusting.

One file is the odd one out — ``PERIMETROS_COR_2025.cpg`` says ``1252`` where every
other says ``UTF-8`` — and it is a yearly layer, so it is only read if it is asked for
by name. The check covers it either way.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers import andalusia_rediam

# The plumbing every wildfire importer shares, re-exported so this module reads as
# one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401

DEFAULT_STAGING_TABLE = "rediam_burnt_areas"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The serial key GDAL puts on the staging table.
#:
#: Not the default ``fid``: the combined layer publishes an attribute of that name — a
#: Real row number — and GDAL then reports ``ERROR 1: Wrong field type for fid`` on
#: every run and numbers the rows itself anyway. Nothing here reads either column; the
#: rename only keeps a harmless message out of the log. See
#: :func:`src.apps.imports.common.load_staging_table`.
STAGING_FID_COLUMN = "ogc_fid"

#: Layer creation options passed to ``ogr2ogr`` on top of the shared ones.
#:
#: ``PRECISION=NO`` stops GDAL's PostgreSQL driver turning a shapefile's declared
#: field width into a ``NUMERIC(width, scale)``, and this dataset needs it: the 2024
#: yearly layer declares ``X_INIC`` as ``Real (19.15)``, and ``numeric(19,15)`` has
#: four digits before the point where the published easting ``596812.000001`` has six.
#: Without this the load of that layer fails outright with a numeric field overflow.
#:
#: The declared widths are fiction throughout — ``Real (24.15)`` on an area of 26.9 ha
#: — so nothing is lost by ignoring them, and the mapping converts the columns to the
#: types it wants anyway.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]

#: Every attribute the perimeter mapping reads, with the PostgreSQL type it needs,
#: named as ``ogr2ogr`` lands it — lower-cased, which is what its ``LAUNDER`` default
#: does.
#:
#: All seven are published by the combined layer and by every yearly one. What varies
#: between the yearly layers, and is one of the reasons the perimeters are read from
#: the combined file, is the **spelling**: 2015 upper-cases ``MUNICIPIO`` and
#: ``PROVINCIA``, and 2020 and 2021 truncate ``SUP_PASTIZ`` to ``SUP_PASTI``.
STAGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("codigo", "text"),
    ("fecha_inc", "date"),
    ("municipio", "text"),
    ("provincia", "text"),
    ("sup_arbola", "double precision"),
    ("sup_matorr", "double precision"),
    ("sup_pastiz", "double precision"),
)

#: The two attributes the ignition mapping reads on top of the code and the date.
#:
#: Published by the 2021-2024 yearly layers and by nothing else. 2021 publishes them
#: as ``Integer64`` and the later years as ``Real``, which is why they are converted
#: rather than read as they land.
IGNITION_STAGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("x_inic", "double precision"),
    ("y_inic", "double precision"),
)

#: What the ignition mapping needs besides the coordinates: the natural key of the
#: fire the point belongs to.
#:
#: The ignition pass normalises these two and :data:`IGNITION_STAGING_COLUMNS` and
#: **not** the whole of :data:`STAGING_COLUMNS`, because it reads nothing else. The
#: yearly layers spell some of the rest differently — 2020 and 2021 publish
#: ``SUP_PASTI`` — and normalising columns nobody is going to read would report a
#: missing attribute that does not matter.
IGNITION_KEY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("codigo", "text"),
    ("fecha_inc", "date"),
)

#: The loaded types each declared type will accept without a conversion, by
#: ``information_schema.data_type`` name. The same table as the ICNF and DARPA
#: imports', with the two types this source adds: GDAL's PostgreSQL driver renders a
#: field that declares a width as ``NUMERIC(width, scale)``, so ``SUP_ARBOLA: Real
#: (24.15)`` arrives as ``numeric(24,15)``.
COMPATIBLE_TYPES: dict[str, frozenset[str]] = {
    "text": frozenset({"text", "character varying", "character"}),
    "date": frozenset({"date"}),
    "double precision": frozenset({"double precision", "real", "numeric",
                                   "integer", "smallint", "bigint"}),
}

#: The characters trimmed off every published text attribute before it is read.
#:
#: Spaces because a DBF character field is space-padded, and CR and LF because the
#: Catalan archive turned out to carry them inside published values and the cost of
#: assuming this one does not is five silently missing fires.
TRIMMED_CHARS = r"E' \t\r\n'"

#: The two signatures of a character set read wrongly, looked for in the staged
#: municipality and province names.
#:
#: ``Ã`` is UTF-8 bytes read as Latin-1 — ``Almería`` becomes ``AlmerÃ­a`` — and
#: U+FFFD is Latin-1 bytes read as UTF-8. Neither occurs in an Andalusian place name,
#: so either is conclusive.
MOJIBAKE_SQL = """
SELECT count(*) FROM {staging_table}
WHERE municipio LIKE '%Ã%' OR municipio LIKE '%' || chr(65533) || '%'
   OR provincia LIKE '%Ã%' OR provincia LIKE '%' || chr(65533) || '%'
"""

#: The years the staged layer holds fires in, after ``--year`` has been applied.
#:
#: Asked before the transform, because these are the years the import replaces — see
#: the module docstring on why it is the years and not the file name. Read from the
#: **data** and never from the layer name, which for the combined file is a range that
#: changes with every publication.
STAGED_YEARS_SQL = """
SELECT DISTINCT EXTRACT(YEAR FROM fecha_inc)::int AS year
FROM {staging_table}
WHERE fecha_inc IS NOT NULL AND ({year_filter})
ORDER BY year
"""

#: How many fires of the years about to be replaced carry a link to an EGIF *parte*.
#:
#: Nothing in this import ever writes that column, so a non-zero answer means a
#: binding application has run and its work for those years is about to be undone.
BOUND_TO_EGIF_SQL = """
SELECT count(*) FROM rediam_wildfire
WHERE year = ANY(:years) AND egif_wildfire_id IS NOT NULL
"""

#: Deletes every stored fire of the given years, with its parent row and its ignition.
#:
#: Four data-modifying CTEs in one statement, which is what keeps the intermediate
#: states from being visible: ``rediam_wildfire.ignition_id`` references ``ignition``
#: and ``rediam_wildfire.id`` references ``wildfire``, so no order of separate
#: statements is safe, while inside one statement the foreign keys are checked once
#: at the end, against a consistent final state.
#:
#: The ignition goes with the fire it belongs to. It was read from a different file,
#: but it is that fire's point and nothing else references it, so leaving it behind
#: would leave a row no query could reach.
DELETE_YEARS_SQL = """
WITH doomed AS (
    SELECT id, ignition_id FROM rediam_wildfire WHERE year = ANY(:years)
),
removed_child AS (
    DELETE FROM rediam_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM rediam_ignition
    WHERE id IN (SELECT ignition_id FROM doomed WHERE ignition_id IS NOT NULL)
    RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: Maps one staging table onto the two tables of the model in a single statement,
#: dissolving the published duplicates into one fire as it goes.
#:
#: The CTEs, in order, and what each is for:
#:
#: ``cleaned``
#:     The four text attributes trimmed of padding and of any stray line ending, with
#:     an all-whitespace value becoming ``NULL``, and ``--year`` applied. First,
#:     because everything below reads these — a code with a trailing space is a
#:     different key.
#: ``valid``
#:     Everything that can be stored: a geometry, a code, a date, a municipality and a
#:     province. Nothing in the published archive fails this, which is exactly why it
#:     is counted — a future publication that does should say so rather than quietly
#:     import fewer fires.
#: ``repaired``
#:     One feature, flattened to 2D and repaired. ``ST_MakeValid`` fixes the 71
#:     self-intersecting rings and ``ST_CollectionExtract(..., 3)`` flattens what the
#:     repair can leave as a ``GEOMETRYCOLLECTION`` back to polygons. Per feature,
#:     **before** the union, so one bad ring cannot fail a whole fire.
#: ``dissolved``
#:     The fire. One row per ``(code, fire_date)``, the features unioned and their
#:     count kept. See the module docstring for how the columns of a duplicated pair
#:     are chosen, and ``area_conflicts`` below for what is reported when they
#:     disagree.
#: ``numbered``
#:     Primary keys drawn from the sequence up front, because the child insert has to
#:     know its parent's id and ``RETURNING`` would come too late. One id per *fire*,
#:     not one per published feature.
#: ``located``
#:     Zone and country from a point *on* the perimeter (``ST_PointOnSurface``, which
#:     unlike a centroid is guaranteed to be inside it). Both are ``LEFT JOIN``\\ s: a
#:     fire outside every imported boundary keeps its date and its geometry and simply
#:     has no country.
#:
#: The final ``SELECT`` returns the whole audit rather than just a count, because every
#: CTE above it is a filter and a number that only said how many rows landed would
#: leave the user to guess which filter ate the rest.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT NULLIF(btrim(staging.codigo, {trimmed}), '') AS code,
           staging.fecha_inc AS fire_date,
           NULLIF(btrim(staging.municipio, {trimmed}), '') AS municipality_name,
           NULLIF(btrim(staging.provincia, {trimmed}), '') AS province_name,
           staging.sup_arbola AS area_ha_wooded,
           staging.sup_matorr AS area_ha_scrub,
           staging.sup_pastiz AS area_ha_grassland,
           staging.geom AS geom
    FROM {staging_table} AS staging
    WHERE staging.fecha_inc IS NOT NULL AND ({year_filter})
),
valid AS MATERIALIZED (
    SELECT * FROM cleaned
    WHERE cleaned.geom IS NOT NULL
      AND cleaned.code IS NOT NULL
      AND cleaned.fire_date IS NOT NULL
      AND cleaned.municipality_name IS NOT NULL
      AND cleaned.province_name IS NOT NULL
),
repaired AS MATERIALIZED (
    SELECT valid.code, valid.fire_date, valid.municipality_name, valid.province_name,
           valid.area_ha_wooded, valid.area_ha_scrub, valid.area_ha_grassland,
           ST_CollectionExtract(ST_MakeValid(ST_Force2D(valid.geom)), 3) AS part
    FROM valid
),
dissolved AS MATERIALIZED (
    SELECT repaired.code,
           repaired.fire_date,
           min(repaired.municipality_name) AS municipality_name,
           min(repaired.province_name) AS province_name,
           max(repaired.area_ha_wooded) AS area_ha_wooded,
           max(repaired.area_ha_scrub) AS area_ha_scrub,
           max(repaired.area_ha_grassland) AS area_ha_grassland,
           count(*) AS part_count,
           -- Non-zero only where a duplicated fire's rows disagree about an area,
           -- which nothing in the published archive does. Counted rather than
           -- resolved in silence; see the module docstring.
           (count(DISTINCT repaired.area_ha_wooded) > 1
            OR count(DISTINCT repaired.area_ha_scrub) > 1
            OR count(DISTINCT repaired.area_ha_grassland) > 1) AS area_conflict,
           ST_Multi(ST_CollectionExtract(ST_Union(repaired.part), 3)) AS perimeter_source
    FROM repaired
    WHERE NOT ST_IsEmpty(repaired.part)
    GROUP BY repaired.code, repaired.fire_date
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id, dissolved.*
    FROM dissolved
    WHERE NOT ST_IsEmpty(dissolved.perimeter_source)
),
projected AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(numbered.perimeter_source, 4326) AS perimeter,
           ST_PointOnSurface(ST_Transform(numbered.perimeter_source, 4326)) AS locator
    FROM numbered
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
           'rediam_wildfire',
           :provider_id,
           (located.fire_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           -- NULL, and deliberately: the dataset publishes one date per fire and does
           -- not say what it is the date of, so an end would be an invention.
           NULL,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO rediam_wildfire (id, source_layer, code, fire_date, year,
                                 municipality_name, province_name, part_count,
                                 area_ha_wooded, area_ha_scrub, area_ha_grassland,
                                 ignition_id, egif_wildfire_id,
                                 perimeter_etrs89_utm30n)
    SELECT located.wildfire_id,
           :source_layer,
           located.code,
           located.fire_date,
           EXTRACT(YEAR FROM located.fire_date)::int,
           located.municipality_name,
           located.province_name,
           located.part_count,
           located.area_ha_wooded,
           located.area_ha_scrub,
           located.area_ha_grassland,
           -- The point comes from a different file and a later pass; see
           -- IGNITION_TRANSFORM_SQL.
           NULL,
           -- Never set here. The link to the EGIF parte is another application's to
           -- fill; see src/providers/andalusia_rediam/__init__.py.
           NULL,
           located.perimeter_source
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS features,
       (SELECT count(*) FROM valid) AS valid,
       (SELECT count(*) FROM dissolved) AS fires,
       (SELECT count(*) FROM dissolved WHERE area_conflict) AS area_conflicts,
       (SELECT count(*) FROM written) AS written
"""

#: Removes the points a yearly layer imported before, and unlinks the fires.
#:
#: In one statement for :data:`DELETE_YEARS_SQL`'s reason: the fires reference the
#: points, so the link has to be gone before the row is, and only inside a single
#: statement is there no moment at which one is true and the other is not.
DELETE_IGNITIONS_SQL = """
WITH doomed AS (
    SELECT id FROM rediam_ignition WHERE source_layer = :source_layer
),
unlinked AS (
    UPDATE rediam_wildfire SET ignition_id = NULL
    WHERE ignition_id IN (SELECT id FROM doomed)
    RETURNING id
),
removed_child AS (
    DELETE FROM rediam_ignition WHERE id IN (SELECT id FROM doomed) RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_child)
"""

#: Maps one yearly staging table onto the ignition tables, and links each point to
#: the fire it belongs to.
#:
#: The CTEs:
#:
#: ``cleaned``
#:     The code trimmed, and only the rows that publish both coordinates.
#: ``one_per_fire``
#:     The published duplicates again — the 2024 yearly layer has two — collapsed on
#:     the natural key. ``max`` on coordinates that are equal by construction; a pair
#:     that disagreed would be a different fault and would show up as a point in the
#:     wrong place rather than as a constraint violation, which is why
#:     ``point_conflicts`` counts them.
#: ``matched``
#:     Joined to the perimeter already imported, on ``(code, fire_date)``. An **inner**
#:     join: a point whose fire is not in the database has nothing to belong to, and
#:     the audit counts what it dropped.
#: ``numbered``, ``projected``, ``located``
#:     As in the perimeter mapping — an id from the sequence, the published easting and
#:     northing turned into a point and reprojected, and the zone and country resolved
#:     from it. A point is unambiguous about its country in a way a perimeter is not,
#:     so no tie-break is needed here.
#:
#: The final ``UPDATE`` writes the link onto the fire. It is in the same statement as
#: the inserts on purpose: the foreign key is checked once, at the end, against a state
#: in which both the ignition and the link exist.
IGNITION_TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT NULLIF(btrim(staging.codigo, {trimmed}), '') AS code,
           staging.fecha_inc AS fire_date,
           staging.x_inic AS utm_x,
           staging.y_inic AS utm_y
    FROM {staging_table} AS staging
    WHERE staging.x_inic IS NOT NULL
      AND staging.y_inic IS NOT NULL
      AND staging.codigo IS NOT NULL
      AND staging.fecha_inc IS NOT NULL
),
one_per_fire AS MATERIALIZED (
    SELECT cleaned.code, cleaned.fire_date,
           max(cleaned.utm_x) AS utm_x, max(cleaned.utm_y) AS utm_y,
           (count(DISTINCT cleaned.utm_x) > 1
            OR count(DISTINCT cleaned.utm_y) > 1) AS point_conflict
    FROM cleaned
    GROUP BY cleaned.code, cleaned.fire_date
),
matched AS MATERIALIZED (
    SELECT one_per_fire.*, fire.id AS wildfire_id
    FROM one_per_fire
    JOIN rediam_wildfire AS fire
      ON fire.code = one_per_fire.code AND fire.fire_date = one_per_fire.fire_date
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('ignition', 'id')) AS ignition_id, matched.*
    FROM matched
),
projected AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(ST_SetSRID(ST_MakePoint(numbered.utm_x, numbered.utm_y),
                                   :source_srid), 4326) AS geometry
    FROM numbered
),
located AS MATERIALIZED (
    SELECT projected.*, zone.name AS time_zone, country.id AS admin_boundary_id
    FROM projected
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry, projected.geometry)
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry, projected.geometry)
        LIMIT 1
    ) AS country ON TRUE
),
ins_ignition AS (
    INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                          admin_boundary_id)
    SELECT located.ignition_id,
           'rediam_ignition',
           :provider_id,
           located.geometry,
           (located.fire_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           located.time_zone,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO rediam_ignition (id, source_layer, code, fire_date, utm_x, utm_y)
    SELECT located.ignition_id, :source_layer, located.code, located.fire_date,
           located.utm_x, located.utm_y
    FROM located
    JOIN ins_ignition ON ins_ignition.id = located.ignition_id
    RETURNING id
),
linked AS (
    UPDATE rediam_wildfire AS fire
    SET ignition_id = located.ignition_id
    FROM located
    WHERE fire.id = located.wildfire_id
      AND located.ignition_id IN (SELECT id FROM written)
    RETURNING fire.id
),
inside AS (
    SELECT count(*) AS n
    FROM located
    JOIN rediam_wildfire AS fire ON fire.id = located.wildfire_id
    WHERE ST_Contains(fire.perimeter_etrs89_utm30n,
                      ST_SetSRID(ST_MakePoint(located.utm_x, located.utm_y),
                                 :source_srid))
)
SELECT (SELECT count(*) FROM cleaned) AS features,
       (SELECT count(*) FROM one_per_fire) AS points,
       (SELECT count(*) FROM one_per_fire WHERE point_conflict) AS point_conflicts,
       (SELECT count(*) FROM matched) AS matched,
       (SELECT count(*) FROM written) AS written,
       (SELECT count(*) FROM linked) AS linked,
       (SELECT n FROM inside) AS inside
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import REDIAM burnt area perimeters for Andalusia into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Perimeters come from the combined "
               "PERIMETROS_COR_<first>_<last> layer and the ignition points from the "
               "yearly ones that publish X_INIC/Y_INIC. Re-importing replaces the years "
               "it reads. Database settings not given here are read from the environment "
               "(.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published shapefiles: the combined "
                             "layer is imported and the yearly ones are read for their "
                             "ignition points")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single .zip, .shp or directory to import instead of the "
                             "whole set; a yearly layer that publishes X_INIC/Y_INIC "
                             "contributes its points as well")

    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year; may be repeated. The year of the "
                             "published FECHA_INC, which this dataset always agrees with "
                             "the year inside the code")
    parser.add_argument("--skip-ignitions", action="store_true",
                        help="do not read the yearly layers for X_INIC/Y_INIC. The "
                             "perimeters are imported alone and every fire keeps a NULL "
                             "ignition")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would have "
                             "been imported. Nothing is written, including the replacement "
                             "of years already in the database")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_layers(args: argparse.Namespace) -> tuple[Path | None, list[Path]]:
    """The layer to import perimeters from, and the layers to read points from.

    Returns
    -------
    tuple of (Path or None, list of Path)
        The combined layer, and the yearly layers in year order. For ``--shapefile``
        the single file is returned as the perimeter layer, and also as an ignition
        layer if it is a yearly one — a yearly file carries both.

    Raises
    ------
    RuntimeError
        If the directory holds no file at all, or holds no combined layer. Both are
        far more likely a wrong path than an empty download, and silently importing
        nothing would hide it.

    Notes
    -----
    The combined layer is recognised by its **shape** rather than by its name (see
    :func:`~src.providers.andalusia_rediam.is_combined_layer`): the range in the name
    grows with every publication, and an import that looked for
    ``PERIMETROS_COR_2008_2025`` would stop finding the file the year it becomes
    ``…_2026``.

    ``--year`` narrows the yearly layers here, because a layer for a year not being
    imported has no point that could belong to anything. It cannot narrow the combined
    layer, which holds every year in one file; that filter is applied in SQL.
    """
    if args.directory is None:
        single = args.shapefile
        yearly = [single] if andalusia_rediam.layer_year(single.stem) is not None else []
        return single, yearly

    found = [*args.directory.glob("*.zip"), *args.directory.glob("*.shp")]
    if not found:
        raise RuntimeError(f"{args.directory} holds no .zip or .shp file")

    combined = [path for path in found if andalusia_rediam.is_combined_layer(path.stem)]
    if not combined:
        raise RuntimeError(
            f"{args.directory} holds no combined layer: expected a file named "
            f"{andalusia_rediam.LAYER_PREFIX}_<first year>_<last year>, as in "
            f"{andalusia_rediam.LAYER_PREFIX}_2008_2025.shp"
        )
    if len(combined) > 1:
        raise RuntimeError(
            f"{args.directory} holds {len(combined)} combined layers "
            f"({', '.join(sorted(path.name for path in combined))}); importing more than "
            f"one would import the overlapping years twice. Pass the one to import with "
            f"--shapefile"
        )

    dated: list[tuple[int, Path]] = []
    for path in found:
        year = andalusia_rediam.layer_year(path.stem)
        if year is None:
            continue
        if args.year and year not in args.year:
            continue
        dated.append((year, path))
    return combined[0], [path for _, path in sorted(dated)]


def skipped_layers(args: argparse.Namespace) -> list[Path]:
    """The files in the directory that neither pass reads.

    Notes
    -----
    A file silently ignored in a directory the user pointed at is exactly the kind of
    thing that is noticed three months later, so this is reported. It is normally
    empty: everything the service publishes here is either the combined layer or a
    yearly one.
    """
    if args.directory is None:
        return []
    return sorted(
        path for path in [*args.directory.glob("*.zip"), *args.directory.glob("*.shp")]
        if not andalusia_rediam.is_combined_layer(path.stem)
        and andalusia_rediam.layer_year(path.stem) is None
    )


def summarise_years(years: list[int]) -> str:
    """A list of years as it reads in a log line: ``2008-2025``, or the list itself.

    A range where the years are consecutive, which the combined layer's always are,
    and the years spelled out otherwise — ``2021, 2023`` after a ``--year`` run, where
    a range would claim 2022 was replaced as well.
    """
    if not years:
        return "no year"
    ordered = sorted(years)
    if len(ordered) > 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]}-{ordered[-1]}"
    return ", ".join(str(year) for year in ordered)


def year_filter(years: list[int] | None) -> str:
    """The SQL predicate ``--year`` becomes, as a fragment.

    ``TRUE`` when no year was asked for, so the statements are the same shape either
    way and the filter cannot be forgotten in one of the two places it is used.
    """
    return "TRUE" if not years else "EXTRACT(YEAR FROM fecha_inc)::int = ANY(:years)"


def normalise_staging_columns(session: Session, staging_table: str,
                              columns: tuple[tuple[str, str], ...],
                              logger: logging.Logger,
                              warn_missing: bool = True) -> tuple[list[str], list[str]]:
    """Bring the loaded table to ``columns``, in name and in type.

    Returns
    -------
    tuple of (list of str, list of str)
        The columns that had to be added and those that had to be converted, both in
        declaration order.

    Notes
    -----
    A column added here is a layer that does not publish what the combined one does —
    ``SUP_PASTI`` in 2020 and 2021, ``MUNICIPIO`` in 2015 — and it is mapped to
    ``NULL`` rather than guessed at, with a warning. That is the price of importing a
    yearly layer directly; the combined layer needs nothing added.

    What does have to be converted are the areas and the coordinates: they are declared
    with a width in the shapefile and GDAL renders that as ``NUMERIC``, differently per
    layer (``Real (16.6)`` in 2008, ``Real (24.15)`` in the combined file,
    ``Integer64`` for 2021's coordinates). Converting the column once beats casting it
    at every use.

    The empty string is treated as ``NULL`` on the way, which is what an unset text
    field can arrive as and what no numeric type would accept.

    ``warn_missing`` is what the ignition pass turns off. There, a layer that does not
    publish ``X_INIC`` and ``Y_INIC`` is the ordinary case — fourteen of the eighteen
    yearly layers do not — and the caller reports it in those terms instead of the
    column list being warned about as a defect.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = dict(session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema, "table": table}).all())

    added: list[str] = []
    converted: list[str] = []
    for name, column_type in columns:
        if name not in loaded:
            added.append(name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ADD COLUMN {name} {column_type}"))
        elif loaded[name] not in COMPATIBLE_TYPES[column_type]:
            converted.append(name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {column_type} "
                f"USING NULLIF({name}::text, '')::{column_type}"))

    if added and warn_missing:
        logger.warning(
            "Layer does not publish %d of the attributes the combined layer does (%s); "
            "those columns will be NULL on every fire it imports", len(added),
            ", ".join(added))
    if converted:
        logger.debug("Converted %d staged column(s) to the type the mapping reads: %s",
                     len(converted), ", ".join(converted))
    return added, converted


def check_encoding(session: Session, staging_table: str, logger: logging.Logger) -> int:
    """Warn if the staged names look like a character set read wrongly.

    Returns the number of suspect names, which is 0 on every published layer: each one
    carries a ``.cpg`` and GDAL reads it. See :data:`MOJIBAKE_SQL` and the module
    docstring — the check goes with the decision not to force an encoding.
    """
    suspect = session.scalar(text(MOJIBAKE_SQL.format(staging_table=staging_table)))
    if suspect:
        logger.warning(
            "%d staged place name(s) look like a character set read wrongly. Every "
            "published .dbf carries a .cpg and GDAL should read it; this GDAL appears "
            "not to have. The names will be stored mangled.", suspect)
    return suspect


def staged_years(session: Session, staging_table: str, years: list[int] | None) -> list[int]:
    """The years the staged layer holds fires in, after ``--year``.

    These are the years the import replaces. Read from the data rather than from the
    file name, which for the combined layer is a range that changes with every
    publication — see the module docstring.
    """
    statement = STAGED_YEARS_SQL.format(staging_table=staging_table,
                                        year_filter=year_filter(years))
    return list(session.scalars(text(statement), {"years": years or []}))


def delete_years(session: Session, years: list[int], logger: logging.Logger) -> None:
    """Remove every stored fire of these years, with its parent row and its point.

    The count of fires bound to an EGIF *parte* is taken first and warned about:
    nothing in this import ever writes that column, so a non-zero answer means a
    binding application has run and its work for those years is going with the rows.
    """
    bound = session.scalar(text(BOUND_TO_EGIF_SQL), {"years": years})
    result = session.execute(text(DELETE_YEARS_SQL), {"years": years})
    logger.info("Replacing %d year(s) (%s): removed %d fire(s)",
                len(years), summarise_years(years), result.rowcount)
    if bound:
        logger.warning(
            "%d of the removed fire(s) were bound to an EGIF parte; the link went with "
            "them. Re-run the binding application for those years.", bound)


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, source_layer: str, years: list[int] | None):
    """Map the staging table onto the model, returning the audit row.

    Returns
    -------
    sqlalchemy.engine.Row
        ``features, valid, fires, area_conflicts, written`` — the staged features in
        scope, how many of them can be stored, how many fires they dissolve into, how
        many of those had rows disagreeing about an area, and how many were stored.

        The whole audit rather than a count, because every stage of the mapping is a
        filter and a single number would leave the caller to guess which one ate the
        rest.
    """
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        trimmed=TRIMMED_CHARS,
        year_filter=year_filter(years),
    )
    return session.execute(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply finds
        # nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": andalusia_rediam.DEFAULT_TIME_ZONE,
        "source_layer": source_layer,
        "years": years or [],
    }).one()


def transform_ignitions(session: Session, provider_id: int,
                        boundary_provider_id: int | None,
                        staging_table: str, source_layer: str):
    """Map one yearly staging table onto the ignition tables, returning the audit row.

    Returns
    -------
    sqlalchemy.engine.Row
        ``features, points, point_conflicts, matched, written, linked, inside``.
    """
    statement = IGNITION_TRANSFORM_SQL.format(
        staging_table=staging_table,
        trimmed=TRIMMED_CHARS,
    )
    return session.execute(text(statement), {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": andalusia_rediam.DEFAULT_TIME_ZONE,
        "source_layer": source_layer,
        "source_srid": andalusia_rediam.SOURCE_SRID,
    }).one()


def load_layer(archive: Path, staging_table: str, args: argparse.Namespace,
               logger: logging.Logger) -> None:
    """Stage one published layer, in the CRS it was published in.

    EPSG:25830 and not the EPSG:3042 GDAL reads off the ``.prj``: the same projection,
    the axis order the coordinates actually follow. See the module docstring.
    """
    datasource, layer = common.shapefile_datasource(archive)
    common.load_staging_table(
        datasource, layer, staging_table, args, common.resolve_database_settings(args),
        logger,
        target_srs=f"EPSG:{andalusia_rediam.SOURCE_SRID}",
        # No ENCODING open option: every .dbf carries a .cpg and GDAL reads it.
        # check_encoding() below is the check that goes with that decision.
        fid_column=STAGING_FID_COLUMN,
        creation_options=STAGING_CREATION_OPTIONS,
    )


def import_perimeters(archive: Path, engine: Engine, args: argparse.Namespace,
                      provider_id: int, boundary_provider_id: int | None,
                      logger: logging.Logger) -> int:
    """Import the perimeters of one layer in its own transaction.

    Returns the fires imported.

    Under ``--dry-run`` everything happens exactly as it would otherwise — including
    the delete of the years already stored, so that the numbers are the ones a real
    run would produce — and the transaction is rolled back at the end.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    source_layer = andalusia_rediam.source_layer_name(archive.stem)
    log = ArchiveLogger(logger, {"archive": archive.name})

    started = time.monotonic()
    load_layer(archive, staging_table, args, log)

    with Session(engine) as session:
        normalise_staging_columns(session, staging_table, STAGING_COLUMNS, log)
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes the staging table as if it held a handful of rows and picks
        # nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))
        check_encoding(session, staging_table, log)

        years = staged_years(session, staging_table, args.year)
        if not years:
            log.warning("No fire in scope: the layer holds nothing for the year(s) asked "
                        "for")
            if not args.keep_staging:
                common.drop_staging_table(session, staging_table, log)
            session.rollback()
            return 0
        delete_years(session, years, log)

        audit = transform(session, provider_id, boundary_provider_id,
                          staging_table, source_layer, args.year)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    unusable = audit.features - audit.valid
    duplicates = audit.valid - audit.fires
    if unusable:
        log.warning("%d of %d feature(s) publish no geometry, code, date, municipality "
                    "or province and were dropped", unusable, audit.features)
    if duplicates:
        log.info("%d feature(s) are a second copy of a fire already in the layer and "
                 "were dissolved into it", duplicates)
    if audit.area_conflicts:
        log.warning("%d fire(s) are published twice with different burnt areas; the "
                    "largest of each was stored", audit.area_conflicts)
    if audit.fires != audit.written:
        log.warning("%d of %d fire(s) were not stored: a dissolved perimeter that the "
                    "repair reduced to nothing cannot be", audit.fires - audit.written,
                    audit.fires)
    if audit.written:
        log.info("%s%d fire(s) from %d feature(s) over %s in %.0fs",
                 "would have imported " if args.dry_run else "imported ",
                 audit.written, audit.valid, summarise_years(years),
                 time.monotonic() - started)
    return audit.written


def import_ignitions(archive: Path, engine: Engine, args: argparse.Namespace,
                     provider_id: int, boundary_provider_id: int | None,
                     logger: logging.Logger) -> int:
    """Import the ignition points of one yearly layer, returning the points stored.

    A layer that publishes no ``X_INIC`` / ``Y_INIC`` is staged, found to have none and
    skipped — which is the only way to know, the attribute list being a property of the
    file rather than of its name. That costs one load of a few dozen rows.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    source_layer = andalusia_rediam.source_layer_name(archive.stem)
    log = ArchiveLogger(logger, {"archive": archive.name})

    load_layer(archive, staging_table, args, log)

    with Session(engine) as session:
        added, _ = normalise_staging_columns(
            session, staging_table, IGNITION_STAGING_COLUMNS, log, warn_missing=False)
        if set(added) == set(andalusia_rediam.IGNITION_COLUMNS):
            log.info("Publishes no ignition coordinate; nothing to read")
            if not args.keep_staging:
                common.drop_staging_table(session, staging_table, log)
            session.rollback()
            return 0

        normalise_staging_columns(session, staging_table, IGNITION_KEY_COLUMNS, log)
        session.execute(text(f"ANALYZE {staging_table}"))

        delete_ignitions(session, source_layer, log)
        audit = transform_ignitions(session, provider_id, boundary_provider_id,
                                    staging_table, source_layer)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    unmatched = audit.points - audit.matched
    if audit.point_conflicts:
        log.warning("%d fire(s) are published twice with different ignition "
                    "coordinates; one of each was stored", audit.point_conflicts)
    if unmatched and args.dry_run and not audit.matched:
        # Not a fault, and not worth a warning: the perimeters this pass would have
        # matched were rolled back a moment ago, because that is what a dry run does.
        log.info("%d published point(s) matched no fire, which is what a dry run looks "
                 "like: the perimeters were rolled back before this pass ran", unmatched)
    elif unmatched:
        log.warning("%d published point(s) belong to no imported fire and were dropped: "
                    "the yearly layer and the combined one disagree about which fires "
                    "exist", unmatched)
    if audit.written:
        log.info("%s%d ignition point(s), %d of them inside their own perimeter",
                 "would have imported " if args.dry_run else "imported ",
                 audit.written, audit.inside)
    return audit.written


def delete_ignitions(session: Session, source_layer: str, logger: logging.Logger) -> None:
    """Remove the points a yearly layer imported before, unlinking the fires first."""
    result = session.execute(text(DELETE_IGNITIONS_SQL), {"source_layer": source_layer})
    if result.rowcount:
        logger.info("Replacing layer %s: removed %d ignition point(s)",
                    source_layer, result.rowcount)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported."""
    perimeter_layer, yearly_layers = find_layers(args)
    common.require_tables(engine, ["wildfire", "rediam_wildfire", "ignition",
                                   "rediam_ignition", "egif_wildfire", "time_zone",
                                   "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    for path in skipped_layers(args):
        logger.warning("Skipping %s: it is neither the combined layer nor a yearly one",
                       path.name)

    with Session(engine) as session:
        check_time_zones(session, logger, andalusia_rediam.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, andalusia_rediam.PROVIDER_NAME, andalusia_rediam.PROVIDER_PRODUCT,
            andalusia_rediam.PROVIDER_FULL_NAME, andalusia_rediam.PROVIDER_URL, logger,
        )
        boundary_provider = find_boundary_provider(session, logger)
        session.commit()
        # Read back after the commit: the objects are expired and the ids are what
        # every layer that follows actually needs.
        provider_id, boundary_provider_id = provider.id, (
            boundary_provider.id if boundary_provider is not None else None
        )

    started = time.monotonic()
    logger.info("Importing perimeters from %s%s", perimeter_layer.name,
                " (dry run: nothing will be written)" if args.dry_run else "")
    imported = import_perimeters(perimeter_layer, engine, args, provider_id,
                                 boundary_provider_id, logger)

    points = 0
    if args.skip_ignitions:
        logger.info("Not reading the yearly layers for ignition points (--skip-ignitions)")
    elif imported or args.dry_run:
        # Under --dry-run the perimeters were rolled back, so nothing the points could
        # match is in the database and every one of them is reported unmatched. The
        # pass is still run: it says whether the yearly files can be read at all.
        # Not filtered against the perimeter layer: in directory mode the combined
        # layer is not a yearly one and cannot be in this list, and in single-file
        # mode the one file is deliberately both — a yearly layer carries the
        # perimeters *and* the points, and reading it twice is what gets both.
        logger.info("Reading %d yearly layer(s) for ignition points", len(yearly_layers))
        for index, archive in enumerate(yearly_layers, start=1):
            logger.info("[%d/%d] %s", index, len(yearly_layers), archive.name)
            points += import_ignitions(archive, engine, args, provider_id,
                                       boundary_provider_id, logger)

    logger.info("%s %d fire(s) and %d ignition point(s) in %.0fs",
                "Would have imported" if args.dry_run else "Imported",
                imported, points, time.monotonic() - started)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("rediam-import")

    source = args.directory if args.directory is not None else args.shapefile
    if not source.exists():
        logger.error("Not found: %s", source)
        return 1
    if shutil.which(args.ogr2ogr) is None:
        logger.error("ogr2ogr not found (looked for %r). It comes with GDAL and must be "
                     "on PATH.", args.ogr2ogr)
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
