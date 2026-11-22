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
failure, dry run) and two real days, FMI's (CC BY 4.0) and the Alaska network's
(public domain). Both are in the repository, each loaded through its provider's
importer, and their tests always run. MeteoCat's data is not licensed for
redistribution, so no real MeteoCat day is used: its reader is tested on
synthetic strokes.
"""

import dataclasses
import datetime
import gzip
import hashlib
import json
import logging
import math
import sys

from pathlib import Path

import numpy as np
import pytest

from sqlalchemy import create_engine
from sqlalchemy import text

import gisfire_algorithms

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import cell_area_km2
from gisfire_algorithms.thunderstorm import discard_by_error
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.lightnings.alaska_uswfs import import_lightnings as alaska_import
from src.apps.imports.lightnings.finland_fmi import import_lightnings as fmi_import
from src.apps.imports.lightnings.finland_fmi import readers as fmi_readers
from src.apps.thunderstorms import build_thunderstorms as app
from src.apps.thunderstorms import readers
from src.apps.thunderstorms import writers
from src.data_model import Base
from src.providers import alaska_uswfs
from src.providers import catalonia_meteocat
from src.providers import finland_fmi

UTC = datetime.timezone.utc

#: Where the synthetic storms are, in EPSG:25831 metres (inland Catalonia).
ORIGIN = (400_000.0, 4_600_000.0)

DAY = datetime.datetime(2020, 7, 13, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)
STORM = datetime.datetime(2020, 7, 13, 14, 0, tzinfo=UTC)

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
    """A synthetic stroke: an instant, a position (metres from ORIGIN), an error.

    ``ground`` is ``lightning.cloud_to_ground``: false makes it a cloud stroke.
    """

    at: datetime.datetime
    dx: float
    dy: float
    flash: int
    error: float = 500.0
    version: int = 2
    id: int | None = None
    ground: bool = True


INSERT_STROKE_SQL = """
WITH point AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 25831), 4258) AS etrs89
), parent AS (
    INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT 'meteocat_lightning', :provider_id, :at, ST_Transform(point.etrs89, 4326), -20.0, :ground
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
                "flash": stroke.flash, "error": stroke.error,
                "ground": stroke.ground}).scalar_one()
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


#: N_min of these tests' runs: their synthetic storms have 6 to 8 flashes, fewer
#: than the default 10, and the regression days were frozen with 5.
MIN_FLASHES = 5

#: The default parameters of these tests' runs (their CRS is still the provider's).
PARAMETERS = CellsearchParameters(min_flashes=MIN_FLASHES)


def run(url: str, *extra: str, start: datetime.datetime = DAY,
        end: datetime.datetime = NEXT_DAY, provider: str = "MeteoCat",
        min_flashes: int | None = MIN_FLASHES, algorithm: str = ALGORITHM,
        zone: bool = False) -> int:
    """Run the application exactly as the command line would.

    ``--min-flashes MIN_FLASHES`` is passed unless ``extra`` gives its own or
    ``min_flashes`` is ``None`` (the application's default). ``--all-storms`` is
    passed unless ``zone``: most of these tests' databases hold no region, and the
    regression days were frozen with every storm.
    """
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["--provider", provider, "--algorithm", algorithm,
            "--from", start.isoformat(), "--to", end.isoformat(),
            "--db-host", host, "--db-port", port or "5432", "--db-name", name,
            "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    if min_flashes is not None and "--min-flashes" not in extra:
        argv += ["--min-flashes", str(min_flashes)]
    if not zone:
        argv.append("--all-storms")
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
    assert stored.parameters == PARAMETERS.to_dict()
    assert stored.lightning_filter == {"network": "newest", "cloud_to_ground": True}
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


def test_by_default_a_storm_needs_ten_flashes(database, two_storms):
    """Without ``--min-flashes`` N_min is 10: storm A's 6 flashes are not kept."""
    engine, url = database
    assert run(url, min_flashes=None) == 0
    stored = experiment(engine)
    assert stored.parameters == CellsearchParameters().to_dict()
    assert stored.parameters["min_flashes"] == 10
    assert count(engine, "thunderstorm") == 0
    assert (stored.summary["cells_total"], stored.summary["cells_kept"]) == (2, 0)


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


def test_the_computation_time_is_returned_and_not_stored(database, two_storms):
    engine, _ = database
    summary, wall_time_s, cpu_time_s = app.build_thunderstorms(
        engine, "MeteoCat", ALGORITHM, CellsearchParameters(), DAY, NEXT_DAY,
        logging.getLogger("test"), zone=False)
    stored = experiment(engine).summary
    assert summary == stored
    assert not {"wall_time_s", "cpu_time_s"} & stored.keys()
    for seconds in (wall_time_s, cpu_time_s):
        assert isinstance(seconds, float)
        assert math.isfinite(seconds) and seconds >= 0.0


def test_the_computation_time_is_added_up_over_the_pieces(database, two_storms, monkeypatch,
                                                          caplog):
    engine, _ = database
    real_cellsearch = app.cellsearch
    monkeypatch.setattr(app, "cellsearch", lambda *args, **kwargs: dataclasses.replace(
        real_cellsearch(*args, **kwargs), wall_time_s=1.0, cpu_time_s=0.5))
    monkeypatch.setattr(app, "PIECE_STROKES", 1)   # the two storms, two pieces
    with caplog.at_level(logging.INFO):
        _, wall_time_s, cpu_time_s = app.build_thunderstorms(
            engine, "MeteoCat", ALGORITHM, CellsearchParameters(), DAY, NEXT_DAY,
            logging.getLogger("test"), zone=False)
    assert (wall_time_s, cpu_time_s) == (2.0, 1.0)
    assert (f"{app.CELLSEARCH_ALGORITHM} computation time: 2.0000 s wall, 1.0000 s CPU, "
            f"over 2 piece(s)") in caplog.text


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
# FMI: its reader, its default CRS, a run
#
# FMI's strokes are stored in fmi_lightning; its reader keys flashes by
# flash_id alone and projects to EPSG:3067 unless told otherwise. A run over
# them without --srid must work in TM35FIN, not in MeteoCat's UTM 31N.
# --------------------------------------------------------------------------

#: Where the synthetic FMI storms are, in EPSG:3067 metres (near Helsinki).
FMI_ORIGIN = (385_000.0, 6_672_000.0)

INSERT_FMI_STROKE_SQL = """
WITH point AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 3067), 4258) AS etrs89
), parent AS (
    INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT 'fmi_lightning', :provider_id, :at, ST_Transform(point.etrs89, 4326), -20.0, :ground
    FROM point
    RETURNING id
)
INSERT INTO fmi_lightning (id, flash_id, multiplicity, stroke_index, published_multiplicity,
                           number_of_sensors, degrees_of_freedom, chi_squared,
                           ellipse_major_axis, ellipse_minor_axis, ellipse_angle, rise_time,
                           peak_to_zero_time, stroke_status, angle_indicator, signal_indicator,
                           timing_indicator, geometry_etrs89)
SELECT parent.id, :flash, 1, 1, 1, 4, 5, 0.5, :error, 0, 0, 5, 20, 17, 1, 0, 1, point.etrs89
FROM parent, point
RETURNING id
"""


@pytest.fixture
def fmi_provider(database):
    """FMI's provider row; its id."""
    engine, _ = database
    with engine.begin() as connection:
        return connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES (:n, :p, :f) RETURNING id"),
            {"n": finland_fmi.PROVIDER_NAME, "p": finland_fmi.PROVIDER_PRODUCT,
             "f": finland_fmi.PROVIDER_FULL_NAME}).scalar_one()


