#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import DARPA burnt area perimeters for Catalonia.

Loads the published *incendis forestals* shapefiles into
:class:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire` rows — the generic
columns in ``wildfire``, the Catalan ones in ``darpa_wildfire``.

The department publishes one shapefile per year, so point the import at the
directory they were downloaded into::

    python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires -d /path/to/catalunya/

or at one file, zipped or not::

    python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires -s incendis2024.zip

and ``--year`` narrows a directory to the years asked for::

    python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires \\
        -d /path/to/catalunya/ --year 2023 --year 2024

Each layer is imported in its own transaction, so a year is either wholly in or
wholly out and a failure on the fifteenth does not throw away the fourteen before
it. ``--dry-run`` does the whole of the work and rolls it back, which is the way
to see what a directory would produce without writing anything.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency, not
a Python package.

A fire is many polygons, and this is what dissolves them
---------------------------------------------------------

The whole shape of this import follows from one property of the source: the
layers were vectorised from a raster and **never dissolved**. Most years publish
one feature per fire; 1991, 1993 and 1994 publish fragments, and one 1994 fire is
published as **1,309 separate features**.

So the mapping groups. Every feature of one ``(CODI_FINAL, DATA_INCEN)`` pair
becomes a single ``MULTIPOLYGON``, and how many it was assembled from is kept in
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.part_count` — 4,533
burnt features across the archive are 860 fires.

**On the pair, and not on the code.** ``303/22N`` names a fire in Lleida on 19
June 2022 and another in Figueres on 7 July, and grouping on the code alone would
have unioned the two into one polygon spanning half of Catalonia with nothing left
to notice it by. See :mod:`src.providers.catalonia_darpa`.

``GRID_CODE`` is a raster class, and dropping it drops every bad value
-----------------------------------------------------------------------

``GRID_CODE`` is not an attribute of the fire. It is the class of the raster the
polygons were vectorised from: :data:`~src.providers.catalonia_darpa.GRID_CODE_BURNT`
is burnt, ``0`` is background. The background features are not fires — 179 of the
4,712 published, 173 of them in 1991 — and they are also where **every** defect in
the dataset lives: the 152 features with no code and no date, and the twenty whose
``DATA_INCEN`` is ``2,152543589*``, a float written into a text column.

Filtering ``GRID_CODE`` therefore does the whole of the data cleaning in one
predicate, which is why ``start_date_time`` can be ``NOT NULL`` here with no
invented placeholder of the kind the ICNF import has to fall back on. The import
reports how many features each filter dropped rather than only how many it kept.

Dates: two formats, and the century comes from the layer
---------------------------------------------------------

``DATA_INCEN`` is text, ``dd/mm/yy`` up to 2018 and ``dd/mm/yyyy`` from 2019, with
a single-digit day here and there. Both are parsed; anything else is dropped and
counted.

A two-digit year is resolved against **the layer's own year**, taking whichever
century lands nearer to it — not against a fixed pivot. The two agree on every
fire in the published archive, but a fixed pivot would misread a New Year's Eve
fire filed in the next layer, and the layer year is information the import
already has.

The parse is then checked twice, because a lenient ``to_date`` is worse than no
parse at all: the day and month have to survive the round trip (so ``31/02`` is
rejected rather than becoming the 3rd of March), and the year has to be the
layer's. Both failures are counted and reported.

Before any of that, the text attributes are **trimmed** — of the padding a DBF
character field always has, and of the ``\\r\\n`` that five published values turn
out to end in. See :data:`TRIMMED_CHARS`: untrimmed, those five are five real
fires quietly missing from the import.

No ENCODING option, deliberately
--------------------------------

The published ``.dbf`` files are **not all in the same character set** and none
carries a ``.cpg``: 1986-1988 and 1991-2012 are ISO-8859-1, while 1989, 1990 and
2013-2024 are UTF-8.

