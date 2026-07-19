#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alembic migration environment for GisFIRE.

The database URL comes from the ``GISFIRE_DB_*`` environment variables (loaded
from ``.env`` by :mod:`src.settings`), never from ``alembic.ini``, so no
credentials are stored in a tracked file.

Autogenerate compares the live database against :attr:`src.data_model.Base.
metadata`. Importing :mod:`src.data_model` and :mod:`src.providers` registers
every model's table, so new models are picked up automatically as long as they
are imported in one of those two packages.

PostGIS needs a little help from GeoAlchemy2: its ``alembic_helpers`` filter out
the PostGIS-managed tables and views (``spatial_ref_sys``, ``geometry_columns``,
...) so they are not mistaken for tables to drop, and render geospatial columns
with the right ``geoalchemy2`` types in generated scripts.
"""

from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import src.providers  # noqa: F401  (registers the provider tables on Base.metadata)

from src.data_model import Base
from src.settings import database_url

# Alembic config object, giving access to alembic.ini.
config = context.config

# Inject the URL built from the environment, but only if the caller has not
# already set one. A caller that passes an explicit URL (the migration tests,
# which point Alembic at their ephemeral database) must win, otherwise it would
# be silently redirected to the real database from .env.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", database_url())

# Model metadata autogenerate diffs the database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection, emitting SQL to stdout.

    Used by ``alembic upgrade <rev> --sql`` to produce a script for a DBA to
    review and apply by hand.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=alembic_helpers.include_object,
        render_item=alembic_helpers.render_item,
        process_revision_directives=alembic_helpers.writer,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=alembic_helpers.include_object,
            render_item=alembic_helpers.render_item,
            process_revision_directives=alembic_helpers.writer,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
