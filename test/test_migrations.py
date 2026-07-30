#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Alembic migrations.

The test suite builds its schema with ``Base.metadata.create_all()``, so the
migrations are never exercised by the model tests. Nothing would then catch the
usual mistake: changing a model and forgetting to generate the migration that
goes with it. These tests run the migrations against a real (ephemeral)
PostgreSQL and compare the result with the models.
"""

import datetime

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


#: The QGIS views the migrations create, each with the geometry column it
#: exposes and the type and SRID that column must have. Keeping the expectation
#: here rather than reading it back from the migration is the point: a view whose
#: geometry stops being detectable is a broken QGIS layer, and the test has to
#: fail on it instead of following the change.
VIEWS = {
    "v_gwis_wildfire": ("perimeter", "MULTIPOLYGON", 4326),
    "v_gfa_wildfire": ("perimeter", "MULTIPOLYGON", 4326),
    "v_gfa_ignition": ("geometry", "POINT", 4326),
    "v_icnf_wildfire_4326": ("perimeter", "MULTIPOLYGON", 4326),
    "v_icnf_wildfire_3763": ("perimeter", "MULTIPOLYGON", 3763),
    "v_egif_ignition": ("geometry", "POINT", 4326),
    # A POINT on a wildfire view, alone among them: EGIF publishes no perimeter,
    # so the fire is mapped at the point it started. See revision 9a3d61c07e84.
    "v_egif_wildfire": ("geometry", "POINT", 4326),
}


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


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_the_dataset_views_are_queryable(alembic_config, view):
    """Each dataset view exists after upgrading and its ``SELECT`` runs.

    ``CREATE VIEW`` already parses the query against the real schema, so a view
    naming a column that does not exist fails the upgrade rather than this
    assertion. What is checked here is the step after that: the join actually
    executes, and the view is a view rather than something the recipe left half
    made.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        assert view in set(inspect(engine).get_view_names())
        # Empty database, so the count is 0 — running the query is the assertion.
        assert connection.execute(text(f"SELECT count(*) FROM {view}")).scalar() == 0
    engine.dispose()


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_the_dataset_views_carry_a_qgis_usable_key(alembic_config, view):
    """Every view exposes ``id`` as a plain integer.

    QGIS cannot infer a primary key for a view: it needs a unique integer column
    to identify features with, and picks ``id`` here. A view that returned it as
    ``bigint``, or dropped it, would still load in QGIS and then misbehave on
    selection and editing, so it is checked explicitly.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        data_type = connection.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :view AND column_name = 'id'"
            ),
            {"view": view},
        ).scalar()
    engine.dispose()

    assert data_type == "integer"


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_the_dataset_views_register_their_geometry(alembic_config, view):
    """PostGIS resolves each view's geometry column, with the right type and SRID.

    This is the property the views are written around. Selecting a geometry
    column straight through keeps its type modifier, which is what puts the view
    in ``geometry_columns`` and lets QGIS detect geometry type and SRID on its
    own. Wrap that column in a function without casting the result back and the
    entry silently degrades to an untyped ``GEOMETRY`` with SRID 0 — the view
    still loads, but only after the user fills the two in by hand.
    """
    config, url = alembic_config
    upgrade(config, "head")

    column, geometry_type, srid = VIEWS[view]
    engine = create_engine(url)
    with engine.connect() as connection:
        registered = connection.execute(
            text(
                "SELECT type, srid FROM geometry_columns "
                "WHERE f_table_name = :view AND f_geometry_column = :column"
            ),
            {"view": view, "column": column},
        ).one_or_none()
    engine.dispose()

    assert registered is not None, f"{view}.{column} is not registered in geometry_columns"
    assert tuple(registered) == (geometry_type, srid)


def test_a_dataset_view_flattens_the_two_tables(alembic_config):
    """A wildfire inserted across the inheritance comes back as one view row.

    The other view tests check shape; this one checks the join is right. The
    parent's columns, the subclass's identifier and the provider's name have to
    arrive on a single row, and ``start_date_time_local`` has to give back the
    wall-clock reading the provider published — 2021-07-29 local from the instant
    ``2021-07-29T07:00:00Z`` and ``America/Los_Angeles``, the worked example in
    the ``wildfire`` module docstring.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        provider_id = connection.execute(
            text(
                "INSERT INTO data_provider (name, product, full_name) "
                "VALUES ('GWIS', 'Global Wildfire Database', 'Global Wildfire Information System') "
                "RETURNING id"
            )
        ).scalar()
        wildfire_id = connection.execute(
            text(
                "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone, perimeter) "
                "VALUES ('gwis_wildfire', :provider_id, '2021-07-29T07:00:00Z', 'America/Los_Angeles', "
                "ST_GeomFromText('MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)))', 4326)) "
                "RETURNING id"
            ),
            {"provider_id": provider_id},
        ).scalar()
        connection.execute(
            text("INSERT INTO gwis_wildfire (id, gwis_id) VALUES (:id, '24935861')"),
            {"id": wildfire_id},
        )

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT id, gwis_id, data_provider_name, admin_boundary_name, "
                "start_date_time_local, end_date_time_local, ST_SRID(perimeter) "
                "FROM v_gwis_wildfire"
            )
        ).one()
    engine.dispose()

    assert row.id == wildfire_id
    assert row.gwis_id == "24935861"
    assert row.data_provider_name == "GWIS"
    # LEFT JOIN: an unresolved boundary must not drop the fire from the view.
    assert row.admin_boundary_name is None
    assert row.start_date_time_local == datetime.datetime(2021, 7, 29, 0, 0)
    # NULL in, NULL out — the fire is still burning, not extinguished at epoch.
    assert row.end_date_time_local is None
    assert row.st_srid == 4326


