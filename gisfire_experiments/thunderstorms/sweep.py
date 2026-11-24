#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensitivity and time analyses of the thunderstorm algorithms over a grid of parameters.

::

    python3 -m gisfire_experiments.thunderstorms.sweep \\
        --sensitivity --provider FMI --from 2018-07-01 --to 2018-08-01
    python3 -m gisfire_experiments.thunderstorms.sweep --algorithm time_distance_galanaki \\
        --time --iterations 17 --provider FMI --from 2018-07-01 --to 2018-08-01
    python3 -m gisfire_experiments.thunderstorms.sweep --algorithm time_distance_galanaki \\
        --sensitivity --provider FMI --periods fmi_2018_extract.csv
    python3 -m gisfire_experiments.thunderstorms.sweep --algorithm time_distance_galanaki \\
        --sensitivity --defaults --provider FMI --periods fmi_2018_extract.csv
    python3 -m gisfire_experiments.thunderstorms.sweep --algorithm time_distance_galanaki \\
        --sensitivity --gap --provider FMI --periods fmi_2018_extract.csv
    python3 -m gisfire_experiments.thunderstorms.sweep --algorithm time_distance_galanaki \\
        --sensitivity --provider FMI --periods fmi_2018_extract.csv \\
        --d 2 4 6 8 10 12 14 16 20 --t 2 4 6 8 10 12 15 20 30

``--algorithm`` chooses the algorithm, by its name in the thunderstorm builder:
Cellsearch (``cellsearch_tuomi_larjavaara``, the default) or the time-distance
clustering (``time_distance_galanaki``). Both analyses run its grid of
parameters (below) over the period; one of ``--sensitivity`` and ``--time`` is
required:

* ``--sensitivity`` stores every combination in the database, through the
  thunderstorm builder, and writes the statistics of its thunderstorms (see
  `Sensitivity analysis`_). With ``--gap`` it also runs every combination on
  copies of the period with its flashes' times shuffled (see `Shuffled runs`_).
* ``--time`` writes nothing to the database: it reads the strokes once and
  times the algorithm's own function (``cellsearch()`` or ``time_distance()``)
  on every combination ``--iterations`` times (default 10), and writes the time
  statistics (see `Time analysis`_).

The grids
---------

Each parameter swept has its own list of values below (:data:`GRIDS`), the
last one changing fastest:

* Cellsearch: R, T, I and C, 6 × 6 × 5 × 6 = 1,080 combinations.
* Time-distance: D and T, 6 × 6 = 36 combinations, with N_min fixed at 10
  (:data:`FIXED`), Cellsearch's default, so that the statistics of both
  algorithms mean the same: with the algorithm's own default of 1, every flash
  would be in a thunderstorm.

The other parameters keep their defaults (Cellsearch's E_max and N_min); the
CRS is the provider's. Only cloud-to-ground strokes are clustered, the
builder's default, as in both articles.

Values can be added to the lists from the command line, with one flag per
symbol in lower case, each followed by its values: ``--d`` and ``--t`` for the
time-distance clustering, ``--r``, ``--t``, ``--i`` and ``--c`` for Cellsearch
(``off`` is C off), for example ``--d 2 4 6 --t 2 4``. Each list becomes its
values and the flag's, sorted ascending (C off first) without repeats
(:func:`grid_lists`), and the grid every combination of them, the new values
with the old ones included: still one complete grid, as the Sobol indices
need. A combination already stored is not run again, so adding values runs
only the new combinations. The lists are logged before the runs, ``Grid: D 2,
4, 5, … 30 km; T 2, 4, 5, … 60 min: 143 combinations``. The flags are not
remembered: each run writes the sensitivity file of its own grid, so a run
without them writes the lists' grid alone. They do not go with ``--defaults``.

``--defaults`` runs one combination instead of the grid: the algorithm's
defaults, its recommended values, with the :data:`FIXED` ones (Cellsearch: R
15 km, T 15 min, I 20, C off, N_min 10; time-distance: D 10 km, T 16 min, N_min
10). Its files are named with ``_defaults`` after the algorithm, so they never
take the place of the grid's (see :func:`csv_filename`).

Sensitivity analysis
--------------------

Every combination of the lists is one run of the thunderstorm builder
(:mod:`src.apps.thunderstorms.build_thunderstorms`) over the period, stored as
one thunderstorm experiment. A combination already stored for the period, from
an earlier run of this script, is not run again, so an interrupted analysis
goes on where it stopped. A run that fails stops the analysis; it stays stored
as ``failed``, and is reported, until it is deleted.

The runs keep only the thunderstorms with a zone flash, the builder's default
(rule 2 of :doc:`/algorithms/thunderstorm_rules`): they cluster the whole
network's strokes and store the storms that touch the network's zone, its
nominal region plus 50 km (:mod:`src.apps.thunderstorms.zones`).

Each combination is logged with the progress of the whole analysis,
``Experiment 34 of 350 (episode 1 of 10, D 30 km, T 60 min)``: the total is
the combinations times the episodes with ``--periods`` (the combinations
alone otherwise), and a combination already stored counts too, as ``...:
already stored as experiment 120 (complete), skipped``. Each run's computation
time (wall-clock and CPU seconds of the algorithm alone, from the builder) is
logged after it; it is not stored yet.

At the end the experiment ids of all the combinations are read back from the
database, and the complete ones are written to a CSV file in ``--output-dir``,
named after the algorithm, the provider and the period (see
:func:`csv_filename`): one row per experiment, with its id, the
parameters swept (C off is an empty cell) and its statistics.

Several periods
---------------

``--periods FILE`` takes the place of ``--from`` and ``--to`` (``--sensitivity``
only): ``FILE`` is an episodes study's file
(:mod:`gisfire_experiments.network_lightning_study.episodes`) or an extract of it
with its header, of which the ``episode``, ``start`` and ``end`` columns are read.
The grid is run for each episode in turn, from :data:`PERIOD_MARGIN` (60 min)
before its ``start`` to as much after its ``end`` (its last zone flash, so it is
inside), each run being an experiment of its own: an interrupted analysis goes
on where it stopped, and a failed run stops it. The statistics are those above,
over each run, and go to one CSV file, named after the algorithm, the provider
and the episodes file (see
:func:`periods_csv_filename`): one row per episode and experiment, with the
episode's ``episode``, ``start`` and ``end`` (as in the file) before the
experiment's columns. The margins hold no zone flash (an episode is ringed by
G with none), so an episode's ``flashes_clustered`` plus
``flashes_discarded_error`` is the episodes file's ``flashes``. Two episodes less
than two margins apart would share the strokes in between; with the episodes of
a G of a few hours they cannot.

Statistics
----------

They follow rule 2 of :doc:`/algorithms/thunderstorm_rules`. They are counted
in **flashes**, the units both algorithms cluster, and in **zone flashes**: a
flash with any of its strokes within 50 km of the network's nominal region. A
thunderstorm counts when it has a zone flash; its **time** comes from all its
flashes, and everything else from its zone flashes only.

* ``thunderstorms``: how many thunderstorms (cells of at least N_min flashes,
  with a zone flash).
* ``flashes_discarded_error``: zone flashes discarded before clustering, their
  location error being E_max or more. They are in no other column. Always 0
  for the time-distance clustering, which discards none.
* ``flashes_clustered``: the zone flashes clustered, after E_max.
* ``flashes_isolated``, ``isolated_pct``: the clustered zone flashes in no
  thunderstorm (in cells smaller than N_min), and their share of
  ``flashes_clustered``.
