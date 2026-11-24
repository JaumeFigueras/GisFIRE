#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The thunderstorm sweep: Cellsearch and the time-distance clustering.

The database part (the sweep and the stored thunderstorms) was checked against
independent SQL on FMI's regression day; these tests pin down the grids, the
arithmetic, the files, and that a run's statistics follow rule 2 of the
thunderstorm rules: from its flashes' representative strokes, its zone flashes
for everything but its time.
"""

import contextlib
import csv
import datetime
import logging
import math

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from sqlalchemy import create_engine
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import TimeDistanceParameters
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from gisfire_experiments.thunderstorms import sweep
from gisfire_experiments.thunderstorms.sweep import FlashCounts
from gisfire_experiments.thunderstorms.sweep import Storm
from src.apps.thunderstorms.build_thunderstorms import ALGORITHMS
from src.apps.thunderstorms.build_thunderstorms import build_thunderstorms
from src.apps.thunderstorms.zones import in_zone
from src.apps.thunderstorms.zones import read_region
from src.data_model import Base
from src.providers import catalonia_meteocat

UTC = datetime.timezone.utc

CELLSEARCH = "cellsearch_tuomi_larjavaara"
TIME_DISTANCE = "time_distance_galanaki"


def test_the_statistics_of_a_run():
    storms = [Storm(flashes=10, area_km2=100.0, duration_min=30.0),
              Storm(flashes=20, area_km2=400.0, duration_min=60.0),
              Storm(flashes=6, area_km2=50.0, duration_min=12.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=48, discarded=2))
    assert result["thunderstorms"] == 3
    assert result["flashes_discarded_error"] == 2
    assert result["flashes_clustered"] == 48
    # 36 flashes in thunderstorms: 12 isolated, a quarter.
    assert result["flashes_isolated"] == 12
    assert result["isolated_pct"] == pytest.approx(25.0)
    # Densities 10, 5 and 12 flashes per 100 km²: the median is 10.
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_median_km"] == pytest.approx(2 * math.sqrt(100 / math.pi))
    # Type 8 places the largest of three at (3 - 1/3) / (3 + 1/3) = 0.8: beyond
    # it, the 90th percentile is the largest diameter.
    assert result["diameter_p90_km"] == pytest.approx(2 * math.sqrt(400 / math.pi))
    assert result["duration_median_min"] == pytest.approx(30.0)


def test_the_diameter_percentile_is_hyndman_and_fans_type_8():
    """Diameters of 1 to 11 km: the 90th percentile sits at the sorted position
    (n + 1/3)·0.9 + 1/3 = 10.533…, between 10 and 11 km (type 7 would give 10)."""
    storms = [Storm(flashes=10, area_km2=math.pi * (d / 2) ** 2,
                    duration_min=10.0) for d in range(11, 0, -1)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=110, discarded=0))
    assert result["diameter_median_km"] == pytest.approx(6.0)
    assert result["diameter_p90_km"] == pytest.approx(10.0 + 8.0 / 15.0)


def test_an_even_number_of_thunderstorms_takes_the_mean_of_the_middle_two():
    storms = [Storm(flashes=5, area_km2=100.0, duration_min=10.0),
              Storm(flashes=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["density_median_per_100km2"] == pytest.approx(7.5)
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_thunderstorm_without_area_counts_but_has_no_density_or_diameter():
    storms = [Storm(flashes=5, area_km2=None, duration_min=10.0),
              Storm(flashes=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["thunderstorms"] == 2
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_median_km"] == pytest.approx(2 * math.sqrt(100 / math.pi))
    assert result["diameter_p90_km"] == pytest.approx(2 * math.sqrt(100 / math.pi))
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_run_without_thunderstorms_has_empty_statistics():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=7, discarded=1))
    assert result["thunderstorms"] == 0
    assert result["flashes_isolated"] == 7
    assert result["isolated_pct"] == pytest.approx(100.0)
    assert result["density_median_per_100km2"] is None
    assert result["diameter_median_km"] is None
    assert result["diameter_p90_km"] is None
    assert result["duration_median_min"] is None


def test_a_run_without_flashes_has_no_isolated_share():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=0, discarded=0))
    assert result["isolated_pct"] is None


def test_a_thunderstorm_without_zone_flashes_does_not_count():
    """Rule 2: a storm counts with one zone flash; its flashes are its zone flashes."""
    storms = [Storm(flashes=6, area_km2=100.0, duration_min=10.0),
              Storm(flashes=0, area_km2=None, duration_min=20.0),
              Storm(flashes=1, area_km2=None, duration_min=30.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=20, discarded=0))
    assert result["thunderstorms"] == 2
    assert result["duration_median_min"] == pytest.approx(20.0)
    # The zone flashes in a thunderstorm are not isolated: 20 - (6 + 1).
    assert result["flashes_isolated"] == 13


def test_the_file_name_holds_the_algorithm_provider_and_period():
    start = datetime.datetime(2022, 8, 19, tzinfo=UTC)
    end = datetime.datetime(2022, 8, 20, 2, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    assert sweep.csv_filename("FMI", start, end) == \
        "cellsearch_tuomi_larjavaara_FMI_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("USWFS", start, end) == \
        "cellsearch_tuomi_larjavaara_USWFS_20220819T000000Z_20220820T000000Z.csv"
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
            [Storm(flashes=10, area_km2=100.0, duration_min=30.0)],
            FlashCounts(clustered=40, discarded=3)),
        limited: sweep.thunderstorm_statistics([], FlashCounts(clustered=40, discarded=3)),
    }
    path = tmp_path / "out" / "sweep.csv"
    sweep.write_csv(path, {off: 7, limited: 8}, results)
    rows = list(csv.reader(path.open()))
    assert rows[0] == ["experiment_id", "attraction_radius_km", "max_waiting_time_min", "inertia",
                       "time_distance_limit_min_km", *sweep.STATISTIC_COLUMNS]
    diameter = f"{2 * math.sqrt(100 / math.pi):.4f}"
    assert rows[1] == ["7", "15", "15", "20", "", "1", "3", "40", "30", "75.0000", "10.0000",
                       diameter, diameter, "30.0000"]
    assert rows[2] == ["8", "10", "15", "20", "40", "0", "3", "40", "40", "100.0000", "", "", "",
                       ""]


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
    assert ("Experiment 1 of 2 (R 15 km, T 15 min, I 20, C off): computation time "
            "1.5000 s wall, 0.2500 s CPU") in caplog.text
    assert ("Experiment 2 of 2 (R 15 km, T 15 min, I 20, C 20 min·km): computation time "
            "1.5000 s wall, 0.2500 s CPU") in caplog.text


def test_the_progress_counts_the_experiments_of_every_episode(monkeypatch, caplog):
    """The second episode of two, with two combinations each: experiments 3 and 4 of 4,
    the first already stored."""
    class NoDatabase:
        def connect(self):
            return contextlib.nullcontext()

    stored = iter([(120, "complete"), None])
    monkeypatch.setattr(sweep, "stored_experiment", lambda *args: next(stored))
    monkeypatch.setattr(sweep, "build_thunderstorms", lambda *args, **kwargs: ({}, 1.5, 0.25))
    grid = [CellsearchParameters(srid=3067),
            CellsearchParameters(time_distance_limit_min_km=20, srid=3067)]
    start = datetime.datetime(2018, 7, 3, tzinfo=UTC)
    with caplog.at_level(logging.INFO):
        sweep.run_grid(NoDatabase(), 1, "FMI", grid, start, start + datetime.timedelta(days=1),
                       logging.getLogger("test"), done=2, total=4, episode="episode 2 of 2")
    assert ("Experiment 3 of 4 (episode 2 of 2, R 15 km, T 15 min, I 20, C off): already "
            "stored as experiment 120 (complete), skipped") in caplog.text
    assert "Experiment 4 of 4 (episode 2 of 2, R 15 km, T 15 min, I 20, C 20 min·km)\n" in \
        caplog.text
    assert ("Experiment 4 of 4 (episode 2 of 2, R 15 km, T 15 min, I 20, C 20 min·km): "
            "computation time 1.5000 s wall, 0.2500 s CPU") in caplog.text


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
                                  ["--time", "--iterations", "0"],
                                  ["--sensitivity", "--country", "Finland"]],
                         ids=["iterations-without-time", "no-iterations", "no-country-any-more"])
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


# --- the algorithm and its grid ------------------------------------------------------

def test_the_algorithm_is_cellsearch_unless_told():
    assert sweep.parse_arguments(["--sensitivity", *PERIOD]).algorithm == CELLSEARCH
    assert sweep.parse_arguments(["--time", "--algorithm", TIME_DISTANCE, *PERIOD]).algorithm == \
        TIME_DISTANCE
    with pytest.raises(SystemExit):
        sweep.parse_arguments(["--sensitivity", "--algorithm", "nope", *PERIOD])


def test_the_cellsearch_grid_is_every_combination_of_r_t_i_and_c():
    grid = sweep.parameter_grid(25831)
    assert grid == sweep.parameter_grid(25831, CELLSEARCH)
    assert len(grid) == 6 * 6 * 5 * 6
    assert grid[:2] == [
        CellsearchParameters(attraction_radius_km=5, max_waiting_time_min=5, inertia=10),
        CellsearchParameters(attraction_radius_km=5, max_waiting_time_min=5, inertia=10,
                             time_distance_limit_min_km=10)]


def test_the_time_distance_grid_sweeps_d_and_t_with_n_min_fixed_at_ten():
    grid = sweep.parameter_grid(3067, TIME_DISTANCE)
    assert len(grid) == 36
    assert [(p.max_distance_km, p.max_time_difference_min) for p in grid[:7]] == [
        (5, 5), (5, 10), (5, 15), (5, 20), (5, 30), (5, 60), (10, 5)]
    assert sorted({p.max_distance_km for p in grid}) == [5, 10, 15, 20, 25, 30]
    assert sorted({p.max_time_difference_min for p in grid}) == [5, 10, 15, 20, 30, 60]
    assert {(p.min_flashes, p.srid) for p in grid} == {(10, 3067)}


def test_a_time_distance_combination_is_described_by_d_and_t():
    parameters = TimeDistanceParameters(max_distance_km=5, max_time_difference_min=20,
                                        min_flashes=10)
    assert sweep.describe(parameters) == "D 5 km, T 20 min"


def test_the_time_distance_file_name_starts_with_its_algorithm():
    start = datetime.datetime(2018, 7, 1, tzinfo=UTC)
    end = datetime.datetime(2018, 8, 1, tzinfo=UTC)
    assert sweep.csv_filename("FMI", start, end, algorithm=TIME_DISTANCE) == \
        "time_distance_galanaki_FMI_20180701T000000Z_20180801T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, suffix="times", algorithm=TIME_DISTANCE) == \
        "time_distance_galanaki_times_FMI_20180701T000000Z_20180801T000000Z.csv"


def test_the_time_distance_files_have_d_and_t_as_their_parameter_columns(tmp_path):
    parameters = TimeDistanceParameters(max_distance_km=5, max_time_difference_min=20,
                                        min_flashes=10, srid=3067)
    results = {parameters: sweep.thunderstorm_statistics(
        [Storm(flashes=10, area_km2=100.0, duration_min=30.0)],
        FlashCounts(clustered=40, discarded=0))}
    sweep.write_csv(tmp_path / "sweep.csv", {parameters: 7}, results, algorithm=TIME_DISTANCE)
    rows = list(csv.reader((tmp_path / "sweep.csv").open()))
    assert rows[0] == ["experiment_id", "max_distance_km", "max_time_difference_min",
                       *sweep.STATISTIC_COLUMNS]
    assert rows[1][:5] == ["7", "5", "20", "1", "0"]
    sweep.write_time_csv(tmp_path / "times.csv",
                         {parameters: {**sweep.time_statistics([(0.5, 0.25)]), "host": "h"}},
                         algorithm=TIME_DISTANCE)
    rows = list(csv.reader((tmp_path / "times.csv").open()))
    assert rows[0][:3] == ["max_distance_km", "max_time_difference_min", "iterations"]
    assert rows[1][:3] == ["5", "20", "1"]
    sweep.write_time_runs_csv(tmp_path / "runs.csv", {parameters: [(0.5, 0.25)]}, "h",
                              algorithm=TIME_DISTANCE)
    rows = list(csv.reader((tmp_path / "runs.csv").open()))
    assert rows == [["max_distance_km", "max_time_difference_min", "iteration", "wall_s", "cpu_s",
                     "host"], ["5", "20", "1", "0.500000", "0.250000", "h"]]


def test_the_time_analysis_times_the_time_distance_core(monkeypatch):
    calls = []

    def fake_time_distance(flashes, parameters):
        calls.append(parameters)
        return SimpleNamespace(wall_time_s=1.0, cpu_time_s=0.5)

    monkeypatch.setattr(sweep, "time_distance", fake_time_distance)
    a, b = sweep.parameter_grid(3067, TIME_DISTANCE)[:2]
    samples = sweep.time_runs(None, [a, b], 1, logging.getLogger("test"))
    assert calls == [a, b, a, b]
    assert samples == {a: [(1.0, 0.5)], b: [(1.0, 0.5)]}


# --- several periods ----------------------------------------------------------------

EPISODES_HEADER = "episode,start,end,duration_s,flashes,strokes\n"


def write_episodes(path: Path, rows: list[str]) -> Path:
    """An extract of an episodes study's file: its header and some of its rows."""
    path.write_text(EPISODES_HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def test_periods_replace_from_and_to_and_go_with_the_sensitivity_analysis():
    args = sweep.parse_arguments(["--sensitivity", "--provider", "FMI", "--periods", "e.csv"])
    assert args.periods == Path("e.csv")
    assert (args.start, args.end) == (None, None)
    for argv in (["--sensitivity", "--periods", "e.csv", *PERIOD],
                 ["--sensitivity", "--periods", "e.csv", "--provider", "FMI", "--from", "2018-07-03"],
                 ["--time", "--periods", "e.csv", "--provider", "FMI"],
                 ["--sensitivity", "--provider", "FMI"],
                 ["--sensitivity", "--provider", "FMI", "--from", "2018-07-03"]):
        with pytest.raises(SystemExit):
            sweep.parse_arguments(argv)


def test_each_episode_of_the_periods_file_is_run_an_hour_wider_on_each_side(tmp_path):
    path = write_episodes(tmp_path / "extract.csv", [
        "3,2018-05-16T09:12:19.000+00:00,2018-05-18T12:54:54.000+00:00,186155.000,4890,7380",
        "7,2018-06-02T23:30:00.000+00:00,2018-06-03T01:00:00.000+00:00,5400.000,150,200"])
    periods = sweep.read_periods(path)
    assert sweep.PERIOD_MARGIN == datetime.timedelta(minutes=60)
    assert [(period.episode, period.start, period.end) for period in periods] == [
        ("3", datetime.datetime(2018, 5, 16, 9, 12, 19, tzinfo=UTC),
         datetime.datetime(2018, 5, 18, 12, 54, 54, tzinfo=UTC)),
        ("7", datetime.datetime(2018, 6, 2, 23, 30, tzinfo=UTC),
         datetime.datetime(2018, 6, 3, 1, 0, tzinfo=UTC))]
    assert (periods[1].run_start, periods[1].run_end) == (
        datetime.datetime(2018, 6, 2, 22, 30, tzinfo=UTC),
        datetime.datetime(2018, 6, 3, 2, 0, tzinfo=UTC))


@pytest.mark.parametrize("content", [
    "from,to\n2018-05-16T09:12:19Z,2018-05-18T12:54:54Z\n",
    EPISODES_HEADER,
    EPISODES_HEADER + "3,yesterday,2018-05-18T12:54:54Z,1,1,1\n",
    EPISODES_HEADER + "3,2018-05-18T12:54:54Z,2018-05-16T09:12:19Z,1,1,1\n",
], ids=["other-columns", "no-episodes", "bad-instant", "end-before-start"])
def test_a_periods_file_that_is_not_an_episodes_extract_is_refused(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        sweep.read_periods(path)


def test_the_periods_file_name_holds_the_algorithm_provider_and_episodes_file():
    path = Path("/data/fmi_2018_extract.csv")
    assert sweep.periods_csv_filename("FMI", path, algorithm=TIME_DISTANCE) == \
        "time_distance_galanaki_FMI_fmi_2018_extract.csv"


def test_the_periods_file_has_a_row_per_episode_and_combination(tmp_path):
    episodes = sweep.read_periods(write_episodes(tmp_path / "extract.csv", [
        "3,2018-05-16T09:12:19.000+00:00,2018-05-18T12:54:54.000+00:00,186155.000,4890,7380",
        "7,2018-06-02T23:30:00.000+00:00,2018-06-03T01:00:00.000+00:00,5400.000,150,200"]))
    a, b = sweep.parameter_grid(3067, TIME_DISTANCE)[:2]
    storm = [Storm(flashes=10, area_km2=100.0, duration_min=30.0)]
    statistics = sweep.thunderstorm_statistics(storm, FlashCounts(clustered=40, discarded=0))
    path = tmp_path / "out.csv"
    sweep.write_periods_csv(path, [(episodes[0], {a: 7, b: 8}, {a: statistics, b: statistics}),
                                   (episodes[1], {a: 9}, {a: statistics})],
                            algorithm=TIME_DISTANCE)
    rows = list(csv.reader(path.open()))
    assert rows[0] == ["episode", "start", "end", "experiment_id", "max_distance_km",
                       "max_time_difference_min", *sweep.STATISTIC_COLUMNS]
    assert [row[:6] for row in rows[1:]] == [
        ["3", "2018-05-16T09:12:19+00:00", "2018-05-18T12:54:54+00:00", "7", "5", "5"],
        ["3", "2018-05-16T09:12:19+00:00", "2018-05-18T12:54:54+00:00", "8", "5", "10"],
        ["7", "2018-06-02T23:30:00+00:00", "2018-06-03T01:00:00+00:00", "9", "5", "5"]]


# --- the defaults ---------------------------------------------------------------------

def test_defaults_replace_the_grid_with_the_algorithms_recommended_values():
    assert sweep.parse_arguments(["--sensitivity", *PERIOD]).defaults is False
    assert sweep.parse_arguments(["--sensitivity", "--defaults", *PERIOD]).defaults is True
    assert sweep.parameter_grid(3067, TIME_DISTANCE, defaults=True) == [TimeDistanceParameters(
        max_distance_km=10, max_time_difference_min=16, min_flashes=10, srid=3067)]
    assert sweep.parameter_grid(3067, CELLSEARCH, defaults=True) == [CellsearchParameters(
        attraction_radius_km=15, max_waiting_time_min=15, inertia=20,
        time_distance_limit_min_km=None, min_flashes=10, srid=3067)]


def test_the_defaults_go_to_files_of_their_own():
    start = datetime.datetime(2018, 7, 1, tzinfo=UTC)
    end = datetime.datetime(2018, 8, 1, tzinfo=UTC)
    assert sweep.csv_filename("FMI", start, end, algorithm=TIME_DISTANCE, defaults=True) == \
        "time_distance_galanaki_defaults_FMI_20180701T000000Z_20180801T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, suffix="times", algorithm=TIME_DISTANCE,
                              defaults=True) == \
        "time_distance_galanaki_defaults_times_FMI_20180701T000000Z_20180801T000000Z.csv"
    assert sweep.periods_csv_filename("FMI", Path("/data/fmi_2018_extract.csv"),
                                      algorithm=TIME_DISTANCE, defaults=True) == \
        "time_distance_galanaki_defaults_FMI_fmi_2018_extract.csv"


# --- the time analysis against a database ------------------------------------------

DAY = datetime.datetime(2020, 7, 13, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)

#: IGN's Catalonia, here a square of 40 km around the strokes: the zone reaches 70 km
#: from their centre, x = 470 000 m east.
INSERT_REGION_SQL = """
WITH provider AS (
    INSERT INTO data_provider (name, product, full_name)
    VALUES ('IGN', 'Base de Datos de Divisiones Administrativas de España test', 'IGN')
    RETURNING id
), boundary AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry)
    SELECT 'ign_admin_boundary', provider.id, '34090000000', 1, 'Cataluña/Catalunya',
           ST_Multi(ST_Transform(ST_MakeEnvelope(380000, 4580000, 420000, 4620000, 25831), 4326))
    FROM provider
    RETURNING id
)
INSERT INTO ign_admin_boundary (id, edition, kind)
SELECT boundary.id, 'test', 'comunidad_autonoma' FROM boundary
"""

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
    """The GisFIRE schema on an ephemeral PostgreSQL with one storm of MeteoCat strokes,
    6 flashes of 2 strokes, 4 min apart, in the region (IGN's Catalonia, a square); the
    engine and the database arguments."""
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
        connection.execute(text(INSERT_REGION_SQL))
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


@pytest.mark.parametrize("algorithm", [CELLSEARCH, TIME_DISTANCE])
def test_the_time_analysis_reads_the_strokes_and_writes_nothing(database, tmp_path, caplog,
                                                                algorithm):
    engine, arguments = database
    before = row_counts(engine)
    argv = ["--time", "--iterations", "2", "--algorithm", algorithm, "--provider", "MeteoCat",
            "--from", DAY.isoformat(), "--to", NEXT_DAY.isoformat(), "--output-dir", str(tmp_path),
            *arguments]
    with caplog.at_level(logging.INFO):
        assert sweep.main(argv) == 0
    assert row_counts(engine) == before
    assert before["lightning"] == 12 and before["thunderstorm_experiment"] == 0
    assert "6 flash(es) read" in caplog.text
    combinations = len(sweep.parameter_grid(25831, algorithm))

    def records(suffix: str) -> list[dict[str, str]]:
        path = tmp_path / sweep.csv_filename("MeteoCat", DAY, NEXT_DAY, suffix=suffix,
                                             algorithm=algorithm)
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


# --- the statistics of a stored run -------------------------------------------------

@pytest.mark.parametrize("parameters", [CellsearchParameters(min_flashes=3),
                                        TimeDistanceParameters(min_flashes=3)],
                         ids=[CELLSEARCH, TIME_DISTANCE])
def test_the_statistics_come_from_the_flashes_representative_strokes(database, parameters):
    """A flash's two strokes are 1 s apart, and its first one represents it (equal
    errors, the earliest wins): the storm lasts 20 min, not 20 min 1 s."""
    engine, _ = database
    logger = logging.getLogger("test")
    algorithm = next(key for key, entry in ALGORITHMS.items()
                     if isinstance(parameters, entry.parameters))
    build_thunderstorms(engine, "MeteoCat", algorithm, parameters, DAY, NEXT_DAY, logger)
    with engine.connect() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
        experiment_id = connection.execute(text("SELECT id FROM thunderstorm_experiment")).scalar_one()
    result = sweep.experiment_statistics(engine, provider_id, "MeteoCat", {parameters: experiment_id},
                                         DAY, NEXT_DAY, logger)[parameters]
    assert (result["thunderstorms"], result["flashes_clustered"], result["flashes_isolated"],
            result["flashes_discarded_error"]) == (1, 6, 0, 0)
    assert result["duration_median_min"] == pytest.approx(20.0)


# --- several periods against a database ----------------------------------------------

#: The day of :func:`store_two_episodes`, two days after the fixture's storm.
EPISODES_DAY = DAY + datetime.timedelta(days=2)


def store_two_episodes(engine, directory: Path) -> Path:
    """Two storms of 12 flashes, 4 min apart, on :data:`EPISODES_DAY`, and the extract of
    an episodes file with an episode for each. A comes from the east, out of the zone,
    from 13:30, and its last three flashes (14:06 to 14:14) are its episode's zone
    flashes, so most of it lies in the margin. B, 20:00 to 20:44, is in the region, its
    episode's own span."""
    day = EPISODES_DAY
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
        for first_flash, start, x0, dx in ((101, day + datetime.timedelta(hours=13, minutes=30),
                                            478_500.0, -1_000.0),
                                           (201, day + datetime.timedelta(hours=20),
                                            400_000.0, 300.0)):
            for k in range(12):
                connection.execute(text(INSERT_STROKE_SQL), {
                    "provider_id": provider_id, "flash": first_flash + k,
                    "at": start + datetime.timedelta(minutes=4 * k),
                    "x": x0 + dx * k, "y": 4_600_000.0 + 200.0 * (k % 3)})
    return write_episodes(directory / "extract.csv", [
        f"1,{(day + datetime.timedelta(hours=14, minutes=6)).isoformat()},"
        f"{(day + datetime.timedelta(hours=14, minutes=14)).isoformat()},480,3,3",
        f"2,{(day + datetime.timedelta(hours=20)).isoformat()},"
        f"{(day + datetime.timedelta(hours=20, minutes=44)).isoformat()},2640,12,12"])


def test_each_episode_is_run_with_its_margins_and_written_to_one_file(database, tmp_path,
                                                                     monkeypatch):
    """The two episodes of :func:`store_two_episodes`, with a one-combination grid."""
    engine, arguments = database
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", [10]),
                                                     "max_time_difference_min": ("T", "min", [16])})
    path = store_two_episodes(engine, tmp_path)
    day = EPISODES_DAY
    argv = ["--sensitivity", "--algorithm", TIME_DISTANCE, "--provider", "MeteoCat",
            "--periods", str(path), "--output-dir", str(tmp_path), *arguments]
    assert sweep.main(argv) == 0
    with engine.connect() as connection:
        runs = connection.execute(text(
            "SELECT date_time_start, date_time_end FROM thunderstorm_experiment ORDER BY id")).all()
    assert [tuple(run) for run in runs] == [
        (day + datetime.timedelta(hours=13, minutes=6), day + datetime.timedelta(hours=15, minutes=14)),
        (day + datetime.timedelta(hours=19), day + datetime.timedelta(hours=21, minutes=44))]
    output = tmp_path / sweep.periods_csv_filename("MeteoCat", path, algorithm=TIME_DISTANCE)
    records = list(csv.DictReader(output.open()))
    episodes = list(csv.DictReader(path.open()))
    assert [record["episode"] for record in records] == ["1", "2"]
    for record, episode in zip(records, episodes):
        assert (record["max_distance_km"], record["max_time_difference_min"]) == ("10", "16")
        assert (record["thunderstorms"], record["flashes_isolated"]) == ("1", "0")
        # The episode's zone flashes, as the episodes study counted them.
        assert int(record["flashes_clustered"]) + int(record["flashes_discarded_error"]) == \
            int(episode["flashes"])
        # The time of the whole storm, margin included.
        assert float(record["duration_median_min"]) == pytest.approx(44.0)


