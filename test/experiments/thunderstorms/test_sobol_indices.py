#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sobol indices of the sweep's statistics, on synthetic grids with known answers."""

import csv
import itertools
import math

import numpy as np
import pandas as pd
import pytest

from gisfire_experiments.thunderstorms import sobol_indices as sobol
from gisfire_experiments.thunderstorms.sweep import STATISTIC_COLUMNS


def table(parameters: dict[str, list], values, episodes=(1,)) -> pd.DataFrame:
    """A sweep's file as read: for each episode the full grid of ``parameters``, every
    statistic ``values(episode, **levels)`` (a number, or a dict by statistic)."""
    rows = []
    for episode in episodes:
        for number, levels in enumerate(itertools.product(*parameters.values()), start=1):
            point = dict(zip(parameters, levels))
            value = values(episode, **point)
            statistics = value if isinstance(value, dict) else {}
            rows.append({"episode": episode, "start": "2018-07-03T00:00:00+00:00",
                         "end": "2018-07-04T00:00:00+00:00", "experiment_id": number, **point,
                         **{name: statistics.get(name, value if not statistics else 1.0)
                            for name in STATISTIC_COLUMNS}})
    return pd.DataFrame(rows)


def indices(result_rows, episode=1, statistic="thunderstorms") -> dict[tuple[str, str], float]:
    return {(row["index"], row["parameters"]): row["value"] for row in result_rows
            if row["episode"] == episode and row["statistic"] == statistic}


# --- the indices -------------------------------------------------------------------

def test_an_additive_output_has_its_totals_equal_to_its_first_order_indices():
    rows, _ = sobol.analyse(table({"a": [0, 1, 2], "b": [0, 3]}, lambda e, a, b: 2.0 * a + b))
    va, vb = 4.0 * np.var([0, 1, 2]), np.var([0, 3])
    got = indices(rows)
    assert got[("first_order", "a")] == pytest.approx(va / (va + vb))
    assert got[("first_order", "b")] == pytest.approx(vb / (va + vb))
    assert got[("total", "a")] == pytest.approx(va / (va + vb))
    assert got[("total", "b")] == pytest.approx(vb / (va + vb))
    assert got[("interaction", "a:b")] == pytest.approx(0.0, abs=1e-12)


def test_a_pure_product_is_all_interaction():
    rows, _ = sobol.analyse(table({"a": [0, 1, 2], "b": [0, 1]},
                                  lambda e, a, b: (a - 1.0) * (b - 0.5)))
    got = indices(rows)
    assert got[("first_order", "a")] == pytest.approx(0.0, abs=1e-12)
    assert got[("first_order", "b")] == pytest.approx(0.0, abs=1e-12)
    assert got[("interaction", "a:b")] == pytest.approx(1.0)
    assert got[("total", "a")] == pytest.approx(1.0)
    assert got[("total", "b")] == pytest.approx(1.0)


def test_a_parameter_without_effect_has_indices_of_zero():
    rows, _ = sobol.analyse(table({"a": [0, 1, 2], "b": [0, 3], "c": [5, 6]},
                                  lambda e, a, b, c: 2.0 * a + b))
    got = indices(rows)
    for key in (("first_order", "c"), ("total", "c"), ("interaction", "a:c"),
                ("interaction", "b:c")):
        assert got[key] == pytest.approx(0.0, abs=1e-12)
    va, vb = 4.0 * np.var([0, 1, 2]), np.var([0, 3])
    assert got[("first_order", "a")] == pytest.approx(va / (va + vb))
    assert list(got) == [("first_order", "a"), ("first_order", "b"), ("first_order", "c"),
                         ("total", "a"), ("total", "b"), ("total", "c"),
                         ("interaction", "a:b"), ("interaction", "a:c"), ("interaction", "b:c")]


def test_an_empty_level_is_a_level_of_its_own():
    """Cellsearch's C off is an empty cell: it must not drop out of the grid."""
    rows, _ = sobol.analyse(table({"a": [0, 1], "c": [np.nan, 10.0]},
                                  lambda e, a, c: a + (0.0 if math.isnan(c) else 2.0)))
    got = indices(rows)
    assert got[("first_order", "a")] == pytest.approx(0.25 / 1.25)
    assert got[("first_order", "c")] == pytest.approx(1.0 / 1.25)