* ``density_median_per_100km2``: the median over the thunderstorms of
  ``100 · zone flashes / area``, the area being that of the zone flashes'
  concave hull (with the builder's hull settings), for both algorithms. It is
  not the stored ``thunderstorm.area``, which is the whole storm's (for
  Cellsearch its article's ``12·√det Σ``).
* ``diameter_median_km``, ``diameter_p90_km``: the median and the 90th
  percentile over the thunderstorms of the diameter of the circle of the same
  area, ``2·√(area / π)``. The percentile is Hyndman & Fan's (1996) type 8,
  approximately median-unbiased whatever the distribution
  (``numpy.percentile(..., method="median_unbiased")``); Hyndman, R. J. & Fan,
  Y. (1996), Sample quantiles in statistical packages, *The American
  Statistician* 50(4), 361–365.
* ``duration_median_min``: the median over the thunderstorms of the time from
  their first flash to their last, all of them, in minutes.

A thunderstorm's flashes are its linked strokes that represent a flash: the
period's strokes are read once, as the builder reads and groups them, so the
flashes are the points the algorithm clustered, and the duration runs from the
first representative stroke to the last. Whether a flash is a zone flash is
tested on all its strokes, with the zone of :mod:`src.apps.thunderstorms.zones`.

A thunderstorm with no area (fewer than three zone flashes, or all on a line)
counts in ``thunderstorms`` and the duration, not in the density or the
diameter. A statistic with no thunderstorm to take it over is an empty cell.

Shuffled runs
-------------

``--gap`` (``--sensitivity`` only) gathers the data of a gap statistic
(Tibshirani, R., Walther, G. & Hastie, T. (2001), Estimating the number of
clusters in a data set via the gap statistic, *Journal of the Royal Statistical
Society: Series B* 63(2), 411–423), which compares the real runs with runs on
data that hold no storms. After the normal runs of a period (of each episode,
with ``--periods``), every combination is run again on ``--shuffles`` copies of
it (default 30) whose flashes' times are shuffled. Nothing more is stored: the
shuffled runs are made in memory, and the real runs, their statistics and their
file are what they are without ``--gap``.

A shuffle (:func:`shuffle_times`) takes every flash the period's run reads (the
whole network's, margins included), in the builder's order (time, then
representative stroke), and gives each one another one's time, a permutation of
them (:func:`permutation`, a Fisher–Yates shuffle); its strokes move with it.
Places, errors and flashes stay: where the lightning falls and how many flashes
come each minute are kept, and only which place goes with which time is broken.
Rules 1 and 2 of :doc:`/algorithms/thunderstorm_rules` hold as for the real
runs: the zone depends on places only.

The permutation is driven by Park & Miller's (1988) "minimal standard"
generator, ``Z ← 16807·Z mod (2³¹ − 1)``, written here, with no library, so
that a seed gives the same shuffle whatever the versions installed. A period's
first shuffle starts at ``--seed`` (default 24061117, from 1 to 2³¹ − 2), and
each next one where the last stopped: with this generator consecutive seeds
would give related shuffles. Every period starts again from ``--seed``, so its
rows do not depend on the other periods run. Each shuffle is made once, and
every combination is run on it: they all have the same shuffles. Each is logged,
``Shuffle 2 of 30 (episode 1 of 10)``.

A shuffled run is the builder's run over the whole period at once (exact: the
builder cuts its pieces at gaps longer than T only), and its statistics are
those of `Sensitivity analysis`_, counted in memory (:func:`memory_storms`) as
they are for a stored run. The area is the zone flashes' concave hull with
shapely, where the real runs' is PostGIS's ``ST_ConcaveHull``: both are GEOS's,
and agree when the two use the same GEOS version. ``isolated_pct`` does not
depend on it.

The rows go to a second CSV file, named as the sensitivity's with ``_gap`` after
the provider (see :func:`periods_csv_filename` and :func:`csv_filename`). It is
written to ``<name>.part``, episode by episode (a grid's shuffled rows are too
many to keep until the end), and takes the place of ``<name>`` when the run
ends, so a run that fails leaves ``<name>`` as it was. For each period, its real
rows (the sensitivity file's), then every combination on the first shuffle, on
the second, and so on. Its columns are, after the episode's ``episode``,
``start`` and ``end`` with ``--periods``:

* ``run``: ``real`` or ``shuffled``;
* ``seed``: where the shuffle started (empty on a real row); with the period's
  strokes it repeats the shuffle;
* ``flashes``: the period's zone flashes (``flashes_clustered`` plus
  ``flashes_discarded_error``, the same on every row of the period);
* ``experiment_id``: the stored experiment, on a real row only;
* the parameters swept and the statistics, as in the sensitivity file.

A gap file already there, from an earlier run, is not run again: what it holds
is copied, and only what it lacks is run. This is how values added to the grid
(see `The grids`_) cost only their own runs.

* Before any run it is checked (:func:`gap_file_blocks`): its columns must be
  this run's, and each of its pairs must have ``--shuffles`` shuffled rows, the
  first from ``--seed``. Otherwise the sweep stops: give the same values, or
  delete the file to start again.
* For each period, a combination with shuffled rows in it is copied, and the
  others are run on the same shuffles. An old row is copied only from the seed
  of its shuffle in this run; another seed means that the period's flashes
  changed since the file was written, and the sweep stops. When the file holds
  every combination of a period, its strokes are not even read.
* Its pairs out of the grid are kept, after the grid's pairs in each block (the
  real rows, then each shuffle), and its episodes out of the periods file after
  the periods file's episodes, as they were.
* It is read one episode at a time (:func:`gap_file_blocks` says where each
  one's lines are), so it is never held whole in memory.
* At the end it becomes ``<name>.old``, the copy of what there was, and the new
  file takes its name. With the same grid and some combinations more, the new
  file is the one a run of them all from scratch would write.

The gap itself is not computed here.

Time analysis
-------------

The strokes of the period are read once, in a read-only transaction, with the
builder's reader (ground strokes, the provider's CRS), and grouped into flashes
once: the same flashes the builder clusters. Then the algorithm's own function
runs over them, in memory, for every combination, and its own computation time
is taken (``wall_time_s`` and ``cpu_time_s`` of its result: the clustering
alone, not the reading nor the flashes). Nothing is written to the database.

The runs go round the grid: a first round warms up and is left out of
everything; then ``--iterations`` timed rounds, every combination once in each,
so that a change in the load of the machine spreads over all the combinations
instead of falling on a few. Two CSV files are written at the end, named as the
sensitivity's with ``_times`` or ``_times_runs`` after the algorithm:

* ``..._times_...``: one row per combination, with the parameters swept,
  ``iterations``, the minimum, mean, median, sample standard deviation and
  maximum of the wall-clock seconds (``wall_min_s``, ``wall_mean_s``,
  ``wall_median_s``, ``wall_std_s``, ``wall_max_s``; the standard deviation
  needs two iterations), the same of the CPU seconds (``cpu_...``), and
  ``host``, the machine they were measured on;
* ``..._times_runs_...``: every timed run, one row each, in the order they ran
  (round by round), with the parameters swept, ``iteration`` (from 1),
  ``wall_s``, ``cpu_s`` and ``host``.

Database settings come from the environment (``.env``, see
:mod:`src.settings`); every one of them can be overridden with a command-line
argument.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import itertools
import logging
import math
import os
import platform
import statistics
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import Flashes
from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import cellsearch
from gisfire_algorithms.thunderstorm import discard_by_error
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from gisfire_algorithms.thunderstorm import time_distance
from src.apps.imports import common
from src.apps.thunderstorms import writers
from src.apps.thunderstorms.build_thunderstorms import ALGORITHMS
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT
from src.apps.thunderstorms.build_thunderstorms import TABLES
from src.apps.thunderstorms.build_thunderstorms import build_thunderstorms
from src.apps.thunderstorms.build_thunderstorms import experiment_configuration
from src.apps.thunderstorms.build_thunderstorms import parse_instant
from src.apps.thunderstorms.build_thunderstorms import provider_id
from src.apps.thunderstorms.readers import READERS
from src.apps.thunderstorms.readers import strokes_from_rows
from src.apps.thunderstorms.zones import in_zone
from src.apps.thunderstorms.zones import read_region
from src.apps.thunderstorms.zones import zone_stroke_counts
from src.data_model.thunderstorm import DEFAULT_HULL_PARAMETERS

#: The algorithm when ``--algorithm`` is not given, by its name in the builder's ``ALGORITHMS``.
DEFAULT_ALGORITHM = "cellsearch_tuomi_larjavaara"

#: R, the radius of attraction, in km.
ATTRACTION_RADII_KM = [5, 10, 15, 20, 25, 30]

#: T, the maximum waiting time, in minutes.
MAX_WAITING_TIMES_MIN = [5, 10, 15, 20, 30, 60]

#: I, the inertia: how many of a cell's latest flashes its centre is the mean of.
INERTIAS = [10, 20, 30, 40, 50]

#: C, the time-distance limit, in min·km; ``None`` turns the condition off.
TIME_DISTANCE_LIMITS_MIN_KM = [None, 10, 20, 40, 80, 160]