def test_the_egif_wildfire_view_keeps_a_fire_that_has_no_coordinate(alembic_config):
    """A *parte* with no published point must still be a row in the layer.

    ``v_egif_wildfire`` inner-joined the ignition while ``ignition_id`` was
    NOT NULL. Now that 22,855 fires of the 2004-2023 archive are known to publish
    no coordinate, that join would drop 9% of the data from the view while leaving
    it looking perfectly healthy — the failure mode a test has to exist for. The
    fire arrives with a NULL geometry instead: a feature with no location rather
    than no feature.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        provider_id = connection.execute(
            text(
                "INSERT INTO data_provider (name, product, full_name) "
                "VALUES ('EGIF', 'Estadistica General de Incendios Forestales', 'MITECO') "
                "RETURNING id"
            )
        ).scalar()
        wildfire_id = connection.execute(
            text(
                "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
                "VALUES ('egif_wildfire', :provider_id, '2005-08-14T13:00:00Z', 'Europe/Madrid') "
                "RETURNING id"
            ),
            {"provider_id": provider_id},
        ).scalar()
        connection.execute(
            text(
                "INSERT INTO egif_wildfire (id, report_number, campaign, province_ine_code, "
                "ignition_id) VALUES (:id, '2005330001', 2005, '33', NULL)"
            ),
            {"id": wildfire_id},
        )

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT id, report_number, ignition_id, utm_zone, datum, datum_code, "
                "geometry, has_full_report FROM v_egif_wildfire"
            )
        ).one()
    engine.dispose()

    assert row.id == wildfire_id
    assert row.report_number == "2005330001"
    assert row.ignition_id is None
    assert row.utm_zone is None
    # No datum either: the XML publishes none before the 2014-2016 campaigns.
    assert (row.datum, row.datum_code) == (None, None)
    assert row.geometry is None
    # Excel-only provenance: no report row, so no XML has been read for this fire.
    assert row.has_full_report is False


def test_migrations_downgrade_to_base(alembic_config):
    """Every revision can be undone, leaving no GisFIRE table or view behind."""
    config, url = alembic_config
    upgrade(config, "head")
    downgrade(config, "base")

    engine = create_engine(url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    views = set(inspector.get_view_names())
    engine.dispose()

    assert "data_provider" not in tables
    assert "wildfire" not in tables
    assert "gwis_wildfire" not in tables
    assert views & set(VIEWS) == set()