# --- episodes and statistics left out ----------------------------------------------

def test_an_episode_without_a_value_or_without_variation_is_left_out_and_counted():
    def values(episode, a, b):
        density = np.nan if (episode, a, b) == (2, 0, 0) else 2.0 * a + b
        thunderstorms = 3.0 if episode == 2 else 2.0 * a + b
        return {"density_median_per_100km2": density, "thunderstorms": thunderstorms,
                "duration_median_min": 2.0 * a + b}

    rows, summary = sobol.analyse(table({"a": [0, 1, 2], "b": [0, 3]}, values, episodes=(1, 2)))
    assert indices(rows, 2, "density_median_per_100km2") == {}
    assert indices(rows, 2, "thunderstorms") == {}
    assert indices(rows, 2, "duration_median_min")
    assert indices(rows, 1, "density_median_per_100km2")
    by_key = {(row["statistic"], row["index"], row["parameters"]): row for row in summary}
    density = by_key[("density_median_per_100km2", "first_order", "a")]
    assert (density["n"], density["episodes_missing"], density["episodes_constant"]) == (1, 1, 0)
    thunderstorms = by_key[("thunderstorms", "total", "b")]
    assert (thunderstorms["n"], thunderstorms["episodes_missing"],
            thunderstorms["episodes_constant"]) == (1, 0, 1)


def test_the_summary_takes_the_mean_median_minimum_and_maximum_over_the_episodes():
    weights = {1: 1.0, 2: 2.0, 3: 3.0}
    rows, summary = sobol.analyse(table({"a": [0, 1], "b": [0, 1]},
                                        lambda e, a, b: weights[e] * a + b, episodes=(1, 2, 3)))
    first = [indices(rows, episode)[("first_order", "a")] for episode in (1, 2, 3)]
    assert first == pytest.approx([w * w / (w * w + 1) for w in (1.0, 2.0, 3.0)])
    row = next(row for row in summary if (row["statistic"], row["index"], row["parameters"])
               == ("thunderstorms", "first_order", "a"))
    assert row["n"] == 3
    assert row["mean"] == pytest.approx(np.mean(first))
    assert row["median"] == pytest.approx(np.median(first))
    assert (row["min"], row["max"]) == (pytest.approx(min(first)), pytest.approx(max(first)))


def test_the_summary_has_the_quartiles_and_the_interquartile_range():
    """Five episodes whose first-order index of a is 0.1, 0.2, 0.3, 0.4 and 0.5
    (Y = w·a + b over a, b in {0, 1} gives w² / (w² + 1))."""
    targets = {episode: 0.1 * episode for episode in range(1, 6)}
    weights = {episode: math.sqrt(s / (1.0 - s)) for episode, s in targets.items()}
    _, summary = sobol.analyse(table({"a": [0, 1], "b": [0, 1]},
                                     lambda e, a, b: weights[e] * a + b, episodes=tuple(targets)))
    row = next(row for row in summary if (row["statistic"], row["index"], row["parameters"])
               == ("thunderstorms", "first_order", "a"))
    assert row["n"] == 5
    assert (row["mean"], row["median"]) == (pytest.approx(0.3), pytest.approx(0.3))
    assert (row["q1"], row["q3"], row["iqr"]) == (pytest.approx(0.2), pytest.approx(0.4),
                                                  pytest.approx(0.2))
    assert (row["min"], row["max"]) == (pytest.approx(0.1), pytest.approx(0.5))


def test_a_statistic_with_no_episode_left_has_an_empty_summary():
    rows, summary = sobol.analyse(table({"a": [0, 1], "b": [0, 1]},
                                        lambda e, a, b: {"thunderstorms": a + b,
                                                         "diameter_p90_km": np.nan}))
    assert indices(rows, 1, "diameter_p90_km") == {}
    row = next(row for row in summary if (row["statistic"], row["index"], row["parameters"])
               == ("diameter_p90_km", "interaction", "a:b"))
    assert (row["n"], row["episodes_missing"]) == (0, 1)
    assert all(math.isnan(row[key]) for key in ("mean", "median", "q1", "q3", "iqr", "min", "max"))