#: D, the time-distance clustering's largest distance between linked flashes, in km.
MAX_DISTANCES_KM = [5, 10, 15, 20, 25, 30]

#: T, the time-distance clustering's largest time difference between linked flashes, in minutes.
MAX_TIME_DIFFERENCES_MIN = [5, 10, 15, 20, 30, 60]

#: The parameters swept, by algorithm: for each field, its symbol and unit in the
#: log and its values. The grid is every combination, the last field changing fastest.
GRIDS: dict[str, dict[str, tuple[str, str, list[Any]]]] = {
    "cellsearch_tuomi_larjavaara": {
        "attraction_radius_km": ("R", "km", ATTRACTION_RADII_KM),
        "max_waiting_time_min": ("T", "min", MAX_WAITING_TIMES_MIN),
        "inertia": ("I", "", INERTIAS),
        "time_distance_limit_min_km": ("C", "min·km", TIME_DISTANCE_LIMITS_MIN_KM),
    },
    "time_distance_galanaki": {
        "max_distance_km": ("D", "km", MAX_DISTANCES_KM),
        "max_time_difference_min": ("T", "min", MAX_TIME_DIFFERENCES_MIN),
    },
}

#: The parameters fixed in every combination, by algorithm; the others keep their
#: defaults. The time-distance clustering's N_min is Cellsearch's default, 10.
FIXED: dict[str, dict[str, Any]] = {
    "cellsearch_tuomi_larjavaara": {},
    "time_distance_galanaki": {"min_flashes": 10},
}

#: How many timed runs of each combination ``--time`` makes by default.
ITERATIONS = 10

#: How many shuffled copies of each period ``--gap`` runs by default.
SHUFFLES = 30

#: Where ``--gap``'s first shuffle starts by default (see :func:`permutation`).
SEED = 24_061_117

#: How much the run of each episode of ``--periods`` is widened on each side.
PERIOD_MARGIN = datetime.timedelta(minutes=60)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The analysis, the provider, the period and the database settings."""
    parser = argparse.ArgumentParser(
        description="Sensitivity or time analysis of a thunderstorm algorithm over one "
                    "provider's strokes.",
        epilog="The period is half-open, [from, to); an instant with no offset is UTC. "
               "Database settings not given here are read from the environment (.env).",
    )
    analysis = parser.add_mutually_exclusive_group(required=True)
    analysis.add_argument("--sensitivity", action="store_true",
                          help="store every combination in the database and write the "
                               "statistics of its thunderstorms")
    analysis.add_argument("--time", action="store_true",
                          help="time the algorithm on every combination, writing nothing to "
                               "the database, and write the time statistics")
    parser.add_argument("--algorithm", choices=sorted(GRIDS), default=DEFAULT_ALGORITHM,
                        help=f"the algorithm whose grid to run (default: {DEFAULT_ALGORITHM})")
    parser.add_argument("--defaults", action="store_true",
                        help="run the algorithm's defaults alone (its recommended values, "
                             "with the grid's fixed ones) instead of its grid, into files of "
                             "their own")
    for symbol in sorted({symbol for fields in GRIDS.values() for symbol, _, _ in fields.values()}):
        swept = ", ".join(f"{algorithm}'s {field}" for algorithm, fields in GRIDS.items()
                          for field, (other, _, _) in fields.items() if other == symbol)
        parser.add_argument(f"--{symbol.lower()}", dest=f"grid_{symbol}", type=grid_value,
                            nargs="+", default=None, metavar="VALUE",
                            help=f"values added to the grid's {symbol} ({swept})"
                                 + ("; off turns it off" if symbol == "C" else ""))
    parser.add_argument("--iterations", type=int, default=None, metavar="N",
                        help=f"--time only: the timed runs of each combination, after one "
                             f"warm-up run (default: {ITERATIONS})")
    parser.add_argument("--gap", action="store_true",
                        help="--sensitivity only: also run every combination, in memory, on "
                             "copies of each period with its flashes' times shuffled, and "
                             "write them with the real runs into a second file")
    parser.add_argument("--shuffles", type=int, default=None, metavar="B",
                        help=f"--gap only: the shuffled copies of each period "
                             f"(default: {SHUFFLES})")
    parser.add_argument("--seed", type=int, default=None, metavar="S",
                        help=f"--gap only: where the first shuffle starts, from 1 to 2**31 - 2 "
                             f"(default: {SEED})")
    parser.add_argument("--provider", required=True, choices=sorted(READERS),
                        help="whose strokes to cluster")
    parser.add_argument("--from", dest="start", type=parse_instant,
                        help="first instant of the period (included)")
    parser.add_argument("--to", dest="end", type=parse_instant,
                        help="end of the period (excluded)")
    parser.add_argument("--periods", type=Path, default=None, metavar="FILE",
                        help="--sensitivity only, instead of --from and --to: run every "
                             "episode of FILE (an episodes study's file, or an extract of it), "
                             f"each widened by {PERIOD_MARGIN.seconds // 60} min on each side")
    parser.add_argument("--output-dir", type=Path, default=Path("."),
                        help="where the CSV file goes (default: the current directory)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    common.add_database_arguments(parser)
    args = parser.parse_args(argv)
    if args.periods is not None:
        if args.start is not None or args.end is not None:
            parser.error("--periods replaces --from and --to")
        if args.time:
            parser.error("--periods goes with --sensitivity")
    elif args.start is None or args.end is None:
        parser.error("--from and --to are required, unless --periods is given")
    if args.sensitivity and args.iterations is not None:
        parser.error("--iterations goes with --time")
    if args.time:
        if args.iterations is None:
            args.iterations = ITERATIONS
        elif args.iterations < 1:
            parser.error("--iterations must be at least 1")
    if args.gap:
        if args.time:
            parser.error("--gap goes with --sensitivity")
        args.shuffles = SHUFFLES if args.shuffles is None else args.shuffles
        args.seed = SEED if args.seed is None else args.seed
        if args.shuffles < 1:
            parser.error("--shuffles must be at least 1")
        if not 1 <= args.seed <= GENERATOR_MODULUS - 1:
            parser.error(f"--seed must be from 1 to {GENERATOR_MODULUS - 1}")
    elif args.shuffles is not None or args.seed is not None:
        parser.error("--shuffles and --seed go with --gap")
    args.extra = {}
    for field, (symbol, _, _) in GRIDS[args.algorithm].items():
        values = getattr(args, f"grid_{symbol}", None)
        if values is not None:
            args.extra[field] = values
    symbols = {symbol for symbol, _, _ in GRIDS[args.algorithm].values()}
    for name, values in vars(args).items():
        if name.startswith("grid_") and values is not None and name[5:] not in symbols:
            parser.error(f"--{name[5:].lower()} is not a parameter of {args.algorithm}'s grid")
    if args.extra:
        if args.defaults:
            parser.error("--defaults runs no grid: it takes no grid values")
        try:
            parameter_grid(READERS[args.provider].default_srid, args.algorithm, extra=args.extra)
        except (TypeError, ValueError) as error:
            parser.error(f"a grid value is wrong: {error}")
    return args


def connect(args: argparse.Namespace, logger: logging.Logger) -> tuple[Engine, int]:
    """The engine and the provider's ``data_provider.id``.

    Raises
    ------
    RuntimeError
        If a database setting is missing, a lightning or thunderstorm table is
        not in the database, or the provider's strokes are not imported.
    """
    engine = create_engine(common.database_url(common.resolve_database_settings(args)))
    common.require_tables(engine, TABLES, logger)
    with engine.connect() as connection:
        identifier = provider_id(connection, READERS[args.provider])
    return engine, identifier


def algorithm_of(parameters: Any) -> str:
    """The algorithm these parameters are of, by its name in the builder's ``ALGORITHMS``."""
    return next(key for key, algorithm in ALGORITHMS.items()
                if isinstance(parameters, algorithm.parameters))


def grid_value(text: str) -> int | float | None:
    """A value of a grid flag: ``off`` (C off) is ``None``, a whole number stays an integer."""
    if text == "off":
        return None
    try:
        return int(text)
    except ValueError:
        return float(text)


