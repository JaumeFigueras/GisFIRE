#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The zone of the thunderstorm rules: a network's nominal region plus 50 km.

The region is read from the database by the builder's and the sweep's tests
(and by the episodes study's); these tests pin down the zone test itself.
"""

import shapely

from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from src.apps.thunderstorms import zones
from src.apps.thunderstorms.readers import READERS

#: A region of 10 × 10 km, in metres of some projected CRS.
REGION = shapely.box(0.0, 0.0, 10_000.0, 10_000.0)


def test_the_zone_reaches_50_km_from_the_region_inclusive():
    x = [5_000.0, 60_000.0, 60_000.001, -50_000.0, 5_000.0]
    y = [5_000.0, 5_000.0, 5_000.0, 5_000.0, -50_000.001]
    assert zones.ZONE_BUFFER_M == 50_000.0
    assert zones.in_zone(REGION, x, y).tolist() == [True, True, False, True, False]


def test_a_flash_is_in_the_zone_with_any_of_its_strokes():
    strokes = Strokes(
        ids=[1, 2, 3, 4, 5],
        flash_keys=[10, 10, 20, 20, 30],
        t=[0.0, 1.0, 60.0, 61.0, 120.0],
        # Flash 10: its accurate stroke (its representative) far away, the other in the
        # zone. Flash 20: both far away. Flash 30: in the region.
        x=[200_000.0, 55_000.0, 200_000.0, 210_000.0, 5_000.0],
        y=[5_000.0] * 5,
        error=[100.0, 900.0, 100.0, 900.0, 100.0])
    flashes = strokes_to_flashes(strokes)
    inside = zones.in_zone(REGION, strokes.x, strokes.y)
    assert inside.tolist() == [False, True, False, False, True]
    assert zones.zone_stroke_counts(flashes, inside).tolist() == [1, 0, 1]


def test_no_strokes_no_zone_flashes():
    flashes = strokes_to_flashes(Strokes(ids=[], flash_keys=[], t=[], x=[], y=[], error=[]))
    assert zones.in_zone(REGION, [], []).tolist() == []
    assert zones.zone_stroke_counts(flashes, zones.in_zone(REGION, [], [])).tolist() == []


def test_every_network_has_its_nominal_region():
    assert set(zones.REGIONS) == set(READERS)
    assert {name: region.value for name, region in zones.REGIONS.items()} == {
        "FMI": "FIN", "MeteoCat": "34090000000", "USWFS": "02"}
