#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Portuguese administrative divisions from the CAOP GeoPackages.

Loads the *distritos*, *municípios* and *freguesias* of the Carta Administrativa
Oficial de Portugal into
:class:`~src.providers.caop.admin_boundary.CaopAdminBoundary` rows, as
administrative levels 1, 2 and 3 below the country. See :mod:`src.providers.caop`
for what the dataset is and why GisFIRE wants it.

Run it over the directory the DGT's four files were unpacked into::

    python3 -m src.apps.imports.admin_boundaries.caop.import_admin_boundaries -d /path/to/caop

Four files, four CRSs
---------------------

The CAOP is published one file per territory, and **each is in its own projected
CRS**: the mainland in EPSG:3763 (ETRS89 / Portugal TM06), the three island groups
in EPSG:5014, 5015 and 5016 (PTRA08 / UTM zones 25N, 26N and 28N). ``ogr2ogr``
reprojects each to EPSG:4326 as it stages it, so nothing downstream has to know
which file a boundary came from. Every file's layer names carry a prefix of their
own (``cont_``, ``ram_``, ``raa_cen_ori_``, ``raa_oci_``), so the layers are
discovered from the GeoPackage rather than named on the command line.

Three passes, largest division first
------------------------------------

Each level is staged and then mapped in turn — *distritos*, then *municípios*,
then *freguesias* — because a boundary's ``parent_id`` points at a row the pass
before it wrote. The parent is found **by code**, not by a spatial test: ``dt`` is
a prefix of ``dtmn`` is a prefix of ``dtmnfr``, without exception in the whole
dataset, so ``left(source_id, n)`` is exact and costs nothing next to 3 596
polygon containment tests.

The *distritos* have no parent in the data — the CAOP publishes no Portugal
polygon, only the three NUTS 1 regions — so they are parented to the country
boundary the OCHA import loads at level 0. If that has not been run, they are
imported as roots and the link is filled in by re-running this import once it has;
see :func:`relink_orphans`.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency,
not a Python package.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sqlite3
import sys

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.data_model.data_provider import DataProvider
from src.providers import caop

# The plumbing every importer shares, re-exported so this module reads as one
# application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import DEFAULT_STAGING_SCHEMA  # noqa: F401
from src.apps.imports.common import database_url  # noqa: F401
from src.apps.imports.common import ogr_connection_string  # noqa: F401
from src.apps.imports.common import resolve_database_settings  # noqa: F401

#: The provider row every imported boundary is attached to. The product carries
#: the edition, so each publication of the CAOP is its own provider — see
#: :mod:`src.providers.caop`.
PROVIDER_NAME = caop.PROVIDER_NAME
PROVIDER_FULL_NAME = caop.PROVIDER_FULL_NAME
PROVIDER_URL = caop.PROVIDER_URL

DEFAULT_EDITION = caop.DEFAULT_EDITION

#: How each level's layer is recognised inside a GeoPackage. The DGT prefixes
#: every layer with the territory (``cont_freguesias``, ``ram_freguesias``), and
#: the prefix differs per file, so the suffix is what identifies the level.
LAYER_SUFFIXES = {
    caop.KIND_DISTRITO: "_distritos",
    caop.KIND_MUNICIPIO: "_municipios",
    caop.KIND_FREGUESIA: "_freguesias",
}

#: Staging table each level is gathered into, from all four files at once.
STAGING_TABLES = {
    caop.KIND_DISTRITO: "caop_distritos",
    caop.KIND_MUNICIPIO: "caop_municipios",
    caop.KIND_FREGUESIA: "caop_freguesias",
}

#: Finds the edition in a published file name (``Continente_CAOP2025.gpkg``), so
#: importing one edition's files under another's label can be caught.
EDITION_IN_FILENAME = re.compile(r"CAOP(\d{4})", re.IGNORECASE)

