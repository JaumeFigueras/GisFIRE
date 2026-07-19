#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`Wildfire` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="GWIS", product="Global Wildfire Database",
                            full_name="Global Wildfire Information System")
    db_session.add(provider)
    db_session.commit()
    return provider


def a_multipolygon() -> MultiPolygon:
    """A two-part perimeter somewhere in Catalonia, in lon/lat (EPSG:4326)."""
    return MultiPolygon([
        Polygon([(2.0, 41.0), (2.1, 41.0), (2.1, 41.1), (2.0, 41.1), (2.0, 41.0)]),
        Polygon([(2.3, 41.3), (2.4, 41.3), (2.4, 41.4), (2.3, 41.4), (2.3, 41.3)]),
    ])


def test_wildfire_persists_and_reads_back(db_session, provider):
    start = datetime.datetime(2024, 7, 15, 12, 30, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
    perimeter = a_multipolygon()

    db_session.add(Wildfire(data_provider=provider, start_date_time=start, end_date_time=end,
                            perimeter=func.ST_GeomFromText(perimeter.wkt, 4326)))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert stored is not None
    assert stored.id is not None  # surrogate autoincrement PK assigned by the DB
    assert stored.start_date_time == start
    assert stored.end_date_time == end
    assert stored.data_provider.name == "GWIS"
    assert stored.data_provider.product == "Global Wildfire Database"
    assert to_shape(stored.perimeter).equals(perimeter)


def test_perimeter_is_stored_as_multipolygon_in_4326(db_session, provider):
    db_session.add(Wildfire(data_provider=provider,
                            start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc),
                            perimeter=func.ST_GeomFromText(a_multipolygon().wkt, 4326)))
    db_session.commit()

    stored = db_session.scalar(select(Wildfire))
    assert db_session.scalar(select(func.ST_SRID(stored.perimeter))) == 4326
    assert db_session.scalar(select(func.GeometryType(stored.perimeter))) == "MULTIPOLYGON"


def test_end_date_time_and_perimeter_are_optional(db_session, provider):
    """A wildfire still burning has neither an end date nor, possibly, a perimeter."""
    wildfire = Wildfire(data_provider=provider,
                        start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    assert wildfire.end_date_time is None
    assert wildfire.perimeter is None


def test_start_date_time_is_required(db_session, provider):
    db_session.add(Wildfire(data_provider=provider))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_is_required(db_session):
    db_session.add(Wildfire(start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_must_exist(db_session):
    db_session.add(Wildfire(data_provider_id=12345,
                            start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_timestamps_are_set_and_timezone_aware(db_session, provider):
    wildfire = Wildfire(data_provider=provider,
                        start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    assert isinstance(wildfire.created_at, datetime.datetime)
    assert isinstance(wildfire.updated_at, datetime.datetime)
    assert wildfire.created_at.tzinfo is not None
    assert wildfire.updated_at.tzinfo is not None


def test_polymorphic_identity_is_set(db_session, provider):
    """Providers add their own attributes (and their own ID) in subclasses."""
    wildfire = Wildfire(data_provider=provider,
                        start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    assert wildfire.type == "wildfire"


def test_repr_before_persist():
    start = datetime.datetime(2024, 7, 15, 12, 30, tzinfo=datetime.timezone.utc)
    wildfire = Wildfire(start_date_time=start)
    assert repr(wildfire) == f"Wildfire(id=None, start_date_time={start!r})"