def grid_lists(algorithm: str, extra: dict[str, list[Any]] | None = None) -> dict[str, list[Any]]:
    """Each parameter swept and its values: its list in :data:`GRIDS` with the ``extra``
    values of its flag added, sorted ascending (C off first), without repeats."""
    extra = extra or {}
    return {field: sorted(set(values) | set(extra.get(field, [])),
                          key=lambda value: (value is not None, value or 0))
            for field, (_, _, values) in GRIDS[algorithm].items()}


def parameter_grid(srid: int, algorithm: str = DEFAULT_ALGORITHM,
                   defaults: bool = False, extra: dict[str, list[Any]] | None = None) -> list[Any]:
    """Every combination of the algorithm's lists (with the ``extra`` values of the grid
    flags, see :func:`grid_lists`), the last one changing fastest; with ``defaults``, the
    algorithm's defaults alone (with the :data:`FIXED` values)."""
    parameters = ALGORITHMS[algorithm].parameters
    if defaults:
        return [parameters(**FIXED[algorithm], srid=srid)]
    lists = grid_lists(algorithm, extra)
    return [parameters(**dict(zip(lists, values)), **FIXED[algorithm], srid=srid)
            for values in itertools.product(*lists.values())]


def describe_grid(algorithm: str, extra: dict[str, list[Any]] | None = None) -> str:
    """The lists swept, e.g. ``D 5, 10 km; T 5, 10 min`` or ``...; C off, 10 min·km``."""
    lists = grid_lists(algorithm, extra)
    return "; ".join(
        f"{symbol} " + ", ".join("off" if value is None else f"{value:g}" for value in lists[field])
        + (f" {unit}" if unit else "")
        for field, (symbol, unit, _) in GRIDS[algorithm].items())


def describe(parameters: Any) -> str:
    """The parameters swept, e.g. ``R 15 km, T 15 min, I 20, C off`` or ``D 10 km, T 16 min``."""
    parts = []
    for field, (symbol, unit, _) in GRIDS[algorithm_of(parameters)].items():
        value = getattr(parameters, field)
        parts.append(f"{symbol} off" if value is None
                     else f"{symbol} {value:g}" + (f" {unit}" if unit else ""))
    return ", ".join(parts)


def stored_experiment(connection: Connection, data_provider_id: int, provider: str,
                      parameters: Any, start: datetime.datetime,
                      end: datetime.datetime) -> tuple[int, str] | None:
    """The ``(id, status)`` of the experiment of this combination and period, if stored."""
    return writers.find_experiment(connection, experiment_configuration(
        data_provider_id, provider, algorithm_of(parameters), parameters, start, end))


def run_grid(engine: Engine, data_provider_id: int, provider: str,
             grid: list[Any], start: datetime.datetime,
             end: datetime.datetime, logger: logging.Logger, done: int = 0,
             total: int | None = None, episode: str | None = None) -> None:
    """Run every combination not stored yet; a failed run raises.

    Each one is logged as ``Experiment n of total (episode, parameters)``: ``done``
    experiments came before this grid (those of the episodes before, with
    ``--periods``), ``total`` is the whole run's (the grid's by default), and
    ``episode`` says which episode this is, if any. A combination already stored
    counts too, so the count reaches the total.
    """
    total = len(grid) if total is None else total
    for number, parameters in enumerate(grid, start=done + 1):
        progress = (f"Experiment {number} of {total} "
                    f"({', '.join(filter(None, (episode, describe(parameters))))})")
        with engine.connect() as connection:
            existing = stored_experiment(connection, data_provider_id, provider, parameters,
                                         start, end)
        if existing is not None:
            logger.info("%s: already stored as experiment %d (%s), skipped", progress, *existing)
            continue
        logger.info("%s", progress)
        try:
            _, wall_time_s, cpu_time_s = build_thunderstorms(
                engine, provider, algorithm_of(parameters), parameters, start, end, logger)
        except Exception as error:
            raise RuntimeError(f"{progress} failed: {error}") from error
        logger.info("%s: computation time %.4f s wall, %.4f s CPU", progress, wall_time_s,
                    cpu_time_s)


def experiment_ids(engine: Engine, data_provider_id: int, provider: str,
                   grid: list[Any], start: datetime.datetime,
                   end: datetime.datetime) -> dict[Any, tuple[int, str] | None]:
    """For every combination, its experiment's ``(id, status)``; ``None`` if not stored."""
    with engine.connect() as connection:
        return {parameters: stored_experiment(connection, data_provider_id, provider, parameters,
                                              start, end)
                for parameters in grid}


@dataclass(frozen=True)
class Period:
    """One episode of ``--periods``: its number and its bounds, as in the file.

    Its run goes from :data:`PERIOD_MARGIN` before ``start`` to as much after
    ``end``.
    """

    episode: str
    start: datetime.datetime
    end: datetime.datetime

    @property
    def run_start(self) -> datetime.datetime:
        return self.start - PERIOD_MARGIN

    @property
    def run_end(self) -> datetime.datetime:
        return self.end + PERIOD_MARGIN


def read_periods(path: Path) -> list[Period]:
    """The episodes of an episodes study's file (or an extract of it, with its header).

    Raises
    ------
    ValueError
        If the file has no ``episode``, ``start`` or ``end`` column, no episode, an
        instant that is not ISO 8601, or an episode that ends before it starts.
    """
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not {"episode", "start", "end"} <= set(reader.fieldnames or ()):
            raise ValueError(f"{path} has no episode, start and end columns: it is not an "
                             f"episodes study's file")
        try:
            periods = [Period(row["episode"], parse_instant(row["start"]), parse_instant(row["end"]))
                       for row in reader]
        except argparse.ArgumentTypeError as error:
            raise ValueError(f"{path}: {error}") from error
    if not periods:
        raise ValueError(f"{path} holds no episode")
    for period in periods:
        if period.end < period.start:
            raise ValueError(f"{path}: episode {period.episode} ends before it starts")
    return periods


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Storm:
    """One stored thunderstorm, as the statistics need it (rule 2 of the thunderstorm rules).

    Attributes
    ----------
    flashes : int
        Its zone flashes; a thunderstorm with none does not count.
    area_km2 : float or None
        The area of its zone flashes' concave hull; ``None`` when undefined.
    duration_min : float
        From its first flash to its last, all of them, in minutes.
    """

    flashes: int
    area_km2: float | None
    duration_min: float


@dataclass(frozen=True)
class FlashCounts:
    """The zone flashes of a run: clustered, and discarded by E_max."""

    clustered: int
    discarded: int


#: Every stored thunderstorm of an experiment: its zone flashes, its duration from
#: all its flashes, and the zone flashes' concave hull.
#: Its flashes are its linked strokes that represent one, staged with their zone
#: flag and their coordinates in ``representative_stroke``.
STORMS_SQL = """
SELECT s.zone_flashes, s.duration_min,
       CASE WHEN GeometryType(s.hull) = 'POLYGON' THEN ST_Area(s.hull) / 1e6 END AS hull_area_km2
FROM (
    SELECT t.id,
           count(*) FILTER (WHERE r.zone) AS zone_flashes,
           EXTRACT(EPOCH FROM max(l.date_time) - min(l.date_time)) / 60.0 AS duration_min,
           ST_ConcaveHull(ST_Collect(ST_SetSRID(ST_MakePoint(r.x, r.y), :srid)
                                     ORDER BY r.id) FILTER (WHERE r.zone),
                          :ratio, :allow_holes) AS hull
    FROM thunderstorm AS t
    JOIN thunderstorm_lightning AS link ON link.thunderstorm_id = t.id
    JOIN representative_stroke AS r ON r.id = link.lightning_id
    JOIN lightning AS l ON l.id = link.lightning_id
    WHERE t.experiment_id = :experiment_id
    GROUP BY t.id
) AS s
ORDER BY s.id
"""


def stored_storms(connection: Connection, experiment_id: int, srid: int) -> list[Storm]:
    """The experiment's thunderstorms; their zone flashes' area is the concave hull's
    (with the builder's hull settings, in ``srid``, the staged points' CRS), for every
    algorithm."""
    rows = connection.execute(text(STORMS_SQL), {
        "experiment_id": experiment_id, "srid": srid,
        "ratio": float(DEFAULT_HULL_PARAMETERS["ratio"]),
        "allow_holes": bool(DEFAULT_HULL_PARAMETERS["allow_holes"])})
    return [Storm(flashes=row.zone_flashes,
                  area_km2=None if row.hull_area_km2 is None else float(row.hull_area_km2),
                  duration_min=float(row.duration_min))
            for row in rows]


