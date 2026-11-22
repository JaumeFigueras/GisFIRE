#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the thunderstorm builder with the time-distance clustering (Galanaki et al. 2018).

The core is tested on its own in ``test/algorithms``; what is pinned down here
is what the adapter adds for this algorithm: every cluster stored (one flash
included), every stroke linked, the area of the concave hull, the summary, the
window flags and the flags of the command line. The database, the synthetic
MeteoCat strokes and the helpers are the Cellsearch tests' own.
"""

import datetime
import logging
import math

import pytest

from sqlalchemy import text

from gisfire_algorithms.thunderstorm import TimeDistanceParameters
from src.apps.thunderstorms import build_thunderstorms as app
from src.apps.thunderstorms import readers

from .test_build_thunderstorms import DAY
from .test_build_thunderstorms import NEXT_DAY
from .test_build_thunderstorms import STORM
from .test_build_thunderstorms import Stroke
from .test_build_thunderstorms import a_storm
from .test_build_thunderstorms import add_strokes
from .test_build_thunderstorms import count
from .test_build_thunderstorms import database  # noqa: F401  (fixture)
from .test_build_thunderstorms import experiment
from .test_build_thunderstorms import minutes
from .test_build_thunderstorms import provider  # noqa: F401  (fixture)
from .test_build_thunderstorms import rows
from .test_build_thunderstorms import run as run_application
from .test_build_thunderstorms import scalar

ALGORITHM = "time_distance_galanaki"

#: A hexagon of radius 2 km: the hull of a storm of six flashes from ``a_storm``.
HEXAGON_KM2 = 3.0 * math.sqrt(3.0) / 2.0 * 2.0 ** 2


def run(url: str, *extra: str, **options) -> int:
    """The application with this algorithm and its default N_min."""
    return run_application(url, *extra, algorithm=ALGORITHM, min_flashes=None, **options)


@pytest.fixture
def three_storms(database, provider):  # noqa: F811
    """A: 6 flashes. B, 50 km east, 2 h later: 2 flashes. C, 100 km west, 4 h later: 1 flash."""
    engine, _ = database
    return add_strokes(engine, provider,
                       a_storm(100, STORM, 6) + a_storm(200, minutes(120), 2, dx=50_000.0)
                       + a_storm(300, minutes(240), 1, dx=-100_000.0))


# --------------------------------------------------------------------------
# A run is stored
# --------------------------------------------------------------------------

def test_a_run_stores_every_cluster_even_of_one_flash(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    storms = rows(engine, "SELECT * FROM thunderstorm ORDER BY label")
    assert [(storm.label, storm.number_of_flashes, storm.number_of_lightnings)
            for storm in storms] == [(1, 6, 12), (2, 2, 4), (3, 1, 2)]
    assert (storms[0].date_time_start, storms[0].date_time_end) == (
        STORM, minutes(20) + datetime.timedelta(seconds=1))


def test_every_stroke_of_a_flash_is_linked_to_its_cluster(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    linked = rows(engine, """
        SELECT t.label, array_agg(l.lightning_id ORDER BY l.lightning_id) AS ids
        FROM thunderstorm t JOIN thunderstorm_lightning l ON l.thunderstorm_id = t.id
        GROUP BY t.label ORDER BY t.label""")
    ids = [stroke.id for stroke in three_storms]
    assert [(row.label, row.ids) for row in linked] == [(1, ids[:12]), (2, ids[12:16]),
                                                        (3, ids[16:])]


def test_the_area_is_the_concave_hulls_in_the_projected_crs(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    area, hull_km2, vertices = rows(engine, """
        SELECT area, ST_Area(ST_Transform(concave_hull, 25831)) / 1e6, ST_NPoints(concave_hull)
        FROM thunderstorm WHERE label = 1""")[0]
    assert vertices == 7  # the six representative strokes, closed
    assert area == pytest.approx(hull_km2, rel=1e-6)
    assert area == pytest.approx(HEXAGON_KM2, rel=1e-3)


def test_a_cluster_of_one_or_two_flashes_has_no_hull_and_no_area(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    small = rows(engine, "SELECT concave_hull, area FROM thunderstorm WHERE label > 1")
    assert [(storm.concave_hull, storm.area) for storm in small] == [(None, None), (None, None)]


def test_the_experiment_is_complete_with_its_configuration(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    stored = experiment(engine)
    assert stored.status == "complete"
    assert stored.algorithm == "TIME_DISTANCE_GALANAKI_2018"
    assert stored.parameters == TimeDistanceParameters().to_dict()
    assert stored.lightning_filter == {"network": "newest", "cloud_to_ground": True}
    assert stored.hull_parameters == {"ratio": 0.3, "allow_holes": False, "srid": 25831}
    assert (stored.date_time_start, stored.date_time_end) == (DAY, NEXT_DAY)


def test_the_summary_counts_clusters_flashes_and_strokes(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    assert experiment(engine).summary == {
        "flashes_total": 9, "flashes_kept": 9, "cells_total": 3, "cells_kept": 3,
        "strokes_total": 18, "cells_open_at_end": 0, "activity_before_start": False}


def test_n_min_keeps_only_the_large_clusters(database, three_storms):  # noqa: F811
    engine, url = database
    assert run(url, "--min-flashes", "3") == 0
    assert [row.label for row in rows(engine, "SELECT label FROM thunderstorm")] == [1]
    stored = experiment(engine)
    assert stored.parameters["min_flashes"] == 3
    assert (stored.summary["cells_kept"], stored.summary["flashes_kept"]) == (1, 6)


@pytest.mark.parametrize("extra, clusters", [
    ((), 1),
    (("--max-distance", "5"), 2),
    (("--max-time-difference", "5"), 2),
])
def test_the_limits_given_are_the_ones_run_and_stored(database, provider, extra,  # noqa: F811
                                                      clusters):
    """Two flashes 8 km and 10 min apart: one cluster with the defaults."""
    engine, url = database
    add_strokes(engine, provider, [Stroke(STORM, 0.0, 0.0, 1), Stroke(minutes(10), 8_000.0, 0.0, 2)])
    assert run(url, *extra) == 0
    assert count(engine, "thunderstorm") == clusters
    parameters = experiment(engine).parameters
    assert parameters["max_distance_km"] == (5.0 if "--max-distance" in extra else 10.0)
    assert parameters["max_time_difference_min"] == (5.0 if "--max-time-difference" in extra
                                                     else 16.0)


# --------------------------------------------------------------------------
# Window truncation and pieces
# --------------------------------------------------------------------------

def test_a_storm_across_the_end_of_the_window_is_flagged(database, three_storms, caplog):  # noqa: F811
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, end=minutes(10)) == 0
    assert experiment(engine).summary["cells_open_at_end"] == 1
    assert "may have been cut" in caplog.text


def test_a_cluster_quiet_for_longer_than_t_before_the_end_is_not_flagged(database,  # noqa: F811
                                                                          three_storms):
    """Storm A's last flash is at 14:20 and T is 16 min: at 14:36:01 nothing can join it."""
    engine, url = database
    assert run(url, end=minutes(36) + datetime.timedelta(seconds=1)) == 0
    assert experiment(engine).summary["cells_open_at_end"] == 0


