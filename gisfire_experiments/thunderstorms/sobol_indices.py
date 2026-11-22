#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sobol indices of the sweep's statistics, per episode, over its grid of parameters.

::

    python3 -m gisfire_experiments.thunderstorms.sobol_indices \\
        time_distance_galanaki_FMI_finland-100-q1.csv [--output-dir DIR]

Reads a CSV file written by the sweep's ``--sensitivity``
(:mod:`gisfire_experiments.thunderstorms.sweep`), of any algorithm, with or
without ``--periods``, and writes how much of each statistic's variation each
parameter explains. Nothing is read from the database, so a file copied from
another machine will do.

The grid
--------

The parameters are the file's columns between ``experiment_id`` and the
statistics: D and T for the time-distance clustering, R, T, I and C for
Cellsearch. The sweep runs a **full factorial grid**, every combination of the
parameters' levels, the same in every episode, and on such a grid the Sobol
indices are exact: the decomposition of the variance (the ANOVA identity) needs
only the means of the statistic grouped by the parameters, with no sampling.
With Y a statistic over one episode's grid, and the variances taken over the
grid's combinations, all of them weighing the same:

* **first-order index** of a parameter, the share of the variance it explains
  alone: ``S_i = Var(E[Y | X_i]) / Var(Y)``;
* **total index**, the share it has a part in, interactions included:
  ``S_Ti = 1 − Var(E[Y | every parameter but X_i]) / Var(Y)``;
* **interaction** of two parameters, the share they explain together beyond
  each one alone: ``S_ij = Var(E[Y | X_i, X_j]) / Var(Y) − S_i − S_j``.

