#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the thunderstorm builder (``build_thunderstorms``) with Cellsearch.

Run against a real (ephemeral) PostgreSQL with PostGIS, mostly through the
application's own entry point, on MeteoCat strokes written straight into the
tables. Synthetic strokes are placed in ETRS89 / UTM 31N metres around
:data:`ORIGIN`, so distances and times are chosen exactly.

The core is tested on its own in ``test/algorithms``; what is pinned down here
is what the adapter adds: which strokes are read, how a run is stored (cells,
every stroke linked, centres, hull over the representative strokes, area,
summary, status), the window truncation flags, the run's life cycle (duplicate,
failure, dry run) and one real day of MeteoCat data. That day is not in the
repository, since MeteoCat's data is not licensed for redistribution: its tests
run where the files are present and are skipped elsewhere.
"""

import csv
import dataclasses
import datetime
import hashlib
import json
import logging
import math

from pathlib import Path

import numpy as np
import pytest

from sqlalchemy import create_engine
from sqlalchemy import text

import gisfire_algorithms

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import cell_area_km2
from src.apps.thunderstorms import build_thunderstorms as app
from src.apps.thunderstorms import readers
from src.apps.thunderstorms import writers
from src.data_model import Base
from src.providers import catalonia_meteocat

UTC = datetime.timezone.utc

#: Where the synthetic storms are, in EPSG:25831 metres (inland Catalonia).
ORIGIN = (400_000.0, 4_600_000.0)

DAY = datetime.datetime(2020, 7, 13, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)
STORM = datetime.datetime(2020, 7, 13, 14, 0, tzinfo=UTC)

#: MeteoCat's strokes of the regression day. Git-ignored: kept locally only.
FIXTURE = Path(__file__).parents[2] / "fixtures" / "data" / "meteocat_lightning_2020-07-13.csv"

ALGORITHM = "cellsearch_tuomi_larjavaara"


# --------------------------------------------------------------------------
# Database and strokes
# --------------------------------------------------------------------------

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
def provider(database):
    """MeteoCat's provider row; its id."""
    engine, _ = database
    with engine.begin() as connection:
        return connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES (:n, :p, :f) RETURNING id"),
            {"n": catalonia_meteocat.PROVIDER_NAME, "p": catalonia_meteocat.PROVIDER_PRODUCT,
             "f": catalonia_meteocat.PROVIDER_FULL_NAME}).scalar_one()


@dataclasses.dataclass
class Stroke:
    """A synthetic stroke: an instant, a position (metres from ORIGIN), an error."""

    at: datetime.datetime
    dx: float
    dy: float
    flash: int
    error: float = 500.0
    version: int = 2
    id: int | None = None


INSERT_STROKE_SQL = """
WITH point AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 25831), 4258) AS etrs89
), parent AS (
    INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT 'meteocat_lightning', :provider_id, :at, ST_Transform(point.etrs89, 4326), -20.0, true
    FROM point
    RETURNING id
)
INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, stroke_index,
                                ellipse_major_axis, ellipse_minor_axis, geometry_etrs89)
SELECT parent.id, :version, :flash, 1, 1, :error, 0, point.etrs89
FROM parent, point
RETURNING id
"""


def add_strokes(engine, provider_id: int, strokes: list[Stroke]) -> list[Stroke]:
    """Store the strokes, in order, and set their ids."""
    with engine.begin() as connection:
        for stroke in strokes:
            stroke.id = connection.execute(text(INSERT_STROKE_SQL), {
                "x": ORIGIN[0] + stroke.dx, "y": ORIGIN[1] + stroke.dy,
                "provider_id": provider_id, "at": stroke.at, "version": stroke.version,
                "flash": stroke.flash, "error": stroke.error}).scalar_one()
    return strokes


def minutes(value: float, start: datetime.datetime = STORM) -> datetime.datetime:
    return start + datetime.timedelta(minutes=value)


def a_storm(first_flash: int, start: datetime.datetime, count: int, *, dx: float = 0.0,
            every_min: float = 4.0, spread_m: float = 2_000.0) -> list[Stroke]:
    """``count`` flashes of two strokes each, ``every_min`` apart, around ``(dx, 0)``.

    The first stroke of each flash is the accurate one (its representative); the
    second, a second later, is less accurate. The flashes go round a circle of
    radius ``spread_m``, so the cell has an area.
    """
    strokes = []
    for k in range(count):
        angle = 2 * math.pi * k / count
        x = dx + spread_m * math.cos(angle)
        y = spread_m * math.sin(angle)
        at = minutes(every_min * k, start)
        strokes.append(Stroke(at, x, y, first_flash + k, error=300.0))
        strokes.append(Stroke(at + datetime.timedelta(seconds=1), x + 150.0, y, first_flash + k,
                              error=900.0))
    return strokes


