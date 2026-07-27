#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import ICNF burnt area polygons for Portugal.

Loads the published *áreas ardidas* archives into
:class:`~src.providers.icnf.wildfire.IcnfWildfire` rows — the generic columns in
``wildfire``, the ICNF ones in ``icnf_wildfire`` — and the fire cause
classification into :class:`~src.providers.icnf.fire_cause.IcnfFireCause`.

The ICNF publishes one zipped shapefile per layer, so point the import at the
directory they were downloaded into::

    python3 -m src.apps.imports.wildfires.portugal_icnf.import_wildfires -d /path/to/portugal/

or at one archive::

    python3 -m src.apps.imports.wildfires.portugal_icnf.import_wildfires -s ardida_2024.zip

Each archive is imported in its own transaction, so a layer is either wholly in
or wholly out and a failure on the fifteenth does not throw away the fourteen
before it.

The attributes change half way through the dataset
--------------------------------------------------

This is the whole difficulty of the source, and it is handled in one place. The
layers from 1975 to 2013 publish two attributes — the year and the burnt area —
and those from 2014 on publish twenty-two. Rather than write two mappings, or
branch on the year, the import **normalises the staging table**: after
``ogr2ogr`` has loaded whatever the file holds,
:func:`normalise_staging_columns` brings it to :data:`STAGING_COLUMNS`, adding
every attribute the file did not have as an empty column and converting every one
it landed in a type the mapping cannot read.

One mapping then covers both eras, and a layer that publishes less simply leaves
more of it ``NULL``. It also means that a future layer dropping an attribute, or
one of the 2022-2023 layers carrying the extra GeoServer ``id`` this import
ignores, changes nothing here.

Dates: what the archives can and cannot say
-------------------------------------------

``DH_Inicio``, ``DH_1Interv``, ``DH_Fim`` and ``Edicao`` are ``xsd:dateTime`` at
the source, but a shapefile's DBF has no datetime type and the ``SHAPE-ZIP``
export truncated all four **to dates**. This import stores what survived — the
date, resolved to local midnight against the time zone the polygon falls in, the
same instant-plus-zone rule as every other importer (see
:mod:`src.data_model.wildfire`) — and records
``date_time_precision = 'day'`` to say so.

A layer with no dates at all gets ``start_date_time`` at local midnight on the
**1st of January of its year** and ``date_time_precision = 'year'``. That is a
placeholder satisfying a ``NOT NULL`` column, not a claim about the fire, and the
precision column is what stops it being read as one.

Neither is fixed up by asking the WFS: putting the times back on the 19,575 dated
fires — and checking the 48,860 that carry none — is a separate job against a
separate source, and doing it inside a bulk import would put tens of thousands of
requests onto the ICNF's server for data that is already sitting on disk.

The geometry is stored twice
----------------------------

``ogr2ogr`` loads the polygons in the CRS they were published in, EPSG:3763, and
the mapping keeps them: the repaired polygon goes into
``icnf_wildfire.perimeter_etrs89_tm06`` and its ``ST_Transform`` to EPSG:4326 into
``wildfire.perimeter``. Deriving the second from the first, rather than loading
each separately, is what guarantees the two are the same geometry.

Roughly one polygon in a hundred is invalid as published — 179 of the 12,654 in
``ardida_1975_1989`` — so they go through ``ST_MakeValid`` first, before either is
stored.

Re-running an import
--------------------

48,861 of the 68,435 features publish no identifier of any kind, so there is no
row-level "have I seen this before". Re-running is therefore controlled a layer
at a time: a layer already in the database is **skipped**, and ``--replace``
deletes what it loaded before importing it again. That second form is what to use
when the ICNF revises a published year, which it does — fires of 2024 carry
``Edicao`` dates into March 2025.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency,
not a Python package.
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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers import icnf
from src.providers.icnf.fire_cause import DESCRIPTION_TRANSLATIONS
from src.providers.icnf.fire_cause import IcnfFireCause
from src.providers.icnf.fire_cause import TYPE_TRANSLATIONS

# The plumbing every wildfire importer shares, re-exported so this module reads
# as one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401

