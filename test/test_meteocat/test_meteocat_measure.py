#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json
import pytest

from src.meteocat.data_model.measure import MeteocatMeasure
from src.meteocat.data_model.measure import MeteocatMeasureValidityCategory
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory

from typing import List


def test_meteocat_measure_01() -> None:
    """
    Tests Variable class initialization.

    :return: None
    """
    measure = MeteocatMeasure()
    assert measure.meteocat_id is None
    assert measure.value is None
    assert measure.validity_state is None
    assert measure.time_base is None
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = MeteocatMeasure(measure_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert measure.measure_date_time == datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC)
    assert measure.tzinfo_measure_date_time == 'UTC'
    assert measure.meteocat_id is None
    assert measure.value is None
    assert measure.validity_state is None
    assert measure.time_base is None
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    measure = MeteocatMeasure(meteocat_id=123456789)
    assert measure.meteocat_id == 123456789
    assert measure.value is None
    assert measure.validity_state is None
    assert measure.time_base is None
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = MeteocatMeasure(value=12.34)
    assert measure.meteocat_id is None
    assert measure.value == 12.34
    assert measure.validity_state is None
    assert measure.time_base is None
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = MeteocatMeasure(validity_state=MeteocatMeasureValidityCategory.VALID)
    assert measure.meteocat_id is None
    assert measure.value is None
    assert measure.validity_state == MeteocatMeasureValidityCategory.VALID
    assert measure.time_base is None
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = MeteocatMeasure(time_base=MeteocatVariableTimeBaseCategory.SH)
    assert measure.meteocat_id is None
    assert measure.value is None
    assert measure.validity_state is None
    assert measure.time_base == MeteocatVariableTimeBaseCategory.SH
    assert measure.extreme_date_time is None
    assert measure.tzinfo_extreme_date_time is None
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    measure = MeteocatMeasure(extreme_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert measure.measure_date_time is None
    assert measure.tzinfo_measure_date_time is None
    assert measure.meteocat_id is None
    assert measure.value is None
    assert measure.validity_state is None
    assert measure.time_base is None
    assert measure.extreme_date_time == datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC)
    assert measure.tzinfo_extreme_date_time == 'UTC'
    measure = MeteocatMeasure(meteocat_id=123456789,
                              measure_date_time=datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                              value=123.321, validity_state=MeteocatMeasureValidityCategory.VALID,
                              time_base=MeteocatVariableTimeBaseCategory.SH,
                              extreme_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert measure.meteocat_id == 123456789
    assert measure.value == 123.321
    assert measure.validity_state == MeteocatMeasureValidityCategory.VALID
    assert measure.time_base == MeteocatVariableTimeBaseCategory.SH
    assert measure.extreme_date_time == datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC)
    assert measure.tzinfo_extreme_date_time == 'UTC'
    assert measure.measure_date_time == datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert measure.tzinfo_measure_date_time == 'UTC'


def test_meteocat_measure_iter_01():
    measure = MeteocatMeasure(meteocat_id=123456789,
                              measure_date_time=datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                              value=123.321, validity_state=MeteocatMeasureValidityCategory.VALID,
                              time_base=MeteocatVariableTimeBaseCategory.SH,
                              extreme_date_time=datetime.datetime(2024, 1, 1, 12, 12, 0, tzinfo=pytz.UTC))
    assert dict(measure) == {
        'id': None,
        'measure_date_time': '2024-01-01T12:00:00+0000',
        'data_provider': None,
        'meteocat_id': 123456789,
        'value': 123.321,
        'validity_state': 'VALID',
        'time_base': 'SH',
        'extreme_date_time': '2024-01-01T12:12:00+0000',
    }

