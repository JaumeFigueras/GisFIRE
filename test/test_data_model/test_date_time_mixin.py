#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import dateutil.parser
import pytest

from src.data_model.lightning import Lightning


def test_date_time_mixin_setter():
    """
    DateTime MixIn is mainly tested with its descendants, but unusual cases are tested here. This test checks the lack
    of time zone information in setter
   """
    lightning = Lightning(date_time=datetime.datetime(2024, 4, 1, 15, 34, 56, tzinfo=pytz.UTC), latitude_epsg_4326=12.34,
                          longitude_epsg_4326=34.56)
    date = dateutil.parser.parse("2024-01-01T00:00:00")
    with pytest.raises(ValueError):
        lightning.date_time = date


def test_date_time_mixin_dict():
    """
    DateTime MixIn is mainly tested with its descendants, but unusual cases are tested here. This test checks the
    correct dict generation when time zone info is provided by a tzoffset eleemnt
   """
    date = dateutil.parser.parse("2024-01-01T00:00:00+03:00")
    lightning = Lightning(date_time=date, latitude_epsg_4326=12.34,
                          longitude_epsg_4326=34.56)
    assert dict(lightning) == {
        'date_time': '2024-01-01T00:00:00+0300',
        'id': None,
        'x_4326': 34.56,
        'y_4326': 12.34,
        'data_provider': None
    }
