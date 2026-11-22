#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The faceted stacked bar chart of the Sobol indices, drawn off-screen."""

import itertools
import struct

import docx
import matplotlib
import pandas as pd
import pytest

from matplotlib import font_manager

from gisfire_experiments.thunderstorms import sobol_chart as chart
from gisfire_experiments.thunderstorms.sobol_indices import SUMMARY_COLUMNS

matplotlib.use("Agg")

PARAMETERS = ["max_distance_km", "max_time_difference_min"]


def summary(statistics=chart.KPIS, n=14, parameters=PARAMETERS) -> pd.DataFrame:
    """A summary as ``sobol_indices`` writes it: for each KPI and parameter, made-up
    indices that differ by KPI (k) and parameter (p) so every value can be told apart."""
    rows = []
    for k, statistic in enumerate(statistics):
        for p, name in enumerate(parameters):
            first = 0.1 + 0.1 * p + 0.01 * k
            total = first + 0.2
            for index, mean, q1, q3 in (("first_order", first, first - 0.05, first + 0.05),
                                        ("total", total, total - 0.1, total + 0.15)):
                rows.append({"statistic": statistic, "index": index, "parameters": name, "n": n,
                             "mean": mean, "median": mean, "q1": q1, "q3": q3, "iqr": q3 - q1,
                             "min": q1 - 0.05, "max": q3 + 0.05, "episodes_missing": 0,
                             "episodes_constant": 0})
        for a, b in itertools.combinations(parameters, 2):
            rows.append({"statistic": statistic, "index": "interaction",
                         "parameters": f"{a}:{b}", "n": n, "mean": 0.2, "median": 0.2,
                         "q1": 0.1, "q3": 0.3, "iqr": 0.2, "min": 0.0, "max": 0.4,
                         "episodes_missing": 0, "episodes_constant": 0})
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def heights(container) -> list[float]:
    return [patch.get_height() for patch in container]


def test_six_panels_in_the_kpi_order_sharing_a_0_to_1_axis():
    figure = chart.chart(summary())
    axes = figure.axes
    assert chart.KPIS == ["thunderstorms", "isolated_pct", "density_median_per_100km2",
                          "diameter_median_km", "diameter_p90_km", "duration_median_min"]
    assert len(axes) == 6
    assert [ax.get_title().splitlines()[0] for ax in axes] == [
        "Thunderstorms", "Isolated", "Density", "Diameter", "Diameter", "Duration"]
    assert all(ax.get_ylim() == (0.0, 1.0) for ax in axes)
    assert all(ax.get_title().splitlines()[-1] == "n = 14" for ax in axes)
    assert axes[0].get_ylabel() == "Sobol index"


def test_each_bar_stacks_the_first_order_index_and_the_interactions():
    data = summary()
    figure = chart.chart(data)
    for k, ax in enumerate(figure.axes):
        first, interaction = ax.containers[0], ax.containers[1]
        expected_first = [0.1 + 0.01 * k, 0.2 + 0.01 * k]
        assert heights(first) == pytest.approx(expected_first)
        assert heights(interaction) == pytest.approx([0.2, 0.2])
        assert [patch.get_y() for patch in interaction] == pytest.approx(expected_first)
        assert [label.get_text() for label in ax.get_xticklabels()] == ["D", "T"]


def test_the_whiskers_span_the_iqr_of_the_total_index():
    figure = chart.chart(summary())
    for k, ax in enumerate(figure.axes):
        segments = ax.containers[2].lines[2][0].get_segments()
        totals = [0.3 + 0.01 * k, 0.4 + 0.01 * k]
        assert [(segment[0][1], segment[1][1]) for segment in segments] == [
            (pytest.approx(total - 0.1), pytest.approx(total + 0.15)) for total in totals]