DEFAULT_STAGING_TABLE = "icnf_burnt_areas"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Every attribute the mapping reads, with the PostgreSQL type it needs, named as
#: ``ogr2ogr`` lands it — lower-cased, which is what its ``LAUNDER`` default does
#: to ``Cod_SGIF`` and ``PI_DICOFRE``.
#:
#: This is the list :func:`normalise_staging_columns` fills in, so it is also the
#: authoritative statement of what this import understands. The order is the
#: published one, which is worth keeping: it makes the list checkable against
#: ``ogrinfo -so`` on an archive.
#:
#: The type is what the mapping needs to read, which is not always what
#: ``ogr2ogr`` produces — see :data:`COMPATIBLE_TYPES` and
#: :func:`normalise_staging_columns`, which bring the loaded table to this.
STAGING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cod_sgif", "text"),
    ("cod_anepc", "text"),
    ("ano", "integer"),
    ("dh_inicio", "date"),
    ("dh_1interv", "date"),
    ("dh_fim", "date"),
    ("duracao_m", "integer"),
    ("pi_dicofre", "text"),
    ("pi_nuts3", "text"),
    ("pi_distrit", "text"),
    ("pi_conc", "text"),
    ("pi_freg", "text"),
    ("pi_local", "text"),
    ("causa_cod", "text"),
    ("causa_tipo", "text"),
    ("causa_desc", "text"),
    ("areahasig", "double precision"),
    ("areahasgif", "double precision"),
    ("areahapov", "double precision"),
    ("areahamato", "double precision"),
    ("areahaagri", "double precision"),
    ("edicao", "date"),
)

#: The loaded types each declared type will accept without a conversion, by
#: ``information_schema.data_type`` name.
#:
#: What ``ogr2ogr`` lands is not what the shapefile's own field types suggest, and
#: it varies with the layer:
#:
#: * GDAL's PostgreSQL driver renders any field that declares a width as
#:   ``NUMERIC(width, scale)``, so ``Ano: Integer (9.0)`` arrives as
#:   ``numeric(9,0)`` — and ``make_date`` has no ``numeric`` overload, so reading
#:   it needs the column converted, not cast at every use.
#: * a date field every one of whose values is empty cannot be recognised as a
#:   date at all and arrives as ``character varying``, which happens in practice:
#:   the 2014-2025 layers publish ``DH_Inicio`` for most fires, but a layer whose
#:   fires are all unmatched would publish it for none.
#:
#: Numbers are the permissive case — ``numeric`` is a perfectly good
#: ``double precision`` for reading — and dates the strict one, because nothing
#: except a ``date`` can be given to ``COALESCE`` beside another ``date``.
COMPATIBLE_TYPES: dict[str, frozenset[str]] = {
    "text": frozenset({"text", "character varying", "character"}),
    "integer": frozenset({"integer", "smallint", "bigint"}),
    "double precision": frozenset({"double precision", "real", "numeric",
                                   "integer", "smallint", "bigint"}),
    "date": frozenset({"date"}),
}

#: The distinct cause classifications a layer uses. Around seventy per layer and
#: 101 over the whole dataset, so this is read into Python and translated there
#: rather than carrying a twenty-nine row translation table into SQL.
CAUSES_SQL = """
SELECT DISTINCT causa_cod, causa_tipo, causa_desc
FROM {staging_table}
WHERE causa_cod IS NOT NULL AND causa_tipo IS NOT NULL AND causa_desc IS NOT NULL
ORDER BY causa_cod
"""

#: Cause codes that name more than one classification, once this layer's have been
#: stored. Reported rather than prevented — it is the provider's data, and both
#: meanings are real — but it is worth knowing about, because a report that groups
#: fires by ``Causa_Cod`` rather than by ``cause_id`` will merge them.
REDEFINED_CAUSES_SQL = """
SELECT code, count(*) AS meanings
FROM icnf_fire_cause
GROUP BY code
HAVING count(*) > 1
ORDER BY code
"""

