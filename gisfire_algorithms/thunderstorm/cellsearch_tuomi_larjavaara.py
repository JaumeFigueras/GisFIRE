#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cellsearch: grouping of lightning flashes into flash cells.

T. J. Tuomi and M. Larjavaara, *Identification and analysis of flash cells in
thunderstorms*, Q. J. R. Meteorol. Soc. **131** (2005) 1191–1214,
doi:10.1256/qj.04.64, section 4(a).

The flashes are read in time order. Each new flash is tested against the open
cells:

(i)   **radius of attraction**: its distance to the cell's current centre is at
      most R;
(ii)  **delay time**: its delay from the cell's latest flash is at most T. Cells
      beyond this limit are closed and never tested again;
(iii) **time–distance limit** (optional): the product of that delay (minutes)
      and its distance to the cell's latest flash (km) is at most C;
(iv)  **closest cell**: of the cells passing (i)–(iii) the one with the closest
      centre is chosen (the article does not say how to break a tie: the lowest
      label wins);
(v)   **new cell**: with no candidate the flash opens a new cell;
(vi)  **cell centre and inertia**: the centre is the mean position of the
      cell's last ``min(I, n)`` flashes.

Before the search, flashes with a location error of E_max or more are discarded.
After it, only cells with at least N_min flashes are *kept* for analysis; the
others are stray flashes, counted in the summary only.

With ``C = None`` condition (iii) is off. That is the variant of the article's
Fig. 14, **not** its basic run: Table 1, Table 2 and Figs. 8 and 13 use
condition (iii), with a value of C the article does not publish.

Internally the thresholds are converted once to the input's units (metres and
seconds), so a boundary given exactly (15 km against 15 000 m, 15 min against
900 s) is compared exactly.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from .flashes import Flashes
from .flashes import discard_by_error

#: The value of ``thunderstorm_experiment.algorithm`` for this algorithm.
ALGORITHM = "CELLSEARCH_TUOMI_LARJAVAARA_2005"

#: Cell-size classes of the summary, as ``(key, smallest, largest)`` with
#: ``None`` for no upper bound. They are the article's Table 1 classes, with its
#: "100–" split into the 100–199 and 200– classes of Table 2.
SIZE_CLASSES: tuple[tuple[str, int, int | None], ...] = (
    ("1", 1, 1),
    ("2-4", 2, 4),
    ("5-9", 5, 9),
    ("10-19", 10, 19),
    ("20-29", 20, 29),
    ("30-49", 30, 49),
    ("50-99", 50, 99),
    ("100-199", 100, 199),
    ("200+", 200, None),
)

#: How often (in flashes) the progress callback and the cancellation check run.
CHECK_EVERY = 1000


class CellsearchCancelled(Exception):
    """Raised when the caller's ``is_cancelled`` callback asks to stop."""


