#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The convergence of the Sobol indices' medians over the episodes, drawn off-screen."""

import itertools
import struct

import matplotlib
import numpy as np
import pandas as pd
import pytest

from matplotlib import font_manager
from matplotlib.colors import to_rgba

from gisfire_experiments.thunderstorms import sobol_convergence as convergence
from gisfire_experiments.thunderstorms import sobol_indices
from gisfire_experiments.thunderstorms.sobol_chart import KPIS
from gisfire_experiments.thunderstorms.sweep import STATISTIC_COLUMNS

matplotlib.use("Agg")

PARAMETERS = ["max_distance_km", "max_time_difference_min"]
CELLSEARCH = ["attraction_radius_km", "max_waiting_time_min", "inertia",
              "time_distance_limit_min_km"]

#: The total indices of D and T, one per episode: their running medians are
#: D 0.2, 0.4, 0.4, 0.5 and T 0.9, 0.5, 0.5, 0.4.
TOTALS = {"max_distance_km": [0.2, 0.6, 0.4, 0.8],
          "max_time_difference_min": [0.9, 0.1, 0.5, 0.3]}

#: Out of numeric order, as an extract of the episodes study is.
EPISODES = [170, 577, 29, 606]


def per_episode(totals=TOTALS, episodes=EPISODES, statistics=KPIS) -> pd.DataFrame:
    """A ``_sobol.csv`` as ``sobol_indices`` writes it: for each episode, in order, and
    statistic, every index; a parameter's total index is ``totals[parameter][episode]``,
    its first-order index half of it and every interaction 0.1."""
    parameters = list(totals)
    rows = []
    for e, episode in enumerate(episodes):
        for statistic in statistics:
            for index, names in sobol_indices.index_keys(parameters):
                value = {"total": totals.get(names, [0.0] * len(episodes))[e],
                         "first_order": totals.get(names, [0.0] * len(episodes))[e] / 2.0,
                         "interaction": 0.1}[index]
                rows.append({"episode": episode, "statistic": statistic, "index": index,
                             "parameters": names, "value": value})
    return pd.DataFrame(rows, columns=sobol_indices.INDEX_COLUMNS)


def y_span(ax, patch) -> tuple[float, float]:
    """The band's lower and upper limits, in the axis's units."""
    y = ax.transData.inverted().transform(patch.get_verts())[:, 1]
    return float(y.min()), float(y.max())


def x_span(ax, patch) -> tuple[float, float]:
    """The band's left and right ends, as fractions of the panel's width."""
    x = ax.transAxes.inverted().transform(patch.get_verts())[:, 0]
    return float(x.min()), float(x.max())


# --- the running medians ------------------------------------------------------------

def test_the_kth_point_is_the_median_of_the_first_k_episodes_in_the_files_order():
    frame = convergence.running_medians(per_episode(), "thunderstorms")
    assert list(frame.columns) == PARAMETERS
    assert list(frame.index) == [1, 2, 3, 4]
    # In the file's order (170, 577, 29, 606), not by id: by id D would give 0.4, 0.3, ...
    assert frame["max_distance_km"].tolist() == pytest.approx([0.2, 0.4, 0.4, 0.5])
    assert frame["max_time_difference_min"].tolist() == pytest.approx([0.9, 0.5, 0.5, 0.4])


def test_an_episode_left_out_of_one_kpi_is_left_out_of_its_curve_only():
    data = per_episode()
    data = data[~((data.episode == 577) & (data.statistic == "diameter_median_km"))]
    diameter = convergence.running_medians(data, "diameter_median_km")
    assert diameter["max_distance_km"].tolist() == pytest.approx([0.2, 0.3, 0.4])
    assert len(convergence.running_medians(data, "thunderstorms")) == 4
    figure = convergence.chart(data)
    titles = [ax.get_title().splitlines()[-1] for ax in figure.axes]
    assert titles == ["n = 4", "n = 4", "n = 4", "n = 3", "n = 4", "n = 4"]
    assert figure.axes[3].lines[0].get_xdata().tolist() == [1, 2, 3]


