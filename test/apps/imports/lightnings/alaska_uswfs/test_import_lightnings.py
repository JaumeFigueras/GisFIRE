#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Alaska (USWFS) lightning import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on releases built as the U.S. Wildland Fire Service ships them.
What is being tested is what this release makes hard: that it is checked whole
before a year is written; that a **UTC year** is the unit replaced, since nothing
identifies a stroke; that the identifiers follow the year's content order, not the
file's; that the flashes GisFIRE groups are stored with ``flash_id`` the first
stroke's identifier; and that the country is found on both sides of the
antimeridian.
"""

import datetime
import importlib.util
import logging
import random

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.lightnings.alaska_uswfs import import_lightnings as app
from src.apps.imports.lightnings.alaska_uswfs import readers
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.lightning import Lightning
from src.providers import alaska_uswfs
from src.providers import ocha
from src.providers.alaska_uswfs.lightning import AlaskaUswfsLightning
from src.settings import ROOT_DIR

from .conftest import REAL_ROWS
from .conftest import SAMPLE_YEARS
from .conftest import row
from .conftest import write_release
from .conftest import write_text

UTC = datetime.timezone.utc

#: The sample's strokes once the four published twice are dropped, and its flashes.
STROKES = sum(strokes for strokes, _, _ in SAMPLE_YEARS.values())
FLASHES = sum(ground + cloud for _, ground, cloud in SAMPLE_YEARS.values())


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
def countries(database):
    """Two OCHA countries round the antimeridian: a box over Alaska, and one west of
    the antimeridian's far side, over the sea off Kamchatka, from 165 to 180 E."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        ids = {}
        for code, wkt in (
                ("USA", "MULTIPOLYGON(((-170 54, -141 54, -141 72, -170 72, -170 54)))"),
                ("RUS", "MULTIPOLYGON(((165 50, 180 50, 180 56, 165 56, 165 50)))")):
            boundary = AdminBoundary(data_provider_id=provider.id, source_id=code, level=0,
                                     name=code, geometry=f"SRID=4326;{wkt}")
            session.add(boundary)
            session.flush()
            ids[code] = boundary.id
        session.commit()
        return ids