def test_the_progress_of_a_periods_run_goes_from_the_first_experiment_to_the_last(
        database, tmp_path, monkeypatch, caplog):
    """Two combinations over the two episodes of :func:`store_two_episodes`: 4 experiments."""
    engine, arguments = database
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", [10]),
                                                     "max_time_difference_min": ("T", "min",
                                                                                 [10, 16])})
    path = store_two_episodes(engine, tmp_path)
    argv = ["--sensitivity", "--algorithm", TIME_DISTANCE, "--provider", "MeteoCat",
            "--periods", str(path), "--output-dir", str(tmp_path), *arguments]
    with caplog.at_level(logging.INFO):
        assert sweep.main(argv) == 0
    started = [record.getMessage() for record in caplog.records
               if record.getMessage().startswith("Experiment ") and ":" not in record.getMessage()]
    assert started == ["Experiment 1 of 4 (episode 1 of 2, D 10 km, T 10 min)",
                       "Experiment 2 of 4 (episode 1 of 2, D 10 km, T 16 min)",
                       "Experiment 3 of 4 (episode 2 of 2, D 10 km, T 10 min)",
                       "Experiment 4 of 4 (episode 2 of 2, D 10 km, T 16 min)"]


def test_the_defaults_run_once_per_episode_into_their_own_file(database, tmp_path):
    engine, arguments = database
    path = store_two_episodes(engine, tmp_path)
    argv = ["--sensitivity", "--defaults", "--algorithm", TIME_DISTANCE, "--provider", "MeteoCat",
            "--periods", str(path), "--output-dir", str(tmp_path), *arguments]
    assert sweep.main(argv) == 0
    with engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT parameters FROM thunderstorm_experiment ORDER BY id")).scalars().all()
    assert stored == [TimeDistanceParameters(min_flashes=10).to_dict()] * 2
    output = tmp_path / sweep.periods_csv_filename("MeteoCat", path, algorithm=TIME_DISTANCE,
                                                   defaults=True)
    assert [(record["episode"], record["max_distance_km"], record["max_time_difference_min"],
             record["thunderstorms"]) for record in csv.DictReader(output.open())] == [
        ("1", "10", "16", "1"), ("2", "10", "16", "1")]
    assert not (tmp_path / sweep.periods_csv_filename("MeteoCat", path,
                                                      algorithm=TIME_DISTANCE)).exists()


