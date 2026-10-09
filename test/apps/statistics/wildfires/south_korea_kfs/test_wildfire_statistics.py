#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service burnt-area statistics application."""

import argparse
import csv
import datetime
import logging

import pytest

from src.apps.statistics.wildfires.south_korea_kfs import wildfire_statistics as app

logger = logging.getLogger("test-kfs-statistics")


def run(db_session, year=None, **kwargs):
    rows, partial = app.compute(db_session, year, logger, **kwargs)
    return rows, partial


def by_year(rows):
    return {row.year: row for row in rows}


def test_the_figures_per_year(fires):
    rows, _ = run(fires)
    years = by_year(rows)

    assert (years[2024].fires, years[2024].minimum, years[2024].maximum,
            years[2024].total) == (3, 0.5, 10.0, pytest.approx(12.5))
    assert (years[2025].fires, years[2025].minimum, years[2025].maximum,
            years[2025].total) == (2, 1.0, 100.0, pytest.approx(101.0))


def test_the_years_are_newest_first_then_the_total(fires):
    rows, _ = run(fires)
    assert [row.year_label for row in rows] == ["2025", "2024", app.TOTAL_LABEL]
    total = rows[-1]
    assert (total.fires, total.minimum, total.maximum) == (5, 0.5, 100.0)
    assert total.total == pytest.approx(113.5)


def test_the_country_is_south_korea_on_every_row(fires):
    rows, _ = run(fires)
    assert {row.country for row in rows} == {"South Korea"}


def test_the_year_is_the_local_one(fires):
    """23:30 on 30 December 2024 in Seoul is still 2024, though 14:30 UTC."""
    rows, _ = run(fires, year=2024)
    assert by_year(rows)[2024].fires == 3


def test_a_year_ending_before_december_is_partial(fires):
    _, partial = run(fires)
    assert partial == {2025: datetime.date(2025, 9, 11)}


def test_one_year_can_be_selected(fires):
    rows, _ = run(fires, year=2025)
    assert [row.year_label for row in rows] == ["2025", app.TOTAL_LABEL]


def test_one_province_can_be_selected(fires):
    rows, _ = run(fires, province_name="경북")
    years = by_year(rows)
    assert (years[2024].fires, years[2025].fires) == (1, 2)


def test_a_minimum_area_selects_the_fires_not_the_years(fires):
    rows, _ = run(fires, min_area=2.0)
    years = by_year(rows)
    assert (years[2024].fires, years[2024].minimum) == (2, 2.0)
    assert (years[2025].fires, years[2025].minimum) == (1, 100.0)


def test_an_empty_report_has_no_rows(fires):
    rows, partial = run(fires, year=2019)
    assert rows == [] and partial == {}


def test_the_partial_paragraph():
    assert app.partial_paragraph({}) is None
    assert "2025 (last fire 2025-09-11)" in app.partial_paragraph(
        {2025: datetime.date(2025, 9, 11)})


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

BASE = ["--db-name", "x", "--db-user", "y"]


def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(BASE)


@pytest.mark.parametrize("option, value", [("--country", "Korea"),
                                           ("--country-source", "geometry"),
                                           ("--area-method", "geodesic")])
def test_other_reports_options_are_refused_with_a_reason(capsys, option, value):
    with pytest.raises(SystemExit):
        app.parse_arguments([option, value, "--csv", "x.csv", *BASE])
    assert "there is no" in capsys.readouterr().err


def test_a_province_is_its_published_abbreviation():
    args = app.parse_arguments(["--province", "경북", "--csv", "x.csv", *BASE])
    assert args.province == "경북"
    with pytest.raises(SystemExit):
        app.parse_arguments(["--province", "Gyeongbuk", "--csv", "x.csv", *BASE])


@pytest.mark.parametrize("text", ["-5", "nan", "inf", "not a number"])
def test_a_nonsense_minimum_area_is_refused(text):
    with pytest.raises(argparse.ArgumentTypeError):
        app.hectares(text)


# --------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------

def test_the_csv(tmp_path, fires):
    path = tmp_path / "burnt.csv"
    rows, _ = run(fires)
    app.write_csv(rows, path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))
    assert tuple(table[0]) == app.COLUMNS
    assert table[-1] == ["South Korea", "Total", "5", "0.50", "100.00", "113.50"]


def test_the_docx_says_the_last_year_is_partial(tmp_path, fires):
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    rows, partial = run(fires)
    app.write_docx(rows, path, logger, partial=partial)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "Incomplete year(s): 2025" in text


def test_the_application_runs_end_to_end(tmp_path, fires, postgresql):
    info = postgresql.info
    path = tmp_path / "burnt.csv"
    argv = ["--csv", str(path), "--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user]
    if info.password:
        argv += ["--db-password", info.password]
    assert app.main(argv) == 0
    assert path.read_text(encoding="utf-8").count("\n") == 4
