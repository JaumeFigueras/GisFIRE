#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import Global Fire Atlas fire perimeters.

Loads the published perimeter shapefiles into
:class:`~src.providers.gfa.wildfire.GfaWildfire` rows — one per fire, with the
generic columns in ``wildfire`` and the GFA measurements in ``gfa_wildfire``.

The Atlas ships one shapefile per year, not zipped, in a single directory::

    python3 -m src.apps.imports.wildfires.gfa.import_wildfires -d /path/to/SHP_perimeters/

Each file is imported in its own transaction: a year is either wholly in or
wholly out, and a failure on the fifteenth file does not throw away the fourteen
before it.

Three things about this dataset shape the mapping
-------------------------------------------------

**One fire is several features.** The shapefiles have geometry type ``Polygon``,
so a fire whose burnt area is in several pieces is published as several features
sharing one ``fire_ID`` and repeating every attribute — the same ignition point,
the same ``size``, the same dates. The import groups by ``fire_ID`` and collects
the parts into one ``MULTIPOLYGON``, which is what makes ``size`` mean what it
says and leaves the identifier a genuine key. Summing ``size`` over ungrouped
features would double-count.

**``fire_ID`` is unique, and used as one.** It carries the year — ``2xxxxxxx``
for 2002 through ``26xxxxxxx`` for 2026 — so it does not collide between files.
The import therefore *skips* fires it already holds, and re-running it is a no-op
rather than a second copy. This is the opposite of
:mod:`~src.apps.imports.wildfires.gwis.import_wildfires`, whose identifier names
genuinely different fires when it repeats and which consequently cannot skip
anything.

**About one perimeter in six is invalid.** The polygons are traced from MODIS
pixels and self-intersect at the corners where the trace doubles back. They are
repaired with ``ST_MakeValid`` on the way in, so that everything downstream — the
country join here, area computations later — is safe. The repair can turn a
bowtie into two polygons, hence the ``ST_CollectionExtract``.

Dates and country
-----------------

``start_date`` and ``end_date`` are bare ``yyyy-mm-dd`` strings meaning local
midnight, exactly as GWIS publishes them, so the same rule applies: they are
resolved to instants against the time zone the fire is in and the zone is kept
alongside as provenance (see :mod:`src.data_model.wildfire`).

Both the zone and the country come from the **ignition point**, built from the
published ``lat``/``lon``. That is cheaper than intersecting the perimeter, never
ambiguous for a fire that straddles a border, and is the fire's own reported
origin rather than something derived from its shape. It does differ from the GWIS
importer, which attributes a fire to the country holding the largest share of its
perimeter.

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
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers import gfa

# The plumbing every wildfire importer shares, re-exported so this module reads
# as one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import FALLBACK_TIME_ZONE  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401

#: Attributes whose names the importer needs to know. Overridable, because a
#: future release of the Atlas could rename them, and a rename would otherwise
#: mean editing the SQL. The rest are read positionally by name in
#: :data:`TRANSFORM_SQL` and are not worth an option each.
DEFAULT_ID_FIELD = "fire_id"
DEFAULT_START_FIELD = "start_date"
DEFAULT_END_FIELD = "end_date"

