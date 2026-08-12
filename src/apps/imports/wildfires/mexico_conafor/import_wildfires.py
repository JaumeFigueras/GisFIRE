#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import CONAFOR burnt area polygons for Mexico.

Loads the published *Incendios Forestales* archives into
:class:`~src.providers.mexico_conafor.wildfire.ConaforWildfire` rows — the generic
columns in ``wildfire``, the CONAFOR ones in ``conafor_wildfire`` — and the cause
classification into
:class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause`.

CONAFOR publishes one zipped shapefile per year, so point the import at the
directory they were downloaded into::

    python3 -m src.apps.imports.wildfires.mexico_conafor.import_wildfires -d /path/to/mexico/

or at one archive::

    python3 -m src.apps.imports.wildfires.mexico_conafor.import_wildfires -s incendios_2023_shp.zip

Each archive is imported in its own transaction, so a year is either wholly in or
wholly out and a failure on the ninth does not throw away the eight before it.

The attributes change every single year
----------------------------------------

This is the whole difficulty of the source, and it is handled in one place.
**Fifty-eight** published names appear across the fourteen archives and **no two
consecutive years have the same schema** — ``TIPVEG`` is also ``TIPVEGE``,
``TIP_VEG`` and ``TIPO_DE_VE``; 2012 uses ``CLAVE`` for the key and ``TOTAL`` for
the area; 2015 renames almost everything, ``CLAVE_DEL`` for the key included;
``CAUSAESP`` stops in 2019 and the six burnt-area strata vanish in 2022.

Rather than write fourteen mappings, or branch on the year, the import
**normalises the staging table**: after ``ogr2ogr`` has loaded whatever the file
holds, :func:`normalise_staging_columns` brings it to :data:`STAGING_COLUMNS` —
renaming every alias in :data:`~src.providers.mexico_conafor.FIELD_ALIASES` onto
one name, adding every attribute the file did not have as an empty column, and
converting every one it landed in a type the mapping cannot read.

One mapping then covers all fourteen years, and a layer that publishes less simply
leaves more of it ``NULL``. It also means that a fifteenth archive dropping an
attribute changes nothing here — though one *renaming* an attribute needs an entry
adding to ``FIELD_ALIASES``, which is what 2015 needed and what
:func:`check_layer_year` catches when it has not been done: a layer whose key
alias is unknown has no key at all, and the run stops rather than importing
anonymous fires.

Dates are parsed in Python, on purpose
---------------------------------------

``FECHAINIC`` and ``FECHALIQ`` arrive as four different written formats — and the
2022 layer uses all four *within* one column — so they cannot simply be read as
dates. They also cannot safely be parsed in SQL: PostgreSQL's ``to_date`` is
lenient, and ``to_date('22/20/2021', 'DD/MM/YYYY')`` silently returns August 2022
rather than refusing a twentieth month. That is exactly the row this dataset has.

So :func:`normalise_staging_dates` reads the **distinct** published strings — a
few hundred per layer, whatever the row count — parses each with
:func:`~src.providers.mexico_conafor.parse_date`, and writes the results back into
two real ``date`` columns. The parser is then one tested function shared by the
model tests and the import, rather than a regular expression in SQL that could
drift away from it.

An unreadable date becomes ``NULL``: three published values in the whole archive
do, and all three are end dates on rows whose start reads fine. A row with no
readable *start* gets the 1st of January of its year and
``date_time_precision = 'year'``, exactly as the ICNF import does — no row of the
archive as published needs it, and the next release might.

No layer publishes a time of day, so every stored instant is local midnight
against the zone the polygon falls in, and every imported row is marked ``day``.
Mexico spans four zones and abolished daylight saving outside the northern border
strip in 2022, so the zone is resolved per fire and stored by name; see
:mod:`src.data_model.wildfire`.

The year comes from the file name, and is checked against the data
-------------------------------------------------------------------

Only three of the fourteen layers publish ``ANO``, so the year is taken from the
archive:
``incendios_2021`` is 2021. That is a file name, which is a weaker thing to trust
than data — so it is **verified**: every published ``CLAVEINC`` is
``YY-EE-NNNN``, and :func:`check_layer_year` compares its two-digit prefix against
the year the name claims and refuses the layer if they disagree. A mis-named or
mis-downloaded archive is caught before anything is written rather than in a
query three months later.

The five duplicate features
----------------------------

``CLAVEINC`` takes 45,909 distinct values in 45,914 rows. All five repeats are in
the 2021 layer and all five are *exact* duplicate features — identical attributes
and byte-identical geometry — except that the second copy of the four Guerrero
ones has its two date fields blanked.

The mapping de-duplicates on the key, keeping the copy that has a start date, and
reports how many it dropped. This is what lets
:attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.fire_code` carry a
``UNIQUE`` constraint — and the constraint is why de-duplicating is not optional:
without it the 2021 archive fails to import at all.

Re-running an import
---------------------