def run(url: str, *extra: str, start: datetime.datetime = DAY,
        end: datetime.datetime = NEXT_DAY) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["--provider", "MeteoCat", "--algorithm", ALGORITHM,
            "--from", start.isoformat(), "--to", end.isoformat(),
            "--db-host", host, "--db-port", port or "5432", "--db-name", name,
            "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + list(extra))


def scalar(engine, sql: str, **parameters):
    with engine.connect() as connection:
        return connection.execute(text(sql), parameters).scalar()


def rows(engine, sql: str, **parameters) -> list:
    with engine.connect() as connection:
        return list(connection.execute(text(sql), parameters))


def count(engine, table: str) -> int:
    return scalar(engine, f"SELECT count(*) FROM {table}")


def experiment(engine):
    return rows(engine, "SELECT * FROM thunderstorm_experiment")[0]


# --------------------------------------------------------------------------
# A run is stored
# --------------------------------------------------------------------------

@pytest.fixture
def two_storms(database, provider):
    """Storm A: 6 flashes (kept). Storm B, 50 km east, 2 h later: 3 flashes (not kept)."""
    engine, _ = database
    return add_strokes(engine, provider,
                       a_storm(100, STORM, 6) + a_storm(200, minutes(120), 3, dx=50_000.0))


def test_a_run_stores_the_kept_cell(database, two_storms):
    engine, url = database
    assert run(url) == 0
    storms = rows(engine, "SELECT * FROM thunderstorm")
    assert len(storms) == 1
    storm = storms[0]
    assert storm.label == 1
    assert storm.number_of_flashes == 6
    assert storm.number_of_lightnings == 12
    assert storm.date_time_start == STORM
    assert storm.date_time_end == minutes(20) + datetime.timedelta(seconds=1)


def test_every_stroke_of_a_kept_flash_is_linked(database, two_storms):
    engine, url = database
    assert run(url) == 0
    linked = {row.lightning_id for row in rows(engine, "SELECT * FROM thunderstorm_lightning")}
    assert linked == {stroke.id for stroke in two_storms[:12]}


def test_each_flash_stores_its_representative_and_the_running_centre(database, two_storms):
    engine, url = database
    assert run(url) == 0
    flashes = rows(engine, """
        SELECT sequence, lightning_id, ST_X(ST_Transform(centre, 25831)) AS x,
               ST_Y(ST_Transform(centre, 25831)) AS y
        FROM thunderstorm_cellsearch_flash ORDER BY sequence""")
    representatives = two_storms[:12:2]
    assert [flash.sequence for flash in flashes] == [1, 2, 3, 4, 5, 6]
    assert [flash.lightning_id for flash in flashes] == [stroke.id for stroke in representatives]
    for k, flash in enumerate(flashes, start=1):
        expected_x = ORIGIN[0] + np.mean([stroke.dx for stroke in representatives[:k]])
        expected_y = ORIGIN[1] + np.mean([stroke.dy for stroke in representatives[:k]])
        assert flash.x == pytest.approx(expected_x, abs=1e-3)
        assert flash.y == pytest.approx(expected_y, abs=1e-3)


def test_the_area_is_the_articles_over_the_representatives(database, two_storms):
    engine, url = database
    assert run(url) == 0
    representatives = two_storms[:12:2]
    expected = cell_area_km2([stroke.dx / 1000 for stroke in representatives],
                             [stroke.dy / 1000 for stroke in representatives])
    assert scalar(engine, "SELECT area FROM thunderstorm") == pytest.approx(expected, rel=1e-9)


def test_the_hull_is_a_polygon_over_the_representatives(database, two_storms):
    engine, url = database
    assert run(url) == 0
    kind, srid, covers_all, vertices = rows(engine, """
        SELECT GeometryType(t.concave_hull), ST_SRID(t.concave_hull),
               bool_and(ST_DWithin(ST_Transform(t.concave_hull, 25831),
                                   ST_Transform(l.geometry, 25831), 0.001)),
               ST_NPoints(t.concave_hull)
        FROM thunderstorm t
        JOIN thunderstorm_cellsearch_flash f ON f.thunderstorm_id = t.id
        JOIN lightning l ON l.id = f.lightning_id
        GROUP BY t.id""")[0]
    assert (kind, srid) == ("POLYGON", 4326)
    assert covers_all
    assert vertices == 7  # six points on a circle, closed


def test_the_experiment_is_complete_with_its_configuration(database, two_storms):
    engine, url = database
    assert run(url) == 0
    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.completed_at is not None
    assert stored.algorithm == "CELLSEARCH_TUOMI_LARJAVAARA_2005"
    assert stored.parameters == CellsearchParameters().to_dict()
    assert stored.lightning_filter == {"network": "newest"}
    assert stored.hull_parameters == {"ratio": 0.3, "allow_holes": False, "srid": 25831}
    assert stored.software_version == gisfire_algorithms.__version__
    assert (stored.date_time_start, stored.date_time_end) == (DAY, NEXT_DAY)


def test_the_summary_counts_cells_flashes_and_strokes(database, two_storms):
    engine, url = database
    assert run(url) == 0
    summary = experiment(engine).summary
    assert summary["flashes_total"] == 9
    assert summary["flashes_kept"] == 6
    assert summary["flashes_discarded_error"] == 0
    assert summary["cells_total"] == 2
    assert summary["cells_kept"] == 1
    assert summary["strokes_total"] == 18
    assert summary["size_classes"]["2-4"] == {"cells": 1, "flashes": 3}
    assert summary["size_classes"]["5-9"] == {"cells": 1, "flashes": 6}
    assert summary["cells_open_at_end"] == 0
    assert summary["activity_before_start"] is False


def test_the_parameters_given_are_the_ones_run_and_stored(database, two_storms):
    """N_min = 3 keeps storm B too; the stored parameters say so."""
    engine, url = database
    assert run(url, "--min-flashes", "3", "--time-distance-limit", "50") == 0
    assert count(engine, "thunderstorm") == 2
    assert {row.label for row in rows(engine, "SELECT label FROM thunderstorm")} == {1, 2}
    parameters = experiment(engine).parameters
    assert parameters["min_flashes"] == 3
    assert parameters["time_distance_limit_min_km"] == 50.0


def test_inaccurate_flashes_are_discarded_and_counted(database, provider):
    engine, url = database
    strokes = a_storm(100, STORM, 6)
    strokes.append(Stroke(minutes(1), 0.0, 0.0, 999, error=10_000.0))
    add_strokes(engine, provider, strokes)
    assert run(url) == 0
    assert experiment(engine).summary["flashes_discarded_error"] == 1
    assert scalar(engine, "SELECT number_of_lightnings FROM thunderstorm") == 12


def test_the_hull_ignores_the_far_stroke_of_a_merged_flash(database, provider):
    """A MeteoCat "flash" with a stroke 30 km away: linked and counted, out of the hull."""
    engine, url = database
    strokes = a_storm(100, STORM, 6)
    far = Stroke(minutes(0) + datetime.timedelta(seconds=2), 30_000.0, 0.0, 100, error=2_000.0)
    add_strokes(engine, provider, strokes + [far])
    assert run(url) == 0
    storm = rows(engine, "SELECT * FROM thunderstorm")[0]
    assert storm.number_of_lightnings == 13
    assert scalar(engine, "SELECT count(*) FROM thunderstorm_lightning WHERE lightning_id = :id",
                  id=far.id) == 1
    assert scalar(engine, """
        SELECT ST_DWithin(ST_Transform(t.concave_hull, 25831), ST_Transform(l.geometry, 25831), 1000)
        FROM thunderstorm t, lightning l WHERE l.id = :id""", id=far.id) is False
    hull_km2 = scalar(engine, "SELECT ST_Area(ST_Transform(concave_hull, 25831)) / 1e6 FROM thunderstorm")
    assert hull_km2 < 15.0  # a hexagon of radius 2 km is 10.4 km²


def test_a_cell_with_all_its_flashes_at_one_point_has_no_hull_and_no_area(database, provider):
    """Points in a line would do too, but a projection round trip bends them into a sliver."""
    engine, url = database
    strokes = [Stroke(minutes(k), 0.0, 0.0, 100 + k) for k in range(5)]
    add_strokes(engine, provider, strokes)
    assert run(url) == 0
    storm = rows(engine, "SELECT * FROM thunderstorm")[0]
    assert storm.number_of_flashes == 5
    assert storm.concave_hull is None
    assert storm.area is None


def test_a_period_without_strokes_completes_empty(database, provider, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url) == 0
    assert "No strokes in the period" in caplog.text
    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.summary["flashes_total"] == 0
    assert stored.summary["strokes_total"] == 0
    assert count(engine, "thunderstorm") == 0


def test_strokes_outside_the_window_are_not_read(database, provider):
    engine, url = database
    inside = a_storm(100, STORM, 6)
    after = a_storm(200, NEXT_DAY + datetime.timedelta(hours=2), 6)
    before = a_storm(300, DAY - datetime.timedelta(hours=2), 6)
    add_strokes(engine, provider, inside + after + before)
    assert run(url) == 0
    linked = {row.lightning_id for row in rows(engine, "SELECT * FROM thunderstorm_lightning")}
    assert linked == {stroke.id for stroke in inside}


# --------------------------------------------------------------------------
# Window truncation
# --------------------------------------------------------------------------

def test_a_storm_across_the_end_of_the_window_is_flagged(database, two_storms, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, end=minutes(10)) == 0
    assert experiment(engine).summary["cells_open_at_end"] == 1
    assert "may have been cut" in caplog.text


def test_a_cell_closed_before_the_end_is_not_flagged(database, two_storms):
    """Storm A's last flash is at 14:20 and T is 15 min: at 14:35:01 it is closed."""
    engine, url = database
    assert run(url, end=minutes(35) + datetime.timedelta(seconds=1)) == 0
    assert experiment(engine).summary["cells_open_at_end"] == 0


def test_activity_just_before_the_window_is_flagged(database, two_storms, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, start=minutes(10)) == 0
    assert experiment(engine).summary["activity_before_start"] is True
    assert "before the start" in caplog.text


def test_only_accepted_flashes_count_as_activity_before_the_window(database, provider):
    engine, url = database
    add_strokes(engine, provider, [Stroke(minutes(-5), 0.0, 0.0, 1, error=12_000.0)]
                + a_storm(100, STORM, 6))
    assert run(url, start=STORM) == 0
    assert experiment(engine).summary["activity_before_start"] is False


def test_activity_longer_before_the_window_is_not_flagged(database, provider):
    engine, url = database
    add_strokes(engine, provider, [Stroke(minutes(-16), 0.0, 0.0, 1)] + a_storm(100, STORM, 6))
    assert run(url, start=STORM) == 0
    assert experiment(engine).summary["activity_before_start"] is False


# --------------------------------------------------------------------------
# The run's life cycle
# --------------------------------------------------------------------------

def test_the_same_configuration_is_refused(database, two_storms, caplog):
    engine, url = database
    assert run(url) == 0
    with caplog.at_level(logging.ERROR):
        assert run(url) == 1
    assert "already stored as thunderstorm experiment" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 1
    assert count(engine, "thunderstorm") == 1


def test_another_parameter_is_another_experiment(database, two_storms):
    engine, url = database
    assert run(url) == 0
    assert run(url, "--inertia", "10") == 0
    assert count(engine, "thunderstorm_experiment") == 2
    assert count(engine, "thunderstorm") == 2


def _failing_after_first_piece(monkeypatch):
    calls = []

    def write(connection, experiment_id, flashes, srid):
        calls.append(experiment_id)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        writers.write_cellsearch_flashes(connection, experiment_id, flashes, srid)

    algorithm = dataclasses.replace(app.ALGORITHMS[ALGORITHM], write_specific=write)
    monkeypatch.setitem(app.ALGORITHMS, ALGORITHM, algorithm)
    monkeypatch.setattr(app, "PIECE_STROKES", 1)
    return calls


def test_a_failure_leaves_the_experiment_failed_and_empty(database, provider, monkeypatch, caplog):
    """The first piece was committed before the second failed; it is deleted too."""
    engine, url = database
    add_strokes(engine, provider, a_storm(100, STORM, 6) + a_storm(200, minutes(120), 6))
    calls = _failing_after_first_piece(monkeypatch)
    with caplog.at_level(logging.ERROR):
        assert run(url) == 1
    assert len(calls) == 2
    assert "disk full" in caplog.text
    stored = experiment(engine)
    assert stored.status == "failed"
    assert stored.completed_at is None
    assert count(engine, "thunderstorm") == 0
    assert count(engine, "thunderstorm_lightning") == 0
    assert count(engine, "thunderstorm_cellsearch_flash") == 0


def test_a_dry_run_writes_nothing(database, two_storms, caplog):
    engine, url = database
    with caplog.at_level(logging.INFO):
        assert run(url, "--dry-run") == 0
    assert "Would cluster 18 stroke(s) into 1 thunderstorm(s)" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 0
    assert count(engine, "thunderstorm") == 0


def test_a_failed_dry_run_writes_nothing(database, provider, monkeypatch):
    engine, url = database
    add_strokes(engine, provider, a_storm(100, STORM, 6) + a_storm(200, minutes(120), 6))
    _failing_after_first_piece(monkeypatch)
    assert run(url, "--dry-run") == 1
    assert count(engine, "thunderstorm_experiment") == 0


def test_running_in_pieces_gives_the_same_result(database, provider, monkeypatch):
    """Three storms more than T apart: one piece each, or all in one."""
    engine, url = database
    add_strokes(engine, provider, a_storm(100, STORM, 6) + a_storm(200, minutes(60), 7, dx=3_000.0)
                + a_storm(300, minutes(120), 8, dx=-4_000.0))
    query = """
        SELECT t.label, t.number_of_flashes, t.number_of_lightnings, t.area,
               ST_AsText(t.concave_hull) AS hull,
               array_agg(f.lightning_id ORDER BY f.sequence) AS flashes,
               array_agg(ST_AsText(f.centre) ORDER BY f.sequence) AS centres
        FROM thunderstorm t JOIN thunderstorm_cellsearch_flash f ON f.thunderstorm_id = t.id
        GROUP BY t.id ORDER BY t.label"""
    assert run(url) == 0
    whole = rows(engine, query)
    summary = experiment(engine).summary
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM thunderstorm_experiment"))

    monkeypatch.setattr(app, "PIECE_STROKES", 1)
    monkeypatch.setattr(readers, "FETCH_SIZE", 5)
    assert run(url) == 0
    assert rows(engine, query) == whole
    assert experiment(engine).summary == summary
    assert [row.label for row in whole] == [1, 2, 3]


def test_the_progress_is_logged(database, provider, monkeypatch, caplog):
    engine, url = database
    add_strokes(engine, provider, a_storm(100, STORM, 6) + a_storm(200, minutes(120), 6))
    monkeypatch.setattr(app, "PIECE_STROKES", 1)
    monkeypatch.setattr(app, "PROGRESS_EVERY", 6)
    with caplog.at_level(logging.INFO):
        assert run(url) == 0
    assert "12 stroke(s), 6 flash(es) so far, 1 thunderstorm(s) stored" in caplog.text
    assert "24 stroke(s), 12 flash(es) so far, 2 thunderstorm(s) stored" in caplog.text


def test_the_period_is_checked_when_called_as_a_library(database):
    engine, _ = database
    with pytest.raises(ValueError, match="--to must be later than --from"):
        app.build_thunderstorms(engine, "MeteoCat", ALGORITHM, CellsearchParameters(), NEXT_DAY,
                                DAY, logging.getLogger("test"))


def test_the_log_can_go_to_a_file(database, two_storms, tmp_path):
    _, url = database
    log = tmp_path / "build.log"
    assert run(url, "--log-file", str(log)) == 0
    assert "Clustered 18 stroke(s) into 1 thunderstorm(s)" in log.read_text()


# --------------------------------------------------------------------------
# What is refused before running
# --------------------------------------------------------------------------

def test_an_invalid_parameter_is_refused(database, two_storms, caplog):
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url, "--min-flashes", "2") == 1
    assert "min_flashes must be at least 3" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 0


