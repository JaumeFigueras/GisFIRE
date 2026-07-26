#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`GfaIgnition` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.providers.gfa.ignition import GfaIgnition

UTC = datetime.timezone.utc


@pytest.fixture
def gfa(db_session):
    """The Global Fire Atlas provider row."""
    provider = DataProvider(name="GFA", product="Fire Atlas", full_name="Global Fire Atlas")
    db_session.add(provider)
    db_session.commit()
    return provider


def test_gfa_ignition_persists_and_reads_back(db_session, gfa):
    db_session.add(GfaIgnition(
        gfa_id=20000001, data_provider=gfa,
        geometry="SRID=4326;POINT(-3.7 40.4)",
        date_time=datetime.datetime(2002, 6, 25, tzinfo=UTC), time_zone="Europe/Madrid"))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(GfaIgnition))
    assert stored.gfa_id == 20000001
    # Inherited from the generic model, not redefined here.
    assert stored.time_zone == "Europe/Madrid"
    assert to_shape(stored.geometry) == Point(-3.7, 40.4)


def test_joined_table_inheritance_splits_the_columns(db_session):
    """The generic columns live in ``ignition``, only ``gfa_id`` in ``gfa_ignition``."""
    assert GfaIgnition.__tablename__ == "gfa_ignition"
    columns = {column["name"] for column in inspect(db_session.get_bind()).get_columns("gfa_ignition")}
    assert columns == {"id", "gfa_id"}


def test_querying_the_parent_returns_the_subclass(db_session, gfa):
    db_session.add(GfaIgnition(gfa_id=20000002, data_provider=gfa,
                               geometry="SRID=4326;POINT(0 0)",
                               date_time=datetime.datetime(2002, 6, 25, tzinfo=UTC)))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Ignition))
    assert isinstance(stored, GfaIgnition)
    assert stored.gfa_id == 20000002


def test_gfa_id_is_unique(db_session, gfa):
    """Unlike GWIS, the GFA identifier is a real key — the second insert must fail."""
    for _ in range(2):
        db_session.add(GfaIgnition(gfa_id=20000003, data_provider=gfa,
                                   geometry="SRID=4326;POINT(0 0)",
                                   date_time=datetime.datetime(2002, 6, 25, tzinfo=UTC)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    assert repr(GfaIgnition(gfa_id=20000001)) == "GfaIgnition(id=None, gfa_id=20000001)"
