#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the MeteoCat lightning import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on extracts written like the delivery. What is being tested is
what this dataset makes hard: that a **UTC year** is the unit replaced, since
nothing identifies a stroke; that the published ETRS89 point is stored as published
beside its EPSG:4326 reprojection; that the flash numbering reaches the database;
and that the country is resolved by a spatial join, strokes at sea having none.
"""

import datetime
import logging

from pathlib import Path

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.lightnings.catalonia_meteocat import import_lightnings as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import catalonia_meteocat
from src.providers import ocha
from src.providers.catalonia_meteocat.lightning import MeteocatLightning

from .conftest import CATALONIA_WKT
from .conftest import ROWS_2009
from .conftest import ROWS_2010
from .conftest import extract_2009
from .conftest import extract_2010
from .conftest import write_extract

UTC = datetime.timezone.utc


@pytest.fixture
def database(postgresql):
    """An empty GisFIRE schema on an ephemeral PostgreSQL, and its URL."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, url
    engine.dispose()


@pytest.fixture
def catalonia(database):
    """An OCHA country boundary roughly the shape of Catalonia's coast."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        boundary = AdminBoundary(data_provider_id=provider.id, source_id="ESP", level=0,
                                 name="Spain", geometry=f"SRID=4326;{CATALONIA_WKT}")
        session.add(boundary)
        session.commit()
        return boundary.id


def run(url: str, *paths: Path, extra: list[str] | None = None, directory: Path | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    source = ["-d", str(directory)] if directory is not None else ["-s", *[str(path) for path in paths]]
    argv = [*source,
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def strokes(engine) -> list[MeteocatLightning]:
    """Every stroke, by instant and then by flash numbering."""
    with Session(engine) as session:
        return session.scalars(select(MeteocatLightning).order_by(
            MeteocatLightning.date_time, MeteocatLightning.stroke_index)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


def stroke_at(engine, current: float) -> MeteocatLightning:
    """The one stroke with this peak current (they are all different)."""
    with Session(engine) as session:
        return session.scalars(select(MeteocatLightning)
                               .where(MeteocatLightning.peak_current == current)).one()


# --------------------------------------------------------------------------
# An extract round trips
# --------------------------------------------------------------------------

def test_an_extract_is_imported_whole(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert count(engine, "meteocat_lightning") == len(ROWS_2009)


def test_the_provider_row_is_created_once(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    with Session(engine) as session:
        providers = session.scalars(select(DataProvider)).all()
    assert len(providers) == 1
    provider = providers[0]
    assert (provider.name, provider.product) == (catalonia_meteocat.PROVIDER_NAME,
                                                 catalonia_meteocat.PROVIDER_PRODUCT)
    assert provider.full_name == catalonia_meteocat.PROVIDER_FULL_NAME
    assert provider.description == catalonia_meteocat.PROVIDER_DESCRIPTION
    assert provider.url == catalonia_meteocat.PROVIDER_URL


def test_a_version_2_stroke_is_stored_as_published(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, -30.5)
    assert stroke.type == "meteocat_lightning"
    assert stroke.date_time == datetime.datetime(2009, 9, 15, 14, 2, 11, 500000, tzinfo=UTC)
    assert stroke.cloud_to_ground is True
    assert (stroke.network_version, stroke.flash_id) == (2, 1832764)
    assert stroke.chi_squared == 1.2
    assert (stroke.ellipse_major_axis, stroke.ellipse_minor_axis) == (1800.0, 500.0)
    assert stroke.ellipse_angle is None
    assert stroke.number_of_sensors == 3
    assert stroke.municipality_code is None


def test_a_version_1_stroke_stores_not_recorded_as_null(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, 12.198)
    assert stroke.network_version == 1
    assert stroke.number_of_sensors is None
    assert stroke.chi_squared is None
    assert stroke.municipality_code == "080193"
    assert stroke.date_time == datetime.datetime(2009, 1, 2, 5, 32, 19, 3386, tzinfo=UTC)


def test_the_point_is_stored_as_published_and_in_4326(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, -30.5)
    assert to_shape(stroke.geometry_etrs89) == Point(1.51, 41.61)
    reprojected = to_shape(stroke.geometry)
    assert reprojected.distance(Point(1.51, 41.61)) < 1e-5
    with Session(engine) as session:
        srids = session.execute(text(
            "SELECT DISTINCT ST_SRID(l.geometry), ST_SRID(m.geometry_etrs89) "
            "FROM lightning l JOIN meteocat_lightning m ON m.id = l.id")).all()
    assert srids == [(4326, 4258)]


def test_an_intra_cloud_stroke_is_stored_as_such(database, tmp_path):
    engine, url = database
    assert run(url, extract_2010(tmp_path)) == 0

    assert stroke_at(engine, 40.1).cloud_to_ground is False


# --------------------------------------------------------------------------
# Flashes
# --------------------------------------------------------------------------

def test_the_flash_numbering_is_stored(database, tmp_path):
    """Version 1's flash 910429 is published 2nd, 1st, 3rd."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    numbering = [(stroke_at(engine, current).stroke_index, stroke_at(engine, current).multiplicity)
                 for current in (-2.241, -1.532, 0.71)]
    assert numbering == [(1, 3), (2, 3), (3, 3)]