They are not ambiguous, though. Each one declares itself in the DBF
language-driver byte — ``0x57`` on every Latin-1 file and ``0x00`` on every UTF-8
one, exactly, across all forty — and GDAL reads it.

So this import passes **no** ``ENCODING`` open option, and that is a decision
rather than an omission. Forcing one overrides the byte, and
:mod:`the ICNF import <src.apps.imports.wildfires.portugal_icnf.import_wildfires>`
has to force one, so this is a real trap for anyone copying that importer:
``ENCODING=ISO-8859-1`` turns ``Alfarràs`` into ``AlfarrÃ s`` in the newer half of
the archive, and ``ENCODING=UTF-8`` turns ``Vallès`` into a name with a
replacement character in it in the older half.

The import checks anyway. After staging it looks for both signatures of a mangling
in the municipality names and warns — the rule is one byte deep in a file format
from 1986, and that is worth asserting rather than trusting.

The geometry is stored twice
----------------------------

``ogr2ogr`` loads the polygons in the CRS they were published in, EPSG:25831, and
the mapping keeps them: the dissolved polygon goes into
``darpa_wildfire.perimeter_etrs89_utm31n`` and its ``ST_Transform`` to EPSG:4326
into ``wildfire.perimeter``. Deriving the second from the first, rather than
loading each separately, is what guarantees the two are the same geometry.

Three layers publish 3D polygons (2017, 2022 and the duplicate), so everything is
flattened with ``ST_Force2D`` before anything else touches it, and the fragments
go through ``ST_MakeValid`` before being unioned — a self-intersecting ring would
otherwise fail the union rather than the feature.

Re-importing a year
-------------------

A layer already in the database is **replaced**: its fires are deleted and the
file is loaded again, in one transaction. The department does republish — the 2024
archive was rewritten in September 2025 — and the alternative, skipping what is
already there, means a corrected perimeter is silently ignored, which is the
failure that is hard to notice.

.. warning::

   Replacing a layer discards any
   :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`
   already bound for that year, because the rows themselves go. The import counts
   the bound rows before deleting them and says so at ``WARNING``; re-running the
   binding application afterwards is what puts them back.

The year comes from the file, not from the layer inside it
-----------------------------------------------------------

``incendis22.zip`` holds a shapefile called plainly ``incendis`` — alone among the
thirty-nine archives — so the GDAL layer read out of it carries no year at all,
while the same fires read from the loose ``incendis2022.shp`` beside it are in a
layer called ``incendis2022``.

So the year, and the
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.source_layer` stored
on every row, come from the name of the **file being imported** and are
canonicalised by
:func:`~src.providers.catalonia_darpa.source_layer_name` to ``incendis`` plus four
digits. ``incendis22.zip``, ``incendis2022.shp`` and an unpacked directory all
import as ``incendis2022``, which is what makes re-importing one after another
replace the year instead of doubling it.

``incendis.shp`` is skipped
----------------------------

The loose one, at the top of a directory: it is byte-identical to
``incendis2022.shp`` — same MD5 on the ``.shp`` and on the ``.dbf`` — because it is
what unpacking ``incendis22.zip`` produces. Importing a directory holding both
would import 2022 twice, with the same codes and the same polygons, and nothing
downstream would flag it.

The **zip** is not skipped: it is a perfectly good source of 2022, and only the
loose copy sitting beside the four-digit file is redundant. See
:data:`~src.providers.catalonia_darpa.DUPLICATE_LAYERS`.
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
from src.providers import catalonia_darpa

# The plumbing every wildfire importer shares, re-exported so this module reads
# as one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401

