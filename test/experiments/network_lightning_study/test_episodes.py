#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The lightning episodes study: the zone flashes, rule 1, the ends of the period and the files."""

import csv
import datetime
import logging

import numpy as np
import pytest

from sqlalchemy import create_engine
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import Strokes
from gisfire_experiments.network_lightning_study import episodes as study
from gisfire_experiments.network_lightning_study.episodes import Episode
from src.data_model import Base
from src.providers import catalonia_meteocat

UTC = datetime.timezone.utc

HOUR = 3600.0


def strokes(keys, t, error=None) -> Strokes:
    """Strokes with these flash keys and times (ids in order, positions unused)."""
    n = len(keys)
    return Strokes(ids=np.arange(1, n + 1), flash_keys=np.array(keys), t=np.array(t, dtype=float),
                   x=np.zeros(n), y=np.zeros(n),
                   error=np.full(n, 500.0) if error is None else np.array(error, dtype=float))


# --- the zone flashes and rule 1 (no database) ---------------------------------------

def test_a_flash_with_any_stroke_in_the_zone_is_a_zone_flash():
    # Flash 1: both strokes in the zone; flash 2: none; flash 3: the second only.
    times, counts = study.zone_flashes(strokes([1, 1, 2, 3, 3], [0, 1, 10, 20, 21]),
                                       np.array([True, True, False, False, True]))
    assert times.tolist() == [0.0, 20.0]
    assert counts.tolist() == [2, 1]


def test_a_zone_flash_is_timed_by_its_representative_stroke_even_outside_the_zone():
    """The most accurate stroke (error 100 m) is outside the zone, a second earlier."""
    times, counts = study.zone_flashes(strokes([7, 7], [50, 51], error=[100, 900]),
                                       np.array([False, True]))
    assert times.tolist() == [50.0]
    assert counts.tolist() == [1]


def test_no_strokes_no_zone_flashes():
    times, counts = study.zone_flashes(study.concatenate([]), np.empty(0, dtype=bool))
    assert times.size == 0 and counts.size == 0


def test_episodes_are_cut_at_gaps_longer_than_g():
    times = np.array([0.0, 0.5, 1.5, 3.0, 3.1]) * HOUR
    episodes = study.find_episodes(times, np.array([1, 2, 3, 4, 5]), HOUR)
    # 0.5 to 1.5 h is exactly G and does not cut; 1.5 to 3 h does.
    assert episodes == [Episode(0.0, 1.5 * HOUR, 3, 6), Episode(3.0 * HOUR, 3.1 * HOUR, 2, 9)]


def test_an_episode_is_followed_while_it_starts_in_the_period_and_may_still_run():
    episode = Episode(start_s=10 * HOUR, end_s=23.5 * HOUR, flashes=3, strokes=3)
    # Read to 24 h: a zone flash up to 24.5 h would still belong to it.
    assert study.follow([episode], 0.0, 24 * HOUR, 24 * HOUR, HOUR)
    # Read to 24.5 h: a flash exactly at 24.5 h would still count, so not yet ended.
    assert study.follow([episode], 0.0, 24 * HOUR, 24.5 * HOUR, HOUR)
    assert not study.follow([episode], 0.0, 24 * HOUR, 25 * HOUR, HOUR)
    # It started before the period, or after it: not this run's.
    assert not study.follow([episode], 11 * HOUR, 24 * HOUR, 24 * HOUR, HOUR)
    assert not study.follow([episode], 0.0, 10 * HOUR, 24 * HOUR, HOUR)
    assert not study.follow([], 0.0, 24 * HOUR, 24 * HOUR, HOUR)


# --- the arguments and the files (no database) ---------------------------------------

