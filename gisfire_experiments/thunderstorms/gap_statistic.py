#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gap statistic of the sweep's share of isolated flashes, per episode, over its grid.

::

    python3 -m gisfire_experiments.thunderstorms.gap_statistic \\
        time_distance_galanaki_FMI_gap_finland-100-q1.csv [--output-dir DIR]

Reads a gap file written by the sweep's ``--sensitivity --gap``
(:mod:`gisfire_experiments.thunderstorms.sweep`), of any algorithm and
provider, with or without ``--periods``, of a grid or of ``--defaults``, and
writes, for each combination of the parameters, how far the real data's share
of isolated flashes falls below its share in the shuffled copies. Nothing is
read from the database, so a file copied from another machine will do.

The gap
-------

The gap statistic (Tibshirani, R., Walther, G. & Hastie, T. (2001), Estimating
the number of clusters in a data set via the gap statistic, *Journal of the
Royal Statistical Society: Series B* 63(2), 411–423) compares a clustering
criterion ``W`` on the data with its values on reference data that hold no
clusters. Here ``W`` is ``isolated_pct``, the share of the zone flashes
clustered that end in no thunderstorm, and the reference data are the sweep's
shuffled copies of each period: the same flashes in the same places, as many
each minute, but with their times permuted, so that no storm is left (see the
sweep's *Shuffled runs*). For an episode and a combination, with ``W`` the real
run's ``isolated_pct`` and ``W*`` the ``isolated_pct`` of each of the ``B``
shuffled runs::

    gap = mean(W*) − W

in percentage points: how many points of the episode's flashes fewer than
chance the real data leave isolated. Two departures from the article:

* the difference is taken in percentage points, not between logarithms:
  ``W`` is already a share of the episode's flashes, from 0 to 100, so the
  differences compare across episodes and combinations, and ``W`` reaches 0
  (every flash in a thunderstorm), where a logarithm has no value;
* the reference is the shuffle of the times, not points drawn uniformly over
  the data's box: it keeps where the lightning falls and when it is most
  frequent, and breaks only the link between the two, the idea of the
  permutation tests of Knox, E. G. (1964), The detection of space-time
  interactions, *Journal of the Royal Statistical Society: Series C* 13(1),
  25–30, and Mantel, N. (1967), The detection of disease clustering and a
  generalized regression approach, *Cancer Research* 27(2), 209–220.

A combination that groups everything, or nothing, leaves the real and the
shuffled data alike (``W`` and ``W*`` both near 0, or both near 100), and its
gap is near 0: the gap is largest where the parameters find storms that chance
does not make. The shuffles' standard deviation (over ``B``, as in the
article) tells how far a gap stands out from their own spread.

Each episode's maximum
----------------------

In each episode, the combination of the largest gap is its **maximum**. When
``k`` combinations share it, each one takes ``1/k`` of the episode, so the
maxima add up to the episodes. An episode whose largest gap is not above 0 (its
real data leave as many flashes isolated as chance, or more, whatever the
combination) has no maximum; it still counts in the medians and the bootstrap,
as every episode weighs the same.

The bootstrap
-------------

How firm the combination of the largest median gap is: :data:`RESAMPLES`
samples of the episodes, as many as there are, drawn with replacement, and in
each sample the combination of the largest median gap over its episodes
(``1/k`` each when ``k`` share it, none when it is not above 0). The share of
the samples each combination takes is its ``bootstrap_best``. The episodes are
drawn, in increasing order of their number, with the sweep's Park & Miller
generator (:func:`~gisfire_experiments.thunderstorms.sweep.next_seed`) from
its seed (:data:`~gisfire_experiments.thunderstorms.sweep.SEED`), one value
``Z`` drawing the episode ``(Z − 1)·n // (2³¹ − 2)`` of the ``n``, so a file
gives the same shares on every computer, with any version of numpy.

The maxima and the bootstrap's shares are counted per combination, so they add
up over any parameters: a matrix of two of Cellsearch's four parameters sums
them over the other two.

The file read
-------------