def test_an_empty_period_is_refused(database, two_storms, caplog):
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url, start=NEXT_DAY, end=DAY) == 1
    assert "--to must be later than --from" in caplog.text


def test_a_missing_provider_is_refused(database, caplog):
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url) == 1
    assert "No data provider 'MeteoCat'" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 0


def test_an_unmigrated_database_is_refused(database, provider, caplog):
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE thunderstorm_lightning CASCADE"))
    with caplog.at_level(logging.ERROR):
        assert run(url) == 1
    assert "thunderstorm_lightning" in caplog.text


def test_an_unknown_algorithm_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--provider", "MeteoCat", "--from", "2020-07-13", "--to",
                             "2020-07-14", "--algorithm", "nope"])


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_the_flags_come_from_the_parameters_dataclass():
    args = app.parse_arguments([
        "--provider", "MeteoCat", "--from", "2020-07-13", "--to", "2020-07-14",
        "--algorithm", ALGORITHM, "--attraction-radius", "10", "--max-waiting-time", "20",
        "--time-distance-limit", "50", "--inertia", "5", "--max-location-error", "2",
        "--min-flashes", "4", "--srid", "3035"])
    parameters = app.parameters_from(args, app.ALGORITHMS[ALGORITHM])
    assert parameters == CellsearchParameters(10.0, 20.0, 50.0, 5, 2.0, 4, 3035)


