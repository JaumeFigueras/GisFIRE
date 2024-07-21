#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

import pytest

from src.data_model.lightning import Lightning


def test_lightning_01() -> None:
    """
    Tests the initialization of a data provider
    """
    lightning = Lightning()
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC))
    assert lightning.date == datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC)
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(latitude_wgs84=34.56)
    assert lightning.date is None
    assert lightning.latitude_wgs84 == 34.56
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(longitude_wgs84=34.56)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 == 34.56
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), latitude_wgs84=12.34, longitude_wgs84=34.56)
    assert lightning.date == datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC)
    assert lightning.latitude_wgs84 == 12.34
    assert lightning.longitude_wgs84 == 34.56
    assert lightning.geometry_wgs84 == "SRID=4326;POINT(34.56 12.34)"


def test_lightning_02() -> None:
    """
    Tests the incorrect initialization of a lightning
    """
    with pytest.raises(ValueError):
        _ = Lightning(latitude_wgs84=90.01)
    with pytest.raises(ValueError):
        _ = Lightning(latitude_wgs84=-90.01)
    with pytest.raises(ValueError):
        _ = Lightning(longitude_wgs84=180.01)
    with pytest.raises(ValueError):
        _ = Lightning(longitude_wgs84=-180.01)
    with pytest.raises(ValueError):
        _ = Lightning(latitude_wgs84=90.01, longitude_wgs84=180.01)
    with pytest.raises(ValueError):
        _ = Lightning(date=datetime.datetime(2024, 4, 1, 15,  34, 56), latitude_wgs84=12.34, longitude_wgs84=34.56)


def test_lightning_latitude_property_01() -> None:
    """
    Tests the latitude getter and setter
    :return:
    """
    lightning = Lightning(latitude_wgs84=34.56)
    assert lightning.latitude_wgs84 == 34.56
    lightning.latitude_wgs84 = 23.45
    assert lightning.latitude_wgs84 == 23.45
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=67.89)
    assert lightning.latitude_wgs84 == 34.56
    lightning.latitude_wgs84 = 23.45
    assert lightning.latitude_wgs84 == 23.45
    assert lightning.geometry_wgs84 == "SRID=4326;POINT(67.89 23.45)"
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=67.89)
    assert lightning.latitude_wgs84 == 34.56
    lightning.latitude_wgs84 = None
    assert lightning.latitude_wgs84 is None
    assert lightning.geometry_wgs84 is None


def test_lightning_latitude_property_02() -> None:
    """
    Tests the latitude setter generates exception when data is incorrect
    :return:
    """
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=34.56)
    with pytest.raises(ValueError):
        lightning.latitude_wgs84 = -90.45
    with pytest.raises(ValueError):
        lightning.latitude_wgs84 = 90.45


def test_lightning_longitude_property_01() -> None:
    """
    Tests the latitude getter and setter
    :return:
    """
    lightning = Lightning(longitude_wgs84=34.56)
    assert lightning.longitude_wgs84 == 34.56
    lightning.longitude_wgs84 = 23.45
    assert lightning.longitude_wgs84 == 23.45
    assert lightning.geometry_wgs84 is None
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=67.89)
    assert lightning.longitude_wgs84 == 67.89
    lightning.longitude_wgs84 = 23.45
    assert lightning.longitude_wgs84 == 23.45
    assert lightning.geometry_wgs84 == "SRID=4326;POINT(23.45 34.56)"
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=67.89)
    assert lightning.longitude_wgs84 == 67.89
    lightning.longitude_wgs84 = None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None


def test_lightning_longitude_property_02() -> None:
    """
    Tests the latitude setter generates exception when data is incorrect
    :return:
    """
    lightning = Lightning(latitude_wgs84=34.56, longitude_wgs84=34.56)
    with pytest.raises(ValueError):
        lightning.longitude_wgs84 = -180.45
    with pytest.raises(ValueError):
        lightning.longitude_wgs84 = 180.45
