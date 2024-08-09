#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json

from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableStateCategory

from typing import List
from typing import Dict


def test_meteocat_variable_state_01() -> None:
    state = MeteocatVariableState()
    assert state.code is None
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatVariableState(code=MeteocatVariableStateCategory.DISMANTLED)
    assert state.code == MeteocatVariableStateCategory.DISMANTLED
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatVariableState(valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert state.code is None
    assert state.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatVariableState(valid_until=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert state.code is None
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'
    state = MeteocatVariableState(code=MeteocatVariableStateCategory.DISMANTLED,
                                  valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                  valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert state.code == MeteocatVariableStateCategory.DISMANTLED
    assert state.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'
    state_new = MeteocatVariableState(state=state)
    assert state_new.code == MeteocatVariableStateCategory.DISMANTLED
    assert state_new.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state_new.tzinfo_valid_from == 'UTC'
    assert state_new.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state_new.tzinfo_valid_until == 'UTC'


def test_meteocat_variable_state_iter_01() -> None:
    """
    Test the creation of a dict with iter of a Meteocat Variable state

    :return: None
    """
    state = MeteocatVariableState(code=MeteocatVariableStateCategory.DISMANTLED,
                                  valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                  valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert dict(state) == {
        'id': None,
        'ts': None,
        'code': 'DISMANTLED',
        'valid_from': "2020-01-01T12:00:00+0000",
        'valid_until': "2023-01-01T12:00:00+0000",
        'variable_id': None,
        'weather_station_id': None,
    }


def test_meteocat_variable_state_iter_02() -> None:
    """
    Test the creation of a dict with iter of a Meteocat Variable state that is stores in the database

    :return: None
    """
    # TODO
    assert True


def test_meteocat_variable_state_json_parser_01() -> None:
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


def test_meteocat_variable_state_json_encoder_01() -> None:
    """
    Test the creation of a JSON with the data of a Meteocat Variable state

    :return: None
    """
    state = MeteocatVariableState(code=MeteocatVariableStateCategory.DISMANTLED,
                                  valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                  valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    state_dict = {
        'id': None,
        'ts': None,
        'code': 'DISMANTLED',
        'valid_from': "2020-01-01T12:00:00+0000",
        'valid_until': "2023-01-01T12:00:00+0000",
        'variable_id': None,
        'weather_station_id': None,
    }
    assert json.loads(json.dumps(state, cls=MeteocatVariableState.JSONEncoder)) == state_dict


def test_meteocat_variable_state_json_encoder_02() -> None:
    """
    Test the creation of a JSON with the data of a Meteocat Variable state read from the database

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
