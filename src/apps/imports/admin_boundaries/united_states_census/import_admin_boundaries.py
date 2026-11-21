#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the US states and counties from the Census Bureau's Cartographic Boundary Files.

Loads the 1:500,000 state and county layers into
:class:`~src.providers.united_states_census.admin_boundary.CensusAdminBoundary`
rows, as administrative levels 1 and 2 below the country. See
:mod:`src.providers.united_states_census` for what the files are and what is left
out of them.

Run it over the directory the two downloaded zips are in::

    python3 -m src.apps.imports.admin_boundaries.united_states_census.import_admin_boundaries -d /path/to/census

The files are found by name — ``cb_<edition>_us_state_500k`` and
``cb_<edition>_us_county_500k``, ``.zip`` as downloaded or the ``.shp`` unpacked
— searched recursively. A zip is read in place, with no unpacking. The source is
NAD83 (EPSG:4269); ``ogr2ogr`` reprojects it to EPSG:4326.

Two passes, states first
------------------------

Each level is staged and then mapped in turn, because a county's ``parent_id``
points at the state the first pass wrote: the state whose ``GEOID`` is the first
two digits of the county's. Only the 50 states and DC (FIPS 01 to 56) and their
counties are imported.

The states have no parent in these files, so they are parented to the country
boundary the OCHA import loads at level 0. If that has not been run, they are
imported as roots and the link is filled in by re-running this import once it
has; see :func:`relink_orphans`.

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
from src.providers import united_states_census as census

# The plumbing every importer shares, re-exported so this module reads as one
# application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import DEFAULT_STAGING_SCHEMA  # noqa: F401
from src.apps.imports.common import database_url  # noqa: F401
from src.apps.imports.common import ogr_connection_string  # noqa: F401
from src.apps.imports.common import resolve_database_settings  # noqa: F401

#: Staging table each level is loaded into.
STAGING_TABLES = {
    census.KIND_STATE: "census_states",
    census.KIND_COUNTY: "census_counties",
}

#: Maps a staged level onto the two tables of the model in one statement, as the
#: IGN import does (see :mod:`src.apps.imports.admin_boundaries.ign.import_admin_boundaries`
#: for why it is a data-modifying CTE and ``ON CONFLICT DO NOTHING``).
#:
#: ``ogr2ogr`` lower-cases the column names on the way into PostgreSQL. The
#: territories are left out by their state code, which both layers carry.
TRANSFORM_SQL = """
WITH inserted AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, name_en,
                                parent_id, geometry)
    SELECT 'census_admin_boundary', :provider_id, staging.geoid, :level, staging.name,
           staging.name, {parent}, staging.geom
    FROM {staging_table} AS staging
    {parent_join}
    WHERE staging.statefp <= :last_state_fips
    ON CONFLICT (data_provider_id, source_id) DO NOTHING
    RETURNING id, source_id
)
INSERT INTO census_admin_boundary (id, edition, kind, lsad)
SELECT inserted.id, :edition, :kind, staging.lsad
FROM inserted JOIN {staging_table} AS staging ON staging.geoid = inserted.source_id
RETURNING id
"""

#: What each level plugs into :data:`TRANSFORM_SQL`.
LEVEL_MAPPINGS = {
    # Parented to the country, which comes from another provider entirely and so
    # is passed in rather than joined to.
    census.KIND_STATE: {"parent": ":country_id", "parent_join": ""},
    census.KIND_COUNTY: {
        "parent": "parent.id",
        "parent_join": (
            "LEFT JOIN admin_boundary AS parent"
            "  ON parent.data_provider_id = :provider_id"
            " AND parent.source_id = staging.statefp"
        ),
    },
}

#: Finds the country row the states hang off: the OCHA level 0 boundary for the
#: United States. Ordered so that a dataset publishing a country as several
#: features still resolves to the same one on every run.
COUNTRY_SQL = """
SELECT admin_boundary.id, admin_boundary.name
FROM admin_boundary
JOIN ocha_admin_boundary ON ocha_admin_boundary.id = admin_boundary.id
WHERE ocha_admin_boundary.iso_3 = :iso_3
ORDER BY admin_boundary.source_id
"""

#: Fills in the parent of the states imported before the country existed.
#: Re-running the import cannot do it: the insert is ``ON CONFLICT DO NOTHING``,
#: so a row already there is not touched.
RELINK_TO_COUNTRY_SQL = """
UPDATE admin_boundary
SET parent_id = :country_id
WHERE data_provider_id = :provider_id AND level = :level AND parent_id IS NULL
RETURNING id
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Every database argument defaults to ``None`` so that a value left unset can
    be told apart from one set explicitly, and only the unset ones fall back to
    the environment.
    """
    parser = argparse.ArgumentParser(
        description="Import the US states and counties (Census Bureau Cartographic Boundary "
                    "Files, 1:500,000) into GisFIRE.",
        epilog="Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("-d", "--directory", required=True, type=Path,
                        help="directory holding the downloaded state and county files "
                             "(cb_<edition>_us_state_500k.zip and cb_<edition>_us_county_500k.zip, "
                             "or their unpacked shapefiles); searched recursively")
    parser.add_argument("--edition", default=census.DEFAULT_EDITION,
                        help=f"edition (year) being imported, as in the file names (default: "
                             f"{census.DEFAULT_EDITION}). Each edition is a separate data "
                             f"provider, so editions do not overwrite one another")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, STAGING_TABLES[census.KIND_COUNTY])
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_files(directory: Path, edition: str) -> dict[str, Path]:
    """Return each level's file under ``directory``, keyed by kind.

    A zip, as downloaded, is preferred to an unpacked shapefile of the same name.

    Raises
    ------
    RuntimeError
        If a level has no file, or more than one of the same kind (two copies in
        different folders, which may not be the same).
    """
    found = {}
    for kind in census.KINDS:
        name = census.file_name(edition, kind)
        for suffix in (".zip", ".shp"):
            paths = sorted(directory.glob(f"**/{name}{suffix}"))
            if len(paths) > 1:
                raise RuntimeError(f"{len(paths)} files named {name}{suffix} under {directory}: "
                                   f"{', '.join(str(path) for path in paths)}")
            if paths:
                found[kind] = paths[0]
                break
        else:
            raise RuntimeError(f"No {name}.zip (nor {name}.shp) under {directory}. Is "
                               f"--edition {edition} the edition downloaded?")
    return found


