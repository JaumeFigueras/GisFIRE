#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`DataProvider` model."""

import datetime

import pytest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider


def test_data_provider_persists_and_reads_back(db_session):
    provider = DataProvider(
        name="MeteoCat",
        full_name="Servei Meteorològic de Catalunya",
        description="Catalan public weather service.",
        url="https://www.meteo.cat",
    )
    db_session.add(provider)
    db_session.commit()

    stored = db_session.scalar(select(DataProvider).where(DataProvider.name == "MeteoCat"))
    assert stored is not None
    assert stored.id is not None  # surrogate autoincrement PK assigned by the DB
    assert stored.full_name == "Servei Meteorològic de Catalunya"
    assert stored.description == "Catalan public weather service."
    assert stored.url == "https://www.meteo.cat"


def test_url_is_optional(db_session):
    provider = DataProvider(name="NOAA", full_name="National Oceanic and Atmospheric Administration",
                            description="US federal weather and climate agency.")
    db_session.add(provider)
    db_session.commit()
    assert provider.url is None


def test_description_is_optional(db_session):
    provider = DataProvider(name="nodesc", full_name="No description provider")
    db_session.add(provider)
    db_session.commit()
    assert provider.description is None


def test_name_must_be_unique(db_session):
    db_session.add(DataProvider(name="dup", full_name="First", description="a"))
    db_session.commit()
    db_session.add(DataProvider(name="dup", full_name="Second", description="b"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    provider = DataProvider(name="MeteoCat", full_name="Servei Meteorològic de Catalunya")
    assert repr(provider) == "DataProvider(id=None, name='MeteoCat')"


def test_repr_after_persist(db_session):
    provider = DataProvider(name="MeteoCat", full_name="Servei Meteorològic de Catalunya")
    db_session.add(provider)
    db_session.commit()
    assert repr(provider) == f"DataProvider(id={provider.id!r}, name='MeteoCat')"


def test_timestamps_are_set_and_timezone_aware(db_session):
    provider = DataProvider(name="tz", full_name="Timezone probe", description="checks ts columns")
    db_session.add(provider)
    db_session.commit()

    assert isinstance(provider.created_at, datetime.datetime)
    assert isinstance(provider.updated_at, datetime.datetime)
    assert provider.created_at.tzinfo is not None
    assert provider.updated_at.tzinfo is not None
