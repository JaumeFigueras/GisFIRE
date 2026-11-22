#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A faceted stacked bar chart of the Sobol indices: every parameter's sensitivity and interactions.

::

    python3 -m gisfire_experiments.thunderstorms.sobol_chart \\
        time_distance_galanaki_FMI_finland-100-q1_sobol_summary.csv [--language ca] [--output FIG.png]

Draws the summary written by :mod:`gisfire_experiments.thunderstorms.sobol_indices`
(``<input>_sobol_summary.csv``), of any algorithm, as one figure, and writes its
numbers as a table: the summary is enough, the per-episode file is not read.

The figure
----------

One panel per KPI of :data:`KPIS`, side by side, sharing the y axis from 0 to 1,
each titled with the KPI and ``n``, the number of episodes its indices were
computed for. In each panel, one bar per parameter, labelled with its symbol in
the sweep's grids (D and T for the time-distance clustering, R, T, I and C for
Cellsearch):

* the **bottom segment** is the mean first-order index over the episodes,
  ``mean(S_i)``;
* the **top segment** is the mean of what the interactions add,
  ``mean(S_Ti) − mean(S_i)`` (drawn as 0 if rounding makes it negative), so the
  **whole bar** is the mean total index, ``mean(S_Ti)``: the first-order index
  is inside the total, so the two are not stacked on each other;
* a **whisker** spans the interquartile range of the total index over the
  episodes (``q1`` to ``q3``), to show when a mean hides episodes that differ.

A KPI with no episode (``n = 0``) draws no bars.

