#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The statistics and the CSV file of the Cellsearch sensitivity analysis.

The database part (the sweep, the stored thunderstorms, the recount of a
country's flashes) was checked against independent SQL on FMI's regression day;
these tests pin down the arithmetic and the file.
"""

import contextlib
import csv
import datetime
import logging
import math

from types import SimpleNamespace

import pytest

from sqlalchemy import create_engine
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_experiments.thunderstorms import cellsearch_tuomi_larjavaara as sweep
from gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara import FlashCounts
from gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara import Storm
from src.data_model import Base
from src.providers import catalonia_meteocat

UTC = datetime.timezone.utc


def test_the_statistics_of_a_run():
    storms = [Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=30.0),
              Storm(flashes=20, flashes_in_region=20, area_km2=400.0, duration_min=60.0),
              Storm(flashes=6, flashes_in_region=6, area_km2=50.0, duration_min=12.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=48, discarded=2))
    assert result["thunderstorms"] == 3
    assert result["flashes_discarded_error"] == 2
    assert result["flashes_clustered"] == 48
    # 36 flashes in thunderstorms: 12 isolated, a quarter.
    assert result["flashes_isolated"] == 12
    assert result["isolated_pct"] == pytest.approx(25.0)
    # Densities 10, 5 and 12 flashes per 100 km²: the median is 10.
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_mean_km"] == pytest.approx(
        (2 * math.sqrt(100 / math.pi) + 2 * math.sqrt(400 / math.pi) + 2 * math.sqrt(50 / math.pi)) / 3)
    assert result["duration_median_min"] == pytest.approx(30.0)


def test_an_even_number_of_thunderstorms_takes_the_mean_of_the_middle_two():
    storms = [Storm(flashes=5, flashes_in_region=5, area_km2=100.0, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["density_median_per_100km2"] == pytest.approx(7.5)
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_thunderstorm_without_area_counts_but_has_no_density_or_diameter():
    storms = [Storm(flashes=5, flashes_in_region=5, area_km2=None, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["thunderstorms"] == 2
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_mean_km"] == pytest.approx(2 * math.sqrt(100 / math.pi))
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_run_without_thunderstorms_has_empty_statistics():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=7, discarded=1))
    assert result["thunderstorms"] == 0
    assert result["flashes_isolated"] == 7
    assert result["isolated_pct"] == pytest.approx(100.0)
    assert result["density_median_per_100km2"] is None
    assert result["diameter_mean_km"] is None
    assert result["duration_median_min"] is None


def test_a_run_without_flashes_has_no_isolated_share():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=0, discarded=0))
    assert result["isolated_pct"] is None


def test_in_a_region_a_thunderstorm_counts_with_more_than_half_its_flashes_there():
    storms = [Storm(flashes=10, flashes_in_region=6, area_km2=100.0, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=5, area_km2=100.0, duration_min=20.0),
              Storm(flashes=10, flashes_in_region=0, area_km2=100.0, duration_min=30.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=20, discarded=0))
    assert result["thunderstorms"] == 1
    assert result["duration_median_min"] == pytest.approx(10.0)
    # The region's flashes in any thunderstorm are not isolated: 20 - (6 + 5).
    assert result["flashes_isolated"] == 9


def test_the_file_name_holds_the_algorithm_provider_country_and_period():
    start = datetime.datetime(2022, 8, 19, tzinfo=UTC)
    end = datetime.datetime(2022, 8, 20, 2, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    assert sweep.csv_filename("FMI", start, end) == \
        "cellsearch_tuomi_larjavaara_FMI_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, "Finland") == \
        "cellsearch_tuomi_larjavaara_FMI_Finland_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("USWFS", start, end, "United States") == \
        "cellsearch_tuomi_larjavaara_USWFS_United_States_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, suffix="times") == \
        "cellsearch_tuomi_larjavaara_times_FMI_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, suffix="times_runs") == \
        "cellsearch_tuomi_larjavaara_times_runs_FMI_20220819T000000Z_20220820T000000Z.csv"


def test_the_file_has_one_row_per_experiment_with_its_parameters_and_statistics(tmp_path):
    off = CellsearchParameters(srid=3067)
    limited = CellsearchParameters(attraction_radius_km=10, time_distance_limit_min_km=40,
                                   srid=3067)
    results = {
        off: sweep.thunderstorm_statistics(
            [Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=30.0)],
            FlashCounts(clustered=40, discarded=3)),
        limited: sweep.thunderstorm_statistics([], FlashCounts(clustered=40, discarded=3)),
    }
    path = tmp_path / "out" / "sweep.csv"
    sweep.write_csv(path, {off: 7, limited: 8}, results)
    rows = list(csv.reader(path.open()))
    assert rows[0] == sweep.CSV_COLUMNS
    assert rows[1] == ["7", "15", "15", "20", "", "1", "3", "40", "30", "75.0000", "10.0000",
                       f"{2 * math.sqrt(100 / math.pi):.4f}", "30.0000"]
    assert rows[2] == ["8", "10", "15", "20", "40", "0", "3", "40", "40", "100.0000", "", "", ""]


def test_each_run_logs_its_computation_time(monkeypatch, caplog):
    class NoDatabase:
        def connect(self):
            return contextlib.nullcontext()

    monkeypatch.setattr(sweep, "stored_experiment", lambda *args: None)
    monkeypatch.setattr(sweep, "build_thunderstorms", lambda *args, **kwargs: ({}, 1.5, 0.25))
    grid = [CellsearchParameters(srid=3067),
            CellsearchParameters(time_distance_limit_min_km=20, srid=3067)]
    start = datetime.datetime(2018, 7, 3, tzinfo=UTC)
    with caplog.at_level(logging.INFO):
        sweep.run_grid(NoDatabase(), 1, "FMI", grid, start, start + datetime.timedelta(days=1),
                       logging.getLogger("test"))
    assert ("Combination 1 of 2 (R 15 km, T 15 min, I 20, C off): computation time "
            "1.5000 s wall, 0.2500 s CPU") in caplog.text
    assert ("Combination 2 of 2 (R 15 km, T 15 min, I 20, C 20 min·km): computation time "
            "1.5000 s wall, 0.2500 s CPU") in caplog.text


# --- the two analyses ------------------------------------------------------------

PERIOD = ["--provider", "FMI", "--from", "2018-07-03", "--to", "2018-07-04"]


def test_one_analysis_must_be_chosen():
    for argv in (PERIOD, ["--sensitivity", "--time", *PERIOD]):
        with pytest.raises(SystemExit):
            sweep.parse_arguments(argv)


def test_the_time_analysis_runs_ten_iterations_unless_told():
    assert sweep.parse_arguments(["--time", *PERIOD]).iterations == sweep.ITERATIONS == 10
    assert sweep.parse_arguments(["--time", "--iterations", "17", *PERIOD]).iterations == 17
    assert sweep.parse_arguments(["--sensitivity", *PERIOD]).iterations is None


@pytest.mark.parametrize("argv", [["--sensitivity", "--iterations", "17"],
                                  ["--time", "--country", "Finland"],
                                  ["--time", "--iterations", "0"]])
def test_an_option_of_the_other_analysis_is_refused(argv):
    with pytest.raises(SystemExit):
        sweep.parse_arguments([*argv, *PERIOD])


def test_the_runs_go_round_the_grid_after_a_warm_up_round(monkeypatch):
    calls = []

    def fake_cellsearch(flashes, parameters):
        calls.append(parameters)
        return SimpleNamespace(wall_time_s=float(len(calls)), cpu_time_s=len(calls) / 10)

    monkeypatch.setattr(sweep, "cellsearch", fake_cellsearch)
    a, b = CellsearchParameters(), CellsearchParameters(inertia=40)
    samples = sweep.time_runs(None, [a, b], 2, logging.getLogger("test"))
    assert calls == [a, b, a, b, a, b]
    # The first round (calls 1 and 2) is the warm-up, not counted.
    assert samples == {a: [(3.0, 0.3), (5.0, 0.5)], b: [(4.0, 0.4), (6.0, 0.6)]}


def test_the_time_statistics_with_an_odd_number_of_runs():
    result = sweep.time_statistics([(3.0, 1.1), (1.0, 0.5), (2.0, 0.5)])
    assert result["iterations"] == 3
    assert (result["wall_min_s"], result["wall_median_s"], result["wall_max_s"]) == (1.0, 2.0, 3.0)
    assert result["wall_mean_s"] == pytest.approx(2.0)
    assert result["wall_std_s"] == pytest.approx(1.0)
    assert (result["cpu_min_s"], result["cpu_median_s"], result["cpu_max_s"]) == (0.5, 0.5, 1.1)
    assert result["cpu_mean_s"] == pytest.approx(0.7)
    assert result["cpu_std_s"] == pytest.approx(math.sqrt(0.12))


def test_the_median_of_an_even_number_of_runs_is_the_mean_of_the_middle_two():
    result = sweep.time_statistics([(4.0, 0.4), (1.0, 0.1), (3.0, 0.3), (2.0, 0.2)])
    assert result["wall_median_s"] == pytest.approx(2.5)
    assert result["cpu_median_s"] == pytest.approx(0.25)


def test_one_run_has_no_standard_deviation():
    result = sweep.time_statistics([(1.0, 0.5)])
    assert result["wall_std_s"] is None and result["cpu_std_s"] is None
    assert result["wall_min_s"] == result["wall_median_s"] == result["wall_max_s"] == 1.0


def test_the_time_file_has_one_row_per_combination(tmp_path):
    off = CellsearchParameters(srid=3067)
    limited = CellsearchParameters(time_distance_limit_min_km=40, srid=3067)
    results = {off: {**sweep.time_statistics([(0.001, 0.0009), (0.003, 0.0011)]), "host": "host-a"},
               limited: {**sweep.time_statistics([(0.25, 0.25)]), "host": "host-a"}}
    path = tmp_path / "out" / "times.csv"
    sweep.write_time_csv(path, results)
    rows = list(csv.reader(path.open()))
    assert rows[0] == ["attraction_radius_km", "max_waiting_time_min", "inertia",
                       "time_distance_limit_min_km", "iterations",
                       "wall_min_s", "wall_mean_s", "wall_median_s", "wall_std_s", "wall_max_s",
                       "cpu_min_s", "cpu_mean_s", "cpu_median_s", "cpu_std_s", "cpu_max_s", "host"]
    assert rows[1] == ["15", "15", "20", "", "2",
                       "0.001000", "0.002000", "0.002000", f"{math.sqrt(2e-6):.6f}", "0.003000",
                       "0.000900", "0.001000", "0.001000", f"{math.sqrt(2e-8):.6f}", "0.001100",
                       "host-a"]
    assert rows[2] == ["15", "15", "20", "40", "1",
                       "0.250000", "0.250000", "0.250000", "", "0.250000",
                       "0.250000", "0.250000", "0.250000", "", "0.250000", "host-a"]


def test_the_runs_file_has_every_run_in_the_order_they_ran(tmp_path):
    off = CellsearchParameters(srid=3067)
    limited = CellsearchParameters(time_distance_limit_min_km=40, srid=3067)
    # time_runs' order: round 1 is (off, limited), round 2 is (off, limited).
    samples = {off: [(0.001, 0.0009), (0.003, 0.0011)],
               limited: [(0.25, 0.24), (0.26, 0.25)]}
    path = tmp_path / "runs.csv"
    sweep.write_time_runs_csv(path, samples, "host-a")
    rows = list(csv.reader(path.open()))
    assert rows[0] == ["attraction_radius_km", "max_waiting_time_min", "inertia",
                       "time_distance_limit_min_km", "iteration", "wall_s", "cpu_s", "host"]
    assert rows[1:] == [["15", "15", "20", "", "1", "0.001000", "0.000900", "host-a"],
                        ["15", "15", "20", "40", "1", "0.250000", "0.240000", "host-a"],
                        ["15", "15", "20", "", "2", "0.003000", "0.001100", "host-a"],
                        ["15", "15", "20", "40", "2", "0.260000", "0.250000", "host-a"]]


# --- the time analysis against a database ------------------------------------------

DAY = datetime.datetime(2020, 7, 13, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)

#: One MeteoCat stroke, given in metres of EPSG:25831 (as the builder's tests do).
INSERT_STROKE_SQL = """
WITH point AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 25831), 4258) AS etrs89
), parent AS (
    INSERT INTO lightning (type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground)
    SELECT 'meteocat_lightning', :provider_id, :at, ST_Transform(point.etrs89, 4326), -20.0, TRUE
    FROM point
    RETURNING id
)
INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, stroke_index,
                                ellipse_major_axis, ellipse_minor_axis, geometry_etrs89)