def test_without_flags_the_parameters_are_the_defaults():
    args = app.parse_arguments(["--provider", "MeteoCat", "--from", "2020-07-13", "--to",
                                "2020-07-14", "--algorithm", ALGORITHM])
    assert app.parameters_from(args, app.ALGORITHMS[ALGORITHM]) == CellsearchParameters()


@pytest.mark.parametrize("name, flag, metavar", [
    ("attraction_radius_km", "--attraction-radius", "KM"),
    ("max_waiting_time_min", "--max-waiting-time", "MIN"),
    ("time_distance_limit_min_km", "--time-distance-limit", "MIN_KM"),
    ("min_flashes", "--min-flashes", "MIN_FLASHES"),
    ("srid", "--srid", "SRID"),
])
def test_a_flag_is_the_field_without_its_unit(name, flag, metavar):
    assert app.flag_name(name) == flag
    assert app.flag_metavar(name) == metavar


@pytest.mark.parametrize("value, expected", [
    ("2020-07-13", datetime.datetime(2020, 7, 13, tzinfo=UTC)),
    ("2020-07-13T14:00Z", datetime.datetime(2020, 7, 13, 14, tzinfo=UTC)),
    ("2020-07-13T16:00+02:00", datetime.datetime(2020, 7, 13, 14, tzinfo=UTC)),
])
def test_an_instant_without_offset_is_utc(value, expected):
    assert app.parse_instant(value) == expected