A layer already in the database is **skipped**, and ``--replace`` deletes what it
loaded before importing it again. Unlike the ICNF import this is a convenience
rather than a necessity — ``fire_code`` is unique, so an upsert would be possible
— but replacing a year is the simpler operation, and it is the only one that
removes a fire CONAFOR has withdrawn from a revised publication.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency, not
a Python package.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import time

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers import mexico_conafor
from src.providers.mexico_conafor import FIELD_ALIASES
from src.providers.mexico_conafor import MISSING_VALUES
from src.providers.mexico_conafor.fire_cause import CAUSE_NORMALISATIONS
from src.providers.mexico_conafor.fire_cause import CAUSE_TRANSLATIONS
from src.providers.mexico_conafor.fire_cause import ConaforFireCause
from src.providers.mexico_conafor.fire_cause import SPECIFIC_CAUSE_TRANSLATIONS

# The plumbing every wildfire importer shares, re-exported so this module reads as
# one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401

DEFAULT_STAGING_TABLE = "conafor_wildfires"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The year in a published archive or layer name — ``incendios_2021_shp.zip``,
#: ``incendios_2021``.
#:
#: Four digits and not two: the published key carries a two-digit year and no
#: century, so the file name is the only thing that says which hundred years these
#: fires burnt in. See :func:`layer_year`.
LAYER_YEAR_PATTERN = re.compile(r"(?<!\d)(\d{4})(?!\d)")

#: Every attribute the mapping reads, with the PostgreSQL type it needs, under the
#: name :func:`normalise_staging_columns` brings it to.
#:
#: The names are the model's own — ``fire_code``, not ``claveinc`` — because with
#: several spellings of some fields there is no published name that could serve.
#: :data:`~src.providers.mexico_conafor.FIELD_ALIASES` is what maps one to the
#: other, and it is the provider module's rather than this one's so that anything
#: else reading the archives folds them the same way.
#:
#: The type is what the mapping needs to read, which is rarely what ``ogr2ogr``
#: produces — see :data:`COMPATIBLE_TYPES` and :func:`normalise_staging_columns`.
#: The two date fields are deliberately ``text``: they arrive as dates in six
#: layers and as strings in seven, in four written formats, and the import parses
#: them itself. See the module docstring.
STAGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fire_code", "text"),
    ("state_name", "text"),
    ("municipality_code", "integer"),
    ("municipality_name", "text"),
    ("property_name", "text"),
    ("cause", "text"),
    ("specific_cause", "text"),
    ("start_date", "text"),
    ("end_date", "text"),
    ("fire_type", "text"),
    ("vegetation_type", "text"),
    ("impact_level", "text"),
    ("protected_area_name", "text"),
    ("area_ha_protected", "double precision"),
    ("area_ha", "double precision"),
    ("area_ha_tree", "double precision"),
    ("area_ha_regeneration", "double precision"),
    ("area_ha_shrub", "double precision"),
    ("area_ha_herbaceous", "double precision"),
    ("area_ha_litter", "double precision"),
    ("area_ha_organic_soil", "double precision"),
    ("perimeter_source", "text"),
)

#: The two ``date`` columns :func:`normalise_staging_dates` derives from the text
#: ones above, and the ``text`` column :func:`normalise_staging_vegetation`
#: derives from ``vegetation_type``.
#:
#: Separate from :data:`STAGING_COLUMNS` because these are not published: they are
#: what the Python passes compute, and the mapping reads them instead of the raw
#: strings.
DERIVED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("start_date_parsed", "date"),
    ("end_date_parsed", "date"),
    ("vegetation_code", "text"),
)

#: The loaded types each declared type will accept without a conversion, by
#: ``information_schema.data_type`` name.
#:
#: What ``ogr2ogr`` lands is not what the shapefile's own field types suggest, and
#: with this dataset it varies wildly between layers of the same series:
#:
#: * ``CLAVEMUN`` is ``Integer (9.0)`` in 2018-2019 and ``Real (24.15)`` from
#:   2020, so it arrives as ``integer`` in two layers and ``numeric(24,15)`` in
#:   four. The mapping needs an integer either way.
#: * the six burnt-area strata are ``Real`` in every layer but 2011 and 2012,
#:   where they are ``String`` — so ``ARBUSTI_HA`` really does arrive as text
#:   holding ``'2907.5'``.
#: * ``ID`` is ``Real`` in twelve layers and ``String`` in 2016. It is not
#:   imported, but it shows how little the declared types can be relied on.
#:
#: ``text`` accepts nothing but text on purpose. The date columns are declared
#: ``text`` here and six layers land them as ``date``, which is precisely the case
#: that has to be converted rather than accepted: the parser reads strings, and a
#: ``date`` handed to it would arrive already interpreted by GDAL.
COMPATIBLE_TYPES: dict[str, frozenset[str]] = {
    "text": frozenset({"text", "character varying", "character"}),
    "integer": frozenset({"integer", "smallint", "bigint"}),
    "double precision": frozenset({"double precision", "real", "numeric",
                                   "integer", "smallint", "bigint"}),
    "date": frozenset({"date"}),
}