#: Maps a staged level onto the two tables of the model in one statement.
#:
#: The data-modifying CTE is what makes the two-table insert possible: the outer
#: insert needs the ``id`` values the inner one generated, and ``RETURNING`` hands
#: them back correlated to ``source_id``, which is unique per provider. Joining on
#: it is therefore safe.
#:
#: ``ON CONFLICT DO NOTHING`` makes re-running the import a no-op rather than an
#: error, and keeps the two inserts consistent: a row that conflicts is not
#: returned, so no orphan child row is written for it.
#:
#: The three levels differ only in which columns they read, so each supplies its
#: own ``code``, ``name``, ``parent`` and per-level column expressions.
TRANSFORM_SQL = """
WITH inserted AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, parent_id, geometry)
    SELECT 'caop_admin_boundary', :provider_id, staging.{code}, {level}, staging.{name},
           {parent}, staging.geom
    FROM {staging_table} AS staging
    {parent_join}
    ON CONFLICT (data_provider_id, source_id) DO NOTHING
    RETURNING id, source_id
)
INSERT INTO caop_admin_boundary (
    id, edition, kind, name_simplified,
    nuts1_code, nuts1_name, nuts2_name, nuts3_code, nuts3_name, area_ha, perimeter_km
)
SELECT inserted.id, :edition, '{kind}', {name_simplified},
       {nuts1_code}, staging.nuts1, {nuts2_name}, {nuts3_code}, {nuts3_name},
       staging.area_ha, staging.perimetro_km
FROM inserted JOIN {staging_table} AS staging ON staging.{code} = inserted.source_id
RETURNING id
"""

#: What each level plugs into :data:`TRANSFORM_SQL`.
#:
#: A *distrito* is the only level the CAOP gives a ``nuts1_cod`` to, and the only
#: one it assigns no NUTS 2 or 3 region — it could not, since a NUTS 3 region
#: crosses *distrito* boundaries (see :mod:`src.providers.caop`). A *freguesia* is
#: the only one with a simplified name. Hence the NULLs rather than one uniform
#: mapping.
LEVEL_MAPPINGS = {
    caop.KIND_DISTRITO: {
        "code": "dt",
        "name": "distrito",
        # Parented to the country, which comes from another provider entirely and
        # so is passed in rather than joined to.
        "parent": ":country_id",
        "parent_join": "",
        "name_simplified": "NULL",
        "nuts1_code": "staging.nuts1_cod",
        "nuts2_name": "NULL",
        "nuts3_code": "NULL",
        "nuts3_name": "NULL",
    },
    caop.KIND_MUNICIPIO: {
        "code": "dtmn",
        "name": "municipio",
        "parent": "parent.id",
        "parent_join": (
            "LEFT JOIN admin_boundary AS parent"
            "  ON parent.data_provider_id = :provider_id"
            " AND parent.source_id = left(staging.dtmn, 2)"
        ),
        "name_simplified": "NULL",
        "nuts1_code": "NULL",
        "nuts2_name": "staging.nuts2",
        "nuts3_code": "staging.nuts3_cod",
        "nuts3_name": "staging.nuts3",
    },
    caop.KIND_FREGUESIA: {
        "code": "dtmnfr",
        "name": "freguesia",
        "parent": "parent.id",
        "parent_join": (
            "LEFT JOIN admin_boundary AS parent"
            "  ON parent.data_provider_id = :provider_id"
            " AND parent.source_id = left(staging.dtmnfr, 4)"
        ),
        "name_simplified": "staging.designacao_simplificada",
        "nuts1_code": "NULL",
        "nuts2_name": "staging.nuts2",
        "nuts3_code": "staging.nuts3_cod",
        "nuts3_name": "staging.nuts3",
    },
}

#: Finds the country row the *distritos* hang off: the OCHA level 0 boundary for
#: Portugal. Ordered so that a dataset publishing a country as several features
#: (as it does for the French Southern Territories) still resolves to the same one
#: on every run.
COUNTRY_SQL = """
SELECT admin_boundary.id, admin_boundary.name
FROM admin_boundary
JOIN ocha_admin_boundary ON ocha_admin_boundary.id = admin_boundary.id
WHERE ocha_admin_boundary.iso_3 = :iso_3
ORDER BY admin_boundary.source_id
"""

#: Fills in the parent of boundaries imported before their parent existed.
#:
#: Re-running the import cannot do it: the insert is ``ON CONFLICT DO NOTHING``,
#: so a row already there is not touched. Without this, importing the CAOP before
#: the OCHA countries would leave 29 *distritos* rooted for good.
RELINK_BY_CODE_SQL = """
UPDATE admin_boundary AS child
SET parent_id = parent.id
FROM admin_boundary AS parent
WHERE child.data_provider_id = :provider_id
  AND child.level = :level
  AND child.parent_id IS NULL
  AND parent.data_provider_id = :provider_id
  AND parent.source_id = left(child.source_id, :parent_code_length)
RETURNING child.id
"""