SELECT parent.id, 2, :flash, 1, 1, 500.0, 0, point.etrs89
FROM parent, point
"""


@pytest.fixture
def database(postgresql):
    """The GisFIRE schema on an ephemeral PostgreSQL with one storm of MeteoCat strokes:
    6 flashes of 2 strokes, 4 min apart; the engine and the database arguments."""
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
        for flash in range(6):
            for stroke in range(2):
                connection.execute(text(INSERT_STROKE_SQL), {
                    "provider_id": provider_id, "flash": flash + 1,
                    "at": DAY + datetime.timedelta(hours=14, minutes=4 * flash, seconds=stroke),
                    "x": 400_000.0 + 300.0 * flash, "y": 4_600_000.0 + 100.0 * stroke})
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


def test_the_time_analysis_reads_the_strokes_and_writes_nothing(database, tmp_path, caplog):
    engine, arguments = database
    before = row_counts(engine)
    argv = ["--time", "--iterations", "2", "--provider", "MeteoCat", "--from", DAY.isoformat(),
            "--to", NEXT_DAY.isoformat(), "--output-dir", str(tmp_path), *arguments]
    with caplog.at_level(logging.INFO):
        assert sweep.main(argv) == 0
    assert row_counts(engine) == before
    assert before["lightning"] == 12 and before["thunderstorm_experiment"] == 0
    assert "6 flash(es) read" in caplog.text
    combinations = len(sweep.parameter_grid(25831))

    def records(suffix: str) -> list[dict[str, str]]:
        path = tmp_path / sweep.csv_filename("MeteoCat", DAY, NEXT_DAY, suffix=suffix)
        return list(csv.DictReader(path.open()))

    summary = records("times")
    assert len(summary) == combinations
    for record in summary:
        assert record["iterations"] == "2"
        for clock in ("wall", "cpu"):
            low, mean, high = (float(record[f"{clock}_{s}_s"]) for s in ("min", "mean", "max"))
            assert 0.0 <= low <= mean <= high and float(record[f"{clock}_std_s"]) >= 0.0
    runs = records("times_runs")
    assert len(runs) == 2 * combinations
    assert [run["iteration"] for run in runs] == ["1"] * combinations + ["2"] * combinations