# --- rule 2: the statistics of a storm half in the zone ------------------------------

def store_half_zone_storm(engine) -> datetime.datetime:
    """Three days after the fixture's storm, 6 flashes, 4 min apart, moving east: the
    first three in the zone (x 467-469 km), the last three out of it (471-473 km).
    Returns their day."""
    day = DAY + datetime.timedelta(days=3)
    xs = [467_000.0, 468_000.0, 469_000.0, 471_000.0, 472_000.0, 473_000.0]
    ys = [4_600_000.0, 4_602_000.0] * 3
    with engine.begin() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
        for k, (x, y) in enumerate(zip(xs, ys)):
            connection.execute(text(INSERT_STROKE_SQL), {
                "provider_id": provider_id, "flash": 301 + k,
                "at": day + datetime.timedelta(hours=14, minutes=4 * k), "x": x, "y": y})
    return day


@pytest.mark.parametrize("parameters", [CellsearchParameters(min_flashes=3),
                                        TimeDistanceParameters(min_flashes=3)],
                         ids=[CELLSEARCH, TIME_DISTANCE])
def test_a_storms_statistics_come_from_its_zone_flashes_and_its_time_from_all(database,
                                                                              parameters):
    """The storm of :func:`store_half_zone_storm`."""
    engine, _ = database
    logger = logging.getLogger("test")
    day = store_half_zone_storm(engine)
    with engine.connect() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
    algorithm = next(key for key, entry in ALGORITHMS.items()
                     if isinstance(parameters, entry.parameters))
    build_thunderstorms(engine, "MeteoCat", algorithm, parameters, day,
                        day + datetime.timedelta(days=1), logger)
    with engine.connect() as connection:
        experiment_id = connection.execute(text("SELECT id FROM thunderstorm_experiment")).scalar_one()
    result = sweep.experiment_statistics(engine, provider_id, "MeteoCat", {parameters: experiment_id},
                                         day, day + datetime.timedelta(days=1), logger)[parameters]
    assert (result["thunderstorms"], result["flashes_clustered"], result["flashes_isolated"],
            result["flashes_discarded_error"]) == (1, 3, 0, 0)
    assert result["duration_median_min"] == pytest.approx(20.0)
    # The area of the three zone flashes, their concave hull's for both algorithms: a
    # triangle of 2 km².
    area = 2.0
    assert result["density_median_per_100km2"] == pytest.approx(100.0 * 3 / area, rel=1e-6)
    assert result["diameter_median_km"] == pytest.approx(2.0 * math.sqrt(area / math.pi), rel=1e-6)