RELINK_TO_COUNTRY_SQL = """
UPDATE admin_boundary
SET parent_id = :country_id
WHERE data_provider_id = :provider_id AND level = 1 AND parent_id IS NULL
RETURNING id
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Every database argument defaults to ``None`` so that a value left unset can
    be told apart from one set explicitly, and only the unset ones fall back to
    the environment.
    """
    parser = argparse.ArgumentParser(
        description="Import the Portuguese administrative divisions (CAOP) into GisFIRE.",
        epilog="Database settings not given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published GeoPackages, one per territory")
    source.add_argument("-g", "--geopackage", type=Path,
                        help="a single GeoPackage, to import one territory on its own")
    parser.add_argument("--edition", default=DEFAULT_EDITION,
                        help=f"CAOP edition being imported (default: {DEFAULT_EDITION}). "
                             f"Each edition is a separate data provider, so editions do not "
                             f"overwrite one another")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, STAGING_TABLES[caop.KIND_FREGUESIA])
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_geopackages(args: argparse.Namespace) -> list[Path]:
    """Return the GeoPackages to import, sorted.

    Raises
    ------
    RuntimeError
        If the directory holds none, which is nearly always the wrong directory
        rather than an empty one.
    """
    if args.geopackage is not None:
        return [args.geopackage]

    found = sorted(args.directory.glob("*.gpkg"))
    if not found:
        raise RuntimeError(f"No GeoPackage (*.gpkg) found in {args.directory}")
    return found


def discover_layers(geopackage: Path) -> dict[str, str]:
    """Return the layer of each level inside one GeoPackage, keyed by kind.

    The layer names are read from ``gpkg_contents``, the table every GeoPackage is
    required to have, because the DGT prefixes them with the territory and the
    prefix is different in each of the four files.

    Raises
    ------
    RuntimeError
        If the file cannot be read as a GeoPackage, or does not hold all three
        levels — importing two of the three would build a tree with a level
        missing from the middle.
    """
    try:
        connection = sqlite3.connect(f"file:{geopackage}?mode=ro", uri=True)
        try:
            tables = [
                row[0] for row in connection.execute(
                    "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
                )
            ]
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise RuntimeError(f"{geopackage} cannot be read as a GeoPackage: {error}") from error

    layers = {}
    for kind, suffix in LAYER_SUFFIXES.items():
        matching = [table for table in tables if table.endswith(suffix)]
        if len(matching) != 1:
            raise RuntimeError(
                f"{geopackage} holds {len(matching)} layers ending in '{suffix}' "
                f"(expected exactly one, for the {kind} level)"
            )
        layers[kind] = matching[0]
    return layers


def check_edition(geopackages: list[Path], edition: str, logger: logging.Logger) -> None:
    """Warn if a file's name names a different edition than the one being imported.

    The edition is what keeps one publication of the codes apart from the next, so
    labelling 2024's files as 2025 would quietly merge two versions of Portugal
    into one provider. It is a warning and not an error because the file names are
    the DGT's convention, not a guarantee.
    """
    for geopackage in geopackages:
        found = EDITION_IN_FILENAME.search(geopackage.name)
        if found and found.group(1) != edition:
            logger.warning(
                "%s looks like the %s edition but is being imported as %s. Pass "
                "--edition %s if that is what you meant.",
                geopackage.name, found.group(1), edition, found.group(1),
            )


def get_or_create_data_provider(session: Session, edition: str,
                                logger: logging.Logger) -> DataProvider:
    """Return the provider row for this CAOP edition, creating it on first import."""
    return common.get_or_create_data_provider(
        session, PROVIDER_NAME, caop.provider_product(edition), PROVIDER_FULL_NAME,
        PROVIDER_URL, logger,
    )


def find_country(session: Session, logger: logging.Logger) -> int | None:
    """Return the id of the OCHA boundary the *distritos* hang off, if imported.

    Returning ``None`` rather than raising is deliberate, for the same reason
    :func:`src.apps.imports.common.find_boundary_provider` does it: the Portuguese
    divisions are worth having on their own, and the country they sit under can be
    imported afterwards — :func:`relink_orphans` picks it up on the next run.
    """
    found = session.execute(text(COUNTRY_SQL), {"iso_3": caop.COUNTRY_ISO_3}).all()
    if not found:
        logger.warning(
            "No OCHA boundary for %s: the distritos will be imported as roots, with no "
            "country above them. Import the countries with "
            "src.apps.imports.admin_boundaries.ocha.import_admin_boundaries and run this "
            "again to link them.",
            caop.COUNTRY_ISO_3,
        )
        return None
    if len(found) > 1:
        logger.warning(
            "%d OCHA boundaries carry iso_3 = %s; parenting the distritos to %r, the first "
            "by source id.", len(found), caop.COUNTRY_ISO_3, found[0].name,
        )
    logger.debug("Parenting the distritos to %r (id %d)", found[0].name, found[0].id)
    return found[0].id


