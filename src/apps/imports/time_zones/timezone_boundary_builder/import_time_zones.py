#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import IANA time zone areas from the *timezone-boundary-builder* shapefile.

Loads the published polygons into
:class:`~src.data_model.geography.time_zone.TimeZone` rows, so that a coordinate
can be turned into an IANA zone name.

Why this table has to exist
---------------------------

The IANA time zone database — the thing behind ``zoneinfo`` and behind
PostgreSQL's ``AT TIME ZONE`` — defines a zone as a *name* with a history of
offsets and daylight-saving rules. It says nothing about where on Earth that
name applies. So neither Python nor PostgreSQL can answer "which zone is this
fire in?", and any provider that publishes local wall-clock time (GWIS, whose
dates are bare and mean local midnight) cannot be converted to an instant
without a set of polygons drawn by someone else.

*timezone-boundary-builder* is that someone: it derives the polygons from
OpenStreetMap and releases them once per IANA update. Download the shapefile
release — the ``with-oceans`` variant, so that a coordinate at sea still
resolves rather than coming back empty — from

    https://github.com/evansiroky/timezone-boundary-builder/releases

and run this once::

    python3 -m src.apps.imports.time_zones.timezone_boundary_builder.import_time_zones \\
        -s timezones-with-oceans.shapefile.zip

The zip is read in place; nothing is unpacked. Re-running it upgrades the table
to a newer release: rows are matched by zone name and their geometry replaced,
which is what makes this safe to repeat when IANA splits or merges a zone.

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

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common

#: Where the release can be downloaded, quoted back at the user when the file
#: they passed is not there.
RELEASES_URL = "https://github.com/evansiroky/timezone-boundary-builder/releases"

#: Name of the attribute holding the IANA zone name. Overridable, but it has been
#: ``tzid`` in every release so far.
DEFAULT_TZID_FIELD = "tzid"

DEFAULT_STAGING_TABLE = "tzbb_time_zones"

#: Maps the staging table onto :class:`~src.data_model.geography.time_zone.TimeZone`.
#:
#: Grouped by zone name because nothing guarantees one feature per zone: the
#: ``with-oceans`` build in particular splits some maritime zones into several
#: bands. ``ST_Collect`` rather than ``ST_Union`` — the parts of a zone are
#: disjoint by construction, so there is nothing to dissolve, and collecting them
#: costs a fraction of what unioning polygons this large would.
#:
#: ``ST_CollectionExtract(..., 3)`` and not ``ST_Multi``: collecting geometries
#: that are *already* multipolygons nests them, so ``ST_Collect`` hands back a
#: ``GEOMETRYCOLLECTION``, which ``ST_Multi`` does not flatten and the column
#: rejects. Extracting the polygons (type 3) pulls every ring back up into one
#: ``MULTIPOLYGON``, whether the group had one feature or twenty.
#:
#: ``DO UPDATE`` rather than ``DO NOTHING``: unlike a boundary import, re-running
#: this one is how the table is *upgraded* to a newer IANA release, and a zone
#: whose area changed must end up with the new geometry.
TRANSFORM_SQL = """
INSERT INTO time_zone (name, geometry)
SELECT staging.{tzid_field}, ST_CollectionExtract(ST_Collect(staging.geom), 3)
FROM {staging_table} AS staging
WHERE staging.{tzid_field} IS NOT NULL
GROUP BY staging.{tzid_field}
ON CONFLICT (name) DO UPDATE
    SET geometry = EXCLUDED.geometry, updated_at = now()
RETURNING id
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import timezone-boundary-builder time zone areas into GisFIRE.",
        epilog=f"Download the shapefile release from {RELEASES_URL} (prefer the "
               f"'with-oceans' variant). Database settings not given here are read "
               f"from the environment (.env).",
    )
    parser.add_argument("-s", "--shapefile", required=True, type=Path,
                        help="the release .zip, a directory holding the shapefile, or the .shp")
    parser.add_argument("--tzid-field", default=DEFAULT_TZID_FIELD,
                        help=f"attribute holding the IANA zone name (default: {DEFAULT_TZID_FIELD})")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def transform(session: Session, staging_table: str, tzid_field: str,
              logger: logging.Logger) -> int:
    """Map the staging table onto the model, returning the number of zones written."""
    result = session.execute(
        text(TRANSFORM_SQL.format(staging_table=staging_table, tzid_field=tzid_field))
    )
    imported = len(result.all())
    logger.info("Imported %d time zones", imported)
    return imported


def import_time_zones(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the zones written.

    The staging load happens outside the transaction — ``ogr2ogr`` opens its own
    connection and commits by itself — but everything that touches the model runs
    inside one, so a failure half way through leaves no partial import behind.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    datasource, layer = common.shapefile_datasource(args.shapefile)

    common.create_staging_schema(engine, args.staging_schema)
    common.load_staging_table(datasource, layer, staging_table, args,
                              common.resolve_database_settings(args), logger)

    with Session(engine) as session:
        imported = transform(session, staging_table, args.tzid_field, logger)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, logger)
        session.commit()

    if args.keep_staging:
        logger.info("Staging table %s kept", staging_table)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("time-zone-import")

    if not args.shapefile.exists():
        logger.error("Shapefile not found: %s. Download the release from %s",
                     args.shapefile, RELEASES_URL)
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
        import_time_zones(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
