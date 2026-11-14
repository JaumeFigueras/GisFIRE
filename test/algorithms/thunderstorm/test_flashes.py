#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for strokes, flashes and the representative stroke of a flash."""

import numpy as np
import pytest

from gisfire_algorithms.thunderstorm.flashes import Flashes
from gisfire_algorithms.thunderstorm.flashes import Strokes
from gisfire_algorithms.thunderstorm.flashes import discard_by_error
from gisfire_algorithms.thunderstorm.flashes import strokes_to_flashes


def make_strokes(rows):
    """Strokes from ``(id, flash_key, t, x, y, error)`` rows."""
    columns = list(zip(*rows)) if rows else [[]] * 6
    return Strokes(ids=columns[0], flash_keys=columns[1], t=columns[2], x=columns[3], y=columns[4],
                   error=columns[5])


def test_representative_is_the_most_accurate_stroke():
    strokes = make_strokes([
        (1, 7, 100.0, 0.0, 0.0, 900.0),
        (2, 7, 100.2, 500.0, 0.0, 300.0),
        (3, 7, 100.4, 900.0, 0.0, 600.0),
    ])
    flashes = strokes_to_flashes(strokes)
    assert len(flashes) == 1
    assert flashes.representative_id.tolist() == [2]
    # Position, time and error all come from the representative.
    assert flashes.t.tolist() == [100.2]
    assert flashes.x.tolist() == [500.0]
    assert flashes.error.tolist() == [300.0]


def test_error_tie_goes_to_the_earliest_then_the_lowest_id():
    earliest = make_strokes([
        (5, 1, 10.5, 0.0, 0.0, 200.0),
        (6, 1, 10.1, 1.0, 0.0, 200.0),
    ])
    assert strokes_to_flashes(earliest).representative_id.tolist() == [6]
    same_time = make_strokes([
        (9, 1, 10.0, 0.0, 0.0, 200.0),
        (4, 1, 10.0, 1.0, 0.0, 200.0),
    ])
    assert strokes_to_flashes(same_time).representative_id.tolist() == [4]


def test_single_stroke_flash():
    flashes = strokes_to_flashes(make_strokes([(11, 3, 5.0, 1.0, 2.0, 50.0)]))
    assert flashes.representative_id.tolist() == [11]
    assert flashes.stroke_flash_index.tolist() == [0]


def test_flashes_are_in_time_order_and_every_stroke_maps_to_its_flash():
    strokes = make_strokes([
        (1, 20, 50.0, 0.0, 0.0, 100.0),   # flash 20, time 50
        (2, 10, 30.0, 0.0, 0.0, 100.0),   # flash 10, time 30 (representative)
        (3, 10, 30.5, 0.0, 0.0, 400.0),   # flash 10
        (4, 30, 30.0, 0.0, 0.0, 100.0),   # flash 30, time 30: tie with flash 10 on time
        (5, 20, 50.1, 0.0, 0.0, 700.0),   # flash 20
    ])
    flashes = strokes_to_flashes(strokes)
    # Sorted by (t, representative_id): stroke 2 (t 30), stroke 4 (t 30), stroke 1 (t 50).
    assert flashes.representative_id.tolist() == [2, 4, 1]
    assert flashes.stroke_flash_index.tolist() == [2, 0, 0, 1, 2]


def test_empty_strokes_give_no_flashes():
    flashes = strokes_to_flashes(make_strokes([]))
    assert len(flashes) == 0
    assert flashes.stroke_flash_index.tolist() == []


def test_discard_by_error_boundary():
    flashes = Flashes(representative_id=[1, 2, 3], t=[0.0, 1.0, 2.0], x=[0.0] * 3, y=[0.0] * 3,
                      error=[9999.999, 10000.0, 12000.0])
    kept, n_discarded = discard_by_error(flashes, 10000.0)
    # "Only flashes with location error below 10 km are accepted".
    assert kept.tolist() == [True, False, False]
    assert n_discarded == 2


def test_arrays_are_read_only_copies():
    t = np.array([0.0, 1.0])
    flashes = Flashes(representative_id=[1, 2], t=t, x=[0.0, 0.0], y=[0.0, 0.0], error=[0.0, 0.0])
    t[0] = 99.0
    assert flashes.t[0] == 0.0
    with pytest.raises(ValueError):
        flashes.t[0] = 5.0


@pytest.mark.parametrize("rows, message", [
    ([(1, 1, 0.0, 0.0, 0.0, 1.0), (1, 2, 1.0, 0.0, 0.0, 1.0)], "unique"),
    ([(1, 1, float("nan"), 0.0, 0.0, 1.0)], "NaN"),
    ([(1, 1, 0.0, float("inf"), 0.0, 1.0)], "NaN"),
    ([(1, 1, 0.0, 0.0, 0.0, -1.0)], "negative"),
])
def test_strokes_validation(rows, message):
    with pytest.raises(ValueError, match=message):
        make_strokes(rows)


def test_strokes_lengths_must_match():
    with pytest.raises(ValueError, match="same length"):
        Strokes(ids=[1, 2], flash_keys=[1], t=[0.0, 1.0], x=[0.0, 0.0], y=[0.0, 0.0], error=[0.0, 0.0])
    with pytest.raises(ValueError, match="one-dimensional"):
        Strokes(ids=[[1]], flash_keys=[[1]], t=[[0.0]], x=[[0.0]], y=[[0.0]], error=[[0.0]])


@pytest.mark.parametrize("ids, t", [
    ([1, 2], [1.0, 0.0]),   # time goes back
    ([2, 1], [0.0, 0.0]),   # same time, ids not increasing
    ([1, 1], [0.0, 0.0]),   # repeated (t, id)
])
def test_flashes_must_be_strictly_sorted(ids, t):
    with pytest.raises(ValueError, match="sorted"):
        Flashes(representative_id=ids, t=t, x=[0.0, 0.0], y=[0.0, 0.0], error=[0.0, 0.0])


def test_flashes_validation():
    with pytest.raises(ValueError, match="same length"):
        Flashes(representative_id=[1, 2], t=[0.0], x=[0.0], y=[0.0], error=[0.0])
    with pytest.raises(ValueError, match="negative"):
        Flashes(representative_id=[1], t=[0.0], x=[0.0], y=[0.0], error=[-1.0])
    with pytest.raises(ValueError, match="NaN"):
        Flashes(representative_id=[1], t=[0.0], x=[float("nan")], y=[0.0], error=[0.0])
    with pytest.raises(ValueError, match="outside"):
        Flashes(representative_id=[1], t=[0.0], x=[0.0], y=[0.0], error=[0.0], stroke_flash_index=[0, 1])


def test_chunk_keeps_the_flash_arrays_and_drops_the_stroke_mapping():
    flashes = Flashes(representative_id=[1, 2, 3], t=[0.0, 1.0, 2.0], x=[0.0, 1.0, 2.0], y=[0.0] * 3,
                      error=[5.0, 6.0, 7.0], stroke_flash_index=[0, 1, 2])
    part = flashes.chunk(slice(1, 3))
    assert part.representative_id.tolist() == [2, 3]
    assert part.x.tolist() == [1.0, 2.0]
    assert part.error.tolist() == [6.0, 7.0]
    assert part.stroke_flash_index is None