def get_or_create_data_provider(session: Session, edition: str,
                                logger: logging.Logger) -> DataProvider:
    """Return the provider row for this edition, creating it on first import."""
    return common.get_or_create_data_provider(
        session, census.PROVIDER_NAME, census.provider_product(edition),
        census.PROVIDER_FULL_NAME, census.PROVIDER_URL, logger,
    )


def find_country(session: Session, logger: logging.Logger) -> int | None:
    """Return the id of the OCHA boundary the states hang off.

    Returning ``None`` rather than raising is deliberate: the states and counties
    are worth having on their own, and the country they sit under can be imported
    afterwards — :func:`relink_orphans` picks it up on the next run.
    """
    found = session.execute(text(COUNTRY_SQL), {"iso_3": census.COUNTRY_ISO_3}).all()
    if not found:
        logger.warning(
            "No OCHA boundary for %s: the states will be imported as roots, with no country "
            "above them. Import the countries with "
            "src.apps.imports.admin_boundaries.ocha.import_admin_boundaries and run this "
            "again to link them.",
            census.COUNTRY_ISO_3,
        )
        return None
    if len(found) > 1:
        logger.warning(
            "%d OCHA boundaries carry iso_3 = %s; parenting the states to %r, the first by "
            "source id.", len(found), census.COUNTRY_ISO_3, found[0].name,
        )
    logger.debug("Parenting the states to %r (id %d)", found[0].name, found[0].id)
    return found[0].id


def transform(session: Session, provider: DataProvider, kind: str, staging_table: str,
              country_id: int | None, edition: str, logger: logging.Logger) -> int:
    """Map one staged level onto the model, returning the number of rows imported."""
    statement = TRANSFORM_SQL.format(staging_table=staging_table, **LEVEL_MAPPINGS[kind])
    parameters: dict[str, object] = {
        "provider_id": provider.id, "level": census.LEVELS[kind], "kind": kind,
        "edition": edition, "last_state_fips": census.LAST_STATE_FIPS,
    }
    if kind == census.KIND_STATE:
        parameters["country_id"] = country_id
    imported = len(session.execute(text(statement), parameters).all())
    logger.info("Imported %d %s boundaries", imported, kind)
    return imported


def relink_orphans(session: Session, provider: DataProvider, country_id: int | None,
                   logger: logging.Logger) -> int:
    """Give the country as parent to the states imported before it existed.

    That happens when the Census files are imported before the OCHA countries.
    The counties need no relinking: they are imported in the same run as their
    states, after them.

    Returns
    -------
    int
        How many states were given a parent.
    """
    if country_id is None:
        return 0
    relinked = len(session.execute(
        text(RELINK_TO_COUNTRY_SQL),
        {"provider_id": provider.id, "country_id": country_id,
         "level": census.LEVELS[census.KIND_STATE]},
    ).all())
    if relinked:
        logger.info("Linked %d state(s) to the country imported later", relinked)
    return relinked


def import_boundaries(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the rows imported.

    The staging loads happen outside the transaction — ``ogr2ogr`` opens its own
    connection and commits by itself — but everything that touches the model runs
    inside one, so a failure half way through leaves no partial import behind.
    """
    files = find_files(args.directory, args.edition)
    logger.info("Importing the %s edition: %s", args.edition,
                ", ".join(str(path) for path in files.values()))

    common.require_tables(
        engine, ["admin_boundary", "census_admin_boundary", "data_provider"], logger
    )
    common.create_staging_schema(engine, args.staging_schema)

    settings = common.resolve_database_settings(args)
    staging_tables = {
        kind: f"{args.staging_schema}.{table}" for kind, table in STAGING_TABLES.items()
    }
    for kind in census.KINDS:
        datasource, layer = common.shapefile_datasource(files[kind])
        common.load_staging_table(datasource, layer, staging_tables[kind], args, settings, logger)

    with Session(engine) as session:
        provider = get_or_create_data_provider(session, args.edition, logger)
        country_id = find_country(session, logger)

        # States first: each county's parent is a row the state pass wrote.
        imported = sum(
            transform(session, provider, kind, staging_tables[kind], country_id, args.edition,
                      logger)
            for kind in census.KINDS
        )
        relink_orphans(session, provider, country_id, logger)

        if not args.keep_staging:
            for staging_table in staging_tables.values():
                common.drop_staging_table(session, staging_table, logger)
        session.commit()

    if args.keep_staging:
        logger.info("Staging tables %s kept", ", ".join(sorted(staging_tables.values())))
    logger.info("Imported %d boundaries", imported)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("census-import")

    if not args.directory.exists():
        logger.error("Directory not found: %s", args.directory)
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


if __name__ == "__main__":  # pragma nocover
    sys.exit(main())