def add_fmi_strokes(engine, provider_id: int, strokes: list[Stroke]) -> list[Stroke]:
    """Store the strokes as FMI's, positions in metres from FMI_ORIGIN, whole seconds."""
    with engine.begin() as connection:
        for stroke in strokes:
            stroke.id = connection.execute(text(INSERT_FMI_STROKE_SQL), {
                "x": FMI_ORIGIN[0] + stroke.dx, "y": FMI_ORIGIN[1] + stroke.dy,
                "provider_id": provider_id, "at": stroke.at.replace(microsecond=0),
                "flash": stroke.flash, "error": stroke.error,
                "ground": stroke.ground}).scalar_one()
    return strokes


def read_fmi(engine, provider_id, start, end, srid=3067, fetch_size=None):
    with engine.connect() as connection:
        return list(readers.read_fmi_strokes(connection, provider_id, start, end, srid,
                                             fetch_size))


def test_the_fmi_reader_is_registered_with_its_crs_and_no_filter():
    reader = readers.READERS["FMI"]
    assert (reader.provider_name, reader.provider_product) == (finland_fmi.PROVIDER_NAME,
                                                               finland_fmi.PROVIDER_PRODUCT)
    assert reader.lightning_filter == {}
    assert reader.default_srid == 3067
    assert readers.READERS["MeteoCat"].default_srid == 25831


def test_the_fmi_reader_gives_metres_seconds_flash_ids_and_errors(database, fmi_provider):
    engine, _ = database
    stroke, = add_fmi_strokes(engine, fmi_provider, [Stroke(STORM, 1234.5, -678.9, 30645787,
                                                             error=700.0)])
    batch, = read_fmi(engine, fmi_provider, DAY, NEXT_DAY)
    assert batch.ids.tolist() == [stroke.id]
    # The flash id alone: FMI numbers its flashes in one sequence.
    assert batch.flash_keys.tolist() == [30645787]
    assert batch.t.tolist() == [STORM.timestamp()]
    assert batch.x[0] == pytest.approx(FMI_ORIGIN[0] + 1234.5, abs=1e-6)
    assert batch.y[0] == pytest.approx(FMI_ORIGIN[1] - 678.9, abs=1e-6)
    assert batch.error.tolist() == [700.0]


def test_the_fmi_reader_uses_the_indexed_expression_for_3067():
    assert finland_fmi.lightning.GEOMETRY_3067.format(column="f.geometry_etrs89") in \
        readers.fmi_strokes_sql(3067)
    assert "ST_Transform(f.geometry_etrs89, 3035)" in readers.fmi_strokes_sql(3035)


def test_the_fmi_reader_projects_to_another_crs(database, fmi_provider):
    engine, _ = database
    add_fmi_strokes(engine, fmi_provider, [Stroke(STORM, 0.0, 0.0, 1)])
    batch, = read_fmi(engine, fmi_provider, DAY, NEXT_DAY, srid=3035)
    expected = scalar(engine, """SELECT ST_X(ST_Transform(ST_Transform(
        ST_SetSRID(ST_MakePoint(:x, :y), 3067), 4258), 3035))""", x=FMI_ORIGIN[0], y=FMI_ORIGIN[1])
    assert batch.x[0] == pytest.approx(expected, abs=1e-6)


def test_the_fmi_reader_breaks_ties_of_one_second_by_id(database, fmi_provider):
    """Whole seconds: strokes of one second come in identifier order, in batches."""
    engine, _ = database
    strokes = add_fmi_strokes(engine, fmi_provider,
                              [Stroke(STORM, 10.0 * k, 0.0, 100 + k) for k in range(5)])
    batches = read_fmi(engine, fmi_provider, DAY, NEXT_DAY, fetch_size=2)
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert np.concatenate([batch.ids for batch in batches]).tolist() == [s.id for s in strokes]


def test_the_fmi_reader_only_reads_fmi(database, provider, fmi_provider):
    engine, _ = database
    add_strokes(engine, provider, [Stroke(STORM, 0, 0, 1)])
    add_fmi_strokes(engine, fmi_provider, [Stroke(STORM, 0, 0, 2)])
    assert len(read_fmi(engine, fmi_provider, DAY, NEXT_DAY)[0]) == 1