def test_the_defaults_and_the_checks_of_the_arguments():
    base = ["--provider", "FMI", "--from", "2018-01-01", "--to", "2019-01-01", "--csv", "x.csv"]
    args = study.parse_arguments([*base, "--gap", "5"])
    assert args.min_flashes == study.MIN_FLASHES == 100
    assert args.gap == 5.0
    assert args.start == datetime.datetime(2018, 1, 1, tzinfo=UTC)
    for wrong in (["--gap", "0"], ["--gap", "5", "--min-flashes", "0"],
                  ["--gap", "5", "--to", "2018-01-01"]):
        with pytest.raises(SystemExit):
            study.parse_arguments([*base, *wrong])
    with pytest.raises(SystemExit):
        study.parse_arguments(["--provider", "Xweather", *base[2:], "--gap", "5"])


def test_every_network_has_a_region():
    assert set(study.REGIONS) == set(study.READERS)


def test_the_quartiles_use_numpys_default_interpolation():
    """Flashes 100, 200, 300, 1000: type 7 puts Q1 at 175 and Q3 at 475."""
    episodes = [Episode(0.0, 1.0, flashes, 0) for flashes in (300, 100, 1000, 200)]
    assert study.quartiles(episodes) == [100.0, 175.0, 250.0, 475.0, 1000.0]
    assert study.quartiles([]) == []


def test_the_files(tmp_path):
    path = tmp_path / "out" / "fmi_2018.csv"
    day = datetime.datetime(2018, 7, 3, tzinfo=UTC).timestamp()
    study.write_files(path, [Episode(day + 6 * HOUR, day + 7.5 * HOUR + 0.25, 120, 300),
                             Episode(day + 20 * HOUR, day + 21 * HOUR, 101, 150)])
    assert list(csv.reader(path.open())) == [
        study.EPISODE_COLUMNS,
        ["1", "2018-07-03T06:00:00.000+00:00", "2018-07-03T07:30:00.250+00:00", "5400.250",
         "120", "300"],
        ["2", "2018-07-03T20:00:00.000+00:00", "2018-07-03T21:00:00.000+00:00", "3600.000",
         "101", "150"]]
    assert study.quartiles_path(path) == tmp_path / "out" / "fmi_2018_quartiles.csv"
    assert list(csv.reader(study.quartiles_path(path).open())) == [
        study.QUARTILE_COLUMNS, ["2", "101.00", "105.75", "110.50", "115.25", "120.00"]]


def test_the_files_with_no_episode(tmp_path):
    path = tmp_path / "none.csv"
    study.write_files(path, [])
    assert list(csv.reader(path.open())) == [study.EPISODE_COLUMNS]
    assert list(csv.reader(study.quartiles_path(path).open())) == [
        study.QUARTILE_COLUMNS, ["0", "", "", "", "", ""]]


# --- a day of MeteoCat strokes ---------------------------------------------------------

DAY = datetime.datetime(2020, 7, 13, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)

#: The test's Catalonia: a 40 km square in EPSG:25831.
REGION = (380_000.0, 4_580_000.0, 420_000.0, 4_620_000.0)

#: Positions in EPSG:25831: in the region, in the zone outside it (30 km east), out of
#: the zone (80 km east) and far away (200 km east).
INSIDE = (400_000.0, 4_600_000.0)
ZONE = (450_000.0, 4_600_000.0)
OUTSIDE = (500_000.0, 4_600_000.0)
FAR = (620_000.0, 4_600_000.0)

#: One MeteoCat stroke, given in metres of EPSG:25831 (as the builder's tests do).
INSERT_STROKE_SQL = """
WITH point AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 25831), 4258) AS etrs89
), parent AS (
    INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT 'meteocat_lightning', :provider_id, :at, ST_Transform(point.etrs89, 4326), -20.0,
           :ground
    FROM point
    RETURNING id
)
INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, stroke_index,
                                ellipse_major_axis, ellipse_minor_axis, geometry_etrs89)
SELECT parent.id, 2, :flash, 1, 1, :error, 0, point.etrs89
FROM parent, point
"""