#: How to convert a staged column to each declared type, as a ``USING``
#: expression. ``{name}`` is the column.
#:
#: Everything goes through text first, which is the only conversion that works
#: from every type a column can arrive as, and the empty string becomes ``NULL``
#: on the way — that is what an unset text field lands as and what no other type
#: would accept.
#:
#: ``integer`` then goes through ``double precision`` rather than straight from
#: text, and it has to: ``CLAVEMUN`` arrives as ``numeric(24,15)`` from 2020, so
#: the text of it is ``'2.000000000000000'``, and PostgreSQL will not cast that to
#: an integer. Every value the column takes is whole, so the rounding is exact.
CONVERSION_EXPRESSIONS: dict[str, str] = {
    "text": "NULLIF(btrim({name}::text), '')",
    "integer": "NULLIF(btrim({name}::text), '')::double precision::integer",
    "double precision": "NULLIF(btrim({name}::text), '')::double precision",
    "date": "NULLIF(btrim({name}::text), '')::date",
}

#: The published values that mean *nothing here*, folded for comparison in SQL.
#:
#: The SQL fold is ``lower(btrim(...))`` with runs of whitespace collapsed, which
#: is :func:`~src.providers.mexico_conafor.normalise` minus the accent stripping.
#: That is enough **because every one of these strings is unaccented ASCII**, which
#: is asserted by a test rather than left to hold by luck — if a null token with an
#: accent is ever added to
#: :data:`~src.providers.mexico_conafor.MISSING_VALUES`, that test fails and this
#: comment stops being true.
MISSING_VALUES_SQL = ", ".join(f"'{value}'" for value in sorted(MISSING_VALUES))

#: Blanks a staged text column where it holds one of the null tokens.
#:
#: Applied to the text columns only. ``'0'`` is one of the tokens and is a
#: perfectly good reading of ``ANP_HA`` — the fire touched no protected area — so
#: running this over a numeric column would turn *no protected area* into *not
#: measured*.
#: The empty string is in the list too. A column the type conversion touched has
#: already had it turned into ``NULL``; one that landed as text and needed no
#: conversion has not, and a shapefile writes an unset text field as ``''``.
NULLIFY_SQL = """
UPDATE {staging_table}
SET {column} = NULL
WHERE {column} IS NOT NULL
  AND lower(btrim(regexp_replace({column}, '\\s+', ' ', 'g'))) IN ({tokens})
"""

#: The distinct published date strings of a layer, both columns at once.
#:
#: A few hundred at most, whatever the row count: a year has 365 days and the
#: archives write each in one or two formats. Reading them distinct is what makes
#: parsing in Python affordable.
DATE_VALUES_SQL = """
SELECT DISTINCT value FROM (
    SELECT start_date AS value FROM {staging_table}
    UNION
    SELECT end_date AS value FROM {staging_table}
) AS published
WHERE value IS NOT NULL AND btrim(value) <> ''
"""

#: The distinct published vegetation types of a layer. 148 over the whole archive,
#: so a few dozen per layer.
VEGETATION_VALUES_SQL = """
SELECT DISTINCT vegetation_type FROM {staging_table}
WHERE vegetation_type IS NOT NULL
"""

#: The two-digit year prefixes the published keys carry, with how many rows use
#: each. One row per prefix, so this is cheap and complete rather than a sample.
#: See :func:`check_layer_year`.
KEY_YEARS_SQL = """
SELECT substring(fire_code from 1 for 2) AS prefix, count(*) AS rows
FROM {staging_table}
WHERE fire_code ~ '^[0-9]{{2}}-[0-9]{{2}}-[0-9]{{4}}$'
GROUP BY 1
ORDER BY 2 DESC
"""

#: The distinct cause classifications a layer uses. Around twenty per layer and
#: 176 over the whole dataset, so this is read into Python and reconciled there
#: rather than carrying a forty-row lookup table into SQL.
CAUSES_SQL = """
SELECT DISTINCT cause, specific_cause
FROM {staging_table}
WHERE cause IS NOT NULL
ORDER BY cause, specific_cause
"""

#: Published causes that reached no canonical form, once this layer's have been
#: stored. Reported rather than prevented — an unreconciled cause is still a
#: cause, and refusing it would drop a fire — but it is worth knowing about,
#: because a series grouped by ``cause_normalised`` silently loses these rows into
#: a ``NULL`` bucket.
UNRECONCILED_CAUSES_SQL = """
SELECT cause, count(*) AS classifications
FROM conafor_fire_cause
WHERE cause_normalised IS NULL
GROUP BY cause
ORDER BY cause
"""