DEFAULT_STAGING_TABLE = "darpa_burnt_areas"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Every attribute the mapping reads, with the PostgreSQL type it needs, named as
#: ``ogr2ogr`` lands it — lower-cased, which is what its ``LAUNDER`` default does.
#:
#: All four are published by every layer of every year; unlike the ICNF's, this
#: list is not a union over two eras. What does vary is the **order** they are
#: declared in, which changes from layer to layer and does not matter, and the
#: type of ``grid_code``, which arrives as anything from ``numeric(1,0)`` to
#: ``bigint`` — see :data:`COMPATIBLE_TYPES`.
#:
#: Two layers (2013 and 2016) publish an extra ``OBJECTID``. It is an ArcGIS row
#: number, not an identifier of the fire, and is ignored rather than listed.
STAGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("codi_final", "text"),
    ("data_incen", "text"),
    ("municipi", "text"),
    ("grid_code", "integer"),
)

#: The loaded types each declared type will accept without a conversion, by
#: ``information_schema.data_type`` name. The same table as the ICNF import's, and
#: for the same reason: GDAL's PostgreSQL driver renders a field that declares a
#: width as ``NUMERIC(width, scale)``, so ``GRID_CODE: Integer (4.0)`` arrives as
#: ``numeric(4,0)`` and cannot be compared with an integer parameter without a
#: conversion.
COMPATIBLE_TYPES: dict[str, frozenset[str]] = {
    "text": frozenset({"text", "character varying", "character"}),
    "integer": frozenset({"integer", "smallint", "bigint", "numeric"}),
}

#: The characters trimmed off every published text attribute before it is read.
#:
#: Spaces because a DBF character field is space-padded, and **CR and LF because
#: five values in the published archive end in a literal ``\\r\\n``** — the dates of
#: four 2021 fires and one 1994 fire, and the municipality of two of them. They are
#: perfectly ordinary values with a line ending typed into them, and GDAL strips
#: the padding but not those.
#:
#: Untrimmed they are silent damage rather than an error: ``31/07/2021\\r\\n`` fails
#: the date shape and takes a real fire out of the report, and
#: ``LA POBLA DE MASSALUCA\\r\\n`` is stored with the line ending still in it.
TRIMMED_CHARS = r"E' \t\r\n'"

#: The published ``DATA_INCEN`` as a date, or ``NULL`` where it is not one.
#:
#: ``{column}`` is the qualified text column and ``:year`` the layer's year. Used
#: by the transform and, unchanged, by the audit that counts what the transform
#: dropped — written once so the two can never disagree about what a date is.
#:
#: Both published formats are handled. The century of a two-digit year is the one
#: that lands nearer the layer's own year, which is exact and needs no pivot: the
#: 1994 layer reads ``94`` as 1994 because 2094 is a century further away, and a
#: 1999 layer would read ``00`` as 2000 for the same reason. A fixed pivot would
#: get the second wrong.
#:
#: The month and day ranges are checked here rather than left to ``to_date``,
#: which is lenient and would turn ``32/01/2024`` into the 1st of February. What it
#: cannot catch is ``31/02``; :data:`FIRE_DATE_IS_REAL_SQL` does that.
FIRE_DATE_SQL = """
    CASE
        WHEN {column} !~ '^[0-9]{{1,2}}/[0-9]{{1,2}}/([0-9]{{2}}|[0-9]{{4}})$' THEN NULL
        WHEN split_part({column}, '/', 2)::int NOT BETWEEN 1 AND 12 THEN NULL
        WHEN split_part({column}, '/', 1)::int NOT BETWEEN 1 AND 31 THEN NULL
        WHEN length(split_part({column}, '/', 3)) = 4
            THEN to_date({column}, 'DD/MM/YYYY')
        ELSE make_date(
            CASE WHEN abs((1900 + split_part({column}, '/', 3)::int) - :year)
                      <= abs((2000 + split_part({column}, '/', 3)::int) - :year)
                 THEN 1900 + split_part({column}, '/', 3)::int
                 ELSE 2000 + split_part({column}, '/', 3)::int END,
            split_part({column}, '/', 2)::int,
            split_part({column}, '/', 1)::int)
    END
"""

