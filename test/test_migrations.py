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
from sqlalchemy.exc import IntegrityError

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
    "v_darpa_wildfire_4326": ("perimeter", "MULTIPOLYGON", 4326),
    "v_darpa_wildfire_25831": ("perimeter", "MULTIPOLYGON", 25831),
    "v_rediam_wildfire_4326": ("perimeter", "MULTIPOLYGON", 4326),
    "v_rediam_wildfire_25830": ("perimeter", "MULTIPOLYGON", 25830),
    "v_rediam_ignition": ("geometry", "POINT", 4326),
    "v_greece_ffa_ignition": ("geometry", "POINT", 4326),
    # The second POINT on a wildfire view, after v_egif_wildfire and for the same
    # reason: the Greek Fire Service publishes no perimeter either. See revision
    # 7d2e51b8c39f — and note that this view shows only the fifth of the dataset
    # that has a point at all, no year before 2020 publishing one.
    "v_greece_ffa_wildfire": ("geometry", "POINT", 4326),
    "v_nbac_wildfire_4326": ("perimeter", "MULTIPOLYGON", 4326),
    "v_nbac_wildfire_3978": ("perimeter", "MULTIPOLYGON", 3978),
    "v_nfdb_ignition": ("geometry", "POINT", 4326),
    # The third POINT on a wildfire view, after v_egif_wildfire and
    # v_greece_ffa_wildfire: the Canadian agencies publish a location, not a shape.
    # Unlike the Greek one this LEFT JOINs its ignition, so a report with no usable
    # coordinate is a feature that does not draw rather than a row that vanishes.
    "v_nfdb_wildfire": ("geometry", "POINT", 4326),
    # The only perimeter provider with a single wildfire view. ICNF, DARPA, REDIAM
    # and NBAC each get a pair because each publishes on a national grid kept beside
    # the EPSG:4326 reprojection; CONAFOR publishes in EPSG:4326 already, so there is
    # no second CRS to expose. See revision 6c2e94ab13d8.
    "v_conafor_wildfire": ("perimeter", "MULTIPOLYGON", 4326),
    "v_inab_ignition": ("geometry", "POINT", 4326),
    # The fourth POINT on a wildfire view, after v_egif_wildfire,
    # v_greece_ffa_wildfire and v_nfdb_wildfire: INAB publishes no perimeter — nor
    # any burnt area at all — so the fire is mapped where it was reported. See
    # revision c5e91a2b8d43.
    "v_inab_wildfire": ("geometry", "POINT", 4326),
    # Chile's CONAF — seven views, and the first provider needing more than two per
    # spatial table. ICNF, DARPA, REDIAM and NBAC each publish on one national grid
    # and get a 4326 view plus one grid view; Chile publishes the mainland on
    # EPSG:32719 and Easter Island on EPSG:32712, and a view has one geometry column
    # with one SRID, so each spatial table needs three. See revision 9d4a06e3f2b8.
    #
    # The two grid views of a pair are disjoint, not alternative renderings: the
    # 32719 one carries the 95,625 mainland rows and the 32712 one the 243 Rapa Nui
    # rows. Only the 4326 view of each pair shows the whole dataset.
    "v_conaf_ignition_4326": ("geometry", "POINT", 4326),
    "v_conaf_ignition_32719": ("geometry", "POINT", 32719),
    "v_conaf_ignition_32712": ("geometry", "POINT", 32712),
    # The fifth POINT on a wildfire view, after v_egif_wildfire,
    # v_greece_ffa_wildfire, v_nfdb_wildfire and v_inab_wildfire: CONAF's seasonal
    # archive publishes a location, not a shape. Unlike the Canadian one it INNER
    # JOINs its ignition, because conaf_wildfire.ignition_id is NOT NULL.
    "v_conaf_wildfire": ("geometry", "POINT", 4326),
    "v_conaf_magnitud_wildfire_4326": ("perimeter", "MULTIPOLYGON", 4326),
    "v_conaf_magnitud_wildfire_32719": ("perimeter", "MULTIPOLYGON", 32719),
    "v_conaf_magnitud_wildfire_32712": ("perimeter", "MULTIPOLYGON", 32712),
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