def test_the_last_point_is_the_median_of_the_summary():
    rng = np.random.default_rng(7)
    weights = {episode: rng.uniform(0.1, 1.0, size=3) for episode in (5, 2, 9, 4, 1)}
    rows = []
    for episode, (u, v, w) in weights.items():
        for number, (d, t) in enumerate(itertools.product([5, 10, 15], [5, 10, 20]), start=1):
            value = u * d + v * t + w * d * t
            rows.append({"episode": episode, "start": "2018-07-03T00:00:00+00:00",
                         "end": "2018-07-04T00:00:00+00:00", "experiment_id": number,
                         "max_distance_km": d, "max_time_difference_min": t,
                         **{name: value for name in STATISTIC_COLUMNS}})
    indices, summary = sobol_indices.analyse(pd.DataFrame(rows))
    indices = pd.DataFrame(indices, columns=sobol_indices.INDEX_COLUMNS)
    summary = pd.DataFrame(summary)
    for kpi in KPIS:
        last = convergence.running_medians(indices, kpi).iloc[-1]
        for name in PARAMETERS:
            median = summary.loc[(summary.statistic == kpi) & (summary["index"] == "total")
                                 & (summary.parameters == name), "median"].item()
            assert last[name] == pytest.approx(median)


# --- the figure ---------------------------------------------------------------------

def test_six_panels_in_two_rows_in_the_kpi_order_sharing_a_0_to_1_axis():
    figure = convergence.chart(per_episode())
    axes = figure.axes
    assert len(axes) == 6
    assert [ax.get_subplotspec().rowspan.start for ax in axes] == [0, 0, 0, 1, 1, 1]
    assert [ax.get_title().splitlines()[0] for ax in axes] == [
        "Thunderstorms", "Isolated flashes (%)", "Density (median)", "Diameter (median)",
        "Diameter (P90)", "Duration (median)"]
    assert all(ax.get_title().splitlines()[-1] == "n = 4" for ax in axes)
    assert all(ax.get_ylim() == (0.0, 1.0) for ax in axes)
    # From the first episode to the last, with half an episode on each side (no 0).
    assert all(ax.get_xlim() == (0.5, 4.5) for ax in axes)
    assert [ax.get_ylabel() for ax in axes] == [convergence.LABELS["en"]["y"], "", "",
                                                convergence.LABELS["en"]["y"], "", ""]
    assert [ax.get_xlabel() for ax in axes] == ["", "", "", "Episodes", "Episodes", "Episodes"]


def test_each_panel_draws_the_running_median_of_each_parameter():
    figure = convergence.chart(per_episode())
    for ax in figure.axes:
        distance, time = ax.lines
        assert distance.get_xdata().tolist() == [1, 2, 3, 4]
        assert distance.get_ydata().tolist() == pytest.approx([0.2, 0.4, 0.4, 0.5])
        assert time.get_ydata().tolist() == pytest.approx([0.9, 0.5, 0.5, 0.4])
        assert (distance.get_color(), distance.get_linestyle()) == ("#2a78d6", "-")
        assert (time.get_color(), time.get_linestyle()) == ("#eb6834", "-")
        assert distance.get_marker() == time.get_marker() == "o"


def test_four_parameters_have_four_colours_all_solid():
    totals = {name: [0.1 * (p + 1)] * 4 for p, name in enumerate(CELLSEARCH)}
    figure = convergence.chart(per_episode(totals=totals))
    lines = figure.axes[0].lines
    assert [line.get_color() for line in lines] == ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    assert [line.get_linestyle() for line in lines] == ["-"] * 4
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        "R", "T", "I", "C", convergence.LABELS["en"]["band"]]


def test_a_band_of_plus_minus_0_025_around_each_last_value_behind_its_line():
    assert convergence.BAND == 0.025
    figure = convergence.chart(per_episode())
    for ax in figure.axes:
        distance, time = ax.patches
        assert y_span(ax, distance) == pytest.approx((0.475, 0.525))
        assert y_span(ax, time) == pytest.approx((0.375, 0.425))
        assert x_span(ax, distance) == pytest.approx((0.0, 1.0))
        assert distance.get_facecolor() == pytest.approx(to_rgba("#2a78d6", convergence.BAND_ALPHA))
        assert time.get_facecolor() == pytest.approx(to_rgba("#eb6834", convergence.BAND_ALPHA))
        assert distance.get_zorder() < ax.lines[0].get_zorder()


