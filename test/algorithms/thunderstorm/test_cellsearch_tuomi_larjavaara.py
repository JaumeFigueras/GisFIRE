#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for Cellsearch (Tuomi & Larjavaara 2005), at least one case per rule.

Coordinates are metres and times seconds, as the adapters pass them. Boundary
cases use values that are exact in binary (15 000 m, 900 s), so ``d = R`` and
``Δt = T`` really sit on the boundary.
"""

import json
import math

import numpy as np
import pytest

from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import ALGORITHM
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import CHECK_EVERY
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import SIZE_CLASSES
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import CellsearchCancelled
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import CellsearchParameters
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import cellsearch
from gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara import merge_summaries
from gisfire_algorithms.thunderstorm.chunking import split_at_gaps
from gisfire_algorithms.thunderstorm.flashes import Flashes

# A small N_min so short synthetic cells are kept unless a test says otherwise.
SMALL = {"min_flashes": 3}


def make_flashes(rows):
    """Flashes from ``(t, x, y)`` or ``(t, x, y, error)`` rows, ids 1, 2, …"""
    rows = [row if len(row) == 4 else (*row, 0.0) for row in rows]
    t, x, y, error = (list(column) for column in zip(*rows)) if rows else ([], [], [], [])
    return Flashes(representative_id=list(range(1, len(rows) + 1)), t=t, x=x, y=y, error=error)


def run(rows, **parameters):
    return cellsearch(make_flashes(rows), CellsearchParameters(**{**SMALL, **parameters}))


# --- (i) radius of attraction -------------------------------------------------

def test_i_distance_equal_to_r_joins():
    result = run([(0.0, 0.0, 0.0), (60.0, 15000.0, 0.0)])
    assert result.label.tolist() == [1, 1]


def test_i_distance_over_r_opens_a_new_cell():
    result = run([(0.0, 0.0, 0.0), (60.0, 15000.001, 0.0)])
    assert result.label.tolist() == [1, 2]


def test_i_distance_is_measured_to_the_centre_not_to_the_last_flash():
    # Centre after two flashes: (7000, 0). The third flash is 15 km from it but
    # 22 km from the first flash and 8 km from the last one.
    result = run([(0.0, 0.0, 0.0), (60.0, 14000.0, 0.0), (120.0, 22000.0, 0.0)])
    assert result.label.tolist() == [1, 1, 1]
    result = run([(0.0, 0.0, 0.0), (60.0, 14000.0, 0.0), (120.0, 22000.5, 0.0)])
    assert result.label.tolist() == [1, 1, 2]


def test_i_works_with_utm_sized_coordinates():
    x0, y0 = 430000.0, 4600000.0
    result = run([(0.0, x0, y0), (60.0, x0 + 9000.0, y0 + 12000.0), (61.0, x0, y0 - 15001.0)])
    # The second flash is exactly 15 km away (a 9-12-15 triangle).
    assert result.label.tolist() == [1, 1, 2]


# --- (ii) delay time ------------------------------------------------------------

def test_ii_delay_equal_to_t_joins():
    result = run([(0.0, 0.0, 0.0), (900.0, 0.0, 0.0)])
    assert result.label.tolist() == [1, 1]


def test_ii_delay_over_t_closes_the_cell():
    result = run([(0.0, 0.0, 0.0), (900.001, 0.0, 0.0)])
    assert result.label.tolist() == [1, 2]


def test_ii_delay_is_measured_from_the_latest_flash():
    result = run([(0.0, 0.0, 0.0), (800.0, 0.0, 0.0), (1600.0, 0.0, 0.0)])
    assert result.label.tolist() == [1, 1, 1]


def test_ii_a_closed_cell_is_never_tested_again():
    rows = [
        (0.0, 0.0, 0.0),          # cell 1
        (1000.0, 10000.0, 0.0),   # cell 1 is closed by now: cell 2, although 10 km ≤ R away
        (1001.0, 0.0, 0.0),       # right on top of cell 1, but only cell 2 is open
    ]
    assert run(rows).label.tolist() == [1, 2, 2]


def test_ii_a_discarded_flash_does_not_keep_a_cell_alive():
    rows = [
        (0.0, 0.0, 0.0),
        (500.0, 0.0, 0.0, 20000.0),   # discarded by E_max
        (1000.0, 0.0, 0.0),           # 1000 s after the cell's latest accepted flash
    ]
    assert run(rows).label.tolist() == [1, -1, 2]


# --- (iii) time–distance limit ---------------------------------------------------

def test_iii_is_ignored_when_c_is_none():
    # Δt = 10 min, d_last = 14 km: the product is 140 min·km.
    result = run([(0.0, 0.0, 0.0), (600.0, 14000.0, 0.0)], time_distance_limit_min_km=None)
    assert result.label.tolist() == [1, 1]


def test_iii_product_equal_to_c_joins_and_over_c_does_not():
    rows = [(0.0, 0.0, 0.0), (600.0, 14000.0, 0.0)]
    assert run(rows, time_distance_limit_min_km=140.0).label.tolist() == [1, 1]
    assert run(rows, time_distance_limit_min_km=139.9).label.tolist() == [1, 2]


def test_iii_uses_the_distance_to_the_latest_flash():
    # After two flashes the centre is (5000, 0) and the latest flash is (10000, 0).
    # The third flash is 7 km from the centre (7 × 2 min = 14 ≤ 15) but 12 km from
    # the latest flash (12 × 2 min = 24 > 15).
    rows = [(0.0, 0.0, 0.0), (60.0, 10000.0, 0.0), (180.0, -2000.0, 0.0)]
    assert run(rows, time_distance_limit_min_km=15.0).label.tolist() == [1, 1, 2]
    assert run(rows, time_distance_limit_min_km=24.0).label.tolist() == [1, 1, 1]


def test_iii_simultaneous_flashes_always_pass():
    result = run([(0.0, 0.0, 0.0), (0.0, 14000.0, 0.0)], time_distance_limit_min_km=0.001)
    assert result.label.tolist() == [1, 1]


# --- (iv) closest cell -----------------------------------------------------------

def test_iv_the_closest_candidate_wins():
    rows = [
        (0.0, 0.0, 0.0),          # cell 1
        (10.0, 20000.0, 0.0),     # cell 2 (20 km > R from cell 1)
        (20.0, 12000.0, 0.0),     # 12 km from cell 1, 8 km from cell 2
    ]
    assert run(rows).label.tolist() == [1, 2, 2]


def test_iv_a_tie_goes_to_the_lowest_label():
    rows = [(0.0, 0.0, 0.0), (10.0, 20000.0, 0.0), (20.0, 10000.0, 0.0)]
    assert run(rows).label.tolist() == [1, 2, 1]
    # Same geometry, but the cell on the right is created first: it has the lower label.
    rows = [(0.0, 20000.0, 0.0), (10.0, 0.0, 0.0), (20.0, 10000.0, 0.0)]
    assert run(rows).label.tolist() == [1, 2, 1]


def test_iv_a_candidate_failing_iii_is_not_chosen_even_if_closer():
    rows = [
        (0.0, 0.0, 0.0),             # cell 1
        (540.0, 20000.0, 0.0),       # cell 2
        (600.0, 9000.0, 0.0),        # 9 km from cell 1 (Δt 10 min → 90), 11 km from cell 2 (Δt 1 min → 11)
    ]
    assert run(rows).label.tolist() == [1, 2, 1]
    assert run(rows, time_distance_limit_min_km=50.0).label.tolist() == [1, 2, 2]


# --- (v) new cell ----------------------------------------------------------------

def test_v_new_cells_take_sequential_labels_from_first_label():
    rows = [(0.0, 0.0, 0.0), (1.0, 50000.0, 0.0), (2.0, 100000.0, 0.0), (3.0, 50000.0, 100.0)]
    result = cellsearch(make_flashes(rows), CellsearchParameters(**SMALL), first_label=7)
    assert result.label.tolist() == [7, 8, 9, 8]
    assert result.next_label == 10


# --- (vi) centre and inertia -------------------------------------------------------

def test_vi_centre_is_the_mean_of_all_flashes_while_n_is_below_i():
    result = run([(0.0, 0.0, 0.0), (1.0, 3000.0, 600.0), (2.0, 6000.0, 1200.0)], inertia=20)
    assert result.centre_x.tolist() == [0.0, 1500.0, 3000.0]
    assert result.centre_y.tolist() == [0.0, 300.0, 600.0]


def test_vi_centre_is_the_mean_of_the_last_i_flashes():
    rows = [(float(k), 3000.0 * k, 0.0) for k in range(5)]
    result = run(rows, inertia=3)
    # Means of: [0], [0, 3], [0, 3, 6], [3, 6, 9], [6, 9, 12] (km).
    assert result.centre_x.tolist() == [0.0, 1500.0, 3000.0, 6000.0, 9000.0]


def test_vi_the_moving_centre_changes_which_flashes_join():
    # With I = 1 the centre is the latest flash, so a cell can travel far.
    rows = [(60.0 * k, 10000.0 * k, 0.0) for k in range(6)]
    assert run(rows, inertia=1).label.tolist() == [1] * 6
    # With I = 20 the centre lags behind and the trail is split.
    assert len(set(run(rows, inertia=20).label.tolist())) > 1


def test_sequence_numbers_flashes_within_each_cell():
    rows = [(0.0, 0.0, 0.0), (1.0, 50000.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (4.0, 50000.0, 0.0)]
    result = run(rows)
    assert result.label.tolist() == [1, 2, 1, 1, 2]
    assert result.sequence.tolist() == [1, 1, 2, 3, 2]


# --- E_max ------------------------------------------------------------------------

def test_e_max_discards_inside_cellsearch():
    rows = [
        (0.0, 0.0, 0.0, 9999.999),
        (1.0, 0.0, 0.0, 10000.0),   # error == E_max: discarded
        (2.0, 0.0, 0.0, 500.0),
    ]
    result = run(rows)
    assert result.label.tolist() == [1, -1, 1]
    assert result.sequence.tolist() == [1, 0, 2]
    assert math.isnan(result.centre_x[1]) and math.isnan(result.centre_y[1])
    assert result.summary["flashes_discarded_error"] == 1
    assert result.summary["flashes_total"] == 3


# --- N_min, summary and open cells --------------------------------------------------

SIZES = [1, 2, 4, 5, 9, 10, 19, 20, 29, 30, 49, 50, 99, 100, 199, 200]


def sized_cells(sizes, *, discarded_every=0):
    """One cell per size, each in its own quiet period (gaps of an hour)."""
    rows = []
    t = 0.0
    for size in sizes:
        for k in range(size):
            rows.append((t, 0.0, 0.0))
            t += 1.0
            if discarded_every and len(rows) % discarded_every == 0:
                rows.append((t, 0.0, 0.0, 50000.0))
                t += 1.0
        t += 3600.0
    return rows


def test_n_min_keeps_only_large_cells_and_the_summary_adds_up():
    rows = sized_cells(SIZES, discarded_every=37)
    result = run(rows, min_flashes=10)
    summary = result.summary
    sizes_by_label = {label: int(np.count_nonzero(result.label == label)) for label in set(result.label.tolist()) - {-1}}
    assert sorted(sizes_by_label.values()) == sorted(SIZES)
    assert result.kept_labels.tolist() == sorted(label for label, n in sizes_by_label.items() if n >= 10)
    assert summary["cells_total"] == len(SIZES)
    assert summary["cells_kept"] == sum(1 for n in SIZES if n >= 10)
    assert summary["flashes_kept"] == sum(n for n in SIZES if n >= 10)
    small = sum(n for n in SIZES if n < 10)
    assert summary["flashes_kept"] + small + summary["flashes_discarded_error"] == summary["flashes_total"]
    assert summary["flashes_total"] == len(rows)
    # Two cells per class (one at each end), except the one-flash class.
    expected = {"1": [1], "2-4": [2, 4], "5-9": [5, 9], "10-19": [10, 19], "20-29": [20, 29],
                "30-49": [30, 49], "50-99": [50, 99], "100-199": [100, 199], "200+": [200]}
    assert list(summary["size_classes"]) == [key for key, _, _ in SIZE_CLASSES]
    for key, members in expected.items():
        assert summary["size_classes"][key] == {"cells": len(members), "flashes": sum(members)}
    assert result.kept_flash_mask().sum() == summary["flashes_kept"]
    json.dumps(summary)


def test_open_at_end_counts_cells_whose_latest_flash_is_within_t_of_the_end():
    # Cell 1's latest flash is 1000 s before the end: closed. Cell 2: open.
    assert run([(0.0, 0.0, 0.0), (1000.0, 50000.0, 0.0)]).open_at_end == 1
    # 500 s apart: both still open.
    assert run([(500.0, 0.0, 0.0), (1000.0, 50000.0, 0.0)]).open_at_end == 2
    assert run([]).open_at_end == 0


def test_empty_input():
    result = run([])
    assert result.label.tolist() == []
    assert result.kept_labels.tolist() == []
    assert result.next_label == 1
    assert result.summary["cells_total"] == 0
    assert result.summary["flashes_total"] == 0


# --- chunks, determinism ---------------------------------------------------------------

def synthetic_day(seed=0):
    """Several moving storms with quiet gaps between some of them, plus noise."""
    rng = np.random.default_rng(seed)
    rows = []
    start = 0.0
    for storm in range(6):
        n = int(rng.integers(150, 400))
        t = start + np.sort(rng.uniform(0.0, 5400.0, n))
        cx = rng.uniform(0.0, 100000.0) + 8.0 * (t - start)   # moving at 8 m/s
        cy = rng.uniform(0.0, 100000.0) + 3.0 * (t - start)
        x = cx + rng.normal(0.0, 4000.0, n)
        y = cy + rng.normal(0.0, 4000.0, n)
        error = rng.exponential(2000.0, n)
        rows.extend(zip(t.tolist(), x.tolist(), y.tolist(), error.tolist()))
        # Storms overlap in pairs; between pairs, a gap far longer than T.
        start += 2000.0 if storm % 2 == 0 else 9000.0
    rows.sort(key=lambda row: row[0])
    return rows


@pytest.mark.parametrize("limit", [None, 60.0])
def test_chunked_and_unchunked_runs_are_identical(limit):
    flashes = make_flashes(synthetic_day())
    params = CellsearchParameters(time_distance_limit_min_km=limit)
    whole = cellsearch(flashes, params)
    chunks = split_at_gaps(flashes.t, params.max_waiting_time_min * 60.0)
    assert len(chunks) == 3
    labels, sequences, xs, ys, kept = [], [], [], [], []
    summary = None
    next_label = 1
    part = None
    for chunk in chunks:
        part = cellsearch(flashes.chunk(chunk), params, first_label=next_label)
        next_label = part.next_label
        labels.append(part.label)
        sequences.append(part.sequence)
        xs.append(part.centre_x)
        ys.append(part.centre_y)
        kept.append(part.kept_labels)
        summary = part.summary if summary is None else merge_summaries(summary, part.summary)
    assert np.array_equal(np.concatenate(labels), whole.label)
    assert np.array_equal(np.concatenate(sequences), whole.sequence)
    assert np.array_equal(np.concatenate(xs), whole.centre_x, equal_nan=True)
    assert np.array_equal(np.concatenate(ys), whole.centre_y, equal_nan=True)
    assert np.array_equal(np.concatenate(kept), whole.kept_labels)
    assert summary == whole.summary
    assert next_label == whole.next_label
    assert part.open_at_end == whole.open_at_end
    assert whole.summary["cells_kept"] > 0
    assert whole.summary["flashes_discarded_error"] > 0


def test_result_is_deterministic():
    flashes = make_flashes(synthetic_day(seed=5))
    params = CellsearchParameters(time_distance_limit_min_km=80.0)
    a = cellsearch(flashes, params)
    b = cellsearch(flashes, params)
    assert np.array_equal(a.label, b.label)
    assert np.array_equal(a.centre_x, b.centre_x, equal_nan=True)
    assert a.summary == b.summary


def test_result_arrays_are_read_only():
    result = run([(0.0, 0.0, 0.0)])
    with pytest.raises(ValueError):
        result.label[0] = 5


# --- parameters ------------------------------------------------------------------

def test_defaults_and_to_dict_is_complete():
    params = CellsearchParameters()
    assert params.to_dict() == {
        "attraction_radius_km": 15.0,
        "max_waiting_time_min": 15.0,
        "time_distance_limit_min_km": None,
        "inertia": 20,
        "max_location_error_km": 10.0,
        "min_flashes": 5,
        "srid": 25831,
    }
    assert json.loads(json.dumps(params.to_dict())) == params.to_dict()
    assert ALGORITHM == "CELLSEARCH_TUOMI_LARJAVAARA_2005"


def test_numbers_are_normalised_so_equal_configurations_compare_equal():
    a = CellsearchParameters(attraction_radius_km=15, time_distance_limit_min_km=60, inertia=np.int64(20))
    b = CellsearchParameters(attraction_radius_km=15.0, time_distance_limit_min_km=60.0, inertia=20)
    assert a == b
    assert a.to_dict() == b.to_dict()
    assert isinstance(a.to_dict()["attraction_radius_km"], float)
    assert isinstance(a.to_dict()["inertia"], int)


@pytest.mark.parametrize("parameters", [
    {"attraction_radius_km": 0},
    {"attraction_radius_km": -1.0},
    {"attraction_radius_km": float("nan")},
    {"attraction_radius_km": "15"},
    {"max_waiting_time_min": 0.0},
    {"max_waiting_time_min": float("inf")},
    {"time_distance_limit_min_km": 0.0},
    {"time_distance_limit_min_km": True},
    {"inertia": 0},
    {"inertia": 2.5},
    {"inertia": True},
    {"max_location_error_km": 0.0},
    {"min_flashes": 2},
    {"min_flashes": 5.0},
    {"srid": 0},
    {"srid": "25831"},
])
def test_invalid_parameters(parameters):
    with pytest.raises(ValueError):
        CellsearchParameters(**parameters)


def test_first_label_must_be_a_positive_integer():
    with pytest.raises(ValueError):
        cellsearch(make_flashes([]), CellsearchParameters(), first_label=0)


# --- progress and cancellation -------------------------------------------------------

def test_progress_is_reported_and_cancellation_stops_the_run():
    rows = [(float(k), 0.0, 0.0) for k in range(2 * CHECK_EVERY + 5)]
    calls = []
    cellsearch(make_flashes(rows), CellsearchParameters(), progress=lambda done, total: calls.append((done, total)))
    total = len(rows)
    assert calls == [(CHECK_EVERY, total), (2 * CHECK_EVERY, total), (total, total)]
    with pytest.raises(CellsearchCancelled):
        cellsearch(make_flashes(rows), CellsearchParameters(), is_cancelled=lambda: True)
    # A callback that never cancels lets the run finish.
    result = cellsearch(make_flashes(rows), CellsearchParameters(), is_cancelled=lambda: False)
    assert result.label.tolist() == [1] * total


def test_merge_summaries_refuses_different_keys():
    with pytest.raises(ValueError):
        merge_summaries({"a": 1}, {"b": 1})
