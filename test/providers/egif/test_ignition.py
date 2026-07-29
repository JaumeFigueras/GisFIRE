#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`EgifIgnition` model.

Two things matter here. The published coordinate has to survive as the numbers
EGIF printed — that is what is stored instead of a geometry in the source CRS —
and the zone and datum have to be constrained, because a transcription error in
either puts the reprojected point in the wrong country.
"""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.providers import egif
from src.providers.egif.ignition import EgifIgnition

UTC = datetime.timezone.utc


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=egif.PROVIDER_NAME, product=egif.PROVIDER_PRODUCT,
                            full_name=egif.PROVIDER_FULL_NAME)
    db_session.add(provider)
    db_session.commit()
    return provider


def an_ignition(provider, **overrides) -> EgifIgnition:
    """The first fire of the Barcelona 2020 sample, as the XML publishes it."""
    values = {
        "data_provider": provider,
        "report_number": "2020080001",
        "geometry": "SRID=4326;POINT(1.85254312549163 41.4441304358167)",
        "date_time": datetime.datetime(2020, 1, 1, 15, 30, tzinfo=UTC),
        "time_zone": egif.DEFAULT_TIME_ZONE,
        "utm_zone": 31,
        "utm_x": 404147.0,
        "utm_y": 4588697.0,
        "datum": egif.DATUM_ETRS89,
        "start_point_count": 1,
        "mtn_sheet": "0902",
        "mtn_grid": "Q09",
        "place_name": "Riu Anoia",
    }
    values.update(overrides)
    return EgifIgnition(**values)


# --------------------------------------------------------------------------
# The published coordinate
# --------------------------------------------------------------------------

def test_the_published_coordinate_is_stored_as_the_numbers_it_was_published_as(
        db_session, provider):
    """The reason there is no geometry column in the source CRS.

    ``utm_x`` and ``utm_y`` *are* the original easting and northing, not a
    reprojection of them, so nothing is lost by keeping only the EPSG:4326 point
    beside them.
    """
    db_session.add(an_ignition(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifIgnition))
    assert (stored.utm_zone, stored.utm_x, stored.utm_y) == (31, 404147.0, 4588697.0)
    assert stored.datum == "ETRS89"
    assert to_shape(stored.geometry) == Point(1.85254312549163, 41.4441304358167)


def test_the_only_geometry_is_the_reprojected_one_on_the_parent(db_session):
    """``egif_ignition`` carries no geometry column at all — see the model docstring."""
    columns = {
        column["name"]
        for column in inspect(db_session.get_bind()).get_columns("egif_ignition")
    }
    assert not any("geom" in name for name in columns)
    assert {"utm_zone", "utm_x", "utm_y", "datum"} <= columns


@pytest.mark.parametrize("zone", egif.UTM_ZONES)
def test_every_zone_spain_spans_is_accepted(db_session, provider, zone):
    db_session.add(an_ignition(provider, utm_zone=zone))
    db_session.commit()

    assert db_session.scalar(select(EgifIgnition)).utm_zone == zone


def test_a_zone_outside_spain_is_rejected(db_session, provider):
    """One 2022 fire is published with ``Huso 3``, a typo for 30.

    The CHECK is what turns that into a failed insert the importer has to resolve,
    instead of a point six hundred kilometres into the Atlantic.
    """
    db_session.add(an_ignition(provider, utm_zone=3))
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.commit()


@pytest.mark.parametrize("datum", egif.DATUMS)
def test_both_published_datums_are_accepted(db_session, provider, datum):
    db_session.add(an_ignition(provider, datum=datum))
    db_session.commit()

    assert db_session.scalar(select(EgifIgnition)).datum == datum


def test_an_unknown_datum_is_rejected(db_session, provider):
    """ED50 may well turn up in older campaigns; it has to be added deliberately."""
    db_session.add(an_ignition(provider, datum="ED50"))
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.commit()


def test_the_datum_and_zone_name_a_real_crs(db_session, provider):
    """The pair is what the importer reprojects from, so it has to resolve."""
    assert egif.SOURCE_SRIDS[(egif.DATUM_ETRS89, 31)] == 25831
    assert egif.SOURCE_SRIDS[(egif.DATUM_REGCAN95, 28)] == 4083
    for datum in egif.DATUMS:
        for zone in egif.UTM_ZONES:
            if (datum, zone) in egif.SOURCE_SRIDS:
                assert isinstance(egif.SOURCE_SRIDS[(datum, zone)], int)


@pytest.mark.parametrize("column", ["utm_zone", "utm_x", "utm_y", "datum"])
def test_the_coordinate_is_required(db_session, provider, column):
    """Every fire in both exports has one; a row without is an importer bug."""
    db_session.add(an_ignition(provider, **{column: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

def test_the_report_number_is_unique(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.add(an_ignition(provider))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_report_number_is_required(db_session, provider):
    db_session.add(an_ignition(provider, report_number=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_report_number_keeps_the_leading_zero_of_its_province(db_session, provider):
    """``2022010001`` is Álava, province 01. As an integer it would be 2022010001
    and the province would still be recoverable — but ``0`` -padded fields are a
    string's job, and the year+province+sequence split is by position."""
    db_session.add(an_ignition(provider, report_number="2022010001"))
    db_session.commit()

    stored = db_session.scalar(select(EgifIgnition))
    assert stored.report_number[4:6] == "01"


# --------------------------------------------------------------------------
# Multiple points of origin
# --------------------------------------------------------------------------

def test_a_fire_may_record_more_ignition_points_than_it_publishes(db_session, provider):
    """888 fires of 13,656 have several; only one coordinate is ever published.

    Storing the count is what stops the stored point being read as *the* origin
    when it is one of fifteen.
    """
    db_session.add(an_ignition(provider, start_point_count=15))
    db_session.commit()

    assert db_session.scalar(select(EgifIgnition)).start_point_count == 15


def test_the_point_count_is_optional(db_session, provider):
    db_session.add(an_ignition(provider, start_point_count=None))
    db_session.commit()

    assert db_session.scalar(select(EgifIgnition)).start_point_count is None


def test_two_fires_may_start_at_the_same_point(db_session, provider):
    """74 coordinate triples in the 2022-2023 export are shared by 149 fires."""
    db_session.add(an_ignition(provider, report_number="2022080001"))
    db_session.add(an_ignition(provider, report_number="2022080002"))
    db_session.commit()

    stored = db_session.scalars(select(EgifIgnition)).all()
    assert len(stored) == 2
    assert {(row.utm_x, row.utm_y) for row in stored} == {(404147.0, 4588697.0)}


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_querying_the_parent_returns_the_subclass(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Ignition))
    assert isinstance(stored, EgifIgnition)
    assert stored.type == "egif_ignition"


def test_the_xml_only_place_name_may_be_absent(db_session, provider):
    """A fire read from the Excel export has no *paraje*."""
    db_session.add(an_ignition(provider, place_name=None, mtn_sheet=None, mtn_grid=None))
    db_session.commit()

    stored = db_session.scalar(select(EgifIgnition))
    assert stored.place_name is None


def test_repr_before_persist(provider):
    assert repr(an_ignition(provider)) == (
        "EgifIgnition(id=None, report_number='2020080001')")