The two segments are one hue at two lightness steps (:data:`COLORS`: the
reference palette's blue ``#2a78d6`` and its lighter ``#86b6ef``, which passes the
2:1 floor against white, where ``#9ec5f4`` does not), so they stay apart in
grayscale print and for colour-blind readers; whiskers and text are near-black,
gridlines a hairline gray. The text is Nimbus Sans (the URW base-35 fonts), 8 pt
for titles and labels and 7 pt for ticks; without it installed matplotlib's
default is used, with a warning.

``--language`` is ``en`` (default) or ``ca`` (:data:`LABELS`).

The table
---------

The same run writes the numbers as a Word table (python-docx), from the same
summary and in the same language: one row per KPI, in the figure's order and
wording, with ``n`` and, for each parameter, its total index ("S\\ :sub:`T` de
D") and, for each pair, their interaction ("Interacció D×T"), as the **median
(q1–q3)** over the episodes, to 2 decimals (a decimal comma in Catalan); a KPI
with no episode shows "—". When there are more index columns than
:data:`ONE_LINE_COLUMNS` (4 for Cellsearch's R, T, I and C: 4 totals and 6
interactions), they go in two tables, the total indices and the interactions,
each under a heading, and a table wider than :data:`ONE_LINE_COLUMNS` columns
puts each cell's median and interval on two lines, so it fits the page. The
table is 16 cm wide like the figure, in Nimbus Sans 8 pt, with rules above and
below the header and at the bottom.

The files
---------

A PNG (lossless), 16 cm wide by :data:`HEIGHT_CM` cm at 600 dpi (3780 × 1654 px),
on white, written to ``--output`` or beside the summary as
``<summary>_chart.png``; and the table, written to ``--table`` or beside the
summary as ``<summary>_table.docx``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from pathlib import Path

import numpy as np
import pandas as pd

from matplotlib import font_manager
from matplotlib import rc_context
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from gisfire_experiments.thunderstorms.sweep import GRIDS
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT

#: The KPIs drawn, one panel each, in this order.
KPIS = ["thunderstorms", "isolated_pct", "density_median_per_100km2", "diameter_median_km",
        "diameter_p90_km", "duration_median_min"]

#: The figure's text, by language.
LABELS = {
    "en": {
        "thunderstorms": "Thunderstorms",
        "isolated_pct": "Isolated\nflashes (%)",
        "density_median_per_100km2": "Density\n(median)",
        "diameter_median_km": "Diameter\n(median)",
        "diameter_p90_km": "Diameter\n(P90)",
        "duration_median_min": "Duration\n(median)",
        "y": "Sobol index",
        "first_order": "First order ($S_i$)",
        "interaction": "Interactions ($S_{Ti} - S_i$)",
        "iqr": "IQR of $S_{Ti}$",
        "kpi": "KPI",
        "total_of": "of",
        "pair": "Interaction",
        "totals": "Total indices",
        "interactions": "Interactions",
        "decimal": ".",
    },
    "ca": {
        "thunderstorms": "Tempestes",
        "isolated_pct": "Llamps\naïllats (%)",
        "density_median_per_100km2": "Densitat\n(mediana)",
        "diameter_median_km": "Diàmetre\n(mediana)",
        "diameter_p90_km": "Diàmetre\n(P90)",
        "duration_median_min": "Durada\n(mediana)",
        "y": "Índex de Sobol",
        "first_order": "Primer ordre ($S_i$)",
        "interaction": "Interaccions ($S_{Ti} - S_i$)",
        "iqr": "RIQ de $S_{Ti}$",
        "kpi": "KPI",
        "total_of": "de",
        "pair": "Interacció",
        "totals": "Índexs totals",
        "interactions": "Interaccions",
        "decimal": ",",
    },
}

#: The palette (see the module's docstring).
COLORS = {"first_order": "#2a78d6", "interaction": "#86b6ef", "whisker": "#0b0b0b",
          "text": "#0b0b0b", "tick": "#52514e", "grid": "#e1e0d9", "axis": "#c3c2b7",
          "surface": "#ffffff"}

#: The figure's size and resolution. The size is taken to whole pixels (16 cm at
#: 600 dpi is 3779.5 px: 3780, which matplotlib would truncate to 3779).
WIDTH_CM = 16.0
HEIGHT_CM = 7.0
DPI = 600
WIDTH_PX = round(WIDTH_CM / 2.54 * DPI)
HEIGHT_PX = round(HEIGHT_CM / 2.54 * DPI)

#: The typeface.
FONT = "Nimbus Sans"

#: The table: the widths of its KPI and n columns (the index columns share the
#: rest of the 16 cm), and the most index columns a table holds with each cell on
#: one line; beyond, the median and the interquartile range take a line each.
KPI_COLUMN_CM = 3.4
N_COLUMN_CM = 0.9
ONE_LINE_COLUMNS = 4

#: The figure's matplotlib settings: the font (math too), its sizes and the colours.
STYLE = {
    "font.family": FONT,
    "font.size": 8,
    "mathtext.fontset": "custom",
    "mathtext.rm": FONT,
    "mathtext.it": f"{FONT}:italic",
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "text.color": COLORS["text"],
    "axes.labelcolor": COLORS["text"],
    "axes.edgecolor": COLORS["axis"],
    "xtick.color": COLORS["axis"],
    "ytick.color": COLORS["axis"],
    "xtick.labelcolor": COLORS["tick"],
    "ytick.labelcolor": COLORS["tick"],
}


def symbols() -> dict[str, str]:
    """Each parameter's symbol in the sweep's grids, by its field (``max_distance_km`` → ``D``)."""
    return {field: symbol for grid in GRIDS.values() for field, (symbol, _, _) in grid.items()}


def _values(rows: pd.DataFrame, index: str, parameters: list[str], column: str) -> np.ndarray:
    """``column`` of ``index`` for each parameter, in order; 0 where there is none."""
    picked = rows[rows["index"] == index].set_index("parameters")[column]
    return np.nan_to_num(picked.reindex(parameters).to_numpy(dtype=float), nan=0.0)


def chart(summary: pd.DataFrame, language: str = "en") -> Figure:
    """The figure of a ``_sobol_summary.csv`` (see the module's docstring).

    Raises
    ------
    ValueError
        If the summary has no rows for a KPI of :data:`KPIS`.
    """
    missing = [kpi for kpi in KPIS if kpi not in set(summary["statistic"])]
    if missing:
        raise ValueError(f"The summary has no indices for {', '.join(missing)}")
    labels = LABELS[language]
    parameters = list(dict.fromkeys(summary.loc[summary["index"] == "first_order", "parameters"]))
    names = symbols()
    x = np.arange(len(parameters))
    with rc_context(STYLE):
        figure = Figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), layout="constrained",
                        facecolor=COLORS["surface"])
        axes = figure.subplots(1, len(KPIS), sharey=True)
        for ax, kpi in zip(axes, KPIS):
            rows = summary[summary["statistic"] == kpi]
            first = _values(rows, "first_order", parameters, "mean")
            total = _values(rows, "total", parameters, "mean")
            q1 = _values(rows, "total", parameters, "q1")
            q3 = _values(rows, "total", parameters, "q3")
            n = int(rows["n"].max())
            ax.bar(x, first, width=0.6, color=COLORS["first_order"], edgecolor=COLORS["surface"],
                   linewidth=0.5, zorder=2)
            ax.bar(x, np.clip(total - first, 0.0, None), width=0.6, bottom=first,
                   color=COLORS["interaction"], edgecolor=COLORS["surface"], linewidth=0.5,
                   zorder=2)
            # Centred on the IQR, so the whisker is q1 to q3 wherever the mean lies.
            ax.errorbar(x, (q1 + q3) / 2.0, yerr=(q3 - q1) / 2.0, fmt="none",
                        ecolor=COLORS["whisker"], elinewidth=0.8, capsize=2.0, capthick=0.8,
                        zorder=3)
            ax.set_title(f"{labels[kpi]}\nn = {n}")
            ax.set_xticks(x, [names.get(name, name) for name in parameters])
            ax.set_xlim(-0.6, len(parameters) - 0.4)
            ax.set_ylim(0.0, 1.0)
            ax.set_yticks(np.linspace(0.0, 1.0, 6))
            ax.grid(axis="y", color=COLORS["grid"], linewidth=0.5)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(length=2.0, width=0.5)
        axes[0].set_ylabel(labels["y"])
        figure.legend(
            handles=[Patch(color=COLORS["first_order"], label=labels["first_order"]),
                     Patch(color=COLORS["interaction"], label=labels["interaction"]),
                     Line2D([], [], color=COLORS["whisker"], linewidth=0.8, marker="_",
                            markersize=6, label=labels["iqr"])],
            loc="outside upper center", ncol=3, frameon=False)
    return figure


