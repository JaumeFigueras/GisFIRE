#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the boundary pieces shared by the lightning imports.

The country of each stroke is looked up in the OCHA boundaries, clipped to the
box the strokes can fall in and cut into small pieces once per run
(:func:`~src.apps.imports.lightnings.common.ensure_boundary_pieces`). What is
pinned down: the box (the provider's area joined with the strokes, plus a
margin, within the globe); that the pieces are cut once and reused while the box
needed is inside the one cut; that they are cut again, over both boxes, when it
is not, so no stroke can lose its country to the clipping; that they follow the
transaction; and that a country is clipped to the box and left out when only its
bounding box touches it.
"""

import logging

from dataclasses import dataclass

import pytest

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.lightnings import common
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import ocha

log = logging.getLogger("test-lightning-common")

TABLE = "test_boundary_pieces"


@dataclass
class Point:
    longitude: float
    latitude: float


@pytest.fixture
def database(postgresql):
    """An empty GisFIRE schema on an ephemeral PostgreSQL."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def boundaries(database):
    """Three OCHA countries; the provider's id.

    ``Wide`` runs from 0 to 40 E, ``Small`` is a square at 20-21 E, and ``Islands``
    is two squares far west and far east, so its bounding box covers everything.
    """
    with Session(database) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        for code, wkt in (
                ("Wide", "MULTIPOLYGON(((0 50, 40 50, 40 60, 0 60, 0 50)))"),
                ("Small", "MULTIPOLYGON(((20 55, 21 55, 21 56, 20 56, 20 55)))"),
                ("Islands", "MULTIPOLYGON(((-60 55, -59 55, -59 56, -60 56, -60 55)),"
                            "((80 55, 81 55, 81 56, 80 56, 80 55)))")):
            session.add(AdminBoundary(data_provider_id=provider.id, source_id=code, level=0,
                                      name=code, geometry=f"SRID=4326;{wkt}"))
        session.commit()
        return provider.id


def pieces(connection) -> tuple[list[str], float, float]:
    """The countries in the pieces, and the pieces' west and east edges."""
    return connection.execute(text(
        f"SELECT array_agg(DISTINCT b.name ORDER BY b.name), min(ST_XMin(p.geometry)), "
        f"max(ST_XMax(p.geometry)) FROM {TABLE} p JOIN admin_boundary b ON b.id = p.admin_boundary_id")).one()


# --------------------------------------------------------------------------
# The box
# --------------------------------------------------------------------------

def test_the_box_is_the_area_plus_the_margin():
    assert common.clipping_box((10, 50, 20, 60), [], 1.0) == {
        "xmin": 9.0, "ymin": 49.0, "xmax": 21.0, "ymax": 61.0}


def test_the_box_takes_in_strokes_outside_the_area():
    box = common.clipping_box((10, 50, 20, 60), [Point(25.0, 55.0), Point(12.0, 48.0)], 1.0)
    assert box == {"xmin": 9.0, "ymin": 47.0, "xmax": 26.0, "ymax": 61.0}


def test_the_box_stays_on_the_globe():
    assert common.clipping_box((-179.5, -89.5, 179.5, 89.5), [], 1.0) == {
        "xmin": -180.0, "ymin": -90.0, "xmax": 180.0, "ymax": 90.0}


# --------------------------------------------------------------------------
# The pieces
# --------------------------------------------------------------------------

def test_a_country_is_clipped_and_one_touching_only_by_its_box_left_out(database, boundaries):
    box = common.clipping_box((10, 52, 30, 58), [], 1.0)
    with database.connect() as connection, connection.begin():
        assert common.ensure_boundary_pieces(connection, TABLE, boundaries, box, log) is True
        names, west, east = pieces(connection)
    assert names == ["Small", "Wide"]
    assert (west, east) == (9.0, 31.0)


def test_the_pieces_are_reused_while_the_box_is_inside_the_one_cut(database, boundaries):
    with database.connect() as connection, connection.begin():
        assert common.ensure_boundary_pieces(
            connection, TABLE, boundaries, common.clipping_box((10, 52, 30, 58), [], 1.0), log)
        assert not common.ensure_boundary_pieces(
            connection, TABLE, boundaries, common.clipping_box((15, 53, 25, 57), [], 1.0), log)