@pytest.mark.parametrize(("provider_name", "extra", "srid"), [
    pytest.param("FMI", [], 3067, id="fmi-default"),
    pytest.param("MeteoCat", [], 25831, id="meteocat-default"),
    pytest.param("USWFS", [], 3338, id="uswfs-default"),
    pytest.param("FMI", ["--srid", "3035"], 3035, id="fmi-explicit"),
    pytest.param("MeteoCat", ["--srid", "3067"], 3067, id="meteocat-explicit"),
    pytest.param("USWFS", ["--srid", "32606"], 32606, id="uswfs-explicit"),
])
def test_the_srid_defaults_to_the_providers(provider_name, extra, srid):
    args = app.parse_arguments(["--provider", provider_name, "--from", "2018-07-01", "--to",
                                "2018-07-02", "--algorithm", ALGORITHM, *extra])
    assert app.parameters_from(args, app.ALGORITHMS[ALGORITHM]).srid == srid


def test_the_srid_help_names_each_providers_default():
    help_text = " ".join(app.build_parser(ALGORITHM).format_help().split())
    assert "(default: the provider's, FMI 3067, MeteoCat 25831, USWFS 3338)" in help_text


def test_a_run_over_fmis_strokes_works_in_tm35fin(database, fmi_provider):
    engine, url = database
    add_fmi_strokes(engine, fmi_provider, a_storm(100, STORM, 6))
    assert run(url, provider="FMI") == 0

    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.parameters == CellsearchParameters(min_flashes=MIN_FLASHES, srid=3067).to_dict()
    assert stored.lightning_filter == {"cloud_to_ground": True}
    assert stored.hull_parameters == {"ratio": 0.3, "allow_holes": False, "srid": 3067}
    assert count(engine, "thunderstorm") == 1
    # The hull was built in TM35FIN and stored in EPSG:4326, around the storm.
    x, y = rows(engine, """SELECT ST_X(ST_Centroid(ST_Transform(concave_hull, 3067))),
                                  ST_Y(ST_Centroid(ST_Transform(concave_hull, 3067)))
                           FROM thunderstorm""")[0]
    assert x == pytest.approx(FMI_ORIGIN[0], abs=1_000)
    assert y == pytest.approx(FMI_ORIGIN[1], abs=1_000)


# --------------------------------------------------------------------------
# Ground strokes only, by default
#
# Cellsearch's article clustered ground flashes, so the readers read
# cloud-to-ground strokes only unless told otherwise, and the stored
# lightning_filter says which. FMI publishes cloud strokes (half of them or
# more from 2015), so it is where the filter matters.
# --------------------------------------------------------------------------

def cloud(strokes: list[Stroke]) -> list[Stroke]:
    """The same strokes, as cloud strokes."""
    return [dataclasses.replace(stroke, ground=False) for stroke in strokes]


@pytest.mark.parametrize("name", sorted(readers.READERS))
def test_the_stored_filter_adds_ground_only_to_the_providers(name):
    reader = readers.READERS[name]
    assert reader.filter_for(True) == {**reader.lightning_filter, "cloud_to_ground": True}
    assert reader.filter_for(False) == reader.lightning_filter


@pytest.mark.parametrize("sql", [
    pytest.param(lambda ground: readers.meteocat_strokes_sql(25831, {}, ground)[0], id="meteocat"),
    pytest.param(lambda ground: readers.fmi_strokes_sql(3067, ground), id="fmi"),
    pytest.param(lambda ground: readers.alaska_uswfs_strokes_sql(3338, ground), id="uswfs"),
])
def test_every_query_reads_ground_strokes_only_unless_told(sql):
    assert "AND l.cloud_to_ground" in sql(True)
    assert "cloud_to_ground" not in sql(False)


def test_the_fmi_reader_reads_ground_strokes_only_by_default(database, fmi_provider):
    engine, _ = database
    ground = add_fmi_strokes(engine, fmi_provider, [Stroke(STORM, 0.0, 0.0, 1)])
    clouds = add_fmi_strokes(engine, fmi_provider, cloud([Stroke(STORM, 50.0, 0.0, 2)]))
    batch, = read_fmi(engine, fmi_provider, DAY, NEXT_DAY)
    assert batch.ids.tolist() == [ground[0].id]
    with engine.connect() as connection:
        batch, = readers.read_fmi_strokes(connection, fmi_provider, DAY, NEXT_DAY, 3067,
                                          cloud_to_ground_only=False)
    assert sorted(batch.ids.tolist()) == sorted([ground[0].id, clouds[0].id])


def test_the_meteocat_reader_reads_ground_strokes_only_by_default(database, provider):
    engine, _ = database
    ground, cloud_stroke = add_strokes(engine, provider, [
        Stroke(STORM, 0.0, 0.0, 1), Stroke(minutes(1), 0.0, 0.0, 2, ground=False)])
    assert ids_read(engine, provider, DAY, NEXT_DAY) == [ground.id]
    with engine.connect() as connection:
        batch, = readers.read_meteocat_strokes(connection, provider, DAY, NEXT_DAY, 25831,
                                               cloud_to_ground_only=False)
    assert batch.ids.tolist() == [ground.id, cloud_stroke.id]


@pytest.fixture
def ground_and_cloud_storms(database, fmi_provider):
    """Two storms of 6 flashes over FMI's area, 50 km apart: one of ground strokes,
    one of cloud strokes."""
    engine, _ = database
    return add_fmi_strokes(engine, fmi_provider,
                           a_storm(100, STORM, 6) + cloud(a_storm(200, STORM, 6, dx=50_000.0)))


def test_a_run_clusters_ground_strokes_only_by_default(database, ground_and_cloud_storms):
    engine, url = database
    assert run(url, provider="FMI") == 0
    stored = experiment(engine)
    assert stored.lightning_filter == {"cloud_to_ground": True}
    assert stored.summary["strokes_total"] == 12
    assert stored.summary["flashes_total"] == 6
    assert count(engine, "thunderstorm") == 1
    assert scalar(engine, """SELECT count(*) FROM thunderstorm_lightning AS t
                             JOIN lightning AS l ON l.id = t.lightning_id
                             WHERE NOT l.cloud_to_ground""") == 0


