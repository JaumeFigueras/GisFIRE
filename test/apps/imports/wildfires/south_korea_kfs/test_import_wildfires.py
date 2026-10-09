#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on a CP949 release written like the published one. What is being
tested is what this dataset makes hard: that a **year** is the unit replaced,
since nothing identifies a fire; that Korean wall-clock times become the right
instants; that a bad end is stored as no end with its reason; and that an unknown
cause text stops the import before anything is touched.
"""

import datetime

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.wildfires.south_korea_kfs import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.providers import south_korea_kfs
from src.providers.south_korea_kfs.wildfire import KfsWildfire

from .conftest import ROWS
from .conftest import fire
from .conftest import write_release

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


def run(url: str, *paths: Path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", *[str(path) for path in paths],
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def stored(engine) -> list[KfsWildfire]:
    """Every Korean fire, in published order."""
    with Session(engine) as session:
        return session.scalars(select(KfsWildfire).order_by(KfsWildfire.source_row)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# A release round trips
# --------------------------------------------------------------------------

def test_a_release_is_imported(tmp_path, database):
    engine, url = database
    path = write_release(tmp_path / "산불발생통계(20251110).csv")

    assert run(url, path) == 0

    fires = stored(engine)
    assert len(fires) == 4
    first = fires[0]
    assert first.year == 2025
    assert first.source_file == "산불발생통계(20251110).csv"
    assert first.source_row == 2
    assert (first.province_name, first.province_name_rr) == ("경북", "Gyeongbuk")
    assert (first.municipality_name, first.municipality_name_rr) == ("의성", "Uiseong")
    assert (first.township_name, first.township_name_rr) == ("안계", "Angye")
    assert first.cause_detail == "논밭두렁소각"
    assert first.cause_class == "agricultural_burning"
    assert first.fire_cause == "human"
    assert first.cause_suspected is False
    assert first.area_ha == 52707.3
    assert first.time_zone == "Asia/Seoul"
    assert first.perimeter is None
    assert first.admin_boundary_id is None


def test_korean_time_becomes_the_right_instant(tmp_path, database):
    """11:25 KST is 02:25 UTC: nine hours, no daylight saving."""
    engine, url = database
    run(url, write_release(tmp_path / "a.csv"))

    first = stored(engine)[0]
    assert first.start_date_time == datetime.datetime(2025, 3, 22, 2, 25, tzinfo=UTC)
    assert first.end_date_time == datetime.datetime(2025, 3, 22, 9, 40, tzinfo=UTC)


def test_the_published_oddities_are_cleaned(tmp_path, database):
    engine, url = database
    run(url, write_release(tmp_path / "a.csv"))

    fires = stored(engine)
    assert fires[1].province_name == "충남"
    assert fires[1].municipality_name_rr == "Cheonan Seobuk"
    assert fires[1].cause_text == "`전기누전"
    assert fires[1].cause_class == "power_electrical"
    assert fires[2].municipality_name is None
    assert fires[2].township_name is None
    assert fires[2].cause_suspected is True


def test_a_bad_end_is_stored_as_no_end_with_its_reason(tmp_path, database):
    engine, url = database
    run(url, write_release(tmp_path / "a.csv"))

    fires = stored(engine)
    assert fires[1].end_date_time is None
    assert fires[1].end_date_problem == "extinguish_before_start"
    assert fires[3].end_date_time is None
    assert fires[3].end_date_problem == "extinguish_year_invalid"


def test_the_provider_is_created_once(tmp_path, database):
    engine, url = database
    path = write_release(tmp_path / "a.csv")
    run(url, path)
    run(url, path)

    with Session(engine) as session:
        provider = session.scalars(select(DataProvider)).one()
    assert (provider.name, provider.product) == (south_korea_kfs.PROVIDER_NAME,
                                                 south_korea_kfs.PROVIDER_PRODUCT)
    assert {fire.data_provider_id for fire in stored(engine)} == {provider.id}


# --------------------------------------------------------------------------
# The year is the unit
# --------------------------------------------------------------------------

def test_reimporting_replaces_rather_than_doubles(tmp_path, database):
    engine, url = database
    path = write_release(tmp_path / "a.csv")
    run(url, path)
    run(url, path)

    assert count(engine, "kfs_wildfire") == 4
    assert count(engine, "wildfire") == 4


def test_a_newer_release_revises_only_its_years(tmp_path, database):
    """The next release holds 2025 complete and nothing before 2023, say."""
    engine, url = database
    run(url, write_release(tmp_path / "old.csv"))
    newer = write_release(tmp_path / "new.csv", [
        fire(start="2025-10-01 10:00", weekday="수", end="2025-10-01 12:00"),
        fire(),
    ])
    run(url, newer)

    by_year = {}
    for row in stored(engine):
        by_year.setdefault(row.year, set()).add(row.source_file)
    assert by_year == {2025: {"new.csv"}, 2024: {"old.csv"}, 2023: {"old.csv"},
                       2022: {"old.csv"}}
    assert sum(1 for row in stored(engine) if row.year == 2025) == 2


def test_only_the_requested_years_are_imported(tmp_path, database):
    engine, url = database
    run(url, write_release(tmp_path / "a.csv"), extra=["-y", "2023", "2024"])
    assert sorted(fire.year for fire in stored(engine)) == [2023, 2024]


# --------------------------------------------------------------------------
# What is refused
# --------------------------------------------------------------------------

def test_an_unknown_cause_stops_the_import_before_anything_changes(tmp_path, database):
    engine, url = database
    run(url, write_release(tmp_path / "a.csv"))
    bad = write_release(tmp_path / "bad.csv", [*ROWS, fire(text="외계인")])

    assert run(url, bad) == 1
    # The earlier import is untouched: no year was deleted.
    assert {fire.source_file for fire in stored(engine)} == {"a.csv"}
    assert count(engine, "kfs_wildfire") == 4


def test_an_unstorable_row_is_skipped_and_the_rest_imported(tmp_path, database):
    engine, url = database
    path = write_release(tmp_path / "a.csv", [fire(), fire(area="")])

    assert run(url, path) == 0
    assert count(engine, "kfs_wildfire") == 1


def test_a_file_that_is_not_a_release_is_refused(tmp_path, database):
    _, url = database
    path = write_release(tmp_path / "dictionary.csv", [], header=("테이블", "순서"))
    assert run(url, path) == 1


def test_a_directory_skips_the_data_dictionary(tmp_path, database):
    engine, url = database
    write_release(tmp_path / "산불발생통계.csv")
    write_release(tmp_path / "데이터사전.csv", [], header=("테이블", "순서"))
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 0
    assert count(engine, "kfs_wildfire") == 4


def test_a_dry_run_writes_nothing(tmp_path, database):
    engine, url = database
    assert run(url, write_release(tmp_path / "a.csv"), extra=["--dry-run"]) == 0
    assert count(engine, "kfs_wildfire") == 0
    assert count(engine, "data_provider") == 0