def test_an_interaction_below_zero_from_rounding_is_drawn_as_zero():
    data = summary()
    first = (data["index"] == "first_order")
    data.loc[first, "mean"] = data.loc[data["index"] == "total", "mean"].to_numpy() + 1e-12
    figure = chart.chart(data)
    assert heights(figure.axes[0].containers[1]) == [0.0, 0.0]


def test_a_kpi_without_episodes_draws_no_bars_and_says_n_0():
    data = summary()
    data.loc[data.statistic == "duration_median_min", ["n", "mean", "median", "q1", "q3",
                                                        "iqr", "min", "max"]] = \
        [0, None, None, None, None, None, None, None]
    ax = chart.chart(data).axes[-1]
    assert ax.get_title().splitlines()[-1] == "n = 0"
    assert heights(ax.containers[0]) == [0.0, 0.0]


def test_the_labels_can_be_catalan():
    figure = chart.chart(summary(), language="ca")
    assert [ax.get_title().splitlines()[0] for ax in figure.axes] == [
        "Tempestes", "Llamps", "Densitat", "Diàmetre", "Diàmetre", "Durada"]
    assert figure.axes[0].get_ylabel() == "Índex de Sobol"
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        chart.LABELS["ca"]["first_order"], chart.LABELS["ca"]["interaction"],
        chart.LABELS["ca"]["iqr"]]
    assert chart.LABELS["ca"]["iqr"].startswith("RIQ")


def test_the_legend_names_the_two_segments_and_the_whiskers():
    figure = chart.chart(summary())
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        chart.LABELS["en"]["first_order"], chart.LABELS["en"]["interaction"],
        chart.LABELS["en"]["iqr"]]


def test_the_text_is_in_nimbus_sans():
    try:
        font_manager.findfont(font_manager.FontProperties(family=chart.FONT),
                              fallback_to_default=False)
    except ValueError:
        pytest.skip("Nimbus Sans is not installed")
    figure = chart.chart(summary())
    assert figure.axes[0].title.get_fontname() == "Nimbus Sans"