#: Deletes everything a named layer imported before, parent rows included.
#:
#: The child rows go first, in a data-modifying CTE whose ``RETURNING`` feeds the
#: parent delete — ``icnf_wildfire.id`` references ``wildfire.id``, so the parents
#: cannot go until the children have, and doing both in one statement means there
#: is no window in which the parents are orphaned.
DELETE_LAYER_SQL = """
WITH removed_child AS (
    DELETE FROM icnf_wildfire WHERE source_layer = :source_layer RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Maps one staging table onto the two tables of the model in a single statement.
#:
#: One published feature becomes one fire: a ``wildfire`` row and its
#: ``icnf_wildfire`` child. There is no grouping, unlike the GFA import — a
#: multipart burn is published here as one ``MultiPolygon`` feature rather than as
#: several features sharing an identifier, and ``Cod_SGIF`` never repeats within a
#: layer.
#:
#: The primary key is drawn from the sequence up front, in ``source``, because the
#: child insert has to know its parent's id and ``RETURNING`` would come too late.
#:
#: ``repaired`` does the geometry work once. ``ST_MakeValid`` fixes the ~1% of
#: published polygons that self-intersect, ``ST_CollectionExtract(..., 3)``
#: flattens what the repair can leave as a ``GEOMETRYCOLLECTION`` back into a
#: ``MULTIPOLYGON``, and only then is the EPSG:4326 copy derived — so the two
#: stored geometries are the same geometry in two CRSs, not two separate
#: computations that could disagree.
#:
#: ``located`` resolves the zone and the country from a point *on* the perimeter
#: (``ST_PointOnSurface``, which unlike a centroid is guaranteed to be inside it).
#: Both are ``LEFT JOIN``\\ s: a fire outside every imported boundary keeps its
#: dates and its geometry and simply has no country.
#:
#: The date rules are the whole point of the ``COALESCE`` on ``dh_inicio``: a
#: layer that publishes a start date gets it at local midnight and is marked
#: ``day``; one that publishes none gets the 1st of January of ``ano`` and is
#: marked ``year``. The end is the last second of its day, as in the GFA import,
#: which is the closest a date-only value can come to "some time that day".
TRANSFORM_SQL = """
WITH source AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           staging.*
    FROM {staging_table} AS staging
    WHERE staging.geom IS NOT NULL
      AND staging.ano IS NOT NULL
      AND staging.areahasig IS NOT NULL
),
repaired AS MATERIALIZED (
    SELECT source.*,
           ST_CollectionExtract(ST_MakeValid(source.geom), 3) AS perimeter_source
    FROM source
),
projected AS MATERIALIZED (
    SELECT repaired.*,
           ST_Transform(repaired.perimeter_source, 4326) AS perimeter,
           ST_PointOnSurface(ST_Transform(repaired.perimeter_source, 4326)) AS locator
    FROM repaired
    WHERE NOT ST_IsEmpty(repaired.perimeter_source)
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
           'icnf_wildfire',
           :provider_id,
           (COALESCE(located.dh_inicio, make_date(located.ano, 1, 1))::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           CASE WHEN located.dh_fim IS NULL THEN NULL
                ELSE (located.dh_fim::timestamp + interval '23:59:59')
                     AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone) END,
           located.time_zone,
           located.perimeter,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO icnf_wildfire (id, source_layer, sgif_code, anepc_code, year,
                               date_time_precision, first_response_date_time,
                               duration_minutes, dicofre_code, nuts3_name, district_name,
                               municipality_name, parish_name, place_name, cause_id,
                               area_ha_gis, area_ha_sgif, area_ha_forest_stand,
                               area_ha_shrubland, area_ha_agricultural, edition_date_time,
                               perimeter_etrs89_tm06)
    SELECT located.wildfire_id,
           :source_layer,
           located.cod_sgif,
           located.cod_anepc,
           located.ano,
           CASE WHEN located.dh_inicio IS NULL THEN :precision_year ELSE :precision_day END,
           CASE WHEN located.dh_1interv IS NULL THEN NULL
                ELSE (located.dh_1interv::timestamp)
                     AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone) END,
           located.duracao_m,
           located.pi_dicofre,
           located.pi_nuts3,
           located.pi_distrit,
           located.pi_conc,
           located.pi_freg,
           located.pi_local,
           cause.id,
           located.areahasig,
           located.areahasgif,
           located.areahapov,
           located.areahamato,
           located.areahaagri,
           CASE WHEN located.edicao IS NULL THEN NULL
                ELSE (located.edicao::timestamp)
                     AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone) END,
           located.perimeter_source
    FROM located
    JOIN ins_wildfire ON ins_wildfire.id = located.wildfire_id
    -- On the whole triple, not on the code: four codes name two different causes
    -- each, and joining on the code alone would give a 2025 fire the meaning its
    -- code had until 2024. See src.providers.icnf.fire_cause.
    LEFT JOIN icnf_fire_cause AS cause
           ON cause.code = located.causa_cod
          AND cause.type = located.causa_tipo
          AND cause.description = located.causa_desc
    RETURNING id
)
SELECT count(*) FROM written
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import ICNF burnt area polygons for Portugal into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Database settings not given here "
               "are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published archives, one per layer")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single .zip, .shp or directory to import instead of a whole set")

    parser.add_argument("--replace", action="store_true",
                        help="re-import a layer already in the database, deleting what it "
                             "loaded before. Use this when the ICNF revises a published "
                             "year; without it an already-imported layer is skipped")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_archives(args: argparse.Namespace) -> list[Path]:
    """List the layers to import, sorted, so the years go in in order.

    Sorting puts the three multi-year layers first — ``ardida_1975_1989``,
    ``ardida_1990_1999``, ``ardida_2000_2008`` sort before ``ardida_2009`` — which
    is the published chronology.

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


def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.Logger) -> tuple[list[str], list[str]]:
    """Bring the loaded table to :data:`STAGING_COLUMNS`, in name and in type.

    This is what lets one mapping read both eras of the dataset, and it does two
    things:

    **Adds what the layer does not publish.** A 1975-2013 layer publishes ``Ano``
    and ``AreaHaSIG`` and nothing else, so twenty of the :data:`STAGING_COLUMNS`
    are created here and stay ``NULL`` all the way into the model.

    **Converts what it publishes in the wrong type.** ``ogr2ogr`` does not land
    the types the shapefile's own field list suggests, and what it lands changes
    with the contents of the layer (see :data:`COMPATIBLE_TYPES`). Converting the
    column once is better than casting it at every use: a cast in the mapping
    would have to be right for every type the column could arrive as, and would
    be wrong for exactly the layer nobody tested.

    The empty string is treated as ``NULL`` on the way, which is what an unset
    text field can arrive as and what no other type would accept.

    Returns
    -------
    tuple of (list of str, list of str)
        The columns that had to be added — the attributes this layer does not
        publish — and those that had to be converted, both in declaration order.
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
        logger.info("Layer does not publish %d of the %d known attributes (%s)",
                    len(added), len(STAGING_COLUMNS), ", ".join(added))
    if converted:
        logger.debug("Converted %d staged column(s) to the type the mapping reads: %s",
                     len(converted), ", ".join(converted))
    return added, converted