#: Deletes everything a named layer imported before, parent rows included.
#:
#: The child rows go first, in a data-modifying CTE whose ``RETURNING`` feeds the
#: parent delete — ``conafor_wildfire.id`` references ``wildfire.id``, so the
#: parents cannot go until the children have, and doing both in one statement
#: means there is no window in which the parents are orphaned.
DELETE_LAYER_SQL = """
WITH removed_child AS (
    DELETE FROM conafor_wildfire WHERE source_layer = :source_layer RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Maps one staging table onto the two tables of the model in a single statement.
#:
#: ``eligible`` is where the de-duplication happens. One published feature becomes
#: one fire, except that five features of the 2021 layer are exact duplicates of
#: five others: ``ROW_NUMBER`` over the key keeps one of each, ordered so that a
#: copy **with** a start date beats one whose dates were blanked, which is the
#: shape those five take. Without this the layer cannot be imported at all, the
#: model's ``fire_code`` being ``UNIQUE``.
#:
#: The filter drops only what could not be stored at all: a row with no key, or a
#: malformed one (there are none today, and a fourteenth archive is not promised).
#:
#: Nothing else is dropped, and two absences are deliberately kept. A row with
#: **no geometry** is imported with a ``NULL`` perimeter — nine features of the
#: 2012 layer carry attributes and an empty shape — and simply resolves no zone
#: and no country. A row with **no burnt area** is imported too: ``21-24-0078``
#: publishes everything else, polygon included, and dropping it over an empty
#: field would lose a real fire. Both are what the nullable columns are for.
#:
#: The primary key is drawn from the sequence up front, in ``eligible``, because
#: the child insert has to know its parent's id and ``RETURNING`` would come too
#: late.
#:
#: ``repaired`` does the geometry work once: ``ST_MakeValid`` fixes the 145
#: published polygons that self-intersect, and ``ST_CollectionExtract(..., 3)``
#: flattens what the repair can leave as a ``GEOMETRYCOLLECTION`` back into a
#: ``MULTIPOLYGON``. A repair that reduces a polygon to nothing yields ``NULL``
#: rather than an empty geometry, so such a fire is kept on the same argument as
#: the shapeless ones above.
#:
#: ``located`` resolves the zone and the country from a point *on* the perimeter
#: (``ST_PointOnSurface``, which unlike a centroid is guaranteed to be inside it).
#: Both are ``LEFT JOIN``\\ s, and both simply find nothing for a fire with no
#: perimeter.
#:
#: The date rules: a start date at local midnight and ``day``, or — where none
#: could be read — the 1st of January of the layer's year and ``year``. The end is
#: the last second of its day, as in the ICNF and GFA imports, which is the closest
#: a date-only value can come to "some time that day".
#:
#: ``state_code`` is read out of the key rather than off ``ESTADO``: the code
#: agrees with the name in all but one of the 45,914 published rows, and the name is spelled 34
#: ways for 32 states.
TRANSFORM_SQL = """
WITH eligible AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id, staged.*
    FROM (
        SELECT staging.*,
               row_number() OVER (
                   PARTITION BY staging.fire_code
                   ORDER BY (staging.start_date_parsed IS NULL), staging.{fid_column}
               ) AS copy_number
        FROM {staging_table} AS staging
        WHERE staging.fire_code ~ '^[0-9]{{2}}-[0-9]{{2}}-[0-9]{{4}}$'
    ) AS staged
    WHERE staged.copy_number = 1
),
repaired AS MATERIALIZED (
    SELECT eligible.*,
           CASE WHEN eligible.geom IS NULL THEN NULL
                ELSE NULLIF(
                    ST_CollectionExtract(ST_MakeValid(eligible.geom), 3),
                    'SRID=4326;MULTIPOLYGON EMPTY'::geometry) END AS perimeter
    FROM eligible
),
located AS MATERIALIZED (
    SELECT repaired.*, zone.name AS time_zone, country.id AS admin_boundary_id
    FROM repaired
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE repaired.perimeter IS NOT NULL
          AND ST_Contains(time_zone.geometry, ST_PointOnSurface(repaired.perimeter))
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND repaired.perimeter IS NOT NULL
          AND ST_Contains(boundary.geometry, ST_PointOnSurface(repaired.perimeter))
        LIMIT 1
    ) AS country ON TRUE
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT located.wildfire_id,
           'conafor_wildfire',
           :provider_id,
           (COALESCE(located.start_date_parsed, make_date(:year, 1, 1))::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           CASE WHEN located.end_date_parsed IS NULL THEN NULL
                ELSE (located.end_date_parsed::timestamp + interval '23:59:59')
                     AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone) END,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO conafor_wildfire (id, fire_code, year, source_layer, state_code,
                                  state_name, municipality_code, municipality_name,
                                  property_name, date_time_precision, cause_id,
                                  fire_type, impact_level, vegetation_type,
                                  vegetation_type_code, protected_area_name,
                                  area_ha_protected, area_ha, area_ha_tree,
                                  area_ha_regeneration, area_ha_shrub,
                                  area_ha_herbaceous, area_ha_litter,
                                  area_ha_organic_soil, perimeter_source)
    SELECT located.wildfire_id,
           located.fire_code,
           :year,
           :source_layer,
           substring(located.fire_code from 4 for 2)::integer,
           located.state_name,
           NULLIF(located.municipality_code, 0),
           located.municipality_name,
           located.property_name,
           CASE WHEN located.start_date_parsed IS NULL THEN :precision_year
                ELSE :precision_day END,
           cause.id,
           located.fire_type,
           located.impact_level,
           located.vegetation_type,
           located.vegetation_code,
           located.protected_area_name,
           located.area_ha_protected,
           located.area_ha,
           located.area_ha_tree,
           located.area_ha_regeneration,
           located.area_ha_shrub,
           located.area_ha_herbaceous,
           located.area_ha_litter,
           located.area_ha_organic_soil,
           located.perimeter_source
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    -- On the whole pair, and NULL-safely: three fires in five have no specific
    -- cause, and `= NULL` would match none of them. See the two partial unique
    -- indexes in src.providers.mexico_conafor.fire_cause.
    LEFT JOIN conafor_fire_cause AS cause
           ON cause.cause = located.cause
          AND cause.specific_cause IS NOT DISTINCT FROM located.specific_cause
    RETURNING id
)
SELECT count(*) FROM written
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import CONAFOR burnt area polygons for Mexico into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time — Mexico spans four zones, so the "
               "lookup really does decide. Database settings not given here are read "
               "from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published archives, one per year")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single .zip, .shp or directory to import instead of a whole set")

    parser.add_argument("--replace", action="store_true",
                        help="re-import a layer already in the database, deleting what it "
                             "loaded before. Without it an already-imported layer is skipped")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_archives(args: argparse.Namespace) -> list[Path]:
    """List the archives to import, sorted, so the years go in in order.

    Sorting is enough to put them in chronological order: the published names all
    read ``incendios_YYYY_shp.zip``, so they sort by year already.

    Raises
    ------
    RuntimeError
        If the directory holds no archive at all — far more likely a wrong path
        than an empty download, and silently importing nothing would hide it.
    """
    if args.directory is None:
        return [args.shapefile]

    found = sorted([*args.directory.glob("*.zip"), *args.directory.glob("*.shp")])
    if not found:
        raise RuntimeError(f"{args.directory} holds no .zip or .shp file")
    return found


