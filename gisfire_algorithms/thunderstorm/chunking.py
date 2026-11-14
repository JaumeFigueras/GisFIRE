#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Split a time-ordered sequence at quiet gaps, to process it piece by piece.

For Cellsearch with ``gap_s`` equal to the maximum waiting time T the split is
**exact**: a gap longer than T closes every open cell, so no cell can span two
pieces and running the pieces one after the other (carrying the label counter)
gives the same result as one run over everything.
"""

from __future__ import annotations

import numpy as np


def split_at_gaps(t, gap_s: float) -> list[slice]:
    """Cut a sorted time sequence wherever two consecutive times are more than ``gap_s`` apart.

    Parameters
    ----------
    t : array_like of float
        Times, in seconds, non-decreasing.
    gap_s : float
        The gap, in seconds, positive. A gap of exactly ``gap_s`` does not cut.

    Returns
    -------
    list of slice
        Contiguous slices covering the whole sequence, in order; empty for an
        empty sequence.

    Raises
    ------
    ValueError
        If ``gap_s`` is not positive or the times are not sorted.
    """
    if not gap_s > 0:
        raise ValueError("gap_s must be positive")
    times = np.asarray(t, dtype=np.float64)
    if times.size == 0:
        return []
    steps = np.diff(times)
    if np.any(steps < 0):
        raise ValueError("times must be sorted")
    cuts = (np.flatnonzero(steps > gap_s) + 1).tolist()
    bounds = [0, *cuts, len(times)]
    return [slice(start, stop) for start, stop in zip(bounds[:-1], bounds[1:])]