def run(url: str, path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", str(path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def strokes(engine) -> list[AlaskaUswfsLightning]:
    """Every stroke, by identifier."""
    with Session(engine) as session:
        return session.scalars(select(AlaskaUswfsLightning).order_by(AlaskaUswfsLightning.id)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


def years(engine) -> dict[int, int]:
    found: dict[int, int] = {}
    for stroke in strokes(engine):
        year = stroke.date_time.astimezone(UTC).year
        found[year] = found.get(year, 0) + 1
    return found


def at(engine, instant: datetime.datetime) -> list[AlaskaUswfsLightning]:
    return [stroke for stroke in strokes(engine) if stroke.date_time == instant]


# --------------------------------------------------------------------------
# A release round trips
# --------------------------------------------------------------------------

def test_a_release_is_imported_whole(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path)) == 0

    assert count(engine, "lightning") == count(engine, "alaska_uswfs_lightning") == STROKES
    assert years(engine) == {year: strokes for year, (strokes, _, _) in SAMPLE_YEARS.items()}
    assert f"Imported {STROKES} stroke(s) in {FLASHES} flash(es) over 5 year(s)" in caplog.text


def test_the_provider_row_is_created_once(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    assert run(url, write_release(tmp_path)) == 0
    with Session(engine) as session:
        providers = session.scalars(select(DataProvider)).all()
    assert [(p.name, p.product) for p in providers] == [("USWFS", "ALDN")]
    assert providers[0].description == alaska_uswfs.PROVIDER_DESCRIPTION


def test_a_real_stroke_is_stored_as_published_and_converted(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0

    [stroke] = at(engine, datetime.datetime(2025, 7, 1, 22, 42, 58, 9000, tzinfo=UTC))
    with Session(engine) as session:
        assert session.get(DataProvider, stroke.data_provider_id).name == "USWFS"
    assert to_shape(stroke.geometry) == Point(-141.6709543, 65.3145394)
    assert (stroke.peak_current, stroke.cloud_to_ground) == (-17.1, True)
    assert (stroke.network_code, stroke.sequence_number, stroke.gdop) == (0, 53586, 3)
    assert (stroke.ellipse_semi_major_axis, stroke.ellipse_semi_minor_axis) == (3000.0, 1000.0)
    assert stroke.ellipse_angle == 72.0


def test_the_values_the_release_leaves_unknown_are_null(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0

    [cloud] = at(engine, datetime.datetime(2025, 7, 1, 2, 55, 5, 955000, tzinfo=UTC))
    assert (cloud.peak_current, cloud.cloud_to_ground) == (None, False)
    [ellipse] = at(engine, datetime.datetime(2014, 4, 26, 3, 29, 59, 901000, tzinfo=UTC))
    assert (ellipse.ellipse_semi_major_axis, ellipse.ellipse_semi_minor_axis) == (None, 1000.0)
    [first] = at(engine, datetime.datetime(2012, 3, 7, 7, 43, 29, 965000, tzinfo=UTC))
    assert first.sequence_number is None


def test_a_stroke_published_twice_is_stored_once(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path)) == 0

    twice = at(engine, datetime.datetime(2012, 6, 15, 14, 9, 7, 898000, tzinfo=UTC))
    assert [stroke.sequence_number for stroke in twice] == [18576]
    assert "2012: 4 stroke(s) published twice, kept once" in caplog.text


def test_the_unknowns_and_contradictions_are_reported(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path)) == 0
    assert "2014: 3 stroke(s) with a semi-major axis of 0, stored as unknown" in caplog.text
    assert "2019: 2 stroke(s) whose POLARITY contradicts the amplitude" in caplog.text
    assert "2026 is the release's last year and ends on 2026-09-28" in caplog.text


# --------------------------------------------------------------------------
# Identifiers and flashes
# --------------------------------------------------------------------------

def test_a_flash_is_its_first_strokes_identifier(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0

    flash = at(engine, datetime.datetime(2025, 7, 1, 22, 42, 58, 9000, tzinfo=UTC))[0].flash_id
    with Session(engine) as session:
        members = session.execute(
            select(AlaskaUswfsLightning.id, AlaskaUswfsLightning.stroke_index,
                   AlaskaUswfsLightning.multiplicity, Lightning.date_time)
            .where(AlaskaUswfsLightning.flash_id == flash)
            .order_by(AlaskaUswfsLightning.stroke_index)).all()
    assert [(m.stroke_index, m.multiplicity) for m in members] == [(1, 3), (2, 3), (3, 3)]
    assert members[0].id == flash
    assert [m.date_time.microsecond for m in members] == [9000, 18000, 262000]


def test_first_strokes_are_one_per_flash(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    with Session(engine) as session:
        first = session.scalar(select(func.count()).where(AlaskaUswfsLightning.stroke_index == 1))
        own = session.scalar(select(func.count()).where(
            AlaskaUswfsLightning.flash_id == AlaskaUswfsLightning.id))
        flashes = session.scalar(select(func.count(func.distinct(AlaskaUswfsLightning.flash_id))))
    assert first == own == flashes == FLASHES


def test_a_cloud_and_a_ground_stroke_of_one_millisecond_are_two_flashes(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    pair = at(engine, datetime.datetime(2025, 5, 24, 21, 27, 57, 335000, tzinfo=UTC))
    assert sorted((s.cloud_to_ground, s.multiplicity, s.flash_id == s.id) for s in pair) == \
        [(False, 1, True), (True, 1, True)]


def test_the_identifiers_follow_the_years_content_not_the_files_order(database, tmp_path):
    """Shuffled within each year, the release gives the same identifiers order."""
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    first = [(s.date_time, s.cloud_to_ground, s.sequence_number, s.stroke_index)
             for s in strokes(engine)]

    by_year: dict[str, list[str]] = {}
    for line in REAL_ROWS:
        by_year.setdefault(line.split(",")[2].split(" ")[0].rsplit("/", 1)[1], []).append(line)
    shuffled = []
    for lines in by_year.values():
        lines = lines[:]
        random.Random(11).shuffle(lines)
        shuffled += lines
    assert run(url, write_release(tmp_path, shuffled, name="shuffled.zip")) == 0

    again = [(s.date_time, s.cloud_to_ground, s.sequence_number, s.stroke_index)
             for s in strokes(engine)]
    assert again == first


def test_the_identifiers_never_go_back_in_time_within_a_year(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    times = [s.date_time for s in strokes(engine)]
    assert times == sorted(times)


# --------------------------------------------------------------------------
# Years
# --------------------------------------------------------------------------

def test_importing_a_release_again_replaces_it(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    first_ids = {s.id for s in strokes(engine)}
    assert run(url, write_release(tmp_path)) == 0
    assert count(engine, "lightning") == STROKES
    assert first_ids.isdisjoint({s.id for s in strokes(engine)})


def test_the_year_filter_imports_only_those_years(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path), extra=["--from-year", "2014", "--to-year", "2019"]) == 0
    assert years(engine) == {2014: 3, 2019: 3}


def test_importing_some_years_leaves_the_others_alone(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    kept = {s.id for s in strokes(engine) if s.date_time.year < 2025}
    assert run(url, write_release(tmp_path), extra=["--from-year", "2025"]) == 0
    assert kept <= {s.id for s in strokes(engine)}
    assert count(engine, "lightning") == STROKES


def test_a_year_filter_that_leaves_nothing_is_refused(database, tmp_path, caplog):
    _, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url, write_release(tmp_path), extra=["--from-year", "2030"]) == 1
    assert "no stroke in the years asked for (it holds 2012-2026)" in caplog.text


def test_years_reversed_are_refused(tmp_path):
    with pytest.raises(SystemExit):
        app.parse_arguments(["-s", str(tmp_path / "x.zip"), "--from-year", "2020",
                             "--to-year", "2019"])


def test_strokes_of_other_providers_are_not_deleted(database, tmp_path):
    engine, url = database
    with Session(engine) as session:
        other = DataProvider(name="Other", product="Network", full_name="Other")
        session.add(other)
        session.flush()
        session.add(Lightning(data_provider_id=other.id,
                              date_time=datetime.datetime(2025, 7, 1, 12, tzinfo=UTC),
                              geometry="SRID=4326;POINT(-147 64)", type="lightning"))
        session.commit()
    assert run(url, write_release(tmp_path)) == 0
    assert run(url, write_release(tmp_path)) == 0
    assert count(engine, "lightning") == STROKES + 1


# --------------------------------------------------------------------------
# A release that fails its checks writes nothing
# --------------------------------------------------------------------------

def test_a_release_that_disagrees_with_its_metadata_is_refused_whole(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url, write_release(tmp_path, points=41)) == 1
    assert count(engine, "lightning") == 0
    assert "declares 41 point(s)" in caplog.text


def test_a_release_with_a_year_split_in_two_is_refused_whole(database, tmp_path):
    engine, url = database
    rows = [row("7/1/2025 10:00:00"), row("1/2/2026 10:00:00"), row("7/2/2025 10:00:00")]
    assert run(url, write_release(tmp_path, rows)) == 1
    assert count(engine, "lightning") == 0


def test_the_extracted_text_is_imported_with_a_warning(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, write_text(tmp_path)) == 0
    assert count(engine, "lightning") == STROKES
    assert "No FGDC metadata beside the strokes" in caplog.text


def test_a_missing_file_is_refused(database, tmp_path):
    _, url = database
    assert run(url, tmp_path / "nowhere.zip") == 1


def test_a_refused_row_is_logged_with_its_line_and_the_rest_imported(database, tmp_path, caplog):
    engine, url = database
    rows = [row("7/1/2025 10:00:00"), row("7/1/2025 11:00:00", gdop="0"),
            row("7/1/2025 12:00:00")]
    with caplog.at_level(logging.WARNING):
        assert run(url, write_release(tmp_path, rows)) == 0
    assert count(engine, "lightning") == 2
    assert "Line 3 skipped: GDOP is below 1: 0" in caplog.text
    assert "2025: 1 row(s) refused" in caplog.text


def test_more_refused_rows_than_reported_are_counted(database, tmp_path, caplog):
    engine, url = database
    rows = [row(f"7/1/2025 10:{minute:02d}:00", gdop="0") for minute in range(25)]
    rows.append(row("7/1/2025 12:00:00"))
    with caplog.at_level(logging.WARNING):
        assert run(url, write_release(tmp_path, rows)) == 0
    assert caplog.text.count("skipped: GDOP") == app.MAX_REPORTED_PROBLEMS
    assert "Further refused rows of 2025 are counted, not logged" in caplog.text
    assert "2025: 25 row(s) refused" in caplog.text


def test_strokes_near_new_year_are_warned_about(database, tmp_path, caplog):
    _, url = database
    rows = [row("1/1/2025 0:00:00", 400), row("6/1/2025 0:00:00")]
    with caplog.at_level(logging.WARNING):
        assert run(url, write_release(tmp_path, rows)) == 0
    assert "2025: 1 stroke(s) within 1 s of the year's start or end" in caplog.text


def test_a_dry_run_writes_nothing(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path), extra=["--dry-run"]) == 0
    assert count(engine, "lightning") == 0
    assert f"Would import {STROKES} stroke(s) in {FLASHES} flash(es)" in caplog.text


def test_a_dry_run_needs_no_database(tmp_path):
    assert app.main(["-s", str(write_release(tmp_path)), "--dry-run",
                     "--db-host", "nowhere.invalid", "--db-name", "x", "--db-user", "x"]) == 0


def test_a_dry_run_still_checks_the_release(tmp_path):
    assert app.main(["-s", str(write_release(tmp_path, points=7)), "--dry-run"]) == 1


def test_an_unmigrated_database_is_refused(database, tmp_path):
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alaska_uswfs_lightning"))
    assert run(url, write_release(tmp_path)) == 1


def test_a_failed_year_leaves_the_stored_one_as_it_was(database, tmp_path, monkeypatch):
    """The delete and the insert are one transaction: a failure keeps the old year."""
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    stored_ids = {s.id for s in strokes(engine)}

    monkeypatch.setattr(app, "INSERT_SQL", "SELECT 1 / 0")
    assert run(url, write_release(tmp_path)) == 1

    assert {s.id for s in strokes(engine)} == stored_ids


def test_a_numbering_that_breaks_the_flash_rule_is_refused_by_the_database(database, tmp_path,
                                                                          monkeypatch, caplog):
    """Were the flash's first stroke not its smallest identifier, the CHECKs stop the
    year: the model holds the import to its rule. Each year is its own transaction and
    an unexpected error stops the run, so the years before 2025 — whose flashes are all
    single strokes, where the smallest and the largest identifier are one — are in;
    2025 is rolled back, and 2026 is never reached."""
    engine, url = database
    monkeypatch.setattr(app, "INSERT_SQL", app.INSERT_SQL.replace("min(numbered.id)",
                                                                  "max(numbered.id)"))
    with caplog.at_level(logging.ERROR):
        assert run(url, write_release(tmp_path)) == 1
    assert "ck_alaska_uswfs_lightning_first_stroke" in caplog.text
    assert set(years(engine)) == {2012, 2014, 2019}


# --------------------------------------------------------------------------
# Countries and views
# --------------------------------------------------------------------------

def test_strokes_on_both_sides_of_the_antimeridian_get_their_country(database, countries,
                                                                     tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    found = {
        "east of 180": at(engine, datetime.datetime(2012, 3, 8, 12, 33, 52, 343000, tzinfo=UTC)),
        "Alaska": at(engine, datetime.datetime(2025, 7, 1, 22, 42, 58, 9000, tzinfo=UTC)),
        "at sea": at(engine, datetime.datetime(2012, 5, 9, 8, 57, 1, 624000, tzinfo=UTC)),
    }
    assert {name: [s.admin_boundary_id for s in hits] for name, hits in found.items()} == {
        "east of 180": [countries["RUS"]], "Alaska": [countries["USA"]], "at sea": [None]}


def test_the_boundaries_are_cut_once_per_run(database, countries, tmp_path, monkeypatch):
    engine, url = database
    built = []
    real = app.ensure_boundary_parts

    def spy(*args, **kwargs):
        built.append(real(*args, **kwargs))
        return built[-1]

    monkeypatch.setattr(app, "ensure_boundary_parts", spy)
    assert run(url, write_release(tmp_path)) == 0
    assert built == [True, False, False, False, False]


def test_the_pieces_are_clipped_across_the_antimeridian(database, countries):
    """Two envelopes: the RUS box east of 180 and the USA box west of it are both in."""
    engine, _ = database
    log = logging.LoggerAdapter(logging.getLogger("test-alaska-parts"), {})
    with Session(engine) as session:
        boundary_provider_id = session.scalar(text("SELECT DISTINCT data_provider_id FROM admin_boundary"))
    with engine.connect() as connection, connection.begin():
        assert app.ensure_boundary_parts(connection, boundary_provider_id, log) is True
        names = connection.execute(text(
            f"SELECT DISTINCT b.name FROM {app.PIECES_TABLE} p "
            f"JOIN admin_boundary b ON b.id = p.admin_boundary_id ORDER BY b.name")).scalars().all()
        stored = connection.execute(text(f"SELECT west, east FROM {app.PIECES_TABLE}_box")).one()
    assert names == ["RUS", "USA"]
    assert tuple(stored) == pytest.approx((167.8, 264.1))


def test_a_run_leaves_no_pieces_behind_in_its_session(database, countries, tmp_path):
    """A pooled connection keeps its temporary tables: the run drops its pieces."""
    engine, _ = database
    args = app.parse_arguments(["-s", str(write_release(tmp_path))])
    app.import_lightnings(args, engine, logging.getLogger("test-alaska-parts"))
    with engine.connect() as connection:
        assert connection.execute(text(app.PARTS_EXIST_SQL)).scalar() is False


def test_without_boundaries_the_strokes_are_still_imported(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, write_release(tmp_path)) == 0
    assert count(engine, "lightning") == STROKES
    with Session(engine) as session:
        assert session.scalar(text("SELECT count(admin_boundary_id) FROM lightning")) == 0


def test_the_imported_strokes_appear_in_the_3338_view(database, tmp_path):
    """``create_all`` builds no views, so the 3338 one is created from the migration."""
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0

    revision = next((ROOT_DIR / "alembic" / "versions").glob("*fdc1d32daef2*.py"))
    spec = importlib.util.spec_from_file_location("alaska_views_revision", revision)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view = module.alaska_uswfs_lightning_3338_view
    with engine.begin() as connection:
        connection.execute(text(f"CREATE VIEW {view.name} AS {view.sqltext}"))
        total = connection.execute(text(f"SELECT count(*) FROM {view.name}")).scalar()
        point = connection.execute(text(
            f"SELECT ST_X(geometry) AS x, ST_Y(geometry) AS y FROM {view.name} "
            f"WHERE date_time = '2025-07-01T22:42:58.009Z'")).one()
    assert total == STROKES
    # 65.3145394 N 141.6709543 W on Alaska Albers, by pyproj: 571.82 km E, 1,759.35 km N.
    assert 571_000 < point.x < 573_000
    assert 1_758_000 < point.y < 1_761_000


# --------------------------------------------------------------------------
# Thunderstorms built on the strokes
# --------------------------------------------------------------------------

def an_experiment(engine, start: datetime.datetime, end: datetime.datetime, *,
                  provider: str = alaska_uswfs.PROVIDER_NAME, with_storm: bool = False) -> int:
    """A complete experiment over ``[start, end)``.

    With ``with_storm``, one thunderstorm made of the network's strokes of that
    period, a tracking and a window: something for a cascade to delete.
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
            status="complete", completed_at=datetime.datetime(2026, 11, 15, tzinfo=UTC))
        session.add(experiment)
        if with_storm:
            members = [s for s in session.scalars(select(AlaskaUswfsLightning)).all()
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
                number_of_lightnings=1, centre="SRID=4326;POINT(-147 64)")])
        session.commit()
        return experiment.id


def experiments(engine) -> set[int]:
    with Session(engine) as session:
        return set(session.scalars(text("SELECT id FROM thunderstorm_experiment")))


YEAR_2025 = (datetime.datetime(2025, 1, 1, tzinfo=UTC), datetime.datetime(2026, 1, 1, tzinfo=UTC))


def test_a_year_covered_by_an_experiment_is_not_replaced(database, tmp_path, caplog):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    stored_2025 = {s.id for s in strokes(engine) if s.date_time.year == 2025}
    experiment_id = an_experiment(engine, *YEAR_2025, with_storm=True)

    with caplog.at_level(logging.WARNING):
        assert run(url, write_release(tmp_path)) == 1

    assert stored_2025 <= {s.id for s in strokes(engine)}
    assert experiments(engine) == {experiment_id}
    assert f"experiment(s) {experiment_id}" in caplog.text
    assert "--drop-thunderstorms" in caplog.text


def test_the_other_years_still_import_when_one_is_covered(database, tmp_path):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    first_2012 = {s.id for s in strokes(engine) if s.date_time.year == 2012}
    an_experiment(engine, *YEAR_2025)

    assert run(url, write_release(tmp_path)) == 1
    assert first_2012.isdisjoint({s.id for s in strokes(engine) if s.date_time.year == 2012})
    assert count(engine, "lightning") == STROKES


@pytest.mark.parametrize(("start", "end", "provider"), [
    pytest.param(*YEAR_2025, "Other", id="another-providers-experiment"),
    pytest.param(datetime.datetime(2024, 1, 1, tzinfo=UTC), YEAR_2025[0],
                 alaska_uswfs.PROVIDER_NAME, id="ends-exactly-at-the-year"),
])
def test_an_experiment_that_does_not_cover_the_year_does_not_block_it(
        database, tmp_path, start, end, provider):
    engine, url = database
    assert run(url, write_release(tmp_path), extra=["--from-year", "2025", "--to-year", "2025"]) == 0
    experiment_id = an_experiment(engine, start, end, provider=provider)

    assert run(url, write_release(tmp_path), extra=["--from-year", "2025", "--to-year", "2025"]) == 0
    assert experiments(engine) == {experiment_id}


def test_drop_thunderstorms_deletes_the_covering_experiments_whole(database, tmp_path, caplog):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    covering = an_experiment(engine, *YEAR_2025, with_storm=True)

    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path), extra=["--drop-thunderstorms"]) == 0

    assert experiments(engine) == set()
    for table in ("thunderstorm", "thunderstorm_lightning", "thunderstorm_tracking",
                  "thunderstorm_evolution"):
        assert count(engine, table) == 0, table
    assert f"Dropping thunderstorm experiment {covering}" in caplog.text
    assert "dropped 1 thunderstorm experiment(s)" in caplog.text


def test_a_dry_run_with_drop_thunderstorms_lists_what_would_go(database, tmp_path, caplog):
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    experiment_id = an_experiment(engine, *YEAR_2025, with_storm=True)

    with caplog.at_level(logging.INFO):
        assert run(url, write_release(tmp_path), extra=["--dry-run", "--drop-thunderstorms"]) == 0

    assert f"Would drop thunderstorm experiment {experiment_id}" in caplog.text
    assert experiments(engine) == {experiment_id}


def test_a_stroke_in_a_storm_is_never_deleted_from_under_it(database, tmp_path, monkeypatch,
                                                           caplog):
    """Were the dependency check to miss an experiment, RESTRICT still stops the delete."""
    engine, url = database
    assert run(url, write_release(tmp_path)) == 0
    stored = {s.id for s in strokes(engine)}
    experiment_id = an_experiment(engine, *YEAR_2025, with_storm=True)
    monkeypatch.setattr(app.lightning_common, "covering_experiments", lambda *a, **k: [])

    with caplog.at_level(logging.ERROR):
        assert run(url, write_release(tmp_path)) == 1

    assert {s.id for s in strokes(engine) if s.date_time.year == 2025} <= stored
    assert f"experiment(s) {experiment_id}, which the check" in caplog.text


def test_the_reader_and_the_import_agree_on_the_flashes(database, tmp_path):
    """What the reader groups is what is stored, flash for flash."""
    engine, url = database
    path = write_release(tmp_path)
    assert run(url, path) == 0
    release = readers.scan(path)
    expected = sum(readers.prepare_year(content).flashes
                   for content in readers.read_years(release))
    with Session(engine) as session:
        assert session.scalar(select(func.count(func.distinct(AlaskaUswfsLightning.flash_id)))) == \
            expected
