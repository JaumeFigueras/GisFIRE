#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json
import pytest

from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory

from typing import List
from typing import Dict


def test_meteocat_variable_time_base_01() -> None:
    time_base = MeteocatVariableTimeBase()
    assert time_base.code is None
    assert time_base.valid_from is None
    assert time_base.tzinfo_valid_from is None
    assert time_base.valid_until is None
    assert time_base.tzinfo_valid_until is None
    time_base = MeteocatVariableTimeBase(code=MeteocatVariableTimeBaseCategory.DM)
    assert time_base.code == MeteocatVariableTimeBaseCategory.DM
    assert time_base.valid_from is None
    assert time_base.tzinfo_valid_from is None
    assert time_base.valid_until is None
    assert time_base.tzinfo_valid_until is None
    time_base = MeteocatVariableTimeBase(valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert time_base.code is None
    assert time_base.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base.tzinfo_valid_from == 'UTC'
    assert time_base.valid_until is None
    assert time_base.tzinfo_valid_until is None
    time_base = MeteocatVariableTimeBase(valid_until=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert time_base.code is None
    assert time_base.valid_from is None
    assert time_base.tzinfo_valid_from is None
    assert time_base.valid_until == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base.tzinfo_valid_until == 'UTC'
    time_base = MeteocatVariableTimeBase(code=MeteocatVariableTimeBaseCategory.DM,
                                         valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                         valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert time_base.code == MeteocatVariableTimeBaseCategory.DM
    assert time_base.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base.tzinfo_valid_from == 'UTC'
    assert time_base.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base.tzinfo_valid_until == 'UTC'
    with pytest.raises(ValueError):
        _ = MeteocatVariableTimeBase(state=time_base)
    time_base_new = MeteocatVariableTimeBase(state=time_base, code=MeteocatVariableTimeBaseCategory.DM)
    assert time_base_new.code == MeteocatVariableTimeBaseCategory.DM
    assert time_base_new.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base_new.tzinfo_valid_from == 'UTC'
    assert time_base_new.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base_new.tzinfo_valid_until == 'UTC'


def test_meteocat_variable_time_base_json_parser_01() -> None:
    """
    The tests of JSON parser for this class are included in the MeteocatVariable JSON parser tests as these class is
    not a direct JSON element but a part of a variable defined inside a weather station
    """
    pass