def test_the_match_method_constraint_accepts_every_method(alembic_config):
    """The migrations' CHECK list and the model's ``MATCH_METHODS`` agree.

    ``compare_metadata`` does not compare check constraints, so the drift test above
    passes happily while a method added to the model is refused by the database the
    migrations built — which is a failure that only shows up in a real run, at the
    moment the new rule first fires. This closes that gap by inserting one fire per
    method and letting the constraint judge.
    """
    from src.providers.catalonia_darpa.wildfire import MATCH_METHOD_CONFIDENCE
    from src.providers.catalonia_darpa.wildfire import MATCH_METHODS

    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('DARPA', 'Perimetres', 'Departament') RETURNING id")).scalar()
        egif_provider = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('EGIF', 'EGIF', 'MITECO') RETURNING id")).scalar()
        egif_parent = connection.execute(text(
            "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
            "VALUES ('egif_wildfire', :p, '1994-08-11T10:00:00Z', 'Europe/Madrid') "
            "RETURNING id"), {"p": egif_provider}).scalar()
        connection.execute(text(
            "INSERT INTO egif_wildfire (id, report_number, campaign, province_ine_code) "
            "VALUES (:id, '1994080496', 1994, '08')"), {"id": egif_parent})

        for index, method in enumerate(MATCH_METHODS):
            parent = connection.execute(text(
                "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
                "VALUES ('darpa_wildfire', :p, '1994-08-11T00:00:00Z', 'Europe/Madrid') "
                "RETURNING id"), {"p": provider_id}).scalar()
            connection.execute(text(
                "INSERT INTO darpa_wildfire (id, source_layer, code, fire_date, year, "
                "municipality_name, part_count, egif_wildfire_id, match_method, "
                "match_confidence, matched_at) "
                "VALUES (:id, 'incendis1994', :code, '1994-08-11', 1994, 'Subirats', 1, "
                ":egif, :method, :confidence, now())"),
                {"id": parent, "code": f"89449{index}", "egif": egif_parent,
                 "method": method, "confidence": MATCH_METHOD_CONFIDENCE[method]})

    with engine.connect() as connection:
        stored = set(connection.scalars(text(
            "SELECT match_method FROM darpa_wildfire")))
    engine.dispose()

    assert stored == set(MATCH_METHODS)


def test_the_rediam_match_method_constraint_accepts_every_method(alembic_config):
    """The migrations' CHECK list and the model's ``MATCH_METHODS`` agree.

    The Andalusian half of the same gap the test above closes for Catalonia:
    ``compare_metadata`` does not compare check constraints, so a method added to the
    model would pass the drift test and be refused by the database at the moment the
    new rule first fires.

    The list here is six values and not Catalonia's eight, and that is the point of
    the last assertion: ``date`` and ``date_name`` are the branches the Catalan
    cascade takes when a code carries no province, every Andalusian code carries one,
    and a database that accepted them would be accepting a binding this cascade must
    never write.
    """
    from src.providers.andalusia_rediam.wildfire import MATCH_METHOD_CONFIDENCE
    from src.providers.andalusia_rediam.wildfire import MATCH_METHODS

    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('REDIAM', 'Perimetros', 'Red de Informacion Ambiental') "
            "RETURNING id")).scalar()
        egif_provider = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('EGIF', 'EGIF', 'MITECO') RETURNING id")).scalar()
        egif_parent = connection.execute(text(
            "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
            "VALUES ('egif_wildfire', :p, '2022-08-01T10:00:00Z', 'Europe/Madrid') "
            "RETURNING id"), {"p": egif_provider}).scalar()
        connection.execute(text(
            "INSERT INTO egif_wildfire (id, report_number, campaign, province_ine_code) "
            "VALUES (:id, '2022040091', 2022, '04')"), {"id": egif_parent})

        for index, method in enumerate(MATCH_METHODS):
            parent = connection.execute(text(
                "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
                "VALUES ('rediam_wildfire', :p, '2022-08-01T00:00:00Z', 'Europe/Madrid') "
                "RETURNING id"), {"p": provider_id}).scalar()
            connection.execute(text(
                "INSERT INTO rediam_wildfire (id, source_layer, code, fire_date, year, "
                "municipality_name, province_name, part_count, egif_wildfire_id, "
                "match_method, match_confidence, matched_at) "
                "VALUES (:id, 'PERIMETROS_COR_2008_2025', :code, '2022-08-01', 2022, "
                "'DALIAS', 'Almeria', 1, :egif, :method, :confidence, now())"),
                {"id": parent, "code": f"202204009{index}", "egif": egif_parent,
                 "method": method, "confidence": MATCH_METHOD_CONFIDENCE[method]})

    with engine.connect() as connection:
        stored = set(connection.scalars(text(
            "SELECT match_method FROM rediam_wildfire")))
    engine.dispose()

    assert stored == set(MATCH_METHODS)
    # The two Catalan-only rules are refused, not merely unused.
    assert {"date", "date_name"} & stored == set()


