#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grouping strokes into flashes, for networks that publish strokes only.

A lightning-location network locates **strokes**; most also group them into
**flashes** and publish the grouping (MeteoCat, FMI). Some do not — the Alaska
Lightning Detection Network publishes strokes alone — and a flash-based algorithm
such as Cellsearch then needs the grouping done first. This module does it with
the rule of the U.S. National Lightning Detection Network (Cummins et al. 1998):
a stroke belongs to a flash when it is

* within ``max_duration_s`` (1 s) of the flash's **first** stroke,
* within ``max_interval_s`` (0.5 s) of the flash's **previous** stroke, and
* within ``max_distance_km`` (10 km) of the flash's **first** stroke.

Each limit is inclusive; the time limits to within :data:`TIME_TOLERANCE_S`,
since a time since the epoch in a float carries rounding of about 1e-7 s and a
gap published as exactly 500 ms must count as 0.5 s. Strokes are taken in time
order; a stroke that fits
several open flashes joins the one whose first stroke is nearest (the earliest of
those at the same distance), and a stroke that fits none starts a flash. Strokes
of different *kinds* (cloud-to-ground and cloud, say) can be kept apart: a stroke
only joins a flash of its own kind.

Cummins, K. L., Murphy, M. J., Bardo, E. A., Hiscox, W. L., Pyle, R. B. and
Pifer, A. E. (1998). A combined TOA/MDF technology upgrade of the U.S. National
Lightning Detection Network. *Journal of Geophysical Research*, 103(D8),
9035-9044.

Units are the caller's: times in seconds (since the epoch, UTC), coordinates in
metres of a projected CRS, as everywhere in this package. The distance is the
plane distance in that CRS, so it carries the CRS's scale error.
"""

from __future__ import annotations

import math

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

import numpy as np

#: The name the grouping is recorded under, wherever a record says how flashes were made.
ALGORITHM = "NLDN_CUMMINS_1998"

#: How far past a time limit a gap may be and still count as within it, in
#: seconds: far below any published time resolution (a millisecond for Alaska),
#: far above the rounding of a float time since the epoch.
TIME_TOLERANCE_S = 1e-6


def _positive_float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


@dataclass(frozen=True)
class FlashGroupingParameters:
    """The limits of the flash rule.

    Attributes
    ----------
    max_duration_s : float
        The longest a flash lasts: a stroke joins it only within this many seconds
        of its first stroke. Default 1.
    max_interval_s : float
        The longest gap within a flash: a stroke joins it only within this many
        seconds of its previous stroke. Default 0.5.
    max_distance_km : float
        A stroke joins a flash only within this many kilometres of its first
        stroke. Default 10.

    Raises
    ------
    ValueError
        If a value is not a positive, finite number.
    """

    max_duration_s: float = 1.0
    max_interval_s: float = 0.5
    max_distance_km: float = 10.0

    def __post_init__(self) -> None:
        for name in ("max_duration_s", "max_interval_s", "max_distance_km"):
            object.__setattr__(self, name, _positive_float(name, getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        """Every limit, by name."""
        return asdict(self)


def group_strokes(t, x, y, parameters: FlashGroupingParameters | None = None,
                  kind=None) -> np.ndarray:
    """The flash each stroke belongs to.

    Parameters
    ----------
    t : array_like of float
        Stroke times, in seconds, **in time order** (equal times allowed: such
        strokes are taken in the order given).
    x, y : array_like of float
        Stroke coordinates, in metres of a projected CRS.
    parameters : FlashGroupingParameters, optional
        The limits; the NLDN ones by default.
    kind : array_like of int, optional
        A kind per stroke; a stroke only joins a flash of its own kind. All the
        same kind when omitted.

    Returns
    -------
    numpy.ndarray of int64
        For each stroke, its flash number: 0, 1, 2 ... in the order of the
        flashes' first strokes, so a flash's first stroke is the first of its
        strokes in the input.

    Raises
    ------
    ValueError
        If the arrays are not one-dimensional or differ in length, a value is NaN
        or infinite, or the times go backwards.
    """
    parameters = parameters or FlashGroupingParameters()
    t = np.asarray(t, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    kind = np.zeros(len(t), dtype=np.int64) if kind is None else np.asarray(kind, dtype=np.int64)
    for name, array in (("t", t), ("x", x), ("y", y), ("kind", kind)):
        if array.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
    if not len(t) == len(x) == len(y) == len(kind):
        raise ValueError("t, x, y and kind must have the same length")
    for name, array in (("t", t), ("x", x), ("y", y)):
        if not np.all(np.isfinite(array)):
            raise ValueError(f"{name} contains NaN or infinite values")
    if np.any(np.diff(t) < 0):
        raise ValueError("t must be in time order")

    duration = parameters.max_duration_s + TIME_TOLERANCE_S
    interval = parameters.max_interval_s + TIME_TOLERANCE_S
    distance_m = parameters.max_distance_km * 1000.0
    flash = [0] * len(t)
    # Per kind, the flashes that may still take a stroke, oldest first:
    # [number, first stroke's t, x, y, last stroke's t]. A flash older than the
    # duration never takes one again (the times only grow), so it is dropped for good.
    open_flashes: dict[int, list[list]] = {}
    count = 0
    for i, (ti, xi, yi, ki) in enumerate(zip(t.tolist(), x.tolist(), y.tolist(), kind.tolist())):
        candidates = [entry for entry in open_flashes.get(ki, ()) if ti - entry[1] <= duration]
        best = None
        best_distance = math.inf
        for entry in candidates:
            if ti - entry[4] > interval:
                continue
            d = math.hypot(xi - entry[2], yi - entry[3])
            if d <= distance_m and d < best_distance:
                best, best_distance = entry, d
        if best is None:
            candidates.append([count, ti, xi, yi, ti])
            flash[i] = count
            count += 1
        else:
            best[4] = ti
            flash[i] = best[0]
        open_flashes[ki] = candidates
    return np.array(flash, dtype=np.int64)
