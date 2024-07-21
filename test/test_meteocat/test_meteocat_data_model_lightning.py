#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest

from src.meteocat.data_model.lightning import MeteocatLightning


def test_lightning_01() -> None:
    """
    Tests the initialization of a lightning
    """
    lightning = MeteocatLightning()
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC))
    assert lightning.date == datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC)
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(meteocat_id=123456789)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id == 123456789
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(peak_current=123.45)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current == 123.45
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(chi_squared=123.45)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared == 123.45
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(ellipse_major_axis=2000)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis == 2000
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(ellipse_minor_axis=600)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis == 600
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(ellipse_angle=23.45)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle == 23.45
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(number_of_sensors=3)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors == 3
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(hit_ground=True)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(municipality_code='08233')
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code == '08233'
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(latitude_etrs89=73.45)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 == 73.45
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(longitude_etrs89=123.45)
    assert lightning.date is None
    assert lightning.latitude_wgs84 is None
    assert lightning.longitude_wgs84 is None
    assert lightning.geometry_wgs84 is None
    assert lightning.meteocat_id is None
    assert lightning.peak_current is None
    assert lightning.chi_squared is None
    assert lightning.ellipse_major_axis is None
    assert lightning.ellipse_minor_axis is None
    assert lightning.ellipse_angle is None
    assert lightning.number_of_sensors is None
    assert not lightning.hit_ground
    assert lightning.municipality_code is None
    assert lightning._latitude_etrs89 is None
    assert lightning._longitude_etrs89 == 123.45
    assert lightning._geometry_etrs89 is None
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.date == datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC)
    assert lightning._latitude_wgs84 == 41.77052639
    assert lightning._longitude_wgs84 == 2.18969857
    assert lightning._geometry_wgs84 == "SRID=4326;POINT(2.18969857 41.77052639)"
    assert lightning.meteocat_id == 123456789
    assert lightning.peak_current == 57.45
    assert lightning.chi_squared == 23.12
    assert lightning.ellipse_major_axis == 3500
    assert lightning.ellipse_minor_axis == 500
    assert lightning.ellipse_angle == 23.45
    assert lightning.number_of_sensors == 2
    assert lightning.hit_ground
    assert lightning.municipality_code == '08233'
    assert lightning._latitude_etrs89 == 41.77052639
    assert lightning._longitude_etrs89 == 2.18969857
    assert lightning._geometry_etrs89 == "SRID=4258;POINT(2.18969857 41.77052639)"


def test_lightning_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                              chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                              latitude_etrs89=-141.77052639, longitude_etrs89=2.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                              chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                              latitude_etrs89=-41.77052639, longitude_etrs89=222.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                              chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=0, hit_ground=True, municipality_code='08233',
                              latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    with pytest.raises(ValueError):
        _ = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56), meteocat_id=123456789, peak_current=57.45,
                              chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                              ellipse_angle=23.45, number_of_sensors=0, hit_ground=True, municipality_code='08233',
                              latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)


def test_lightning_latitude_etrs89_01() -> None:
    """
    Tests the assignment and read of the latitude property of a lightning

    :return: None
    """
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.latitude_etrs89 == 41.77052639
    lightning.latitude_etrs89 = 2.18969857
    assert lightning._latitude_etrs89 == 2.18969857
    assert lightning._geometry_etrs89 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning._latitude_wgs84 == 2.18969857
    assert lightning._geometry_wgs84 == "SRID=4326;POINT(2.18969857 2.18969857)"
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.latitude_etrs89 == 41.77052639
    lightning.latitude_etrs89 = None
    assert lightning._latitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    assert lightning._latitude_wgs84 is None
    assert lightning._geometry_wgs84 is None
    lightning.latitude_etrs89 = 2.18969857
    assert lightning._latitude_etrs89 == 2.18969857
    assert lightning._geometry_etrs89 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning._latitude_wgs84 == 2.18969857
    assert lightning._geometry_wgs84 == "SRID=4326;POINT(2.18969857 2.18969857)"
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.latitude_etrs89 == 41.77052639
    assert lightning.longitude_etrs89 == 2.18969857
    lightning._longitude_etrs89 = None
    lightning.latitude_etrs89 = 23.45
    assert lightning._geometry_etrs89 is None
    assert lightning._latitude_wgs84 is None
    assert lightning._longitude_wgs84 is None
    assert lightning._geometry_wgs84 is None


def test_lightning_latitude_etrs89_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.latitude_etrs89 == 41.77052639
    with pytest.raises(ValueError):
        lightning.latitude_etrs89 = 222.18969857


def test_lightning_longitude_etrs89_01() -> None:
    """
    Tests the assignment and read of the longitude property of a lightning

    :return: None
    """
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=2.18969857, longitude_etrs89=41.77052639)
    assert lightning.longitude_etrs89 == 41.77052639
    lightning.longitude_etrs89 = 2.18969857
    assert lightning._longitude_etrs89 == 2.18969857
    assert lightning._geometry_etrs89 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning._longitude_wgs84 == 2.18969857
    assert lightning._geometry_wgs84 == "SRID=4326;POINT(2.18969857 2.18969857)"
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=2.18969857, longitude_etrs89=41.77052639)
    assert lightning.longitude_etrs89 == 41.77052639
    lightning.longitude_etrs89 = None
    assert lightning._longitude_etrs89 is None
    assert lightning._geometry_etrs89 is None
    assert lightning._longitude_wgs84 is None
    assert lightning._geometry_wgs84 is None
    lightning.longitude_etrs89 = 2.18969857
    assert lightning._longitude_etrs89 == 2.18969857
    assert lightning._geometry_etrs89 == "SRID=4258;POINT(2.18969857 2.18969857)"
    assert lightning._longitude_wgs84 == 2.18969857
    assert lightning._geometry_wgs84 == "SRID=4326;POINT(2.18969857 2.18969857)"
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.latitude_etrs89 == 41.77052639
    assert lightning.longitude_etrs89 == 2.18969857
    lightning._latitude_etrs89 = None
    lightning.longitude_etrs89 = 23.45
    assert lightning._geometry_etrs89 is None
    assert lightning._latitude_wgs84 is None
    assert lightning._longitude_wgs84 is None
    assert lightning._geometry_wgs84 is None


def test_lightning_longitude_etrs89_02() -> None:
    """
    Tests the exceptions with semantic error on lightning initialization

    :return: None
    """
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.longitude_etrs89 == 2.18969857
    with pytest.raises(ValueError):
        lightning.longitude_etrs89 = 222.18969857


def test_lightning_geometry_etrs89_01() -> None:
    """
    Tests reading od the geometry property

    :return: None
    """
    lightning = MeteocatLightning(date=datetime.datetime(2024,4,1,15, 34,56, tzinfo=pytz.UTC), meteocat_id=123456789, peak_current=57.45,
                                  chi_squared=23.12, ellipse_major_axis=3500, ellipse_minor_axis=500,
                                  ellipse_angle=23.45, number_of_sensors=2, hit_ground=True, municipality_code='08233',
                                  latitude_etrs89=41.77052639, longitude_etrs89=2.18969857)
    assert lightning.geometry_etrs89 == "SRID=4258;POINT(2.18969857 41.77052639)"

