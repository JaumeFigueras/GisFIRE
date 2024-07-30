#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from src.data_model.lightning import Lightning


def test_location_metaclass_setter() -> None:
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
