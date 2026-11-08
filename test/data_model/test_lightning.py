#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`Lightning` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.lightning import Lightning

UTC = datetime.timezone.utc

#: A stroke over Barcelona, 2014-05-26 08:29:25.737483 UTC.
DETECTED = datetime.datetime(2014, 5, 26, 8, 29, 25, 737483, tzinfo=UTC)


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="MeteoCat", product="XDDE", full_name="Servei Meteorològic de Catalunya")
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


def a_stroke(provider, **overrides) -> Lightning:
    values = {
        "data_provider_id": provider.id,
        "date_time": DETECTED,
        "geometry": "SRID=4326;POINT(2.1812854 41.3828)",
        "peak_current": -22.903,
        "cloud_to_ground": True,
    }
    values.update(overrides)
    return Lightning(**values)


def test_lightning_persists_and_reads_back(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(Lightning))
    assert stored.date_time == DETECTED
    assert to_shape(stored.geometry) == Point(2.1812854, 41.3828)
    assert stored.peak_current == -22.903
    assert stored.cloud_to_ground is True
    assert stored.data_provider.name == "MeteoCat"


def test_the_instant_keeps_its_microseconds(db_session, provider):
    """Strokes of one flash are microseconds apart; truncating would merge them."""
    db_session.add(a_stroke(provider))
    db_session.add(a_stroke(provider, date_time=DETECTED + datetime.timedelta(microseconds=1)))
    db_session.commit()

    first, second = db_session.scalars(select(Lightning.date_time).order_by(Lightning.date_time)).all()
    assert second - first == datetime.timedelta(microseconds=1)


def test_the_instant_is_stored_as_an_instant(db_session, provider):
    """Given in any zone, it comes back as the same moment."""
    madrid = datetime.timezone(datetime.timedelta(hours=2))
    db_session.add(a_stroke(provider, date_time=DETECTED.astimezone(madrid)))
    db_session.commit()

    assert db_session.scalar(select(Lightning)).date_time == DETECTED


def test_the_geometry_is_a_point_in_4326(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    kind, srid = db_session.execute(
        select(func.GeometryType(Lightning.geometry), func.ST_SRID(Lightning.geometry))
    ).one()
    assert (kind, srid) == ("POINT", 4326)


def test_the_polarity_is_the_sign_of_the_peak_current(db_session, provider):
    db_session.add(a_stroke(provider, peak_current=22.4405))
    db_session.add(a_stroke(provider, peak_current=-22.903))
    db_session.commit()

    currents = db_session.scalars(select(Lightning.peak_current).order_by(Lightning.id)).all()
    assert currents == [22.4405, -22.903]


def test_an_intra_cloud_stroke_is_not_cloud_to_ground(db_session, provider):
    db_session.add(a_stroke(provider, cloud_to_ground=False))
    db_session.commit()

    assert db_session.scalar(select(Lightning)).cloud_to_ground is False


@pytest.mark.parametrize("optional", ["peak_current", "cloud_to_ground"])
def test_what_not_every_network_reports_is_optional(db_session, provider, optional):
    db_session.add(a_stroke(provider, **{optional: None}))
    db_session.commit()

    assert getattr(db_session.scalar(select(Lightning)), optional) is None


def test_the_country_is_optional_and_links_when_set(db_session, provider, country):
    db_session.add(a_stroke(provider))
    db_session.add(a_stroke(provider, admin_boundary_id=country.id))
    db_session.commit()

    without, with_country = db_session.scalars(select(Lightning).order_by(Lightning.id)).all()
    assert without.admin_boundary is None
    assert with_country.admin_boundary.name == "Spain"


@pytest.mark.parametrize("missing", ["geometry", "date_time"])
def test_required_columns_are_enforced(db_session, provider, missing):
    db_session.add(a_stroke(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_is_required(db_session, provider):
    db_session.add(a_stroke(provider, data_provider_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_must_exist(db_session, provider):
    db_session.add(a_stroke(provider, data_provider_id=provider.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_timestamps_are_set_and_timezone_aware(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(Lightning))
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None


def test_polymorphic_identity_is_set(db_session, provider):
    """The discriminator is what lets a provider subclass join onto this table."""
    db_session.add(a_stroke(provider))
    db_session.commit()

    assert db_session.scalar(select(Lightning)).type == "lightning"


def test_repr_before_persist():
    assert repr(Lightning(date_time=DETECTED)) == f"Lightning(id=None, date_time={DETECTED!r})"