def test_a_box_reaching_further_cuts_them_again_over_both(database, boundaries):
    """A later period with strokes outside the box: no stroke may lose its country."""
    with database.connect() as connection, connection.begin():
        common.ensure_boundary_pieces(
            connection, TABLE, boundaries, common.clipping_box((10, 52, 30, 58), [], 1.0), log)
        further = common.clipping_box((10, 52, 30, 58), [Point(35.0, 55.0)], 1.0)
        assert common.ensure_boundary_pieces(connection, TABLE, boundaries, further, log) is True
        _, west, east = pieces(connection)
        box = connection.execute(text(f"SELECT west, south, east, north FROM {TABLE}_box")).one()
    assert (west, east) == (9.0, 36.0)
    assert tuple(box) == (9.0, 51.0, 36.0, 59.0)


def test_the_pieces_follow_the_transaction(database, boundaries):
    box = common.clipping_box((10, 52, 30, 58), [], 1.0)
    with database.connect() as connection:
        with connection.begin() as transaction:
            assert common.ensure_boundary_pieces(connection, TABLE, boundaries, box, log)
            transaction.rollback()
        with connection.begin():
            assert not common.pieces_exist(connection, TABLE)
        with connection.begin():
            assert common.ensure_boundary_pieces(connection, TABLE, boundaries, box, log)
        with connection.begin():
            assert common.pieces_exist(connection, TABLE)
            common.drop_boundary_pieces(connection, TABLE)
        with connection.begin():
            assert not common.pieces_exist(connection, TABLE)


def test_with_no_boundary_provider_the_pieces_are_empty(database, boundaries):
    with database.connect() as connection, connection.begin():
        common.ensure_boundary_pieces(
            connection, TABLE, None, common.clipping_box((10, 52, 30, 58), [], 1.0), log)
        assert connection.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 0


# --------------------------------------------------------------------------
# Across the antimeridian
# --------------------------------------------------------------------------

#: An area crossing 180, written past it as ``alaska_uswfs.NETWORK_AREA`` is:
#: 168.8 E to 96.9 W.
ACROSS = (168.8, 46.1, 263.1, 79.4)


