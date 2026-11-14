#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for splitting a time sequence at quiet gaps."""

import pytest

from gisfire_algorithms.thunderstorm.chunking import split_at_gaps


def test_gap_of_exactly_the_limit_does_not_cut():
    assert split_at_gaps([0.0, 900.0, 1800.0], 900.0) == [slice(0, 3)]


def test_gap_just_over_the_limit_cuts():
    assert split_at_gaps([0.0, 900.0, 1800.5, 1801.0, 5000.0], 900.0) == [
        slice(0, 2), slice(2, 4), slice(4, 5),
    ]


def test_empty_and_single():
    assert split_at_gaps([], 900.0) == []
    assert split_at_gaps([7.0], 900.0) == [slice(0, 1)]


def test_validation():
    with pytest.raises(ValueError, match="positive"):
        split_at_gaps([0.0, 1.0], 0.0)
    with pytest.raises(ValueError, match="sorted"):
        split_at_gaps([1.0, 0.0], 900.0)