def upsert_causes(session: Session, staging_table: str, logger: logging.Logger) -> int:
    """Store the cause classifications this layer uses, returning how many it has.

    The classification is not seeded from a fixed list — it is whatever the layer
    actually contains — so a classification the ICNF adds arrives with the first
    fire that uses it. The English comes from the translation tables beside the
    model; a string missing from them is stored with no translation and reported,
    which is the only honest answer for a category that postdates the code.

    ``ON CONFLICT DO NOTHING`` on the whole ``(code, type, description)`` triple,
    which is the natural key: the same classification appears in every layer, so
    all but the first import of it is a no-op. Conflicting on the code alone would
    be wrong — the ICNF has reused four of them for different causes — and would
    quietly drop the newer meaning. It also means an existing row is left alone
    rather than rewritten, so a translation added by hand to the database survives
    the next import.
    """
    rows = session.execute(text(CAUSES_SQL.format(staging_table=staging_table))).all()
    if not rows:
        return 0

    values = [
        {"code": code, "type": type_pt, "description": description_pt,
         "type_en": TYPE_TRANSLATIONS.get(type_pt),
         "description_en": DESCRIPTION_TRANSLATIONS.get(description_pt)}
        for code, type_pt, description_pt in rows
    ]

    untranslated = sorted(
        {entry["type"] for entry in values if entry["type_en"] is None}
        | {entry["description"] for entry in values if entry["description_en"] is None}
    )
    if untranslated:
        logger.warning("No English for %d cause term(s), stored untranslated: %s. "
                       "Add them to src.providers.icnf.fire_cause.",
                       len(untranslated), ", ".join(repr(term) for term in untranslated))

    session.execute(
        pg_insert(IcnfFireCause.__table__).values(values)
        .on_conflict_do_nothing(constraint="uq_icnf_fire_cause_code_type_description")
    )

    # Checked after the insert, and against the whole table rather than this
    # layer's rows, because the interesting case spans layers: 127 meant one thing
    # from 2014 to 2024 and another in 2025, which no single layer reveals.
    redefined = session.execute(text(REDEFINED_CAUSES_SQL)).all()
    if redefined:
        logger.warning("%d cause code(s) name more than one classification (%s). Both "
                       "meanings are stored and each fire links to its own, but grouping "
                       "fires by Causa_Cod rather than by cause_id would merge them.",
                       len(redefined),
                       ", ".join(f"{code} x{meanings}" for code, meanings in redefined))
    return len(values)


