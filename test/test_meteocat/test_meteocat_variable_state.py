#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json
import pytest

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory
from src.meteocat.data_model.state import MeteocatStateCategory

from typing import List
from typing import Dict


def test_meteocat_variable_state_01() -> None:
    state = MeteocatVariableState()
    assert state.code is None
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatVariableState(code=MeteocatStateCategory.DISMANTLED)
    assert state.code == MeteocatStateCategory.DISMANTLED
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
    state = MeteocatVariableState(code=MeteocatStateCategory.DISMANTLED,
                                  valid_from=datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC),
                                  valid_until=datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC))
    assert state.code == MeteocatStateCategory.DISMANTLED
    assert state.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'
    state_new = MeteocatVariableState(state=state)
    assert state_new.code == MeteocatStateCategory.DISMANTLED
    assert state_new.valid_from == datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state_new.tzinfo_valid_from == 'UTC'
    assert state_new.valid_until == datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert state_new.tzinfo_valid_until == 'UTC'


def test_meteocat_variable_state_json_parser_01() -> None:
    """
    The tests of JSON parser for this class are included in the MeteocatVariable JSON parser tests as these class is
    not a direct JSON element but a part of a variable defined inside a weather station
    """
    pass