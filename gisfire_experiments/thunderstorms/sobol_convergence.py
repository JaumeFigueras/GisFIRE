#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The convergence of the Sobol indices' medians as the episodes add up.

::

    python3 -m gisfire_experiments.thunderstorms.sobol_convergence \\
        time_distance_galanaki_MeteoCat_catalunya-100-q1_sobol.csv [--language ca] [--output FIG.png]

Reads the per-episode indices written by
:mod:`gisfire_experiments.thunderstorms.sobol_indices` (``<input>_sobol.csv``), of
any algorithm, and draws how the median of each parameter's total index settles
as the episodes are taken one after the other: whether there are episodes enough
for the medians of :mod:`gisfire_experiments.thunderstorms.sobol_chart`.

The curves
----------

For each KPI of :data:`~gisfire_experiments.thunderstorms.sobol_chart.KPIS` and
each parameter, the total index ``S_Ti`` of the episodes in the file's order
(the order of the sweep's ``--periods`` file), counting only the episodes the
KPI has indices for (``sobol_indices`` leaves an episode out of a KPI when a
combination has no value or the KPI does not vary). The ``k``-th point is the
median of the first ``k`` episodes' indices (the mean of the two middle ones for
an even ``k``), so the first point is the first episode's index and the last is
the median over all of them, the one in ``_sobol_summary.csv``. The curve
depends on the order of the episodes; its last point does not.

The figure
----------

One panel per KPI, in two rows of three, each titled with the KPI and ``n``, the
number of episodes it has indices for; its x axis runs from the first episode
to the ``n``-th, with half an episode on each side; the y
axis, the median of the total index, runs from 0 to 1 in every panel. In each
panel, one line per parameter, named in the legend by its symbol in the sweep's
grids (D and T for the time-distance clustering, R, T, I and C for Cellsearch),
solid, in a colour of its own (:data:`LINE_COLORS`: the reference palette's
categorical blue, orange, aqua and yellow, which pass its validator on white
and for colour-blind readers; aqua and yellow are under 3:1 against it, hence
the legend), with a small marker on each point so that a single episode still
shows.

Behind each line, a band of its own colour, pale (:data:`BAND_ALPHA`), spans
the panel at the last value ± :data:`BAND` (cut at 0 and 1): from where the
curve stays inside it, more episodes no longer move the median by more than
that. A KPI with no episode (``n = 0``) has an empty panel.

The text is Nimbus Sans, 8 pt for titles and labels and 7 pt for ticks, as in
the bar chart; ``--language`` is ``en`` (default) or ``ca``.

The file
--------

A PNG (lossless), 16 cm wide by :data:`HEIGHT_CM` cm at 600 dpi (3780 × 2362 px),
on white, written to ``--output`` or beside the input as
``<input>_convergence.png``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from pathlib import Path

import pandas as pd

from matplotlib import font_manager
from matplotlib import rc_context
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

from gisfire_experiments.thunderstorms import sobol_chart
from gisfire_experiments.thunderstorms.sobol_chart import COLORS
from gisfire_experiments.thunderstorms.sobol_chart import DPI
from gisfire_experiments.thunderstorms.sobol_chart import FONT
from gisfire_experiments.thunderstorms.sobol_chart import KPIS
from gisfire_experiments.thunderstorms.sobol_chart import STYLE
from gisfire_experiments.thunderstorms.sobol_chart import WIDTH_PX
from gisfire_experiments.thunderstorms.sobol_chart import symbols
from gisfire_experiments.thunderstorms.sobol_indices import INDEX_COLUMNS
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT

#: The figure's own text, by language (the KPIs' names are the bar chart's).
LABELS = {
    "en": {"x": "Episodes", "y": "Median of $S_{Ti}$", "band": "Final median ± 0.025"},
    "ca": {"x": "Episodis", "y": "Mediana de $S_{Ti}$", "band": "Mediana final ± 0,025"},
}

#: Each parameter's line colour, in the file's order of the parameters.
LINE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

#: The band around each curve's last value: its half-width and its opacity.
BAND = 0.025
BAND_ALPHA = 0.15

#: The figure's height; the width and resolution are the bar chart's.
HEIGHT_CM = 10.0
HEIGHT_PX = round(HEIGHT_CM / 2.54 * DPI)