The indices describe the grid's levels: they take each level of a parameter as
equally likely (T in 5, 10, 15, 20, 30 and 60 min, say), so other levels would
give other indices. A level written as an empty cell (Cellsearch's C off) is a
level of its own.

Each episode must hold the full grid, every combination once: a file that does
not, or whose parameters do not vary (a ``--defaults`` file), is refused. SALib,
the usual library for Sobol indices, estimates them from a sample of its own
design (Saltelli's), not from a grid, so it is not used.

Statistics and episodes
-----------------------

The statistics analysed are those of :data:`STATISTICS`: the sweep's, but for
``flashes_clustered`` and ``flashes_discarded_error``, which no parameter swept
changes within an episode. A statistic's indices are computed for each episode
where it has a value for every combination and varies; the other episodes are
left out of that statistic, with nothing filled in (a combination with no
thunderstorm has no density, diameter or duration), and counted.

The files
---------

Beside the input file, or in ``--output-dir``, named after it:

* ``<input>_sobol.csv``: one row per episode, statistic and index, ``episode``
  (empty for a file of one period), ``statistic``, ``index``
  (``first_order``, ``total`` or ``interaction``), ``parameters`` (a
  parameter's name, or two joined by ``:`` for an interaction) and ``value``;
* ``<input>_sobol_summary.csv``: one row per statistic and index, with ``n``,
  the number of episodes it was computed for, the ``mean``, ``median``, first
  and third quartiles (``q1``, ``q3``: pandas' default, linear interpolation,
  Hyndman & Fan's type 7, as the episodes study's quartiles), interquartile
  range (``iqr``, ``q3 − q1``), ``min`` and ``max`` of the index over those
  episodes, empty when there is none, and the episodes left out
  (``episodes_missing``: a combination without a value; ``episodes_constant``:
  no variation).
"""

from __future__ import annotations

import argparse
import itertools
import logging
import math
import os
import sys

from pathlib import Path
from typing import Any

import pandas as pd

from gisfire_experiments.thunderstorms.sweep import STATISTIC_COLUMNS
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT

#: The columns of a sweep's file that are neither parameters nor statistics.
LEADING_COLUMNS = ("episode", "start", "end", "experiment_id")

#: The statistics analysed: the sweep's, but for those no parameter swept changes.
STATISTICS = [name for name in STATISTIC_COLUMNS
              if name not in ("flashes_clustered", "flashes_discarded_error")]

#: The columns of the two files.
INDEX_COLUMNS = ["episode", "statistic", "index", "parameters", "value"]
SUMMARY_COLUMNS = ["statistic", "index", "parameters", "n", "mean", "median", "q1", "q3", "iqr",
                   "min", "max", "episodes_missing", "episodes_constant"]


def parameter_columns(columns: list[str]) -> list[str]:
    """The parameters swept: the columns that are neither leading ones nor statistics."""
    return [name for name in columns
            if name not in LEADING_COLUMNS and name not in STATISTIC_COLUMNS]


def index_keys(parameters: list[str]) -> list[tuple[str, str]]:
    """Every index of a grid, in the files' order: ``(index, parameters)``."""
    return ([("first_order", name) for name in parameters]
            + [("total", name) for name in parameters]
            + [("interaction", f"{a}:{b}") for a, b in itertools.combinations(parameters, 2)])


def grid_indices(frame: pd.DataFrame, parameters: list[str],
                 statistic: str) -> dict[tuple[str, str], float] | str:
    """The Sobol indices of ``statistic`` over one episode's full grid.

    Returns ``"missing"`` when a combination has no value and ``"constant"`` when
    the statistic does not vary: it has no indices then.
    """
    y = frame[statistic].astype(float)
    if y.isna().any():
        return "missing"
    variance = y.var(ddof=0)
    if not variance > 0:
        return "constant"

    def explained(names: list[str]) -> float:
        """``Var(E[Y | names])``; every group holds as many combinations (a full grid)."""
        if not names:
            return 0.0
        return frame.assign(y=y).groupby(names, dropna=False)["y"].mean().var(ddof=0)

    first = {name: explained([name]) / variance for name in parameters}
    result: dict[tuple[str, str], float] = {("first_order", name): first[name] for name in parameters}
    for name in parameters:
        result[("total", name)] = 1.0 - explained([other for other in parameters
                                                   if other != name]) / variance
    for a, b in itertools.combinations(parameters, 2):
        result[("interaction", f"{a}:{b}")] = explained([a, b]) / variance - first[a] - first[b]
    return result


def analyse(table: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The indices of every episode and statistic, and their summary over the episodes.

    Raises
    ------
    ValueError
        If a parameter does not vary or an episode does not hold the full grid.
    """
    parameters = parameter_columns(list(table.columns))
    if not parameters:
        raise ValueError("The file has no parameter columns: it is not a sweep's file")
    still = [name for name in parameters if table[name].nunique(dropna=False) < 2]
    if still:
        raise ValueError(f"{', '.join(still)} {'does' if len(still) == 1 else 'do'} not vary: "
                         f"the indices need a grid (not a --defaults file)")
    size = math.prod(table[name].nunique(dropna=False) for name in parameters)
    episodes = (table.groupby("episode", sort=False) if "episode" in table.columns
                else [("", table)])

    rows: list[dict[str, Any]] = []
    skipped = {statistic: {"missing": 0, "constant": 0} for statistic in STATISTICS}
    for episode, frame in episodes:
        if len(frame) != size or frame.duplicated(parameters).any():
            raise ValueError(f"episode {episode} does not hold the full grid of {size} "
                             f"combinations, each once")
        for statistic in STATISTICS:
            result = grid_indices(frame, parameters, statistic)
            if isinstance(result, str):
                skipped[statistic][result] += 1
                continue
            rows.extend({"episode": episode, "statistic": statistic, "index": index,
                         "parameters": names, "value": value}
                        for (index, names), value in result.items())

    values = pd.DataFrame(rows, columns=INDEX_COLUMNS)
    summary = []
    for statistic in STATISTICS:
        for index, names in index_keys(parameters):
            series = values.loc[(values.statistic == statistic) & (values["index"] == index)
                                & (values.parameters == names), "value"]
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            summary.append({"statistic": statistic, "index": index, "parameters": names,
                            "n": len(series), "mean": series.mean(), "median": series.median(),
                            "q1": q1, "q3": q3, "iqr": q3 - q1,
                            "min": series.min(), "max": series.max(),
                            "episodes_missing": skipped[statistic]["missing"],
                            "episodes_constant": skipped[statistic]["constant"]})
    return rows, summary


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sobol indices of the statistics of a sweep's CSV file, per episode.")
    parser.add_argument("file", type=Path, help="a CSV file written by the sweep's --sensitivity")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="where the two files go (default: beside the input file)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("sobol-indices")
    directory = args.output_dir or args.file.parent
    paths = (directory / f"{args.file.stem}_sobol.csv",
             directory / f"{args.file.stem}_sobol_summary.csv")
    try:
        rows, summary = analyse(pd.read_csv(args.file))
        directory.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=INDEX_COLUMNS).to_csv(paths[0], index=False,
                                                         float_format="%.6f")
        pd.DataFrame(summary, columns=SUMMARY_COLUMNS).to_csv(paths[1], index=False,
                                                              float_format="%.6f")
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        return 1
    for statistic in STATISTICS:
        row = next(row for row in summary if row["statistic"] == statistic)
        logger.info("%s: %d episode(s), %d left out (%d with a missing value, %d constant)",
                    statistic, row["n"], row["episodes_missing"] + row["episodes_constant"],
                    row["episodes_missing"], row["episodes_constant"])
    logger.info("Wrote %s and %s", *paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
