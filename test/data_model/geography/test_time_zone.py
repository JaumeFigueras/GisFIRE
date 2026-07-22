#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`TimeZone` model."""

from src.data_model.geography.time_zone import TimeZone

SQUARE = "SRID=4326;MULTIPOLYGON(((0 40, 1 40, 1 41, 0 41, 0 40)))"


def test_repr_before_persist():
    zone = TimeZone(name="Europe/Madrid")
    assert repr(zone) == "TimeZone(id=None, name='Europe/Madrid')"


def test_repr_carries_the_id_once_persisted(db_session):
    """The id is the half of it worth printing, and it only exists after a flush."""
    zone = TimeZone(name="Europe/Madrid", geometry=SQUARE)
    db_session.add(zone)
    db_session.commit()

    assert repr(zone) == f"TimeZone(id={zone.id!r}, name='Europe/Madrid')"
    assert zone.id is not None