def _positive_float(name: str, value: Any, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def _integer(name: str, value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class CellsearchParameters:
    """The parameters of a Cellsearch run.

    Attributes
    ----------
    attraction_radius_km : float
        R, the radius of attraction, in km (condition i). Default 15.
    max_waiting_time_min : float
        T, the maximum waiting (delay) time, in minutes (condition ii).
        Default 15.
    time_distance_limit_min_km : float or None
        C, the time–distance limit, in min·km (condition iii). ``None`` (the
        default) turns the condition off.
    inertia : int
        I, the cell inertia: the number of latest flashes the centre is the mean
        of (condition vi). Default 20.
    max_location_error_km : float
        E_max: flashes with this location error or more are discarded, in km.
        Default 10.
    min_flashes : int
        N_min: cells with fewer flashes are stray flashes, not kept. Default 5,
        at least 3 (an area needs three points).
    srid : int
        The EPSG code of the projected CRS (in metres) the coordinates are in.
        Default 25831. The core only records it; the adapters project.

    Raises
    ------
    ValueError
        If a value has the wrong type or is out of range.
    """

    attraction_radius_km: float = 15.0
    max_waiting_time_min: float = 15.0
    time_distance_limit_min_km: float | None = None
    inertia: int = 20
    max_location_error_km: float = 10.0
    min_flashes: int = 5
    srid: int = 25831

    def __post_init__(self) -> None:
        normalised = {
            "attraction_radius_km": _positive_float("attraction_radius_km", self.attraction_radius_km),
            "max_waiting_time_min": _positive_float("max_waiting_time_min", self.max_waiting_time_min),
            "time_distance_limit_min_km": _positive_float(
                "time_distance_limit_min_km", self.time_distance_limit_min_km, optional=True
            ),
            "inertia": _integer("inertia", self.inertia, 1),
            "max_location_error_km": _positive_float("max_location_error_km", self.max_location_error_km),
            "min_flashes": _integer("min_flashes", self.min_flashes, 3),
            "srid": _integer("srid", self.srid, 1),
        }
        for name, value in normalised.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        """Every parameter, defaults and ``None`` included.

        The experiment's uniqueness rule compares the stored JSON by value, so
        a run with a default left implicit must not look different from one
        that states it.
        """
        return asdict(self)


@dataclass(frozen=True, eq=False)
class CellsearchResult:
    """The outcome of :func:`cellsearch`, per input flash and in summary.

    Attributes
    ----------
    label : numpy.ndarray of int64
        For each input flash, its cell's label (sequential from
        ``first_label``, in order of creation), or −1 for a flash discarded by
        E_max. Labels of cells that are not kept stay in the numbering, so the
        kept labels have gaps, as the article's running numbers do.
    sequence : numpy.ndarray of int32
        The flash's position in its cell, from 1; 0 for a discarded flash.
    centre_x, centre_y : numpy.ndarray of float64
        The cell's running centre right after adding the flash, in the input's
        CRS (metres); NaN for a discarded flash.
    kept_labels : numpy.ndarray of int64
        The labels of the cells with at least ``min_flashes`` flashes, sorted.
    summary : dict
        ``size_classes`` (``{key: {"cells": int, "flashes": int}}`` for every
        class of :data:`SIZE_CLASSES`), ``flashes_total`` (input flashes),
        ``flashes_discarded_error``, ``flashes_kept`` (in kept cells),
        ``cells_total`` and ``cells_kept``. Flashes in kept cells, flashes in
        smaller cells and discarded flashes add up to ``flashes_total``.
    open_at_end : int
        How many cells were still open after the last flash, i.e. whose latest
        flash is within T of it. If the input was cut at the end of a time
        window, these cells may have been cut too.
    next_label : int
        The first label for a following run, so labels stay unique when the
        input is processed in chunks.
    """

    label: np.ndarray
    sequence: np.ndarray
    centre_x: np.ndarray
    centre_y: np.ndarray
    kept_labels: np.ndarray
    summary: dict[str, Any]
    open_at_end: int
    next_label: int

    def kept_flash_mask(self) -> np.ndarray:
        """``True`` for the flashes that belong to a kept cell."""
        return np.isin(self.label, self.kept_labels)


class _Cell:
    """An open cell during the search."""

    __slots__ = ("label", "t_last", "x_last", "y_last", "xs", "ys", "centre_x", "centre_y", "n")

    def __init__(self, label: int, inertia: int) -> None:
        self.label = label
        self.xs: deque[float] = deque(maxlen=inertia)
        self.ys: deque[float] = deque(maxlen=inertia)
        self.n = 0
        self.t_last = self.x_last = self.y_last = self.centre_x = self.centre_y = 0.0

    def add(self, t: float, x: float, y: float) -> None:
        self.n += 1
        self.t_last, self.x_last, self.y_last = t, x, y
        self.xs.append(x)
        self.ys.append(y)
        # The mean of at most I values: recomputed rather than kept as a running
        # sum, so it is exact to the last bit and does not drift.
        k = len(self.xs)
        self.centre_x = math.fsum(self.xs) / k
        self.centre_y = math.fsum(self.ys) / k


def _size_class(n: int) -> str:
    for key, smallest, largest in SIZE_CLASSES:
        if n >= smallest and (largest is None or n <= largest):
            return key
    raise ValueError(f"no size class for {n} flashes")  # pragma: no cover


def _summary(sizes: list[int], min_flashes: int, flashes_total: int, discarded: int) -> dict[str, Any]:
    classes = {key: {"cells": 0, "flashes": 0} for key, _, _ in SIZE_CLASSES}
    for n in sizes:
        entry = classes[_size_class(n)]
        entry["cells"] += 1
        entry["flashes"] += n
    kept = [n for n in sizes if n >= min_flashes]
    return {
        "size_classes": classes,
        "flashes_total": flashes_total,
        "flashes_discarded_error": discarded,
        "flashes_kept": sum(kept),
        "cells_total": len(sizes),
        "cells_kept": len(kept),
    }


def cellsearch(
    flashes: Flashes,
    params: CellsearchParameters,
    *,
    first_label: int = 1,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> CellsearchResult:
    """Group time-ordered flashes into flash cells (Tuomi & Larjavaara 2005).

    Parameters
    ----------
    flashes : Flashes
        The flashes, in time order, with coordinates in metres of a projected
        CRS. Flashes with ``error ≥ E_max`` are discarded here; the caller
        does not filter them beforehand.
    params : CellsearchParameters
        The parameters of the run.
    first_label : int, optional
        The label of the first cell (default 1). Pass the previous chunk's
        ``next_label`` to keep labels unique across chunks.
    progress : callable, optional
        Called as ``progress(done, total)`` every :data:`CHECK_EVERY` flashes
        and once at the end.
    is_cancelled : callable, optional
        Called every :data:`CHECK_EVERY` flashes; returning ``True`` stops the
        search.

    Returns
    -------
    CellsearchResult

    Raises
    ------
    CellsearchCancelled
        If ``is_cancelled`` returns ``True``.
    ValueError
        If ``first_label`` is not an integer of at least 1.
    """
    first_label = _integer("first_label", first_label, 1)
    total = len(flashes)
    radius_m = params.attraction_radius_km * 1000.0
    waiting_s = params.max_waiting_time_min * 60.0
    # Δt[min] · d[km] ≤ C  ⇔  Δt[s] · d[m] ≤ C · 60 · 1000
    limit_s_m = (None if params.time_distance_limit_min_km is None
                 else params.time_distance_limit_min_km * 60.0 * 1000.0)

    kept_mask, discarded = discard_by_error(flashes, params.max_location_error_km * 1000.0)

    label = np.full(total, -1, dtype=np.int64)
    sequence = np.zeros(total, dtype=np.int32)
    centre_x = np.full(total, np.nan)
    centre_y = np.full(total, np.nan)

    t_all = flashes.t.tolist()
    x_all = flashes.x.tolist()
    y_all = flashes.y.tolist()
    use = kept_mask.tolist()

    open_cells: list[_Cell] = []  # always in increasing label order
    sizes: list[int] = []  # flashes per cell, indexed by label - first_label
    next_label = first_label

    for i in range(total):
        if i % CHECK_EVERY == 0 and i:
            if is_cancelled is not None and is_cancelled():
                raise CellsearchCancelled(f"cancelled after {i} of {total} flashes")
            if progress is not None:
                progress(i, total)
        if not use[i]:
            continue
        t, x, y = t_all[i], x_all[i], y_all[i]

        # (ii) Close the cells that waited too long; they are never tested again.
        open_cells = [cell for cell in open_cells if t - cell.t_last <= waiting_s]

        # (i), (iii) and (iv): the closest acceptable centre; on a tie the lowest
        # label, because the cells are visited in label order and only a strictly
        # closer one replaces the best so far.
        best: _Cell | None = None
        best_distance = math.inf
        for cell in open_cells:
            distance = math.hypot(x - cell.centre_x, y - cell.centre_y)
            if distance > radius_m:
                continue
            if limit_s_m is not None:
                last_distance = math.hypot(x - cell.x_last, y - cell.y_last)
                if (t - cell.t_last) * last_distance > limit_s_m:
                    continue
            if distance < best_distance:
                best, best_distance = cell, distance

        # (v) A new cell when there is no candidate.
        if best is None:
            best = _Cell(next_label, params.inertia)
            next_label += 1
            open_cells.append(best)
            sizes.append(0)

        # (vi) Add the flash and move the centre.
        best.add(t, x, y)
        sizes[best.label - first_label] = best.n
        label[i] = best.label
        sequence[i] = best.n
        centre_x[i] = best.centre_x
        centre_y[i] = best.centre_y

    if progress is not None:
        progress(total, total)

    kept_labels = np.array(
        [first_label + k for k, n in enumerate(sizes) if n >= params.min_flashes], dtype=np.int64
    )
    for array in (label, sequence, centre_x, centre_y, kept_labels):
        array.setflags(write=False)
    return CellsearchResult(
        label=label,
        sequence=sequence,
        centre_x=centre_x,
        centre_y=centre_y,
        kept_labels=kept_labels,
        summary=_summary(sizes, params.min_flashes, total, discarded),
        open_at_end=len(open_cells),
        next_label=next_label,
    )


def merge_summaries(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Add two summaries of :func:`cellsearch`, e.g. of consecutive chunks.

    Raises
    ------
    ValueError
        If the two summaries do not have the same keys.
    """
    if a.keys() != b.keys():
        raise ValueError("summaries with different keys cannot be merged")
    merged: dict[str, Any] = {}
    for key, value in a.items():
        if isinstance(value, dict):
            merged[key] = merge_summaries(value, b[key])
        else:
            merged[key] = value + b[key]
    return merged