def test_the_constant_statistics_of_the_sweep_are_not_analysed():
    assert "flashes_clustered" not in sobol.STATISTICS
    assert "flashes_discarded_error" not in sobol.STATISTICS
    assert set(sobol.STATISTICS) < set(STATISTIC_COLUMNS)


# --- what is refused ----------------------------------------------------------------

def test_an_episode_without_the_full_grid_is_refused():
    frame = table({"a": [0, 1, 2], "b": [0, 3]}, lambda e, a, b: a + b, episodes=(1, 2))
    with pytest.raises(ValueError, match="episode 2"):
        sobol.analyse(frame.drop(index=frame.index[-1]))
    with pytest.raises(ValueError, match="episode 1"):
        sobol.analyse(pd.concat([frame, frame.iloc[[0]]], ignore_index=True))


def test_a_file_whose_parameters_do_not_vary_is_refused():
    with pytest.raises(ValueError, match="max_time_difference_min"):
        sobol.analyse(table({"max_distance_km": [5, 10], "max_time_difference_min": [16]},
                            lambda e, **levels: 1.0))


def test_a_file_of_one_period_is_one_episode():
    frame = table({"a": [0, 1, 2], "b": [0, 3]}, lambda e, a, b: 2.0 * a + b)
    rows, _ = sobol.analyse(frame.drop(columns=["episode", "start", "end"]))
    assert {row["episode"] for row in rows} == {""}
    assert indices(rows, "")[("interaction", "a:b")] == pytest.approx(0.0, abs=1e-12)


def test_the_parameters_are_the_columns_between_the_experiment_and_the_statistics():
    columns = ["episode", "start", "end", "experiment_id", "attraction_radius_km",
               "max_waiting_time_min", "inertia", "time_distance_limit_min_km", *STATISTIC_COLUMNS]
    assert sobol.parameter_columns(columns) == ["attraction_radius_km", "max_waiting_time_min",
                                                "inertia", "time_distance_limit_min_km"]


# --- the command line ---------------------------------------------------------------

def test_the_command_line_writes_the_indices_and_their_summary(tmp_path):
    source = tmp_path / "in" / "time_distance_galanaki_FMI_finland-100-q1.csv"
    source.parent.mkdir()
    table({"max_distance_km": [5, 10, 15], "max_time_difference_min": [5, 10]},
          lambda e, max_distance_km, max_time_difference_min:
          max_distance_km + 0.1 * max_time_difference_min * e,
          episodes=(184, 352)).to_csv(source, index=False)
    assert sobol.main([str(source), "--output-dir", str(tmp_path / "out")]) == 0
    stem = "time_distance_galanaki_FMI_finland-100-q1"
    rows = list(csv.DictReader((tmp_path / "out" / f"{stem}_sobol.csv").open()))
    assert list(rows[0]) == ["episode", "statistic", "index", "parameters", "value"]
    # 7 statistics × (2 first-order + 2 total + 1 interaction) × 2 episodes.
    assert len(rows) == len(sobol.STATISTICS) * 5 * 2
    assert {row["episode"] for row in rows} == {"184", "352"}
    summary = list(csv.DictReader((tmp_path / "out" / f"{stem}_sobol_summary.csv").open()))
    assert list(summary[0]) == ["statistic", "index", "parameters", "n", "mean", "median", "q1",
                                "q3", "iqr", "min", "max", "episodes_missing",
                                "episodes_constant"]
    assert len(summary) == len(sobol.STATISTICS) * 5


def test_the_output_goes_beside_the_input_by_default(tmp_path):
    source = tmp_path / "sweep.csv"
    table({"a": [0, 1], "b": [0, 1]}, lambda e, a, b: a + 2.0 * b).to_csv(source, index=False)
    assert sobol.main([str(source)]) == 0
    assert (tmp_path / "sweep_sobol.csv").exists()
    assert (tmp_path / "sweep_sobol_summary.csv").exists()


def test_a_bad_file_is_reported_not_raised(tmp_path, caplog):
    source = tmp_path / "defaults.csv"
    table({"a": [0, 1], "b": [3]}, lambda e, a, b: a).to_csv(source, index=False)
    assert sobol.main([str(source)]) == 1
    assert "does not vary" in caplog.text
