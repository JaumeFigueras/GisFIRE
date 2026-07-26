#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`GfaWildfire` model, and its link to the ignition."""

import datetime

import pytest

from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers.gfa.ignition import GfaIgnition
from src.providers.gfa.wildfire import GfaWildfire

UTC = datetime.timezone.utc


@pytest.fixture
def gfa(db_session):
    provider = DataProvider(name="GFA", product="Fire Atlas", full_name="Global Fire Atlas")
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def ignition(db_session, gfa):
    ignition = GfaIgnition(gfa_id=20000001, data_provider=gfa,
                           geometry="SRID=4326;POINT(-3.7 40.4)",
                           date_time=datetime.datetime(2002, 6, 25, tzinfo=UTC))
    db_session.add(ignition)
    db_session.commit()
    return ignition


def a_wildfire(gfa, ignition, **overrides) -> GfaWildfire:
    values = {
        "gfa_id": 20000001, "data_provider": gfa, "gfa_ignition_id": ignition.id,
        "start_date_time": datetime.datetime(2002, 6, 25, tzinfo=UTC),
        "size_km2": 3.64, "direction": "east",
    }
    values.update(overrides)
    return GfaWildfire(**values)


def test_the_wildfire_links_to_its_ignition(db_session, gfa, ignition):
    ignition_id = ignition.id
    db_session.add(a_wildfire(gfa, ignition))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(GfaWildfire))
    assert stored.ignition.id == ignition_id
    assert stored.ignition.gfa_id == stored.gfa_id


def test_joined_table_inheritance_splits_the_columns(db_session):
    """The measurements and the link live here; the generic columns on ``wildfire``."""
    assert GfaWildfire.__tablename__ == "gfa_wildfire"
    columns = {column["name"] for column in inspect(db_session.get_bind()).get_columns("gfa_wildfire")}
    assert "gfa_ignition_id" in columns
    assert "ignition_point" not in columns  # the point moved to the ignition
    assert "size_km2" in columns


def test_the_ignition_link_is_required(db_session, gfa, ignition):
    db_session.add(a_wildfire(gfa, ignition, gfa_ignition_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_ignition_link_must_exist(db_session, gfa, ignition):
    db_session.add(a_wildfire(gfa, ignition, gfa_ignition_id=ignition.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_gfa_id_is_unique(db_session, gfa, ignition):
    db_session.add(a_wildfire(gfa, ignition))
    db_session.add(a_wildfire(gfa, ignition))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_querying_the_parent_returns_the_subclass(db_session, gfa, ignition):
    db_session.add(a_wildfire(gfa, ignition))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert isinstance(stored, GfaWildfire)
    assert stored.size_km2 == pytest.approx(3.64)


def test_repr_before_persist():
    assert repr(GfaWildfire(gfa_id=20000001)) == "GfaWildfire(id=None, gfa_id=20000001)"