def layer_year(layer: str) -> int:
    """Read the year out of a layer name — ``incendios_2021`` is 2021.

    Only three of the fourteen layers publish ``ANO``, so the name is where the
    year comes from. It is checked against the data afterwards by
    :func:`check_layer_year`, which is what makes trusting a file name acceptable.

    Raises
    ------
    RuntimeError
        If the name carries no four-digit number, or more than one and so no
        unambiguous choice.
    """
    found = LAYER_YEAR_PATTERN.findall(layer)
    if not found:
        raise RuntimeError(
            f"Cannot tell which year layer {layer!r} is: the name carries no four-digit "
            f"year, and only three of the published layers publish one as an attribute. "
            f"Rename the archive to the published form, incendios_YYYY_shp.zip."
        )
    if len(set(found)) > 1:
        raise RuntimeError(
            f"Layer {layer!r} carries {len(set(found))} four-digit numbers "
            f"({', '.join(sorted(set(found)))}); cannot tell which is the year."
        )
    return int(found[0])


def check_layer_year(session: Session, staging_table: str, year: int,
                     logger: logging.Logger) -> None:
    """Verify the year from the file name against the keys in the data.

    Every published ``CLAVEINC`` is ``YY-EE-NNNN``, and its two-digit prefix is the
    year. Comparing it against the name catches a renamed, mis-downloaded or
    duplicated archive **before** anything is written — which matters here more
    than in the sibling imports, because the year is the unit an import replaces
    and a wrong one would replace the wrong year's fires.

    The comparison is on the two digits, the key carrying no century.

    Raises
    ------
    RuntimeError
        If the majority of the keys disagree with the name.
    """
    rows = session.execute(text(KEY_YEARS_SQL.format(staging_table=staging_table))).all()
    if not rows:
        raise RuntimeError(
            f"No row of this layer has a key of the published form YY-EE-NNNN, so it "
            f"cannot be checked against the year {year} its name claims, and nothing "
            f"identifies its fires. Is this a CONAFOR incendios archive?"
        )

    expected = f"{year % 100:02d}"
    prefix, rows_with_prefix = rows[0]
    if prefix != expected:
        raise RuntimeError(
            f"Layer says {year}, but {rows_with_prefix} of its keys begin {prefix!r} "
            f"rather than {expected!r}. Refusing to import: the year is what an import "
            f"replaces, so a wrong one would replace another year's fires."
        )

    stragglers = sum(count for other, count in rows[1:])
    if stragglers:
        logger.warning("%d key(s) of this layer carry a year prefix other than %r (%s). "
                       "They are imported under %d, which is the layer they were "
                       "published in.", stragglers, expected,
                       ", ".join(f"{other} x{count}" for other, count in rows[1:]), year)


