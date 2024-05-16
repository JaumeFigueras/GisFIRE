#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.data_model.data_provider import DataProvider


def test_data_provider_init_01() -> None:
    """
    Tests the initialization of a data provider
    """
    data_provider = DataProvider()
    assert data_provider.name is None
    assert data_provider.url is None
    data_provider = DataProvider(name='test name')
    assert data_provider.name == 'test name'
    assert data_provider.url is None
    data_provider = DataProvider(url='test url')
    assert data_provider.name is None
    assert data_provider.url == 'test url'
    data_provider = DataProvider('test name', 'test url')
    assert data_provider.name == 'test name'
    assert data_provider.url == 'test url'