def running_medians(indices: pd.DataFrame, statistic: str) -> pd.DataFrame:
    """The running median of each parameter's total index of ``statistic``.

    One column per parameter, in the file's order, and one row per episode that
    has indices for ``statistic``, numbered from 1 in the file's order: row ``k``
    is the median over the first ``k`` episodes. No row when there is none.
    """
    totals = indices[indices["index"] == "total"]
    parameters = list(dict.fromkeys(totals["parameters"]))
    rows = totals[totals["statistic"] == statistic]
    frame = pd.DataFrame({name: rows.loc[rows["parameters"] == name, "value"]
                          .expanding().median().to_numpy() for name in parameters},
                         columns=parameters)
    frame.index = range(1, len(frame) + 1)
    return frame


def chart(indices: pd.DataFrame, language: str = "en") -> Figure:
    """The figure of a ``_sobol.csv`` (see the module's docstring)."""
    labels = LABELS[language]
    names = symbols()
    curves = {kpi: running_medians(indices, kpi) for kpi in KPIS}
    parameters = list(curves[KPIS[0]].columns)
    with rc_context(STYLE):
        figure = Figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), layout="constrained",
                        facecolor=COLORS["surface"])
        axes = figure.subplots(2, 3, sharey=True).ravel()
        for number, (ax, kpi) in enumerate(zip(axes, KPIS)):
            frame = curves[kpi]
            for p, name in enumerate(frame.columns if len(frame) else []):
                last = frame[name].iloc[-1]
                ax.axhspan(max(last - BAND, 0.0), min(last + BAND, 1.0), linewidth=0,
                           facecolor=LINE_COLORS[p], alpha=BAND_ALPHA, zorder=1)
                ax.plot(frame.index.to_list(), frame[name].to_list(), color=LINE_COLORS[p],
                        linewidth=1.0, marker="o", markersize=1.5, zorder=2)
            kpi_name = sobol_chart.LABELS[language][kpi].replace("\n", " ")
            ax.set_title(f"{kpi_name}\nn = {len(frame)}")
            ax.set_xlim(0.5, max(len(frame), 1) + 0.5)
            ax.set_ylim(0.0, 1.0)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.grid(color=COLORS["grid"], linewidth=0.5)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(length=2.0, width=0.5)
            if number % 3 == 0:
                ax.set_ylabel(labels["y"])
            if number >= 3:
                ax.set_xlabel(labels["x"])
        handles = [Line2D([], [], color=LINE_COLORS[p], linewidth=1.0, marker="o",
                          markersize=1.5, label=names.get(name, name))
                   for p, name in enumerate(parameters)]
        handles.append(Patch(facecolor=COLORS["tick"], alpha=BAND_ALPHA, linewidth=0,
                             label=labels["band"]))
        figure.legend(handles=handles, loc="outside upper center", ncol=len(handles),
                      frameon=False)
    return figure


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draw the convergence of the medians of the Sobol indices over the "
                    "episodes (PNG).")
    parser.add_argument("file", type=Path, help="a _sobol.csv file of sobol_indices")
    parser.add_argument("--output", type=Path, default=None,
                        help="the PNG file (default: beside the input, <input>_convergence.png)")
    parser.add_argument("--language", choices=sorted(LABELS), default="en",
                        help="the language of the figure's text (default: en)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("sobol-convergence")
    output = args.output or args.file.with_name(f"{args.file.stem}_convergence.png")
    try:
        font_manager.findfont(font_manager.FontProperties(family=FONT), fallback_to_default=False)
    except ValueError:
        logger.warning("%s is not installed: the figure uses matplotlib's default font", FONT)
    try:
        indices = pd.read_csv(args.file)
        missing = [name for name in INDEX_COLUMNS if name not in indices.columns]
        if missing:
            raise ValueError(f"{args.file} has no {', '.join(missing)} column: it is not a "
                             f"per-episode _sobol.csv file of sobol_indices")
        figure = chart(indices, args.language)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=DPI, format="png", facecolor=COLORS["surface"])
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        return 1
    names = symbols()
    for kpi in KPIS:
        frame = running_medians(indices, kpi)
        finals = ", ".join(f"{names.get(name, name)} {frame[name].iloc[-1]:.3f}"
                           for name in frame.columns) if len(frame) else "no median"
        logger.info("%s: %d episode(s), final median %s", kpi, len(frame), finals)
    logger.info("Wrote %s", output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
