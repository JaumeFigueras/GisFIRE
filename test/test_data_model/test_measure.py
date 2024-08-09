#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

import pytz

from src.data_model.measure import Measure


def test_measure_01() -> None:
    """
    Tests Variable class initialization.

    :return: None
    """
    measure = Measure()
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = Measure(measure_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert measure.measure_date_time == datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC)
    assert measure.tzinfo_measure_date_time == 'UTC'


def test_measure_iter_01() -> None:
    """
    Tests Variable class iterator to convert it to a dict.
    :return:
    """
    measure = Measure(measure_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert dict(measure) == {
        'id': None,
        'measure_date_time': '2024-01-01T12:12:00+0000',
        'data_provider': None
    }
