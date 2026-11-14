#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the reader of the FMI downloader's monthly files.

No database. What matters: that the converted values are those the model
expects (metres, NULL for "not recorded", the cloud flag the right way round);
that every row a CHECK would refuse is refused here, with its reason; and that a
month's records come out in an order of their own, the same whatever order the
file holds them in.
"""

import datetime
import gzip
import json
import random

import pytest

from src.apps.imports.lightnings.finland_fmi import readers
from src.providers import finland_fmi

from .conftest import HEADER
from .conftest import MID_JULY
from .conftest import REAL_ROWS
from .conftest import ROWS_2023_07
from .conftest import july_2023
from .conftest import row
from .conftest import write_month

UTC = datetime.timezone.utc
JULY = (datetime.datetime(2023, 7, 1, tzinfo=UTC), datetime.datetime(2023, 8, 1, tzinfo=UTC))


def parse(line: str):
    return readers.parse_row(line.split(","), 2, *JULY)


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("name", "month"), [
    ("fmi_lightning_2023-07.csv.gz", (2023, 7)),
    ("fmi_lightning_1998-01.csv.gz", (1998, 1)),
    ("fmi_lightning_2023-13.csv.gz", None),
    ("fmi_lightning_2023-07.meta.json", None),
    ("fmi_lightning_2023-07.csv.gz.part", None),
    ("DATMET-12706_cg_cm_2014.csv", None),
])
def test_the_month_comes_from_the_file_name(tmp_path, name, month):
    assert readers.month_of(tmp_path / name) == month


def test_december_ends_at_the_new_year(tmp_path):
    content = readers.MonthFile(path=tmp_path / "fmi_lightning_2022-12.csv.gz", year=2022, month=12)
    assert (content.start, content.end) == (datetime.datetime(2022, 12, 1, tzinfo=UTC),
                                            datetime.datetime(2023, 1, 1, tzinfo=UTC))


def test_a_blank_line_is_skipped(tmp_path):
    path = tmp_path / "fmi_lightning_2023-07.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(f"{HEADER}\n{row(MID_JULY, 1, 1, '-5')}\n\n")
    content = readers.read_month(path)
    assert (len(content.records), content.problems) == (1, [])


def test_the_sidecar_sits_beside_the_file(tmp_path):
    assert readers.sidecar_path(tmp_path / "fmi_lightning_2023-07.csv.gz") == \
        tmp_path / "fmi_lightning_2023-07.meta.json"


def test_a_monthly_file_has_no_header_problem(tmp_path):
    assert readers.header_problem(july_2023(tmp_path)) is None


def test_the_header_is_the_downloaders():
    assert HEADER.split(",") == list(finland_fmi.FILE_COLUMNS)


@pytest.mark.parametrize(("name", "content", "reason"), [
    ("fmi_lightning_2023-07.csv.gz", "gzip:unixtime,lat,lon\n", "unexpected header"),
    ("fmi_lightning_2023-07.csv.gz", "plain:not gzip at all", "not a readable gzip"),
    ("lightning_2023-07.csv.gz", "gzip:" + HEADER + "\n", "not named"),
])
def test_a_file_that_is_not_a_monthly_file_says_why(tmp_path, name, content, reason):
    path = tmp_path / name
    kind, _, body = content.partition(":")
    if kind == "gzip":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(body)
    else:
        path.write_text(body)
    assert reason in readers.header_problem(path)


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def test_a_real_row_is_converted():
    """The first stroke of flash 30645787, as the downloader wrote it."""
    line = next(r for r in REAL_ROWS if r.split(",")[3:5] == ["30645787", "4"])
    record = parse(line)
    assert record.date_time == datetime.datetime(2023, 7, 1, 12, 0, 15, tzinfo=UTC)
    assert (record.latitude, record.longitude) == (59.7094, 31.8554)
    assert (record.flash_id, record.published_multiplicity) == (30645787, 4)
    assert record.peak_current == -83.0
    assert record.cloud_to_ground is True
    assert (record.number_of_sensors, record.degrees_of_freedom) == (10, 7)
    assert record.ellipse_angle == 109.9
    # Kilometres to metres, exactly.
    assert (record.ellipse_major_axis, record.ellipse_minor_axis) == (700.0, 100.0)
    assert record.chi_squared == 0.4
    assert (record.rise_time, record.peak_to_zero_time) == (8.9, 30.4)
    assert (record.angle_indicator, record.signal_indicator, record.timing_indicator) == (1, 0, 1)
    assert record.stroke_status == 17


@pytest.mark.parametrize(("kilometres", "metres"), [
    ("0.3", 300.0), ("0.1", 100.0), ("0.7", 700.0), ("14.7", 14700.0), ("0", 0.0), ("50", 50000.0),
])
def test_the_ellipse_axes_are_metres_without_float_noise(kilometres, metres):
    record = parse(row(MID_JULY, 1, 1, "-5", major="50", minor=kilometres))
    assert record.ellipse_minor_axis == metres


def test_a_peak_current_of_zero_is_not_recorded():
    assert parse(row(MID_JULY, 1, 1, "0")).peak_current is None


def test_an_intra_cloud_stroke_is_not_cloud_to_ground():
    assert parse(row(MID_JULY, 1, 1, "9", cloud="1")).cloud_to_ground is False


def test_the_indicators_and_status_are_kept_whatever_they_are():
    record = parse(row(MID_JULY, 1, 1, "-5", indicators="0,0,0", status="101"))
    assert (record.angle_indicator, record.signal_indicator, record.timing_indicator,
            record.stroke_status) == (0, 0, 0, 101)


def test_the_edges_seen_in_the_data_are_accepted():
    record = parse(row(MID_JULY, 0, 0, "-5", sensors="2", dof="0", angle="180", major="0.1",
                       minor="0", chi="0", rise="0", ptz="0"))
    assert (record.ellipse_angle, record.chi_squared, record.degrees_of_freedom) == (180.0, 0.0, 0)


@pytest.mark.parametrize(("line", "reason"), [
    pytest.param(row(MID_JULY, 1, 1, "NaN"), "peak_current is NaN", id="nan"),
    pytest.param(row(MID_JULY, 1, 1, "-5", chi="inf"), "chi_square is inf", id="infinite"),
    pytest.param(row(MID_JULY, 1, 1, "abc"), "peak_current is not a number", id="not-a-number"),
    pytest.param(row(MID_JULY, 1.5, 1, "-5"), "flash_id is not an integer", id="flash-not-integer"),
    pytest.param(row(MID_JULY, -1, 1, "-5"), "flash_id is below 0", id="negative-flash"),
    pytest.param(row(MID_JULY, 1, -1, "-5"), "multiplicity is below 0", id="negative-multiplicity"),
    pytest.param(row(MID_JULY, 1, 1, "-5", sensors="0"), "sensors is below 1", id="no-sensor"),
    pytest.param(row(MID_JULY, 1, 1, "-5", dof="-1"), "freedom_degree is below 0", id="negative-dof"),
    pytest.param(row(MID_JULY, 1, 1, "-5", cloud="2"), "cloud_indicator is above 1", id="cloud-2"),
    pytest.param(row(MID_JULY, 1, 1, "-5", angle="180.1"), "ellipse_angle", id="angle"),
    pytest.param(row(MID_JULY, 1, 1, "-5", major="0.1", minor="0.3"), "larger than", id="axes"),
    pytest.param(row(MID_JULY, 1, 1, "-5", major="-0.1", minor="-0.2"), "negative", id="negative-axis"),
    pytest.param(row(MID_JULY, 1, 1, "-5", chi="-0.1"), "chi_square is negative", id="negative-chi"),
    pytest.param(row(MID_JULY, 1, 1, "-5", rise="-1"), "rise_time is negative", id="negative-rise"),
    pytest.param(row(MID_JULY, 1, 1, "-5", ptz="-1"), "ptz_time is negative", id="negative-ptz"),
    pytest.param(row(MID_JULY, 1, 1, "-5", status="40000"), "stroke_status is above", id="status"),
    pytest.param(row(MID_JULY, 1, 1, "-5", latitude="91"), "latitude out of range", id="latitude"),
    pytest.param(row(MID_JULY, 1, 1, "-5", longitude="-181"), "longitude out of range", id="longitude"),
    pytest.param(row(1688169599, 1, 1, "-5"), "outside the file's month", id="june-in-july"),
    pytest.param(row(1690848000, 1, 1, "-5"), "outside the file's month", id="first-of-august"),
    pytest.param(row(MID_JULY, 1, 1, "-5") + ",extra", "20 columns", id="extra-column"),
])
def test_a_row_that_cannot_be_stored_says_why(line, reason):
    with pytest.raises(readers.RowError, match=reason):
        parse(line)


# --------------------------------------------------------------------------
# A month
# --------------------------------------------------------------------------

def test_a_month_is_read_with_its_sidecar(tmp_path):
    content = readers.read_month(july_2023(tmp_path))
    assert (content.year, content.month, content.label) == (2023, 7, "2023-07")
    assert len(content.records) == content.rows == len(ROWS_2023_07)
    assert content.problems == []
    assert content.sidecar == {"month": "2023-07", "complete": True, "strokes": len(ROWS_2023_07)}


def test_a_month_without_a_sidecar_is_read(tmp_path):
    assert readers.read_month(july_2023(tmp_path, sidecar=False)).sidecar is None


def test_a_sidecar_that_is_not_json_stops_the_read(tmp_path):
    path = july_2023(tmp_path)
    readers.sidecar_path(path).write_text("{not json")
    with pytest.raises(RuntimeError, match="not readable JSON"):
        readers.read_month(path)


def test_a_bad_row_is_kept_as_a_problem_with_its_line(tmp_path):
    path = write_month(tmp_path, 2023, 7, [row(MID_JULY, 1, 1, "-5"), row(MID_JULY, 2, 1, "NaN")])
    content = readers.read_month(path)
    assert len(content.records) == 1
    assert content.problems == [(3, "peak_current is NaN")]
    assert content.rows == 2


def test_the_records_come_in_content_order_whatever_the_file_order(tmp_path):
    """The service returns a second's strokes in no stable order; the reader does not."""
    expected = readers.read_month(july_2023(tmp_path))
    shuffled = list(ROWS_2023_07)
    random.Random(7).shuffle(shuffled)
    again = readers.read_month(write_month(tmp_path, 2023, 7, shuffled))

    def values(content):
        return [(r.ordinal, readers.content_key(r)) for r in content.records]

    assert values(again) == values(expected)
    assert [r.ordinal for r in expected.records] == list(range(1, len(ROWS_2023_07) + 1))


def test_a_flashs_first_stroke_comes_first_within_its_second(tmp_path):
    content = readers.read_month(july_2023(tmp_path))
    pair = [r for r in content.records if r.flash_id == 30700002]
    assert [(r.published_multiplicity, r.peak_current) for r in pair] == [(2, -35.0), (0, -11.0)]
    four = [r.published_multiplicity for r in content.records if r.flash_id == 30645787]
    assert four[0] == 4 and four[1:] == [0, 0, 0]


def test_the_sidecar_is_read_as_json(tmp_path):
    path = july_2023(tmp_path, sidecar={"month": "2023-07", "complete": False, "strokes": 3})
    assert readers.read_month(path).sidecar == {"month": "2023-07", "complete": False,
                                                "strokes": 3}
    assert json.loads(readers.sidecar_path(path).read_text())["strokes"] == 3


def test_reading_a_file_that_is_not_a_monthly_file_is_refused(tmp_path):
    path = tmp_path / "fmi_lightning_2023-07.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("a,b\n1,2\n")
    with pytest.raises(RuntimeError, match="unexpected header"):
        readers.read_month(path)
