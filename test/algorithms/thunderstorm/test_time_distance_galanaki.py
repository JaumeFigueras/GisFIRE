#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the time-distance clustering of Galanaki et al. (2018).

Coordinates are metres and times seconds, as the adapters pass them. Boundary
cases use values that are exact in binary (10 000 m, 960 s), so ``d = D`` and
``Δt = T`` really sit on the boundary.
"""

import json
import math

import numpy as np
import pytest

from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import merge_summaries
from gisfire_algorithms.thunderstorm.chunking import split_at_gaps
from gisfire_algorithms.thunderstorm.flashes import Flashes
from gisfire_algorithms.thunderstorm.time_distance_galanaki import ALGORITHM
from gisfire_algorithms.thunderstorm.time_distance_galanaki import TimeDistanceParameters
from gisfire_algorithms.thunderstorm.time_distance_galanaki import time_distance

D = 10_000.0
T = 960.0


def make_flashes(rows):
    """Flashes from ``(t, x, y)`` rows, ids 1, 2, …"""
    t, x, y = (list(column) for column in zip(*rows)) if rows else ([], [], [])
    return Flashes(representative_id=list(range(1, len(rows) + 1)), t=t, x=x, y=y,
                   error=[0.0] * len(rows))


def run(rows, **parameters):
    return time_distance(make_flashes(rows), TimeDistanceParameters(**parameters))


# --- distance ---------------------------------------------------------------------

def test_distance_equal_to_d_joins():
    assert run([(0.0, 0.0, 0.0), (60.0, D, 0.0)]).label.tolist() == [1, 1]


def test_distance_over_d_does_not_join():
    assert run([(0.0, 0.0, 0.0), (60.0, D + 0.001, 0.0)]).label.tolist() == [1, 2]


def test_distance_is_euclidean_with_utm_sized_coordinates():
    x0, y0 = 430_000.0, 4_600_000.0
    # 6-8-10 km: exactly D away. 7.1 km in both axes: 10.04 km, beyond it.
    assert run([(0.0, x0, y0), (60.0, x0 + 6000.0, y0 + 8000.0)]).label.tolist() == [1, 1]
    assert run([(0.0, x0, y0), (60.0, x0 + 7100.0, y0 + 7100.0)]).label.tolist() == [1, 2]


# --- time ---------------------------------------------------------------------------

def test_time_difference_equal_to_t_joins():
    assert run([(0.0, 0.0, 0.0), (T, 0.0, 0.0)]).label.tolist() == [1, 1]


def test_time_difference_over_t_does_not_join():
    assert run([(0.0, 0.0, 0.0), (T + 0.001, 0.0, 0.0)]).label.tolist() == [1, 2]


def test_simultaneous_flashes_join_within_d():
    assert run([(0.0, 0.0, 0.0), (0.0, 0.0, D)]).label.tolist() == [1, 1]


# --- both at once -------------------------------------------------------------------

def test_near_in_space_only_or_in_time_only_stays_apart():
    assert run([(0.0, 0.0, 0.0), (2 * T, 0.0, 0.0)]).label.tolist() == [1, 2]
    assert run([(0.0, 0.0, 0.0), (0.0, 2 * D, 0.0)]).label.tolist() == [1, 2]


def test_a_chain_in_space_joins_flashes_farther_than_d_apart():
    rows = [(60.0 * k, 8000.0 * k, 0.0) for k in range(4)]   # 0 to 24 km
    assert run(rows).label.tolist() == [1, 1, 1, 1]


def test_a_chain_in_time_joins_flashes_farther_than_t_apart():
    rows = [(900.0 * k, 0.0, 0.0) for k in range(4)]          # 0 to 45 min
    assert run(rows).label.tolist() == [1, 1, 1, 1]


def test_a_later_flash_joins_two_clusters_into_one():
    rows = [
        (0.0, 0.0, 0.0),         # A
        (60.0, 18000.0, 0.0),    # B, 18 km from A
        (120.0, 9000.0, 0.0),    # 9 km from both: A and B are one cluster
    ]
    assert run(rows).label.tolist() == [1, 1, 1]


# --- labels -------------------------------------------------------------------------

def test_labels_follow_each_clusters_first_flash_from_first_label():
    rows = [
        (0.0, 0.0, 0.0),         # cluster A
        (60.0, 50000.0, 0.0),    # cluster B
        (120.0, 0.0, 0.0),       # A again
        (5000.0, 0.0, 0.0),      # C, more than T after A
    ]
    result = time_distance(make_flashes(rows), TimeDistanceParameters(), first_label=5)
    assert result.label.tolist() == [5, 6, 5, 7]
    assert result.next_label == 8


def test_first_label_must_be_a_positive_integer():
    with pytest.raises(ValueError):
        time_distance(make_flashes([]), TimeDistanceParameters(), first_label=0)


# --- N_min and the summary ----------------------------------------------------------

def sized_clusters(sizes):
    """One cluster per size, each in its own quiet period (gaps of an hour)."""
    rows = []
    t = 0.0
    for size in sizes:
        for _ in range(size):
            rows.append((t, 0.0, 0.0))
            t += 1.0
        t += 3600.0
    return rows


def test_by_default_every_cluster_is_kept_even_of_one_flash():
    result = run(sized_clusters([1, 2, 5]))
    assert result.kept_labels.tolist() == [1, 2, 3]
    assert result.kept_flash_mask().all()


def test_n_min_keeps_only_large_clusters_and_the_summary_adds_up():
    sizes = [1, 2, 3, 5, 1]
    result = run(sized_clusters(sizes), min_flashes=3)
    assert result.kept_labels.tolist() == [3, 4]
    assert result.kept_flash_mask().sum() == 8
    assert result.summary == {"flashes_total": 12, "flashes_kept": 8, "cells_total": 5,
                              "cells_kept": 2}
    json.dumps(result.summary)


def test_empty_input():
    result = run([])
    assert result.label.tolist() == []
    assert result.kept_labels.tolist() == []
    assert result.next_label == 1
    assert result.summary == {"flashes_total": 0, "flashes_kept": 0, "cells_total": 0,
                              "cells_kept": 0}


# --- the clusters are the article's, however they are found ------------------------

def synthetic_day(seed=0):
    """Several moving storms, some overlapping, with quiet gaps between pairs."""
    rng = np.random.default_rng(seed)
    rows = []
    start = 0.0
    for storm in range(6):
        n = int(rng.integers(40, 120))
        t = start + np.sort(rng.uniform(0.0, 5400.0, n))
        x = rng.uniform(0.0, 60000.0) + 8.0 * (t - start) + rng.normal(0.0, 6000.0, n)
        y = rng.uniform(0.0, 60000.0) + 3.0 * (t - start) + rng.normal(0.0, 6000.0, n)
        rows.extend(zip(t.tolist(), x.tolist(), y.tolist()))
        start += 2000.0 if storm % 2 == 0 else 9000.0
    rows.sort(key=lambda row: row[0])
    return rows


def every_pair(rows):
    """The clusters by brute force: join every pair within D and T, number by first flash."""
    group = list(range(len(rows)))

    def root(i):
        while group[i] != i:
            i = group[i]
        return i

    for i, (ti, xi, yi) in enumerate(rows):
        for j in range(i + 1, len(rows)):
            tj, xj, yj = rows[j]
            if abs(tj - ti) <= T and math.hypot(xj - xi, yj - yi) <= D:
                group[max(root(i), root(j))] = min(root(i), root(j))
    labels = {}
    return [labels.setdefault(root(i), len(labels) + 1) for i in range(len(rows))]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_clusters_join_every_pair_within_d_and_t(seed):
    rows = synthetic_day(seed)
    result = run(rows)
    assert result.label.tolist() == every_pair(rows)
    assert 1 < result.summary["cells_total"] < len(rows)


def test_chunked_and_unchunked_runs_are_identical():
    flashes = make_flashes(synthetic_day(seed=4))
    params = TimeDistanceParameters(min_flashes=5)
    whole = time_distance(flashes, params)
    chunks = split_at_gaps(flashes.t, T)
    assert len(chunks) > 1
    labels, kept = [], []
    summary = None
    next_label = 1
    for chunk in chunks:
        part = time_distance(flashes.chunk(chunk), params, first_label=next_label)
        next_label = part.next_label
        labels.append(part.label)
        kept.append(part.kept_labels)
        summary = part.summary if summary is None else merge_summaries(summary, part.summary)
    assert np.array_equal(np.concatenate(labels), whole.label)
    assert np.array_equal(np.concatenate(kept), whole.kept_labels)
    assert summary == whole.summary
    assert next_label == whole.next_label


def test_result_arrays_are_read_only():
    result = run([(0.0, 0.0, 0.0)])
    with pytest.raises(ValueError):
        result.label[0] = 5
    with pytest.raises(ValueError):
        result.kept_labels[0] = 5


@pytest.mark.parametrize("rows", [[], synthetic_day(seed=3)], ids=["empty", "day"])
def test_the_computation_time_is_returned_out_of_the_summary(rows):
    result = run(rows)
    for seconds in (result.wall_time_s, result.cpu_time_s):
        assert isinstance(seconds, float)
        assert math.isfinite(seconds) and seconds >= 0.0
    assert not {"wall_time_s", "cpu_time_s"} & result.summary.keys()


# --- parameters ---------------------------------------------------------------------

def test_defaults_and_to_dict_is_complete():
    params = TimeDistanceParameters()
    assert params.to_dict() == {
        "max_distance_km": 10.0,
        "max_time_difference_min": 16.0,
        "min_flashes": 1,
        "srid": 25831,
    }
    assert json.loads(json.dumps(params.to_dict())) == params.to_dict()
    assert ALGORITHM == "TIME_DISTANCE_GALANAKI_2018"


def test_the_limits_are_given_in_km_and_minutes():
    rows = [(0.0, 0.0, 0.0), (60.0, 7000.0, 0.0), (1260.0, 7000.0, 0.0)]
    assert run(rows, max_distance_km=5.0).label.tolist() == [1, 2, 3]
    assert run(rows, max_time_difference_min=20.0).label.tolist() == [1, 1, 1]


def test_numbers_are_normalised_so_equal_configurations_compare_equal():
    a = TimeDistanceParameters(max_distance_km=10, max_time_difference_min=16,
                               min_flashes=np.int64(1))
    b = TimeDistanceParameters(max_distance_km=10.0, max_time_difference_min=16.0, min_flashes=1)
    assert a == b
    assert a.to_dict() == b.to_dict()
    assert isinstance(a.to_dict()["max_distance_km"], float)
    assert isinstance(a.to_dict()["min_flashes"], int)


@pytest.mark.parametrize("parameters", [
    {"max_distance_km": 0},
    {"max_distance_km": -1.0},
    {"max_distance_km": float("nan")},
    {"max_distance_km": "10"},
    {"max_distance_km": True},
    {"max_time_difference_min": 0.0},
    {"max_time_difference_min": float("inf")},
    {"min_flashes": 0},
    {"min_flashes": 1.5},
    {"min_flashes": True},
    {"srid": 0},
    {"srid": "25831"},
])
def test_invalid_parameters(parameters):
    with pytest.raises(ValueError):
        TimeDistanceParameters(**parameters)
