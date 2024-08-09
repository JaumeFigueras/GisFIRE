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
    time_base_new = MeteocatVariableTimeBase(time_base=time_base)
    assert time_base_new.code == MeteocatVariableTimeBaseCategory.DM
    assert time_base_new.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base_new.tzinfo_valid_from == 'UTC'
    assert time_base_new.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert time_base_new.tzinfo_valid_until == 'UTC'


def test_meteocat_variable_time_base_iter_01() -> None:
    """
    Test the creation of a dict with iter of a Meteocat Variable time base

    :return: None
    """
    time_base = MeteocatVariableTimeBase(code=MeteocatVariableTimeBaseCategory.SH,
                                         valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                         valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert dict(time_base) == {
        'id': None,
        'ts': None,
        'code': 'SH',
        'valid_from': "2020-01-01T12:00:00+0000",
        'valid_until': "2023-01-01T12:00:00+0000",
        'variable_id': None,
        'weather_station_id': None,
    }


def test_meteocat_variable_time_base_iter_02() -> None:
    """
    Test the creation of a dict with iter of a Meteocat Variable time base that is stored in the database

    :return: None
    """
    # TODO
    assert True


def test_meteocat_variable_time_base_json_parser_01() -> None:
    """
    The tests of JSON parser for the METEOCAT API for this class are included in the MeteocatVariable JSON parser
    tests as these class is not a direct JSON element but a part of a variable defined inside a weather station
    """
    pass


def test_meteocat_variable_state_json_parser_02() -> None:
    """
    The tests of JSON parser for the GISFIRE API for this class are included in the MeteocatVariable JSON parser
    tests as these class is not a direct JSON element but a part of a variable defined inside a weather station
    """
    pass


def test_meteocat_variable_time_base_json_encoder_01() -> None:
    """
    Test the creation of a JSON with the data of a Meteocat Variable time base

    :return: None
    """
    time_base = MeteocatVariableTimeBase(code=MeteocatVariableTimeBaseCategory.SH,
                                         valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                         valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    time_base_dict = {
        'id': None,
        'ts': None,
        'code': 'SH',
        'valid_from': "2020-01-01T12:00:00+0000",
        'valid_until': "2023-01-01T12:00:00+0000",
        'variable_id': None,
        'weather_station_id': None,
    }
    assert json.loads(json.dumps(time_base, cls=MeteocatVariableTimeBase.JSONEncoder)) == time_base_dict


def test_meteocat_variable_time_base_json_encoder_02() -> None:
    """
    Test the creation of a JSON with the data of a Meteocat Variable time base read from the database

    :return: None
    """
    # TODO
    state_dict = {
        'id': None,
        'ts': None,
        'code': 'DISMANTLED',
        'valid_from': "2020-01-01T12:00:00+0000",
        'valid_until': "2023-01-01T12:00:00+0000",
        'variable_id': None,
        'weather_station_id': None,
    }
    # assert json.loads(json.dumps(state, cls=MeteocatVariableState.JSONEncoder)) == state_dict