def _a_conaf_report(connection, provider_id, *, number, region_code="08"):
    """Insert one CONAF report and its ignition, returning the report's id.

    Four rows for one fire — ``ignition``, ``conaf_ignition``, ``wildfire``,
    ``conaf_wildfire`` — because both halves of the pair use joined table
    inheritance. The point is on the mainland grid, which is what
    ``ck_conaf_ignition_one_grid`` wants exactly one of.
    """
    ignition_parent = connection.execute(text(
        "INSERT INTO ignition (type, data_provider_id, geometry, date_time, time_zone) "
        "VALUES ('conaf_ignition', :p, ST_SetSRID(ST_MakePoint(-72.5, -36.5), 4326), "
        "'2019-01-15T18:30:00Z', 'America/Santiago') RETURNING id"),
        {"p": provider_id}).scalar()
    connection.execute(text(
        "INSERT INTO conaf_ignition (id, season_start_year, number, region_code, "
        "geometry_utm19s) VALUES (:id, 2018, :number, :region_code, "
        "ST_Transform(ST_SetSRID(ST_MakePoint(-72.5, -36.5), 4326), 32719))"),
        {"id": ignition_parent, "number": number, "region_code": region_code})
    parent = connection.execute(text(
        "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
        "VALUES ('conaf_wildfire', :p, '2019-01-15T18:30:00Z', 'America/Santiago') "
        "RETURNING id"), {"p": provider_id}).scalar()
    connection.execute(text(
        "INSERT INTO conaf_wildfire (id, ignition_id, season, season_start_year, "
        "number, name, region_code, date_time_precision, area_totals_agree) "
        "VALUES (:id, :ignition, '2018-2019', 2018, :number, 'EL BOLDO', "
        ":region_code, 'minute', true)"),
        {"id": parent, "ignition": ignition_parent, "number": number,
         "region_code": region_code})
    return parent


def test_the_conaf_match_method_constraint_accepts_every_method(alembic_config):
    """The migrations' CHECK list and the model's ``MATCH_METHODS`` agree.

    The Chilean half of the gap the two tests above close for Catalonia and
    Andalusia: ``compare_metadata`` does not compare check constraints, so a method
    added to the model would pass the drift test and be refused by the database the
    migrations built, at the moment the new rule first fires.

    The constraint arrives in its own revision, ``2c9f4e7b81a6``, rather than with
    the tables in ``268b915dce92`` — the vocabulary was the binder's and the binder
    did not exist yet — so this test is also what proves that second revision ran.
    """
    from src.providers.chile_conaf_magnitud import MATCH_METHOD_CONFIDENCE
    from src.providers.chile_conaf_magnitud import MATCH_METHODS

    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        report_provider = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('CONAF', 'Incendios forestales por temporada', "
            "'Corporacion Nacional Forestal') RETURNING id")).scalar()
        perimeter_provider = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('CONAF', 'Incendios forestales de magnitud', "
            "'Corporacion Nacional Forestal') RETURNING id")).scalar()

        for index, method in enumerate(MATCH_METHODS):
            # One report each, because the binder never binds two perimeters to one
            # report and a test that did would be pinning the wrong behaviour.
            report = _a_conaf_report(connection, report_provider, number=200 + index)
            parent = connection.execute(text(
                "INSERT INTO wildfire (type, data_provider_id, start_date_time, "
                "time_zone, perimeter) VALUES ('conaf_magnitud_wildfire', :p, "
                "'2019-01-15T18:30:00Z', 'America/Santiago', "
                "ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(-72.5, -36.5), 4326), 0.01))) "
                "RETURNING id"), {"p": perimeter_provider}).scalar()
            connection.execute(text(
                "INSERT INTO conaf_magnitud_wildfire (id, season, season_start_year, "
                "number, name, region_code, part_count, date_time_precision, "
                "perimeter_utm19s, conaf_wildfire_id, match_method, match_confidence, "
                "matched_at) VALUES (:id, '2018-2019', 2018, :number, 'EL BOLDO', '08', "
                "1, 'minute', ST_Multi(ST_Buffer(ST_Transform(ST_SetSRID("
                "ST_MakePoint(-72.5, -36.5), 4326), 32719), 500)), :report, :method, "
                ":confidence, now())"),
                {"id": parent, "number": 200 + index, "report": report,
                 "method": method, "confidence": MATCH_METHOD_CONFIDENCE[method]})

    with engine.connect() as connection:
        stored = set(connection.scalars(text(
            "SELECT match_method FROM conaf_magnitud_wildfire")))
    engine.dispose()

    assert stored == set(MATCH_METHODS)
    # The Iberian binders' rules are refused, not merely unused: Chile matches on a
    # published running number and a name, never on a report code or a bare date.
    assert {"date", "date_name", "code", "code_year"} & stored == set()


