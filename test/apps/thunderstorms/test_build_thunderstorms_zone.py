#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the zone of the thunderstorm rules in the builder (rule 2).

The builder clusters the whole network's strokes, but by default stores only the
thunderstorms with at least one **zone flash**: a flash with any of its strokes
within 50 km of the network's nominal region (for MeteoCat, IGN's Catalonia).
``--all-storms`` stores every storm. The region here is a square of 40 km around
the Cellsearch tests' origin, so the zone reaches 70 km east of it.
"""

import datetime
import logging

import pytest

from sqlalchemy import text

from gisfire_algorithms.thunderstorm import CellsearchParameters
from src.apps.thunderstorms import build_thunderstorms as app

from .test_build_thunderstorms import ORIGIN
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

TIME_DISTANCE = "time_distance_galanaki"

#: IGN's Catalonia, as the episodes study's tests store it, here a square of 40 km.
INSERT_REGION_SQL = """
WITH provider AS (
    INSERT INTO data_provider (name, product, full_name)
    VALUES ('IGN', 'Base de Datos de Divisiones Administrativas de España test', 'IGN')
    RETURNING id
), boundary AS (
    INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry)
    SELECT 'ign_admin_boundary', provider.id, '34090000000', 1, 'Cataluña/Catalunya',
           ST_Multi(ST_Transform(ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 25831), 4326))
    FROM provider
    RETURNING id
)
INSERT INTO ign_admin_boundary (id, edition, kind)
SELECT boundary.id, 'test', 'comunidad_autonoma' FROM boundary
"""


@pytest.fixture
def catalonia(database):  # noqa: F811
    """The region: 20 km on each side of ORIGIN."""
    engine, _ = database
    with engine.begin() as connection:
        connection.execute(text(INSERT_REGION_SQL), {
            "xmin": ORIGIN[0] - 20_000.0, "ymin": ORIGIN[1] - 20_000.0,
            "xmax": ORIGIN[0] + 20_000.0, "ymax": ORIGIN[1] + 20_000.0})


@pytest.fixture
def three_storms(database, provider):  # noqa: F811
    """A in the region; B 150 km east, out of the zone; C 100 km east, out of the zone
    but for one inaccurate stroke of its first flash, 60 km east, in the zone."""
    engine, _ = database
    c = a_storm(300, minutes(240), 6, dx=100_000.0)
    reach = Stroke(minutes(240) + datetime.timedelta(seconds=2), 60_000.0, 0.0, 300, error=5_000.0)
    return add_strokes(engine, provider, a_storm(100, STORM, 6)
                       + a_storm(200, minutes(120), 6, dx=150_000.0) + c + [reach])


def run(url: str, *extra: str, zone: bool = True, **options) -> int:
    """The application with the time-distance clustering (N_min 1), the zone on."""
    return run_application(url, *extra, algorithm=TIME_DISTANCE, min_flashes=None, zone=zone,
                           **options)


def test_by_default_only_the_storms_with_a_zone_flash_are_stored(database, catalonia,  # noqa: F811
                                                                 three_storms):
    engine, url = database
    assert run(url) == 0
    storms = rows(engine, "SELECT label, number_of_flashes, number_of_lightnings FROM thunderstorm "
                          "ORDER BY label")
    # B (label 2) is dropped; its label stays out of the numbering.
    assert [tuple(storm) for storm in storms] == [(1, 6, 12), (3, 6, 13)]
    assert experiment(engine).summary["cells_outside_zone"] == 1


def test_a_storm_with_one_stroke_in_the_zone_is_stored_whole(database, catalonia,  # noqa: F811
                                                             three_storms):
    engine, url = database
    assert run(url) == 0
    linked = {row.lightning_id for row in rows(engine, """
        SELECT l.lightning_id FROM thunderstorm_lightning l
        JOIN thunderstorm t ON t.id = l.thunderstorm_id WHERE t.label = 3""")}
    assert linked == {stroke.id for stroke in three_storms[24:]}


def test_the_zone_is_part_of_the_configuration(database, catalonia, three_storms):  # noqa: F811
    engine, url = database
    assert run(url) == 0
    assert experiment(engine).lightning_filter == {
        "network": "newest", "cloud_to_ground": True,
        "zone": {"region": "34090000000", "buffer_km": 50.0}}
    configuration = app.experiment_configuration(7, "FMI", "cellsearch_tuomi_larjavaara",
                                                 CellsearchParameters(srid=3067),
                                                 STORM, STORM + datetime.timedelta(days=1))
    assert configuration["lightning_filter"] == {"cloud_to_ground": True,
                                                 "zone": {"region": "FIN", "buffer_km": 50.0}}


def test_all_storms_keeps_every_storm_as_another_experiment(database, catalonia,  # noqa: F811
                                                            three_storms):
    engine, url = database
    assert run(url, zone=False) == 0
    every = experiment(engine)
    assert every.lightning_filter == {"network": "newest", "cloud_to_ground": True}
    assert "cells_outside_zone" not in every.summary
    assert count(engine, "thunderstorm") == 3
    assert run(url) == 0
    assert count(engine, "thunderstorm_experiment") == 2
    assert count(engine, "thunderstorm") == 5


def test_a_run_without_its_region_is_refused(database, three_storms, caplog):  # noqa: F811
    engine, url = database
    with caplog.at_level(logging.ERROR):
        assert run(url) == 1
    assert "IGN's Catalonia" in caplog.text
    assert "--all-storms" in caplog.text
    assert count(engine, "thunderstorm_experiment") == 0


def test_cellsearch_stores_the_flashes_of_the_zone_storms_only(database, catalonia,  # noqa: F811
                                                               three_storms):
    engine, url = database
    assert run_application(url, zone=True) == 0          # Cellsearch, N_min 5
    assert [row.label for row in rows(engine, "SELECT label FROM thunderstorm ORDER BY label")] == \
        [1, 3]
    assert count(engine, "thunderstorm_cellsearch_flash") == 12
    assert experiment(engine).summary["cells_outside_zone"] == 1