DEFAULT_STAGING_TABLE = "gfa_perimeters"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Maps one staging table onto the two tables of the model in a single statement.
#:
#: Reading it from the bottom up: the last two inserts are the joined-inheritance
#: split — the generic columns into ``wildfire``, the GFA measurements into
#: ``gfa_wildfire`` — and everything above them works out what to put in them.
#:
#: ``source`` is where one fire becomes one row. It groups by ``fire_ID`` and
#: aggregates with ``min()``, which is not a choice about *which* value to keep:
#: the parts of a fire repeat every attribute identically, so any aggregate
#: returns the same answer and ``min()`` is simply the cheapest way to say "the
#: value they all share". The geometry is the exception, and the reason the
#: grouping exists at all — ``ST_Collect`` gathers the parts and ``ST_MakeValid``
#: repairs the self-intersections MODIS pixel tracing leaves behind.
#: ``ST_CollectionExtract(..., 3)`` then flattens the result, which the repair
#: can leave as a ``GEOMETRYCOLLECTION``, back into one ``MULTIPOLYGON``.
#:
#: The ``NOT EXISTS`` is what makes re-running the import a no-op. It is an
#: index-backed probe per staging row against the unique ``gfa_id``, and it sits
#: in ``WHERE`` rather than in an ``ON CONFLICT`` because the identifier lives on
#: the child table while the insert that would conflict is on the parent.
#:
#: The primary keys are drawn from the sequence up front rather than being
#: generated by the insert, for the same reason as in the GWIS importer: the
#: child insert needs them, and ``RETURNING`` cannot hand them back correlated to
#: anything the child could join on.
TRANSFORM_SQL = """
WITH source AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS id,
           staging.{id_field}                                   AS gfa_id,
           NULLIF(min(staging.{start_field}), '')               AS start_date,
           NULLIF(min(staging.{end_field}), '')                 AS end_date,
           ST_SetSRID(ST_MakePoint(min(staging.lon), min(staging.lat)), 4326) AS ignition_point,
           ST_CollectionExtract(ST_MakeValid(ST_Collect(staging.geom)), 3)    AS perimeter,
           min(staging.size)        AS size_km2,
           min(staging.perimeter)   AS perimeter_km,
           min(staging.duration)    AS duration_days,
           min(staging.fire_line)   AS fire_line_km,
           min(staging.spread)      AS spread_km2_day,
           min(staging.speed)       AS speed_km_day,
           min(staging.direction)   AS direction,
           min(staging.direc_frac)  AS direction_fraction,
           min(staging.modis_tile)  AS modis_tile,
           min(staging.landcover)   AS landcover,
           min(staging.landc_frac)  AS landcover_fraction,
           min(staging.gfed_regio)  AS gfed_region
    FROM {staging_table} AS staging
    WHERE staging.{id_field} IS NOT NULL
      AND NULLIF(staging.{start_field}, '') IS NOT NULL
      AND staging.geom IS NOT NULL
      AND staging.lat IS NOT NULL
      AND staging.lon IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM gfa_wildfire AS already WHERE already.gfa_id = staging.{id_field}
      )
    GROUP BY staging.{id_field}
),
-- The zone and the country of the ignition point, in one pass over the fires.
-- Both are LEFT JOINs: a fire at sea or outside every imported boundary keeps
-- its perimeter and its dates and simply has no country.
located AS MATERIALIZED (
    SELECT source.*, zone.name AS time_zone, country.id AS admin_boundary_id
    FROM source
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry, source.ignition_point)
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry, source.ignition_point)
        LIMIT 1
    ) AS country ON TRUE
),
inserted AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT located.id,
           'gfa_wildfire',
           :provider_id,
           (located.start_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           (located.end_date::timestamp + interval '23:59:59')
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           located.time_zone,
           -- ST_MakeValid can reduce a degenerate trace to nothing. An empty
           -- multipolygon would satisfy the column and mean less than NULL does.
           CASE WHEN ST_IsEmpty(located.perimeter) THEN NULL ELSE located.perimeter END,
           located.admin_boundary_id
    FROM located
    RETURNING id
),
written AS (
    INSERT INTO gfa_wildfire (id, gfa_id, ignition_point, size_km2, perimeter_km,
                              duration_days, fire_line_km, spread_km2_day, speed_km_day,
                              direction, direction_fraction, modis_tile, landcover,
                              landcover_fraction, gfed_region)
    SELECT located.id, located.gfa_id, located.ignition_point, located.size_km2,
           located.perimeter_km, located.duration_days, located.fire_line_km,
           located.spread_km2_day, located.speed_km_day, located.direction,
           located.direction_fraction, located.modis_tile, located.landcover,
           located.landcover_fraction, located.gfed_region
    FROM located JOIN inserted ON inserted.id = located.id
    RETURNING id
)
SELECT count(*) FROM written
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import Global Fire Atlas fire perimeters into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Database settings not given here "
               "are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published shapefiles, one per year")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single .shp, .zip or directory to import instead of a whole set")

    fields = parser.add_argument_group("layer", "attribute names, should the dataset rename them")
    fields.add_argument("--id-field", default=DEFAULT_ID_FIELD,
                        help=f"attribute holding the fire id (default: {DEFAULT_ID_FIELD})")
    fields.add_argument("--start-field", default=DEFAULT_START_FIELD,
                        help=f"attribute holding the start date (default: {DEFAULT_START_FIELD})")
    fields.add_argument("--end-field", default=DEFAULT_END_FIELD,
                        help=f"attribute holding the end date (default: {DEFAULT_END_FIELD})")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_shapefiles(args: argparse.Namespace) -> list[Path]:
    """List the files to import, sorted, so the years go in in order.

    The Atlas publishes loose shapefiles rather than one archive per year, so a
    directory holds ``.shp`` files directly. Zips are accepted too, since the
    download itself is one and importing it without unpacking is useful.

    Raises
    ------
    RuntimeError
        If the directory holds no shapefile at all — far more likely a wrong path
        than an empty download, and silently importing nothing would hide it.
    """
    if args.directory is None:
        return [args.shapefile]

    found = sorted([*args.directory.glob("*.shp"), *args.directory.glob("*.zip")])
    if not found:
        raise RuntimeError(f"{args.directory} holds no .shp or .zip file")
    return found


def warn_if_already_imported(session: Session, logger: logging.Logger) -> int:
    """Report how many GFA fires are already stored, returning the count.

    Not a refusal: ``fire_ID`` is unique, so the import skips what it already has
    and adding a newly published year to a database that holds the earlier ones
    is the normal way to use this. The count is logged so that a re-run reporting
    zero imported reads as "nothing new" rather than as a failure.
    """
    already = session.scalar(text("SELECT count(*) FROM gfa_wildfire")) or 0
    if already:
        logger.info("%d GFA fires already stored; those will be skipped", already)
    return already


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, args: argparse.Namespace, logger: logging.Logger) -> int:
    """Map the staging table onto the model, returning the number of fires imported.

    The count is computed by the statement itself rather than by counting the ids
    it returns: a year's file is the better part of a million fires, and pulling
    that many ids back only to call ``len`` on them would cost more memory than
    the import.
    """
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        id_field=args.id_field,
        start_field=args.start_field,
        end_field=args.end_field,
    )
    return session.scalar(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply
        # finds nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": FALLBACK_TIME_ZONE,
    })


def import_shapefile(shapefile: Path, engine: Engine, args: argparse.Namespace,
                     provider_id: int, boundary_provider_id: int | None,
                     logger: logging.Logger) -> int:
    """Import one shapefile in its own transaction, returning the fires imported."""
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    datasource, layer = common.shapefile_datasource(shapefile)
    log = ArchiveLogger(logger, {"archive": shapefile.name})

    started = time.monotonic()
    common.load_staging_table(datasource, layer, staging_table, args,
                              common.resolve_database_settings(args), log)

    with Session(engine) as session:
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes a million-row staging table as if it held a handful and
        # picks nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))

        staged = session.scalar(text(f"SELECT count(*) FROM {staging_table}"))
        log.info("staged %d features in %.0fs, now mapping them onto the model",
                 staged, time.monotonic() - started)

        imported = transform(session, provider_id, boundary_provider_id, staging_table, args, log)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        session.commit()

    log.info("imported %d fires from %d features in %.0fs", imported, staged,
             time.monotonic() - started)
    return imported


def import_wildfires(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported."""
    shapefiles = find_shapefiles(args)
    common.require_tables(engine, ["wildfire", "gfa_wildfire", "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        check_time_zones(session, logger)
        provider = common.get_or_create_data_provider(
            session, gfa.PROVIDER_NAME, gfa.PROVIDER_PRODUCT,
            gfa.PROVIDER_FULL_NAME, gfa.PROVIDER_URL, logger,
        )
        warn_if_already_imported(session, logger)
        boundary_provider = find_boundary_provider(session, logger)
        session.commit()
        # Read back after the commit: the objects are expired and the ids are
        # what every file that follows actually needs.
        provider_id, boundary_provider_id = provider.id, (
            boundary_provider.id if boundary_provider is not None else None
        )

    started = time.monotonic()
    imported = 0
    logger.info("Importing %d shapefile(s)", len(shapefiles))
    for index, shapefile in enumerate(shapefiles, start=1):
        logger.info("[%d/%d] %s", index, len(shapefiles), shapefile.name)
        imported += import_shapefile(shapefile, engine, args, provider_id,
                                     boundary_provider_id, logger)

    logger.info("Imported %d fires from %d shapefile(s) in %.0fs", imported, len(shapefiles),
                time.monotonic() - started)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("gfa-import")

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