def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.Logger) -> tuple[list[str], list[str]]:
    """Bring the loaded table to :data:`STAGING_COLUMNS`, in name and in type.

    This is what lets one mapping read all fourteen years, and it does three
    things.

    **Renames every published alias onto one name.** ``TIPVEG``, ``TIPVEGE`` and
    ``TIP_VEG`` all become ``vegetation_type``; ``CLAVEINC`` and ``CLAVE`` both
    become ``fire_code``. The aliases come from
    :data:`~src.providers.mexico_conafor.FIELD_ALIASES`, in the order declared
    there, so a layer publishing two of them — none does — would take the first.

    **Adds what the layer does not publish.** 2012 publishes no vegetation, type,
    impact or protected area; 2022 and 2023 publish none of the six burnt-area
    strata; only 2023 publishes ``POLIGONO``. Those columns are created here and
    stay ``NULL`` all the way into the model.

    **Converts what it publishes in the wrong type.** ``ogr2ogr`` does not land the
    types the shapefile's field list suggests, and what it lands changes with the
    layer (see :data:`COMPATIBLE_TYPES`). Converting the column once is better
    than casting it at every use: a cast in the mapping would have to be right for
    every type the column could arrive as, and would be wrong for exactly the
    layer nobody tested.

    The empty string is treated as ``NULL`` on the way, which is what an unset text
    field can arrive as and what no other type would accept.

    Returns
    -------
    tuple of (list of str, list of str)
        The columns that had to be added — the attributes this layer does not
        publish — and those that had to be converted, both in declaration order.

    Notes
    -----
    ``ogr2ogr`` lower-cases the published names on the way in (its ``LAUNDER``
    default), so the aliases are matched case-insensitively rather than assuming
    either case.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = dict(session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema, "table": table}).all())

    renamed: list[str] = []
    for name, _ in STAGING_COLUMNS:
        if name in loaded:
            continue
        for alias in FIELD_ALIASES[name]:
            landed = next((column for column in loaded if column.lower() == alias.lower()), None)
            if landed is not None:
                session.execute(text(
                    f'ALTER TABLE {staging_table} RENAME COLUMN "{landed}" TO {name}'))
                loaded[name] = loaded.pop(landed)
                renamed.append(f"{landed} -> {name}")
                break
    if renamed:
        logger.debug("Renamed %d published column(s) onto the mapping's names: %s",
                     len(renamed), ", ".join(renamed))

    added: list[str] = []
    converted: list[str] = []
    for name, column_type in (*STAGING_COLUMNS, *DERIVED_COLUMNS):
        if name not in loaded:
            added.append(name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ADD COLUMN {name} {column_type}"))
        elif loaded[name] not in COMPATIBLE_TYPES[column_type]:
            converted.append(name)
            using = CONVERSION_EXPRESSIONS[column_type].format(name=name)
            session.execute(text(
                f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {column_type} "
                f"USING {using}"))

    published = {name for name, _ in STAGING_COLUMNS}
    missing = [name for name in added if name in published]
    if missing:
        logger.info("Layer does not publish %d of the %d known attributes (%s)",
                    len(missing), len(STAGING_COLUMNS), ", ".join(missing))
    if converted:
        logger.debug("Converted %d staged column(s) to the type the mapping reads: %s",
                     len(converted), ", ".join(converted))
    return added, converted


def blank_missing_values(session: Session, staging_table: str,
                         logger: logging.Logger) -> int:
    """Turn the archives' several null tokens into real ``NULL``\\ s.

    ``'0'``, ``'N/A'``, ``'Sin dato'``, ``'Ninguna / No aplica'`` and the empty
    string all appear, sometimes in the same column in different years, and every
    one of them has to become ``NULL`` rather than be stored as text that looks
    like data. See :data:`~src.providers.mexico_conafor.MISSING_VALUES`.

    Applied to the **text** columns only, and deliberately not to the numeric
    ones: ``'0'`` is a null token *and* a perfectly good reading of ``ANP_HA`` —
    the fire touched no protected area — and blanking it would turn *no protected
    area* into *not measured*.

    ``fire_code`` is exempt for a different reason: it is the key, it is never a
    null token, and a key that folded to one would be a data error worth seeing
    rather than a value worth discarding.

    Returns
    -------
    int
        How many values were blanked, across all columns.
    """
    blanked = 0
    for name, column_type in STAGING_COLUMNS:
        if column_type != "text" or name in ("fire_code", "start_date", "end_date"):
            continue
        result = session.execute(text(NULLIFY_SQL.format(
            staging_table=staging_table, column=name, tokens=MISSING_VALUES_SQL)))
        blanked += result.rowcount
    logger.debug("Blanked %d value(s) that mean 'nothing here'", blanked)
    return blanked


def normalise_staging_dates(session: Session, staging_table: str,
                            logger: logging.Logger) -> tuple[int, list[str]]:
    """Parse the published date strings into two real ``date`` columns.

    Reads the **distinct** published strings — a few hundred per layer, whatever
    the row count — parses each with
    :func:`~src.providers.mexico_conafor.parse_date`, and writes the results back
    with a single ``UPDATE`` per column joined against a ``VALUES`` list.

    Done in Python rather than in SQL because ``to_date`` is lenient in exactly
    the way this dataset needs it not to be: ``to_date('22/20/2021', 'DD/MM/YYYY')``
    returns August 2022 instead of refusing a twentieth month, and that row is in
    the 2021 archive. See the module docstring.

    Returns
    -------
    tuple of (int, list of str)
        How many distinct strings were parsed, and the ones that could not be —
        sorted, and at most a handful.
    """
    published = [row[0] for row in session.execute(
        text(DATE_VALUES_SQL.format(staging_table=staging_table))).all()]
    if not published:
        return 0, []

    parsed = {value: mexico_conafor.parse_date(value) for value in published}
    unreadable = sorted(value for value, date in parsed.items() if date is None)
    readable = {value: date for value, date in parsed.items() if date is not None}

    for column in ("start_date", "end_date"):
        if not readable:
            continue
        session.execute(
            text(f"UPDATE {staging_table} AS staging SET {column}_parsed = mapping.parsed "
                 f"FROM (SELECT * FROM unnest(:published ::text[], :dates ::date[])) "
                 f"AS mapping(published, parsed) "
                 f"WHERE staging.{column} = mapping.published"),
            {"published": list(readable), "dates": list(readable.values())},
        )

    if unreadable:
        logger.warning("%d published date value(s) could not be read and are stored as "
                       "NULL: %s. A fire with no readable start date is dated to the 1st "
                       "of January of its year and marked 'year'.",
                       len(unreadable), ", ".join(repr(value) for value in unreadable))
    logger.debug("Parsed %d distinct published date string(s)", len(readable))
    return len(readable), unreadable


def normalise_staging_vegetation(session: Session, staging_table: str,
                                 logger: logging.Logger) -> int:
    """Split the INEGI code out of the published vegetation types.

    Same distinct-value pass as :func:`normalise_staging_dates`, and for the same
    reason: :func:`~src.providers.mexico_conafor.split_vegetation_type` needs the
    fixed set of real codes to avoid reading the *Pino* of
    ``'Bosque de Encino - Pino'`` as one, and that set lives in Python beside the
    model.

    The published string itself is left exactly as it is. Only the derived code is
    written.

    Returns
    -------
    int
        How many distinct published types carried a code.
    """
    published = [row[0] for row in session.execute(
        text(VEGETATION_VALUES_SQL.format(staging_table=staging_table))).all()]
    coded = {value: mexico_conafor.split_vegetation_type(value)[1] for value in published}
    coded = {value: code for value, code in coded.items() if code is not None}
    if not coded:
        return 0

    session.execute(
        text(f"UPDATE {staging_table} AS staging SET vegetation_code = mapping.code "
             f"FROM (SELECT * FROM unnest(:published ::text[], :codes ::text[])) "
             f"AS mapping(published, code) "
             f"WHERE staging.vegetation_type = mapping.published"),
        {"published": list(coded), "codes": list(coded.values())},
    )
    logger.debug("Read an INEGI vegetation code off %d distinct published type(s)",
                 len(coded))
    return len(coded)


def upsert_causes(session: Session, staging_table: str, logger: logging.Logger) -> int:
    """Store the cause classifications this layer uses, returning how many it has.

    The catalogue is not seeded from a fixed list — it is whatever the layer
    actually contains — so a cause CONAFOR types for the first time arrives with
    the first fire that uses it. The canonical Spanish comes from
    :data:`~src.providers.mexico_conafor.fire_cause.CAUSE_NORMALISATIONS` and the
    English from the two translation tables beside the model; a string missing
    from them is stored unreconciled and reported, which is the only honest answer
    for a category that postdates the code.

    ``ON CONFLICT DO NOTHING``, in **two statements**, because uniqueness is
    enforced by two partial indexes rather than one constraint: three fires in
    five have no specific cause, and in SQL two ``NULL``\\ s are not equal, so the
    rows that have one and the rows that do not need different conflict targets.
    See :mod:`src.providers.mexico_conafor.fire_cause`.

    Doing nothing on conflict also means an existing row is left alone rather than
    rewritten, so a reconciliation corrected by hand in the database survives the
    next import.
    """
    rows = session.execute(text(CAUSES_SQL.format(staging_table=staging_table))).all()
    if not rows:
        return 0

    values = []
    for cause, specific_cause in rows:
        canonical = CAUSE_NORMALISATIONS.get(mexico_conafor.normalise(cause))
        values.append({
            "cause": cause,
            "cause_normalised": canonical,
            "cause_en": CAUSE_TRANSLATIONS.get(canonical) if canonical else None,
            "specific_cause": specific_cause,
            "specific_cause_en": SPECIFIC_CAUSE_TRANSLATIONS.get(
                mexico_conafor.normalise(specific_cause)) if specific_cause else None,
        })

    unreconciled = sorted({entry["cause"] for entry in values
                           if entry["cause_normalised"] is None})
    if unreconciled:
        logger.warning("No canonical form for %d published cause(s), stored unreconciled: "
                       "%s. Add them to src.providers.mexico_conafor.fire_cause.",
                       len(unreconciled), ", ".join(repr(term) for term in unreconciled))
    untranslated = sorted({entry["specific_cause"] for entry in values
                           if entry["specific_cause"] and entry["specific_cause_en"] is None})
    if untranslated:
        logger.warning("No English for %d specific cause(s), stored untranslated: %s.",
                       len(untranslated), ", ".join(repr(term) for term in untranslated))

    paired = [entry for entry in values if entry["specific_cause"] is not None]
    unpaired = [entry for entry in values if entry["specific_cause"] is None]
    if paired:
        session.execute(
            pg_insert(ConaforFireCause.__table__).values(paired)
            .on_conflict_do_nothing(index_elements=["cause", "specific_cause"],
                                    index_where=text("specific_cause IS NOT NULL"))
        )
    if unpaired:
        session.execute(
            pg_insert(ConaforFireCause.__table__).values(unpaired)
            .on_conflict_do_nothing(index_elements=["cause"],
                                    index_where=text("specific_cause IS NULL"))
        )

    # Checked against the whole table rather than this layer's rows: a cause that
    # only ever appears in one year is still a hole in a fourteen-year series, and
    # this is the one place the whole catalogue is in view.
    stranded = session.execute(text(UNRECONCILED_CAUSES_SQL)).all()
    if stranded:
        logger.warning("%d published cause(s) in the catalogue have no canonical form "
                       "(%s). Their fires are stored, but a series grouped by "
                       "cause_normalised drops them into a NULL bucket.",
                       len(stranded),
                       ", ".join(f"{cause!r} x{count}" for cause, count in stranded))
    return len(values)


def layer_is_imported(session: Session, source_layer: str) -> bool:
    """Whether any row of this layer is already stored."""
    return session.scalar(
        text("SELECT EXISTS (SELECT 1 FROM conafor_wildfire WHERE source_layer = :source_layer)"),
        {"source_layer": source_layer},
    )


def delete_layer(session: Session, source_layer: str, logger: logging.Logger) -> None:
    """Remove everything a named layer imported before, children and parents."""
    result = session.execute(text(DELETE_LAYER_SQL), {"source_layer": source_layer})
    logger.info("Replacing layer %s: removed %d fire(s)", source_layer, result.rowcount)


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, source_layer: str, year: int,
              fid_column: str = "fid") -> int:
    """Map the staging table onto the model, returning the number of fires imported."""
    statement = TRANSFORM_SQL.format(staging_table=staging_table, fid_column=fid_column)
    return session.scalar(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply
        # finds nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": mexico_conafor.DEFAULT_TIME_ZONE,
        "source_layer": source_layer,
        "year": year,
        "precision_year": mexico_conafor.PRECISION_YEAR,
        "precision_day": mexico_conafor.PRECISION_DAY,
    })


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> int:
    """Import one archive in its own transaction, returning the fires imported.

    The already-imported check happens before ``ogr2ogr`` runs, not after: loading
    a staging table takes as long as the import itself and there is no point
    paying for it only to throw the result away.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    datasource, layer = common.shapefile_datasource(archive)
    year = layer_year(layer)
    log = ArchiveLogger(logger, {"archive": archive.name})

    with Session(engine) as session:
        already = layer_is_imported(session, layer)
    if already and not args.replace:
        log.info("Layer %s is already imported; skipping (pass --replace to load it again)",
                 layer)
        return 0

    started = time.monotonic()
    common.load_staging_table(
        datasource, layer, staging_table, args, common.resolve_database_settings(args), log,
        # The CRS the archives publish in, and the one the model stores. Forced
        # rather than assumed: all fourteen .prj files agree today, and an import
        # should not quietly depend on a fourteenth agreeing too.
        target_srs=f"EPSG:{mexico_conafor.SOURCE_SRID}",
        # The published field widths are enormous — Real (24.15) on every numeric
        # column — and GDAL renders a declared width as NUMERIC(width, scale). A
        # numeric(24,15) cannot hold a five-digit hectare figure, and the 2021
        # layer has fires of 19,102 ha, so the COPY fails outright without this.
        creation_options=["PRECISION=NO"],
    )

    with Session(engine) as session:
        if already:
            delete_layer(session, layer, log)

        normalise_staging_columns(session, staging_table, log)
        check_layer_year(session, staging_table, year, log)
        blank_missing_values(session, staging_table, log)
        normalise_staging_dates(session, staging_table, log)
        normalise_staging_vegetation(session, staging_table, log)
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes the staging table as if it held a handful of rows and
        # picks nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))

        staged = session.scalar(text(f"SELECT count(*) FROM {staging_table}"))
        causes = upsert_causes(session, staging_table, log)
        log.info("staged %d features for %d in %.0fs (%d cause classification(s)), now "
                 "mapping them onto the model", staged, year, time.monotonic() - started,
                 causes)

        imported = transform(session, provider_id, boundary_provider_id, staging_table,
                             layer, year)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        session.commit()

    if imported != staged:
        log.warning("%d of %d feature(s) were not imported: a feature is dropped when it "
                    "repeats another's CLAVEINC, or when its key is not of the published "
                    "form. A feature with no geometry or no burnt area is kept.",
                    staged - imported, staged)
    log.info("imported %d fires from %d features in %.0fs", imported, staged,
             time.monotonic() - started)
    return imported


def import_wildfires(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported."""
    archives = find_archives(args)
    common.require_tables(engine, ["wildfire", "conafor_wildfire", "conafor_fire_cause",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        check_time_zones(session, logger, mexico_conafor.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, mexico_conafor.PROVIDER_NAME, mexico_conafor.PROVIDER_PRODUCT,
            mexico_conafor.PROVIDER_FULL_NAME, mexico_conafor.PROVIDER_URL, logger,
        )
        boundary_provider = find_boundary_provider(session, logger)
        session.commit()
        # Read back after the commit: the objects are expired and the ids are what
        # every archive that follows actually needs.
        provider_id, boundary_provider_id = provider.id, (
            boundary_provider.id if boundary_provider is not None else None
        )

    started = time.monotonic()
    imported = 0
    logger.info("Importing %d archive(s)", len(archives))
    for index, archive in enumerate(archives, start=1):
        logger.info("[%d/%d] %s", index, len(archives), archive.name)
        imported += import_archive(archive, engine, args, provider_id,
                                   boundary_provider_id, logger)

    logger.info("Imported %d fires from %d archive(s) in %.0fs", imported, len(archives),
                time.monotonic() - started)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("conafor-import")

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
