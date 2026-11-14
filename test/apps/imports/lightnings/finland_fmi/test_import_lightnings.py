#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the FMI lightning import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on monthly files written as the downloader writes them. What is
being tested is what this dataset makes hard: that a **UTC month** is the unit
replaced, since nothing identifies a stroke; that the identifiers follow the
month's content order, not the file's, since the service returns a second's
strokes in no stable order; that a flash straddling two months is numbered whole
whichever is imported first; that the sidecar is checked; and that the country is
resolved by a spatial join, strokes outside it having none.
"""

import datetime
import importlib.util
import logging
import random

from pathlib import Path

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.lightnings.finland_fmi import import_lightnings as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.lightning import Lightning
from src.providers import finland_fmi
from src.providers import ocha
from src.providers.finland_fmi.lightning import FmiLightning
from src.settings import ROOT_DIR

from .conftest import FINLAND_WKT
from .conftest import ROWS_2023_06
from .conftest import ROWS_2023_07
from .conftest import july_2022
from .conftest import july_2023
from .conftest import june_2023
from .conftest import row
from .conftest import write_month

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
def finland(database):
    """An OCHA country boundary, a rough box over Finland."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        boundary = AdminBoundary(data_provider_id=provider.id, source_id="FIN", level=0,
                                 name="Finland", geometry=f"SRID=4326;{FINLAND_WKT}")
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


def strokes(engine) -> list[FmiLightning]:
    """Every stroke, by identifier."""
    with Session(engine) as session:
        return session.scalars(select(FmiLightning).order_by(FmiLightning.id)).all()


