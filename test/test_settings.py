#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the environment-based configuration."""

import pytest

from src.settings import database_url


@pytest.fixture
def db_env(monkeypatch):
    """Set the required GISFIRE_DB_* variables, clearing the optional ones."""
    monkeypatch.setenv("GISFIRE_DB_NAME", "gisfire")
    monkeypatch.setenv("GISFIRE_DB_USER", "gisfire")
    for variable in ("GISFIRE_DB_HOST", "GISFIRE_DB_PORT", "GISFIRE_DB_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)


def test_database_url_from_environment(db_env, monkeypatch):
    monkeypatch.setenv("GISFIRE_DB_HOST", "db.example.org")
    monkeypatch.setenv("GISFIRE_DB_PORT", "5433")
    monkeypatch.setenv("GISFIRE_DB_PASSWORD", "secret")

    assert database_url() == "postgresql+psycopg://gisfire:secret@db.example.org:5433/gisfire"


def test_database_url_defaults_to_localhost(db_env):
    assert database_url() == "postgresql+psycopg://gisfire@localhost:5432/gisfire"


def test_password_is_url_encoded(db_env, monkeypatch):
    """A password with URL-significant characters must not corrupt the URL."""
    monkeypatch.setenv("GISFIRE_DB_PASSWORD", "p@ss:w/rd")

    assert database_url() == "postgresql+psycopg://gisfire:p%40ss%3Aw%2Frd@localhost:5432/gisfire"


def test_driver_can_be_overridden(db_env):
    assert database_url(driver="postgresql").startswith("postgresql://")


@pytest.mark.parametrize("missing", ["GISFIRE_DB_NAME", "GISFIRE_DB_USER"])
def test_missing_required_variable_raises(db_env, monkeypatch, missing):
    """Fail loudly rather than connecting somewhere unintended."""
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        database_url()