The parameters are the file's columns between ``experiment_id`` and the
statistics, so an algorithm added to the sweep needs nothing here. A level
written as an empty cell (Cellsearch's C off) is a level of its own. The file is
refused unless every combination of every episode has one real row and ``B``
shuffled ones (the same ``B`` for all), every episode holds the same
combinations, and every row has an ``isolated_pct`` (empty when no zone flash
was clustered).

The files
---------

Beside the input file, or in ``--output-dir``, named after it:

* ``<input>_gap.csv``: one row per episode and combination: ``episode`` (empty
  for a file of one period), ``flashes`` (the episode's zone flashes), the
  parameters (as written in the input), ``isolated_pct`` (the real run's),
  ``shuffled_mean`` and ``shuffled_sd`` (of the ``B`` shuffled runs'
  ``isolated_pct``, the standard deviation over ``B``), ``gap`` and ``best``
  (1 at the episode's maximum, ``1/k`` when ``k`` share it, 0 elsewhere and
  in an episode without one);
* ``<input>_gap_summary.csv``: one row per combination: the parameters, ``n``
  (the episodes), the gap's ``mean``, ``median``, first and third quartiles
  (``q1``, ``q3``: pandas' default, Hyndman & Fan's type 7, as the Sobol
  summary), interquartile range (``iqr``, ``q3 − q1``), ``min`` and ``max``
  over the episodes, ``episodes_best`` (the episodes whose maximum it is, the
  sum of its ``best``) and ``bootstrap_best`` (its share of the bootstrap's
  samples, from 0 to 1).

The log names the combination of the largest median gap, the two combinations
of the largest bootstrap shares and the episodes without a maximum.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from gisfire_experiments.thunderstorms.sweep import (GAP_COLUMNS, GENERATOR_MODULUS, SEED,
                                                     STATISTIC_COLUMNS, next_seed)
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT

#: The columns of a gap file that are neither parameters nor statistics.
LEADING_COLUMNS = ("episode", "start", "end", *GAP_COLUMNS)

#: How many samples of the episodes the bootstrap draws.
RESAMPLES = 1000

#: The columns of the two files after the parameters (the first file's ``episode`` and
#: ``flashes`` come before them).
VALUE_COLUMNS = ["isolated_pct", "shuffled_mean", "shuffled_sd", "gap", "best"]
SUMMARY_COLUMNS = ["n", "mean", "median", "q1", "q3", "iqr", "min", "max", "episodes_best",
                   "bootstrap_best"]


def parameter_columns(columns: list[str]) -> list[str]:
    """The parameters swept: a gap file's columns between ``experiment_id`` and the
    statistics."""
    return [name for name in columns
            if name not in LEADING_COLUMNS and name not in STATISTIC_COLUMNS]


def describe(levels: pd.Series) -> str:
    """A combination as ``name value, ...``, an empty level as ``empty``."""
    return ", ".join(f"{name} {'empty' if pd.isna(value) else value}"
                     for name, value in levels.items())


def maxima(gaps: np.ndarray) -> np.ndarray:
    """The maximum of each row of ``gaps`` (or of a single row): ``1/k`` at the ``k``
    places of its largest value, 0 elsewhere, and 0 everywhere in a row whose largest
    value is not above 0."""
    top = gaps.max(axis=-1, keepdims=True)
    tied = (gaps == top) & (top > 0)
    return tied / np.maximum(tied.sum(axis=-1, keepdims=True), 1)


def bootstrap_best(gaps: np.ndarray, resamples: int = RESAMPLES, seed: int = SEED) -> np.ndarray:
    """Each column's share of ``resamples`` samples of the rows of ``gaps`` (episodes ×
    combinations; as many rows as there are, with replacement) in which its median is
    the largest (see :func:`maxima`).

    The rows are drawn with the sweep's generator, from ``seed``: a value ``Z`` draws
    the row ``(Z − 1)·n // (2³¹ − 2)``.
    """
    n = len(gaps)
    shares = np.zeros(gaps.shape[1])
    for _ in range(resamples):
        rows = []
        for _ in range(n):
            seed = next_seed(seed)
            rows.append((seed - 1) * n // (GENERATOR_MODULUS - 1))
        shares += maxima(np.median(gaps[rows], axis=0))
    return shares / resamples


def _episode(episode: Any) -> str:
    return "the period" if episode == "" else f"episode {episode}"


def analyse(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[Any]]:
    """The gap of every episode and combination, its summary per combination, and the
    episodes without a maximum.

    Raises
    ------
    ValueError
        If the file is not a gap file, a combination of an episode does not have one real
        row and as many shuffled rows as the others, the episodes do not hold the same
        combinations, or an ``isolated_pct`` is empty.
    """
    missing = [name for name in ("run", "flashes", "isolated_pct") if name not in table.columns]
    parameters = parameter_columns(list(table.columns))
    if missing or not parameters:
        raise ValueError(f"The file has no {', '.join(missing) or 'parameter'} column: it is not "
                         f"a sweep's gap file (--gap)")
    if "episode" not in table.columns:
        table = table.assign(episode="")
    empty = table.loc[table.isolated_pct.isna(), "episode"]
    if len(empty):
        raise ValueError(f"{_episode(empty.iloc[0])} has an empty isolated_pct (no zone flash "
                         f"clustered): it has no gap")

    table = table.assign(combination=table.groupby(parameters, dropna=False,
                                                   sort=False).ngroup())
    levels = table.drop_duplicates("combination").set_index("combination")[parameters]
    counts = (table.groupby(["episode", "combination", "run"], sort=False).size()
              .unstack("run", fill_value=0).reindex(columns=["real", "shuffled"], fill_value=0))
    shuffles = counts.shuffled.mode().iloc[0]
    if shuffles < 1:
        raise ValueError("The file has no shuffled rows: it is not a sweep's gap file (--gap)")
    wrong = counts[(counts.real != 1) | (counts.shuffled != shuffles)]
    if len(wrong):
        (episode, combination), row = next(wrong.iterrows())
        raise ValueError(f"{_episode(episode)}, {describe(levels.loc[combination])}: "
                         f"{row.real} real and {row.shuffled} shuffled rows; every combination "
                         f"must have 1 real row and {shuffles} shuffled rows, as the others")
    episodes = counts.index.get_level_values("episode").unique()
    present = counts.groupby(level="combination").size()
    absent = present[present != len(episodes)]
    if len(absent):
        raise ValueError(f"{describe(levels.loc[absent.index[0]])} is in {absent.iloc[0]} of the "
                         f"{len(episodes)} episodes: every episode must hold the same "
                         f"combinations")

    real = table[table.run == "real"].set_index(["episode", "combination"])
    shuffled = (table[table.run == "shuffled"]
                .groupby(["episode", "combination"], sort=False)["isolated_pct"])
    values = real[["flashes", *parameters, "isolated_pct"]].assign(
        shuffled_mean=shuffled.mean(), shuffled_sd=shuffled.std(ddof=0))
    values["gap"] = values.shuffled_mean - values.isolated_pct
    gaps = values["gap"].unstack("combination")      # episodes (increasing) × combinations
    best = maxima(gaps.to_numpy())
    values["best"] = best[gaps.index.get_indexer(values.index.get_level_values("episode")),
                          gaps.columns.get_indexer(values.index.get_level_values("combination"))]

    q1, q3 = gaps.quantile(0.25), gaps.quantile(0.75)
    summary = levels.assign(
        n=gaps.count(), mean=gaps.mean(), median=gaps.median(), q1=q1, q3=q3, iqr=q3 - q1,
        min=gaps.min(), max=gaps.max(),
        episodes_best=values["best"].groupby(level="combination").sum(),
        bootstrap_best=pd.Series(bootstrap_best(gaps.to_numpy()), index=gaps.columns))
    no_maximum = list(gaps.index[best.sum(axis=1) == 0])
    return (values.reset_index()[["episode", "flashes", *parameters, *VALUE_COLUMNS]],
            summary.reset_index(drop=True)[[*parameters, *SUMMARY_COLUMNS]], no_maximum)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gap statistic of the share of isolated flashes of a sweep's gap file, per "
                    "episode.")
    parser.add_argument("file", type=Path, help="a CSV file written by the sweep's --gap")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="where the two files go (default: beside the input file)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("gap-statistic")
    directory = args.output_dir or args.file.parent
    paths = (directory / f"{args.file.stem}_gap.csv",
             directory / f"{args.file.stem}_gap_summary.csv")
    try:
        # Only the columns used; the parameters as text, so they are written as read.
        columns = list(pd.read_csv(args.file, nrows=0).columns)
        parameters = parameter_columns(columns)
        used = {"episode", "run", "flashes", "isolated_pct", *parameters}
        values, summary, no_maximum = analyse(
            pd.read_csv(args.file, usecols=[name for name in columns if name in used],
                        dtype=dict.fromkeys(parameters, str)))
        directory.mkdir(parents=True, exist_ok=True)
        values.to_csv(paths[0], index=False, float_format="%.6f")
        summary.to_csv(paths[1], index=False, float_format="%.6f")
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        return 1
    top = summary.loc[summary["median"].idxmax()]
    logger.info("%d episode(s), %d combination(s); largest median gap %.2f points: %s",
                top["n"], len(summary), top["median"], describe(top[parameters]))
    logger.info("Largest bootstrap shares: %s",
                "; ".join(f"{describe(row[parameters])} {100.0 * row.bootstrap_best:.1f} %"
                          for _, row in summary.nlargest(2, "bootstrap_best").iterrows()))
    logger.info("Episodes without a maximum (no gap above 0): %s",
                ", ".join(map(str, no_maximum)) or "none")
    logger.info("Wrote %s and %s", *paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