def zone_flash_counts(flashes: Flashes, zone: np.ndarray, max_error_km: float | None) -> FlashCounts:
    """The zone flashes (``zone``, one per flash): clustered, and discarded by E_max (with
    none, ``None``, every flash is clustered)."""
    if max_error_km is None:
        kept = np.ones(len(flashes), dtype=bool)
    else:
        kept, _ = discard_by_error(flashes, max_error_km * 1000.0)
    return FlashCounts(clustered=int(np.count_nonzero(zone & kept)),
                       discarded=int(np.count_nonzero(zone & ~kept)))


def thunderstorm_statistics(storms: list[Storm], counts: FlashCounts) -> dict[str, Any]:
    """The statistics of one experiment (see the module's docstring).

    A thunderstorm counts with at least one zone flash. A zone flash is isolated
    when it is clustered and in no thunderstorm.
    """
    kept = [storm for storm in storms if storm.flashes]
    isolated = counts.clustered - sum(storm.flashes for storm in kept)
    with_area = [storm for storm in kept if storm.area_km2]
    diameters = [2.0 * math.sqrt(storm.area_km2 / math.pi) for storm in with_area]
    return {
        "thunderstorms": len(kept),
        "flashes_discarded_error": counts.discarded,
        "flashes_clustered": counts.clustered,
        "flashes_isolated": isolated,
        "isolated_pct": 100.0 * isolated / counts.clustered if counts.clustered else None,
        "density_median_per_100km2": statistics.median(
            100.0 * storm.flashes / storm.area_km2 for storm in with_area) if with_area else None,
        "diameter_median_km": statistics.median(diameters) if diameters else None,
        "diameter_p90_km": float(np.percentile(diameters, 90, method="median_unbiased"))
        if diameters else None,
        "duration_median_min": statistics.median(
            storm.duration_min for storm in kept) if kept else None,
    }


def experiment_statistics(engine: Engine, data_provider_id: int, provider: str,
                          experiments: dict[Any, int], start: datetime.datetime,
                          end: datetime.datetime,
                          logger: logging.Logger) -> dict[Any, dict[str, Any]]:
    """For every experiment, its statistics, by rule 2 of the thunderstorm rules.

    The period's strokes are read once, as the builder reads and groups them: a
    thunderstorm's flashes are its linked strokes that represent one, and its
    zone flashes those with any stroke in the provider's zone.
    """
    if not experiments:
        return {}
    strokes = read_strokes(engine, data_provider_id, provider, start, end)
    flashes = strokes_to_flashes(strokes)
    results = {}
    counts: dict[float | None, FlashCounts] = {}
    with engine.connect() as connection:
        zone = zone_stroke_counts(flashes, in_zone(read_region(connection, provider),
                                                   strokes.x, strokes.y)) > 0
        writers._stage(connection, "representative_stroke",
                       "id integer, zone boolean, x double precision, y double precision",
                       zip(flashes.representative_id.tolist(), zone.tolist(), flashes.x.tolist(),
                           flashes.y.tolist()))
        for parameters, experiment_id in experiments.items():
            error_km = getattr(parameters, "max_location_error_km", None)
            if error_km not in counts:
                counts[error_km] = zone_flash_counts(flashes, zone, error_km)
            storms = stored_storms(connection, experiment_id, parameters.srid)
            results[parameters] = thunderstorm_statistics(storms, counts[error_km])
        connection.rollback()
    logger.info("Statistics of %d experiment(s) computed", len(results))
    return results


# --------------------------------------------------------------------------
# Time analysis
# --------------------------------------------------------------------------

def read_strokes(engine: Engine, data_provider_id: int, provider: str,
                 start: datetime.datetime, end: datetime.datetime) -> Strokes:
    """The strokes of ``[start, end)`` the builder clusters (ground strokes, the
    provider's CRS), read in a read-only transaction."""
    reader = READERS[provider]
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        batches = list(reader.read(connection, data_provider_id, start, end, reader.default_srid))
        connection.rollback()
    if not batches:
        return strokes_from_rows([])
    return Strokes(*(np.concatenate([getattr(batch, name) for batch in batches])
                     for name in ("ids", "flash_keys", "t", "x", "y", "error")))


def read_flashes(engine: Engine, data_provider_id: int, provider: str,
                 start: datetime.datetime, end: datetime.datetime) -> Flashes:
    """The flashes of ``[start, end)`` the builder clusters, read in a read-only transaction."""
    return strokes_to_flashes(read_strokes(engine, data_provider_id, provider, start, end))


def _core(parameters: Any) -> Any:
    """The algorithm's own function: ``cellsearch`` or ``time_distance``."""
    return cellsearch if isinstance(parameters, CellsearchParameters) else time_distance


def time_runs(flashes: Flashes, grid: list[Any], iterations: int,
              logger: logging.Logger) -> dict[Any, list[tuple[float, float]]]:
    """For every combination, the ``(wall, CPU)`` seconds of its ``iterations`` timed runs.

    Round 0 runs every combination once to warm up and is not counted; then
    every round runs every combination once, in the grid's order.
    """
    samples: dict[Any, list[tuple[float, float]]] = {parameters: [] for parameters in grid}
    for iteration in range(iterations + 1):
        for parameters in grid:
            result = _core(parameters)(flashes, parameters)
            if iteration:
                samples[parameters].append((result.wall_time_s, result.cpu_time_s))
        if iteration:
            logger.info("Iteration %d of %d done", iteration, iterations)
        else:
            logger.info("Warm-up round done")
    return samples


def time_statistics(samples: list[tuple[float, float]]) -> dict[str, Any]:
    """The minimum, mean, median, sample standard deviation and maximum of the
    wall and CPU seconds; the standard deviation is ``None`` for one sample."""
    result: dict[str, Any] = {"iterations": len(samples)}
    for clock, seconds in (("wall", [wall for wall, _ in samples]),
                           ("cpu", [cpu for _, cpu in samples])):
        result |= {
            f"{clock}_min_s": min(seconds),
            f"{clock}_mean_s": statistics.fmean(seconds),
            f"{clock}_median_s": statistics.median(seconds),
            f"{clock}_std_s": statistics.stdev(seconds) if len(seconds) > 1 else None,
            f"{clock}_max_s": max(seconds),
        }
    return result


def time_analysis(engine: Engine, data_provider_id: int, args: argparse.Namespace,
                  grid: list[Any], logger: logging.Logger) -> int:
    """Time every combination and write the two CSV files; nothing goes to the database."""
    flashes = read_flashes(engine, data_provider_id, args.provider, args.start, args.end)
    logger.info("%d flash(es) read; timing %s %d time(s) on every combination, after a "
                "warm-up round", len(flashes), args.algorithm, args.iterations)
    samples = time_runs(flashes, grid, args.iterations, logger)
    host = platform.node()
    results = {parameters: {**time_statistics(runs), "host": host}
               for parameters, runs in samples.items()}
    path = args.output_dir / csv_filename(args.provider, args.start, args.end, suffix="times",
                                          algorithm=args.algorithm, defaults=args.defaults)
    runs_path = args.output_dir / csv_filename(args.provider, args.start, args.end,
                                               suffix="times_runs", algorithm=args.algorithm,
                                               defaults=args.defaults)
    try:
        write_time_csv(path, results, algorithm=args.algorithm)
        write_time_runs_csv(runs_path, samples, host, algorithm=args.algorithm)
    except OSError as error:
        logger.error("Cannot write %s: %s", error.filename, error)
        return 1
    logger.info("Wrote %s (%d combinations) and %s (%d runs)", path, len(results), runs_path,
                sum(len(runs) for runs in samples.values()))
    return 0


# --------------------------------------------------------------------------
# Shuffled runs
# --------------------------------------------------------------------------

#: Park & Miller's (1988) "minimal standard" generator, ``Z ← 16807·Z mod (2³¹ − 1)``:
#: its values, and so its seeds, are 1 … 2³¹ − 2. Written here, with no library, so a
#: seed gives the same shuffle whatever the versions installed. Park, S. K. & Miller,
#: K. W. (1988), Random number generators: good ones are hard to find,
#: *Communications of the ACM* 31(10), 1192–1201.
GENERATOR_MULTIPLIER = 16807
GENERATOR_MODULUS = 2**31 - 1


