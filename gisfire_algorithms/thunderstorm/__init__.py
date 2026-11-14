#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grouping of lightning into thunderstorms.

- :mod:`.flashes`: strokes and flashes, the input of the flash-based algorithms.
- :mod:`.cell_statistics`: area (Tuomi & Larjavaara 2005, appendix), lifetime,
  flash rate and density of a group of flashes.
- :mod:`.chunking`: split a time-ordered sequence at quiet gaps.
- :mod:`.cellsearch_tuomi_larjavaara`: Cellsearch (Tuomi & Larjavaara 2005).
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
from .flashes import Flashes
from .flashes import Strokes
from .flashes import discard_by_error
from .flashes import strokes_to_flashes

__all__ = [
    "CELLSEARCH_ALGORITHM",
    "CellsearchCancelled",
    "CellsearchParameters",
    "CellsearchResult",
    "Flashes",
    "Strokes",
    "cell_area_km2",
    "cellsearch",
    "density_per_100km2",
    "discard_by_error",
    "flash_rate_per_min",
    "lifetime_min",
    "merge_summaries",
    "split_at_gaps",
    "strokes_to_flashes",
]
