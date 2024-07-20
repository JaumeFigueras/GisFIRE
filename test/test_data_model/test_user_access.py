#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from src.data_model.user_access import UserAccess
from src.data_model.user_access import HttpMethods


def test_user_access_init_01() -> None:
    """
    Tests the initialization of a user access

    :return: None
    """
    user_access = UserAccess()
    assert user_access.ip is None
    assert user_access.url is None
    assert user_access.method is None
    assert user_access.params is None
    assert user_access.user_id is None
    user_access = UserAccess(ip='123.45.67.89')
    assert user_access.ip == '123.45.67.89'
    assert user_access.url is None
    assert user_access.method is None
    assert user_access.params is None
    assert user_access.user_id is None
    user_access = UserAccess(url='http://test.com/api')
    assert user_access.ip is None
    assert user_access.url == 'http://test.com/api'
    assert user_access.method is None
    assert user_access.params is None
    assert user_access.user_id is None
    user_access = UserAccess(method=HttpMethods.POST)
    assert user_access.ip is None
    assert user_access.url is None
    assert user_access.method == HttpMethods.POST
    assert user_access.params is None
    assert user_access.user_id is None
    user_access = UserAccess(params={'key': 'value'})
    assert user_access.ip is None
    assert user_access.url is None
    assert user_access.method is None
    assert user_access.params == {'key': 'value'}
    assert user_access.user_id is None
    user_access = UserAccess(user=1)
    assert user_access.ip is None
    assert user_access.url is None
    assert user_access.method is None
    assert user_access.params is None
    assert user_access.user_id == 1
    user_access = UserAccess(ip='159.25.36.214', url='/api/test', method=HttpMethods.GET, params={'date': '2024-01-01'}, user=1)
    assert user_access.ip == '159.25.36.214'
    assert user_access.url == '/api/test'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {'date': '2024-01-01'}
    assert user_access.user_id == 1