def _interval(rows: pd.DataFrame, index: str, names: str, decimal: str) -> tuple[str, str] | None:
    """The median and the ``(q1–q3)`` of an index, formatted; ``None`` when it has no episode."""
    picked = rows[(rows["index"] == index) & (rows["parameters"] == names)]
    if picked.empty or not picked["n"].iloc[0] or pd.isna(picked["median"].iloc[0]):
        return None
    median, q1, q3 = (f"{picked[column].iloc[0]:.2f}".replace(".", decimal)
                      for column in ("median", "q1", "q3"))
    return median, f"({q1}–{q3})"


def _rule(cell, *sides: str) -> None:
    """A 0.75 pt black rule on the given sides of a table cell."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = cell._tc.get_or_add_tcPr()
    borders = properties.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        properties.append(borders)
    for side in sides:
        border = OxmlElement(f"w:{side}")
        for key, value in (("val", "single"), ("sz", "6"), ("space", "0"), ("color", "000000")):
            border.set(qn(f"w:{key}"), value)
        borders.append(border)


def _add_table(document, summary: pd.DataFrame, labels: dict[str, str],
               columns: list[tuple[str, str, str]]) -> None:
    """One table: KPI, n, and ``columns`` as ``(index, parameters, header)``, the header's
    ``_T`` written as a subscript T."""
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    two_lines = len(columns) > ONE_LINE_COLUMNS
    width = (WIDTH_CM - KPI_COLUMN_CM - N_COLUMN_CM) / len(columns)
    widths = [Cm(KPI_COLUMN_CM), Cm(N_COLUMN_CM)] + [Cm(width)] * len(columns)
    table = document.add_table(rows=1 + len(KPIS), cols=2 + len(columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    # The grid as well as every cell: LibreOffice and Word lay a table out by its columns.
    for column, column_width in zip(table.columns, widths):
        column.width = column_width
    header = table.rows[0].cells
    header[0].text, header[1].text = labels["kpi"], "n"
    for cell, (_, _, text) in zip(header[2:], columns):
        paragraph = cell.paragraphs[0]
        before, _, after = text.partition("_T")
        paragraph.add_run(before)
        if after or text.endswith("_T"):
            paragraph.add_run("T").font.subscript = True
        paragraph.add_run(after)
    for cell in header:
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row, kpi in zip(table.rows[1:], KPIS):
        rows = summary[summary["statistic"] == kpi]
        row.cells[0].text = labels[kpi].replace("\n", " ")
        row.cells[1].text = str(int(rows["n"].max()))
        for cell, (index, names, _) in zip(row.cells[2:], columns):
            value = _interval(rows, index, names, labels["decimal"])
            paragraph = cell.paragraphs[0]
            if value is None:
                paragraph.add_run("—")
            elif two_lines:
                run = paragraph.add_run(value[0])
                run.add_break()
                run.add_text(value[1])
            else:
                paragraph.add_run(f"{value[0]} {value[1]}")
    for row in table.rows:
        for column, (cell, cell_width) in enumerate(zip(row.cells, widths)):
            cell.width = cell_width
            if column:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for cell in table.rows[0].cells:
        _rule(cell, "top", "bottom")
    for cell in table.rows[-1].cells:
        _rule(cell, "bottom")


def table_document(summary: pd.DataFrame, language: str = "en"):
    """The table of a ``_sobol_summary.csv``: per KPI, ``n`` and each total index's and
    interaction's median (q1–q3), a Word document (``docx.Document``).

    One table when the index columns fit (:data:`ONE_LINE_COLUMNS`), otherwise one of
    the total indices and one of the interactions, each under a heading.

    Raises
    ------
    ValueError
        If the summary has no rows for a KPI of :data:`KPIS`.
    """
    from docx import Document
    from docx.shared import Pt

    missing = [kpi for kpi in KPIS if kpi not in set(summary["statistic"])]
    if missing:
        raise ValueError(f"The summary has no indices for {', '.join(missing)}")
    labels = LABELS[language]
    names = symbols()
    parameters = list(dict.fromkeys(summary.loc[summary["index"] == "first_order", "parameters"]))
    totals = [("total", name, f"S_T {labels['total_of']} {names.get(name, name)}")
              for name in parameters]
    pairs = list(dict.fromkeys(summary.loc[summary["index"] == "interaction", "parameters"]))
    interactions = [("interaction", pair, f"{labels['pair']} "
                     + "×".join(names.get(name, name) for name in pair.split(":")))
                    for pair in pairs]
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = FONT, Pt(8)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0
    if len(totals) + len(interactions) <= ONE_LINE_COLUMNS:
        _add_table(document, summary, labels, totals + interactions)
    else:
        for heading, columns in ((labels["totals"], totals), (labels["interactions"], interactions)):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(4)
            paragraph.add_run(heading).bold = True
            _add_table(document, summary, labels, columns)
    return document


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draw a Sobol indices summary as a faceted stacked bar chart (PNG).")
    parser.add_argument("summary", type=Path, help="a _sobol_summary.csv file of sobol_indices")
    parser.add_argument("--output", type=Path, default=None,
                        help="the PNG file (default: beside the summary, <summary>_chart.png)")
    parser.add_argument("--table", type=Path, default=None,
                        help="the DOCX file of the table (default: beside the summary, "
                             "<summary>_table.docx)")
    parser.add_argument("--language", choices=sorted(LABELS), default="en",
                        help="the language of the figure's text (default: en)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("sobol-chart")
    output = args.output or args.summary.with_name(f"{args.summary.stem}_chart.png")
    table_path = args.table or args.summary.with_name(f"{args.summary.stem}_table.docx")
    try:
        font_manager.findfont(font_manager.FontProperties(family=FONT), fallback_to_default=False)
    except ValueError:
        logger.warning("%s is not installed: the figure uses matplotlib's default font", FONT)
    try:
        data = pd.read_csv(args.summary)
        figure = chart(data, args.language)
        document = table_document(data, args.language)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=DPI, format="png", facecolor=COLORS["surface"])
        table_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(table_path))
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        return 1
    logger.info("Wrote %s and %s", output, table_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
