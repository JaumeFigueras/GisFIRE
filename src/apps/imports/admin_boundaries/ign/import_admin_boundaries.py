#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Spanish administrative divisions from the IGN ``recintos`` shapefiles.

Loads the *comunidades autónomas*, *provincias* and *municipios* of the Base de
Datos de Divisiones Administrativas de España into
:class:`~src.providers.spain_ign.admin_boundary.IgnAdminBoundary` rows, as administrative
levels 1, 2 and 3 below the country. See :mod:`src.providers.spain_ign` for what the
dataset is and what it leaves out.

Run it over the directory the IGN's download was unpacked into::

    python3 -m src.apps.imports.admin_boundaries.ign.import_admin_boundaries -d /path/to/bddae

Two datums, six shapefiles
--------------------------

The data is published twice, once per datum — the peninsula and the Balearics in
ETRS89 (EPSG:4258), the Canaries in REGCAN95 (EPSG:4081) — with the three levels
in a ``recintos_*`` directory each. That is six shapefiles, found by walking the
directory rather than named on the command line, since the layer name is the file
name and differs per datum. Both CRSs are geographic and transform to EPSG:4326
without moving a coordinate; ``ogr2ogr`` is still told to do it, so the import
does not quietly depend on the source never changing.

The companion ``ll_*`` directories hold the boundary lines and are ignored: only
the ``recintos`` are areas, and an area is what a fire is attributed to.

Three passes, largest division first
------------------------------------

Each level is staged and then mapped in turn, because a boundary's ``parent_id``
points at a row the pass before it wrote. The parent is found **by code**: an
11-digit ``NATCODE`` is zero-padded on the right, so the parent of a *municipio*
is ``left(natcode, 6) || '00000'`` rather than a plain prefix.

The *comunidades autónomas* have no parent in the data — the BDDAE publishes no
Spain polygon — so they are parented to the country boundary the OCHA import loads
at level 0. If that has not been run, they are imported as roots and the link is
filled in by re-running this import once it has; see :func:`relink_orphans`.

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
from src.providers import spain_ign

# The plumbing every importer shares, re-exported so this module reads as one
# application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import DEFAULT_STAGING_SCHEMA  # noqa: F401
from src.apps.imports.common import database_url  # noqa: F401
from src.apps.imports.common import ogr_connection_string  # noqa: F401
from src.apps.imports.common import resolve_database_settings  # noqa: F401

#: The provider row every imported boundary is attached to. The product carries
#: the edition, so each publication of the BDDAE is its own provider — see
#: :mod:`src.providers.spain_ign`.
PROVIDER_NAME = spain_ign.PROVIDER_NAME
PROVIDER_FULL_NAME = spain_ign.PROVIDER_FULL_NAME
PROVIDER_URL = spain_ign.PROVIDER_URL

DEFAULT_EDITION = spain_ign.DEFAULT_EDITION

#: How each level's shapefile is recognised while walking the directory. The IGN
#: names them for the level in Spanish and for the datum, and only the level part
#: is common to both publications.
FILENAME_MARKERS = {
    spain_ign.KIND_COMUNIDAD_AUTONOMA: "recintos_autonomicas",
    spain_ign.KIND_PROVINCIA: "recintos_provinciales",
    spain_ign.KIND_MUNICIPIO: "recintos_municipales",
}