def test_include_cloud_strokes_clusters_them_too_as_another_experiment(database,
                                                                       ground_and_cloud_storms):
    engine, url = database
    assert run(url, provider="FMI") == 0
    # Not the same configuration: it is not refused.
    assert run(url, "--include-cloud-strokes", provider="FMI") == 0
    stored = rows(engine, "SELECT * FROM thunderstorm_experiment ORDER BY id")
    assert [experiment_.lightning_filter for experiment_ in stored] == [
        {"cloud_to_ground": True}, {}]
    assert stored[1].summary["strokes_total"] == 24
    assert stored[1].summary["flashes_total"] == 12
    assert scalar(engine, "SELECT count(*) FROM thunderstorm WHERE experiment_id = :id",
                  id=stored[1].id) == 2
    # Run again, it is refused: the filter is part of the configuration.
    assert run(url, "--include-cloud-strokes", provider="FMI") == 1


def test_the_configuration_records_the_filter():
    start, end = DAY, NEXT_DAY
    ground = app.experiment_configuration(7, "FMI", ALGORITHM, CellsearchParameters(srid=3067),
                                          start, end, zone=False)
    both = app.experiment_configuration(7, "FMI", ALGORITHM, CellsearchParameters(srid=3067),
                                        start, end, cloud_to_ground_only=False, zone=False)
    assert ground["lightning_filter"] == {"cloud_to_ground": True}
    assert both["lightning_filter"] == {}
    assert {key: value for key, value in ground.items() if key != "lightning_filter"} == \
        {key: value for key, value in both.items() if key != "lightning_filter"}


# --------------------------------------------------------------------------
# USWFS (Alaska): its reader, its default CRS, a run
#
# The Alaska strokes are stored in alaska_uswfs_lightning, the point on
# lightning itself (published in WGS 84). Flashes are the import's: flash_id is
# the id of the flash's first stroke, which the table's CHECKs enforce, so the
# synthetic flashes are numbered the same way here. A NULL semi-major axis (a
# published 0) is read as larger than any E_max.
# --------------------------------------------------------------------------

#: Where the synthetic Alaska storms are, in EPSG:3338 metres (Fairbanks).
ALASKA_ORIGIN = (297_500.0, 1_667_300.0)

#: On the antimeridian, at 52° N (the western Aleutians), in EPSG:3338 metres.
ANTIMERIDIAN_ORIGIN = (-1_748_800.0, 567_750.0)

INSERT_ALASKA_STROKE_SQL = """
INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current, cloud_to_ground)
VALUES ('alaska_uswfs_lightning', :provider_id, :at,
        ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 3338), 4326), -20.0, :ground)
RETURNING id
"""

INSERT_ALASKA_CHILD_SQL = """
INSERT INTO alaska_uswfs_lightning (id, flash_id, multiplicity, stroke_index, network_code,
                                    sequence_number, gdop, ellipse_semi_major_axis,
                                    ellipse_semi_minor_axis, ellipse_angle)
VALUES (:id, :flash_id, :multiplicity, :stroke_index, 0, 1000, 2, :semi_major, :semi_minor, 10.0)
"""


@pytest.fixture
def alaska_provider(database):
    """USWFS's provider row; its id."""
    engine, _ = database
    with engine.begin() as connection:
        return connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES (:n, :p, :f) RETURNING id"),
            {"n": alaska_uswfs.PROVIDER_NAME, "p": alaska_uswfs.PROVIDER_PRODUCT,
             "f": alaska_uswfs.PROVIDER_FULL_NAME}).scalar_one()


def add_alaska_strokes(engine, provider_id: int, strokes: list[Stroke],
                       origin: tuple[float, float] = ALASKA_ORIGIN) -> list[Stroke]:
    """Store the strokes as USWFS's, positions in metres from ``origin``.

    ``Stroke.flash`` only groups them: the stored ``flash_id`` is the id of the
    first stroke of the group, as the import numbers them. ``error`` is the
    semi-major axis; ``None`` stores it as NULL (published as 0).
    """
    sizes: dict[int, int] = {}
    for stroke in strokes:
        sizes[stroke.flash] = sizes.get(stroke.flash, 0) + 1
    first: dict[int, int] = {}
    seen: dict[int, int] = {}
    with engine.begin() as connection:
        for stroke in strokes:
            stroke.id = connection.execute(text(INSERT_ALASKA_STROKE_SQL), {
                "x": origin[0] + stroke.dx, "y": origin[1] + stroke.dy,
                "provider_id": provider_id, "at": stroke.at,
                "ground": stroke.ground}).scalar_one()
            seen[stroke.flash] = seen.get(stroke.flash, 0) + 1
            connection.execute(text(INSERT_ALASKA_CHILD_SQL), {
                "id": stroke.id, "flash_id": first.setdefault(stroke.flash, stroke.id),
                "multiplicity": sizes[stroke.flash], "stroke_index": seen[stroke.flash],
                "semi_major": stroke.error,
                "semi_minor": 100.0 if stroke.error is None else min(stroke.error, 100.0)})
    return strokes


def read_alaska(engine, provider_id, start, end, srid=3338, fetch_size=None):
    with engine.connect() as connection:
        return list(readers.read_alaska_uswfs_strokes(connection, provider_id, start, end, srid,
                                                      fetch_size))


def test_the_alaska_reader_is_registered_with_its_crs_and_no_filter():
    reader = readers.READERS["USWFS"]
    assert (reader.provider_name, reader.provider_product) == ("USWFS", "ALDN")
    assert reader.lightning_filter == {}
    assert reader.default_srid == 3338