# --- the time shuffle: the generator and the permutation ------------------------------

def test_the_generator_is_park_and_millers_minimal_standard():
    """Park & Miller (1988)'s check: from 1, the 10,000th value is 1,043,618,065."""
    seed = 1
    for _ in range(10_000):
        seed = sweep.next_seed(seed)
    assert seed == 1_043_618_065


def test_the_permutation_of_four_flashes():
    """A, B, C, D and the seed 24061117: A takes D's time, B C's, C A's and D B's, and
    the chain stops at 135629465."""
    order, seed = sweep.permutation(4, 24_061_117)
    assert order.tolist() == [3, 2, 0, 1]
    assert seed == 135_629_465


def test_a_permutation_draws_one_number_per_flash_but_the_first():
    _, seed = sweep.permutation(5, 1)
    expected = 1
    for _ in range(4):
        expected = sweep.next_seed(expected)
    assert seed == expected


def test_a_permutation_holds_every_flash_once_and_repeats_with_its_seed():
    order, seed = sweep.permutation(1_000, 24_061_117)
    assert sorted(order.tolist()) == list(range(1_000))
    again, seed_again = sweep.permutation(1_000, 24_061_117)
    assert again.tolist() == order.tolist() and seed_again == seed
    # The next shuffle starts where this one stopped, and is another one.
    following, _ = sweep.permutation(1_000, seed)
    assert following.tolist() != order.tolist()