#: Staging table each level is gathered into, from both datums at once.
STAGING_TABLES = {
    spain_ign.KIND_COMUNIDAD_AUTONOMA: "ign_autonomicas",
    spain_ign.KIND_PROVINCIA: "ign_provinciales",
    spain_ign.KIND_MUNICIPIO: "ign_municipales",
}

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
#: ``ogr2ogr`` lower-cases the INSPIRE column names on the way into PostgreSQL,
#: which is why they are read as ``natcode`` rather than ``NATCODE``.
#:
#: The NUTS codes are doubly ``nullif``-ed because a DBF has no NULL: a field the
#: IGN did not fill arrives as an empty string, and the one it fills with a
#: placeholder — the excluded territories, which get ``'0'`` — arrives as that. Both
#: mean "no region" and both should be NULL rather than sorted alongside real codes.
TRANSFORM_SQL = """
WITH inserted AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, parent_id, geometry)
    SELECT 'ign_admin_boundary', :provider_id, staging.natcode, {level}, staging.nameunit,
           {parent}, staging.geom
    FROM {staging_table} AS staging
    {parent_join}
    WHERE TRUE {territory_filter}
    ON CONFLICT (data_provider_id, source_id) DO NOTHING
    RETURNING id, source_id
)
INSERT INTO ign_admin_boundary (id, edition, kind, ine_code, nuts1_code, nuts2_code, nuts3_code)
SELECT inserted.id, :edition, {kind}, {ine_code},
       nullif(nullif(staging.codnut1, ''), '0'),
       nullif(nullif(staging.codnut2, ''), '0'),
       nullif(nullif(staging.codnut3, ''), '0')
FROM inserted JOIN {staging_table} AS staging ON staging.natcode = inserted.source_id
RETURNING id
"""

#: What each level plugs into :data:`TRANSFORM_SQL`.
#:
#: Only the *municipios* layer needs a ``kind`` worked out per row rather than
#: fixed: it holds the seven ``Territorio`` areas alongside the municipalities, and
#: they are stored at the same level. The other two layers are one kind throughout.
#:
#: ``ine_code`` is the last five digits of the code, which are the INE municipal
#: code at the bottom level and padding above it — hence NULL rather than
#: ``'00000'``.
LEVEL_MAPPINGS = {
    spain_ign.KIND_COMUNIDAD_AUTONOMA: {
        # Parented to the country, which comes from another provider entirely and
        # so is passed in rather than joined to.
        "parent": ":country_id",
        "parent_join": "",
        "kind": f"'{spain_ign.KIND_COMUNIDAD_AUTONOMA}'",
        "ine_code": "NULL",
    },
    spain_ign.KIND_PROVINCIA: {
        "parent": "parent.id",
        "parent_join": (
            "LEFT JOIN admin_boundary AS parent"
            "  ON parent.data_provider_id = :provider_id"
            " AND parent.source_id = left(staging.natcode, 4) || '0000000'"
        ),
        "kind": f"'{spain_ign.KIND_PROVINCIA}'",
        "ine_code": "NULL",
    },
    spain_ign.KIND_MUNICIPIO: {
        "parent": "parent.id",
        "parent_join": (
            "LEFT JOIN admin_boundary AS parent"
            "  ON parent.data_provider_id = :provider_id"
            " AND parent.source_id = left(staging.natcode, 6) || '00000'"
        ),
        "kind": (
            f"CASE WHEN staging.natlevname = '{spain_ign.EXCLUDED_NATLEVNAME}'"
            f" THEN '{spain_ign.KIND_TERRITORIO}' ELSE '{spain_ign.KIND_MUNICIPIO}' END"
        ),
        "ine_code": "right(staging.natcode, 5)",
    },
}

#: Removes the branch that is not a Spanish administrative division: Gibraltar,
#: the *plazas de soberanía*, the Isla de los Faisanes and the pseudo *comunidad
#: autónoma* and *provincia* that exist only to hold them. Nine rows across the
#: three levels. See :mod:`src.providers.spain_ign`.
#:
#: Written as ``left(...) <> ...`` rather than ``NOT LIKE '3420%'`` on purpose: a
#: literal ``%`` inside :func:`sqlalchemy.text` has to be doubled for the DBAPI's
#: parameter style, which is a trap for whoever edits this next. The comparison
#: says the same thing and cannot be got wrong.
TERRITORY_FILTER = (
    f"AND left(staging.natcode, {len(spain_ign.EXCLUDED_CODE_PREFIX)}) "
    f"<> '{spain_ign.EXCLUDED_CODE_PREFIX}'"
)