def test_the_alaska_reader_gives_metres_milliseconds_flash_ids_and_errors(database,
                                                                          alaska_provider):
    engine, _ = database
    at = STORM + datetime.timedelta(milliseconds=123)
    later = at + datetime.timedelta(milliseconds=40)
    first, second = add_alaska_strokes(engine, alaska_provider, [
        Stroke(at, 1234.5, -678.9, 1, error=2_000.0),
        Stroke(later, 1500.0, -500.0, 1, error=4_000.0)])
    batch, = read_alaska(engine, alaska_provider, DAY, NEXT_DAY)
    assert batch.ids.tolist() == [first.id, second.id]
    # The import's flash: the id of its first stroke, for both.
    assert batch.flash_keys.tolist() == [first.id, first.id]
    assert batch.t.tolist() == [at.timestamp(), later.timestamp()]
    assert batch.x[0] == pytest.approx(ALASKA_ORIGIN[0] + 1234.5, abs=1e-6)
    assert batch.y[0] == pytest.approx(ALASKA_ORIGIN[1] - 678.9, abs=1e-6)
    assert batch.error.tolist() == [2_000.0, 4_000.0]


def test_an_unknown_error_is_read_as_the_largest_float(database, alaska_provider):
    engine, _ = database
    add_alaska_strokes(engine, alaska_provider, [Stroke(STORM, 0.0, 0.0, 1, error=None)])
    batch, = read_alaska(engine, alaska_provider, DAY, NEXT_DAY)
    assert readers.UNKNOWN_ERROR_M == sys.float_info.max
    # Bound and read back exactly: still finite, larger than any E_max.
    assert batch.error.tolist() == [sys.float_info.max]
    assert np.isfinite(batch.error).all()


def test_an_unknown_error_never_represents_a_flash_with_a_known_one(database, alaska_provider):
    engine, _ = database
    unknown, known = add_alaska_strokes(engine, alaska_provider, [
        Stroke(STORM, 0.0, 0.0, 1, error=None),
        Stroke(STORM + datetime.timedelta(milliseconds=200), 500.0, 0.0, 1, error=9_000.0)])
    batch, = read_alaska(engine, alaska_provider, DAY, NEXT_DAY)
    flashes = strokes_to_flashes(batch)
    assert flashes.representative_id.tolist() == [known.id]
    # Even the largest E_max a run can take keeps the known stroke's flash only.
    kept, discarded = discard_by_error(flashes, 1e300)
    assert (kept.tolist(), discarded) == ([True], 0)


def test_a_flash_of_unknown_error_is_discarded_by_any_e_max(database, alaska_provider):
    engine, _ = database
    add_alaska_strokes(engine, alaska_provider, [Stroke(STORM, 0.0, 0.0, 1, error=None)])
    flashes = strokes_to_flashes(read_alaska(engine, alaska_provider, DAY, NEXT_DAY)[0])
    for max_error_m in (10_000.0, 1e300, sys.float_info.max):
        kept, discarded = discard_by_error(flashes, max_error_m)
        assert (kept.tolist(), discarded) == ([False], 1), max_error_m


def test_the_alaska_reader_uses_the_indexed_expression_for_3338():
    assert alaska_uswfs.lightning.GEOMETRY_3338.format(column="l.geometry") in \
        readers.alaska_uswfs_strokes_sql(3338)
    assert "ST_Transform(l.geometry, 32606)" in readers.alaska_uswfs_strokes_sql(32606)


def test_the_alaska_reader_projects_to_another_crs(database, alaska_provider):
    engine, _ = database
    add_alaska_strokes(engine, alaska_provider, [Stroke(STORM, 0.0, 0.0, 1)])
    batch, = read_alaska(engine, alaska_provider, DAY, NEXT_DAY, srid=32606)
    expected = scalar(engine, """SELECT ST_X(ST_Transform(ST_Transform(
        ST_SetSRID(ST_MakePoint(:x, :y), 3338), 4326), 32606))""",
                      x=ALASKA_ORIGIN[0], y=ALASKA_ORIGIN[1])
    assert batch.x[0] == pytest.approx(expected, abs=1e-6)


def test_the_alaska_reader_breaks_ties_of_one_millisecond_by_id(database, alaska_provider):
    engine, _ = database
    strokes = add_alaska_strokes(engine, alaska_provider,
                                 [Stroke(STORM, 20_000.0 * k, 0.0, k) for k in range(5)])
    batches = read_alaska(engine, alaska_provider, DAY, NEXT_DAY, fetch_size=2)
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert np.concatenate([batch.ids for batch in batches]).tolist() == [s.id for s in strokes]


def test_the_alaska_reader_only_reads_alaska(database, provider, fmi_provider, alaska_provider):
    engine, _ = database
    add_strokes(engine, provider, [Stroke(STORM, 0, 0, 1)])
    add_fmi_strokes(engine, fmi_provider, [Stroke(STORM, 0, 0, 2)])
    alaska, = add_alaska_strokes(engine, alaska_provider, [Stroke(STORM, 0, 0, 3)])
    batch, = read_alaska(engine, alaska_provider, DAY, NEXT_DAY)
    assert batch.ids.tolist() == [alaska.id]


def test_a_run_over_alaskas_strokes_works_in_alaska_albers(database, alaska_provider):
    engine, url = database
    add_alaska_strokes(engine, alaska_provider, a_storm(100, STORM, 6))
    assert run(url, provider="USWFS") == 0

    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.parameters == CellsearchParameters(min_flashes=MIN_FLASHES, srid=3338).to_dict()
    assert stored.lightning_filter == {"cloud_to_ground": True}
    assert stored.hull_parameters == {"ratio": 0.3, "allow_holes": False, "srid": 3338}
    assert stored.summary["flashes_total"] == 6
    assert count(engine, "thunderstorm") == 1
    assert scalar(engine, "SELECT number_of_lightnings FROM thunderstorm") == 12
    # The hull was built in Alaska Albers and stored in EPSG:4326, around the storm.
    x, y = rows(engine, """SELECT ST_X(ST_Centroid(ST_Transform(concave_hull, 3338))),
                                  ST_Y(ST_Centroid(ST_Transform(concave_hull, 3338)))
                           FROM thunderstorm""")[0]
    assert x == pytest.approx(ALASKA_ORIGIN[0], abs=1_000)
    assert y == pytest.approx(ALASKA_ORIGIN[1], abs=1_000)


