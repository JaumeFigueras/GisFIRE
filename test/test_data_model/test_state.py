#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest

from sqlalchemy.orm import Session
from shapely.geometry import Point

from src.data_model.state import State

from typing import Union
from typing import List


def test_state_01() -> None:
    state = State()
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state.valid_from == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_from == 'UTC'
    assert state.valid_until is None
    assert state.tzinfo_valid_until is None
    state = State(valid_until=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state.valid_from is None
    assert state.tzinfo_valid_from is None
    assert state.valid_until == datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    assert state.tzinfo_valid_until == 'UTC'


def test_state_equals_01() -> None:
    state_1 = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                    valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state_1 != 1
    assert state_1 != 'Hello'
    assert not state_1 == 1
    assert not state_1 == 'Hello'
    state_2 = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                    valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.timezone('America/New_York')))
    assert state_1 != state_2
    assert not state_1 == state_2
    state_2 = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert state_1 != state_2
    assert not state_1 == state_2
    state_2 = State()
    assert state_1 != state_2
    assert not state_1 == state_2
    state_2 = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                    valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert not state_1 != state_2
    assert state_1 == state_2


def test_state_iter_01() -> None:
    state = State(valid_from=datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                  valid_until=datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=pytz.UTC))
    assert dict(state) == {
        'valid_from': "2024-01-01T00:00:00+0000",
        'valid_until': "2024-03-01T00:00:00+0000",
    }