def test_a_bad_instant_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--provider", "MeteoCat", "--from", "yesterday", "--to",
                             "2020-07-14", "--algorithm", ALGORITHM])


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------

def strokes_at(seconds: list[float], keys: list[int] | None = None) -> Strokes:
    n = len(seconds)
    return Strokes(ids=np.arange(1, n + 1), flash_keys=keys or list(range(n)), t=seconds,
                   x=np.zeros(n), y=np.zeros(n), error=np.zeros(n))


def batches_of(strokes: Strokes, size: int):
    for start in range(0, len(strokes), size):
        yield app._take(strokes, slice(start, start + size))


def test_pieces_are_cut_at_gaps_longer_than_the_gap():
    strokes = strokes_at([0, 10, 1000, 1010, 1910, 3000])
    pieces = list(app.pieces(batches_of(strokes, 2), gap_s=900, piece_strokes=1))
    assert [piece.t.tolist() for piece in pieces] == [[0, 10], [1000, 1010, 1910], [3000]]


def test_pieces_keep_every_stroke_in_order():
    """Every gap is a cut here, so a piece is the target less the stretch kept back."""
    strokes = strokes_at(list(np.arange(0, 100_000, 400.0)))
    pieces = list(app.pieces(batches_of(strokes, 7), gap_s=300, piece_strokes=20))
    assert np.concatenate([piece.ids for piece in pieces]).tolist() == strokes.ids.tolist()
    assert all(19 <= len(piece) <= 21 for piece in pieces[:-1])