def test_a_run_discards_the_flashes_of_unknown_error(database, alaska_provider):
    engine, url = database
    strokes = a_storm(100, STORM, 6)
    strokes.append(Stroke(minutes(1), 0.0, 0.0, 999, error=None))
    add_alaska_strokes(engine, alaska_provider, strokes)
    # E_max of 10,000 km: it would keep any located stroke on Earth.
    assert run(url, "--max-location-error", "10000", provider="USWFS") == 0
    assert experiment(engine).summary["flashes_discarded_error"] == 1
    assert scalar(engine, "SELECT number_of_lightnings FROM thunderstorm") == 12


def test_a_storm_across_the_antimeridian_is_one_cell(database, alaska_provider):
    """In Alaska Albers a storm astride 180° is one place, not two halves 360° apart."""
    engine, url = database
    strokes = add_alaska_strokes(engine, alaska_provider, a_storm(100, STORM, 6),
                                 origin=ANTIMERIDIAN_ORIGIN)
    longitudes = [row[0] for row in rows(engine, "SELECT ST_X(geometry) FROM lightning")]
    assert min(longitudes) < -179.9 and max(longitudes) > 179.9
    assert run(url, provider="USWFS") == 0

    storm = rows(engine, "SELECT * FROM thunderstorm")[0]
    assert count(engine, "thunderstorm") == 1
    assert storm.number_of_flashes == 6
    assert storm.number_of_lightnings == len(strokes)
    # The hull: some 4 km across in Alaska Albers, around the storm.
    width, x, y = rows(engine, """
        SELECT ST_XMax(h.hull) - ST_XMin(h.hull), ST_X(ST_Centroid(h.hull)),
               ST_Y(ST_Centroid(h.hull))
        FROM thunderstorm, LATERAL (SELECT ST_Transform(concave_hull, 3338) AS hull) AS h""")[0]
    assert width == pytest.approx(4_000, abs=10)
    assert (x, y) == (pytest.approx(ANTIMERIDIAN_ORIGIN[0], abs=1_000),
                      pytest.approx(ANTIMERIDIAN_ORIGIN[1], abs=1_000))


# --------------------------------------------------------------------------
# Regression days: what a run stored, and how two are compared
#
# Shared by the FMI and Alaska days below and by their freeze scripts.
# --------------------------------------------------------------------------

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


def assert_same_result(actual: dict, expected: dict) -> None:
    """A run's :func:`stored_result` equals a frozen one: exactly, but for the area
    and the last centre, which are floats computed in the database."""
    assert actual["summary"] == expected["summary"]
    assert len(actual["thunderstorms"]) == len(expected["thunderstorms"])
    for got, want in zip(actual["thunderstorms"], expected["thunderstorms"]):
        assert got["area"] == pytest.approx(want["area"], rel=1e-9)
        assert got["last_centre"] == pytest.approx(want["last_centre"], abs=1e-9)
        exact = {key: value for key, value in want.items() if key not in ("area", "last_centre")}
        assert {key: got[key] for key in exact} == exact


#: The values of C frozen, as the keys of each frozen file's runs.
LIMITS = ("None", "10", "15", "25", "50", "100", "200")


# --------------------------------------------------------------------------
# Regression: FMI, 2018-07-03
#
# A real day that can be published (FMI open data, CC BY 4.0), so its tests
# always run. It is loaded through the FMI importer, as a monthly file, so the
# strokes get their identifiers in the importer's content order — the order
# that breaks ties between strokes of the same second — exactly as they would
# in gisfire_db. The file also holds the hour before the day, which a real
# database has too and the look-back before the window reads.
# --------------------------------------------------------------------------

#: FMI's strokes of 2018-07-02 23:00 to 2018-07-04 00:00 UTC, as the downloader
#: wrote them. Source: Finnish Meteorological Institute (FMI), open data, CC BY 4.0.
FMI_DAY = Path(__file__).parents[2] / "fixtures" / "data" / "fmi_regression" / "fmi_lightning_2018-07-03.csv"

#: What the seven runs of 2018-07-03 stored, written by
#: ``test/fixtures/data/fmi_regression/freeze_cellsearch_2018-07-03.py``; see
#: its README. Regenerate it only for a deliberate change of output: an
#: algorithm's (with a bump of ``gisfire_algorithms.__version__``) or the
#: builder's defaults' (the runs are ground strokes only, the default, with
#: N_min = MIN_FLASHES).
FMI_EXPECTED = FMI_DAY.with_name("cellsearch_2018-07-03_expected.json")

FMI_DAY_START = datetime.datetime(2018, 7, 3, tzinfo=UTC)
FMI_DAY_END = FMI_DAY_START + datetime.timedelta(days=1)


def load_fmi_day(engine, provider_id: int, directory: Path, source: Path = FMI_DAY) -> int:
    """Import the FMI regression day with the FMI importer; how many strokes it holds.

    The importer reads monthly files, so the day (``source``, the fixture by
    default) is written to ``directory`` as the month's file first.
    """
    path = directory / f"{finland_fmi.FILE_STEM}_2018-07.csv.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(source.read_bytes())
    content = fmi_readers.read_month(path)
    if content.problems:
        raise RuntimeError(f"the regression day has refused rows: {content.problems[:3]}")
    log = ArchiveLogger(logging.getLogger("fmi-regression-day"), {"archive": path.name})
    with engine.connect() as connection:
        fmi_import.import_month(connection, content, provider_id, None, log)
    return len(content.records)


@pytest.fixture
def fmi_2018_07_03(database, fmi_provider, tmp_path):
    """FMI's strokes of the regression day, imported."""
    engine, _ = database
    return load_fmi_day(engine, fmi_provider, tmp_path)


def _fmi_expected() -> dict:
    with FMI_EXPECTED.open() as handle:
        return json.load(handle)


def test_every_frozen_fmi_run_is_tested():
    assert sorted(_fmi_expected()["runs"]) == sorted(LIMITS)