#: Whether a parsed date is the date that was published.
#:
#: ``to_date`` never fails and never says it did not understand: given ``31/02`` it
#: returns the 3rd of March. The only way to know it read what was written is to
#: read the answer back, which is what this does — and it is also where the layer's
#: year is enforced, so a file named for the wrong year is caught here instead of
#: filling ``year`` with a lie.
FIRE_DATE_IS_REAL_SQL = """
    {date} IS NOT NULL
    AND EXTRACT(DAY FROM {date})::int = split_part({column}, '/', 1)::int
    AND EXTRACT(MONTH FROM {date})::int = split_part({column}, '/', 2)::int
    AND EXTRACT(YEAR FROM {date})::int = :year
"""

#: The two signatures of a character set read wrongly, looked for in the staged
#: municipality names.
#:
#: This import deliberately lets GDAL detect the encoding (see the module
#: docstring), and a rule that leans on autodetection deserves a check. ``Ã`` is
#: UTF-8 bytes read as Latin-1 — ``Alfarràs`` becomes ``AlfarrÃ s`` — and U+FFFD is
#: Latin-1 bytes read as UTF-8. Neither occurs in a Catalan municipality name, so
#: either is conclusive.
MOJIBAKE_SQL = """
SELECT count(*) FROM {staging_table}
WHERE municipi LIKE '%Ã%' OR municipi LIKE '%' || chr(65533) || '%'
"""

#: How many fires of a layer already carry a link to an EGIF *parte*.
#:
#: Asked before a replace, because replacing deletes the rows and the link with
#: them. Nothing in this import ever writes the column, so a non-zero answer means
#: a binding application has run and its work for this year is about to be undone.
BOUND_TO_EGIF_SQL = """
SELECT count(*) FROM darpa_wildfire
WHERE source_layer = :source_layer AND egif_wildfire_id IS NOT NULL
"""