#: Finds the country row the *comunidades autónomas* hang off: the OCHA level 0
#: boundary for Spain. Ordered so that a dataset publishing a country as several
#: features still resolves to the same one on every run.
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
#: so a row already there is not touched. Without this, importing the BDDAE before
#: the OCHA countries would leave the *comunidades autónomas* rooted for good.
RELINK_BY_CODE_SQL = """
UPDATE admin_boundary AS child
SET parent_id = parent.id
FROM admin_boundary AS parent
WHERE child.data_provider_id = :provider_id
  AND child.level = :level
  AND child.parent_id IS NULL
  AND parent.data_provider_id = :provider_id
  AND parent.source_id = left(child.source_id, :parent_code_length)
                         || repeat('0', :padding)
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
        description="Import the Spanish administrative divisions (IGN BDDAE) into GisFIRE.",
        epilog="Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("-d", "--directory", required=True, type=Path,
                        help="directory holding the published shapefiles; searched recursively, "
                             "so it can be the download root or one datum's folder")
    parser.add_argument("--edition", default=DEFAULT_EDITION,
                        help=f"BDDAE edition being imported (default: {DEFAULT_EDITION}). Each "
                             f"edition is a separate data provider, so editions do not overwrite "
                             f"one another. Nothing in the published files names it")
    parser.add_argument("--include-territories", action="store_true",
                        help="also import Gibraltar, the plazas de soberanía and the Isla de los "
                             "Faisanes, which the IGN maps but does not call municipios (9 rows "
                             "across the three levels, excluded by default)")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, STAGING_TABLES[spain_ign.KIND_MUNICIPIO])
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def find_shapefiles(directory: Path) -> dict[str, list[Path]]:
    """Return the ``recintos`` shapefiles under ``directory``, keyed by level.

    Searched recursively, so the argument can be the download root — which holds a
    directory per datum, each holding a directory per level — or a single datum's
    folder. The ``ll_*`` line layers are not matched and so are never picked up.

    Raises
    ------
    RuntimeError
        If no level has a shapefile at all, which is nearly always the wrong
        directory rather than an empty one.
    """
    found = {
        kind: sorted(
            path for path in directory.glob("**/*.shp")
            if path.name.startswith(marker)
        )
        for kind, marker in FILENAME_MARKERS.items()
    }
    if not any(found.values()):
        raise RuntimeError(
            f"No recintos shapefile found under {directory}. Expected files named "
            f"{', '.join(sorted(f'{marker}_*.shp' for marker in FILENAME_MARKERS.values()))}."
        )
    return found


def get_or_create_data_provider(session: Session, edition: str,
                                logger: logging.Logger) -> DataProvider:
    """Return the provider row for this BDDAE edition, creating it on first import."""
    return common.get_or_create_data_provider(
        session, PROVIDER_NAME, spain_ign.provider_product(edition), PROVIDER_FULL_NAME,
        PROVIDER_URL, logger,
    )


def find_country(session: Session, logger: logging.Logger) -> int | None:
    """Return the id of the OCHA boundary the *comunidades autónomas* hang off.

    Returning ``None`` rather than raising is deliberate, for the same reason
    :func:`src.apps.imports.common.find_boundary_provider` does it: the Spanish
    divisions are worth having on their own, and the country they sit under can be
    imported afterwards — :func:`relink_orphans` picks it up on the next run.
    """
    found = session.execute(text(COUNTRY_SQL), {"iso_3": spain_ign.COUNTRY_ISO_3}).all()
    if not found:
        logger.warning(
            "No OCHA boundary for %s: the comunidades autónomas will be imported as roots, "
            "with no country above them. Import the countries with "
            "src.apps.imports.admin_boundaries.ocha.import_admin_boundaries and run this "
            "again to link them.",
            spain_ign.COUNTRY_ISO_3,
        )
        return None
    if len(found) > 1:
        logger.warning(
            "%d OCHA boundaries carry iso_3 = %s; parenting the comunidades autónomas to %r, "
            "the first by source id.", len(found), spain_ign.COUNTRY_ISO_3, found[0].name,
        )
    logger.debug("Parenting the comunidades autónomas to %r (id %d)", found[0].name, found[0].id)
    return found[0].id


def load_staging(shapefiles: list[Path], staging_table: str, args: argparse.Namespace,
                 settings: dict[str, str], logger: logging.Logger) -> None:
    """Stage one level from every datum's shapefile into a single table.

    The first file replaces the table and the rest are appended to it, so the two
    publications — each in its own geographic CRS and reprojected to EPSG:4326 on
    the way in — end up as one relation to map from.
    """
    for index, shapefile in enumerate(shapefiles):
        datasource, layer = common.shapefile_datasource(shapefile)
        common.load_staging_table(
            datasource, layer, staging_table, args, settings, logger, append=index > 0,
        )


def transform(session: Session, provider: DataProvider, kind: str, staging_table: str,
              country_id: int | None, args: argparse.Namespace,
              logger: logging.Logger) -> int:
    """Map one staged level onto the model, returning the number of rows imported."""
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        level=spain_ign.LEVELS[kind],
        territory_filter="" if args.include_territories else TERRITORY_FILTER,
        **LEVEL_MAPPINGS[kind],
    )
    parameters: dict[str, object] = {"provider_id": provider.id, "edition": args.edition}
    if kind == spain_ign.KIND_COMUNIDAD_AUTONOMA:
        parameters["country_id"] = country_id

    # The statement returns one row per boundary written, so counting them needs
    # no reliance on ``rowcount`` and its dialect-specific corner cases.
    imported = len(session.execute(text(statement), parameters).all())
    logger.info("Imported %d %s", imported, kind)
    return imported


def relink_orphans(session: Session, provider: DataProvider, country_id: int | None,
                   logger: logging.Logger) -> int:
    """Give a parent to boundaries that were imported before their parent existed.

    Two ways that happens: the BDDAE was imported before the OCHA countries, which
    leaves the *comunidades autónomas* rooted; or one datum's folder was imported
    before the other's, in a run that had no *comunidad* for a *provincia* to hang
    off. Both are fixed by running the import again once the missing piece is
    there, which the ``ON CONFLICT DO NOTHING`` insert alone would not do.

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

    for kind in (spain_ign.KIND_PROVINCIA, spain_ign.KIND_MUNICIPIO):
        parent_kind = spain_ign.TREE_KINDS[spain_ign.TREE_KINDS.index(kind) - 1]
        parent_code_length = spain_ign.CODE_LENGTHS[parent_kind]
        relinked += len(session.execute(
            text(RELINK_BY_CODE_SQL),
            {
                "provider_id": provider.id,
                "level": spain_ign.LEVELS[kind],
                "parent_code_length": parent_code_length,
                "padding": spain_ign.CODE_WIDTH - parent_code_length,
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
    shapefiles = find_shapefiles(args.directory)
    logger.info("Importing %d shapefile(s) as the %s edition",
                sum(len(paths) for paths in shapefiles.values()), args.edition)
    if not args.include_territories:
        logger.info("Excluding Gibraltar, the plazas de soberanía and the Isla de los Faisanes "
                    "(pass --include-territories to keep them)")

    common.require_tables(
        engine, ["admin_boundary", "ign_admin_boundary", "data_provider"], logger
    )
    common.create_staging_schema(engine, args.staging_schema)

    settings = common.resolve_database_settings(args)
    staging_tables = {
        kind: f"{args.staging_schema}.{table}" for kind, table in STAGING_TABLES.items()
    }
    for kind in spain_ign.TREE_KINDS:
        load_staging(shapefiles[kind], staging_tables[kind], args, settings, logger)

    with Session(engine) as session:
        provider = get_or_create_data_provider(session, args.edition, logger)
        country_id = find_country(session, logger)

        # Largest division first: each level's parent is a row the pass before it
        # wrote, so the order is not an optimisation but a requirement.
        imported = sum(
            transform(session, provider, kind, staging_tables[kind], country_id, args, logger)
            for kind in spain_ign.TREE_KINDS
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
    logger = logging.getLogger("ign-import")

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