def test_the_strokes_before_the_start_are_set_aside():
    """Batches of two: the first lies wholly before 100, the second straddles it,
    and a stroke exactly at 100 belongs to the period."""
    strokes = strokes_at([10, 20, 30, 100, 150, 160])
    before = []
    after = list(app.split_before(batches_of(strokes, 2), 100.0, before))
    assert [batch.t.tolist() for batch in before] == [[10, 20], [30]]
    assert [batch.t.tolist() for batch in after] == [[100], [150, 160]]


def test_a_piece_never_splits_a_flash():
    """Strokes of flash 7 lie 1000 s apart: the gap between them cannot be a cut."""
    strokes = strokes_at([0, 1000, 2500], keys=[7, 7, 8])
    pieces = list(app.pieces(batches_of(strokes, 1), gap_s=900, piece_strokes=1))
    assert [piece.flash_keys.tolist() for piece in pieces] == [[7, 7], [8]]


def test_no_strokes_no_pieces():
    assert list(app.pieces(iter([]), gap_s=900, piece_strokes=1)) == []


# --------------------------------------------------------------------------
# The MeteoCat reader
# --------------------------------------------------------------------------

def read(engine, provider_id, start, end, srid=25831, fetch_size=None):
    with engine.connect() as connection:
        return list(readers.read_meteocat_strokes(connection, provider_id, start, end, srid,
                                                  fetch_size))


def test_the_reader_gives_metres_seconds_flash_keys_and_errors(database, provider):
    engine, _ = database
    stroke, = add_strokes(engine, provider, [Stroke(STORM, 1234.5, -678.9, 42, error=750.0)])
    batch, = read(engine, provider, DAY, NEXT_DAY)
    assert batch.ids.tolist() == [stroke.id]
    assert batch.flash_keys.tolist() == [2 * readers.METEOCAT_FLASH_KEY_FACTOR + 42]
    assert batch.t.tolist() == [STORM.timestamp()]
    assert batch.x[0] == pytest.approx(ORIGIN[0] + 1234.5, abs=1e-6)
    assert batch.y[0] == pytest.approx(ORIGIN[1] - 678.9, abs=1e-6)
    assert batch.error.tolist() == [750.0]


def test_the_reader_keeps_microseconds(database, provider):
    engine, _ = database
    at = STORM + datetime.timedelta(microseconds=123_457)
    add_strokes(engine, provider, [Stroke(at, 0.0, 0.0, 1)])
    batch, = read(engine, provider, DAY, NEXT_DAY)
    assert datetime.datetime.fromtimestamp(batch.t[0], UTC) == at


def test_the_reader_projects_to_another_crs(database, provider):
    engine, _ = database
    add_strokes(engine, provider, [Stroke(STORM, 0.0, 0.0, 1)])
    batch, = read(engine, provider, DAY, NEXT_DAY, srid=3035)
    expected = scalar(engine, """SELECT ST_X(ST_Transform(ST_Transform(
        ST_SetSRID(ST_MakePoint(:x, :y), 25831), 4258), 3035))""", x=ORIGIN[0], y=ORIGIN[1])
    assert batch.x[0] == pytest.approx(expected, abs=1e-6)


def test_the_reader_streams_in_time_order_in_batches(database, provider):
    engine, _ = database
    strokes = add_strokes(engine, provider,
                          [Stroke(minutes(10 - k), 0.0, 0.0, k) for k in range(5)])
    batches = read(engine, provider, DAY, NEXT_DAY, fetch_size=2)
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert np.concatenate([batch.ids for batch in batches]).tolist() == [
        stroke.id for stroke in reversed(strokes)]


def test_the_two_networks_do_not_share_flash_keys(database, provider):
    engine, _ = database
    add_strokes(engine, provider, [Stroke(datetime.datetime(2009, 8, 1, tzinfo=UTC), 0, 0, 5,
                                          version=1),
                                   Stroke(datetime.datetime(2009, 8, 2, tzinfo=UTC), 0, 0, 5,
                                          version=2)])
    batch, = read(engine, provider, datetime.datetime(2009, 1, 1, tzinfo=UTC),
                  datetime.datetime(2009, 8, 3, tzinfo=UTC))
    assert len(set(batch.flash_keys.tolist())) == 2