def test_a_band_stops_at_the_axis_ends():
    figure = convergence.chart(per_episode(totals={"max_distance_km": [1.0] * 4,
                                                   "max_time_difference_min": [0.01] * 4}))
    ax = figure.axes[0]
    assert y_span(ax, ax.patches[0]) == pytest.approx((0.975, 1.0))
    assert y_span(ax, ax.patches[1]) == pytest.approx((0.0, 0.035))


def test_the_legend_names_the_parameters_and_the_band():
    figure = convergence.chart(per_episode())
    assert [text.get_text() for text in figure.legends[0].get_texts()] == [
        "D", "T", "Final median ± 0.025"]


def test_a_kpi_without_episodes_draws_an_empty_panel_with_n_0():
    data = per_episode()
    ax = convergence.chart(data[data.statistic != "duration_median_min"]).axes[-1]
    assert ax.get_title().splitlines()[-1] == "n = 0"
    assert (len(ax.lines), len(ax.patches)) == (0, 0)


def test_the_labels_can_be_catalan():
    figure = convergence.chart(per_episode(), language="ca")
    assert [ax.get_title().splitlines()[0] for ax in figure.axes] == [
        "Tempestes", "Llamps aïllats (%)", "Densitat (mediana)", "Diàmetre (mediana)",
        "Diàmetre (P90)", "Durada (mediana)"]
    assert figure.axes[0].get_ylabel() == convergence.LABELS["ca"]["y"]
    assert figure.axes[3].get_xlabel() == "Episodis"
    assert [text.get_text() for text in figure.legends[0].get_texts()][-1] == \
        "Mediana final ± 0,025"


def test_the_text_is_in_nimbus_sans():
    try:
        font_manager.findfont(font_manager.FontProperties(family=convergence.FONT),
                              fallback_to_default=False)
    except ValueError:
        pytest.skip("Nimbus Sans is not installed")
    figure = convergence.chart(per_episode())
    assert figure.axes[0].title.get_fontname() == "Nimbus Sans"


# --- the file -----------------------------------------------------------------------

def png_size(path) -> tuple[int, int, float]:
    """Width and height in pixels, and resolution in dots per inch, from the PNG's chunks."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    at = data.index(b"pHYs")
    per_metre = struct.unpack(">I", data[at + 4:at + 8])[0]
    return width, height, per_metre * 0.0254


def test_the_png_is_16_by_10_cm_at_600_dpi(tmp_path):
    source = tmp_path / "time_distance_galanaki_MeteoCat_catalunya-100-q1_sobol.csv"
    per_episode().to_csv(source, index=False)
    output = tmp_path / "figure.png"
    assert convergence.main([str(source), "--output", str(output)]) == 0
    width, height, dpi = png_size(output)
    assert (width, height) == (round(16.0 / 2.54 * 600), round(10.0 / 2.54 * 600))
    assert dpi == pytest.approx(600.0, abs=0.1)


def test_the_png_goes_beside_the_file_by_default(tmp_path):
    source = tmp_path / "sweep_sobol.csv"
    per_episode().to_csv(source, index=False)
    assert convergence.main([str(source), "--language", "ca"]) == 0
    assert (tmp_path / "sweep_sobol_convergence.png").exists()


def test_a_file_that_is_not_per_episode_is_refused(tmp_path, caplog):
    source = tmp_path / "sweep_sobol_summary.csv"
    pd.DataFrame(columns=sobol_indices.SUMMARY_COLUMNS).to_csv(source, index=False)
    assert convergence.main([str(source)]) == 1
    assert "_sobol.csv" in caplog.text
    assert not (tmp_path / "sweep_sobol_summary_convergence.png").exists()