@pytest.mark.parametrize("n", [0, 1])
def test_nothing_to_shuffle_draws_nothing(n):
    order, seed = sweep.permutation(n, 24_061_117)
    assert order.tolist() == list(range(n))
    assert seed == 24_061_117


# --- the time shuffle: a run's strokes ----------------------------------------------------

def four_flashes() -> Strokes:
    """Six strokes in four flashes, in the builder's flash order 10, 20, 30, 40 (at 0,
    60, 120.2 and 600 s). Flash 10 is represented by its first stroke (the more
    accurate), its second 0.5 s later; flash 30 by its second, its first 0.2 s before."""
    return Strokes(ids=np.array([1, 2, 3, 4, 5, 6]), flash_keys=np.array([10, 10, 20, 30, 30, 40]),
                   t=np.array([0.0, 0.5, 60.0, 120.0, 120.2, 600.0]),
                   x=np.array([0.0, 10.0, 1_000.0, 2_000.0, 2_010.0, 5_000.0]),
                   y=np.array([0.0, 5.0, 1_000.0, 3_000.0, 3_005.0, 7_000.0]),
                   error=np.array([100.0, 200.0, 100.0, 300.0, 150.0, 100.0]))


def by_id(strokes: Strokes, name: str) -> dict[int, float]:
    return dict(zip(strokes.ids.tolist(), getattr(strokes, name).tolist()))


def test_a_shuffle_gives_each_flash_another_flash_s_time_and_moves_its_strokes_with_it():
    """The seed 24061117 orders four places [3, 2, 0, 1]: flash 10 takes flash 40's time,
    20 takes 30's, 30 takes 10's and 40 takes 20's."""
    shuffled, seed = sweep.shuffle_times(four_flashes(), 24_061_117)
    assert by_id(shuffled, "t") == pytest.approx({1: 600.0, 2: 600.5, 3: 120.2, 4: -0.2,
                                                  5: 0.0, 6: 60.0})
    assert seed == sweep.permutation(4, 24_061_117)[1]


def test_a_shuffle_keeps_every_stroke_s_place_error_and_flash():
    strokes = four_flashes()
    shuffled, _ = sweep.shuffle_times(strokes, 24_061_117)
    for name in ("flash_keys", "x", "y", "error"):
        assert by_id(shuffled, name) == by_id(strokes, name)


def test_the_shuffled_strokes_are_in_time_order_then_by_id():
    shuffled, _ = sweep.shuffle_times(four_flashes(), 24_061_117)
    assert np.lexsort((shuffled.ids, shuffled.t)).tolist() == list(range(len(shuffled)))


def test_a_shuffle_keeps_the_flashes_and_permutes_their_times_exactly():
    strokes = four_flashes()
    shuffled, _ = sweep.shuffle_times(strokes, 24_061_117)
    before, after = strokes_to_flashes(strokes), strokes_to_flashes(shuffled)
    assert sorted(after.representative_id.tolist()) == sorted(before.representative_id.tolist())
    assert sorted(after.t.tolist()) == sorted(before.t.tolist())


def test_the_same_seed_repeats_a_shuffle_and_the_next_one_differs():
    rng = np.random.default_rng(0)
    n = 300
    strokes = Strokes(ids=np.arange(1, n + 1), flash_keys=np.arange(n) // 2,
                      t=np.sort(rng.uniform(0.0, 3_600.0, n)), x=rng.uniform(0.0, 1e5, n),
                      y=rng.uniform(0.0, 1e5, n), error=rng.uniform(0.0, 500.0, n))
    first, seed = sweep.shuffle_times(strokes, 24_061_117)
    again, seed_again = sweep.shuffle_times(strokes, 24_061_117)
    assert first.ids.tolist() == again.ids.tolist() and first.t.tolist() == again.t.tolist()
    assert seed_again == seed
    following, _ = sweep.shuffle_times(strokes, seed)
    assert by_id(following, "t") != by_id(first, "t")


# --- a run's statistics in memory -------------------------------------------------------

@pytest.mark.parametrize("algorithm_parameters", [CellsearchParameters, TimeDistanceParameters],
                         ids=[CELLSEARCH, TIME_DISTANCE])
@pytest.mark.parametrize(("storms", "min_flashes", "thunderstorms", "isolated_pct"), [
    ("fixture", 3, 1, 0.0),
    ("fixture", 7, 0, 100.0),
    ("half_zone", 3, 1, 0.0),
    ("two_episodes", 3, 2, 0.0),
    ("mixed", 7, 2, 100.0 * 6 / 21),
])
def test_a_run_s_statistics_in_memory_equal_those_of_its_stored_run(
        database, tmp_path, algorithm_parameters, storms, min_flashes, thunderstorms,
        isolated_pct):
    """With the real times: the fixture's storm (6 flashes of two strokes 1 s apart, on a
    line in EPSG:25831, a sliver once read back from the database), alone or too small
    for N_min 7 (every flash isolated); :func:`store_half_zone_storm`'s;
    :func:`store_two_episodes`'s two storms of 12 flashes; and all three together over
    three days with N_min 7, so 6 of the 21 zone flashes are isolated."""
    engine, _ = database
    logger = logging.getLogger("test")
    parameters = algorithm_parameters(min_flashes=min_flashes)
    day = DAY
    end = day + datetime.timedelta(days=1)
    if storms == "half_zone":
        day = store_half_zone_storm(engine)
        end = day + datetime.timedelta(days=1)
    elif storms in ("two_episodes", "mixed"):
        store_two_episodes(engine, tmp_path)
        day = EPISODES_DAY if storms == "two_episodes" else DAY
        end = EPISODES_DAY + datetime.timedelta(days=1)
    algorithm = next(key for key, entry in ALGORITHMS.items()
                     if isinstance(parameters, entry.parameters))
    build_thunderstorms(engine, "MeteoCat", algorithm, parameters, day, end, logger)
    with engine.connect() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
        experiment_id = connection.execute(text("SELECT id FROM thunderstorm_experiment")).scalar_one()
        region = read_region(connection, "MeteoCat")
    stored = sweep.experiment_statistics(engine, provider_id, "MeteoCat", {parameters: experiment_id},
                                         day, end, logger)[parameters]
    strokes = sweep.read_strokes(engine, provider_id, "MeteoCat", day, end)
    zone_ids = strokes.ids[in_zone(region, strokes.x, strokes.y)]
    in_memory = sweep.thunderstorm_statistics(*sweep.memory_storms(strokes, zone_ids, parameters))
    assert (stored["thunderstorms"], stored["isolated_pct"]) == (thunderstorms,
                                                                pytest.approx(isolated_pct))
    assert in_memory.keys() == stored.keys()
    for name, value in stored.items():
        assert in_memory[name] == (None if value is None else pytest.approx(value, rel=1e-9)), name


# --- the shuffled runs' options and file ----------------------------------------------

def test_the_gap_option_shuffles_thirty_times_from_24061117_unless_told():
    args = sweep.parse_arguments(["--sensitivity", "--gap", *PERIOD])
    assert args.gap and (args.shuffles, args.seed) == (sweep.SHUFFLES, sweep.SEED) == \
        (30, 24_061_117)
    args = sweep.parse_arguments(["--sensitivity", "--gap", "--shuffles", "2", "--seed", "1",
                                  *PERIOD])
    assert (args.shuffles, args.seed) == (2, 1)
    args = sweep.parse_arguments(["--sensitivity", *PERIOD])
    assert not args.gap and (args.shuffles, args.seed) == (None, None)


def test_the_largest_seed_is_two_to_the_31_minus_2():
    args = sweep.parse_arguments(["--sensitivity", "--gap", "--seed", str(2**31 - 2), *PERIOD])
    assert args.seed == 2**31 - 2


