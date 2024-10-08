#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest

from sqlalchemy.orm import Session
from shapely.geometry import Point

from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.data_provider import DataProvider

from test.fixtures.database.database import populate_data_providers

from typing import Union
from typing import List


def test_lightning_01() -> None:
    """
    Tests the initialization of a lightning
    """
    lightning = MeteocatLightning()
    assert lightning.date_time is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC))
    assert lightning.date_time == datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC)
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(meteocat_id=123456789)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id == 123456789
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(peak_current=123.45)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current == 123.45
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(chi_squared=123.45)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared == 123.45
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(ellipse_major_axis=2000)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis == 2000
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(ellipse_minor_axis=600)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis == 600
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(ellipse_angle=23.45)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle == 23.45
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(number_of_sensors=3)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors == 3
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(hit_ground=True)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(municipality_code='08233')
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code == '08233'
    assert lightning.x_4258 is None
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(latitude_epsg_4258=73.45)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 is None
    assert lightning.y_4258 == 73.45
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(longitude_epsg_4258=123.45)
    assert lightning.date_time is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning.x_4258 == 123.45
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.date_time == datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC)
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 41.77052639
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 41.77052639)"
    assert lightning.meteocat_id == 123456789
    assert lightning.peak_current == 57.45
    assert lightning.chi_squared == 23.12
    assert lightning.ellipse_major_axis == 3500
    assert lightning.ellipse_minor_axis == 500
    assert lightning.ellipse_angle == 23.45
    assert lightning.number_of_sensors == 2
    assert lightning.hit_ground
    assert lightning.municipality_code == '08233'
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 41.77052639
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 41.77052639)"
    assert lightning.x_25831 == 432651.9440920378
    assert lightning.y_25831 == 4624615.796608334
    assert lightning.geometry_25831 == "SRID=25831;POINT(432651.9440920378 4624615.796608334)"


def test_lightning_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC), meteocat_id=123456789,
                              peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                              latitude_epsg_4258=-141.77052639, longitude_epsg_4258=2.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC), meteocat_id=123456789,
                              peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                              latitude_epsg_4258=-41.77052639, longitude_epsg_4258=222.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC), meteocat_id=123456789,
                              peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=0, hit_ground=True, municipality_code='08233',
                              latitude_epsg_4258=41.77052639, longitude_epsg_4258=2.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56), meteocat_id=123456789, peak_current=57.45,
                              chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=0, hit_ground=True, municipality_code='08233',
                              latitude_epsg_4258=41.77052639, longitude_epsg_4258=2.18969857)


def test_lightning_latitude_etrs89_01() -> None:
    """
    Tests the assignment and read of the latitude property of a lightning

    :return: None
    """
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.y_4258 == 41.77052639
    lightning.y_4258 = 2.18969857
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 2.18969857
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 2.18969857
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 2.18969857)"
    assert lightning.x_25831 == 409896.12224567804
    assert lightning.y_25831 == 242053.01211426232
    assert lightning.geometry_25831 == "SRID=25831;POINT(409896.12224567804 242053.01211426232)"
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.y_4258 == 41.77052639
    lightning.y_4258 = None
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning.y_4258 = 2.18969857
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 2.18969857
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 2.18969857
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 2.18969857)"
    assert lightning.x_25831 == 409896.12224567804
    assert lightning.y_25831 == 242053.01211426232
    assert lightning.geometry_25831 == "SRID=25831;POINT(409896.12224567804 242053.01211426232)"
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 41.77052639
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 41.77052639)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 41.77052639
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 41.77052639)"
    assert lightning.x_25831 == 432651.9440920378
    assert lightning.y_25831 == 4624615.796608334
    assert lightning.geometry_25831 == "SRID=25831;POINT(432651.9440920378 4624615.796608334)"
    lightning.y_4258 = None
    lightning.x_4258 = 23.45
    assert lightning.x_4258 == 23.45
    assert lightning.y_4258 is None
    assert lightning.geometry_4258 is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None


def test_lightning_latitude_etrs89_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.y_4258 == 41.77052639
    with pytest.raises(ValueError):
        lightning.y_4258 = 222.18969857
    assert lightning.y_4258 == 41.77052639


