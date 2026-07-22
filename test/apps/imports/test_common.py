#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the plumbing shared by the import applications.

The ``ogr2ogr`` invocation is checked by intercepting :func:`subprocess.run`
rather than by running it: what matters here is which flags are passed and which
streams are captured, and both are visible in the call.
"""

import argparse
import logging
import subprocess
import threading
import time

import pytest

from sqlalchemy import select
from sqlalchemy import text

from src.apps.imports import common
from src.data_model.data_provider import DataProvider

PROVIDER = ("GWIS", "Global Wildfire Database v3", "Global Wildfire Information System",
            "https://gwis.jrc.ec.europa.eu/")

SETTINGS = {"host": "localhost", "port": "5432", "name": "gisfire", "user": "gisfire", "password": ""}


@pytest.fixture
def args():
    return argparse.Namespace(ogr2ogr="ogr2ogr")


@pytest.fixture
def recorded_run(monkeypatch):
    """Intercept ``subprocess.run``, recording the command and the stream arguments."""
    recorded = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=None, stderr="")

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    return recorded


def load(args, level):
    logger = logging.getLogger(f"test-common-{level}")
    logger.setLevel(level)
    common.load_staging_table("source.shp", "layer", "staging.table", args, SETTINGS, logger)


def test_the_progress_bar_is_asked_for_and_left_on_stdout(args, recorded_run):
    """A load can run for minutes; without the bar it looks hung.

    ``stdout=None`` inherits the terminal, which is what makes the bar appear as
    it is drawn rather than in one lump at the end.
    """
    load(args, logging.INFO)

    assert "-progress" in recorded_run["command"]
    assert recorded_run["kwargs"]["stdout"] is None


def test_a_quiet_run_asks_for_no_progress(args, recorded_run):
    """Below INFO the user has asked not to be told, and the log may be redirected."""
    load(args, logging.WARNING)

    assert "-progress" not in recorded_run["command"]
    assert recorded_run["kwargs"]["stdout"] is subprocess.DEVNULL


@pytest.mark.parametrize("level", [logging.INFO, logging.WARNING])
def test_stderr_is_captured_whatever_the_level(args, recorded_run, level):
    """It holds the diagnostics, and it is the only clue when ogr2ogr fails."""
    load(args, level)

    assert recorded_run["kwargs"]["stderr"] is subprocess.PIPE


def test_a_provider_being_inserted_by_someone_else_is_waited_for_and_reused(db_session):
    """The look-then-insert this replaced killed every racing importer but the winner.

    Deterministic rather than hopeful: the competing row is inserted on a second
    connection and left uncommitted, so the lookup inside
    :func:`~src.apps.imports.common.get_or_create_data_provider` is guaranteed to
    miss and its insert is guaranteed to block on the unique index. A plain
    ``INSERT`` would raise ``UniqueViolation`` the moment the winner commits;
    ``ON CONFLICT DO NOTHING`` plus a second lookup returns the winner's row.
    """
    logger = logging.getLogger("test-common-race")
    name, product, full_name, url = PROVIDER

    winner = db_session.get_bind().connect()
    winner.execute(text(
        "INSERT INTO data_provider (name, product, full_name, url) "
        "VALUES (:name, :product, :full_name, :url)"
    ), {"name": name, "product": product, "full_name": full_name, "url": url})

    outcome: list[object] = []

    def loser():
        try:
            outcome.append(common.get_or_create_data_provider(
                db_session, name, product, full_name, url, logger).id)
        except Exception as error:  # noqa: BLE001  (reported by the assertions below)
            outcome.append(error)

    thread = threading.Thread(target=loser)
    thread.start()
    try:
        time.sleep(0.5)
        assert thread.is_alive(), "the insert should be blocked on the uncommitted row"
        winner.commit()
        thread.join(timeout=30)
    finally:
        winner.close()

    assert not thread.is_alive()
    assert outcome and not isinstance(outcome[0], Exception), f"raised {outcome[0]!r}"
    assert len(db_session.scalars(select(DataProvider)).all()) == 1
    assert outcome[0] == db_session.scalar(select(DataProvider.id))


def test_a_failure_still_reports_what_ogr2ogr_said(args, monkeypatch):
    def failing_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout=None,
                                           stderr="ERROR 1: no such table\n")

    monkeypatch.setattr(common.subprocess, "run", failing_run)

    with pytest.raises(RuntimeError, match="ERROR 1: no such table"):
        load(args, logging.INFO)
