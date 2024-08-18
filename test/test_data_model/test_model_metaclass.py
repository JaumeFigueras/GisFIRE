#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest

from sqlalchemy.orm import Session
from shapely.geometry import Point

from src.data_model.lightning import Lightning
from src.data_model.data_provider import DataProvider

from test.fixtures.database.database import populate_data_providers

from typing import List
from typing import Union

# The tests are using the Lightning class as it uses both locations and dates


def test_location_metaclass_setter_01() -> None:
    """
    Metaclass is tested with its sons, but for coverage purposes the geometry setter that is not used is checked here
    """
    lightning = Lightning(date_time=datetime.datetime(2024, 4, 1, 15,  34, 56, tzinfo=pytz.UTC), latitude_epsg_4326=12.34,
                          longitude_epsg_4326=34.56)
    assert lightning.date_time == datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC)
    assert lightning.y_4326 == 12.34
    assert lightning.x_4326 == 34.56
    assert lightning.geometry_4326 == "SRID=4326;POINT(34.56 12.34)"
    lightning.geometry_4326 = "SRID=4326;POINT(0 0)"
    assert lightning.geometry_4326 == "SRID=4326;POINT(34.56 12.34)"


def test_metaclass_longitude_property_01() -> None:
    """
    Tests the latitude getter and setter
    :return:
    """
    lightning = Lightning(longitude_epsg_4326=34.56)
    assert lightning.x_4326 == 34.56
    lightning.x_4326 = 23.45
    assert lightning.x_4326 == 23.45
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=67.89)
    assert lightning.x_4326 == 67.89
    lightning.x_4326 = 23.45
    assert lightning.x_4326 == 23.45
    assert lightning.y_4326 == 34.56
    assert lightning.geometry_4326 == "SRID=4326;POINT(23.45 34.56)"
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=67.89)
    assert lightning.x_4326 == 67.89
    lightning.x_4326 = None
    assert lightning.x_4326 is None
    assert lightning.y_4326 == 34.56
    assert lightning.geometry_4326 is None


def test_metaclass_longitude_property_02() -> None:
    """
    Tests the latitude setter generates exception when data is incorrect
    :return:
    """
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=34.56)
    with pytest.raises(ValueError):
        lightning.x_4326 = -180.45
    with pytest.raises(ValueError):
        lightning.x_4326 = 180.45


def test_metaclass_latitude_property_01() -> None:
    """
    Tests the latitude getter and setter
    :return:
    """
    lightning = Lightning(latitude_epsg_4326=34.56)
    assert lightning.y_4326 == 34.56
    lightning.y_4326 = 23.45
    assert lightning.x_4326 is None
    assert lightning.y_4326 == 23.45
    assert lightning.geometry_4326 is None
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=67.89)
    assert lightning.y_4326 == 34.56
    lightning.y_4326 = 23.45
    assert lightning.x_4326 == 67.89
    assert lightning.y_4326 == 23.45
    assert lightning.geometry_4326 == "SRID=4326;POINT(67.89 23.45)"
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=67.89)
    assert lightning.y_4326 == 34.56
    lightning.y_4326 = None
    assert lightning.x_4326 == 67.89
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None


def test_metaclass_latitude_property_02() -> None:
    """
    Tests the latitude setter generates exception when data is incorrect
    :return:
    """
    lightning = Lightning(latitude_epsg_4326=34.56, longitude_epsg_4326=34.56)
    with pytest.raises(ValueError):
        lightning.y_4326 = -90.45
    with pytest.raises(ValueError):
        lightning.y_4326 = 90.45


@pytest.mark.parametrize('data_provider_list', [{'data_providers': ['Meteo.cat']},], indirect=True)
def test_metaclass_geometries_01(db_session: Session, data_provider_list: Union[List[DataProvider], None]) -> None:
    populate_data_providers(db_session, data_provider_list)
    lightning = Lightning(date_time=datetime.datetime(2024, 4, 1, 15,  34, 56, tzinfo=pytz.UTC), latitude_epsg_4326=12.34,
                          longitude_epsg_4326=34.56)
    lightning.data_provider_name = "Meteo.cat"
    db_session.add(lightning)
    db_session.commit()
    assert lightning.id == 1
    assert lightning.geometry_4326 == Point([34.56, 12.34])
    point: Point = lightning.geometry_4326
    assert point.x == 34.56
    assert point.y == 12.34


def test_date_metaclass_setter_01() -> None:
    """
    Metaclass is tested with its sons, but for coverage purposes the geometry setter that is not used is checked here
    """
    lightning = Lightning(date_time=datetime.datetime(2024, 4, 1, 15,  34, 56, tzinfo=pytz.UTC), latitude_epsg_4326=12.34,
                          longitude_epsg_4326=34.56)
    assert lightning.date_time == datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC)
    assert lightning.tzinfo_date_time == 'UTC'
    lightning.tzinfo_date_time = 'CET'
    assert lightning.tzinfo_date_time == 'CET'