def flash(engine, flash_id: int) -> list[tuple]:
    """``(stroke_index, multiplicity, published_multiplicity, peak_current)`` of a flash."""
    with Session(engine) as session:
        return session.execute(
            select(FmiLightning.stroke_index, FmiLightning.multiplicity,
                   FmiLightning.published_multiplicity, FmiLightning.peak_current)
            .where(FmiLightning.flash_id == flash_id)
            .order_by(FmiLightning.stroke_index)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


def months(engine) -> list[str]:
    return [stroke.date_time.astimezone(UTC).strftime("%Y-%m") for stroke in strokes(engine)]


# --------------------------------------------------------------------------
# A month round trips
# --------------------------------------------------------------------------

def test_a_month_is_imported_whole(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2023_07)
    assert count(engine, "fmi_lightning") == len(ROWS_2023_07)


def test_the_provider_row_is_created_once(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    assert run(url, july_2023(tmp_path)) == 0

    with Session(engine) as session:
        providers = session.scalars(select(DataProvider)).all()
    assert len(providers) == 1
    provider = providers[0]
    assert (provider.name, provider.product) == (finland_fmi.PROVIDER_NAME,
                                                 finland_fmi.PROVIDER_PRODUCT)
    assert provider.full_name == finland_fmi.PROVIDER_FULL_NAME
    assert provider.description == finland_fmi.PROVIDER_DESCRIPTION
    assert provider.url == finland_fmi.PROVIDER_URL


def test_a_real_stroke_is_stored_as_published_and_converted(database, tmp_path):
    """The first stroke of flash 30645787: ellipse in metres, the point twice."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0

    with Session(engine) as session:
        stroke = session.scalars(select(FmiLightning).where(
            FmiLightning.flash_id == 30645787, FmiLightning.stroke_index == 1)).one()
        assert stroke.type == "fmi_lightning"
        assert stroke.date_time == datetime.datetime(2023, 7, 1, 12, 0, 15, tzinfo=UTC)
        assert (stroke.peak_current, stroke.cloud_to_ground) == (-83.0, True)
        assert (stroke.multiplicity, stroke.published_multiplicity) == (4, 4)
        assert (stroke.number_of_sensors, stroke.degrees_of_freedom) == (10, 7)
        assert (stroke.ellipse_major_axis, stroke.ellipse_minor_axis) == (700.0, 100.0)
        assert (stroke.ellipse_angle, stroke.chi_squared) == (109.9, 0.4)
        assert (stroke.rise_time, stroke.peak_to_zero_time) == (8.9, 30.4)
        assert (stroke.stroke_status, stroke.angle_indicator, stroke.signal_indicator,
                stroke.timing_indicator) == (17, 1, 0, 1)
        assert to_shape(stroke.geometry_etrs89) == Point(31.8554, 59.7094)
        published, reprojected = session.execute(text(
            "SELECT ST_SRID(f.geometry_etrs89), ST_SRID(l.geometry) FROM fmi_lightning f "
            "JOIN lightning l ON l.id = f.id WHERE f.id = :id"), {"id": stroke.id}).one()
        assert (published, reprojected) == (4258, 4326)
        assert to_shape(stroke.geometry).distance(Point(31.8554, 59.7094)) < 1e-5


def test_not_recorded_and_old_values_are_stored_as_such(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0

    with Session(engine) as session:
        stroke = session.scalars(select(FmiLightning).where(FmiLightning.flash_id == 30700000)).one()
    assert stroke.peak_current is None
    assert (stroke.stroke_status, stroke.angle_indicator, stroke.signal_indicator,
            stroke.timing_indicator) == (0, 0, 0, 0)


def test_an_intra_cloud_stroke_is_stored_as_such(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    # 30645782 is a real intra-cloud stroke (cloud_indicator 1).
    with Session(engine) as session:
        stroke = session.scalars(select(FmiLightning).where(FmiLightning.flash_id == 30645782)).one()
    assert stroke.cloud_to_ground is False


# --------------------------------------------------------------------------
# Flashes
# --------------------------------------------------------------------------

def test_a_flash_is_numbered_from_its_first_stroke(database, tmp_path):
    """All four strokes are in one second, so after FMI's first stroke the order is
    the import's content order — here by latitude, 59.7173, 59.718, 59.7292 — not
    the order FMI happened to send them in (−27, −13, −12)."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    assert flash(engine, 30645787) == [(1, 4, 4, -83.0), (2, 4, 0, -27.0),
                                       (3, 4, 0, -12.0), (4, 4, 0, -13.0)]


def test_a_lone_subsequent_stroke_is_a_flash_of_one(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    assert flash(engine, 30700001) == [(1, 1, 0, -9.0)]


def test_a_flash_announcing_more_strokes_than_published_counts_what_is_stored(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    assert flash(engine, 30700003) == [(1, 1, 2, -40.0)]


def test_two_strokes_of_one_second_and_place_are_numbered_first_stroke_first(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    assert flash(engine, 30700002) == [(1, 2, 2, -35.0), (2, 2, 0, -11.0)]


def test_first_strokes_are_one_per_flash(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    with Session(engine) as session:
        flashes, firsts = session.execute(text(
            "SELECT count(DISTINCT flash_id), count(*) FILTER (WHERE stroke_index = 1) "
            "FROM fmi_lightning")).one()
    assert flashes == firsts


@pytest.mark.parametrize("order", ["june-first", "july-first"])
def test_a_flash_straddling_two_months_is_numbered_whole(database, tmp_path, order):
    """Its first stroke is in the June file, its second in the July file."""
    engine, url = database
    files = [june_2023(tmp_path), july_2023(tmp_path)]
    if order == "july-first":
        files.reverse()
    for path in files:
        assert run(url, path) == 0

    assert flash(engine, 30600000) == [(1, 2, 2, -21.0), (2, 2, 0, -14.0)]


def test_reimporting_one_side_of_a_straddling_flash_keeps_it_whole(database, tmp_path):
    engine, url = database
    assert run(url, june_2023(tmp_path), july_2023(tmp_path)) == 0
    assert run(url, july_2023(tmp_path)) == 0
    assert run(url, june_2023(tmp_path)) == 0
    assert flash(engine, 30600000) == [(1, 2, 2, -21.0), (2, 2, 0, -14.0)]


# --------------------------------------------------------------------------
# Order and identifiers
# --------------------------------------------------------------------------

def stored_order(engine) -> list[tuple]:
    """The strokes' values in identifier order."""
    return [(s.date_time, s.flash_id, s.peak_current, s.stroke_index) for s in strokes(engine)]


def test_the_identifiers_follow_the_months_content_not_the_files_order(database, tmp_path):
    """Two downloads of a month hold its strokes in different orders: same result."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    first = stored_order(engine)

    shuffled = list(ROWS_2023_07)
    random.Random(11).shuffle(shuffled)
    assert run(url, write_month(tmp_path, 2023, 7, shuffled)) == 0

    assert stored_order(engine) == first
    # And the order is the content order: by instant, then flash.
    assert first == sorted(first, key=lambda values: (values[0], values[1], values[3]))


def test_importing_a_month_again_replaces_it(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    first_ids = {stroke.id for stroke in strokes(engine)}
    assert run(url, july_2023(tmp_path)) == 0

    assert count(engine, "fmi_lightning") == len(ROWS_2023_07)
    assert {stroke.id for stroke in strokes(engine)}.isdisjoint(first_ids)


def test_importing_a_month_leaves_the_others_alone(database, tmp_path):
    engine, url = database
    assert run(url, june_2023(tmp_path), july_2023(tmp_path)) == 0
    june_ids = {s.id for s in strokes(engine) if s.date_time.astimezone(UTC).month == 6}
    assert run(url, july_2023(tmp_path)) == 0

    assert {s.id for s in strokes(engine) if s.date_time.astimezone(UTC).month == 6} == june_ids
    assert months(engine).count("2023-06") == len(ROWS_2023_06)


def test_strokes_of_other_providers_are_not_deleted(database, tmp_path):
    engine, url = database
    with Session(engine) as session:
        other = DataProvider(name="Other", product="Network", full_name="Other")
        session.add(other)
        session.flush()
        session.add(Lightning(data_provider_id=other.id, type="lightning",
                              date_time=datetime.datetime(2023, 7, 15, tzinfo=UTC),
                              geometry="SRID=4326;POINT(25 61)"))
        session.commit()

    assert run(url, july_2023(tmp_path)) == 0
    assert run(url, july_2023(tmp_path)) == 0
    assert count(engine, "lightning") == len(ROWS_2023_07) + 1


# --------------------------------------------------------------------------
# Files, years and sidecars
# --------------------------------------------------------------------------

def test_a_directory_imports_every_month_and_skips_the_rest(database, tmp_path, caplog):
    engine, url = database
    june_2023(tmp_path)
    july_2023(tmp_path)
    (tmp_path / "notes.csv.gz").write_bytes(b"")
    (tmp_path / "fmi_lightning_2023-08.csv.gz").write_text("not gzip")

    with caplog.at_level(logging.WARNING):
        assert run(url, directory=tmp_path) == 0

    assert sorted(set(months(engine))) == ["2023-06", "2023-07"]
    assert "Skipping fmi_lightning_2023-08.csv.gz" in caplog.text


def test_the_year_filter_imports_only_those_years(database, tmp_path):
    engine, url = database
    july_2022(tmp_path)
    july_2023(tmp_path)
    assert run(url, directory=tmp_path, extra=["--from-year", "2023"]) == 0
    assert set(months(engine)) == {"2023-07"}

    assert run(url, directory=tmp_path, extra=["--to-year", "2022"]) == 0
    assert set(months(engine)) == {"2022-07", "2023-07"}


def test_a_year_filter_that_leaves_nothing_is_refused(database, tmp_path):
    _, url = database
    assert run(url, july_2023(tmp_path), extra=["--from-year", "2024"]) == 1


def test_a_file_that_is_not_a_monthly_file_is_refused(database, tmp_path):
    engine, url = database
    other = tmp_path / "strokes.csv.gz"
    other.write_bytes(july_2023(tmp_path).read_bytes())
    assert run(url, july_2023(tmp_path), other) == 1
    assert count(engine, "lightning") == 0


def test_a_missing_file_is_refused(database, tmp_path):
    _, url = database
    assert run(url, tmp_path / "fmi_lightning_2023-07.csv.gz") == 1


def test_a_refused_row_is_logged_with_its_line_and_the_rest_imported(database, tmp_path, caplog):
    engine, url = database
    rows = [*ROWS_2023_07, row(1689435000, 1, 1, "NaN")]
    path = write_month(tmp_path, 2023, 7, rows)
    with caplog.at_level(logging.WARNING):
        assert run(url, path) == 0
    assert count(engine, "fmi_lightning") == len(ROWS_2023_07)
    assert f"Line {len(rows) + 1} skipped: peak_current is NaN" in caplog.text


def test_a_file_that_disagrees_with_its_sidecar_is_refused(database, tmp_path, caplog):
    """A truncated or altered file: the other months still import, the run fails."""
    engine, url = database
    june_2023(tmp_path)
    july_2023(tmp_path, sidecar={"month": "2023-07", "complete": True, "strokes": 999})

    with caplog.at_level(logging.ERROR):
        assert run(url, directory=tmp_path) == 1

    assert set(months(engine)) == {"2023-06"}
    assert "sidecar says 999" in caplog.text


def test_a_sidecar_for_another_month_is_refused(database, tmp_path):
    engine, url = database
    path = july_2023(tmp_path, sidecar={"month": "2023-08", "complete": True,
                                        "strokes": len(ROWS_2023_07)})
    assert run(url, path) == 1
    assert count(engine, "lightning") == 0


@pytest.mark.parametrize(("options", "warning"), [
    pytest.param({"sidecar": False}, "No sidecar", id="no-sidecar"),
    pytest.param({"complete": False}, "was not complete", id="incomplete"),
])
def test_a_month_without_proof_of_completeness_is_imported_with_a_warning(
        database, tmp_path, caplog, options, warning):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, july_2023(tmp_path, **options)) == 0
    assert count(engine, "fmi_lightning") == len(ROWS_2023_07)
    assert warning in caplog.text


def test_a_month_without_strokes_is_imported_as_none(database, tmp_path):
    """Early winters have whole months without a stroke: the file is a header."""
    engine, url = database
    assert run(url, write_month(tmp_path, 1998, 2, [])) == 0
    assert count(engine, "lightning") == 0


def test_more_refused_rows_than_reported_are_counted(database, tmp_path, caplog):
    engine, url = database
    bad = [row(1689435000 + n, n, 1, "NaN") for n in range(app.MAX_REPORTED_PROBLEMS + 3)]
    with caplog.at_level(logging.WARNING):
        assert run(url, write_month(tmp_path, 2023, 7, [*ROWS_2023_07, *bad])) == 0
    assert "Further refused rows in this file are counted, not logged" in caplog.text
    assert f"{len(bad)} row(s) refused" in caplog.text


def test_years_reversed_are_refused(tmp_path):
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", str(tmp_path), "--from-year", "2023", "--to-year", "2022"])


def test_a_directory_with_no_monthly_file_is_refused(database, tmp_path):
    _, url = database
    (tmp_path / "notes.txt").write_text("nothing")
    assert run(url, directory=tmp_path) == 1


def test_a_missing_directory_is_refused(database, tmp_path):
    _, url = database
    assert run(url, directory=tmp_path / "nowhere") == 1


def test_a_dry_run_still_checks_the_file(tmp_path):
    other = tmp_path / "fmi_lightning_2023-07.csv.gz"
    write_month(tmp_path, 2023, 7, ROWS_2023_07, header="a,b,c")
    assert app.main(["-s", str(other), "--dry-run"]) == 1


def test_a_dry_run_needs_no_database(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        assert app.main(["-s", str(july_2023(tmp_path)), "--dry-run"]) == 0
    assert f"Would import {len(ROWS_2023_07)} stroke(s)" in caplog.text


def test_a_dry_run_writes_nothing(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path), extra=["--dry-run"]) == 0
    assert count(engine, "lightning") == 0


def test_an_unmigrated_database_is_refused(database, tmp_path):
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE fmi_lightning"))
    assert run(url, july_2023(tmp_path)) == 1


def test_a_failed_month_leaves_the_stored_one_as_it_was(database, tmp_path, monkeypatch):
    """The delete and the insert are one transaction: a failure keeps the old month."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}

    monkeypatch.setattr(app, "INSERT_SQL", "SELECT 1 / 0")
    assert run(url, july_2023(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids


# --------------------------------------------------------------------------
# Countries and views
# --------------------------------------------------------------------------

def test_strokes_in_the_boundary_get_the_country_and_the_others_none(database, finland, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    with Session(engine) as session:
        located = dict(session.execute(text(
            "SELECT f.flash_id, l.admin_boundary_id FROM fmi_lightning f "
            "JOIN lightning l ON l.id = f.id WHERE f.flash_id IN (30645782, 30645785, 30645787) "
            "AND f.stroke_index = 1")).all())
    # 30645782 is in Finland (61.09 N 29.18 E), 30645785 in Sweden (60.64 N 13.88 E)
    # and 30645787 in Russia (59.71 N 31.86 E).
    assert located == {30645782: finland, 30645785: None, 30645787: None}


def test_without_boundaries_the_strokes_are_still_imported(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, july_2023(tmp_path)) == 0
    assert count(engine, "fmi_lightning") == len(ROWS_2023_07)
    assert "events will have no country" in caplog.text


def test_the_imported_strokes_appear_in_the_3067_view(database, tmp_path):
    """``create_all`` builds no views, so the 3067 one is created from the migration."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0

    revision = next((ROOT_DIR / "alembic" / "versions").glob("*95b95aac852f*.py"))
    spec = importlib.util.spec_from_file_location("fmi_views_revision", revision)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view = module.fmi_lightning_3067_view
    with engine.begin() as connection:
        connection.execute(text(f"CREATE VIEW {view.name} AS {view.sqltext}"))
        row_ = connection.execute(text(
            f"SELECT count(*) AS n, ST_X(geometry) AS x, ST_Y(geometry) AS y FROM {view.name} "
            f"WHERE flash_id = 30645782 GROUP BY geometry")).one()
    assert row_.n == 1
    # 61.0945 N 29.1807 E on TM35FIN, by pyproj: 617.58 km east, 6,775.27 km north.
    assert 617_000 < row_.x < 618_000
    assert 6_775_000 < row_.y < 6_776_000


# --------------------------------------------------------------------------
# Thunderstorms built on the strokes
# --------------------------------------------------------------------------

def an_experiment(engine, start: datetime.datetime, end: datetime.datetime, *,
                  provider: str = finland_fmi.PROVIDER_NAME, with_storm: bool = False) -> int:
    """A complete experiment over ``[start, end)``.

    With ``with_storm``, one thunderstorm made of FMI's strokes of that period, a
    tracking and a window: something for a cascade to delete.
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
            data_provider_id=owner.id, algorithm="Cellsearch", parameters={"r_km": 10},
            date_time_start=start, date_time_end=end, software_version="test",
            status="complete", completed_at=datetime.datetime(2026, 11, 14, tzinfo=UTC))
        session.add(experiment)
        if with_storm:
            members = [s for s in session.scalars(select(FmiLightning)).all()
                       if start <= s.date_time < end]
            storm = Thunderstorm(
                experiment=experiment, label=0, number_of_lightnings=len(members),
                date_time_start=min(s.date_time for s in members),
                date_time_end=max(s.date_time for s in members),
                lightning_links=[ThunderstormLightning(lightning=s) for s in members])
            tracking = ThunderstormTracking(
                experiment=experiment, window_length=datetime.timedelta(minutes=10),
                window_step=datetime.timedelta(minutes=2), software_version="test")
            session.add_all([storm, tracking, ThunderstormEvolution(
                tracking=tracking, thunderstorm=storm, sequence=1,
                window_start=storm.date_time_start,
                window_end=storm.date_time_start + datetime.timedelta(minutes=10),
                number_of_lightnings=1, centre="SRID=4326;POINT(25 61)")])
        session.commit()
        return experiment.id


def experiments(engine) -> set[int]:
    with Session(engine) as session:
        return set(session.scalars(text("SELECT id FROM thunderstorm_experiment")))


JULY = (datetime.datetime(2023, 7, 1, tzinfo=UTC), datetime.datetime(2023, 8, 1, tzinfo=UTC))


def test_a_month_covered_by_an_experiment_is_not_replaced(database, tmp_path, caplog):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    experiment_id = an_experiment(engine, *JULY, with_storm=True)

    with caplog.at_level(logging.WARNING):
        assert run(url, july_2023(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids
    assert experiments(engine) == {experiment_id}
    assert f"experiment(s) {experiment_id}" in caplog.text
    assert "--drop-thunderstorms" in caplog.text


def test_the_other_months_still_import_when_one_is_covered(database, tmp_path):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    an_experiment(engine, *JULY)

    assert run(url, june_2023(tmp_path), july_2023(tmp_path)) == 1
    assert months(engine).count("2023-06") == len(ROWS_2023_06)


@pytest.mark.parametrize(("start", "end", "provider"), [
    pytest.param(*JULY, "Other", id="another-providers-experiment"),
    pytest.param(datetime.datetime(2023, 6, 1, tzinfo=UTC), JULY[0], finland_fmi.PROVIDER_NAME,
                 id="ends-exactly-at-the-month"),
    pytest.param(JULY[1], datetime.datetime(2023, 9, 1, tzinfo=UTC), finland_fmi.PROVIDER_NAME,
                 id="starts-exactly-after-the-month"),
])
def test_an_experiment_that_does_not_cover_the_month_does_not_block_it(
        database, tmp_path, start, end, provider):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    experiment_id = an_experiment(engine, start, end, provider=provider)

    assert run(url, july_2023(tmp_path)) == 0
    assert experiments(engine) == {experiment_id}


def test_drop_thunderstorms_deletes_the_covering_experiments_whole(database, tmp_path, caplog):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    first_ids = {stroke.id for stroke in strokes(engine)}
    covering = an_experiment(engine, *JULY, with_storm=True)

    with caplog.at_level(logging.INFO):
        assert run(url, july_2023(tmp_path), extra=["--drop-thunderstorms"]) == 0

    assert experiments(engine) == set()
    for table in ("thunderstorm", "thunderstorm_lightning", "thunderstorm_tracking",
                  "thunderstorm_evolution"):
        assert count(engine, table) == 0, table
    assert {stroke.id for stroke in strokes(engine)}.isdisjoint(first_ids)
    assert f"Dropping thunderstorm experiment {covering}" in caplog.text
    assert "dropped 1 thunderstorm experiment(s)" in caplog.text


def test_a_dry_run_with_drop_thunderstorms_lists_what_would_go(database, tmp_path, caplog):
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    experiment_id = an_experiment(engine, *JULY, with_storm=True)

    with caplog.at_level(logging.INFO):
        assert run(url, july_2023(tmp_path), extra=["--dry-run", "--drop-thunderstorms"]) == 0

    assert f"Would drop thunderstorm experiment {experiment_id}" in caplog.text
    assert experiments(engine) == {experiment_id}


def test_a_stroke_in_a_storm_is_never_deleted_from_under_it(database, tmp_path, monkeypatch,
                                                           caplog):
    """Were the dependency check to miss an experiment, RESTRICT still stops the delete."""
    engine, url = database
    assert run(url, july_2023(tmp_path)) == 0
    stored_ids = {stroke.id for stroke in strokes(engine)}
    experiment_id = an_experiment(engine, *JULY, with_storm=True)
    monkeypatch.setattr(app.lightning_common, "covering_experiments", lambda *a, **k: [])

    with caplog.at_level(logging.ERROR):
        assert run(url, july_2023(tmp_path)) == 1

    assert {stroke.id for stroke in strokes(engine)} == stored_ids
    assert f"experiment(s) {experiment_id}, which the check" in caplog.text
