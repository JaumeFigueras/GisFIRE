#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared plumbing for the import applications.

Every importer in :mod:`src.apps.imports` does the same four things around the
part that is actually specific to its source: resolve where the database is,
hand a file to ``ogr2ogr`` to land in a staging table, make sure the
:class:`~src.data_model.data_provider.DataProvider` row exists, and clean the
staging table up. That is what lives here.

What is *not* here is the mapping from staging table to model. It is different
for every source, it is the only interesting part of an importer, and pushing it
behind a shared abstraction would hide the one thing a reader of an import
application comes to read.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency,
not a Python package.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import zipfile

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from src.data_model.data_provider import DataProvider

#: Where the importers unload their staging tables. A schema of its own,
#: deliberately: a staging table in ``public`` would be picked up by Alembic
#: autogenerate, which would then write a ``DROP TABLE`` for it into the next
#: migration.
DEFAULT_STAGING_SCHEMA = "staging"


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def add_database_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the ``--db-*`` options, all defaulting to ``None``.

    ``None`` rather than the environment value, so that a setting left unset can
    be told apart from one set explicitly and only the unset ones fall back to
    the environment (see :func:`resolve_database_settings`).
    """
    group = parser.add_argument_group("database", "override the values taken from the environment")
    group.add_argument("--db-host", help="database host (env: GISFIRE_DB_HOST, default localhost)")
    group.add_argument("--db-port", help="database port (env: GISFIRE_DB_PORT, default 5432)")
    group.add_argument("--db-name", help="database name (env: GISFIRE_DB_NAME)")
    group.add_argument("--db-user", help="database user (env: GISFIRE_DB_USER)")
    group.add_argument("--db-password", help="database password (env: GISFIRE_DB_PASSWORD)")


def add_staging_arguments(parser: argparse.ArgumentParser, default_table: str) -> None:
    """Add the staging-table options, given the table name this importer uses."""
    group = parser.add_argument_group("staging")
    group.add_argument("--staging-schema", default=DEFAULT_STAGING_SCHEMA,
                       help=f"schema ogr2ogr unloads into (default: {DEFAULT_STAGING_SCHEMA})")
    group.add_argument("--staging-table", default=default_table,
                       help=f"table ogr2ogr unloads into (default: {default_table})")
    group.add_argument("--keep-staging", action="store_true",
                       help="do not drop the staging table afterwards, to inspect what was loaded")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the options every importer has: the ``ogr2ogr`` path and the log level."""
    parser.add_argument("--ogr2ogr", default="ogr2ogr",
                        help="path to the ogr2ogr binary (default: found on PATH)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")


# --------------------------------------------------------------------------
# Database settings
# --------------------------------------------------------------------------

def resolve_database_settings(args: argparse.Namespace) -> dict[str, str]:
    """Merge the command-line database arguments over the environment.

    Raises
    ------
    RuntimeError
        If a setting with no sensible default is missing from both, rather than
        silently connecting somewhere unintended.
    """
    name = args.db_name or os.getenv("GISFIRE_DB_NAME")
    user = args.db_user or os.getenv("GISFIRE_DB_USER")
    for key, value in (("name", name), ("user", user)):
        if not value:
            raise RuntimeError(
                f"No database {key} given. Pass --db-{key} or set GISFIRE_DB_{key.upper()} "
                f"(copy .env.example to .env and fill it in)."
            )
    return {
        "host": args.db_host or os.getenv("GISFIRE_DB_HOST", "localhost"),
        "port": args.db_port or os.getenv("GISFIRE_DB_PORT", "5432"),
        "name": str(name),
        "user": str(user),
        # An empty password is a legitimate choice (peer/trust authentication),
        # so it is not required and not defaulted away.
        "password": args.db_password or os.getenv("GISFIRE_DB_PASSWORD", ""),
    }


def database_url(settings: dict[str, str]) -> URL:
    """Build the SQLAlchemy URL, letting SQLAlchemy handle any escaping."""
    return URL.create("postgresql+psycopg", username=settings["user"], password=settings["password"],
                      host=settings["host"], port=int(settings["port"]), database=settings["name"])


def ogr_connection_string(settings: dict[str, str]) -> str:
    """Build the GDAL PostgreSQL connection string.

    The password is deliberately left out: it is passed to the subprocess through
    ``PGPASSWORD`` instead, so it never appears in the process arguments, where
    any user on the machine could read it out of ``ps``.
    """
    return (f"PG:host={settings['host']} port={settings['port']} "
            f"dbname={settings['name']} user={settings['user']}")