#: Deletes everything a named layer imported before, parent rows included.
#:
#: The child rows go first, in a data-modifying CTE whose ``RETURNING`` feeds the
#: parent delete — ``darpa_wildfire.id`` references ``wildfire.id``, so the parents
#: cannot go until the children have, and doing both in one statement means there
#: is no window in which the parents are orphaned.
DELETE_LAYER_SQL = """
WITH removed_child AS (
    DELETE FROM darpa_wildfire WHERE source_layer = :source_layer RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Maps one staging table onto the two tables of the model in a single statement,
#: dissolving the published fragments into one fire as it goes.
#:
#: The CTEs, in order, and what each is for:
#:
#: ``cleaned``
#:     The three text attributes trimmed of padding and of the stray line endings
#:     five of them carry, with an all-whitespace value becoming ``NULL``. First,
#:     because everything below reads these — a code with a trailing ``\\r\\n`` is a
#:     different key, and a date with one is not a date. See :data:`TRIMMED_CHARS`.
#: ``burnt``
#:     Everything that is a fire: ``GRID_CODE`` is the burnt class, and the three
#:     attributes and the geometry are all present. Dropping the background class
#:     removes every null and every corrupt value in the dataset in one predicate.
#: ``dated``
#:     The published date parsed, and checked by reading it back
#:     (:data:`FIRE_DATE_IS_REAL_SQL`).
#: ``repaired``
#:     One fragment, flattened to 2D — three layers publish 3D polygons — and
#:     repaired. ``ST_MakeValid`` fixes a self-intersecting ring, and
#:     ``ST_CollectionExtract(..., 3)`` flattens what the repair can leave as a
#:     ``GEOMETRYCOLLECTION`` back to polygons. Doing this **per fragment, before
#:     the union**, is what keeps one bad ring from failing a whole fire.
#: ``dissolved``
#:     The fire. One row per ``(code, fire_date)`` — see the module docstring on
#:     why not per code — with the fragments unioned, their count kept, and the
#:     municipality taken with ``min`` because the group has exactly one.
#: ``numbered``
#:     Primary keys drawn from the sequence up front, because the child insert has
#:     to know its parent's id and ``RETURNING`` would come too late. Here rather
#:     than at the top, unlike the ICNF import: one id per *fire*, not one per
#:     published feature, or 1994 alone would burn 3,642 of them.
#: ``located``
#:     Zone and country from a point *on* the perimeter (``ST_PointOnSurface``,
#:     which unlike a centroid is guaranteed to be inside it). Both are
#:     ``LEFT JOIN``\\ s: a fire outside every imported boundary keeps its date and
#:     its geometry and simply has no country.
#:
#: The final ``SELECT`` returns the whole audit rather than just a count, because
#: every CTE above it is a filter and a number that only said how many rows landed
#: would leave the user to guess which filter ate the rest.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT NULLIF(btrim(staging.codi_final, {trimmed}), '') AS code,
           NULLIF(btrim(staging.data_incen, {trimmed}), '') AS published_date,
           NULLIF(btrim(staging.municipi, {trimmed}), '') AS municipality_name,
           staging.grid_code AS grid_code,
           staging.geom AS geom
    FROM {staging_table} AS staging
),
burnt AS MATERIALIZED (
    SELECT cleaned.code, cleaned.published_date, cleaned.municipality_name, cleaned.geom
    FROM cleaned
    WHERE cleaned.geom IS NOT NULL
      AND cleaned.grid_code = :grid_code_burnt
      AND cleaned.code IS NOT NULL
      AND cleaned.published_date IS NOT NULL
      AND cleaned.municipality_name IS NOT NULL
),
parsed AS MATERIALIZED (
    SELECT burnt.*, {fire_date} AS fire_date
    FROM burnt
),
dated AS MATERIALIZED (
    SELECT parsed.* FROM parsed WHERE {fire_date_is_real}
),
repaired AS MATERIALIZED (
    SELECT dated.code, dated.fire_date, dated.municipality_name,
           ST_CollectionExtract(ST_MakeValid(ST_Force2D(dated.geom)), 3) AS part
    FROM dated
),
dissolved AS MATERIALIZED (
    SELECT repaired.code,
           repaired.fire_date,
           min(repaired.municipality_name) AS municipality_name,
           count(*) AS part_count,
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
           'darpa_wildfire',
           :provider_id,
           (located.fire_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           -- NULL, and deliberately: the dataset publishes one date per fire and
           -- does not say what it is the date of, so an end would be an invention.
           NULL,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO darpa_wildfire (id, source_layer, code, fire_date, year,
                                municipality_name, part_count, egif_wildfire_id,
                                perimeter_etrs89_utm31n)
    SELECT located.wildfire_id,
           :source_layer,
           located.code,
           located.fire_date,
           :year,
           located.municipality_name,
           located.part_count,
           -- Never set here. The link to the EGIF parte is another application's
           -- to fill; see src/providers/catalonia_darpa/__init__.py.
           NULL,
           located.perimeter_source
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM {staging_table}) AS features,
       (SELECT count(*) FROM burnt) AS burnt,
       (SELECT count(*) FROM dated) AS dated,
       (SELECT count(*) FROM dissolved) AS fires,
       (SELECT count(*) FROM written) AS written
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import DARPA burnt area perimeters for Catalonia into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. A layer already in the database is "
               "replaced, because the department republishes years. Database settings not "
               "given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published shapefiles, one per year")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single .zip, .shp or directory to import instead of a whole set")

    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year from the directory; may be repeated. "
                             "The year of the published layer, which this dataset always "
                             "agrees with the dates inside it")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would have "
                             "been imported. Nothing is written, including the replacement "
                             "of a layer already in the database")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_archives(args: argparse.Namespace) -> list[Path]:
    """List the layers to import, oldest year first.

    Sorted by the year the name carries rather than by the name, so ``incendis10``
    lands between 2009 and 2011 instead of between 1 and 1986.

    A file whose name carries no year, and one named in
    :data:`~src.providers.catalonia_darpa.DUPLICATE_LAYERS`, is left out — the
    second is a byte-identical copy of another layer and importing both would
    double a year. Both are reported by :func:`import_wildfires`, which is where
    there is a logger to report them to.

    Raises
    ------
    RuntimeError
        If the directory holds no archive at all — far more likely a wrong path
        than an empty download, and silently importing nothing would hide it.
        Also if ``--year`` selected none of the archives that are there.
    """
    if args.directory is None:
        return [args.shapefile]

    found = [*args.directory.glob("*.zip"), *args.directory.glob("*.shp")]
    if not found:
        raise RuntimeError(f"{args.directory} holds no .zip or .shp file")

    dated: list[tuple[int, Path]] = []
    for path in found:
        try:
            year = catalonia_darpa.layer_year(path.stem)
        except ValueError:
            continue
        if path.stem in catalonia_darpa.DUPLICATE_LAYERS:
            continue
        if args.year and year not in args.year:
            continue
        dated.append((year, path))

    if not dated:
        wanted = f" for year(s) {', '.join(str(year) for year in sorted(set(args.year)))}" \
            if args.year else ""
        raise RuntimeError(
            f"{args.directory} holds no layer to import{wanted}: expected files named "
            f"{catalonia_darpa.LAYER_PREFIX}<year>, as in "
            f"{catalonia_darpa.LAYER_PREFIX}1994.shp"
        )
    return [path for _, path in sorted(dated)]


def skipped_archives(args: argparse.Namespace) -> tuple[list[Path], list[Path]]:
    """The files in the directory that :func:`find_archives` left out, and why.

    Returns
    -------
    tuple of (list of Path, list of Path)
        The duplicates of another layer, and the files whose name carries no year.
        Both empty for a single-file import, which selects nothing and so skips
        nothing.

    Notes
    -----
    Separate from :func:`find_archives` so that the selection stays a pure list of
    what to import, but reported all the same: a file silently ignored in a
    directory the user pointed at is exactly the kind of thing that is noticed
    three months later.
    """
    if args.directory is None:
        return [], []

    duplicates: list[Path] = []
    unnamed: list[Path] = []
    for path in [*args.directory.glob("*.zip"), *args.directory.glob("*.shp")]:
        if path.stem in catalonia_darpa.DUPLICATE_LAYERS:
            duplicates.append(path)
            continue
        try:
            catalonia_darpa.layer_year(path.stem)
        except ValueError:
            unnamed.append(path)
    return sorted(duplicates), sorted(unnamed)


def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.Logger) -> tuple[list[str], list[str]]:
    """Bring the loaded table to :data:`STAGING_COLUMNS`, in name and in type.

    Every layer publishes all four attributes, so nothing should ever have to be
    added — unlike the ICNF import, where whole eras of the dataset are missing
    most of them. A column added here means a layer that does not publish what
    every other one does, which is worth saying out loud rather than mapping to
    ``NULL`` in silence.

    What does have to be converted is ``grid_code``: it is declared with a width in
    the shapefile and GDAL renders that as ``NUMERIC``, differently per layer
    (``Integer (1.0)`` in 1986, ``Integer (4.0)`` in 1989, ``Integer64`` in 2019).
    Converting the column once beats casting it at every use.

    The empty string is treated as ``NULL`` on the way, which is what an unset text
    field can arrive as and what no numeric type would accept.

    Returns
    -------
    tuple of (list of str, list of str)
        The columns that had to be added and those that had to be converted, both
        in declaration order.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = dict(session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema, "table": table}).all())

    added: list[str] = []
    converted: list[str] = []
    for name, column_type in STAGING_COLUMNS:
        if name not in loaded:
            added.append(name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ADD COLUMN {name} {column_type}"))
        elif loaded[name] not in COMPATIBLE_TYPES[column_type]:
            converted.append(name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {column_type} "
                f"USING NULLIF({name}::text, '')::{column_type}"))

    if added:
        logger.warning(
            "Layer does not publish %d of the %d attributes every other one does (%s); "
            "those fires cannot be stored", len(added), len(STAGING_COLUMNS),
            ", ".join(added))
    if converted:
        logger.debug("Converted %d staged column(s) to the type the mapping reads: %s",
                     len(converted), ", ".join(converted))
    return added, converted


