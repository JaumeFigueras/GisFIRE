#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Alembic migrations.

The test suite builds its schema with ``Base.metadata.create_all()``, so the
migrations are never exercised by the model tests. Nothing would then catch the
usual mistake: changing a model and forgetting to generate the migration that
goes with it. These tests run the migrations against a real (ephemeral)
PostgreSQL and compare the result with the models.
"""

import pytest

from alembic.autogenerate import compare_metadata
from alembic.command import downgrade
from alembic.command import upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy import text

import src.providers  # noqa: F401  (registers the provider tables on Base.metadata)

from src.data_model import Base
from src.settings import ROOT_DIR


@pytest.fixture
def alembic_config(postgresql):
    """An Alembic ``Config`` pointing at the ephemeral test database."""
    info = postgresql.info
    url = f"postgresql+psycopg://{info.user}:{info.password or ''}@{info.host}:{info.port}/{info.dbname}"
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    # Overrides the URL that alembic/env.py builds from the environment, so the
    # tests can never touch the real database configured in .env.
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config, url


def test_migrations_upgrade_to_head(alembic_config):
    """``alembic upgrade head`` builds the whole schema from an empty database."""
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert {"data_provider", "wildfire", "gwis_wildfire"} <= tables


def test_migrations_match_the_models(alembic_config):
    """After upgrading, the database matches ``Base.metadata`` exactly.

    A failure here means a model was changed without generating the matching
    revision — run ``make migration M="..."``.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": alembic_helpers.include_object,
                "compare_type": True,
                "compare_server_default": True,
            },
        )
        differences = compare_metadata(context, Base.metadata)
    engine.dispose()

    assert differences == []


@pytest.mark.parametrize("table", ["wildfire", "ignition"])
def test_the_sequence_backed_ids_have_a_usable_sequence(alembic_config, table):
    """The wildfire importers draw ids with ``nextval(pg_get_serial_sequence(...))``.

    ``compare_metadata`` does not catch a primary key created as a plain integer
    instead of a ``SERIAL``: the difference is a missing owned sequence, not a
    type or a default the model states explicitly. So the drift test would pass
    while the import fails on ``nextval(NULL)``. This checks the sequence directly
    on the schema the *migrations* build, not the one ``create_all`` builds.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table}
        ).scalar()
        assert sequence is not None, f"{table}.id has no owned sequence"
        # And it actually advances, which is all the transform asks of it.
        assert connection.execute(text(f"SELECT nextval('{sequence}')")).scalar() >= 1
    engine.dispose()


def test_migrations_downgrade_to_base(alembic_config):
    """Every revision can be undone, leaving no GisFIRE table behind."""
    config, url = alembic_config
    upgrade(config, "head")
    downgrade(config, "base")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert "data_provider" not in tables
    assert "wildfire" not in tables
    assert "gwis_wildfire" not in tables
