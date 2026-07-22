#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`Ignition` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.ignition import Ignition

MADRID = datetime.timezone(datetime.timedelta(hours=2))


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="GFA", product="Fire Atlas", full_name="Global Fire Atlas")
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def country(db_session, provider):
    boundary = AdminBoundary(data_provider_id=provider.id, source_id="ESP", level=0, name="Spain",
                             geometry="SRID=4326;MULTIPOLYGON(((-9 36, 3 36, 3 44, -9 44, -9 36)))")
    db_session.add(boundary)
    db_session.commit()
    return boundary


def an_ignition(provider, **overrides) -> Ignition:
    values = {
        "data_provider_id": provider.id,
        "geometry": "SRID=4326;POINT(-3.7 40.4)",
        "date_time": datetime.datetime(2002, 6, 25, 0, 0, tzinfo=MADRID),
        "time_zone": "Europe/Madrid",
    }
    values.update(overrides)
    return Ignition(**values)


def test_ignition_persists_and_reads_back(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(Ignition))
    assert stored.date_time == datetime.datetime(2002, 6, 25, 0, 0, tzinfo=MADRID)
    assert stored.time_zone == "Europe/Madrid"
    assert to_shape(stored.geometry) == Point(-3.7, 40.4)


def test_the_instant_is_stored_as_an_instant(db_session, provider):
    """timestamptz has no zone of its own: what comes back is the same moment, in UTC."""
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(Ignition))
    assert stored.date_time.astimezone(datetime.timezone.utc) == \
        datetime.datetime(2002, 6, 24, 22, 0, tzinfo=datetime.timezone.utc)
    # The zone is provenance, so the published local reading stays recoverable.
    assert stored.date_time.astimezone(MADRID).hour == 0


def test_the_geometry_is_a_point_in_4326(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    kind, srid = db_session.execute(
        select(func.GeometryType(Ignition.geometry), func.ST_SRID(Ignition.geometry))
    ).one()
    assert (kind, srid) == ("POINT", 4326)


def test_the_country_is_optional_and_links_when_set(db_session, provider, country):
    db_session.add(an_ignition(provider))
    db_session.add(an_ignition(provider, admin_boundary_id=country.id))
    db_session.commit()

    without, with_country = db_session.scalars(select(Ignition).order_by(Ignition.id)).all()
    assert without.admin_boundary is None
    assert with_country.admin_boundary.name == "Spain"


def test_the_time_zone_is_optional(db_session, provider):
    """A provider publishing an instant outright involves no conversion to record."""
    db_session.add(an_ignition(provider, time_zone=None))
    db_session.commit()

    assert db_session.scalar(select(Ignition)).time_zone is None


@pytest.mark.parametrize("missing", ["geometry", "date_time"])
def test_required_columns_are_enforced(db_session, provider, missing):
    db_session.add(an_ignition(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_is_required(db_session, provider):
    db_session.add(an_ignition(provider, data_provider_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_must_exist(db_session, provider):
    db_session.add(an_ignition(provider, data_provider_id=provider.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_timestamps_are_set_and_timezone_aware(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(Ignition))
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None


def test_polymorphic_identity_is_set(db_session, provider):
    """The discriminator is what lets a provider subclass join onto this table."""
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(select(Ignition)).type == "ignition"


def test_repr_before_persist():
    moment = datetime.datetime(2002, 6, 25, 0, 0, tzinfo=MADRID)
    assert repr(Ignition(date_time=moment)) == f"Ignition(id=None, date_time={moment!r})"
