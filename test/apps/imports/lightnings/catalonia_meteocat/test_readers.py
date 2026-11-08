#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the MeteoCat extract reader.

No database: this is the part of the import that turns a published line into a
record. What is pinned down is what the delivery makes easy to get wrong — that the
instant is UTC to the microsecond, that a version-1 ``0`` is "not recorded" and not
a value, and that strokes are numbered within their flash by instant and not by
their order in the file, a flash being the network version *and* the flash id.
"""

import datetime

import pytest

from src.apps.imports.lightnings.catalonia_meteocat import readers

from .conftest import HEADER
from .conftest import ROWS_2009
from .conftest import ROWS_2010
from .conftest import extract_2009
from .conftest import row
from .conftest import write_extract

UTC = datetime.timezone.utc


@pytest.fixture
def extract(tmp_path):
    return readers.read_extract(extract_2009(tmp_path))


def by_row(extract, line: int):
    """The record read from a given file line."""
    return next(record for record in extract.records if record.row == line)


# --------------------------------------------------------------------------
# The file
# --------------------------------------------------------------------------

def test_every_row_is_read(extract, tmp_path):
    assert extract.name == "DATMET-12706_cg_cm_2009.csv"
    assert len(extract.records) == len(ROWS_2009)
    assert extract.problems == []


def test_rows_are_numbered_by_file_line(extract):
    """Line 1 is the header, so the first stroke is line 2."""
    assert [record.row for record in extract.records] == list(range(2, 2 + len(ROWS_2009)))


def test_a_file_with_another_header_is_refused(tmp_path):
    path = write_extract(tmp_path / "other.csv", ROWS_2009, header='"a";"b";"c"')
    with pytest.raises(RuntimeError, match="header"):
        readers.read_extract(path)


def test_an_empty_file_is_refused(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="ascii")
    with pytest.raises(RuntimeError):
        readers.read_extract(path)


# --------------------------------------------------------------------------
# A row
# --------------------------------------------------------------------------

def test_a_version_2_row_is_read_as_published(extract):
    record = by_row(extract, 7)
    assert record.flash_id == 1832764
    assert record.date_time == datetime.datetime(2009, 9, 15, 14, 2, 11, 500000, tzinfo=UTC)
    assert record.peak_current == -30.5
    assert record.chi_squared == 1.2
    assert (record.ellipse_major_axis, record.ellipse_minor_axis) == (1800.0, 500.0)
    assert record.number_of_sensors == 3
    assert record.cloud_to_ground is True
    assert record.municipality_code is None
    assert (record.longitude, record.latitude) == (1.51, 41.61)
    assert record.network_version == 2


def test_the_instant_is_utc_to_the_microsecond(extract):
    assert by_row(extract, 2).date_time == \
        datetime.datetime(2009, 1, 2, 5, 32, 19, 3386, tzinfo=UTC)


def test_a_version_1_row_stores_not_recorded_as_none(extract):
    record = by_row(extract, 2)
    assert record.network_version == 1
    assert record.number_of_sensors is None
    assert record.chi_squared is None
    # The ellipse *is* recorded, as a circle.
    assert (record.ellipse_major_axis, record.ellipse_minor_axis) == (5250.0, 5250.0)


def test_a_version_2_chi_squared_of_zero_is_a_value(tmp_path):
    """Only the sensor count tells the networks apart; a v2 chi² of 0 is real."""
    path = write_extract(tmp_path / "x.csv", [
        row(1, "2015-07-01 10:00:00.000001", "-5", "0", "300", "100", "3")])
    record = readers.read_extract(path).records[0]
    assert record.network_version == 2
    assert record.chi_squared == 0.0


def test_the_municipality_code_is_kept_as_published(extract):
    """Six digits, leading zero included: it is a code, not a number."""
    assert by_row(extract, 2).municipality_code == "080193"


def test_an_intra_cloud_stroke_is_not_cloud_to_ground(tmp_path):
    path = write_extract(tmp_path / "x.csv", ROWS_2010)
    records = readers.read_extract(path).records
    assert [record.cloud_to_ground for record in records] == [True, False]


@pytest.mark.parametrize(("line", "reason"), [
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "abc", "1", "300", "100", "3"),
                 "correntpic", id="current-not-a-number"),
    pytest.param(row(1, "2015-13-01 10:00:00.000001", "-5", "1", "300", "100", "3"),
                 "data", id="impossible-date"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "1", "300", "100", "3",
                     ground="x"), "nuvolterra", id="ground-flag-unknown"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "1", "300", "100", "3",
                     municipality="8019"), "idmunicipi", id="municipality-not-six-digits"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "1", "300", "100", "3",
                     longitude="200"), "longitud", id="longitude-out-of-range"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "1", "100", "300", "3"),
                 "eixmenor", id="minor-axis-larger"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "1", "300", "100", "-1"),
                 "numsensors", id="negative-sensors"),
    pytest.param(row(1, "2015-07-01 10:00:00.000001", "-5", "3", "300", "100", "0"),
                 "chi2", id="version-1-with-a-chi-squared"),
    pytest.param('1;"2015-07-01 10:00:00.000001";-5;1', "columns", id="short-row"),
])
def test_a_row_that_cannot_be_stored_is_reported_and_skipped(tmp_path, line, reason):
    good = row(2, "2015-07-01 11:00:00.000001", "-5", "1", "300", "100", "3")
    path = write_extract(tmp_path / "x.csv", [line, good])
    extract = readers.read_extract(path)

    assert [record.row for record in extract.records] == [3]
    assert len(extract.problems) == 1
    line_number, message = extract.problems[0]
    assert line_number == 2
    assert reason in message


# --------------------------------------------------------------------------
# Flashes
# --------------------------------------------------------------------------

def test_strokes_are_numbered_by_instant_not_by_file_order(extract):
    """Lines 3-5 are published 2nd, 1st, 3rd."""
    numbering = [(by_row(extract, line).stroke_index, by_row(extract, line).multiplicity)
                 for line in (3, 4, 5)]
    assert numbering == [(2, 3), (1, 3), (3, 3)]


def test_a_single_stroke_flash(extract):
    record = by_row(extract, 2)
    assert (record.stroke_index, record.multiplicity) == (1, 1)


def test_the_same_flash_id_in_two_networks_is_two_flashes(extract):
    """Line 6 is version 1's flash 1832764, lines 7-8 version 2's."""
    assert (by_row(extract, 6).stroke_index, by_row(extract, 6).multiplicity) == (1, 1)
    assert (by_row(extract, 7).stroke_index, by_row(extract, 7).multiplicity) == (1, 2)
    assert (by_row(extract, 8).stroke_index, by_row(extract, 8).multiplicity) == (2, 2)


def test_strokes_at_the_same_instant_are_numbered_in_file_order(extract):
    assert (by_row(extract, 9).stroke_index, by_row(extract, 10).stroke_index) == (1, 2)
    assert by_row(extract, 9).multiplicity == by_row(extract, 10).multiplicity == 2


def test_number_flashes_numbers_a_list_in_place():
    first = readers.StrokeRecord(
        row=2, flash_id=7, date_time=datetime.datetime(2015, 1, 1, 0, 0, 0, 2, tzinfo=UTC),
        peak_current=-5.0, chi_squared=1.0, ellipse_major_axis=300.0, ellipse_minor_axis=100.0,
        number_of_sensors=3, cloud_to_ground=True, municipality_code=None,
        longitude=2.0, latitude=41.0, network_version=2)
    second = readers.StrokeRecord(
        row=3, flash_id=7, date_time=datetime.datetime(2015, 1, 1, 0, 0, 0, 1, tzinfo=UTC),
        peak_current=-6.0, chi_squared=1.0, ellipse_major_axis=300.0, ellipse_minor_axis=100.0,
        number_of_sensors=3, cloud_to_ground=True, municipality_code=None,
        longitude=2.0, latitude=41.0, network_version=2)
    readers.number_flashes([first, second])
    assert (first.stroke_index, second.stroke_index) == (2, 1)
    assert first.multiplicity == second.multiplicity == 2


# --------------------------------------------------------------------------
# Years
# --------------------------------------------------------------------------

def test_records_are_grouped_by_utc_year(tmp_path):
    path = write_extract(tmp_path / "x.csv", [ROWS_2009[-1], ROWS_2010[0]])
    years = readers.by_year(readers.read_extract(path).records)
    assert sorted(years) == [2009, 2010]
    assert [record.row for record in years[2009]] == [2]
    assert [record.row for record in years[2010]] == [3]


def test_the_header_constant_is_the_published_one():
    assert HEADER.startswith('"secidx";"data"')
