#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gap statistic of the sweep's share of isolated flashes, on synthetic gap files with known
answers."""

import csv
import itertools
import math

import numpy as np
import pandas as pd
import pytest

from gisfire_experiments.thunderstorms import gap_statistic as gap
from gisfire_experiments.thunderstorms.sweep import (GRIDS, SEED, STATISTIC_COLUMNS,
                                                     gap_file_columns, next_seed)

CELLSEARCH = list(GRIDS["cellsearch_tuomi_larjavaara"])


def gap_table(parameters: dict[str, list], real, shuffled, episodes=(1,), shuffles=3,
              flashes=100) -> pd.DataFrame:
    """A sweep's gap file as read, in its column order: for each episode its real rows over
    the full grid of ``parameters`` (``isolated_pct = real(episode, **levels)``), then the
    grid on each of ``shuffles`` shuffles (``shuffled(episode, shuffle, **levels)``)."""
    grid = [dict(zip(parameters, levels)) for levels in itertools.product(*parameters.values())]

    def row(episode, run, seed, experiment, point, value):
        return {"episode": episode, "start": "2018-07-03T00:00:00+00:00",
                "end": "2018-07-04T00:00:00+00:00", "run": run, "seed": seed,
                "flashes": flashes, "experiment_id": experiment, **point,
                **dict.fromkeys(STATISTIC_COLUMNS, 1.0), "isolated_pct": value}

    rows = []
    for episode in episodes:
        rows += [row(episode, "real", "", number, point, real(episode, **point))
                 for number, point in enumerate(grid, start=1)]
        rows += [row(episode, "shuffled", 1000 + shuffle, "", point,
                     shuffled(episode, shuffle, **point))
                 for shuffle in range(shuffles) for point in grid]
    return pd.DataFrame(rows)


def at(frame: pd.DataFrame, **levels) -> pd.Series:
    """The one row of ``frame`` at ``levels``."""
    (index,) = frame.index[np.logical_and.reduce([frame[name] == value
                                                  for name, value in levels.items()])]
    return frame.loc[index]


# --- the gap ------------------------------------------------------------------------

def test_the_gap_is_the_shuffles_mean_minus_the_real_share():
    """Shuffles of 50, 60 and 70 %: mean 60, standard deviation over B √(200 / 3)."""
    values, _, _ = gap.analyse(gap_table({"x": [0, 1], "y": [0, 1]},
                                         lambda e, x, y: 10.0 * x + 20.0 * y,
                                         lambda e, b, x, y: 50.0 + 10.0 * b))
    assert list(values.columns) == ["episode", "flashes", "x", "y", "isolated_pct",
                                    "shuffled_mean", "shuffled_sd", "gap", "best"]
    assert len(values) == 4
    for x, y in itertools.product([0, 1], [0, 1]):
        row = at(values, episode=1, x=x, y=y)
        assert row.isolated_pct == pytest.approx(10.0 * x + 20.0 * y)
        assert row.shuffled_mean == pytest.approx(60.0)
        assert row.shuffled_sd == pytest.approx(math.sqrt(200.0 / 3.0))
        assert row.gap == pytest.approx(60.0 - 10.0 * x - 20.0 * y)
        assert row.flashes == 100


def test_best_is_each_episodes_largest_gap():
    values, summary, no_maximum = gap.analyse(gap_table(
        {"x": [0, 1], "y": [0, 1]},
        lambda e, x, y: 40.0 if (x, y) == ((0, 0) if e == 1 else (1, 1)) else 60.0,
        lambda e, b, x, y: 80.0, episodes=(1, 2)))
    assert at(values, episode=1, x=0, y=0).best == 1.0
    assert at(values, episode=2, x=1, y=1).best == 1.0
    assert values.best.sum() == 2.0
    assert at(summary, x=0, y=0).episodes_best == 1.0
    assert at(summary, x=1, y=1).episodes_best == 1.0
    assert at(summary, x=0, y=1).episodes_best == 0.0
    assert no_maximum == []


def test_a_shared_maximum_is_split_equally():
    values, summary, _ = gap.analyse(gap_table({"x": [0, 1], "y": [0, 1, 2]},
                                               lambda e, x, y: 10.0 * x + (5.0 if y == 2 else 0.0),
                                               lambda e, b, x, y: 50.0))
    assert at(values, episode=1, x=0, y=0).best == pytest.approx(0.5)
    assert at(values, episode=1, x=0, y=1).best == pytest.approx(0.5)
    assert values.best.sum() == pytest.approx(1.0)
    assert at(summary, x=0, y=1).episodes_best == pytest.approx(0.5)


def test_an_episode_with_no_gap_above_zero_has_no_maximum_but_counts():
    """Episode 2's real data leave as many flashes isolated as its shuffles, or more."""
    values, summary, no_maximum = gap.analyse(gap_table(
        {"x": [0, 1], "y": [0, 1]},
        lambda e, x, y: 10.0 * x if e == 1 else 100.0 - 5.0 * x * y,
        lambda e, b, x, y: 50.0 if e == 1 else 95.0, episodes=(1, 2)))
    assert no_maximum == [2]
    assert (values.loc[values.episode == 2, "best"] == 0.0).all()
    assert values.loc[values.episode == 1, "best"].sum() == 1.0
    row = at(summary, x=1, y=1)
    assert row.n == 2
    assert row["median"] == pytest.approx((40.0 + 0.0) / 2.0)


