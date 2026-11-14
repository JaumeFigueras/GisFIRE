#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for grouping strokes into flashes (the NLDN rule, Cummins et al. 1998).

What is pinned down: each of the three limits, at its edge (inclusive) and just
past it; that the duration and the distance are measured from the flash's first
stroke and the interval from its previous one; that interleaved storms make
separate flashes; that a stroke joins the nearest of two open flashes; that kinds
are kept apart while the numbering stays global; the input checks; and a real
case from the Alaska network.
"""

import math

import numpy as np
import pytest

from gisfire_algorithms.thunderstorm import FlashGroupingParameters
from gisfire_algorithms.thunderstorm import group_strokes
from gisfire_algorithms.thunderstorm.flash_grouping import TIME_TOLERANCE_S

#: A time since the epoch, as a real one is: 2025-07-01 22:42:58.009 UTC.
T0 = 1751409778.009


def flashes(t, x=None, y=None, **kwargs):
    x = [0.0] * len(t) if x is None else x
    y = [0.0] * len(t) if y is None else y
    return group_strokes(t, x, y, **kwargs).tolist()


# --- Parameters --------------------------------------------------------------


def test_the_default_limits_are_the_nldn_ones():
    assert FlashGroupingParameters().to_dict() == {
        "max_duration_s": 1.0, "max_interval_s": 0.5, "max_distance_km": 10.0}


@pytest.mark.parametrize("field", ["max_duration_s", "max_interval_s", "max_distance_km"])
@pytest.mark.parametrize("value", [0, -1.0, math.inf, math.nan, "1", True, None])
def test_the_limits_must_be_positive_finite_numbers(field, value):
    with pytest.raises(ValueError, match=field):
        FlashGroupingParameters(**{field: value})


def test_an_integer_limit_is_taken_as_a_float():
    assert FlashGroupingParameters(max_distance_km=5).max_distance_km == 5.0


# --- The three limits --------------------------------------------------------


def test_the_interval_is_inclusive():
    """Published as exactly 500 ms apart, in times since the epoch."""
    assert flashes([T0, T0 + 0.5]) == [0, 0]


def test_past_the_interval_a_new_flash_starts():
    assert flashes([T0, T0 + 0.501]) == [0, 1]


def test_the_interval_is_measured_from_the_previous_stroke():
    """0.4 s steps: each within 0.5 s of the one before, the last 0.8 s after the first."""
    assert flashes([T0, T0 + 0.4, T0 + 0.8]) == [0, 0, 0]


def test_the_duration_is_inclusive():
    assert flashes([T0, T0 + 0.5, T0 + 1.0]) == [0, 0, 0]


def test_past_the_duration_a_new_flash_starts_however_close_the_previous_stroke():
    """Measured from the first stroke: 0.3 s after the previous one is not enough."""
    assert flashes([T0, T0 + 0.4, T0 + 0.8, T0 + 1.1]) == [0, 0, 0, 1]


def test_the_tolerance_covers_rounding_only():
    assert TIME_TOLERANCE_S <= 1e-6
    assert flashes([T0, T0 + 0.5 + 2 * TIME_TOLERANCE_S]) == [0, 1]


def test_the_distance_is_inclusive():
    assert flashes([T0, T0 + 0.1], x=[0.0, 10_000.0]) == [0, 0]


def test_past_the_distance_a_new_flash_starts():
    assert flashes([T0, T0 + 0.1], x=[0.0, 10_000.1]) == [0, 1]


def test_the_distance_is_measured_from_the_first_stroke():
    """The third stroke is 6 km from the second but 12 km from the first."""
    assert flashes([T0, T0 + 0.1, T0 + 0.2], x=[0.0, 6_000.0, 12_000.0]) == [0, 0, 1]


def test_the_distance_is_in_the_plane():
    """3 km east and 4 km north is 5 km."""
    assert flashes([T0, T0 + 0.1], x=[0.0, 3_000.0], y=[0.0, 4_000.0],
                   parameters=FlashGroupingParameters(max_distance_km=5.0)) == [0, 0]


def test_other_limits_can_be_given():
    parameters = FlashGroupingParameters(max_duration_s=2.0, max_interval_s=1.0,
                                         max_distance_km=20.0)
    assert flashes([T0, T0 + 0.9, T0 + 1.8], x=[0.0, 15_000.0, 19_000.0],
                   parameters=parameters) == [0, 0, 0]


# --- Several flashes at once -------------------------------------------------


def test_two_storms_interleaved_in_time_make_two_flashes():
    """Strokes alternate between two places 100 km apart within the same second."""
    t = [T0, T0 + 0.1, T0 + 0.2, T0 + 0.3]
    x = [0.0, 100_000.0, 500.0, 100_400.0]
    assert flashes(t, x=x) == [0, 1, 0, 1]


def test_a_stroke_joins_the_nearest_open_flash():
    """Two flashes 12 km apart; the stroke is 8 km from the first and 4 km from the second."""
    assert flashes([T0, T0 + 0.1, T0 + 0.2], x=[0.0, 12_000.0, 8_000.0]) == [0, 1, 1]


def test_at_the_same_distance_the_earlier_flash_wins():
    assert flashes([T0, T0 + 0.1, T0 + 0.2], x=[0.0, 12_000.0, 6_000.0]) == [0, 1, 0]


def test_a_flash_gone_quiet_is_skipped_for_a_farther_one():
    """The stroke is 3 km from a flash quiet for 0.6 s and 8 km from one quiet for 0.1 s."""
    t = [T0, T0 + 0.5, T0 + 0.6]
    x = [1_000.0, 12_000.0, 4_000.0]
    assert flashes(t, x=x) == [0, 1, 1]


def test_the_flashes_are_numbered_by_their_first_stroke():
    t = [T0, T0 + 0.1, T0 + 0.2, T0 + 5.0, T0 + 5.1]
    x = [0.0, 50_000.0, 100.0, 0.0, 50_000.0]
    assert flashes(t, x=x) == [0, 1, 0, 2, 3]


def test_strokes_at_the_same_instant_are_taken_in_the_given_order():
    assert flashes([T0, T0, T0], x=[0.0, 50_000.0, 1_000.0]) == [0, 1, 0]


# --- Kinds -------------------------------------------------------------------


def test_kinds_are_kept_apart_and_numbered_together():
    """A cloud stroke beside a ground flash starts its own flash, numbered in order."""
    t = [T0, T0 + 0.05, T0 + 0.1, T0 + 0.2]
    kind = [1, 0, 1, 0]
    assert flashes(t, kind=kind) == [0, 1, 0, 1]


def test_without_kinds_every_stroke_is_of_one_kind():
    assert flashes([T0, T0 + 0.05]) == [0, 0]


# --- Input -------------------------------------------------------------------


def test_empty_and_single():
    assert flashes([]) == []
    assert flashes([T0]) == [0]


def test_the_result_is_an_int64_array():
    result = group_strokes(np.array([T0, T0 + 0.1]), np.zeros(2), np.zeros(2))
    assert result.dtype == np.int64


def test_times_going_backwards_are_refused():
    with pytest.raises(ValueError, match="time order"):
        flashes([T0, T0 - 0.001])


@pytest.mark.parametrize("name", ["t", "x", "y"])
def test_nan_and_infinity_are_refused(name):
    values = {"t": [T0, T0 + 0.1], "x": [0.0, 0.0], "y": [0.0, 0.0]}
    values[name] = [values[name][0], math.nan]
    with pytest.raises(ValueError, match=f"{name} contains NaN"):
        group_strokes(values["t"], values["x"], values["y"])
    values[name] = [values[name][0], math.inf]
    with pytest.raises(ValueError, match=f"{name} contains NaN"):
        group_strokes(values["t"], values["x"], values["y"])


def test_arrays_of_different_lengths_are_refused():
    with pytest.raises(ValueError, match="same length"):
        group_strokes([T0, T0 + 0.1], [0.0], [0.0, 0.0])
    with pytest.raises(ValueError, match="same length"):
        group_strokes([T0], [0.0], [0.0], kind=[0, 1])


def test_arrays_must_be_one_dimensional():
    with pytest.raises(ValueError, match="one-dimensional"):
        group_strokes([[T0]], [[0.0]], [[0.0]])


# --- A real case -------------------------------------------------------------

#: Six ground strokes of the Alaska Lightning Detection Network on 2025-07-01,
#: near the Alaska-Yukon border (USWFS, public domain), on NAD83 / Alaska Albers
#: (EPSG:3338): times since the epoch, x and y in metres.
ALASKA_2025_07_01 = [
    (1751409778.009, 571822.7, 1759345.6),  # 22:42:58.009
    (1751409778.018, 574449.3, 1762138.1),  # 22:42:58.018, 3.8 km from the first
    (1751409778.262, 572329.8, 1757334.9),  # 22:42:58.262, 2.1 km from the first
    (1751410968.164, 569436.7, 1753596.6),  # 23:02:48.164, twenty minutes later
    (1751410968.169, 569456.2, 1753664.1),  # 23:02:48.169
    (1751410968.175, 568351.0, 1753249.4),  # 23:02:48.175
]


def test_a_real_case_makes_two_three_stroke_flashes():
    t, x, y = zip(*ALASKA_2025_07_01)
    result = group_strokes(t, x, y)
    assert result.tolist() == [0, 0, 0, 1, 1, 1]
    assert np.bincount(result).tolist() == [3, 3]
