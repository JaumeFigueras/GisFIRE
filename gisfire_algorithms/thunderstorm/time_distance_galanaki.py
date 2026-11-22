#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Time-distance clustering: grouping of lightning flashes into thunderstorms.

E. Galanaki, K. Lagouvardos, V. Kotroni, E. Flaounas and A. Argiriou,
*Thunderstorm climatology in the Mediterranean using cloud-to-ground lightning
observations*, Atmospheric Research **207** (2018) 136–144,
doi:10.1016/j.atmosres.2018.03.004, section 2.2.

The article clusters in three steps:

1. a flash not yet in a cluster is the "lightning core" of a new cluster;
2. every flash within a distance D **and** a time difference T of it joins the
   cluster; this is repeated for every flash that joins, until no flash is left
   to join;
3. the cluster takes the next sequential number.

Both limits are inclusive, the distance is Euclidean in the projected CRS and
the time difference goes both ways, so a flash can bring in an earlier one. The
clusters do not depend on which flash step 1 takes: they are the groups of
flashes linked by chains of pairs within D and T. The flashes are taken in time
order, so the labels follow each cluster's first flash.

The article uses D = 0.1° ("about 10 km") and T = 16 min, sets no minimum size
and filters no flash by its location error. Clusters with fewer than N_min
flashes (by default 1: every cluster) are not *kept*; they are counted in the
summary only.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from .cellsearch_tuomi_larjavaara import _integer
from .cellsearch_tuomi_larjavaara import _positive_float
from .flashes import Flashes

#: The value of ``thunderstorm_experiment.algorithm`` for this algorithm.
ALGORITHM = "TIME_DISTANCE_GALANAKI_2018"


@dataclass(frozen=True)
class TimeDistanceParameters:
    """The parameters of a time-distance run.

    Attributes
    ----------
    max_distance_km : float
        D, the largest distance between two linked flashes, in km. Default 10.
    max_time_difference_min : float
        T, the largest time difference between two linked flashes, in
        minutes. Default 16.
    min_flashes : int
        N_min: clusters with fewer flashes are not kept. Default 1, every
        cluster, as in the article.
    srid : int
        The EPSG code of the projected CRS (in metres) the coordinates are in.
        Default 25831. The core only records it; the adapters project.

    Raises
    ------
    ValueError
        If a value has the wrong type or is out of range.
    """

    max_distance_km: float = 10.0
    max_time_difference_min: float = 16.0
    min_flashes: int = 1
    srid: int = 25831

    def __post_init__(self) -> None:
        normalised = {
            "max_distance_km": _positive_float("max_distance_km", self.max_distance_km),
            "max_time_difference_min": _positive_float("max_time_difference_min",
                                                       self.max_time_difference_min),
            "min_flashes": _integer("min_flashes", self.min_flashes, 1),
            "srid": _integer("srid", self.srid, 1),
        }
        for name, value in normalised.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        """Every parameter, defaults included."""
        return asdict(self)


@dataclass(frozen=True, eq=False)
class TimeDistanceResult:
    """The outcome of :func:`time_distance`.

    Attributes
    ----------
    label : numpy.ndarray of int64
        For each input flash, its cluster's label, sequential from
        ``first_label`` in the order of the clusters' first flashes.
    kept_labels : numpy.ndarray of int64
        The labels of the clusters with at least ``min_flashes`` flashes,
        sorted.
    summary : dict
        ``flashes_total``, ``flashes_kept`` (in kept clusters), ``cells_total``
        and ``cells_kept``.
    next_label : int
        The first label for a following run, so labels stay unique when the
        input is processed in chunks.
    wall_time_s, cpu_time_s : float
        The computation time of the call, in seconds of wall-clock time
        (``time.perf_counter``) and of CPU time (``time.process_time``).
    """

    label: np.ndarray
    kept_labels: np.ndarray
    summary: dict[str, Any]
    next_label: int
    wall_time_s: float
    cpu_time_s: float

    def kept_flash_mask(self) -> np.ndarray:
        """``True`` for the flashes that belong to a kept cluster."""
        return np.isin(self.label, self.kept_labels)


def time_distance(flashes: Flashes, params: TimeDistanceParameters, *,
                  first_label: int = 1) -> TimeDistanceResult:
    """Group time-ordered flashes into clusters (Galanaki et al. 2018).

    Parameters
    ----------
    flashes : Flashes
        The flashes, in time order, with coordinates in metres of a projected
        CRS.
    params : TimeDistanceParameters
        The parameters of the run.
    first_label : int, optional
        The label of the first cluster (default 1). Pass the previous chunk's
        ``next_label`` to keep labels unique across chunks.

    Raises
    ------
    ValueError
        If ``first_label`` is not an integer of at least 1.
    """
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    first_label = _integer("first_label", first_label, 1)
    distance_m = params.max_distance_km * 1000.0
    difference_s = params.max_time_difference_min * 60.0
    t, x, y = flashes.t, flashes.x, flashes.y

    # The flashes within T of each flash: the times are sorted.
    first = np.searchsorted(t, t - difference_s, side="left")
    last = np.searchsorted(t, t + difference_s, side="right")
    label = np.full(len(t), -1, dtype=np.int64)
    next_label = first_label
    for core in range(len(t)):
        if label[core] >= 0:
            continue
        label[core] = next_label
        pending = [core]
        while pending:
            i = pending.pop()
            a, b = first[i], last[i]
            joining = a + np.flatnonzero(
                (label[a:b] < 0) & (np.hypot(x[a:b] - x[i], y[a:b] - y[i]) <= distance_m))
            label[joining] = next_label
            pending.extend(joining.tolist())
        next_label += 1

    sizes = np.bincount(label - first_label, minlength=next_label - first_label)
    kept = sizes >= params.min_flashes
    kept_labels = first_label + np.flatnonzero(kept)
    label.setflags(write=False)
    kept_labels.setflags(write=False)
    summary = {
        "flashes_total": len(t),
        "flashes_kept": int(sizes[kept].sum()),
        "cells_total": len(sizes),
        "cells_kept": len(kept_labels),
    }
    return TimeDistanceResult(
        label=label,
        kept_labels=kept_labels,
        summary=summary,
        next_label=next_label,
        wall_time_s=time.perf_counter() - wall_start,
        cpu_time_s=time.process_time() - cpu_start,
    )