def test_the_summary_is_taken_over_the_episodes():
    """Five episodes whose gap at x = 1 is 1, 2, 3, 4 and 5 points."""
    _, summary, _ = gap.analyse(gap_table({"x": [0, 1]},
                                          lambda e, x: 50.0 - e * x,
                                          lambda e, b, x: 50.0, episodes=(1, 2, 3, 4, 5)))
    row = at(summary, x=1)
    assert row.n == 5
    assert (row["mean"], row["median"]) == (pytest.approx(3.0), pytest.approx(3.0))
    assert (row.q1, row.q3, row.iqr) == (pytest.approx(2.0), pytest.approx(4.0),
                                         pytest.approx(2.0))
    assert (row["min"], row["max"]) == (pytest.approx(1.0), pytest.approx(5.0))
    assert row.episodes_best == 5.0
    assert row.bootstrap_best == 1.0
    assert at(summary, x=0).episodes_best == 0.0
    assert list(summary.columns) == ["x", "n", "mean", "median", "q1", "q3", "iqr", "min", "max",
                                     "episodes_best", "bootstrap_best"]


def test_an_empty_level_is_a_level_of_its_own():
    """Cellsearch's four parameters, C off as an empty cell."""
    grid = {CELLSEARCH[0]: [10, 20], CELLSEARCH[1]: [15], CELLSEARCH[2]: [20],
            CELLSEARCH[3]: [np.nan, 10.0]}
    values, summary, _ = gap.analyse(gap_table(
        grid, lambda e, **levels: 30.0 if math.isnan(levels[CELLSEARCH[3]]) else 20.0,
        lambda e, b, **levels: 50.0))
    assert len(values) == 4 and len(summary) == 4
    off = summary[summary[CELLSEARCH[3]].isna()]
    assert len(off) == 2
    assert off["median"].tolist() == pytest.approx([20.0, 20.0])
    on = summary[summary[CELLSEARCH[3]] == 10.0]
    assert on["median"].tolist() == pytest.approx([30.0, 30.0])
    assert on.episodes_best.tolist() == pytest.approx([0.5, 0.5])


# --- the bootstrap ------------------------------------------------------------------