def next_seed(seed: int) -> int:
    """The generator's value after ``seed``."""
    return GENERATOR_MULTIPLIER * seed % GENERATOR_MODULUS


def permutation(n: int, seed: int) -> tuple[np.ndarray, int]:
    """A Fisher–Yates shuffle of ``n`` places driven by the generator from ``seed``.

    From the last place ``i`` down to the second, one value ``Z`` picks the place
    ``j = (Z − 1)·(i + 1) // (2³¹ − 2)``, from 0 to ``i``, and the two are swapped:
    whole numbers only, so every computer gives the same order.

    Returns
    -------
    order : numpy.ndarray
        Place ``k`` takes what was at ``order[k]``.
    seed : int
        The last value drawn (``seed`` itself when ``n`` < 2, which draws none),
        where the next shuffle starts.
    """
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        seed = next_seed(seed)
        j = (seed - 1) * (i + 1) // (GENERATOR_MODULUS - 1)
        order[i], order[j] = order[j], order[i]
    return np.array(order, dtype=np.int64), seed


def shuffle_times(strokes: Strokes, seed: int) -> tuple[Strokes, int]:
    """The strokes with their flashes' times shuffled, and where the generator stopped.

    The flashes are the builder's, in its order (time, then representative id), and
    :func:`permutation` gives each one another flash's time. Its strokes move with
    it, keeping their offsets from its representative stroke, whose time is the new
    one exactly; places, errors and flashes stay. The strokes come back sorted by time,
    then id, as the reader sorts them.
    """
    flashes = strokes_to_flashes(strokes)
    order, seed = permutation(len(flashes), seed)
    flash = flashes.stroke_flash_index
    t = flashes.t[order][flash] + (strokes.t - flashes.t[flash])
    by_time = np.lexsort((strokes.ids, t))
    return Strokes(ids=strokes.ids[by_time], flash_keys=strokes.flash_keys[by_time],
                   t=t[by_time], x=strokes.x[by_time], y=strokes.y[by_time],
                   error=strokes.error[by_time]), seed


def memory_storms(strokes: Strokes, zone_ids: np.ndarray,
                  parameters: Any) -> tuple[list[Storm], FlashCounts]:
    """One run in memory, and its thunderstorms and zone flashes as the statistics need them.

    The algorithm's run is the builder's (``ALGORITHMS``), over all ``strokes`` at
    once; each storm is then what :data:`STORMS_SQL` reads of a stored one. Its flashes
    are its linked strokes that represent one, its zone flashes those with a stroke in
    ``zone_ids`` (the ids of the strokes in the zone), its area their concave hull's
    (shapely, with the builder's hull settings, points in id order as ``ST_Collect``
    takes them) and its duration from all its flashes. A storm with no zone flash is
    returned with none, and :func:`thunderstorm_statistics` leaves it out, as the
    builder's zone filter leaves it unstored.
    """
    piece = ALGORITHMS[algorithm_of(parameters)].run(strokes, parameters, 1)
    flashes = strokes_to_flashes(strokes)
    zone = zone_stroke_counts(flashes, np.isin(strokes.ids, zone_ids)) > 0
    counts = zone_flash_counts(flashes, zone, getattr(parameters, "max_location_error_km", None))
    if not len(piece.cells.link_lightning_id):
        return [], counts
    # Each flash's storm, through the link of its representative stroke.
    links = np.argsort(piece.cells.link_lightning_id)
    linked = piece.cells.link_lightning_id[links]
    place = np.minimum(np.searchsorted(linked, flashes.representative_id), len(linked) - 1)
    in_storm = np.flatnonzero(linked[place] == flashes.representative_id)
    label = piece.cells.link_label[links][place][in_storm]
    # By storm, and within one by representative id, the order ST_Collect takes them in.
    order = np.lexsort((flashes.representative_id[in_storm], label))
    storms = []
    for members in np.split(in_storm[order], np.flatnonzero(np.diff(label[order])) + 1):
        zone_members = members[zone[members]]
        hull = shapely.concave_hull(
            shapely.multipoints(np.column_stack((flashes.x[zone_members], flashes.y[zone_members]))),
            ratio=float(DEFAULT_HULL_PARAMETERS["ratio"]),
            allow_holes=bool(DEFAULT_HULL_PARAMETERS["allow_holes"]))
        storms.append(Storm(
            flashes=len(zone_members),
            area_km2=hull.area / 1e6 if hull.geom_type == "Polygon" and not hull.is_empty else None,
            duration_min=float(flashes.t[members].max() - flashes.t[members].min()) / 60.0))
    return storms, counts


def gap_rows(engine: Engine, data_provider_id: int, args: argparse.Namespace, grid: list[Any],
             start: datetime.datetime, end: datetime.datetime, complete: dict[Any, int],
             results: dict[Any, dict[str, Any]], logger: logging.Logger,
             episode: str | None = None, old: list[list[str]] | None = None) -> list[list[Any]]:
    """``--gap``'s rows of ``[start, end)``, from ``run`` on (see :data:`GAP_COLUMNS`).

    First its real runs, ``complete`` and ``results`` as :func:`sensitivity` returns
    them; then, for each of ``args.shuffles`` shuffles of the period's strokes (the
    first from ``args.seed``, each next one from where the last stopped), every
    combination of ``grid``, run and counted in memory (:func:`memory_storms`). Every
    row carries the period's zone flashes.

    ``old`` holds the period's rows of the gap file already there (from ``run`` on,
    checked by :func:`gap_file_blocks`). A combination with shuffled rows there is
    copied, not run again; when every one is, the strokes are not read. A pair of
    ``old`` not in ``grid`` is kept as it was, after the grid's pairs in each block
    (the real rows, then each shuffle). An old row is copied only from the seed of
    its shuffle in this run: another means that the period's flashes changed
    (``RuntimeError``).
    """
    count = len(GRIDS[args.algorithm])
    pair_of = {parameters: tuple(_parameter_cells(parameters, args.algorithm))
               for parameters in grid}
    old_real: dict[tuple[str, ...], list[str]] = {}
    old_shuffled: dict[tuple[tuple[str, ...], str], list[str]] = {}
    old_seeds: dict[tuple[str, ...], list[str]] = {}
    for row in old or []:
        pair = tuple(row[len(GAP_COLUMNS):len(GAP_COLUMNS) + count])
        seeds = old_seeds.setdefault(pair, [])
        if row[0] == "real":
            old_real[pair] = row
        else:
            old_shuffled[pair, row[1]] = row
            seeds.append(row[1])
    in_grid = set(pair_of.values())
    kept = [pair for pair in old_seeds if pair not in in_grid]
    new = {parameters for parameters in grid if not old_seeds.get(pair_of[parameters])}
    logger.info("Gap file%s: %d combination(s) copied, %d run, %d kept out of the grid",
                f" ({episode})" if episode else "", len(grid) - len(new), len(new), len(kept))

    def copied(pair: tuple[str, ...], seed: Any) -> list[str]:
        if (pair, str(seed)) not in old_shuffled:
            raise RuntimeError(f"The gap file has no shuffle from seed {seed} for "
                               f"{', '.join(pair)}{f' in {episode}' if episode else ''}: the "
                               f"period's flashes changed since it was written; delete it")
        return old_shuffled[pair, str(seed)]

    if new:
        strokes = read_strokes(engine, data_provider_id, args.provider, start, end)
        with engine.connect() as connection:
            region = read_region(connection, args.provider)
            connection.rollback()
        zone_ids = strokes.ids[in_zone(region, strokes.x, strokes.y)]
        flashes: Any = int(np.count_nonzero(zone_stroke_counts(strokes_to_flashes(strokes),
                                                               np.isin(strokes.ids, zone_ids))))
    else:
        flashes = old[0][2]
        # The seeds of the old shuffles, in order: every pair has the same.
        chain = next(seeds for seeds in old_seeds.values() if seeds)
    rows = [["real", "", flashes, *row]
            for row in _experiment_rows(complete, results, args.algorithm)]
    rows += [old_real[pair] for pair in kept if pair in old_real]
    seed: Any = args.seed
    for number in range(1, args.shuffles + 1):
        if new:
            logger.info("Shuffle %d of %d%s", number, args.shuffles,
                        f" ({episode})" if episode else "")
            shuffled, next_seed_ = shuffle_times(strokes, seed)
        else:
            seed = chain[number - 1]
        for parameters in grid:
            if parameters in new:
                values = thunderstorm_statistics(*memory_storms(shuffled, zone_ids, parameters))
                rows.append(["shuffled", seed, flashes, "",
                             *_parameter_cells(parameters, args.algorithm),
                             *(_cell(values[column]) for column in STATISTIC_COLUMNS)])
            else:
                rows.append(copied(pair_of[parameters], seed))
        rows += [copied(pair, seed) for pair in kept if old_seeds[pair]]
        if new:
            seed = next_seed_
    return rows


