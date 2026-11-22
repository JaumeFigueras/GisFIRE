#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grouping of lightning into thunderstorms.

- :mod:`.flashes`: strokes and flashes, the input of the flash-based algorithms.
- :mod:`.flash_grouping`: strokes grouped into flashes (NLDN rule), for networks
  that publish strokes only.
- :mod:`.cell_statistics`: area (Tuomi & Larjavaara 2005, appendix), lifetime,
  flash rate and density of a group of flashes.
- :mod:`.chunking`: split a time-ordered sequence at quiet gaps.
- :mod:`.cellsearch_tuomi_larjavaara`: Cellsearch (Tuomi & Larjavaara 2005).
- :mod:`.time_distance_galanaki`: time-distance clustering (Galanaki et al. 2018).
"""

from .cell_statistics import cell_area_km2
from .cell_statistics import density_per_100km2
from .cell_statistics import flash_rate_per_min
from .cell_statistics import lifetime_min
from .cellsearch_tuomi_larjavaara import ALGORITHM as CELLSEARCH_ALGORITHM
from .cellsearch_tuomi_larjavaara import CellsearchCancelled
from .cellsearch_tuomi_larjavaara import CellsearchParameters
from .cellsearch_tuomi_larjavaara import CellsearchResult
from .cellsearch_tuomi_larjavaara import cellsearch
from .cellsearch_tuomi_larjavaara import merge_summaries
from .chunking import split_at_gaps
from .flash_grouping import FlashGroupingParameters
from .flash_grouping import group_strokes
from .flashes import Flashes
from .flashes import Strokes
from .flashes import discard_by_error
from .flashes import strokes_to_flashes
from .time_distance_galanaki import ALGORITHM as TIME_DISTANCE_ALGORITHM
from .time_distance_galanaki import TimeDistanceParameters
from .time_distance_galanaki import TimeDistanceResult
from .time_distance_galanaki import time_distance

__all__ = [
    "CELLSEARCH_ALGORITHM",
    "CellsearchCancelled",
    "CellsearchParameters",
    "CellsearchResult",
    "FlashGroupingParameters",
    "Flashes",
    "Strokes",
    "TIME_DISTANCE_ALGORITHM",
    "TimeDistanceParameters",
    "TimeDistanceResult",
    "cell_area_km2",
    "cellsearch",
    "density_per_100km2",
    "discard_by_error",
    "flash_rate_per_min",
    "group_strokes",
    "lifetime_min",
    "merge_summaries",
    "split_at_gaps",
    "strokes_to_flashes",
    "time_distance",
]