@pytest.mark.parametrize("argv", [["--time", "--gap"],
                                  ["--sensitivity", "--shuffles", "5"],
                                  ["--sensitivity", "--seed", "5"],
                                  ["--sensitivity", "--gap", "--shuffles", "0"],
                                  ["--sensitivity", "--gap", "--seed", "0"],
                                  ["--sensitivity", "--gap", "--seed", str(2**31 - 1)]],
                         ids=["gap-with-time", "shuffles-without-gap", "seed-without-gap",
                              "no-shuffles", "seed-0", "seed-modulus"])
def test_a_wrong_gap_option_is_refused(argv):
    with pytest.raises(SystemExit):
        sweep.parse_arguments([*argv, *PERIOD])


def test_the_gap_file_is_named_as_the_sensitivity_one_with_gap_after_the_provider():
    episodes = Path("fmi_q1.csv")
    assert sweep.periods_csv_filename("MeteoCat", episodes, algorithm=TIME_DISTANCE, gap=True) == \
        "time_distance_galanaki_MeteoCat_gap_fmi_q1.csv"
    assert sweep.periods_csv_filename("MeteoCat", episodes, algorithm=TIME_DISTANCE,
                                      defaults=True, gap=True) == \
        "time_distance_galanaki_defaults_MeteoCat_gap_fmi_q1.csv"
    start = datetime.datetime(2018, 7, 3, tzinfo=UTC)
    assert sweep.csv_filename("FMI", start, start + datetime.timedelta(days=1),
                              algorithm=TIME_DISTANCE, gap=True) == \
        "time_distance_galanaki_FMI_gap_20180703T000000Z_20180704T000000Z.csv"


# --- the shuffled runs against a database ----------------------------------------------

def two_combinations(monkeypatch) -> None:
    """Time-distance's grid cut to D 10 and 20 km, T 16 min."""
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", [10, 20]),
                                                     "max_time_difference_min": ("T", "min", [16])})


def test_the_gap_option_adds_its_file_and_changes_nothing_else(database, tmp_path, monkeypatch):
    """The two episodes of :func:`store_two_episodes`, two combinations, two shuffles: run
    without --gap, then with it (the experiments are stored by then), then with it again."""
    engine, arguments = database
    two_combinations(monkeypatch)
    episodes_path = store_two_episodes(engine, tmp_path)
    argv = ["--sensitivity", "--algorithm", TIME_DISTANCE, "--provider", "MeteoCat",
            "--periods", str(episodes_path), *arguments]
    assert sweep.main([*argv, "--output-dir", str(tmp_path / "plain")]) == 0
    before = row_counts(engine)
    assert sweep.main([*argv, "--gap", "--shuffles", "2", "--output-dir",
                       str(tmp_path / "gap")]) == 0
    assert row_counts(engine) == before
    name = sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE)
    assert (tmp_path / "gap" / name).read_bytes() == (tmp_path / "plain" / name).read_bytes()
    assert not (tmp_path / "plain" / sweep.periods_csv_filename(
        "MeteoCat", episodes_path, algorithm=TIME_DISTANCE, gap=True)).exists()
    gap_path = tmp_path / "gap" / sweep.periods_csv_filename("MeteoCat", episodes_path,
                                                             algorithm=TIME_DISTANCE, gap=True)
    with gap_path.open() as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == ["episode", "start", "end", "run", "seed", "flashes",
                                     "experiment_id", "max_distance_km",
                                     "max_time_difference_min", *sweep.STATISTIC_COLUMNS]
        records = list(reader)
    sensitivity = list(csv.DictReader((tmp_path / "plain" / name).open()))
    episodes = list(csv.DictReader(episodes_path.open()))
    with engine.connect() as connection:
        provider_id = connection.execute(text(
            "SELECT id FROM data_provider WHERE name = 'MeteoCat'")).scalar_one()
    # Per episode: its 2 real rows, then shuffle 1 and shuffle 2 of both combinations.
    assert [(record["episode"], record["run"], record["max_distance_km"]) for record in records] == [
        (episode, run, d) for episode in ("1", "2")
        for run in ("real", "shuffled", "shuffled") for d in ("10", "20")]
    for number, episode in enumerate(episodes):
        rows = records[6 * number:6 * (number + 1)]
        assert {record["flashes"] for record in rows} == {episode["flashes"]}
        # The real rows are the sensitivity file's.
        for record, row in zip(rows[:2], sensitivity[2 * number:2 * (number + 1)]):
            assert record["seed"] == ""
            assert {key: record[key] for key in row} == row
        # Every episode starts again from the seed; each shuffle, made once, serves both
        # combinations; the second starts where the first stopped.
        strokes = sweep.read_strokes(engine, provider_id, "MeteoCat",
                                     datetime.datetime.fromisoformat(episode["start"])
                                     - sweep.PERIOD_MARGIN,
                                     datetime.datetime.fromisoformat(episode["end"])
                                     + sweep.PERIOD_MARGIN)
        second = sweep.permutation(len(strokes_to_flashes(strokes)), sweep.SEED)[1]
        assert [(record["seed"], record["experiment_id"]) for record in rows[2:]] == [
            (str(sweep.SEED), ""), (str(sweep.SEED), ""), (str(second), ""), (str(second), "")]
    assert sweep.main([*argv, "--gap", "--shuffles", "2", "--output-dir",
                       str(tmp_path / "again")]) == 0
    assert (tmp_path / "again" / gap_path.name).read_bytes() == gap_path.read_bytes()


def test_the_gap_file_of_a_period_has_no_episode_columns(database, tmp_path, monkeypatch, caplog):
    engine, arguments = database
    two_combinations(monkeypatch)
    argv = ["--sensitivity", "--gap", "--shuffles", "3", "--seed", "7", "--algorithm",
            TIME_DISTANCE, "--provider", "MeteoCat", "--from", DAY.isoformat(), "--to",
            NEXT_DAY.isoformat(), "--output-dir", str(tmp_path), *arguments]
    with caplog.at_level(logging.INFO):
        assert sweep.main(argv) == 0
    gap_path = tmp_path / sweep.csv_filename("MeteoCat", DAY, NEXT_DAY, algorithm=TIME_DISTANCE,
                                             gap=True)
    with gap_path.open() as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames[:4] == ["run", "seed", "flashes", "experiment_id"]
        records = list(reader)
    assert [record["run"] for record in records] == ["real"] * 2 + ["shuffled"] * 6
    assert {record["flashes"] for record in records} == {"6"}
    assert records[2]["seed"] == records[3]["seed"] == "7"
    assert [record.getMessage() for record in caplog.records
            if record.getMessage().startswith("Shuffle ")] == [
        "Shuffle 1 of 3", "Shuffle 2 of 3", "Shuffle 3 of 3"]


def test_shuffling_the_times_breaks_the_storms_up(database, tmp_path, monkeypatch):
    """Three days, three storms (the fixture's and :func:`store_two_episodes`'): their
    30 flashes' times spread over the three days, few stay within T of a neighbour."""
    engine, arguments = database
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", [10]),
                                                     "max_time_difference_min": ("T", "min", [16])})
    store_two_episodes(engine, tmp_path)
    end = EPISODES_DAY + datetime.timedelta(days=1)
    argv = ["--sensitivity", "--gap", "--shuffles", "3", "--algorithm", TIME_DISTANCE,
            "--provider", "MeteoCat", "--from", DAY.isoformat(), "--to", end.isoformat(),
            "--output-dir", str(tmp_path), *arguments]
    assert sweep.main(argv) == 0
    path = tmp_path / sweep.csv_filename("MeteoCat", DAY, end, algorithm=TIME_DISTANCE, gap=True)
    records = list(csv.DictReader(path.open()))
    real, shuffled = records[0], records[1:]
    # N_min 10: storms A and B are kept, the fixture's 6 flashes are isolated.
    assert (real["thunderstorms"], real["flashes_isolated"], real["flashes"]) == ("2", "6", "21")
    assert len(shuffled) == 3
    for record in shuffled:
        assert record["flashes_clustered"] == "21"
        assert float(record["isolated_pct"]) > float(real["isolated_pct"])


# --- extra grid values from the command line ----------------------------------------------

EXTRA_D = ["2", "4", "6", "8", "10", "12", "14", "16", "20"]
EXTRA_T = ["2", "4", "6", "8", "10", "12", "15", "20", "30"]


