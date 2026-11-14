#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statistics of a group of flashes: area, lifetime, flash rate and density.

The area is the one of Tuomi & Larjavaara (2005, appendix), built from the
regression of the points' coordinates::

    A = 12 · s_x · s_y · √(1 − r²) = 12 · √det(Σ)

with Σ the **population** covariance matrix of the points (sums divided by n).
A uniformly filled square of side L has an area of L², a stray point barely
inflates it, and it does not depend on the orientation of the axes.
"""

from __future__ import annotations

import math

import numpy as np

#: Below this value of ``1 − r²`` a set of points is treated as a line.
_COLLINEAR_TOLERANCE = 1e-12


def cell_area_km2(x_km, y_km) -> float | None:
    """The area covered by a set of points (Tuomi & Larjavaara 2005, appendix).

    Parameters
    ----------
    x_km, y_km : array_like of float
        The points' coordinates, in km of a projected CRS.

    Returns
    -------
    float or None
        The area in km², or ``None`` when it is undefined: fewer than three
        points, or points on a line (``1 − r²`` below a tolerance, all points
        equal included). It is never 0, so a density is never infinite.

    Raises
    ------
    ValueError
        If the coordinate arrays differ in length.
    """
    x = np.asarray(x_km, dtype=np.float64)
    y = np.asarray(y_km, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("x_km and y_km must be one-dimensional and of the same length")
    if len(x) < 3:
        return None
    # Centre first: the variance of raw projected coordinates computed as
    # Σx²/n − x̄² would lose most of its digits.
    xc = x - x.mean()
    yc = y - y.mean()
    sxx = float(np.mean(xc * xc))
    syy = float(np.mean(yc * yc))
    sxy = float(np.mean(xc * yc))
    scale = sxx * syy
    det = scale - sxy * sxy
    if scale <= 0 or det <= _COLLINEAR_TOLERANCE * scale:
        return None
    return 12.0 * math.sqrt(det)


def lifetime_min(t_s) -> float:
    """The lifetime of a group of flashes: last minus first flash, in minutes.

    Parameters
    ----------
    t_s : array_like of float
        The flashes' times, in seconds, at least one.
    """
    t = np.asarray(t_s, dtype=np.float64)
    if t.size == 0:
        raise ValueError("a lifetime needs at least one flash")
    return float(t.max() - t.min()) / 60.0


def flash_rate_per_min(number_of_flashes: int, lifetime: float) -> float | None:
    """Flashes per minute, or ``None`` for a lifetime of zero."""
    if lifetime <= 0:
        return None
    return number_of_flashes / lifetime


def density_per_100km2(number_of_flashes: int, area_km2: float | None) -> float | None:
    """Flashes per 100 km², as the article reports it, or ``None`` with no area."""
    if area_km2 is None or area_km2 <= 0:
        return None
    return 100.0 * number_of_flashes / area_km2