def png_size(path) -> tuple[int, int, float]:
    """Width and height in pixels, and resolution in dots per inch, from the PNG's chunks."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    at = data.index(b"pHYs")
    per_metre = struct.unpack(">I", data[at + 4:at + 8])[0]
    return width, height, per_metre * 0.0254


def test_the_png_is_16_cm_wide_at_600_dpi(tmp_path):
    source = tmp_path / "time_distance_galanaki_FMI_finland-100-q1_sobol_summary.csv"
    summary().to_csv(source, index=False)
    output = tmp_path / "figure.png"
    assert chart.main([str(source), "--output", str(output)]) == 0
    width, height, dpi = png_size(output)
    assert width == round(16.0 / 2.54 * 600)
    assert height == round(chart.HEIGHT_CM / 2.54 * 600)
    assert dpi == pytest.approx(600.0, abs=0.1)


def test_the_png_goes_beside_the_summary_by_default(tmp_path):
    source = tmp_path / "sweep_sobol_summary.csv"
    summary().to_csv(source, index=False)
    assert chart.main([str(source), "--language", "ca"]) == 0
    assert (tmp_path / "sweep_sobol_summary_chart.png").exists()


def test_a_summary_without_a_kpi_is_reported(tmp_path, caplog):
    source = tmp_path / "partial_sobol_summary.csv"
    summary(statistics=chart.KPIS[:3]).to_csv(source, index=False)
    assert chart.main([str(source)]) == 1
    assert "diameter_median_km" in caplog.text


# --- the table ------------------------------------------------------------------------

def cells(table) -> list[list[str]]:
    return [[cell.text for cell in row.cells] for row in table.rows]


def test_one_run_writes_the_chart_and_the_table_beside_the_summary(tmp_path):
    source = tmp_path / "sweep_sobol_summary.csv"
    summary().to_csv(source, index=False)
    assert chart.main([str(source)]) == 0
    assert (tmp_path / "sweep_sobol_summary_chart.png").exists()
    assert (tmp_path / "sweep_sobol_summary_table.docx").exists()


def test_the_table_has_the_totals_and_the_interaction_as_median_and_iqr(tmp_path):
    source = tmp_path / "sweep_sobol_summary.csv"
    summary().to_csv(source, index=False)
    path = tmp_path / "table.docx"
    assert chart.main([str(source), "--output", str(tmp_path / "chart.png"),
                       "--table", str(path)]) == 0
    document = docx.Document(str(path))
    assert len(document.tables) == 1
    rows = cells(document.tables[0])
    assert rows[0] == ["KPI", "n", "ST of D", "ST of T", "Interaction D×T"]
    subscript = document.tables[0].rows[0].cells[2].paragraphs[0].runs[1]
    assert (subscript.text, subscript.font.subscript) == ("T", True)
    assert [row[0] for row in rows[1:]] == [
        "Thunderstorms", "Isolated flashes (%)", "Density (median)", "Diameter (median)",
        "Diameter (P90)", "Duration (median)"]
    # Thunderstorms (k = 0): totals 0.3 and 0.4, each with q1 0.1 below and q3 0.15 above.
    assert rows[1] == ["Thunderstorms", "14", "0.30 (0.20–0.45)", "0.40 (0.30–0.55)",
                       "0.20 (0.10–0.30)"]
    assert rows[6][2] == "0.35 (0.25–0.50)"


def test_the_table_in_catalan_has_decimal_commas():
    document = chart.table_document(summary(), language="ca")
    rows = cells(document.tables[0])
    assert rows[0] == ["KPI", "n", "ST de D", "ST de T", "Interacció D×T"]
    assert rows[1] == ["Tempestes", "14", "0,30 (0,20–0,45)", "0,40 (0,30–0,55)",
                       "0,20 (0,10–0,30)"]
    assert rows[2][0] == "Llamps aïllats (%)"


def test_a_kpi_without_episodes_has_dashes():
    data = summary()
    data.loc[data.statistic == "thunderstorms", ["n", "mean", "median", "q1", "q3", "iqr",
                                                 "min", "max"]] = [0] + [None] * 7
    rows = cells(chart.table_document(data).tables[0])
    assert rows[1] == ["Thunderstorms", "0", "—", "—", "—"]


def test_four_parameters_make_two_tables_the_wide_one_on_two_lines():
    data = summary(parameters=["attraction_radius_km", "max_waiting_time_min", "inertia",
                               "time_distance_limit_min_km"])
    document = chart.table_document(data)
    totals, interactions = document.tables
    assert cells(totals)[0] == ["KPI", "n", "ST of R", "ST of T", "ST of I", "ST of C"]
    assert cells(interactions)[0] == ["KPI", "n", "Interaction R×T", "Interaction R×I",
                                      "Interaction R×C", "Interaction T×I", "Interaction T×C",
                                      "Interaction I×C"]
    assert cells(totals)[1][2] == "0.30 (0.20–0.45)"
    assert cells(interactions)[1][2] == "0.20\n(0.10–0.30)"
    headings = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    assert headings == [chart.LABELS["en"]["totals"], chart.LABELS["en"]["interactions"]]


def test_the_table_is_16_cm_wide_in_nimbus_sans_8_pt():
    document = chart.table_document(summary())
    normal = document.styles["Normal"].font
    assert (normal.name, normal.size) == ("Nimbus Sans", docx.shared.Pt(8))
    widths = [cell.width for cell in document.tables[0].rows[0].cells]
    assert sum(widths) == pytest.approx(docx.shared.Cm(16), abs=docx.shared.Cm(0.01))
    # The table's grid too: LibreOffice and Word lay a table out by its columns.
    grid = [column.width for column in document.tables[0].columns]
    assert grid == widths
    assert grid[0] == pytest.approx(docx.shared.Cm(chart.KPI_COLUMN_CM), abs=docx.shared.Cm(0.01))