def check_encoding(session: Session, staging_table: str, logger: logging.Logger) -> int:
    """Warn if the staged names look like a character set read wrongly.

    Returns the number of suspect names, which is 0 on every published layer read
    with a GDAL that detects the two encodings correctly. See :data:`MOJIBAKE_SQL`
    and the module docstring: this import deliberately does not force an encoding,
    and this is the check that goes with that decision.
    """
    suspect = session.scalar(text(MOJIBAKE_SQL.format(staging_table=staging_table)))
    if suspect:
        logger.warning(
            "%d staged municipality name(s) look like a character set read wrongly. The "
            "layers are a mix of ISO-8859-1 and UTF-8 and GDAL is left to detect which; "
            "this GDAL appears to have guessed wrong. The names will be stored mangled.",
            suspect)
    return suspect


def layer_is_imported(session: Session, source_layer: str) -> bool:
    """Whether any row of this layer is already stored."""
    return session.scalar(
        text("SELECT EXISTS (SELECT 1 FROM darpa_wildfire WHERE source_layer = :source_layer)"),
        {"source_layer": source_layer},
    )


def delete_layer(session: Session, source_layer: str, logger: logging.Logger) -> None:
    """Remove everything a named layer imported before, children and parents.

    The count of fires that were bound to an EGIF *parte* is taken first and
    warned about: nothing in this import ever writes that column, so a non-zero
    answer means a binding application has run and its work for this year is going
    with the rows.
    """
    bound = session.scalar(text(BOUND_TO_EGIF_SQL), {"source_layer": source_layer})
    result = session.execute(text(DELETE_LAYER_SQL), {"source_layer": source_layer})
    logger.info("Replacing layer %s: removed %d fire(s)", source_layer, result.rowcount)
    if bound:
        logger.warning(
            "%d of the removed fire(s) were bound to an EGIF parte; the link went with "
            "them. Re-run the binding application for %s.", bound, source_layer)


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, source_layer: str, year: int):
    """Map the staging table onto the model, returning the audit row.

    Returns
    -------
    sqlalchemy.engine.Row
        ``features, burnt, dated, fires, written`` — the staged features, how many
        of them are fires, how many of those carry a date that parses, how many
        fires they dissolve into and how many were stored.

        The whole audit rather than a count, because every stage of the mapping is
        a filter and a single number would leave the caller to guess which one ate
        the rest.
    """
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        trimmed=TRIMMED_CHARS,
        fire_date=FIRE_DATE_SQL.format(column="burnt.published_date"),
        fire_date_is_real=FIRE_DATE_IS_REAL_SQL.format(
            date="parsed.fire_date", column="parsed.published_date"),
    )
    return session.execute(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply
        # finds nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": catalonia_darpa.DEFAULT_TIME_ZONE,
        "grid_code_burnt": catalonia_darpa.GRID_CODE_BURNT,
        "source_layer": source_layer,
        "year": year,
    }).one()


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> int:
    """Import one layer in its own transaction, returning the fires imported.

    Under ``--dry-run`` everything happens exactly as it would otherwise —
    including the delete of a layer already stored, so that the numbers are the
    ones a real run would produce — and the transaction is rolled back at the end.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    datasource, layer = common.shapefile_datasource(archive)
    # From the file the department versions, never from the GDAL layer inside it:
    # incendis22.zip holds a layer called plainly "incendis", which carries no year
    # at all, and the same fires read from the loose file are in "incendis2022".
    # See src/providers/catalonia_darpa/__init__.py.
    year = catalonia_darpa.layer_year(archive.stem)
    source_layer = catalonia_darpa.source_layer_name(year)
    log = ArchiveLogger(logger, {"archive": archive.name})

    started = time.monotonic()
    common.load_staging_table(
        datasource, layer, staging_table, args, common.resolve_database_settings(args), log,
        # The published CRS, kept rather than converted: the model stores the
        # polygon in it as well as in EPSG:4326, and the 4326 one is derived from
        # it in SQL so that the two provably agree.
        target_srs=f"EPSG:{catalonia_darpa.SOURCE_SRID}",
        # No ENCODING open option, deliberately. The layers are a mix of
        # ISO-8859-1 and UTF-8, GDAL detects both correctly, and forcing either
        # one corrupts half the archive. See the module docstring, and
        # check_encoding() below, which is the check that goes with the decision.
    )

    with Session(engine) as session:
        if layer_is_imported(session, source_layer):
            delete_layer(session, source_layer, log)

        normalise_staging_columns(session, staging_table, log)
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes the staging table as if it held a handful of rows and
        # picks nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))
        check_encoding(session, staging_table, log)

        audit = transform(session, provider_id, boundary_provider_id,
                          staging_table, source_layer, year)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    background = audit.features - audit.burnt
    undated = audit.burnt - audit.dated
    if background:
        log.info("%d of %d feature(s) are not fires: GRID_CODE is the raster class and "
                 "only %d is burnt", background, audit.features,
                 catalonia_darpa.GRID_CODE_BURNT)
    if undated:
        log.warning("%d burnt feature(s) have a DATA_INCEN that is not a date of %d and "
                    "were dropped", undated, year)
    if audit.fires != audit.written:
        log.warning("%d of %d fire(s) were not stored: a dissolved perimeter that the "
                    "repair reduced to nothing cannot be", audit.fires - audit.written,
                    audit.fires)
    if audit.written:
        log.info("%s%d fire(s) from %d burnt feature(s) in %.0fs (%.1f polygons per fire)",
                 "would have imported " if args.dry_run else "imported ",
                 audit.written, audit.dated, time.monotonic() - started,
                 audit.dated / audit.written)
    return audit.written


def import_wildfires(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported."""
    archives = find_archives(args)
    duplicates, unnamed = skipped_archives(args)
    common.require_tables(engine, ["wildfire", "darpa_wildfire", "egif_wildfire",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    for path in duplicates:
        logger.info("Skipping %s: it is a second copy of another layer, and importing both "
                    "would import that year twice", path.name)
    for path in unnamed:
        logger.warning("Skipping %s: its name carries no year, so there is no layer to "
                       "import it as", path.name)

    with Session(engine) as session:
        check_time_zones(session, logger, catalonia_darpa.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, catalonia_darpa.PROVIDER_NAME, catalonia_darpa.PROVIDER_PRODUCT,
            catalonia_darpa.PROVIDER_FULL_NAME, catalonia_darpa.PROVIDER_URL, logger,
        )
        boundary_provider = find_boundary_provider(session, logger)
        session.commit()
        # Read back after the commit: the objects are expired and the ids are
        # what every archive that follows actually needs.
        provider_id, boundary_provider_id = provider.id, (
            boundary_provider.id if boundary_provider is not None else None
        )

    started = time.monotonic()
    imported = 0
    logger.info("Importing %d layer(s)%s", len(archives),
                " (dry run: nothing will be written)" if args.dry_run else "")
    for index, archive in enumerate(archives, start=1):
        logger.info("[%d/%d] %s", index, len(archives), archive.name)
        imported += import_archive(archive, engine, args, provider_id,
                                   boundary_provider_id, logger)

    logger.info("%s %d fires from %d layer(s) in %.0fs",
                "Would have imported" if args.dry_run else "Imported",
                imported, len(archives), time.monotonic() - started)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("darpa-import")

    source = args.directory if args.directory is not None else args.shapefile
    if not source.exists():
        logger.error("Not found: %s", source)
        return 1
    if shutil.which(args.ogr2ogr) is None:
        logger.error("ogr2ogr not found (looked for %r). It comes with GDAL and must be on PATH.",
                     args.ogr2ogr)
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
