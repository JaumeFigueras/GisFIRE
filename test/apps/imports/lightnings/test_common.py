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