def _gap_block(path: Path, lines: tuple[int, int]) -> list[list[str]]:
    """The rows of a gap file from its line ``lines[0]`` to ``lines[1]`` (from 1, the
    header's), the lines before them skipped unread (see :func:`gap_file_blocks`)."""
    first, last = lines
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.reader(itertools.islice(file, first - 1, last)))


# --------------------------------------------------------------------------
# The CSV files
# --------------------------------------------------------------------------

def _analysis(algorithm: str, defaults: bool, suffix: str = "") -> str:
    """``time_distance_galanaki``, ``..._defaults``, ``..._times``, ``..._defaults_times``."""
    return "_".join(part for part in (algorithm, "defaults" if defaults else "", suffix) if part)


def csv_filename(provider: str, start: datetime.datetime, end: datetime.datetime,
                 suffix: str = "", algorithm: str = DEFAULT_ALGORITHM,
                 defaults: bool = False, gap: bool = False) -> str:
    """``cellsearch_tuomi_larjavaara_FMI_20180703T000000Z_20180704T000000Z.csv``.

    The algorithm (followed by ``_defaults`` for ``--defaults``, and by ``_`` and
    ``suffix`` if given: ``times`` and ``times_runs`` for the time analysis), the
    provider as given to ``--provider`` (followed by ``_gap`` for ``--gap``'s file),
    and the period ``[start, end)`` in UTC, in the ISO 8601 basic format (no colons).
    """
    def instant(value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return (f"{_analysis(algorithm, defaults, suffix)}_{provider}_{'gap_' if gap else ''}"
            f"{instant(start)}_{instant(end)}.csv")


def periods_csv_filename(provider: str, periods: Path, algorithm: str = DEFAULT_ALGORITHM,
                         defaults: bool = False, gap: bool = False) -> str:
    """``time_distance_galanaki_FMI_fmi_2018.csv``: as :func:`csv_filename`, with the
    episodes file's name (without its extension) in place of the period."""
    return f"{_analysis(algorithm, defaults)}_{provider}_{'gap_' if gap else ''}{periods.stem}.csv"


#: The statistics, as the CSV file's columns (see the module's docstring).
STATISTIC_COLUMNS = ["thunderstorms", "flashes_discarded_error", "flashes_clustered",
                     "flashes_isolated", "isolated_pct", "density_median_per_100km2",
                     "diameter_median_km", "diameter_p90_km", "duration_median_min"]

#: ``--gap``'s file's columns before the parameters (after the episode's, with
#: ``--periods``): ``real`` or ``shuffled``, the shuffle's seed (empty on a real
#: row), the period's zone flashes, and the stored experiment (on a real row only).
GAP_COLUMNS = ["run", "seed", "flashes", "experiment_id"]

#: The time statistics, as the time analysis' summary file's columns.
TIME_COLUMNS = ["iterations",
                *(f"{clock}_{statistic}_s" for clock in ("wall", "cpu")
                  for statistic in ("min", "mean", "median", "std", "max")),
                "host"]

#: The time analysis' runs file's columns after the parameters swept: one timed run.
TIME_RUN_COLUMNS = ["iteration", "wall_s", "cpu_s", "host"]


def _cell(value: Any, decimals: int = 4) -> str:
    """A CSV cell: empty for ``None``, a float to ``decimals`` decimals, anything else as is."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _parameter_cells(parameters: Any, algorithm: str) -> list[str]:
    """The parameters swept, as cells, in the algorithm's columns; C off is an empty cell."""
    cells = []
    for field in GRIDS[algorithm]:
        value = getattr(parameters, field)
        cells.append("" if value is None else f"{value:g}")
    return cells


def _write(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def _append(path: Path, rows: list[list[Any]]) -> None:
    with path.open("a", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)


def _experiment_rows(experiments: dict[Any, int], results: dict[Any, dict[str, Any]],
                     algorithm: str) -> list[list[Any]]:
    """One row per experiment, in the order given: its id, the parameters swept, its statistics."""
    return [[experiment_id, *_parameter_cells(parameters, algorithm),
             *(_cell(results[parameters][column]) for column in STATISTIC_COLUMNS)]
            for parameters, experiment_id in experiments.items()]


def write_csv(path: Path, experiments: dict[Any, int], results: dict[Any, dict[str, Any]],
              algorithm: str = DEFAULT_ALGORITHM) -> None:
    """The sensitivity analysis: one row per experiment, in the order given."""
    _write(path, ["experiment_id", *GRIDS[algorithm], *STATISTIC_COLUMNS],
           _experiment_rows(experiments, results, algorithm))


def write_periods_csv(path: Path,
                      periods: list[tuple[Period, dict[Any, int], dict[Any, dict[str, Any]]]],
                      algorithm: str = DEFAULT_ALGORITHM) -> None:
    """The sensitivity analysis of ``--periods``: for each episode, in the order given, one
    row per experiment, led by the episode's number and its bounds (as in the file)."""
    _write(path, ["episode", "start", "end", "experiment_id", *GRIDS[algorithm],
                  *STATISTIC_COLUMNS],
           [[period.episode, period.start.isoformat(), period.end.isoformat(), *row]
            for period, experiments, results in periods
            for row in _experiment_rows(experiments, results, algorithm)])


def write_time_csv(path: Path, results: dict[Any, dict[str, Any]],
                   algorithm: str = DEFAULT_ALGORITHM) -> None:
    """The time analysis' summary: one row per combination, in the order given;
    seconds to 6 decimals."""
    _write(path, [*GRIDS[algorithm], *TIME_COLUMNS], [
        [*_parameter_cells(parameters, algorithm),
         *(_cell(results[parameters][column], decimals=6) for column in TIME_COLUMNS)]
        for parameters in results])


def gap_file_columns(algorithm: str, periods: bool) -> list[str]:
    """``--gap``'s file's columns: the episode's with ``--periods``, :data:`GAP_COLUMNS`,
    the parameters swept and the statistics."""
    return [*(["episode", "start", "end"] if periods else []), *GAP_COLUMNS, *GRIDS[algorithm],
            *STATISTIC_COLUMNS]


def gap_file_blocks(path: Path, columns: list[str], shuffles: int,
                    seed: int) -> dict[str | None, tuple[int, int]]:
    """Check a gap file already there against this run, and where each episode's rows are.

    Read once, keeping per episode and pair only how many shuffled rows it has and the
    seed of the first. Every pair must have ``shuffles`` of them, the first from
    ``seed``.

    Returns
    -------
    dict
        For each episode (``None`` in a file with no episode column), in the file's
        order, its first and last line (from 1, the header's).

    Raises
    ------
    ValueError
        If the columns are not ``columns``, an episode's rows are not together, a row is
        neither ``real`` nor ``shuffled``, or a pair's shuffled rows are not this run's.
    """
    run = columns.index("run")
    parameters = slice(run + len(GAP_COLUMNS), len(columns) - len(STATISTIC_COLUMNS))
    blocks: dict[str | None, list[int]] = {}
    shuffled: dict[tuple[str | None, tuple[str, ...]], list[Any]] = {}
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        if next(reader, None) != columns:
            raise ValueError(f"{path}: its columns are not those of this run's gap file (another "
                             f"algorithm's, or not a gap file)")
        current: Any = object()
        for row in reader:
            episode = row[0] if run else None
            if episode != current:
                if episode in blocks:
                    raise ValueError(f"{path}: episode {episode}'s rows are not together")
                blocks[episode] = [reader.line_num, reader.line_num]
                current = episode
            blocks[episode][1] = reader.line_num
            if row[run] == "shuffled":
                counted = shuffled.setdefault((episode, tuple(row[parameters])), [0, row[run + 1]])
                counted[0] += 1
            elif row[run] != "real":
                raise ValueError(f"{path}, line {reader.line_num}: run {row[run]!r} is neither "
                                 f"real nor shuffled")
    names = columns[parameters]
    for (episode, pair), (count, first) in shuffled.items():
        if count != shuffles or first != str(seed):
            where = ", ".join(f"{name} {value}" for name, value in zip(names, pair))
            raise ValueError(f"{path}: {f'episode {episode}, ' if run else ''}{where} has {count} "
                             f"shuffled row(s) from seed {first}, not {shuffles} from {seed}: give "
                             f"the same --seed and --shuffles, or delete the file")
    return {episode: (first, last) for episode, (first, last) in blocks.items()}


def write_time_runs_csv(path: Path, samples: dict[Any, list[tuple[float, float]]], host: str,
                        algorithm: str = DEFAULT_ALGORITHM) -> None:
    """The time analysis' runs: one row per timed run, in the order they ran (round by
    round, the combinations in the order given); seconds to 6 decimals.

    Every combination has the same number of runs, as :func:`time_runs` makes them.
    """
    iterations = len(next(iter(samples.values()), []))
    _write(path, [*GRIDS[algorithm], *TIME_RUN_COLUMNS], [
        [*_parameter_cells(parameters, algorithm), iteration + 1, _cell(runs[iteration][0], decimals=6),
         _cell(runs[iteration][1], decimals=6), host]
        for iteration in range(iterations)
        for parameters, runs in samples.items()])


def sensitivity(engine: Engine, data_provider_id: int, args: argparse.Namespace, grid: list[Any],
                start: datetime.datetime, end: datetime.datetime, logger: logging.Logger,
                done: int = 0, total: int | None = None, episode: str | None = None
                ) -> tuple[dict[Any, int], dict[Any, dict[str, Any]], bool]:
    """Run the grid over ``[start, end)`` and compute the statistics of its complete runs.

    ``done``, ``total`` and ``episode`` are :func:`run_grid`'s, for the progress.

    Returns
    -------
    complete : dict
        The complete experiments' ids, by combination.
    results : dict
        Their statistics, by combination.
    unfinished : bool
        Whether a combination is not stored, or not complete (each is logged).

    Raises
    ------
    RuntimeError
        If a run fails.
    """
    run_grid(engine, data_provider_id, args.provider, grid, start, end, logger, done, total,
             episode)
    experiments = experiment_ids(engine, data_provider_id, args.provider, grid, start, end)
    unfinished = {parameters: stored for parameters, stored in experiments.items()
                  if stored is None or stored[1] != "complete"}
    for parameters, stored in unfinished.items():
        logger.warning("%s: %s", describe(parameters),
                       "not stored" if stored is None else f"experiment {stored[0]} is {stored[1]}")
    complete = {parameters: stored[0] for parameters, stored in experiments.items()
                if parameters not in unfinished}
    logger.info("%d of %d combinations complete; their experiment ids: %s", len(complete),
                len(grid), sorted(complete.values()))
    results = experiment_statistics(engine, data_provider_id, args.provider, complete, start, end,
                                    logger)
    return complete, results, bool(unfinished)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("sweep-time" if args.time else "sweep-sensitivity")
    periods: list[Period] = []
    if args.periods is not None:
        try:
            periods = read_periods(args.periods)
        except (OSError, ValueError) as error:
            logger.error("%s", error)
            return 1
    elif args.end <= args.start:
        logger.error("--to must be later than --from")
        return 1
    try:
        engine, data_provider_id = connect(args, logger)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    try:
        grid = parameter_grid(READERS[args.provider].default_srid, args.algorithm, args.defaults,
                              args.extra)
        if not args.defaults:
            logger.info("Grid: %s: %d combinations", describe_grid(args.algorithm, args.extra),
                        len(grid))
        if periods:
            logger.info("%d combinations of %s over %s strokes (data provider %d), for each of "
                        "%d episode(s) of %s", len(grid), args.algorithm, args.provider,
                        data_provider_id, len(periods), args.periods)
        else:
            logger.info("%d combinations of %s over %s strokes (data provider %d), %s to %s",
                        len(grid), args.algorithm, args.provider, data_provider_id,
                        args.start.isoformat(), args.end.isoformat())
        if args.time:
            return time_analysis(engine, data_provider_id, args, grid, logger)
        gap_written = 0
        try:
            if args.gap:
                # Written to <name>.part, episode by episode (a grid's shuffled rows are too
                # many to keep), from what the gap file already there holds and what is new;
                # it takes the file's place at the end, the file becoming <name>.old.
                gap_path = args.output_dir / (
                    periods_csv_filename(args.provider, args.periods, algorithm=args.algorithm,
                                         defaults=args.defaults, gap=True) if periods else
                    csv_filename(args.provider, args.start, args.end, algorithm=args.algorithm,
                                 defaults=args.defaults, gap=True))
                gap_columns = gap_file_columns(args.algorithm, periods=bool(periods))
                blocks = (gap_file_blocks(gap_path, gap_columns, args.shuffles, args.seed)
                          if gap_path.exists() else {})
                if blocks:
                    logger.info("%s holds %d period(s) already: what it has is copied, not run "
                                "again", gap_path, len(blocks))
                part = gap_path.with_name(f"{gap_path.name}.part")
                _write(part, gap_columns, [])
            if periods:
                collected = []
                unfinished = False
                for number, period in enumerate(periods, start=1):
                    logger.info("Episode %s (%d of %d): %s to %s, run from %s to %s",
                                period.episode, number, len(periods), period.start.isoformat(),
                                period.end.isoformat(), period.run_start.isoformat(),
                                period.run_end.isoformat())
                    complete, results, incomplete = sensitivity(
                        engine, data_provider_id, args, grid, period.run_start, period.run_end,
                        logger, done=(number - 1) * len(grid), total=len(grid) * len(periods),
                        episode=f"episode {number} of {len(periods)}")
                    collected.append((period, complete, results))
                    unfinished = unfinished or incomplete
                    if args.gap:
                        old = ([row[3:] for row in _gap_block(gap_path, blocks[period.episode])]
                               if period.episode in blocks else None)
                        rows = gap_rows(engine, data_provider_id, args, grid, period.run_start,
                                        period.run_end, complete, results, logger,
                                        episode=f"episode {number} of {len(periods)}", old=old)
                        _append(part, [[period.episode, period.start.isoformat(),
                                        period.end.isoformat(), *row] for row in rows])
                        gap_written += len(rows)
                if args.gap:
                    episodes = {period.episode for period in periods}
                    for episode, lines in blocks.items():
                        if episode not in episodes:
                            rows = _gap_block(gap_path, lines)
                            _append(part, rows)
                            gap_written += len(rows)
                            logger.info("Episode %s of %s is not in %s: kept as it was", episode,
                                        gap_path.name, args.periods)
                path = args.output_dir / periods_csv_filename(args.provider, args.periods,
                                                              algorithm=args.algorithm,
                                                              defaults=args.defaults)
                write_periods_csv(path, collected, algorithm=args.algorithm)
                written = sum(len(complete) for _, complete, _ in collected)
            else:
                complete, results, unfinished = sensitivity(
                    engine, data_provider_id, args, grid, args.start, args.end, logger)
                path = args.output_dir / csv_filename(args.provider, args.start, args.end,
                                                      algorithm=args.algorithm,
                                                      defaults=args.defaults)
                write_csv(path, complete, results, algorithm=args.algorithm)
                written = len(complete)
                if args.gap:
                    old = _gap_block(gap_path, blocks[None]) if None in blocks else None
                    rows = gap_rows(engine, data_provider_id, args, grid, args.start, args.end,
                                    complete, results, logger, old=old)
                    _append(part, rows)
                    gap_written = len(rows)
            if args.gap:
                if gap_path.exists():
                    os.replace(gap_path, gap_path.with_name(f"{gap_path.name}.old"))
                os.replace(part, gap_path)
        except (RuntimeError, ValueError) as error:
            logger.error("%s", error)
            return 1
        except OSError as error:
            logger.error("Cannot write %s: %s", error.filename, error)
            return 1
        logger.info("Wrote %s (%d experiments)", path, written)
        if args.gap:
            logger.info("Wrote %s (%d rows: real runs and %d shuffle(s) of each period)",
                        gap_path, gap_written, args.shuffles)
    finally:
        engine.dispose()
    return 1 if unfinished else 0


if __name__ == "__main__":
    sys.exit(main())
