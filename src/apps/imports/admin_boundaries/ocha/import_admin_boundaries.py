#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import OCHA international boundaries from a GeoPackage.

Loads the *Global International Boundaries (OSM)* layer
(https://data.humdata.org/dataset/global-international-boundaries-osm) into
:class:`~src.providers.ocha.admin_boundary.OchaAdminBoundary` rows, as
administrative level 0.

The import runs in two stages. ``ogr2ogr`` copies the layer verbatim into a
staging table, then a single SQL statement maps that table onto the two tables of
the model. Splitting it this way leaves every part GDAL is better at than we are
— GeoPackage parsing, polygon promotion, coordinate transformation, invalid
geometries — to GDAL, and keeps what we write down to column-to-column SQL.

The mapping cannot be done by ``ogr2ogr`` alone: joined table inheritance splits
one feature across ``admin_boundary`` and ``ocha_admin_boundary``, which share a
primary key the database only assigns on insert, and ``ogr2ogr`` writes a single
table.

Run it with::

    python3 -m src.apps.imports.admin_boundaries.ocha.import_admin_boundaries -g adm0_polygons.gpkg

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
from src.data_model.data_provider import DataProvider
from src.providers import ocha

# The plumbing every importer shares, re-exported so this module reads as one
# application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import DEFAULT_STAGING_SCHEMA  # noqa: F401
from src.apps.imports.common import database_url  # noqa: F401
from src.apps.imports.common import ogr_connection_string  # noqa: F401
from src.apps.imports.common import resolve_database_settings  # noqa: F401

#: The provider row every imported boundary is attached to, defined beside the
#: model in :mod:`src.providers.ocha` because the wildfire importers need it too.
PROVIDER_NAME = ocha.PROVIDER_NAME
PROVIDER_FULL_NAME = ocha.PROVIDER_FULL_NAME
PROVIDER_PRODUCT = ocha.PROVIDER_PRODUCT
PROVIDER_URL = ocha.PROVIDER_URL

#: Default name of the layer inside the GeoPackage.
DEFAULT_LAYER = "adm0_polygons"

DEFAULT_STAGING_TABLE = "ocha_adm0_polygons"

#: Maps the staging table onto the two tables of the model in one statement.
#:
#: The data-modifying CTE is what makes the two-table insert possible: the outer
#: insert needs the ``id`` values the inner one generated, and ``RETURNING`` hands
#: them back correlated to ``source_id``, which is unique per provider. Joining on
#: it is therefore safe.
#:
#: ``ON CONFLICT DO NOTHING`` makes re-running the import a no-op rather than an
#: error. It also keeps the two inserts consistent: a row that conflicts is not
#: returned, so no orphan child row is written for it.
#:
#: ``name`` falls back from ``adm0_name`` to ``adm0_name1``. ``adm0_name`` is the
#: name qualified with its sovereign — ``"Aruba (Neth.)"`` — which is undefined
#: for a disputed area, and the layer leaves it empty for all 32 of them. Their
#: plain name is in ``adm0_name1``, which is never empty, so the fallback is what
#: keeps areas like Aksai Chin and the Spratly Islands importable at all.
TRANSFORM_SQL = """
WITH inserted AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry)
    SELECT 'ocha_admin_boundary', :provider_id, staging.adm0_id, 0,
           COALESCE(staging.adm0_name, staging.adm0_name1), staging.geom
    FROM {staging_table} AS staging
    ON CONFLICT (data_provider_id, source_id) DO NOTHING
    RETURNING id, source_id
)
INSERT INTO ocha_admin_boundary (
    id, source, name_alt, iso_code, iso_2, iso_3, iso_name, iso_3_group,
    region1_code, region1_name, region2_code, region2_name, region3_code, region3_name,
    status_code, status_name, valid_date, update_date, land_source, view, notes
)
SELECT
    inserted.id,
    staging.adm0_src,
    staging.adm0_name2::text,
    staging.iso_cd::integer,
    staging.iso_2,
    staging.iso_3,
    staging.adm0_name1,
    staging.iso_3_grp,
    staging.region1_cd::integer, staging.region1_nm,
    staging.region2_cd::integer, staging.region2_nm,
    staging.region3_cd::integer, staging.region3_nm,
    staging.status_cd::integer, staging.status_nm,
    staging.wld_date, staging.wld_update,
    staging.wld_land, staging.wld_view, staging.wld_notes
FROM inserted JOIN {staging_table} AS staging ON staging.adm0_id = inserted.source_id
RETURNING id
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Every database argument defaults to ``None`` so that a value left unset can
    be told apart from one set explicitly, and only the unset ones fall back to
    the environment.
    """
    parser = argparse.ArgumentParser(
        description="Import OCHA international boundaries from a GeoPackage into GisFIRE.",
        epilog="Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("-g", "--geopackage", required=True, type=Path,
                        help="path to the GeoPackage holding the boundaries layer")
    parser.add_argument("-l", "--layer", default=DEFAULT_LAYER,
                        help=f"layer to read inside the GeoPackage (default: {DEFAULT_LAYER})")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def get_or_create_data_provider(session: Session, logger: logging.Logger) -> DataProvider:
    """Return the OCHA provider row, creating it on first import."""
    return common.get_or_create_data_provider(
        session, PROVIDER_NAME, PROVIDER_PRODUCT, PROVIDER_FULL_NAME, PROVIDER_URL, logger
    )


def transform(session: Session, provider: DataProvider, staging_table: str,
              logger: logging.Logger) -> int:
    """Map the staging table onto the model, returning the number of rows imported."""
    # The statement returns one row per boundary written, so counting them needs
    # no reliance on ``rowcount`` and its dialect-specific corner cases.
    result = session.execute(
        text(TRANSFORM_SQL.format(staging_table=staging_table)), {"provider_id": provider.id}
    )
    imported = len(result.all())
    logger.info("Imported %d boundaries", imported)
    return imported


def import_boundaries(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the rows imported.

    The staging load happens outside the transaction — ``ogr2ogr`` opens its own
    connection and commits by itself — but everything that touches the model runs
    inside one, so a failure half way through leaves no partial import behind.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"

    common.create_staging_schema(engine, args.staging_schema)
    common.load_staging_table(str(args.geopackage), args.layer, staging_table, args,
                              common.resolve_database_settings(args), logger)

    with Session(engine) as session:
        provider = get_or_create_data_provider(session, logger)
        imported = transform(session, provider, staging_table, logger)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, logger)
        session.commit()

    if args.keep_staging:
        logger.info("Staging table %s kept", staging_table)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("ocha-import")

    if not args.geopackage.exists():
        logger.error("GeoPackage not found: %s", args.geopackage)
        return 1
    if shutil.which(args.ogr2ogr) is None:
        logger.error("ogr2ogr not found (looked for %r). It comes with GDAL and must be on PATH.",
                     args.ogr2ogr)
        return 1

    try:
        settings = resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        import_boundaries(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
