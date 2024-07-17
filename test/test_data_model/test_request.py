#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlalchemy.orm

from src.data_model.request import Request

import datetime


def test_day_request_init_01() -> None:
    """
    Tests the initialization of a day value
    """
    day_request = Request()
    assert day_request.uri is None
    assert day_request.params == {}
    assert day_request.request_result is None
    day_request = Request(uri='test')
    assert day_request.uri == 'test'
    assert day_request.params == {}
    assert day_request.request_result is None
    day_request = Request(params={'from': datetime.date(2020, 1, 1).strftime('%Y-%m-%d'), 'to': datetime.date(2020, 1, 1).strftime('%Y-%m-%d')})
    assert day_request.uri is None
    assert day_request.params == {'from': datetime.date(2020, 1, 1).strftime('%Y-%m-%d'), 'to': datetime.date(2020, 1, 1).strftime('%Y-%m-%d')}
    assert day_request.request_result is None
    day_request = Request(request_result=200)
    assert day_request.uri is None
    assert day_request.params == {}
    assert day_request.request_result == 200


def test_day_request_init_02() -> None:
    """
    Tests the initialization of a day value
    """
    day_request = Request(uri='AAPL', params={'from': datetime.date(2020, 1, 1).strftime('%Y-%m-%d'), 'to': datetime.date(2020, 1, 1).strftime('%Y-%m-%d')}, request_result=404)
    assert day_request.uri == 'AAPL'
    assert day_request.params == {'from': datetime.date(2020, 1, 1).strftime('%Y-%m-%d'), 'to': datetime.date(2020, 1, 1).strftime('%Y-%m-%d')}
    assert day_request.request_result == 404

