#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strokes and flashes: the input of the flash-based thunderstorm algorithms.

A lightning-location network reports **strokes** and groups them into
**flashes**. Flash-based algorithms (Cellsearch, Tuomi & Larjavaara 2005) work
on flashes, each one represented by its most accurate stroke: that stroke gives
the flash its position, its time and its location error.

Units are the caller's: times in seconds (since the epoch, UTC), coordinates in
metres of a projected CRS, errors in metres. All arrays are copied and made
read-only, so a :class:`Strokes` or :class:`Flashes` cannot change after it has
been validated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _frozen(values, dtype, name: str) -> np.ndarray:
    """A read-only 1-D copy of ``values`` as ``dtype``."""
    array = np.array(values, dtype=dtype, copy=True)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    array.setflags(write=False)
    return array


def _check_finite(name: str, array: np.ndarray) -> None:
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or infinite values")


@dataclass(frozen=True, eq=False)
class Strokes:
    """Strokes as parallel arrays, one element per stroke.

    Attributes
    ----------
    ids : numpy.ndarray of int64
        Stroke identifiers, unique.
    flash_keys : numpy.ndarray of int64
        The flash each stroke belongs to. The caller folds whatever identifies
        a flash (for MeteoCat, ``(network_version, flash_id)``) into one key.
    t : numpy.ndarray of float64
        Times, in seconds since the epoch (UTC).
    x, y : numpy.ndarray of float64
        Coordinates, in metres of a projected CRS.
    error : numpy.ndarray of float64
        Location errors, in metres, not negative.

    Raises
    ------
    ValueError
        If the arrays are not one-dimensional or differ in length, a value is
        NaN or infinite, an error is negative or an id is repeated.
    """

    ids: np.ndarray
    flash_keys: np.ndarray
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    error: np.ndarray

    def __post_init__(self) -> None:
        for name in ("ids", "flash_keys"):
            object.__setattr__(self, name, _frozen(getattr(self, name), np.int64, name))
        for name in ("t", "x", "y", "error"):
            array = _frozen(getattr(self, name), np.float64, name)
            _check_finite(name, array)
            object.__setattr__(self, name, array)
        n = len(self.ids)
        if any(len(getattr(self, name)) != n for name in ("flash_keys", "t", "x", "y", "error")):
            raise ValueError("all stroke arrays must have the same length")
        if np.any(self.error < 0):
            raise ValueError("error must not be negative")
        if len(np.unique(self.ids)) != n:
            raise ValueError("stroke ids must be unique")

    def __len__(self) -> int:
        return len(self.ids)


@dataclass(frozen=True, eq=False)
class Flashes:
    """Flashes as parallel arrays, one element per flash, in time order.

    Each flash is represented by one stroke, whose id, time, position and error
    are stored here. The flashes must be sorted by ``(t, representative_id)``
    with no repeated pair, which is the order the algorithms read them in.

    Attributes
    ----------
    representative_id : numpy.ndarray of int64
        The id of the stroke that represents each flash.
    t : numpy.ndarray of float64
        Times, in seconds since the epoch (UTC).
    x, y : numpy.ndarray of float64
        Coordinates, in metres of a projected CRS.
    error : numpy.ndarray of float64
        Location errors, in metres, not negative.
    stroke_flash_index : numpy.ndarray of int64 or None
        For each stroke of the :class:`Strokes` these flashes were built from
        (in that object's order), the index of its flash here. It lets an
        adapter link **every** stroke of a flash, not only the representative.
        ``None`` when unknown, e.g. for a :meth:`chunk`.

    Raises
    ------
    ValueError
        If the arrays differ in length, a value is NaN or infinite, an error is
        negative, the flashes are not strictly sorted by ``(t,
        representative_id)``, or ``stroke_flash_index`` points outside them.
    """

    representative_id: np.ndarray
    t: np.ndarray
    x: np.ndarray
    y: np.ndarray
    error: np.ndarray
    stroke_flash_index: np.ndarray | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "representative_id",
                           _frozen(self.representative_id, np.int64, "representative_id"))
        for name in ("t", "x", "y", "error"):
            array = _frozen(getattr(self, name), np.float64, name)
            _check_finite(name, array)
            object.__setattr__(self, name, array)
        n = len(self.representative_id)
        if any(len(getattr(self, name)) != n for name in ("t", "x", "y", "error")):
            raise ValueError("all flash arrays must have the same length")
        if np.any(self.error < 0):
            raise ValueError("error must not be negative")
        dt = np.diff(self.t)
        did = np.diff(self.representative_id)
        if not np.all((dt > 0) | ((dt == 0) & (did > 0))):
            raise ValueError("flashes must be strictly sorted by (t, representative_id)")
        if self.stroke_flash_index is not None:
            index = _frozen(self.stroke_flash_index, np.int64, "stroke_flash_index")
            if len(index) and (index.min() < 0 or index.max() >= n):
                raise ValueError("stroke_flash_index points outside the flashes")
            object.__setattr__(self, "stroke_flash_index", index)

    def __len__(self) -> int:
        return len(self.representative_id)

    def chunk(self, part: slice) -> Flashes:
        """The flashes in ``part`` (a slice of contiguous flashes).

        The chunk's ``stroke_flash_index`` is ``None``: the caller keeps the
        parent's mapping, whose indices are offset by ``part.start``.
        """
        return Flashes(
            representative_id=self.representative_id[part],
            t=self.t[part],
            x=self.x[part],
            y=self.y[part],
            error=self.error[part],
        )


