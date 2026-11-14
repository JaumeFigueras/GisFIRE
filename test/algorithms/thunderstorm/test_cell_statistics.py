#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the cell area of Tuomi & Larjavaara (2005, appendix) and the derived ratios."""

import math

import numpy as np
import pytest

from gisfire_algorithms.thunderstorm.cell_statistics import cell_area_km2
from gisfire_algorithms.thunderstorm.cell_statistics import density_per_100km2
from gisfire_algorithms.thunderstorm.cell_statistics import flash_rate_per_min
from gisfire_algorithms.thunderstorm.cell_statistics import lifetime_min


def test_triangle_exact_value():
    # Population covariance of (0,0), (1,0), (0,1): s_x² = s_y² = 2/9, s_xy = −1/9,
    # det = 1/27, so A = 12/√27 = 4/√3.
    assert cell_area_km2([0.0, 1.0, 0.0], [0.0, 0.0, 1.0]) == pytest.approx(4 / math.sqrt(3), rel=1e-12)


def test_filled_square_has_an_area_close_to_its_side_squared():
    side = 10.0
    m = 201
    grid = np.linspace(0.0, side, m)
    x, y = np.meshgrid(grid, grid)
    # A discrete grid of m points per side gives exactly L² (m + 1) / (m − 1).
    area = cell_area_km2(x.ravel(), y.ravel())
    assert area == pytest.approx(side**2 * (m + 1) / (m - 1), rel=1e-9)
    assert area == pytest.approx(side**2, rel=0.02)


def test_uniform_random_square():
    rng = np.random.default_rng(1)
    x, y = rng.uniform(0.0, 20.0, size=(2, 20000))
    assert cell_area_km2(x, y) == pytest.approx(400.0, rel=0.03)


def test_area_does_not_depend_on_rotation_or_translation():
    rng = np.random.default_rng(2)
    x = rng.normal(0.0, 4.0, 300)
    y = rng.normal(0.0, 1.5, 300)
    reference = cell_area_km2(x, y)
    angle = math.radians(37.0)
    xr = x * math.cos(angle) - y * math.sin(angle)
    yr = x * math.sin(angle) + y * math.cos(angle)
    assert cell_area_km2(xr, yr) == pytest.approx(reference, rel=1e-9)
    # UTM-sized offsets (EPSG:25831, in km): the centring keeps every digit that matters.
    assert cell_area_km2(xr + 430.0, yr + 4600.0) == pytest.approx(reference, rel=1e-9)


def test_a_stray_point_barely_changes_the_area_of_a_large_cell():
    rng = np.random.default_rng(3)
    x, y = rng.uniform(0.0, 15.0, size=(2, 300))
    base = cell_area_km2(x, y)
    with_stray = cell_area_km2(np.append(x, 25.0), np.append(y, 25.0))
    assert with_stray / base < 1.1


def test_collinear_points_have_no_area():
    t = np.linspace(0.0, 10.0, 50)
    assert cell_area_km2(t, 2.0 * t + 1.0) is None
    assert cell_area_km2(t, np.zeros_like(t)) is None
    assert cell_area_km2([3.0] * 5, [4.0] * 5) is None
    # Nearly on a line (far below any real location error): still no area.
    noise = np.random.default_rng(4).normal(0.0, 1e-10, t.size)
    assert cell_area_km2(t + 430.0, 2.0 * t + 4600.0 + noise) is None


def test_fewer_than_three_points_have_no_area():
    assert cell_area_km2([], []) is None
    assert cell_area_km2([0.0], [0.0]) is None
    assert cell_area_km2([0.0, 1.0], [0.0, 1.0]) is None


def test_area_arrays_must_match():
    with pytest.raises(ValueError):
        cell_area_km2([0.0, 1.0, 2.0], [0.0, 1.0])


def test_lifetime_rate_and_density():
    assert lifetime_min([600.0, 60.0, 1260.0]) == 20.0
    assert lifetime_min([5.0]) == 0.0
    with pytest.raises(ValueError):
        lifetime_min([])
    assert flash_rate_per_min(40, 20.0) == 2.0
    assert flash_rate_per_min(1, 0.0) is None
    # Cell 271 of the article: 344 flashes, 34.7 flashes / 100 km² → about 991 km².
    assert density_per_100km2(344, 991.4) == pytest.approx(34.7, abs=0.01)
    assert density_per_100km2(10, None) is None
