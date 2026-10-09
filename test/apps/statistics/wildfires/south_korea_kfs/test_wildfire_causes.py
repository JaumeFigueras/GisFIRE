#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service counts-by-cause application."""

import csv
import logging

import pytest

from src.apps.statistics.wildfires.new_zealand_wod import wildfire_causes as wod
from src.apps.statistics.wildfires.south_korea_kfs import wildfire_causes as app
from src.apps.statistics.wildfires.south_korea_kfs import wildfire_statistics

logger = logging.getLogger("test-kfs-causes")


def by_year(rows):
    return {row.year: row for row in rows}


# --------------------------------------------------------------------------
# The shared fire causes
# --------------------------------------------------------------------------

def test_the_shared_table_has_the_new_zealand_columns():
    assert app.COLUMNS == wod.COLUMNS


def test_the_shared_counts(fires):
    years = by_year(app.compute(fires))

    row = years[2024]
    assert (row.fires, row.lightning, row.natural, row.human, row.unknown) == (3, 1, 0, 1, 1)
    assert row.determined == 2
    assert row.lightning_hectares == pytest.approx(2.0)
    assert row.determined_hectares == pytest.approx(2.5)
    # Lightning is half the determined fires and 80% of their area.
    assert row.values[5] == "50.00"
    assert row.values[10] == "80.00"


def test_a_rekindle_is_unknown(fires):
    row = by_year(app.compute(fires))[2025]
    assert (row.human, row.unknown, row.determined) == (1, 1, 1)


def test_the_total_recomputes_the_shares(fires):
    total = app.compute(fires)[-1]
    assert total.is_total
    assert (total.fires, total.determined, total.lightning) == (5, 3, 1)
    assert total.values[5] == "33.33"


def test_the_fires_agree_with_the_statistics_report(fires):
    causes = [row.fires for row in app.compute(fires)]
    statistics, _ = wildfire_statistics.compute(fires, None, logger)
    assert causes == [row.fires for row in statistics]


def test_the_scope_applies(fires):
    rows = app.compute(fires, year=2024, province_name="경북")
    assert [(row.year_label, row.fires, row.unknown) for row in rows] == [
        ("2024", 1, 1), ("Total", 1, 1)]


# --------------------------------------------------------------------------
# The classes
# --------------------------------------------------------------------------

def test_the_class_rows(fires):
    rows = app.compute_classes(fires)

    assert [(row.year_label, row.cause_class) for row in rows] == [
        ("2025", "agricultural_burning"), ("2025", "rekindle"),
        ("2024", "visitor"), ("2024", "unknown"), ("2024", "lightning"),
        ("Total", "visitor"), ("Total", "unknown"), ("Total", "agricultural_burning"),
        ("Total", "lightning"), ("Total", "rekindle"),
    ]


def test_a_year_of_classes_adds_up_to_all_its_fires(fires):
    rows = [row for row in app.compute_classes(fires) if row.year == 2025]
    assert sum(row.fires for row in rows) == rows[0].year_fires == 2
    agricultural = rows[0]
    assert agricultural.values[4:] == ("50.00", "100.00", "99.01", "1")


def test_the_total_classes_are_over_every_year(fires):
    total = {row.cause_class: row for row in app.compute_classes(fires) if row.is_total}
    assert total["unknown"].fires == 1
    assert total["unknown"].year_fires == 5
    assert total["unknown"].hectares == pytest.approx(10.0)
    assert sum(row.suspected for row in total.values()) == 2


def test_no_fires_no_classes(fires):
    assert app.compute_classes(fires, year=2019) == []


# --------------------------------------------------------------------------
# The command line and the outputs
# --------------------------------------------------------------------------

BASE = ["--db-name", "x", "--db-user", "y"]


def test_an_output_is_required(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(BASE)
    assert "--classes-csv" in capsys.readouterr().err


def test_the_classes_csv_alone_is_enough():
    args = app.parse_arguments(["--classes-csv", "c.csv", *BASE])
    assert args.csv is None and args.docx is None


def test_the_country_option_is_refused(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--country", "Korea", "--csv", "x.csv", *BASE])
    assert "there is no" in capsys.readouterr().err


def run_application(tmp_path, postgresql, *outputs):
    info = postgresql.info
    argv = [*outputs, "--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user]
    if info.password:
        argv += ["--db-password", info.password]
    return app.main(argv)


def test_both_csvs_are_written(tmp_path, fires, postgresql):
    shared, classes = tmp_path / "causes.csv", tmp_path / "classes.csv"
    assert run_application(tmp_path, postgresql, "--csv", str(shared),
                           "--classes-csv", str(classes)) == 0

    with shared.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))
    assert tuple(table[0]) == app.COLUMNS
    assert len(table) == 4
    with classes.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))
    assert tuple(table[0]) == app.CLASS_COLUMNS
    assert len(table) == 11


def test_the_docx_holds_both_tables(tmp_path, fires, postgresql):
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    assert run_application(tmp_path, postgresql, "--docx", str(path)) == 0
    assert len(docx.Document(str(path)).tables) == 2