def test_the_bootstrap_draws_the_episodes_with_the_sweeps_generator():
    """From seed 1 the generator gives 16807, 282475249, 1622650073, 984943658,
    1144108930, 470211272, 101027544 and 1457850878: of two episodes, (Z − 1)·2 // (2³¹ − 2)
    draws 0, 0 | 1, 0 | 1, 0 | 0, 1. Episode 0 alone has the largest median at x, the others
    at y."""
    z, draws = 1, []
    for _ in range(8):
        z = next_seed(z)
        draws.append((z - 1) * 2 // (2**31 - 2))
    assert draws == [0, 0, 1, 0, 1, 0, 0, 1]
    gaps = np.array([[10.0, 0.0], [0.0, 20.0]])
    assert gap.bootstrap_best(gaps, resamples=4, seed=1) == pytest.approx([0.25, 0.75])


def test_a_shared_median_is_split_and_none_above_zero_takes_no_sample():
    assert gap.bootstrap_best(np.array([[10.0, 10.0]]), resamples=3, seed=1) == pytest.approx(
        [0.5, 0.5])
    assert gap.bootstrap_best(np.array([[0.0, -1.0]]), resamples=3, seed=1) == pytest.approx(
        [0.0, 0.0])


def test_the_bootstrap_draws_a_thousand_samples_from_the_sweeps_seed():
    assert gap.RESAMPLES == 1000
    gaps = np.array([[10.0, 0.0, 5.0], [0.0, 20.0, 5.0], [3.0, 2.0, 1.0]])
    shares = gap.bootstrap_best(gaps)
    assert shares.tolist() == gap.bootstrap_best(gaps, resamples=1000, seed=SEED).tolist()
    assert shares.tolist() == gap.bootstrap_best(gaps).tolist()
    assert shares.sum() == pytest.approx(1.0)


def test_the_bootstrap_takes_the_episodes_in_increasing_order():
    """Episodes 3, 1 and 2 in the file; their gaps 30 at x = 1, 10 at x = 1, 20 at x = 0."""
    _, summary, _ = gap.analyse(gap_table({"x": [0, 1]},
                                          lambda e, x: 50.0 - 10.0 * e if x == e % 2 else 50.0,
                                          lambda e, b, x: 50.0, episodes=(3, 1, 2)))
    expected = gap.bootstrap_best(np.array([[0.0, 10.0], [20.0, 0.0], [0.0, 30.0]]))
    assert summary.bootstrap_best.tolist() == pytest.approx(expected.tolist())


# --- what a file may hold -----------------------------------------------------------

def test_a_defaults_file_has_one_combination():
    values, summary, no_maximum = gap.analyse(gap_table(
        {"max_distance_km": [10], "max_time_difference_min": [16]},
        lambda e, **levels: 10.0 * e, lambda e, b, **levels: 35.0, episodes=(1, 2, 3, 4)))
    assert len(summary) == 1
    assert values.best.tolist() == [1.0, 1.0, 1.0, 0.0]
    assert no_maximum == [4]
    assert summary.episodes_best.iloc[0] == 3.0


def test_a_file_of_one_period_is_one_episode():
    frame = gap_table({"x": [0, 1]}, lambda e, x: 10.0 * x, lambda e, b, x: 50.0)
    values, summary, _ = gap.analyse(frame.drop(columns=["episode", "start", "end"]))
    assert values.episode.tolist() == ["", ""]
    assert values.gap.tolist() == pytest.approx([50.0, 40.0])
    assert summary.n.tolist() == [1, 1]


@pytest.mark.parametrize("periods", [True, False])
@pytest.mark.parametrize("algorithm", list(GRIDS))
def test_the_parameters_of_every_algorithm_are_the_columns_after_the_experiment(algorithm,
                                                                                periods):
    assert gap.parameter_columns(gap_file_columns(algorithm, periods)) == list(GRIDS[algorithm])


# --- what is refused ----------------------------------------------------------------

def test_a_file_that_is_not_a_gap_file_is_refused():
    frame = gap_table({"x": [0, 1]}, lambda e, x: 10.0, lambda e, b, x: 50.0)
    with pytest.raises(ValueError, match="not a sweep's gap file"):
        gap.analyse(frame[frame.run == "real"].drop(columns=["run", "seed", "flashes"]))
    with pytest.raises(ValueError, match="no shuffled rows"):
        gap.analyse(frame[frame.run == "real"])


def test_a_combination_without_one_real_row_and_the_others_shuffles_is_refused():
    frame = gap_table({"x": [0, 1], "y": [0, 1]}, lambda e, x, y: 10.0,
                      lambda e, b, x, y: 50.0, episodes=(1, 2))
    real = frame.index[(frame.run == "real") & (frame.episode == 2)]
    with pytest.raises(ValueError, match="episode 2, x 0, y 0: 0 real and 3 shuffled"):
        gap.analyse(frame.drop(index=real[0]))
    with pytest.raises(ValueError, match="episode 2, x 0, y 0: 2 real"):
        gap.analyse(pd.concat([frame, frame.loc[[real[0]]]], ignore_index=True))
    shuffled = frame.index[(frame.run == "shuffled") & (frame.episode == 1)]
    with pytest.raises(ValueError, match="episode 1, x 1, y 1: 1 real and 2 shuffled"):
        gap.analyse(frame.drop(index=shuffled[-1]))


def test_episodes_with_other_combinations_are_refused():
    frame = gap_table({"x": [0, 1], "y": [0, 1]}, lambda e, x, y: 10.0,
                      lambda e, b, x, y: 50.0, episodes=(1, 2))
    with pytest.raises(ValueError, match="x 1, y 0 is in 1 of the 2 episodes"):
        gap.analyse(frame[~((frame.episode == 2) & (frame.x == 1) & (frame.y == 0))])


def test_an_empty_isolated_pct_is_refused():
    frame = gap_table({"x": [0, 1]}, lambda e, x: np.nan if x else 10.0, lambda e, b, x: 50.0,
                      episodes=(7,))
    with pytest.raises(ValueError, match="episode 7 has an empty isolated_pct"):
        gap.analyse(frame)


# --- the command line ---------------------------------------------------------------

def test_the_command_line_writes_the_gaps_and_their_summary(tmp_path):
    source = tmp_path / "in" / "cellsearch_tuomi_larjavaara_FMI_gap_finland-100-q1.csv"
    source.parent.mkdir()
    grid = {CELLSEARCH[0]: [10, 15], CELLSEARCH[1]: [15], CELLSEARCH[2]: [20],
            CELLSEARCH[3]: [np.nan, 10.0]}
    gap_table(grid, lambda e, **levels: e % 7 + levels[CELLSEARCH[0]],
              lambda e, b, **levels: 50.0 + b, episodes=(184, 352)).to_csv(source, index=False)
    assert gap.main([str(source), "--output-dir", str(tmp_path / "out")]) == 0
    stem = "cellsearch_tuomi_larjavaara_FMI_gap_finland-100-q1"
    rows = list(csv.DictReader((tmp_path / "out" / f"{stem}_gap.csv").open()))
    assert list(rows[0]) == ["episode", "flashes", *CELLSEARCH, *gap.VALUE_COLUMNS]
    assert len(rows) == 2 * 4
    # The parameters as written in the input: C off empty, the others as they were.
    assert [(row[CELLSEARCH[0]], row[CELLSEARCH[2]], row[CELLSEARCH[3]]) for row in rows[:4]] == [
        ("10", "20", ""), ("10", "20", "10.0"), ("15", "20", ""), ("15", "20", "10.0")]
    assert float(rows[0]["gap"]) == pytest.approx(51.0 - (184 % 7 + 10))
    summary = list(csv.DictReader((tmp_path / "out" / f"{stem}_gap_summary.csv").open()))
    assert list(summary[0]) == [*CELLSEARCH, *gap.SUMMARY_COLUMNS]
    assert len(summary) == 4


def test_the_output_goes_beside_the_input_by_default(tmp_path, caplog):
    source = tmp_path / "sweep_gap.csv"
    gap_table({"x": [0, 1]}, lambda e, x: 10.0 * x, lambda e, b, x: 50.0,
              episodes=(1, 2)).to_csv(source, index=False)
    caplog.set_level("INFO")
    assert gap.main([str(source)]) == 0
    assert (tmp_path / "sweep_gap_gap.csv").exists()
    assert (tmp_path / "sweep_gap_gap_summary.csv").exists()
    assert "largest median gap 50.00 points: x 0" in caplog.text
    assert "Episodes without a maximum (no gap above 0): none" in caplog.text


def test_a_bad_file_is_reported_not_raised(tmp_path, caplog):
    source = tmp_path / "sensitivity.csv"
    gap_table({"x": [0, 1]}, lambda e, x: 10.0, lambda e, b, x: 50.0).drop(
        columns=["run", "seed", "flashes"]).to_csv(source, index=False)
    assert gap.main([str(source)]) == 1
    assert "not a sweep's gap file" in caplog.text
