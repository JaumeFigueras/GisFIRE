#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service release reader."""

import datetime

import pytest

from src.apps.imports.wildfires.south_korea_kfs import readers
from src.providers.south_korea_kfs import COLUMNS

from .conftest import fire
from .conftest import write_release


def test_a_cp949_release_is_read(tmp_path):
    release = readers.read_release(write_release(tmp_path / "산불발생통계.csv"))

    assert release.name == "산불발생통계.csv"
    assert release.encoding == "cp949"
    assert len(release.records) == 4
    first = release.records[0]
    assert first.row == 2
    assert first.year == 2025
    assert first.start == datetime.datetime(2025, 3, 22, 11, 25)
    assert first.end == datetime.datetime(2025, 3, 22, 18, 40)
    assert first.end_date_problem is None
    assert (first.office, first.province, first.municipality, first.township,
            first.village) == ("경북", "경북", "의성", "안계", "용기")
    assert first.cause_category_code is None
    assert first.area_ha == 52707.3
    assert first.problems == []


def test_a_utf8_copy_is_read_too(tmp_path):
    release = readers.read_release(write_release(tmp_path / "a.csv", encoding="utf-8-sig"))
    assert release.encoding == "utf-8-sig"
    assert release.records[0].office == "경북"


def test_names_are_trimmed_and_blanks_are_none(tmp_path):
    records = readers.read_release(write_release(tmp_path / "a.csv")).records
    assert records[1].province == "충남"
    assert records[2].municipality is None
    assert records[2].township is None


def test_the_cause_text_is_kept_as_published(tmp_path):
    """The backtick goes at lookup, not here: a record says what the file said."""
    records = readers.read_release(write_release(tmp_path / "a.csv")).records
    assert records[1].cause_text == "`전기누전"


def test_bad_ends_are_flagged_not_dropped(tmp_path):
    records = readers.read_release(write_release(tmp_path / "a.csv")).records
    assert records[1].end_date_problem == "extinguish_before_start"
    assert records[1].end == datetime.datetime(2024, 4, 6, 0, 0)
    assert records[3].end_date_problem == "extinguish_year_invalid"
    assert any("extinguish" in problem for problem in records[3].problems)


def test_a_wrong_weekday_is_a_problem(tmp_path):
    record, = readers.read_release(
        write_release(tmp_path / "a.csv", [fire(weekday="월")])).records
    assert any("weekday" in problem for problem in record.problems)


@pytest.mark.parametrize("row, problem", [
    (fire(start="2025-02-30 10:00"), "start"),
    (fire(start="2025-03-22 25:00"), "start"),
    (fire(area=""), "area"),
    (fire(area="-1"), "area"),
    (fire(text=""), "cause text"),
])
def test_unparseable_values_are_problems(tmp_path, row, problem):
    record, = readers.read_release(write_release(tmp_path / "a.csv", [row])).records
    assert any(problem in message for message in record.problems)


def test_a_different_header_is_refused(tmp_path):
    header = tuple(reversed(COLUMNS))
    with pytest.raises(RuntimeError, match="another order"):
        readers.read_release(write_release(tmp_path / "a.csv", [], header=header))


def test_an_unrelated_csv_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="not a KFS"):
        readers.read_release(write_release(tmp_path / "a.csv", [], header=("테이블", "순서")))


def test_a_short_row_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="line 2"):
        readers.read_release(write_release(tmp_path / "a.csv", [fire()[:10]]))


def test_blank_lines_are_ignored(tmp_path):
    release = readers.read_release(
        write_release(tmp_path / "a.csv", [fire(), [""] * len(COLUMNS)]))
    assert len(release.records) == 1
