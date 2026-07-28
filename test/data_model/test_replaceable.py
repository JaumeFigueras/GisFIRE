#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the replaceable-object Alembic operations.

``op.create_view()`` and ``op.drop_view()`` are covered end to end by
``test/test_migrations.py``, which runs them against a real database.
``op.replace_view()`` is not: nothing replaces a view until a revision changes
one, and by then the recipe has to work. These tests exercise it without a
database, driving the operations through stubs, so the machinery is verified
before the day it is first needed.
"""

import pytest

from src.data_model.replaceable import CreateViewOp
from src.data_model.replaceable import DropViewOp
from src.data_model.replaceable import ReplaceableObject
from src.data_model.replaceable import ReversibleOp


class FakeRevisionModule:
    """Stands in for a revision file's module, holding one view definition."""

    old_view = ReplaceableObject("v_test", "SELECT 1 AS id")


class FakeOperations:
    """Minimal stand-in for Alembic's ``op``, recording what it is asked to run.

    Attributes
    ----------
    invoked : list
        The operations passed to :meth:`invoke`, in order.
    """

    def __init__(self):
        self.invoked = []

    def invoke(self, operation):
        self.invoked.append(operation)

    def get_context(self):
        return self

    @property
    def script(self):
        return self

    def get_revision(self, version):
        assert version == "abcdef123456"
        return self

    @property
    def module(self):
        return FakeRevisionModule


NEW_VIEW = ReplaceableObject("v_test", "SELECT 2 AS id")


def test_replaceable_object_keeps_its_name_and_sql():
    view = ReplaceableObject("v_test", "SELECT 1 AS id")
    assert view.name == "v_test"
    assert view.sqltext == "SELECT 1 AS id"
    assert repr(view) == "ReplaceableObject(name='v_test')"


def test_create_and_drop_reverse_into_each_other():
    view = ReplaceableObject("v_test", "SELECT 1 AS id")
    assert isinstance(CreateViewOp(view).reverse(), DropViewOp)
    assert isinstance(DropViewOp(view).reverse(), CreateViewOp)
    # And the reversed operation still points at the same object.
    assert CreateViewOp(view).reverse().target is view


def test_the_base_operation_has_no_reverse():
    """``ReversibleOp`` is abstract: a new op type has to say how to undo itself."""
    with pytest.raises(NotImplementedError):
        ReversibleOp(ReplaceableObject("v_test", "SELECT 1 AS id")).reverse()


def test_replaces_drops_the_old_definition_and_creates_the_new_one():
    """An ``upgrade()``: the superseded view goes, this revision's view arrives."""
    operations = FakeOperations()

    CreateViewOp.replace(operations, NEW_VIEW, replaces="abcdef123456.old_view")

    drop, create = operations.invoked
    assert isinstance(drop, DropViewOp)
    assert drop.target is FakeRevisionModule.old_view
    assert isinstance(create, CreateViewOp)
    assert create.target is NEW_VIEW


def test_replace_with_puts_the_old_definition_back():
    """The matching ``downgrade()``, the mirror image of the test above."""
    operations = FakeOperations()

    CreateViewOp.replace(operations, NEW_VIEW, replace_with="abcdef123456.old_view")

    drop, create = operations.invoked
    assert isinstance(drop, DropViewOp)
    assert drop.target is NEW_VIEW
    assert isinstance(create, CreateViewOp)
    assert create.target is FakeRevisionModule.old_view


def test_replace_needs_to_be_told_which_definition_it_supersedes():
    """Neither argument given is a mistake, not a no-op: refuse it."""
    with pytest.raises(TypeError):
        CreateViewOp.replace(FakeOperations(), NEW_VIEW)