def layer_is_imported(session: Session, source_layer: str) -> bool:
    """Whether any row of this layer is already stored."""
    return session.scalar(
        text("SELECT EXISTS (SELECT 1 FROM icnf_wildfire WHERE source_layer = :source_layer)"),
        {"source_layer": source_layer},
    )


def delete_layer(session: Session, source_layer: str, logger: logging.Logger) -> None:
    """Remove everything a named layer imported before, children and parents."""
    result = session.execute(text(DELETE_LAYER_SQL), {"source_layer": source_layer})
    logger.info("Replacing layer %s: removed %d fire(s)", source_layer, result.rowcount)


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, source_layer: str) -> int:
    """Map the staging table onto the model, returning the number of fires imported."""
    statement = TRANSFORM_SQL.format(staging_table=staging_table)
    return session.scalar(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply
        # finds nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": icnf.DEFAULT_TIME_ZONE,
        "source_layer": source_layer,
        "precision_year": icnf.PRECISION_YEAR,
        "precision_day": icnf.PRECISION_DAY,
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
        # The published CRS, kept rather than converted: the model stores the
        # polygon in it as well as in EPSG:4326, and the 4326 one is derived from
        # it in SQL so that the two provably agree.
        target_srs=f"EPSG:{icnf.SOURCE_SRID}",
        # Without this every accented Portuguese name is silently mangled: the
        # archives carry a .cst file, which GDAL does not read, and no .cpg,
        # which it does.
        open_options=[f"ENCODING={icnf.SOURCE_ENCODING}"],
    )

    with Session(engine) as session:
        if already:
            delete_layer(session, layer, log)

        normalise_staging_columns(session, staging_table, log)
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes the staging table as if it held a handful of rows and
        # picks nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))

        staged = session.scalar(text(f"SELECT count(*) FROM {staging_table}"))
        causes = upsert_causes(session, staging_table, log)
        log.info("staged %d features in %.0fs (%d cause classification(s)), now mapping them "
                 "onto the model", staged, time.monotonic() - started, causes)

        imported = transform(session, provider_id, boundary_provider_id, staging_table, layer)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        session.commit()

    if imported != staged:
        log.warning("%d of %d feature(s) were not imported: a feature with no geometry, no "
                    "year or no area cannot be stored, and neither can one whose polygon the "
                    "repair reduced to nothing", staged - imported, staged)
    log.info("imported %d fires from %d features in %.0fs", imported, staged,
             time.monotonic() - started)
    return imported


def import_wildfires(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported."""
    archives = find_archives(args)
    common.require_tables(engine, ["wildfire", "icnf_wildfire", "icnf_fire_cause",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        check_time_zones(session, logger, icnf.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, icnf.PROVIDER_NAME, icnf.PROVIDER_PRODUCT,
            icnf.PROVIDER_FULL_NAME, icnf.PROVIDER_URL, logger,
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
    logger = logging.getLogger("icnf-import")

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