INSERT_REGION_SQL = """
WITH provider AS (
    INSERT INTO data_provider (name, product, full_name)
    VALUES ('IGN', 'Base de Datos de Divisiones Administrativas de España ' || :edition, 'IGN')
    RETURNING id
), boundary AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry)
    SELECT 'ign_admin_boundary', provider.id, '34090000000', 1, 'Cataluña/Catalunya',
           ST_Multi(ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 25831), 4326))
    FROM provider
    RETURNING id
)
INSERT INTO ign_admin_boundary (id, edition, kind)
SELECT boundary.id, :edition, 'comunidad_autonoma' FROM boundary
"""


def at(hours: float, seconds: float = 0.0) -> datetime.datetime:
    return DAY + datetime.timedelta(hours=hours, seconds=seconds)


#: (flash, hours after DAY 00:00, [(seconds, position, error), ...], ground)
FLASHES = [
    # A: running at --from (00:00), from 23:30 the day before: left out.
    (1, -0.5, [(0, INSIDE, 500.0)], True),
    (2, 0.25, [(0, INSIDE, 500.0)], True),
    # B: 06:00 to 07:50, 5 zone flashes, 9 strokes in the zone.
    (3, 6.0, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    (4, 6 + 1 / 6, [(0, INSIDE, 500.0)], False),           # a cloud stroke: ignored
    (5, 6 + 1 / 3, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    (6, 6.5, [(0, FAR, 500.0), (1, FAR, 500.0)], True),    # far away: not a zone flash
    (7, 6 + 2 / 3, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    # Timed by its most accurate stroke, out of the zone; one stroke in the zone.
    (8, 6 + 5 / 6, [(0, OUTSIDE, 100.0), (1, ZONE, 900.0)], True),
    # Exactly G after the previous zone flash: still B.
    (9, 7 + 5 / 6, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    # C: 2 zone flashes, under --min-flashes 3.
    (10, 12.0, [(0, INSIDE, 500.0)], True),
    (11, 12.5, [(0, INSIDE, 500.0)], True),
    # D: running at --to (24:00), 23:30 to 01:10 the next day, 3 flashes, 6 strokes.
    (12, 23.5, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    (13, 24 + 1 / 3, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
    (14, 25 + 1 / 6, [(0, INSIDE, 500.0), (1, ZONE, 500.0)], True),
    # E: starts at 03:00 the next day, after the period.
    (15, 27.0, [(0, INSIDE, 500.0), (1, INSIDE, 500.0)], True),
]


@pytest.fixture
def database(postgresql):
    """The GisFIRE schema on an ephemeral PostgreSQL with :data:`FLASHES` and the region;
    the engine and the database arguments."""
    info = postgresql.info
    engine = create_engine(f"postgresql+psycopg://{info.user}:{info.password or ''}"
                           f"@{info.host}:{info.port}/{info.dbname}")
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES (:n, :p, :f) RETURNING id"),
            {"n": catalonia_meteocat.PROVIDER_NAME, "p": catalonia_meteocat.PROVIDER_PRODUCT,
             "f": catalonia_meteocat.PROVIDER_FULL_NAME}).scalar_one()
        for flash, hours, flash_strokes, ground in FLASHES:
            for seconds, (x, y), error in flash_strokes:
                connection.execute(text(INSERT_STROKE_SQL), {
                    "provider_id": provider_id, "flash": flash, "at": at(hours, seconds),
                    "x": x, "y": y, "error": error, "ground": ground})
        connection.execute(text(INSERT_REGION_SQL), dict(zip(("xmin", "ymin", "xmax", "ymax"),
                                                             REGION), edition="2026"))
    arguments = ["--db-host", info.host, "--db-port", str(info.port), "--db-name", info.dbname,
                 "--db-user", info.user]
    if info.password:
        arguments += ["--db-password", info.password]
    yield engine, arguments
    engine.dispose()


def row_counts(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {table.name: connection.execute(text(f"SELECT count(*) FROM {table.name}")).scalar()
                for table in Base.metadata.sorted_tables}


def run(arguments, path, start=DAY, end=NEXT_DAY, gap="1", min_flashes="3") -> int:
    return study.main(["--provider", "MeteoCat", "--from", start.isoformat(), "--to",
                       end.isoformat(), "--gap", gap, "--min-flashes", min_flashes,
                       "--csv", str(path), *arguments])


def test_the_episodes_of_a_day(database, tmp_path, caplog):
    engine, arguments = database
    before = row_counts(engine)
    path = tmp_path / "meteocat.csv"
    with caplog.at_level(logging.INFO):
        assert run(arguments, path) == 0
    assert row_counts(engine) == before
    assert list(csv.reader(path.open())) == [
        study.EPISODE_COLUMNS,
        ["1", "2020-07-13T06:00:00.000+00:00", "2020-07-13T07:50:00.000+00:00", "6600.000",
         "5", "9"],
        ["2", "2020-07-13T23:30:00.000+00:00", "2020-07-14T01:10:00.000+00:00", "6000.000",
         "3", "6"]]
    assert list(csv.reader(study.quartiles_path(path).open())) == [
        study.QUARTILE_COLUMNS, ["2", "3.00", "3.50", "4.00", "4.50", "5.00"]]
    assert "The episode running at --from (since 2020-07-12T23:30:00.000+00:00" in caplog.text
    assert "still running: read on to 2020-07-15T00:00:00+00:00" in caplog.text
    assert "3 episode(s) start in the period: 2 kept, 1 with fewer than 3 zone flashes" in \
        caplog.text
    assert "The data end" not in caplog.text


def test_the_minimum_leaves_out_the_small_episodes_only(database, tmp_path):
    engine, arguments = database
    path = tmp_path / "meteocat.csv"
    assert run(arguments, path, min_flashes="1") == 0
    rows = list(csv.DictReader(path.open()))
    assert [(row["start"][11:16], row["flashes"]) for row in rows] == [
        ("06:00", "5"), ("12:00", "2"), ("23:30", "3")]


def test_a_longer_gap_joins_the_episodes(database, tmp_path):
    """With G = 6 h, A runs into B and B into C (00:15 to 06:00 and 07:50 to 12:00 are
    under 6 h): one episode that started before --from, all of it left out. 12:30 to
    23:30 is 11 h, and D runs on into E (01:10 to 03:00), past --to."""
    engine, arguments = database
    path = tmp_path / "meteocat.csv"
    assert run(arguments, path, gap="6", min_flashes="1") == 0
    rows = list(csv.DictReader(path.open()))
    assert [(row["start"], row["end"], row["flashes"], row["strokes"]) for row in rows] == [
        ("2020-07-13T23:30:00.000+00:00", "2020-07-14T03:00:00.000+00:00", "4", "8")]


def test_the_end_of_the_data_is_reported(database, tmp_path, caplog):
    """E, the last flash in the database, starts at 03:00: nothing shows it has ended."""
    engine, arguments = database
    path = tmp_path / "meteocat.csv"
    with caplog.at_level(logging.WARNING):
        assert run(arguments, path, start=at(26), end=at(28), min_flashes="1") == 0
    assert [row["start"] for row in csv.DictReader(path.open())] == [
        "2020-07-14T03:00:00.000+00:00"]
    assert "The data end before the episode that started at 2020-07-14T03:00:00.000+00:00" in \
        caplog.text


def test_a_missing_region_is_reported(database, tmp_path, caplog):
    engine, arguments = database
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM ign_admin_boundary"))
        connection.execute(text("DELETE FROM admin_boundary"))
    assert run(arguments, tmp_path / "x.csv") == 1
    assert "No boundary for IGN's Catalonia (NATCODE 34090000000)" in caplog.text


def test_two_editions_of_the_region_are_refused(database, tmp_path, caplog):
    engine, arguments = database
    with engine.begin() as connection:
        connection.execute(text(INSERT_REGION_SQL), dict(zip(("xmin", "ymin", "xmax", "ymax"),
                                                             REGION), edition="2019"))
    assert run(arguments, tmp_path / "x.csv") == 1
    assert "2 boundaries match IGN's Catalonia" in caplog.text
