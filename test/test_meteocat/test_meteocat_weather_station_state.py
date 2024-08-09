#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.data_model.weather_station import MeteocatWeatherStationStateCategory

from typing import List


def test_meteocat_weather_station_state_01() -> None:
    state = MeteocatWeatherStationState()
    assert state.code is None
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.REPAIR)
    assert state.code == MeteocatWeatherStationStateCategory.REPAIR
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatWeatherStationState(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state.code is None
    assert state.valid_from == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = MeteocatWeatherStationState(valid_until=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state.code is None
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'
    state = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.REPAIR,
                                        valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                        valid_until=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state.code == MeteocatWeatherStationStateCategory.REPAIR
    assert state.valid_from == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'


def test_meteocat_weather_station_state_equals_01() -> None:
    state_1 = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.REPAIR,
                                          valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                          valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state_1 != 1
    assert state_1 != 'Hello'
    assert not state_1 == 1
    assert not state_1 == 'Hello'
    state_2 = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.ACTIVE,
                                          valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                          valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state_1 != state_2
    assert not state_1 == state_2
    state_2 = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.REPAIR,
                                          valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                          valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert not state_1 != state_2
    assert state_1 == state_2


def test_meteocat_weather_station_state_iter_01() -> None:
    state = MeteocatWeatherStationState(code=MeteocatWeatherStationStateCategory.ACTIVE,
                                        valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                        valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert dict(state) == {
        'id': None,
        'code': 'ACTIVE',
        'valid_from': "2024-01-01T00:00:00+0000",
        'valid_until': "2024-03-01T00:00:00+0000",
        'weather_station_id': None,
        'ts': None,
    }


def test_meteocat_weather_station_state_json_parser(meteocat_api_weather_station_states: str) -> None:
    lsts: List[List[MeteocatWeatherStationState]] = json.loads(meteocat_api_weather_station_states, cls=NoNoneInList,
                                                               object_hook=MeteocatWeatherStationState.object_hook_meteocat_api)
    for lst in lsts:
        for element in lst:
            assert isinstance(element, MeteocatWeatherStationState)
    element = lsts[0][0]
    assert isinstance(element, MeteocatWeatherStationState)
    assert element.code == MeteocatWeatherStationStateCategory.ACTIVE
    assert element.valid_from == datetime.datetime(1992, 5, 11, 15, 30, tzinfo=pytz.UTC)
    assert element.tzinfo_valid_from == 'UTC'
    assert element.valid_until == datetime.datetime(2002, 10, 29, 5, 0, tzinfo=pytz.UTC)
    assert element.tzinfo_valid_until == 'UTC'