def test_the_fmi_runs_were_frozen_with_the_current_version():
    """A change of output comes with a version bump and a new frozen file."""
    expected = _fmi_expected()
    assert expected["software_version"] == gisfire_algorithms.__version__
    frozen = CellsearchParameters(min_flashes=MIN_FLASHES, srid=3067)
    assert expected["parameters_but_c"] == {
        key: value for key, value in frozen.to_dict().items()
        if key != "time_distance_limit_min_km"}
    # The runs are the default ones: ground strokes only.
    assert expected["lightning_filter"] == {"cloud_to_ground": True}


@pytest.mark.parametrize("limit", LIMITS)
def test_regression_fmi_2018_07_03(database, fmi_2018_07_03, limit):
    """A real FMI day gives exactly the frozen result for each value of C."""
    engine, url = database
    assert fmi_2018_07_03 == 3178
    extra = () if limit == "None" else ("--time-distance-limit", limit)
    assert run(url, *extra, start=FMI_DAY_START, end=FMI_DAY_END, provider="FMI") == 0

    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.parameters["srid"] == 3067
    assert stored.lightning_filter == _fmi_expected()["lightning_filter"]
    assert stored.parameters["time_distance_limit_min_km"] == (
        None if limit == "None" else float(limit))
    with engine.connect() as connection:
        actual = stored_result(connection, stored.id)
    assert_same_result(actual, _fmi_expected()["runs"][limit])

    summary = actual["summary"]
    # The hour before the day is read only as look-back: a storm was going on.
    assert summary["activity_before_start"] is True
    assert count(engine, "thunderstorm_cellsearch_flash") == summary["flashes_kept"]
    assert count(engine, "thunderstorm_lightning") == sum(
        storm["number_of_lightnings"] for storm in actual["thunderstorms"])


def test_the_fmi_day_with_cloud_strokes_reads_them_all(database, fmi_2018_07_03):
    """Half of the day's strokes are cloud strokes, each a flash of its own: the
    frozen runs leave them out, ``--include-cloud-strokes`` reads them."""
    engine, url = database
    assert run(url, "--include-cloud-strokes", start=FMI_DAY_START, end=FMI_DAY_END,
               provider="FMI") == 0
    stored = experiment(engine)
    assert stored.lightning_filter == {}
    assert scalar(engine, """SELECT count(*) FROM lightning
                             WHERE date_time >= :start AND date_time < :end""",
                  start=FMI_DAY_START, end=FMI_DAY_END) == stored.summary["strokes_total"] == 3069
    assert stored.summary["flashes_total"] == 2488
    ground = _fmi_expected()["runs"]["None"]["summary"]
    assert (ground["strokes_total"], ground["flashes_total"]) == (1481, 900)


@pytest.mark.parametrize("limit", ["None", "50"])
def test_the_fmi_regression_does_not_depend_on_the_order_of_the_file(database, fmi_provider,
                                                                     tmp_path, limit):
    """FMI returns a second's strokes in no stable order: a second download of the
    day holds the same rows in another order, and must give the same result."""
    import random

    engine, url = database
    header, *rows = FMI_DAY.read_text().splitlines()
    random.Random(2018).shuffle(rows)
    shuffled = tmp_path / "shuffled.csv"
    shuffled.write_text("\n".join([header, *rows]) + "\n")
    assert load_fmi_day(engine, fmi_provider, tmp_path, shuffled) == 3178

    extra = () if limit == "None" else ("--time-distance-limit", limit)
    assert run(url, *extra, start=FMI_DAY_START, end=FMI_DAY_END, provider="FMI") == 0
    with engine.connect() as connection:
        actual = stored_result(connection, experiment(engine).id)
    assert_same_result(actual, _fmi_expected()["runs"][limit])


# --------------------------------------------------------------------------
# Regression: USWFS (Alaska), 2019-06-30
#
# A real day of the Alaska network that can be published (public domain, the
# USWFS cited), so its tests always run. It is loaded through the Alaska
# importer from the strokes file as the release ships it, so the flashes are
# the importer's (the release has none) and the ids follow its content order.
# The window is 2019-06-30 12:00 to 2019-07-01 12:00 UTC, 04:00 to 04:00 in
# Alaska (AKDT): a UTC day would cut the afternoon storms, which peak around
# midnight UTC. The file also holds the hour before, which the look-back reads.
# --------------------------------------------------------------------------

#: The Alaska network's strokes of 2019-06-30 11:00 to 2019-07-01 12:00 UTC, cut
#: verbatim from the release. Source: U.S. Wildland Fire Service (USWFS), Alaska
#: Lightning Detection Network, public domain; see the README beside it.
ALASKA_DAY = (Path(__file__).parents[2] / "fixtures" / "data" / "alaska_uswfs_regression"
              / "alaska_uswfs_lightning_2019-06-30.txt")

#: What the seven runs of the day stored, written by
#: ``test/fixtures/data/alaska_uswfs_regression/freeze_cellsearch_2019-06-30.py``;
#: see its README. Regenerate it only for a deliberate change of output: an
#: algorithm's (with a bump of ``gisfire_algorithms.__version__``) or the
#: builder's defaults' (the runs are ground strokes only, the default, with
#: N_min = MIN_FLASHES).
ALASKA_EXPECTED = ALASKA_DAY.with_name("cellsearch_2019-06-30_expected.json")

ALASKA_DAY_START = datetime.datetime(2019, 6, 30, 12, tzinfo=UTC)
ALASKA_DAY_END = ALASKA_DAY_START + datetime.timedelta(days=1)

#: Rows of the file, and strokes the importer writes from them.
ALASKA_DAY_ROWS = 5892
ALASKA_DAY_STROKES = 5892


def load_alaska_day(engine, source: Path = ALASKA_DAY) -> int:
    """Import the Alaska regression day (``source``, the fixture by default) with the
    Alaska importer, exactly as the command line would; the strokes written."""
    args = alaska_import.parse_arguments(["-s", str(source)])
    return alaska_import.import_lightnings(args, engine, logging.getLogger("alaska-regression-day"))