def test_activity_just_before_the_window_is_flagged(database, three_storms, caplog):  # noqa: F811
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, start=minutes(10)) == 0
    assert experiment(engine).summary["activity_before_start"] is True
    assert "before the start" in caplog.text


def test_activity_longer_than_t_before_the_window_is_not_flagged(database, provider):  # noqa: F811
    engine, url = database
    add_strokes(engine, provider, [Stroke(minutes(-17), 0.0, 0.0, 1)] + a_storm(100, STORM, 6))
    assert run(url, start=STORM) == 0
    assert experiment(engine).summary["activity_before_start"] is False


def test_running_in_pieces_gives_the_same_result(database, provider, monkeypatch):  # noqa: F811
    """Three storms more than T apart: one piece each, or all in one."""
    engine, url = database
    add_strokes(engine, provider, a_storm(100, STORM, 6) + a_storm(200, minutes(60), 7, dx=3_000.0)
                + a_storm(300, minutes(120), 8, dx=-4_000.0))
    query = """
        SELECT t.label, t.number_of_flashes, t.number_of_lightnings, t.area,
               ST_AsText(t.concave_hull) AS hull,
               array_agg(l.lightning_id ORDER BY l.lightning_id) AS strokes
        FROM thunderstorm t JOIN thunderstorm_lightning l ON l.thunderstorm_id = t.id
        GROUP BY t.id ORDER BY t.label"""
    assert run(url) == 0
    whole = rows(engine, query)
    summary = experiment(engine).summary
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM thunderstorm_experiment"))

    monkeypatch.setattr(app, "PIECE_STROKES", 1)
    monkeypatch.setattr(readers, "FETCH_SIZE", 5)
    assert run(url) == 0
    assert rows(engine, query) == whole
    assert experiment(engine).summary == summary
    assert [row.label for row in whole] == [1, 2, 3]


def test_the_progress_counts_flashes(database, three_storms, monkeypatch, caplog):  # noqa: F811
    """One batch of strokes is cut at its last quiet gap: A and B, then C."""
    engine, url = database
    monkeypatch.setattr(app, "PIECE_STROKES", 1)
    monkeypatch.setattr(app, "PROGRESS_EVERY", 6)
    with caplog.at_level(logging.INFO):
        assert run(url) == 0
    assert "16 stroke(s), 8 flash(es) so far, 2 thunderstorm(s) stored" in caplog.text
    assert "over 2 piece(s)" in caplog.text
    assert scalar(engine, "SELECT count(*) FROM thunderstorm") == 3


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

BASE_ARGUMENTS = ["--from", "2020-07-13", "--to", "2020-07-14", "--algorithm", ALGORITHM]


def test_the_flags_come_from_the_parameters_dataclass():
    args = app.parse_arguments(["--provider", "MeteoCat", *BASE_ARGUMENTS, "--max-distance", "5",
                                "--max-time-difference", "20", "--min-flashes", "3",
                                "--srid", "3035"])
    assert app.parameters_from(args, app.ALGORITHMS[ALGORITHM]) == TimeDistanceParameters(
        5.0, 20.0, 3, 3035)


@pytest.mark.parametrize("provider_name, srid", [("MeteoCat", 25831), ("FMI", 3067),
                                                 ("USWFS", 3338)])
def test_without_flags_the_parameters_are_the_defaults_in_the_providers_crs(provider_name, srid):
    args = app.parse_arguments(["--provider", provider_name, *BASE_ARGUMENTS])
    assert app.parameters_from(args, app.ALGORITHMS[ALGORITHM]) == TimeDistanceParameters(
        srid=srid)


def test_an_invalid_parameter_is_refused(database, three_storms, caplog):  # noqa: F811
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url, "--min-flashes", "0") == 1
    assert "min_flashes must be at least 1" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 0