def test_the_grid_flags_add_their_values_to_the_lists_sorted():
    args = sweep.parse_arguments(["--sensitivity", "--algorithm", TIME_DISTANCE, "--d", *EXTRA_D,
                                  "--t", *EXTRA_T, *PERIOD])
    assert args.extra == {"max_distance_km": [int(d) for d in EXTRA_D],
                          "max_time_difference_min": [int(t) for t in EXTRA_T]}
    assert sweep.grid_lists(TIME_DISTANCE, args.extra) == {
        "max_distance_km": [2, 4, 5, 6, 8, 10, 12, 14, 15, 16, 20, 25, 30],
        "max_time_difference_min": [2, 4, 5, 6, 8, 10, 12, 15, 20, 30, 60]}
    grid = sweep.parameter_grid(3067, TIME_DISTANCE, extra=args.extra)
    assert len(grid) == 13 * 11 == 143
    assert [(p.max_distance_km, p.max_time_difference_min) for p in grid[:3]] == \
        [(2, 2), (2, 4), (2, 5)]
    assert (grid[-1].max_distance_km, grid[-1].max_time_difference_min) == (30, 60)
    # Every pair of the lists alone is in it, the same parameters: stored ones are found again.
    assert all(parameters in grid for parameters in sweep.parameter_grid(3067, TIME_DISTANCE))


def test_cellsearch_s_grid_flags_take_off_decimals_and_repeats():
    args = sweep.parse_arguments(["--sensitivity", "--r", "2.5", "--i", "15", "20",
                                  "--c", "off", "5", *PERIOD])
    lists = sweep.grid_lists(CELLSEARCH, args.extra)
    assert lists["attraction_radius_km"] == [2.5, 5, 10, 15, 20, 25, 30]
    assert lists["inertia"] == [10, 15, 20, 30, 40, 50]
    assert lists["time_distance_limit_min_km"] == [None, 5, 10, 20, 40, 80, 160]
    assert lists["max_waiting_time_min"] == sweep.MAX_WAITING_TIMES_MIN
    assert len(sweep.parameter_grid(25831, CELLSEARCH, extra=args.extra)) == 7 * 6 * 6 * 7


def test_without_grid_flags_the_grid_is_the_lists():
    assert sweep.parse_arguments(["--sensitivity", *PERIOD]).extra == {}
    for algorithm in (CELLSEARCH, TIME_DISTANCE):
        assert sweep.parameter_grid(3067, algorithm, extra={}) == \
            sweep.parameter_grid(3067, algorithm)
        assert sweep.grid_lists(algorithm, {}) == {
            field: values for field, (_, _, values) in sweep.GRIDS[algorithm].items()}


@pytest.mark.parametrize("argv", [["--algorithm", TIME_DISTANCE, "--r", "5"],
                                  ["--c", "5", "--algorithm", TIME_DISTANCE],
                                  ["--algorithm", TIME_DISTANCE, "--defaults", "--d", "2"],
                                  ["--algorithm", TIME_DISTANCE, "--d", "0"],
                                  ["--algorithm", TIME_DISTANCE, "--d", "off"],
                                  ["--algorithm", TIME_DISTANCE, "--d", "two"],
                                  ["--i", "2.5"]],
                         ids=["r-with-time-distance", "c-with-time-distance", "with-defaults",
                              "not-positive", "d-off", "not-a-number", "i-not-whole"])
def test_a_wrong_grid_flag_is_refused(argv):
    with pytest.raises(SystemExit):
        sweep.parse_arguments(["--sensitivity", *argv, *PERIOD])


def test_a_grid_flag_runs_only_the_new_combinations(database, tmp_path, monkeypatch, caplog):
    """The grid cut to D 10 km, T 16 min, run; then with --d 20: D 10 is skipped."""
    engine, arguments = database
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", [10]),
                                                     "max_time_difference_min": ("T", "min", [16])})
    argv = ["--sensitivity", "--algorithm", TIME_DISTANCE, "--provider", "MeteoCat", "--from",
            DAY.isoformat(), "--to", NEXT_DAY.isoformat(), "--output-dir", str(tmp_path),
            *arguments]
    assert sweep.main(argv) == 0
    with caplog.at_level(logging.INFO):
        assert sweep.main([*argv, "--d", "20"]) == 0
    messages = [record.getMessage() for record in caplog.records]
    assert "Grid: D 10, 20 km; T 16 min: 2 combinations" in messages
    assert any(message.startswith("Experiment 1 of 2 (D 10 km, T 16 min): already stored")
               for message in messages)
    assert "Experiment 2 of 2 (D 20 km, T 16 min)" in messages
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM thunderstorm_experiment")).scalar() == 2
    output = tmp_path / sweep.csv_filename("MeteoCat", DAY, NEXT_DAY, algorithm=TIME_DISTANCE)
    assert [record["max_distance_km"] for record in csv.DictReader(output.open())] == ["10", "20"]


# --- an old gap file: reading and checking it ---------------------------------------------

def gap_file(path: Path, rows: list[tuple[str, str, str, int, int]], periods: bool = True,
             algorithm: str = TIME_DISTANCE) -> Path:
    """A made-up gap file: each row ``(episode, run, seed, D, T)``, its other cells filler."""
    columns = sweep.gap_file_columns(algorithm, periods)
    lines = [",".join(columns)]
    for episode, run, seed, d, t in rows:
        cells = [episode, "2020-07-15T14:06:00+00:00", "2020-07-15T14:14:00+00:00"] if periods else []
        cells += [run, seed, "3", "1" if run == "real" else "", str(d), str(t),
                  *["0"] * len(sweep.STATISTIC_COLUMNS)]
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def two_shuffles(episode: str, d: int, first: str = str(sweep.SEED),
                 second: str = "764990744") -> list[tuple[str, str, str, int, int]]:
    """A pair's rows with T 16 min: its real row and two shuffled rows."""
    return [(episode, "real", "", d, 16), (episode, "shuffled", first, d, 16),
            (episode, "shuffled", second, d, 16)]


def test_a_gap_file_written_by_the_sweep_is_read_back(database, tmp_path, monkeypatch):
    """The file of :func:`test_the_gap_option_adds_its_file_and_changes_nothing_else`:
    a header, then 6 rows per episode."""
    engine, arguments = database
    two_combinations(monkeypatch)
    episodes_path = store_two_episodes(engine, tmp_path)
    assert sweep.main(["--sensitivity", "--gap", "--shuffles", "2", "--algorithm", TIME_DISTANCE,
                       "--provider", "MeteoCat", "--periods", str(episodes_path), "--output-dir",
                       str(tmp_path), *arguments]) == 0
    path = tmp_path / sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE,
                                                 gap=True)
    assert sweep.gap_file_blocks(path, sweep.gap_file_columns(TIME_DISTANCE, True), 2,
                                 sweep.SEED) == {"1": (2, 7), "2": (8, 13)}


def test_a_period_s_gap_file_is_one_block(tmp_path):
    path = gap_file(tmp_path / "gap.csv", two_shuffles("", 10) + two_shuffles("", 20),
                    periods=False)
    assert sweep.gap_file_blocks(path, sweep.gap_file_columns(TIME_DISTANCE, False), 2,
                                 sweep.SEED) == {None: (2, 7)}


@pytest.mark.parametrize(("rows", "shuffles", "seed", "message"), [
    (two_shuffles("1", 10), 3, sweep.SEED, "has 2 shuffled row"),
    (two_shuffles("1", 10, first="7"), 2, sweep.SEED, "from seed 7"),
    (two_shuffles("1", 10) + two_shuffles("2", 10) + two_shuffles("1", 20), 2, sweep.SEED,
     "rows are not together"),
    ([("1", "other", "", 10, 16)], 2, sweep.SEED, "neither real nor shuffled"),
], ids=["fewer-shuffles", "another-seed", "episode-split", "unknown-run"])
def test_a_gap_file_that_does_not_match_the_run_is_refused(tmp_path, rows, shuffles, seed, message):
    path = gap_file(tmp_path / "gap.csv", rows)
    with pytest.raises(ValueError, match=message):
        sweep.gap_file_blocks(path, sweep.gap_file_columns(TIME_DISTANCE, True), shuffles, seed)