def strokes_to_flashes(strokes: Strokes) -> Flashes:
    """Group strokes into flashes, each represented by its most accurate stroke.

    The representative is the stroke with the smallest error; ties go to the
    earliest stroke, then to the lowest id, so the choice is deterministic.

    Parameters
    ----------
    strokes : Strokes
        The strokes, in any order.

    Returns
    -------
    Flashes
        One flash per distinct flash key, sorted by ``(t, representative_id)``,
        with ``stroke_flash_index`` mapping every stroke to its flash.
    """
    n = len(strokes)
    if n == 0:
        empty = np.empty(0)
        return Flashes(representative_id=np.empty(0, dtype=np.int64), t=empty, x=empty, y=empty,
                       error=empty, stroke_flash_index=np.empty(0, dtype=np.int64))
    # By flash, then by the representative's preference: error, time, id.
    order = np.lexsort((strokes.ids, strokes.t, strokes.error, strokes.flash_keys))
    sorted_keys = strokes.flash_keys[order]
    new_flash = np.empty(n, dtype=bool)
    new_flash[0] = True
    new_flash[1:] = sorted_keys[1:] != sorted_keys[:-1]
    representative = order[new_flash]
    group_of_stroke = np.empty(n, dtype=np.int64)
    group_of_stroke[order] = np.cumsum(new_flash) - 1
    # Flashes in reading order: by time, then by representative id.
    flash_order = np.lexsort((strokes.ids[representative], strokes.t[representative]))
    rank = np.empty(len(representative), dtype=np.int64)
    rank[flash_order] = np.arange(len(representative))
    chosen = representative[flash_order]
    return Flashes(
        representative_id=strokes.ids[chosen],
        t=strokes.t[chosen],
        x=strokes.x[chosen],
        y=strokes.y[chosen],
        error=strokes.error[chosen],
        stroke_flash_index=rank[group_of_stroke],
    )


def discard_by_error(flashes: Flashes, max_error_m: float) -> tuple[np.ndarray, int]:
    """Which flashes pass the location-error filter.

    The article accepts "only flashes with location error below 10 km", so a
    flash is kept when ``error < max_error_m`` and discarded when it is equal
    or larger.

    Parameters
    ----------
    flashes : Flashes
        The flashes.
    max_error_m : float
        The maximum location error E_max, in metres.

    Returns
    -------
    kept_mask : numpy.ndarray of bool
        ``True`` for the flashes that are kept.
    n_discarded : int
        How many flashes are discarded.
    """
    kept = flashes.error < max_error_m
    return kept, int(len(kept) - np.count_nonzero(kept))