def test_the_same_flash_id_in_two_networks_is_numbered_separately(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    assert (stroke_at(engine, -15.2).network_version, stroke_at(engine, -15.2).multiplicity) == (1, 1)
    assert [(stroke_at(engine, c).stroke_index, stroke_at(engine, c).multiplicity)
            for c in (-30.5, -18.1)] == [(1, 2), (2, 2)]


def test_first_strokes_are_one_per_flash(database, tmp_path):
    """``stroke_index = 1`` is what a flash-density count selects."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    with Session(engine) as session:
        first = session.scalar(text("SELECT count(*) FROM meteocat_lightning WHERE stroke_index = 1"))
        flashes = session.scalar(text(
            "SELECT count(*) FROM (SELECT DISTINCT network_version, flash_id "
            "FROM meteocat_lightning) AS f"))
    assert first == flashes == 6


# --------------------------------------------------------------------------
# The administrative boundary
# --------------------------------------------------------------------------

def test_strokes_on_land_get_the_country_and_at_sea_none(database, catalonia, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    on_land = {12.198, -15.2, -30.5, -18.1}
    for stroke in strokes(engine):
        expected = catalonia if stroke.peak_current in on_land else None
        assert stroke.admin_boundary_id == expected, stroke.peak_current


def test_without_boundaries_the_strokes_are_still_imported(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert all(stroke.admin_boundary_id is None for stroke in strokes(engine))
    assert "boundaries" in caplog.text


# --------------------------------------------------------------------------
# The year is the unit
# --------------------------------------------------------------------------

def test_importing_a_year_again_replaces_it(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    first_ids = {stroke.id for stroke in strokes(engine)}
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert count(engine, "meteocat_lightning") == len(ROWS_2009)
    assert first_ids.isdisjoint({stroke.id for stroke in strokes(engine)})


def test_importing_a_year_leaves_the_others_alone(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009) + len(ROWS_2010)
    years = {stroke.date_time.astimezone(UTC).year for stroke in strokes(engine)}
    assert years == {2009, 2010}


def test_the_year_boundary_is_utc(database, tmp_path):
    """The last stroke of 2009 and the first of 2010 are 73 seconds apart."""
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 0
    write_extract(tmp_path / "late.csv", [ROWS_2009[-1]])
    assert run(url, tmp_path / "late.csv") == 0

    # Re-importing 2009 from a one-stroke file leaves exactly that stroke in 2009,
    # and the stroke at 2010-01-01 00:00:00.000022 UTC untouched.
    assert count(engine, "lightning") == 1 + len(ROWS_2010)


def test_a_year_filter_imports_only_that_year(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path), extra=["--year", "2010"]) == 0

    assert {stroke.date_time.astimezone(UTC).year for stroke in strokes(engine)} == {2010}


def test_strokes_of_other_providers_are_not_deleted(database, tmp_path):
    """Replacing a year deletes MeteoCat's strokes in it, nobody else's."""
    engine, url = database
    with engine.begin() as connection:
        other = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('Other', 'Network', 'Other network') RETURNING id")).scalar()
        connection.execute(text(
            "INSERT INTO lightning (type, data_provider_id, date_time, geometry) "
            "VALUES ('lightning', :p, '2009-06-01T12:00:00Z', "
            "ST_GeomFromText('POINT(2 41)', 4326))"), {"p": other})
    assert run(url, extract_2009(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009) + 1


# --------------------------------------------------------------------------
# A directory, a dry run and the ways a run is refused
# --------------------------------------------------------------------------

def test_a_directory_imports_every_extract_and_skips_other_csvs(database, tmp_path):
    engine, url = database
    extract_2009(tmp_path)
    extract_2010(tmp_path)
    (tmp_path / "README.csv").write_text("not;an;extract\n", encoding="ascii")

    assert run(url, directory=tmp_path) == 0
    assert count(engine, "lightning") == len(ROWS_2009) + len(ROWS_2010)


def test_a_bad_row_is_skipped_and_the_rest_imported(database, tmp_path):
    engine, url = database
    bad = '1;"2009-07-01 10:00:00.000001";abc;1;300;100;3;t;"";2;41'
    path = write_extract(tmp_path / "x.csv", [*ROWS_2009, bad])

    assert run(url, path) == 0
    assert count(engine, "lightning") == len(ROWS_2009)


def test_a_dry_run_needs_no_database(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        assert app.main(["-s", str(extract_2009(tmp_path)), "--dry-run"]) == 0
    assert str(len(ROWS_2009)) in caplog.text


def test_a_dry_run_writes_nothing(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extra=["--dry-run"]) == 0

    assert count(engine, "lightning") == 0


def test_a_missing_file_is_refused(database, tmp_path):
    _, url = database
    assert run(url, tmp_path / "nowhere.csv") == 1


def test_a_file_that_is_not_an_extract_is_refused(database, tmp_path):
    engine, url = database
    path = tmp_path / "other.csv"
    path.write_text("a;b;c\n1;2;3\n", encoding="ascii")

    assert run(url, path) == 1
    assert count(engine, "lightning") == 0


def test_an_unmigrated_database_is_refused(database, tmp_path):
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE meteocat_lightning"))

    assert run(url, extract_2009(tmp_path)) == 1


# --------------------------------------------------------------------------
# Added in the review of these tests
# --------------------------------------------------------------------------

def test_a_failed_year_leaves_the_stored_one_as_it_was(database, tmp_path, monkeypatch):
    """The delete and the insert are one transaction: a failure keeps the old year."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}

    monkeypatch.setattr(app, "INSERT_SQL", "SELECT 1 / 0")
    assert run(url, extract_2009(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids


def test_a_flash_across_new_year_is_numbered_whole(database, tmp_path):
    """Numbering is done over the file before it is split into years."""
    engine, url = database
    path = write_extract(tmp_path / "x.csv", [
        '7;"2009-12-31 23:59:59.900000";-10;1;300;100;3;t;"";2;41',
        '7;"2010-01-01 00:00:00.100000";-11;1;300;100;3;t;"";2;41',
    ])
    assert run(url, path) == 0

    numbering = {stroke.date_time.astimezone(UTC).year:
                 (stroke.stroke_index, stroke.multiplicity) for stroke in strokes(engine)}
    assert numbering == {2009: (1, 2), 2010: (2, 2)}


def test_a_refused_row_is_logged_with_its_line(database, tmp_path, caplog):
    engine, url = database
    bad = '1;"2009-07-01 10:00:00.000001";abc;1;300;100;3;t;"";2;41'
    path = write_extract(tmp_path / "x.csv", [*ROWS_2009, bad])

    with caplog.at_level(logging.WARNING):
        assert run(url, path) == 0
    line = len(ROWS_2009) + 2
    assert f"Line {line} skipped" in caplog.text
    assert "correntpic" in caplog.text


def test_a_year_in_two_files_is_warned_about(database, tmp_path, caplog):
    """The second file replaces the first: worth saying, since nothing else will."""
    engine, url = database
    second = write_extract(tmp_path / "again.csv", [ROWS_2009[0]])

    with caplog.at_level(logging.WARNING):
        assert run(url, extract_2009(tmp_path), second) == 0
    assert "imported twice" in caplog.text
    assert count(engine, "lightning") == 1


def test_a_directory_with_no_extract_is_refused(database, tmp_path):
    _, url = database
    (tmp_path / "README.csv").write_text("not;an;extract\n", encoding="ascii")

    assert run(url, directory=tmp_path) == 1


def test_a_dry_run_still_checks_the_header(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a;b;c\n", encoding="ascii")

    assert app.main(["-s", str(path), "--dry-run"]) == 1


def test_the_imported_strokes_appear_in_the_views(database, tmp_path):
    """``create_all`` builds no views, so this test creates the 25831 one from the
    migration's own SQL and checks the imported point arrives on the UTM grid."""
    import importlib.util

    from src.settings import ROOT_DIR

    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    revision = next((ROOT_DIR / "alembic" / "versions").glob("*9c4f1a7e3b62*.py"))
    spec = importlib.util.spec_from_file_location("views_revision", revision)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view = module.meteocat_lightning_25831_view
    with engine.begin() as connection:
        connection.execute(text(f"CREATE VIEW {view.name} AS {view.sqltext}"))
        row = connection.execute(text(
            f"SELECT count(*) AS n, min(ST_X(geometry)) AS x FROM {view.name}")).one()

    assert row.n == len(ROWS_2009)
    assert 300_000 < row.x < 700_000


# --------------------------------------------------------------------------
# Thunderstorms built on the strokes
#
# A thunderstorm experiment is computed from a provider's strokes over a period.
# Replacing a year of strokes under it would change its input silently — and the
# strokes in its thunderstorms cannot be deleted at all (RESTRICT). So a year an
# experiment covers is refused, unless ``--drop-thunderstorms`` says to delete
# those experiments, whole, first.
# --------------------------------------------------------------------------

def an_experiment(engine, first_year: int, last_year: int, *, provider: str = "MeteoCat",
                  algorithm: str = "DBSCAN", strokes_of: int | None = None) -> int:
    """A complete experiment over ``first_year``-``last_year`` (whole UTC years).

    With ``strokes_of``, it has one thunderstorm made of MeteoCat's strokes of that
    year, a tracking and a window: something for a cascade to delete.
    """
    from src.data_model.thunderstorm import Thunderstorm
    from src.data_model.thunderstorm import ThunderstormEvolution
    from src.data_model.thunderstorm import ThunderstormExperiment
    from src.data_model.thunderstorm import ThunderstormLightning
    from src.data_model.thunderstorm import ThunderstormTracking

    with Session(engine) as session:
        owner = session.scalars(select(DataProvider).where(DataProvider.name == provider)).first()
        if owner is None:
            owner = DataProvider(name=provider, product="Network", full_name=provider)
            session.add(owner)
            session.flush()
        experiment = ThunderstormExperiment(
            data_provider_id=owner.id, algorithm=algorithm, parameters={"eps_m": 10000},
            date_time_start=datetime.datetime(first_year, 1, 1, tzinfo=UTC),
            date_time_end=datetime.datetime(last_year + 1, 1, 1, tzinfo=UTC),
            software_version="test", status="complete",
            completed_at=datetime.datetime(2026, 11, 8, tzinfo=UTC))
        session.add(experiment)
        if strokes_of is not None:
            members = [stroke for stroke in session.scalars(select(MeteocatLightning)).all()
                       if stroke.date_time.astimezone(UTC).year == strokes_of]
            storm = Thunderstorm(
                experiment=experiment, label=0, number_of_lightnings=len(members),
                date_time_start=min(stroke.date_time for stroke in members),
                date_time_end=max(stroke.date_time for stroke in members),
                lightning_links=[ThunderstormLightning(lightning=stroke) for stroke in members])
            tracking = ThunderstormTracking(
                experiment=experiment, window_length=datetime.timedelta(minutes=10),
                window_step=datetime.timedelta(minutes=2), software_version="test")
            session.add_all([storm, tracking, ThunderstormEvolution(
                tracking=tracking, thunderstorm=storm, sequence=1,
                window_start=storm.date_time_start,
                window_end=storm.date_time_start + datetime.timedelta(minutes=10),
                number_of_lightnings=1, centre="SRID=4326;POINT(2 41)")])
        session.commit()
        return experiment.id


def experiments(engine) -> set[int]:
    with Session(engine) as session:
        return set(session.scalars(text("SELECT id FROM thunderstorm_experiment")))


def test_a_year_covered_by_an_experiment_is_not_replaced(database, tmp_path, caplog):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    experiment_id = an_experiment(engine, 2009, 2009, strokes_of=2009)

    with caplog.at_level(logging.WARNING):
        assert run(url, extract_2009(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids
    assert experiments(engine) == {experiment_id}
    assert f"experiment(s) {experiment_id}" in caplog.text
    assert "--drop-thunderstorms" in caplog.text


def test_a_covered_year_is_refused_even_with_no_stroke_in_a_storm(database, tmp_path):
    """RESTRICT alone would let this through: the experiment's input would change."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    an_experiment(engine, 2009, 2009)

    assert run(url, extract_2009(tmp_path)) == 1
    assert {stroke.id for stroke in strokes(engine)} == stored_ids


def test_the_other_years_still_import_when_one_is_covered(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    an_experiment(engine, 2009, 2009)

    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 1

    years = [stroke.date_time.astimezone(UTC).year for stroke in strokes(engine)]
    assert years.count(2010) == len(ROWS_2010)
    assert {stroke.id for stroke in strokes(engine)} >= stored_ids


@pytest.mark.parametrize(("first_year", "last_year", "provider"), [
    pytest.param(2009, 2009, "Other", id="another-providers-experiment"),
    pytest.param(2008, 2008, "MeteoCat", id="ends-exactly-at-new-year"),
    pytest.param(2010, 2012, "MeteoCat", id="starts-exactly-after-the-year"),
])
def test_an_experiment_that_does_not_cover_the_year_does_not_block_it(
        database, tmp_path, first_year, last_year, provider):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    experiment_id = an_experiment(engine, first_year, last_year, provider=provider)

    assert run(url, extract_2009(tmp_path)) == 0
    assert experiments(engine) == {experiment_id}


def test_drop_thunderstorms_deletes_the_covering_experiments_whole(database, tmp_path, caplog):
    """The whole run goes, not the year's storms: a run is one consistent result."""
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 0
    first_ids = {stroke.id for stroke in strokes(engine)}
    covering = an_experiment(engine, 2008, 2011, strokes_of=2009)
    unrelated = an_experiment(engine, 2015, 2015, algorithm="HDBSCAN")

    with caplog.at_level(logging.INFO):
        assert run(url, extract_2009(tmp_path), extra=["--drop-thunderstorms"]) == 0

    assert experiments(engine) == {unrelated}
    for table in ("thunderstorm", "thunderstorm_lightning", "thunderstorm_tracking",
                  "thunderstorm_evolution"):
        assert count(engine, table) == 0, table
    replaced = {stroke.id for stroke in strokes(engine)
                if stroke.date_time.astimezone(UTC).year == 2009}
    assert len(replaced) == len(ROWS_2009)
    assert replaced.isdisjoint(first_ids)
    assert f"Dropping thunderstorm experiment {covering}" in caplog.text
    assert "1 thunderstorm(s), 1 tracking(s)" in caplog.text
    assert "dropped 1 thunderstorm experiment(s)" in caplog.text


def test_an_experiment_holding_the_years_strokes_outside_its_period_blocks_it(database,
                                                                             tmp_path):
    """A builder bug, but the strokes are what RESTRICT protects: found by its links."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    experiment_id = an_experiment(engine, 2015, 2015, strokes_of=2009)

    assert run(url, extract_2009(tmp_path)) == 1
    assert run(url, extract_2009(tmp_path), extra=["--drop-thunderstorms"]) == 0
    assert experiment_id not in experiments(engine)


def test_a_dry_run_with_drop_thunderstorms_lists_what_would_go(database, tmp_path, caplog):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    experiment_id = an_experiment(engine, 2009, 2009, strokes_of=2009)

    with caplog.at_level(logging.INFO):
        assert run(url, extract_2009(tmp_path), extra=["--dry-run", "--drop-thunderstorms"]) == 0

    assert f"Would drop thunderstorm experiment {experiment_id}" in caplog.text
    assert experiments(engine) == {experiment_id}
    assert {stroke.id for stroke in strokes(engine)} == stored_ids


def test_a_stroke_in_a_storm_is_never_deleted_from_under_it(database, tmp_path, monkeypatch,
                                                            caplog):
    """The safety net: if the check missed an experiment, RESTRICT refuses the delete,
    the year is rolled back and the message says why."""
    from src.apps.imports.lightnings import common as lightning_common

    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    an_experiment(engine, 2009, 2009, strokes_of=2009)
    monkeypatch.setattr(lightning_common, "covering_experiments", lambda *args, **kwargs: [])

    with caplog.at_level(logging.ERROR):
        assert run(url, extract_2009(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids
    assert "are in thunderstorms" in caplog.text


# --------------------------------------------------------------------------
# Added in the review of the thunderstorm tests
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["running", "failed"])
def test_an_unfinished_experiment_blocks_the_year_too(database, tmp_path, status):
    """A run being built reads the strokes now; a failed one is still in the way."""
    from src.data_model.thunderstorm import ThunderstormExperiment

    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    experiment_id = an_experiment(engine, 2009, 2009)
    with Session(engine) as session:
        experiment = session.get(ThunderstormExperiment, experiment_id)
        experiment.status, experiment.completed_at = status, None
        session.commit()

    assert run(url, extract_2009(tmp_path)) == 1
    assert experiments(engine) == {experiment_id}


def test_a_failed_year_keeps_the_experiments_it_would_have_dropped(database, tmp_path,
                                                                   monkeypatch):
    """The drop and the replacement are one transaction."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    experiment_id = an_experiment(engine, 2009, 2009, strokes_of=2009)

    monkeypatch.setattr(app, "INSERT_SQL", "SELECT 1 / 0")
    assert run(url, extract_2009(tmp_path), extra=["--drop-thunderstorms"]) == 1

    assert experiments(engine) == {experiment_id}
    assert count(engine, "thunderstorm_lightning") == len(ROWS_2009)
    assert {stroke.id for stroke in strokes(engine)} == stored_ids


def test_every_covering_experiment_is_dropped_and_counted(database, tmp_path, caplog):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    an_experiment(engine, 2009, 2009, strokes_of=2009)
    an_experiment(engine, 2006, 2020, algorithm="HDBSCAN", strokes_of=2009)

    with caplog.at_level(logging.INFO):
        assert run(url, extract_2009(tmp_path), extra=["--drop-thunderstorms"]) == 0

    assert experiments(engine) == set()
    assert "Also dropped 2 thunderstorm experiment(s)" in caplog.text


def test_the_flag_changes_nothing_when_no_experiment_is_in_the_way(database, tmp_path, caplog):
    engine, url = database
    unrelated = an_experiment(engine, 2015, 2015)

    with caplog.at_level(logging.INFO):
        assert run(url, extract_2009(tmp_path), extra=["--drop-thunderstorms"]) == 0

    assert experiments(engine) == {unrelated}
    assert count(engine, "lightning") == len(ROWS_2009)
    assert "dropped" not in caplog.text.lower()


def test_a_dry_run_with_the_flag_on_a_database_without_meteocat_lists_nothing(database,
                                                                              tmp_path):
    """MeteoCat's row is created by the first real import; a dry run creates nothing."""
    engine, url = database
    assert run(url, extract_2009(tmp_path), extra=["--dry-run", "--drop-thunderstorms"]) == 0
    assert count(engine, "data_provider") == 0


def test_a_database_without_the_thunderstorm_tables_is_refused(database, tmp_path, caplog):
    """The check reads them, so a database not migrated that far is refused up front."""
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE thunderstorm_lightning"))

    with caplog.at_level(logging.ERROR):
        assert run(url, extract_2009(tmp_path)) == 1
    assert "thunderstorm_lightning" in caplog.text
    assert count(engine, "lightning") == 0