def test_a_stroke_across_180_joins_the_box_in_the_area_frame():
    """A stroke at 170 W is 190 in the area's frame, inside it: the box does not
    become the whole globe, as the least and greatest longitude would make it."""
    box = common.clipping_box(ACROSS, [Point(-170.0, 60.0), Point(175.0, 55.0)], 1.0)
    assert box == pytest.approx({"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4})


def test_a_stroke_past_the_area_widens_the_box_on_its_side():
    box = common.clipping_box(ACROSS, [Point(166.0, 60.0), Point(-90.0, 60.0)], 1.0)
    assert box == pytest.approx({"xmin": 165.0, "ymin": 45.1, "xmax": 271.0, "ymax": 80.4})


def test_the_usual_areas_keep_their_frame():
    """MeteoCat's and FMI's boxes are what they were before the frame existed."""
    assert common.clipping_box((-6.5, 35.6, 9.5, 47.1), [Point(-7.0, 40.0)], 1.0) == \
        pytest.approx({"xmin": -8.0, "ymin": 34.6, "xmax": 10.5, "ymax": 48.1})


@pytest.mark.parametrize(("box", "expected"), [
    pytest.param({"xmin": 9.0, "ymin": 49.0, "xmax": 21.0, "ymax": 61.0},
                 [(9.0, 49.0, 21.0, 61.0)], id="one"),
    pytest.param({"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4},
                 [(167.8, 45.1, 180.0, 80.4), (-180.0, 45.1, -95.9, 80.4)], id="across-180"),
    pytest.param({"xmin": -185.0, "ymin": 50.0, "xmax": -170.0, "ymax": 60.0},
                 [(175.0, 50.0, 180.0, 60.0), (-180.0, 50.0, -170.0, 60.0)], id="across-minus-180"),
    pytest.param({"xmin": 190.0, "ymin": 50.0, "xmax": 200.0, "ymax": 60.0},
                 [(-170.0, 50.0, -160.0, 60.0)], id="past-180-only"),
    pytest.param({"xmin": -180.0, "ymin": -90.0, "xmax": 180.0, "ymax": 90.0},
                 [(-180.0, -90.0, 180.0, 90.0)], id="globe"),
])
def test_the_envelopes_of_a_box(box, expected):
    result = common.envelopes(box)
    assert len(result) == len(expected)
    for envelope, wanted in zip(result, expected):
        assert envelope == pytest.approx(wanted)


@pytest.mark.parametrize(("inner", "holds"), [
    pytest.param((170.0, 175.0), True, id="east-of-180"),
    pytest.param((-175.0, -160.0), True, id="west-of-180-other-frame"),
    pytest.param((185.0, 200.0), True, id="west-of-180-same-frame"),
    pytest.param((179.0, 181.0), True, id="across-180"),
    pytest.param((100.0, 110.0), False, id="outside"),
    pytest.param((-100.0, -90.0), False, id="past-east-edge"),
])
def test_a_box_across_180_holds_boxes_in_either_frame(inner, holds):
    outer = {"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4}
    box = {"xmin": inner[0], "ymin": 50.0, "xmax": inner[1], "ymax": 60.0}
    assert common.box_holds(outer, box) is holds


def test_a_box_never_holds_one_reaching_further_north_or_south():
    outer = {"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4}
    assert not common.box_holds(outer, {"xmin": 170.0, "ymin": 40.0, "xmax": 175.0, "ymax": 60.0})


def test_the_globe_holds_everything():
    globe = {"xmin": -180.0, "ymin": -90.0, "xmax": 180.0, "ymax": 90.0}
    assert common.box_holds(globe, {"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4})


def test_the_union_across_180_stays_in_the_first_frame():
    first = {"xmin": 167.8, "ymin": 45.1, "xmax": 264.1, "ymax": 80.4}
    second = {"xmin": -100.0, "ymin": 40.0, "xmax": -90.0, "ymax": 50.0}
    assert common.box_union(first, second) == pytest.approx(
        {"xmin": 167.8, "ymin": 40.0, "xmax": 270.0, "ymax": 80.4})


def test_the_union_goes_the_shorter_way_round():
    """0..170 and -170..-5: -170..170 (340°), not 0..355."""
    first = {"xmin": 0.0, "ymin": 0.0, "xmax": 170.0, "ymax": 10.0}
    second = {"xmin": -170.0, "ymin": 0.0, "xmax": -5.0, "ymax": 10.0}
    assert common.box_union(first, second) == {"xmin": -170.0, "ymin": 0.0, "xmax": 170.0, "ymax": 10.0}


def test_a_union_a_turn_wide_is_the_globe():
    """0..200 and -170..10 (190..370 in the first's frame) leave no gap."""
    first = {"xmin": 0.0, "ymin": 0.0, "xmax": 200.0, "ymax": 10.0}
    second = {"xmin": -170.0, "ymin": 0.0, "xmax": 10.0, "ymax": 10.0}
    assert common.box_union(first, second) == {"xmin": -180.0, "ymin": 0.0, "xmax": 180.0, "ymax": 10.0}


@pytest.fixture
def boundaries_across_180(database):
    """Countries round the antimeridian; the provider's id.

    ``Chukotka`` lies on both sides of 180; ``Alaska`` has a part in the box and a
    far one at 80-70 W that the box leaves out; ``Faraway`` is in Europe.
    """
    with Session(database) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        for code, wkt in (
                ("Chukotka", "MULTIPOLYGON(((170 60, 180 60, 180 70, 170 70, 170 60)),"
                             "((-180 60, -169 60, -169 70, -180 70, -180 60)))"),
                ("Alaska", "MULTIPOLYGON(((-168 55, -141 55, -141 71, -168 71, -168 55)),"
                           "((-80 30, -70 30, -70 40, -80 40, -80 30)))"),
                ("Faraway", "MULTIPOLYGON(((10 40, 20 40, 20 50, 10 50, 10 40)))")):
            session.add(AdminBoundary(data_provider_id=provider.id, source_id=code, level=0,
                                      name=code, geometry=f"SRID=4326;{wkt}"))
        session.commit()
        return provider.id


def extent_per_country(connection) -> dict[str, tuple[float, float, int]]:
    """Per country in the pieces: its least and greatest longitude, and its pieces."""
    rows = connection.execute(text(
        f"SELECT b.name, min(ST_XMin(p.geometry)), max(ST_XMax(p.geometry)), count(*) "
        f"FROM {TABLE} p JOIN admin_boundary b ON b.id = p.admin_boundary_id GROUP BY b.name"))
    return {name: (west, east, pieces) for name, west, east, pieces in rows}


def test_the_pieces_across_180_are_clipped_on_both_sides(database, boundaries_across_180):
    box = common.clipping_box(ACROSS, [], 1.0)
    with database.connect() as connection, connection.begin():
        assert common.ensure_boundary_pieces(connection, TABLE, boundaries_across_180, box, log)
        extents = extent_per_country(connection)
        east_side, west_side = connection.execute(text(
            f"SELECT count(*) FILTER (WHERE ST_XMin(p.geometry) >= 170), "
            f"count(*) FILTER (WHERE ST_XMax(p.geometry) <= -169) "
            f"FROM {TABLE} p JOIN admin_boundary b ON b.id = p.admin_boundary_id "
            f"WHERE b.name = 'Chukotka'")).one()
    assert set(extents) == {"Alaska", "Chukotka"}
    assert (east_side, west_side) == (1, 1)
    # Alaska's far part, at 80-70 W, is past the box's east edge (95.9 W).
    assert extents["Alaska"][:2] == (-168.0, -141.0)


def test_a_stroke_either_side_of_180_finds_its_country(database, boundaries_across_180):
    box = common.clipping_box(ACROSS, [], 1.0)
    with database.connect() as connection, connection.begin():
        common.ensure_boundary_pieces(connection, TABLE, boundaries_across_180, box, log)
        found = connection.execute(text(
            f"SELECT point.longitude, b.name FROM (VALUES (175.0), (-175.0), (-150.0)) "
            f"AS point (longitude) "
            f"JOIN {TABLE} p ON ST_Intersects(p.geometry, ST_SetSRID(ST_MakePoint(point.longitude, 65), 4326)) "
            f"JOIN admin_boundary b ON b.id = p.admin_boundary_id ORDER BY point.longitude")).all()
    assert [tuple(row) for row in found] == [(-175.0, "Chukotka"), (-150.0, "Alaska"),
                                            (175.0, "Chukotka")]


def test_the_pieces_across_180_are_reused_for_a_box_in_the_other_frame(database,
                                                                        boundaries_across_180):
    with database.connect() as connection, connection.begin():
        assert common.ensure_boundary_pieces(
            connection, TABLE, boundaries_across_180, common.clipping_box(ACROSS, [], 1.0), log)
        other_frame = {"xmin": -175.0, "ymin": 55.0, "xmax": -150.0, "ymax": 70.0}
        assert not common.ensure_boundary_pieces(
            connection, TABLE, boundaries_across_180, other_frame, log)


def test_the_pieces_are_cut_again_over_a_union_across_180(database, boundaries_across_180):
    """First a box from 170 E to 160 W, then strokes at 120 W: cut again over 169..241."""
    with database.connect() as connection, connection.begin():
        common.ensure_boundary_pieces(connection, TABLE, boundaries_across_180,
                                      common.clipping_box((170.0, 55.0, 200.0, 70.0), [], 1.0), log)
        assert set(extent_per_country(connection)) == {"Alaska", "Chukotka"}
        further = common.clipping_box((170.0, 55.0, 200.0, 70.0), [Point(-120.0, 60.0)], 1.0)
        assert common.ensure_boundary_pieces(connection, TABLE, boundaries_across_180, further, log)
        stored = connection.execute(text(f"SELECT west, south, east, north FROM {TABLE}_box")).one()
        extents = extent_per_country(connection)
    assert tuple(stored) == pytest.approx((169.0, 54.0, 241.0, 71.0))
    # Before, Alaska was cut at the box's edge, 159 W; now it is whole up to 141 W.
    assert extents["Alaska"][1] == -141.0