def test_a_conaf_geometry_belongs_to_exactly_one_grid(alembic_config):
    """``conaf_ignition`` refuses a point on both grids, and a point on neither.

    Chile is the only provider in the schema publishing on two projected CRSs — the
    mainland on EPSG:32719 and Easter Island on EPSG:32712 — so it is the only one
    whose grid column is a pair. ``ck_conaf_ignition_one_grid`` is what keeps that
    pair from becoming a row that is on both grids at once, which would be two
    different claims about where the fire was, or on neither, which would be a point
    row with no published point in it.

    Written against the migrated schema rather than against ``create_all`` because
    the ``CHECK`` uses ``num_nonnulls``, and a constraint that renders differently
    through Alembic than through the ORM would pass a model test and fail here.
    """
    config, url = alembic_config
    upgrade(config, "head")

    engine = create_engine(url)
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('CONAF', 'Incendios forestales por temporada', "
            "'Corporacion Nacional Forestal') RETURNING id")).scalar()

        def an_ignition(utm19s: str | None, utm12s: str | None):
            parent = connection.execute(text(
                "INSERT INTO ignition (type, data_provider_id, geometry, date_time, "
                "time_zone) VALUES ('conaf_ignition', :p, "
                "ST_SetSRID(ST_MakePoint(-72.5, -36.5), 4326), "
                "'2019-01-15T18:30:00Z', 'America/Santiago') RETURNING id"),
                {"p": provider_id}).scalar()
            connection.execute(text(
                "INSERT INTO conaf_ignition (id, season_start_year, geometry_utm19s, "
                "geometry_utm12s) VALUES (:id, 2018, "
                "ST_GeomFromEWKT(CAST(:utm19s AS text)), "
                "ST_GeomFromEWKT(CAST(:utm12s AS text)))"),
                {"id": parent, "utm19s": utm19s, "utm12s": utm12s})

        mainland = "SRID=32719;POINT(722000 5957000)"
        rapa_nui = "SRID=32712;POINT(660000 6998000)"

        # One grid: accepted, once for each.
        an_ignition(mainland, None)
        an_ignition(None, rapa_nui)

    for utm19s, utm12s in ((mainland, rapa_nui), (None, None)):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                provider_id = connection.execute(text(
                    "SELECT id FROM data_provider WHERE name = 'CONAF' LIMIT 1")).scalar()
                parent = connection.execute(text(
                    "INSERT INTO ignition (type, data_provider_id, geometry, date_time, "
                    "time_zone) VALUES ('conaf_ignition', :p, "
                    "ST_SetSRID(ST_MakePoint(-72.5, -36.5), 4326), "
                    "'2019-01-15T18:30:00Z', 'America/Santiago') RETURNING id"),
                    {"p": provider_id}).scalar()
                connection.execute(text(
                    "INSERT INTO conaf_ignition (id, season_start_year, geometry_utm19s, "
                    "geometry_utm12s) VALUES (:id, 2018, "
                    "ST_GeomFromEWKT(CAST(:utm19s AS text)), "
                    "ST_GeomFromEWKT(CAST(:utm12s AS text)))"),
                    {"id": parent, "utm19s": utm19s, "utm12s": utm12s})

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM conaf_ignition")).scalar() == 2
    engine.dispose()