def test_another_algorithm_s_gap_file_is_refused(tmp_path):
    path = gap_file(tmp_path / "gap.csv", two_shuffles("1", 10))
    with pytest.raises(ValueError, match="columns"):
        sweep.gap_file_blocks(path, sweep.gap_file_columns(CELLSEARCH, True), 2, sweep.SEED)


def test_the_two_episodes_of_one_pair_are_each_complete(tmp_path):
    """D 10 in episodes 1 and 2, two shuffles in each: each has its 2, so it is accepted."""
    path = gap_file(tmp_path / "gap.csv", two_shuffles("1", 10) + two_shuffles("2", 10))
    assert sweep.gap_file_blocks(path, sweep.gap_file_columns(TIME_DISTANCE, True), 2,
                                 sweep.SEED) == {"1": (2, 4), "2": (5, 7)}


# --- the gap file merge ---------------------------------------------------------------------

def grid_of(monkeypatch, distances: list[int]) -> None:
    """Time-distance's grid cut to D ``distances`` km, T 16 min."""
    monkeypatch.setitem(sweep.GRIDS, TIME_DISTANCE, {"max_distance_km": ("D", "km", distances),
                                                     "max_time_difference_min": ("T", "min", [16])})


def gap_run(arguments: list[str], output_dir: Path, *extra: str) -> int:
    """A --gap run of two shuffles of time-distance on MeteoCat's strokes."""
    return sweep.main(["--sensitivity", "--gap", "--shuffles", "2", "--algorithm", TIME_DISTANCE,
                       "--provider", "MeteoCat", "--output-dir", str(output_dir), *arguments, *extra])


def computed_distances(monkeypatch) -> list[float]:
    """The D of every run made in memory from now on."""
    calls = []
    run = sweep.memory_storms

    def counting(strokes, zone_ids, parameters):
        calls.append(parameters.max_distance_km)
        return run(strokes, zone_ids, parameters)

    monkeypatch.setattr(sweep, "memory_storms", counting)
    return calls


def episodes_file_records(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


@pytest.mark.parametrize("periods", [True, False], ids=["periods", "from-to"])
def test_adding_a_pair_runs_only_it_and_writes_a_fresh_run_s_file(database, tmp_path, monkeypatch,
                                                                  periods):
    """D 10, then D 10 and 20: only D 20 is run in memory, the old file is kept as .old, and
    the new one is the file of a run of both from scratch."""
    engine, arguments = database
    grid_of(monkeypatch, [10])
    if periods:
        episodes_path = store_two_episodes(engine, tmp_path)
        arguments = [*arguments, "--periods", str(episodes_path)]
        name = sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE,
                                          gap=True)
    else:
        arguments = [*arguments, "--from", DAY.isoformat(), "--to", NEXT_DAY.isoformat()]
        name = sweep.csv_filename("MeteoCat", DAY, NEXT_DAY, algorithm=TIME_DISTANCE, gap=True)
    assert gap_run(arguments, tmp_path / "out") == 0
    first = (tmp_path / "out" / name).read_bytes()
    computed = computed_distances(monkeypatch)
    assert gap_run(arguments, tmp_path / "out", "--d", "20") == 0
    assert computed == [20.0] * 2 * (2 if periods else 1)
    assert (tmp_path / "out" / f"{name}.old").read_bytes() == first
    assert not (tmp_path / "out" / f"{name}.part").exists()
    assert gap_run(arguments, tmp_path / "fresh", "--d", "20") == 0
    assert (tmp_path / "out" / name).read_bytes() == (tmp_path / "fresh" / name).read_bytes()


def test_a_pair_out_of_the_grid_is_kept_after_the_grid_s_pairs(database, tmp_path, monkeypatch):
    """D 10 and 20, then D 20 and 30: every block has D 20, D 30, then D 10 as it was."""
    engine, arguments = database
    episodes_path = store_two_episodes(engine, tmp_path)
    arguments = [*arguments, "--periods", str(episodes_path)]
    path = tmp_path / sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE,
                                                 gap=True)
    grid_of(monkeypatch, [10, 20])
    assert gap_run(arguments, tmp_path) == 0
    old = [record for record in episodes_file_records(path) if record["max_distance_km"] == "10"]
    grid_of(monkeypatch, [20])
    assert gap_run(arguments, tmp_path, "--d", "30") == 0
    records = episodes_file_records(path)
    assert [(record["episode"], record["run"], record["max_distance_km"]) for record in records] == [
        (episode, run, d) for episode in ("1", "2") for run in ("real", "shuffled", "shuffled")
        for d in ("20", "30", "10")]
    assert [record for record in records if record["max_distance_km"] == "10"] == old


def test_an_episode_out_of_the_periods_file_is_kept_after_its_episodes(database, tmp_path,
                                                                      monkeypatch):
    """Both episodes, then a periods file with episode 2 only: episode 1 follows, as it was."""
    engine, arguments = database
    grid_of(monkeypatch, [10])
    episodes_path = store_two_episodes(engine, tmp_path)
    arguments = [*arguments, "--periods", str(episodes_path)]
    path = tmp_path / sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE,
                                                 gap=True)
    assert gap_run(arguments, tmp_path) == 0
    old = episodes_file_records(path)
    header, _, second = episodes_path.read_text(encoding="utf-8").splitlines()
    episodes_path.write_text(f"{header}\n{second}\n", encoding="utf-8")
    computed = computed_distances(monkeypatch)
    assert gap_run(arguments, tmp_path) == 0
    assert computed == []
    records = episodes_file_records(path)
    assert [record["episode"] for record in records] == ["2"] * 3 + ["1"] * 3
    assert records[3:] == old[:3]
    assert records[:3] == old[3:]


def test_an_episode_with_nothing_new_reads_no_strokes(database, tmp_path, monkeypatch, caplog):
    """The same run twice: the second copies every row, reading only the statistics' strokes."""
    engine, arguments = database
    grid_of(monkeypatch, [10])
    episodes_path = store_two_episodes(engine, tmp_path)
    arguments = [*arguments, "--periods", str(episodes_path)]
    path = tmp_path / sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE,
                                                 gap=True)
    assert gap_run(arguments, tmp_path) == 0
    first = path.read_bytes()
    reads = []
    read = sweep.read_strokes
    monkeypatch.setattr(sweep, "read_strokes", lambda *args: reads.append(args) or read(*args))
    computed = computed_distances(monkeypatch)
    with caplog.at_level(logging.INFO):
        assert gap_run(arguments, tmp_path) == 0
    assert computed == []
    assert len(reads) == 2  # the statistics of each episode's stored runs, nothing more
    assert not [record for record in caplog.records if record.getMessage().startswith("Shuffle ")]
    assert path.read_bytes() == first


def test_a_failed_run_leaves_the_gap_file_as_it_was(database, tmp_path, monkeypatch):
    engine, arguments = database
    grid_of(monkeypatch, [10])
    episodes_path = store_two_episodes(engine, tmp_path)
    arguments = [*arguments, "--periods", str(episodes_path)]
    name = sweep.periods_csv_filename("MeteoCat", episodes_path, algorithm=TIME_DISTANCE, gap=True)
    assert gap_run(arguments, tmp_path) == 0
    first = (tmp_path / name).read_bytes()

    def failing(strokes, zone_ids, parameters):
        raise RuntimeError("the machine stopped")

    monkeypatch.setattr(sweep, "memory_storms", failing)
    assert gap_run(arguments, tmp_path, "--d", "20") == 1
    assert (tmp_path / name).read_bytes() == first
    assert (tmp_path / f"{name}.part").exists()
    assert not (tmp_path / f"{name}.old").exists()


def test_a_gap_file_of_other_shuffles_stops_the_run_before_it_starts(database, tmp_path,
                                                                   monkeypatch, caplog):
    engine, arguments = database
    grid_of(monkeypatch, [10])
    episodes_path = store_two_episodes(engine, tmp_path)
    arguments = [*arguments, "--periods", str(episodes_path)]
    assert gap_run(arguments, tmp_path) == 0
    before = row_counts(engine)
    with caplog.at_level(logging.ERROR):
        assert gap_run(arguments, tmp_path, "--shuffles", "3", "--d", "20") == 1
    assert row_counts(engine) == before
    assert "give the same --seed and --shuffles, or delete the file" in caplog.text