# --------------------------------------------------------------------------
# Reading the source file
# --------------------------------------------------------------------------

def shapefile_datasource(path: Path) -> tuple[str, str]:
    """Return the GDAL datasource and layer name for a shapefile, zipped or not.

    ``path`` may be the ``.shp`` itself, a directory holding one, or a ``.zip``
    holding one. A zip is *not* unpacked: GDAL's ``/vsizip/`` handler reads the
    shapefile straight out of it, so importing a 300 MB archive needs no
    temporary space at all.

    The layer name is not a parameter because a shapefile's layer is always the
    file's base name, and for these datasets that name carries the year
    (``Final_GlobFirev3_GWIS_MCD64A1__2021``), so it differs from file to file
    and could not have a useful default anyway.

    Returns
    -------
    tuple of (str, str)
        The datasource path to hand to ``ogr2ogr`` and the layer to read from it.

    Raises
    ------
    RuntimeError
        If the archive holds no ``.shp``, or more than one and so no unambiguous
        choice.
    """
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".shp")]
        if not members:
            raise RuntimeError(f"{path} contains no shapefile (.shp)")
        if len(members) > 1:
            raise RuntimeError(
                f"{path} contains {len(members)} shapefiles ({', '.join(sorted(members))}); "
                f"unzip it and pass the one you want"
            )
        # ``/vsizip/`` wants the member's path inside the archive appended to the
        # archive's own path. Members are always '/'-separated, whatever the
        # platform that wrote them.
        return f"/vsizip/{path}/{members[0]}", Path(members[0]).stem

    if path.is_dir():
        members = sorted(path.glob("*.shp"))
        if not members:
            raise RuntimeError(f"{path} contains no shapefile (.shp)")
        if len(members) > 1:
            raise RuntimeError(
                f"{path} contains {len(members)} shapefiles; pass the one you want"
            )
        return str(members[0]), members[0].stem

    return str(path), path.stem


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def load_staging_table(datasource: str, layer: str, staging_table: str,
                       args: argparse.Namespace, settings: dict[str, str],
                       logger: logging.Logger, geometry_type: str = "MULTIPOLYGON") -> None:
    """Copy one layer into the staging table with ``ogr2ogr``.

    Geometries are promoted to ``geometry_type`` and forced to EPSG:4326 to match
    the models, even for sources that already publish both — an import should not
    quietly depend on the source never changing.
    """
    command = [
        args.ogr2ogr,
        "-f", "PostgreSQL", ogr_connection_string(settings), datasource, layer,
        "-nln", staging_table,
        "-overwrite",
        "-nlt", geometry_type,
        "-t_srs", "EPSG:4326",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=fid",
    ]
    logger.info("Loading %s (layer %s) into %s with ogr2ogr", datasource, layer, staging_table)
    logger.debug("Running %s", " ".join(command))

    environment = dict(os.environ)
    if settings["password"]:
        environment["PGPASSWORD"] = settings["password"]

    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode != 0:
        # ogr2ogr writes its diagnostics to stderr and they are the only clue as
        # to what went wrong, so they are surfaced rather than swallowed.
        raise RuntimeError(
            f"ogr2ogr failed with exit code {result.returncode}:\n{result.stderr.strip()}"
        )
    if result.stderr.strip():
        logger.warning("ogr2ogr: %s", result.stderr.strip())


def create_staging_schema(engine: Engine, schema: str) -> None:
    """Create the staging schema if it is not there yet, in its own transaction."""
    with Session(engine) as session:
        session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        session.commit()


def drop_staging_table(session: Session, staging_table: str, logger: logging.Logger) -> None:
    session.execute(text(f"DROP TABLE IF EXISTS {staging_table}"))
    logger.debug("Dropped staging table %s", staging_table)


# --------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------

def get_or_create_data_provider(session: Session, name: str, product: str, full_name: str,
                                url: str, logger: logging.Logger) -> DataProvider:
    """Return the provider row for ``(name, product)``, creating it on first import.

    Looked up by the pair, which is what is unique: an agency publishes more than
    one dataset and each is its own provider row.
    """
    existing: DataProvider | None = session.scalar(
        select(DataProvider).where(DataProvider.name == name, DataProvider.product == product)
    )
    if existing is not None:
        logger.debug("Using existing data provider %s", existing)
        return existing

    provider = DataProvider(name=name, product=product, full_name=full_name, url=url)
    session.add(provider)
    session.flush()
    logger.info("Created data provider %s / %s", name, product)
    return provider