def load_staging(geopackages: list[Path], kind: str, staging_table: str,
                 args: argparse.Namespace, settings: dict[str, str],
                 logger: logging.Logger) -> None:
    """Stage one level from every GeoPackage into a single table.

    The first file replaces the table and the rest are appended to it, so the four
    territories — each published in its own CRS and reprojected to EPSG:4326 on the
    way in — end up as one relation to map from.
    """
    for index, geopackage in enumerate(geopackages):
        layer = discover_layers(geopackage)[kind]
        common.load_staging_table(
            str(geopackage), layer, staging_table, args, settings, logger,
            append=index > 0,
        )


def transform(session: Session, provider: DataProvider, kind: str, staging_table: str,
              country_id: int | None, edition: str, logger: logging.Logger) -> int:
    """Map one staged level onto the model, returning the number of rows imported."""
    mapping = LEVEL_MAPPINGS[kind]
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table, kind=kind, level=caop.LEVELS[kind], **mapping
    )
    parameters: dict[str, object] = {"provider_id": provider.id, "edition": edition}
    if kind == caop.KIND_DISTRITO:
        parameters["country_id"] = country_id

    # The statement returns one row per boundary written, so counting them needs
    # no reliance on ``rowcount`` and its dialect-specific corner cases.
    imported = len(session.execute(text(statement), parameters).all())
    logger.info("Imported %d %s", imported, kind)
    return imported


def relink_orphans(session: Session, provider: DataProvider, country_id: int | None,
                   logger: logging.Logger) -> int:
    """Give a parent to boundaries that were imported before their parent existed.

    Two ways that happens: the CAOP was imported before the OCHA countries, which
    leaves the *distritos* rooted; or one territory's file was imported before
    another's, in a run that had no *distrito* for a *município* to hang off. Both
    are fixed by running the import again once the missing piece is there, which
    the ``ON CONFLICT DO NOTHING`` insert alone would not do.

    Returns
    -------
    int
        How many boundaries were given a parent.
    """
    relinked = 0
    if country_id is not None:
        relinked += len(session.execute(
            text(RELINK_TO_COUNTRY_SQL),
            {"provider_id": provider.id, "country_id": country_id},
        ).all())

    for kind in (caop.KIND_MUNICIPIO, caop.KIND_FREGUESIA):
        parent_kind = caop.KINDS[caop.KINDS.index(kind) - 1]
        relinked += len(session.execute(
            text(RELINK_BY_CODE_SQL),
            {
                "provider_id": provider.id,
                "level": caop.LEVELS[kind],
                "parent_code_length": caop.CODE_LENGTHS[parent_kind],
            },
        ).all())

    if relinked:
        logger.info("Linked %d boundary(ies) to a parent imported later", relinked)
    return relinked


def import_boundaries(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the rows imported.

    The staging loads happen outside the transaction — ``ogr2ogr`` opens its own
    connection and commits by itself — but everything that touches the model runs
    inside one, so a failure half way through leaves no partial import behind.
    """
    geopackages = find_geopackages(args)
    check_edition(geopackages, args.edition, logger)
    logger.info("Importing %d GeoPackage(s) as the %s edition", len(geopackages), args.edition)

    common.require_tables(
        engine, ["admin_boundary", "caop_admin_boundary", "data_provider"], logger
    )
    common.create_staging_schema(engine, args.staging_schema)

    settings = common.resolve_database_settings(args)
    staging_tables = {
        kind: f"{args.staging_schema}.{table}" for kind, table in STAGING_TABLES.items()
    }
    for kind in caop.KINDS:
        load_staging(geopackages, kind, staging_tables[kind], args, settings, logger)

    with Session(engine) as session:
        provider = get_or_create_data_provider(session, args.edition, logger)
        country_id = find_country(session, logger)

        # Largest division first: each level's parent is a row the pass before it
        # wrote, so the order is not an optimisation but a requirement.
        imported = sum(
            transform(session, provider, kind, staging_tables[kind], country_id,
                      args.edition, logger)
            for kind in caop.KINDS
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
    logger = logging.getLogger("caop-import")

    source = args.directory if args.geopackage is None else args.geopackage
    if not source.exists():
        logger.error("%s not found: %s", "Directory" if args.geopackage is None else "GeoPackage",
                     source)
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