def test_lightning_longitude_etrs89_01() -> None:
    """
    Tests the assignment and read of the longitude property of a lightning

    :return: None
    """
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=2.18969857,
                                  longitude_epsg_4258=41.77052639)
    assert lightning.x_4258 == 41.77052639
    lightning.x_4258 = 2.18969857
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 2.18969857
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 2.18969857
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 2.18969857)"
    assert lightning.x_25831 == 409896.12224567804
    assert lightning.y_25831 == 242053.01211426232
    assert lightning.geometry_25831 == "SRID=25831;POINT(409896.12224567804 242053.01211426232)"
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=2.18969857,
                                  longitude_epsg_4258=41.77052639)
    assert lightning.x_4258 == 41.77052639
    lightning.x_4258 = None
    assert lightning.x_4258 is None
    assert lightning.y_4258 == 2.18969857
    assert lightning.geometry_4258 is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None
    lightning.x_4258 = 2.18969857
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 2.18969857
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 2.18969857
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 2.18969857)"
    assert lightning.x_25831 == 409896.12224567804
    assert lightning.y_25831 == 242053.01211426232
    assert lightning.geometry_25831 == "SRID=25831;POINT(409896.12224567804 242053.01211426232)"
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.x_4258 == 2.18969857
    assert lightning.y_4258 == 41.77052639
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 41.77052639)"
    assert lightning.x_4326 == 2.18969857
    assert lightning.y_4326 == 41.77052639
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 41.77052639)"
    assert lightning.x_25831 == 432651.9440920378
    assert lightning.y_25831 == 4624615.796608334
    assert lightning.geometry_25831 == "SRID=25831;POINT(432651.9440920378 4624615.796608334)"
    lightning.x_4258 = None
    lightning.y_4258 = 23.45
    assert lightning.x_4258 is None
    assert lightning.y_4258 == 23.45
    assert lightning.geometry_4258 is None
    assert lightning.x_4326 is None
    assert lightning.y_4326 is None
    assert lightning.geometry_4326 is None
    assert lightning.x_25831 is None
    assert lightning.y_25831 is None
    assert lightning.geometry_25831 is None


def test_lightning_longitude_etrs89_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.x_4258 == 2.18969857
    with pytest.raises(ValueError):
        lightning.x_4258 = 222.18969857
    assert lightning.x_4258 == 2.18969857


def test_lightning_geometry_etrs89_01() -> None:
    """
    Tests reading od the geometry property

    :return: None
    """
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    assert lightning.geometry_4258 == "SRID=4258;POINT(2.18969857 41.77052639)"
    assert lightning.geometry_4326 == "SRID=4326;POINT(2.18969857 41.77052639)"
    assert lightning.geometry_25831 == "SRID=25831;POINT(432651.9440920378 4624615.796608334)"


@pytest.mark.parametrize('data_provider_list', [{'data_providers': ['Meteo.cat']},], indirect=True)
def test_geometries_01(db_session: Session, data_provider_list: Union[List[DataProvider], None]) -> None:
    populate_data_providers(db_session, data_provider_list)
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    lightning.data_provider_name = "Meteo.cat"
    db_session.add(lightning)
    db_session.commit()
    assert lightning.id == 1
    point: Point = lightning.geometry_4258
    assert point.x == 2.18969857
    assert point.y == 41.77052639
    point: Point = lightning.geometry_25831
    assert point.x == 432651.9440920378
    assert point.y == 4624615.796608334
    point: Point = lightning.geometry_4326
    assert point.x == 2.18969857
    assert point.y == 41.77052639


def test_iter_01() -> None:
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    dct = dict(lightning)
    assert dct == {
        'id': None,
        'x_4326': 2.18969857,
        'y_4326': 41.77052639,
        'date_time': '2024-04-01T15:34:56+0000',
        'meteocat_id': 123456789,
        'peak_current': 57.45,
        'chi_squared': 23.12,
        'multiplicity': None,
        'ellipse_major_axis': 3500,
        'ellipse_minor_axis': 500,
        'ellipse_angle': 23.45,
        'number_of_sensors': 2,
        'hit_ground': True,
        'municipality_code': '08233',
        'x_4258': 2.18969857,
        'y_4258': 41.77052639,
        'x_25831': 432651.9440920378,
        'y_25831': 4624615.796608334,
        'data_provider': None
    }


@pytest.mark.parametrize('data_provider_list', [{'data_providers': ['Meteo.cat']},], indirect=True)
def test_iter_02(db_session: Session, data_provider_list: Union[List[DataProvider], None]) -> None:
    populate_data_providers(db_session, data_provider_list)
    lightning = MeteocatLightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC),
                                  meteocat_id=123456789, peak_current=57.45, chi_squared=23.12, ellipse_major_axis=3500,
                                  ellipse_minor_axis=500, ellipse_angle=23.45, number_of_sensors=2, hit_ground=True,
                                  municipality_code='08233', latitude_epsg_4258=41.77052639,
                                  longitude_epsg_4258=2.18969857)
    lightning.data_provider_name = "Meteo.cat"
    db_session.add(lightning)
    db_session.commit()
    dct = dict(lightning)
    assert dct == {
        'id': 1,
        'x_4326': 2.18969857,
        'y_4326': 41.77052639,
        'date_time': '2024-04-01T15:34:56+0000',
        'meteocat_id': 123456789,
        'peak_current': 57.45,
        'chi_squared': 23.12,
        'multiplicity': None,
        'ellipse_major_axis': 3500,
        'ellipse_minor_axis': 500,
        'ellipse_angle': 23.45,
        'number_of_sensors': 2,
        'hit_ground': True,
        'municipality_code': '08233',
        'x_4258': 2.18969857,
        'y_4258': 41.77052639,
        'x_25831': 432651.9440920378,
        'y_25831': 4624615.796608334,
        'data_provider': 'Meteo.cat'
    }