@pytest.fixture
def overlap(database, provider):
    """Version 1 runs until the end of September 2009; version 2 starts on the 1st."""
    engine, _ = database
    first_v2 = datetime.datetime(2009, 9, 1, 0, 6, tzinfo=UTC)
    return add_strokes(engine, provider, [
        Stroke(datetime.datetime(2009, 8, 31, 12, tzinfo=UTC), 0, 0, 1, version=1),
        Stroke(first_v2 - datetime.timedelta(seconds=1), 0, 0, 2, version=1),
        Stroke(first_v2, 0, 0, 3, version=1),
        Stroke(first_v2, 10, 0, 1, version=2),
        Stroke(datetime.datetime(2009, 9, 15, tzinfo=UTC), 0, 0, 4, version=1),
        Stroke(datetime.datetime(2009, 9, 15, 0, 0, 1, tzinfo=UTC), 10, 0, 2, version=2),
    ])


def ids_read(engine, provider_id, start, end) -> list[int]:
    return [identifier for batch in read(engine, provider_id, start, end)
            for identifier in batch.ids.tolist()]


def test_newest_network_drops_older_strokes_from_the_first_newer_one(database, provider, overlap):
    engine, _ = database
    ids = ids_read(engine, provider, datetime.datetime(2009, 8, 1, tzinfo=UTC),
                   datetime.datetime(2009, 10, 1, tzinfo=UTC))
    assert ids == [overlap[0].id, overlap[1].id, overlap[3].id, overlap[5].id]


def test_newest_network_does_not_depend_on_the_window(database, provider, overlap):
    """A window that starts after the first version 2 stroke still drops version 1."""
    engine, _ = database
    ids = ids_read(engine, provider, datetime.datetime(2009, 9, 10, tzinfo=UTC),
                   datetime.datetime(2009, 9, 20, tzinfo=UTC))
    assert ids == [overlap[5].id]


def test_newest_network_keeps_older_strokes_before_the_newer_one(database, provider, overlap):
    engine, _ = database
    ids = ids_read(engine, provider, datetime.datetime(2009, 8, 1, tzinfo=UTC),
                   datetime.datetime(2009, 9, 1, 0, 6, tzinfo=UTC))
    assert ids == [overlap[0].id, overlap[1].id]


def test_the_reader_only_reads_its_provider(database, provider):
    engine, _ = database
    add_strokes(engine, provider, [Stroke(STORM, 0, 0, 1)])
    with engine.begin() as connection:
        other = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES ('X', 'Y', 'Z') "
            "RETURNING id")).scalar_one()
    add_strokes(engine, other, [Stroke(STORM, 0, 0, 2)])
    assert len(ids_read(engine, provider, DAY, NEXT_DAY)) == 1


# --------------------------------------------------------------------------
# Regression: MeteoCat, 2020-07-13
# --------------------------------------------------------------------------

LOAD_FIXTURE_SQL = """
WITH staged AS MATERIALIZED (
    SELECT s.*, ST_SetSRID(ST_MakePoint(s.longitude, s.latitude), 4258) AS etrs89,
           CAST(nextval(pg_get_serial_sequence('lightning', 'id')) AS integer) AS id
    FROM (SELECT * FROM fixture ORDER BY source_row) AS s
), parents AS (
    INSERT INTO lightning (id, type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT id, 'meteocat_lightning', :provider_id, date_time, ST_Transform(etrs89, 4326),
           peak_current, cloud_to_ground
    FROM staged
    RETURNING id
)
INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, stroke_index,
                                ellipse_major_axis, ellipse_minor_axis, geometry_etrs89)
SELECT staged.id, network_version, flash_id, multiplicity, stroke_index, ellipse_major_axis,
       ellipse_minor_axis, etrs89
FROM staged JOIN parents ON parents.id = staged.id
"""