@pytest.fixture
def alaska_2019_06_30(database):
    """The Alaska network's strokes of the regression day, imported."""
    engine, _ = database
    return load_alaska_day(engine)


def _alaska_expected() -> dict:
    with ALASKA_EXPECTED.open() as handle:
        return json.load(handle)


def test_the_alaska_day_is_the_window_and_the_hour_before():
    header, *rows = ALASKA_DAY.read_text(encoding="utf-8-sig").splitlines()
    assert tuple(header.split(",")) == alaska_uswfs.FILE_COLUMNS
    assert len(rows) == ALASKA_DAY_ROWS
    instants = [datetime.datetime.strptime(row.split(",")[2], "%m/%d/%Y %H:%M:%S")
                .replace(tzinfo=UTC) for row in rows]
    assert instants == sorted(instants)
    assert ALASKA_DAY_START - datetime.timedelta(hours=1) <= instants[0] < ALASKA_DAY_START
    assert instants[-1] < ALASKA_DAY_END


def test_every_frozen_alaska_run_is_tested():
    assert sorted(_alaska_expected()["runs"]) == sorted(LIMITS)


def test_the_alaska_runs_were_frozen_with_the_current_version():
    """A change of output comes with a version bump and a new frozen file."""
    expected = _alaska_expected()
    assert expected["software_version"] == gisfire_algorithms.__version__
    frozen = CellsearchParameters(min_flashes=MIN_FLASHES, srid=3338)
    assert expected["parameters_but_c"] == {
        key: value for key, value in frozen.to_dict().items()
        if key != "time_distance_limit_min_km"}
    # The runs are the default ones: ground strokes only.
    assert expected["lightning_filter"] == {"cloud_to_ground": True}


@pytest.mark.parametrize("limit", LIMITS)
def test_regression_alaska_2019_06_30(database, alaska_2019_06_30, limit):
    """A real Alaska day gives exactly the frozen result for each value of C."""
    engine, url = database
    assert alaska_2019_06_30 == ALASKA_DAY_STROKES
    extra = () if limit == "None" else ("--time-distance-limit", limit)
    assert run(url, *extra, start=ALASKA_DAY_START, end=ALASKA_DAY_END, provider="USWFS") == 0

    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.parameters["srid"] == 3338
    assert stored.lightning_filter == _alaska_expected()["lightning_filter"]
    assert stored.parameters["time_distance_limit_min_km"] == (
        None if limit == "None" else float(limit))
    with engine.connect() as connection:
        actual = stored_result(connection, stored.id)
    assert_same_result(actual, _alaska_expected()["runs"][limit])

    summary = actual["summary"]
    # Ground strokes only: 5,774 strokes and 3,764 flashes with the cloud ones.
    assert summary["strokes_total"] == 5604
    assert summary["flashes_total"] == 3605
    assert summary["flashes_discarded_error"] == 325
    assert count(engine, "thunderstorm_cellsearch_flash") == summary["flashes_kept"]
    assert count(engine, "thunderstorm_lightning") == sum(
        storm["number_of_lightnings"] for storm in actual["thunderstorms"])
    # No flash a cell kept is represented by a stroke of unknown error.
    assert scalar(engine, """
        SELECT count(*) FROM thunderstorm_cellsearch_flash AS f
        JOIN alaska_uswfs_lightning AS a ON a.id = f.lightning_id
        WHERE a.ellipse_semi_major_axis IS NULL""") == 0


def test_the_alaska_day_has_flashes_of_unknown_error_and_e_max_drops_them(database,
                                                                         alaska_2019_06_30):
    """The window holds flashes with no stroke of known error (the network published
    no semi-major axis from 11:20 to 16:07 UTC): 30, of which 29 are ground flashes.
    Every run discards those it reads."""
    engine, url = database
    unknown = rows(engine, """
        SELECT ground, count(*) AS flashes FROM (
            SELECT a.flash_id, bool_and(l.cloud_to_ground) AS ground
            FROM alaska_uswfs_lightning AS a JOIN lightning AS l ON l.id = a.id
            WHERE l.date_time >= :start AND l.date_time < :end
            GROUP BY a.flash_id
            HAVING bool_and(a.ellipse_semi_major_axis IS NULL)) AS flash
        GROUP BY ground ORDER BY ground""",
                   start=ALASKA_DAY_START, end=ALASKA_DAY_END)
    assert [(row.ground, row.flashes) for row in unknown] == [(False, 1), (True, 29)]
    # Even an E_max of 10,000 km discards exactly those, the ground ones by default.
    assert run(url, "--max-location-error", "10000", start=ALASKA_DAY_START,
               end=ALASKA_DAY_END, provider="USWFS") == 0
    assert experiment(engine).summary["flashes_discarded_error"] == 29
    assert run(url, "--max-location-error", "10000", "--include-cloud-strokes",
               start=ALASKA_DAY_START, end=ALASKA_DAY_END, provider="USWFS") == 0
    assert rows(engine, "SELECT summary FROM thunderstorm_experiment ORDER BY id")[1].summary[
        "flashes_discarded_error"] == 30


@pytest.mark.parametrize("limit", ["None", "50"])
def test_the_alaska_regression_does_not_depend_on_the_order_of_the_file(database, tmp_path,
                                                                        limit):
    """The importer draws ids in content order, so the same rows in another order
    give the same strokes, flashes and cells."""
    import random

    engine, url = database
    header, *rows = ALASKA_DAY.read_bytes().rstrip(b"\n").split(b"\n")
    random.Random(2019).shuffle(rows)
    shuffled = tmp_path / "shuffled.txt"
    shuffled.write_bytes(b"\n".join([header, *rows]) + b"\n")
    assert load_alaska_day(engine, shuffled) == ALASKA_DAY_STROKES

    extra = () if limit == "None" else ("--time-distance-limit", limit)
    assert run(url, *extra, start=ALASKA_DAY_START, end=ALASKA_DAY_END, provider="USWFS") == 0
    with engine.connect() as connection:
        actual = stored_result(connection, experiment(engine).id)
    assert_same_result(actual, _alaska_expected()["runs"][limit])
