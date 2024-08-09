#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.data_model.variable import Variable


def test_variable_01() -> None:
    """
    Tests Variable class initialization.

    :return: None
    """
    variable = Variable()
    assert variable.name is None
    variable = Variable(name='var')
    assert variable.name == 'var'


def test_variable_iter_01() -> None:
    """
    Tests Variable class iterator to convert it to a dict.
    :return:
    """
    var = Variable(name='var')
    assert dict(var) == {
        'id': None,
        'name': 'var',
        'ts': None,
    }