@pytest.fixture
def meteocat_2020_07_13(database, provider):
    """MeteoCat's strokes of 2020-07-13 (UTC), exported from gisfire_db, in id order."""
    engine, _ = database
    with FIXTURE.open(newline="") as handle:
        records = list(csv.DictReader(handle))
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TEMPORARY TABLE fixture (
                source_row integer, date_time timestamptz, longitude double precision,
                latitude double precision, network_version integer, flash_id integer,
                multiplicity integer, stroke_index integer, ellipse_major_axis double precision,
                ellipse_minor_axis double precision, peak_current double precision,
                cloud_to_ground boolean) ON COMMIT DROP"""))
        raw = connection.connection.driver_connection
        with raw.cursor() as cursor, cursor.copy("COPY fixture FROM STDIN") as copy:
            for row, record in enumerate(records):
                copy.write_row((row, *record.values()))
        connection.execute(text(LOAD_FIXTURE_SQL), {"provider_id": provider})
    return len(records)


#: What the runs of 2020-07-13 stored in gisfire_db, one per value of C, after
#: Jaume checked them in QGIS (2026-11-13). Written by
#: ``test/fixtures/data/export_cellsearch_2020-07-13.py`` with
#: :func:`stored_result`; regenerate it only for a deliberate change of output,
#: together with a bump of ``gisfire_algorithms.__version__``.
EXPECTED = FIXTURE.with_name("cellsearch_2020-07-13_expected.json")

#: The regression day's files are git-ignored (MeteoCat's data is not licensed
#: for redistribution), so its tests skip where they are missing.
requires_regression_day = pytest.mark.skipif(
    not (FIXTURE.exists() and EXPECTED.exists()),
    reason=f"the regression day is kept locally only: {FIXTURE.name} and {EXPECTED.name} not found")


def stored_result(connection, experiment_id: int) -> dict:
    """What an experiment stored, in a form that does not depend on database ids.

    For each thunderstorm, by label: its counts, time span and area, whether it
    has a hull, a digest of its flashes' times in sequence and its last centre.
    """
    summary = connection.execute(text(
        "SELECT summary FROM thunderstorm_experiment WHERE id = :id"), {"id": experiment_id}).scalar_one()
    storms = connection.execute(text("""
        SELECT t.label, t.number_of_flashes, t.number_of_lightnings, t.date_time_start,
               t.date_time_end, t.area, t.concave_hull IS NOT NULL AS has_hull,
               array_agg(l.date_time ORDER BY f.sequence) AS flash_times,
               (array_agg(ST_X(f.centre) ORDER BY f.sequence DESC))[1] AS last_centre_lon,
               (array_agg(ST_Y(f.centre) ORDER BY f.sequence DESC))[1] AS last_centre_lat
        FROM thunderstorm AS t
        JOIN thunderstorm_cellsearch_flash AS f ON f.thunderstorm_id = t.id
        JOIN lightning AS l ON l.id = f.lightning_id
        WHERE t.experiment_id = :id
        GROUP BY t.id
        ORDER BY t.label"""), {"id": experiment_id})

    def instant(value: datetime.datetime) -> str:
        return value.astimezone(UTC).isoformat()

    return {
        "summary": summary,
        "thunderstorms": [{
            "label": storm.label,
            "number_of_flashes": storm.number_of_flashes,
            "number_of_lightnings": storm.number_of_lightnings,
            "date_time_start": instant(storm.date_time_start),
            "date_time_end": instant(storm.date_time_end),
            "area": storm.area,
            "has_hull": storm.has_hull,
            "flash_times_sha1": hashlib.sha1(
                "|".join(instant(t) for t in storm.flash_times).encode()).hexdigest(),
            "last_centre": [storm.last_centre_lon, storm.last_centre_lat],
        } for storm in storms],
    }


def _expected() -> dict:
    with EXPECTED.open() as handle:
        return json.load(handle)


#: The values of C frozen, as the keys of :data:`EXPECTED`'s runs.
LIMITS = ("None", "10", "15", "25", "50", "100", "200")


@requires_regression_day
def test_every_frozen_run_is_tested():
    assert sorted(_expected()["runs"]) == sorted(LIMITS)


@requires_regression_day
@pytest.mark.parametrize("limit", LIMITS)
def test_regression_2020_07_13(database, meteocat_2020_07_13, limit):
    """A real day gives exactly what gisfire_db stored for each value of C.

    The database's runs read its own strokes; these read the exported fixture,
    so the test also shows that the fixture reproduces the database.
    """
    engine, url = database
    assert meteocat_2020_07_13 == 2947
    extra = () if limit == "None" else ("--time-distance-limit", limit)
    assert run(url, *extra) == 0

    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.parameters["time_distance_limit_min_km"] == (
        None if limit == "None" else float(limit))
    with engine.connect() as connection:
        actual = stored_result(connection, stored.id)
    expected = _expected()["runs"][limit]

    assert actual["summary"] == expected["summary"]
    assert len(actual["thunderstorms"]) == len(expected["thunderstorms"])
    for got, want in zip(actual["thunderstorms"], expected["thunderstorms"]):
        assert got["area"] == pytest.approx(want["area"], rel=1e-9)
        assert got["last_centre"] == pytest.approx(want["last_centre"], abs=1e-9)
        exact = {key: value for key, value in want.items() if key not in ("area", "last_centre")}
        assert {key: got[key] for key in exact} == exact

    summary = actual["summary"]
    assert summary["strokes_total"] == 2947
    assert summary["flashes_total"] == 2224
    assert summary["flashes_discarded_error"] == 15
    assert count(engine, "thunderstorm_cellsearch_flash") == summary["flashes_kept"]
    assert count(engine, "thunderstorm_lightning") == sum(
        storm["number_of_lightnings"] for storm in actual["thunderstorms"])
