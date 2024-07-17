#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import freezegun
import datetime

from src.data_model.user import User


@freezegun.freeze_time('2024-01-01 12:00:00')
def test_user_init_01() -> None:
    """
    Tests the initialization of a user

    :return: None
    """
    user = User()
    assert user.id is None
    assert user.username is None
    assert len(user.token) == 64
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=12, day=31, hour=12, minute=0, second=0)


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_user_init_02() -> None:
    """
    Tests the initialization of a user

    :return: None
    """
    user = User()
    assert user.id is None
    assert user.username is None
    assert len(user.token) == 64
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_user_init_03() -> None:
    """
    Tests the initialization of a user

    :return: None
    """
    user = User(username="test")
    assert user.id is None
    assert user.username == "test"
    assert len(user.token) == 64
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)
    user = User(token="test")
    assert user.id is None
    assert user.username is None
    assert user.token == "test"
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)
    user = User(is_admin=True)
    assert user.id is None
    assert user.username is None
    assert len(user.token) == 64
    assert user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)
    user = User(valid_until=datetime.datetime(year=2025, month=1, day=1, hour=12, minute=0, second=0))
    assert user.id is None
    assert user.username is None
    assert len(user.token) == 64
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2025, month=1, day=1, hour=12, minute=0, second=0)
    user = User(username='test@test.com')
    assert user.id is None
    assert user.username == "test@test.com"
    assert len(user.token) == 64
    assert not user.is_admin
    assert user.valid_until == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)
    user = User(username='test@test.com', is_admin=True, valid_until=datetime.datetime(year=2099, month=1, day=1, hour=12, minute=0, second=0))
    assert user.id is None
    assert user.username == "test@test.com"
    assert len(user.token) == 64
    assert user.is_admin
    assert user.valid_until == datetime.datetime(year=2099, month=1, day=1, hour=12, minute=0, second=0)


def test_user_generate_token_01() -> None:
    """
    Tests the generation of a token

    :return: None
    """
    token = User._generate_token()
    for char in token:
        assert char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!()_:;@?"
    assert len(token) == 64


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_user_generate_valid_until_01() -> None:
    """
    Tests the generation of a valid until date is one year more

    :return: None
    """
    valid_date = User._generate_valid_until()
    assert valid_date == datetime.datetime(year=2024, month=1, day=1, hour=12, minute=0, second=0)