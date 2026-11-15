#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the reader of the Alaska network's yearly release.

No database. What matters: that a release is checked whole before a row is
converted (header, the metadata's point count, each year in one piece); that the
converted values are those the model expects (the millisecond kept, kiloamperes,
metres, NULL where the release leaves a value unknown); that every row a CHECK
would refuse is refused here, with its reason; that a year's records come out in
an order of their own, the same whatever order the file holds them in, without the
strokes published twice; and that they are grouped into flashes.
"""

import datetime
import random
import zipfile

import pytest

from src.apps.imports.lightnings.alaska_uswfs import readers

from .conftest import DATA_MEMBER
from .conftest import HEADER
from .conftest import REAL_ROWS
from .conftest import SAMPLE_YEARS
from .conftest import row
from .conftest import write_release
from .conftest import write_text

UTC = datetime.timezone.utc


def parse(line: str):
    return readers.parse_row(line.split(","), 2)


def real(prefix: str, milliseconds: int | None = None) -> str:
    """The real row starting with ``prefix`` (its type, network and UTC time), and with
    those ``milliseconds`` when several share the second."""
    matches = [line for line in REAL_ROWS if line.startswith(prefix)
               and (milliseconds is None or line.split(",")[4] == str(milliseconds))]
    assert len(matches) == 1, prefix
    return matches[0]


def years_of(path, years=None) -> dict:
    release = readers.scan(path)
    return {content.year: content for content in readers.read_years(release, years)}


# --------------------------------------------------------------------------
# Scanning a release
# --------------------------------------------------------------------------

def test_the_release_is_scanned_whole(tmp_path):
    release = readers.scan(write_release(tmp_path))
    assert (release.member, release.point_count, release.rows) == (DATA_MEMBER, 42, 42)
    assert release.years == {2012: 24, 2014: 3, 2019: 3, 2025: 9, 2026: 3}
    assert release.name == f"Historical_Lightning_2012_forward_as_txt.zip:{DATA_MEMBER}"


def test_the_extracted_text_can_be_scanned_without_a_count(tmp_path):
    release = readers.scan(write_text(tmp_path))
    assert (release.member, release.point_count, release.rows) == (None, None, 42)
    assert release.name == DATA_MEMBER


def test_a_release_without_metadata_has_no_count(tmp_path):
    assert readers.scan(write_release(tmp_path, points=False)).point_count is None


def test_metadata_without_a_point_count_has_no_count(tmp_path):
    path = tmp_path / "release.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(DATA_MEMBER, ("﻿" + HEADER + "\n" + REAL_ROWS[0] + "\n").encode())
        archive.writestr("X_FGDC_metadata.xml", "<metadata></metadata>")
    assert readers.scan(path).point_count is None


def test_a_count_that_disagrees_with_the_metadata_refuses_the_release(tmp_path):
    with pytest.raises(RuntimeError, match="holds 42 row.* declares 43 point.*incomplete or altered"):
        readers.scan(write_release(tmp_path, points=43))


def test_an_unexpected_header_refuses_the_release(tmp_path):
    with pytest.raises(RuntimeError, match="unexpected header"):
        readers.scan(write_release(tmp_path, header=HEADER.replace("GDOP", "DOP")))


def test_a_zip_without_the_strokes_refuses_the_release(tmp_path):
    with pytest.raises(RuntimeError, match="holds 0 file.*_TOA_WGS84.txt"):
        readers.scan(write_release(tmp_path, data_member="strokes.csv"))


def test_a_year_split_in_two_refuses_the_release(tmp_path):
    rows = [row("7/1/2025 10:00:00"), row("1/2/2026 10:00:00"), row("7/2/2025 10:00:00")]
    with pytest.raises(RuntimeError, match="rows of 2025 are not together .line 4 goes back"):
        readers.scan(write_release(tmp_path, rows))


def test_an_unreadable_file_refuses_the_release(tmp_path):
    path = tmp_path / "strokes.txt"
    path.write_bytes(b"\xff\xfe\x00garbage")
    with pytest.raises(RuntimeError, match="not readable|unexpected header"):
        readers.scan(path)


def test_an_empty_release_has_no_years(tmp_path):
    release = readers.scan(write_release(tmp_path, []))
    assert (release.rows, release.years) == (0, {})


# --------------------------------------------------------------------------
# A row
# --------------------------------------------------------------------------

def test_a_real_ground_stroke_is_converted():
    """2025-07-01 22:42:58.009, the first of a three-stroke flash."""
    record = parse(real("GROUND_STROKE,0,7/1/2025 22:42:58", 9))
    assert record.date_time == datetime.datetime(2025, 7, 1, 22, 42, 58, 9000, tzinfo=UTC)
    assert (record.latitude, record.longitude) == (65.3145394, -141.6709543)
    assert (record.peak_current, record.cloud_to_ground) == (-17.1, True)
    assert (record.network_code, record.sequence_number, record.gdop) == (0, 53586, 3)
    assert (record.ellipse_semi_major_axis, record.ellipse_semi_minor_axis) == (3000.0, 1000.0)
    assert record.ellipse_angle == 72.0
    assert record.polarity_contradicted is False


def test_the_millisecond_is_the_fraction_of_the_second():
    assert parse(row("7/1/2025 22:42:58", 999)).date_time.microsecond == 999_000


def test_a_cloud_stroke_has_no_peak_current():
    record = parse(real("CLOUD_STROKE,0,7/1/2025 2:55:05"))
    assert (record.peak_current, record.cloud_to_ground) == (None, False)


def test_a_semi_major_axis_of_0_is_unknown():
    record = parse(real("GROUND_STROKE,0,4/26/2014 3:29:59"))
    assert (record.ellipse_semi_major_axis, record.ellipse_semi_minor_axis) == (None, 1000.0)


def test_a_missing_sequence_number_is_none():
    assert parse(real("GROUND_STROKE,0,3/7/2012 7:43:29")).sequence_number is None


def test_a_stroke_east_of_180_keeps_its_longitude():
    assert parse(real("GROUND_STROKE,0,3/8/2012 12:33:52")).longitude == 172.2168772


def test_the_saturated_values_are_kept():
    assert parse(real("GROUND_STROKE,0,5/9/2012 8:57:01")).peak_current == 500.0
    assert parse(real("GROUND_STROKE,0,5/9/2012 9:32:27")).peak_current == -500.0
    ceiling = parse(real("GROUND_STROKE,0,3/28/2012 20:31:41"))
    assert (ceiling.gdop, ceiling.ellipse_semi_major_axis, ceiling.ellipse_semi_minor_axis) == \
        (255, 255000.0, 9000.0)


@pytest.mark.parametrize(("line", "contradicted"), [
    pytest.param(real("GROUND_STROKE,0,6/6/2019 22:16:10"), True, id="positive-on-negative"),
    pytest.param(real("GROUND_STROKE,0,1/1/2019 14:35:44"), False, id="missing"),
    pytest.param(real("GROUND_STROKE,0,5/9/2012 8:57:01"), False, id="positive"),
    pytest.param(real("CLOUD_STROKE,0,7/1/2025 2:55:05"), False, id="cloud"),
    pytest.param(row("7/1/2025 10:00:00", cloud=True, polarity="Negative"), True,
                 id="negative-on-cloud"),
])
def test_a_polarity_contradicting_the_amplitude_is_flagged(line, contradicted):
    assert parse(line).polarity_contradicted is contradicted


def test_the_local_time_and_strike_time_are_not_read():
    values = row("7/1/2025 10:00:00").split(",")
    values[3], values[12] = "garbage", "garbage"
    assert readers.parse_row(values, 2).date_time.hour == 10


@pytest.mark.parametrize(("line", "reason"), [
    pytest.param(row("7/1/2025 10:00:00") + ",extra", "16 columns instead of 15", id="columns"),
    pytest.param(row("7/1/2025 10:00:00").replace("GROUND_STROKE", "IC_PULSE"),
                 "STROKETYPE is unknown", id="stroke-type"),
    pytest.param(row("7/1/2025 10:00:00", 1000), "MILLISECONDS is above 999", id="ms-1000"),
    pytest.param(row("7/1/2025 10:00:00").replace(",0,64.8", ",0.5,64.8"),
                 "MILLISECONDS is not an integer", id="ms-fraction"),
    pytest.param(row("13/1/2025 10:00:00"), "UTCDATETIME is not a date", id="month-13"),
    pytest.param(row("7/1/2025"), "UTCDATETIME is not a date", id="no-time"),
    pytest.param(row("7/1/2025 10:00:00", latitude="91"), "LATITUDE out of range", id="latitude"),
    pytest.param(row("7/1/2025 10:00:00", longitude="-181"), "LONGITUDE out of range",
                 id="longitude"),
    pytest.param(row("7/1/2025 10:00:00", amplitude="abc"), "AMPLITUDE is not a number",
                 id="amplitude-text"),
    pytest.param(row("7/1/2025 10:00:00", amplitude="nan"), "AMPLITUDE is nan", id="amplitude-nan"),
    pytest.param(row("7/1/2025 10:00:00", amplitude="0.000000000000000"),
                 "AMPLITUDE is 0 on a GROUND_STROKE", id="ground-without-amplitude"),
    pytest.param(row("7/1/2025 10:00:00", cloud=True).replace(",0.000000000000000,", ",5000,"),
                 "AMPLITUDE is 5000.0 on a CLOUD_STROKE", id="cloud-with-amplitude"),
    pytest.param(row("7/1/2025 10:00:00", semi_minor="0"), "ERRSEMIMINOR is not positive",
                 id="semi-minor-0"),
    pytest.param(row("7/1/2025 10:00:00", semi_major="-1"), "ERRSEMIMAJOR is negative",
                 id="semi-major-negative"),
    pytest.param(row("7/1/2025 10:00:00", semi_major="1", semi_minor="2"),
                 "ERRSEMIMINOR 2.0 is larger than ERRSEMIMAJOR 1.0", id="minor-past-major"),
    pytest.param(row("7/1/2025 10:00:00", angle="91"), "ERRELIPSEANGLE is outside -90 to 90",
                 id="angle"),
    pytest.param(row("7/1/2025 10:00:00", gdop="0"), "GDOP is below 1", id="gdop-0"),
    pytest.param(row("7/1/2025 10:00:00", gdop="1.5"), "GDOP is not an integer", id="gdop-fraction"),
    pytest.param(row("7/1/2025 10:00:00", gdop="40000"), "GDOP is above 32767", id="gdop-smallint"),
    pytest.param(row("7/1/2025 10:00:00", network="-1"), "NETWORKCODE is below 0", id="network"),
    pytest.param(row("7/1/2025 10:00:00", sequence="-1"), "STRIKESEQNUMBER is below 0",
                 id="sequence-negative"),
    pytest.param(row("7/1/2025 10:00:00", sequence="x"), "STRIKESEQNUMBER is not a number",
                 id="sequence-text"),
])
def test_a_row_the_model_would_refuse_is_refused_with_its_reason(line, reason):
    with pytest.raises(readers.RowError, match=reason):
        parse(line)


def test_the_edges_seen_in_the_release_are_read():
    for line in (row("7/1/2025 10:00:00", angle="-90"), row("7/1/2025 10:00:00", angle="90"),
                 row("7/1/2025 10:00:00", sequence="0"), row("7/1/2025 10:00:00", sequence="65535"),
                 row("7/1/2025 10:00:00", semi_major="1", semi_minor="1")):
        parse(line)


# --------------------------------------------------------------------------
# Years
# --------------------------------------------------------------------------

def test_the_years_come_one_at_a_time_in_file_order(tmp_path):
    years = years_of(write_release(tmp_path))
    assert list(years) == [2012, 2014, 2019, 2025, 2026]
    assert {year: len(content.records) for year, content in years.items()} == \
        {2012: 24, 2014: 3, 2019: 3, 2025: 9, 2026: 3}
    assert all(not content.problems for content in years.values())


def test_only_the_years_asked_for_are_read(tmp_path):
    assert list(years_of(write_release(tmp_path), {2014, 2026})) == [2014, 2026]


def test_a_refused_row_is_kept_with_its_year_and_line(tmp_path):
    rows = [row("7/1/2025 10:00:00"), row("7/1/2025 11:00:00", latitude="95"),
            row("7/1/2025 12:00:00")]
    content = years_of(write_release(tmp_path, rows))[2025]
    assert len(content.records) == 2
    assert content.problems == [(3, "LATITUDE out of range: 95.0")]


def test_a_refused_row_without_a_year_goes_with_the_year_being_read(tmp_path):
    rows = [row("7/1/2025 10:00:00"), row("not a date"), row("7/1/2025 12:00:00")]
    content = years_of(write_release(tmp_path, rows))[2025]
    assert content.problems == [(3, "UTCDATETIME is not a date: 'not a date'")]


def test_a_refused_row_before_any_year_goes_with_the_first(tmp_path):
    rows = [row("garbage"), row("7/1/2025 12:00:00")]
    assert years_of(write_release(tmp_path, rows))[2025].problems == [
        (2, "UTCDATETIME is not a date: 'garbage'")]


def test_a_year_is_a_half_open_range():
    content = readers.ReleaseYear(2025)
    assert (content.start, content.end) == (datetime.datetime(2025, 1, 1, tzinfo=UTC),
                                            datetime.datetime(2026, 1, 1, tzinfo=UTC))


# --------------------------------------------------------------------------
# Order, duplicates and flashes
# --------------------------------------------------------------------------

def prepared(path, year):
    return readers.prepare_year(years_of(path, {year})[year])


def test_the_sample_years_come_to_their_strokes_and_flashes(tmp_path):
    years = years_of(write_release(tmp_path))
    found = {}
    for year, content in years.items():
        readers.prepare_year(content)
        found[year] = (len(content.records), content.flashes - content.cloud_flashes,
                       content.cloud_flashes)
    assert found == SAMPLE_YEARS


def test_strokes_published_twice_are_kept_once_with_the_lower_sequence_number(tmp_path):
    content = prepared(write_release(tmp_path), 2012)
    assert content.duplicates == 4
    same_day = [record for record in content.records
                if record.date_time.date() == datetime.date(2012, 6, 15)]
    assert [record.sequence_number for record in same_day] == [18547, 18548, 18576, 18577]


def test_the_records_are_numbered_in_content_order(tmp_path):
    content = prepared(write_release(tmp_path), 2025)
    assert [record.ordinal for record in content.records] == list(range(1, 10))
    times = [record.date_time for record in content.records]
    assert times == sorted(times)
    # The cloud and the ground stroke of one millisecond: the cloud one first.
    assert [record.cloud_to_ground for record in content.records[:2]] == [False, True]


def test_the_content_order_does_not_depend_on_the_files(tmp_path):
    """Shuffled within each year, the release gives the same records in the same order."""
    original = prepared(write_release(tmp_path), 2012)
    rows = REAL_ROWS[:24]
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    again = prepared(write_release(tmp_path, shuffled + REAL_ROWS[24:], name="shuffled.zip"), 2012)
    assert [readers.content_key(record) for record in again.records] == \
        [readers.content_key(record) for record in original.records]
    assert [(record.first_ordinal, record.multiplicity, record.stroke_index)
            for record in again.records] == \
        [(record.first_ordinal, record.multiplicity, record.stroke_index)
         for record in original.records]


def test_the_strokes_are_grouped_into_flashes(tmp_path):
    """2025: the two three-stroke flashes of 07-01, and a cloud and a ground stroke of
    one millisecond that stay apart."""
    content = prepared(write_release(tmp_path), 2025)
    flashes = [(record.date_time.strftime("%m-%d %H:%M:%S.%f")[:-3], record.cloud_to_ground,
                record.first_ordinal, record.multiplicity, record.stroke_index)
               for record in content.records]
    assert flashes == [
        ("05-24 21:27:57.335", False, 1, 1, 1),
        ("05-24 21:27:57.335", True, 2, 1, 1),
        ("07-01 02:55:05.955", False, 3, 1, 1),
        ("07-01 22:42:58.009", True, 4, 3, 1),
        ("07-01 22:42:58.018", True, 4, 3, 2),
        ("07-01 22:42:58.262", True, 4, 3, 3),
        ("07-01 23:02:48.164", True, 7, 3, 1),
        ("07-01 23:02:48.169", True, 7, 3, 2),
        ("07-01 23:02:48.175", True, 7, 3, 3),
    ]
    assert (content.flashes, content.cloud_flashes) == (5, 2)


def test_the_unknowns_and_contradictions_are_counted(tmp_path):
    assert prepared(write_release(tmp_path), 2014).unknown_semi_major == 3
    assert prepared(write_release(tmp_path), 2019).polarity_contradictions == 2


def test_strokes_near_new_year_are_counted(tmp_path):
    rows = [row("1/1/2025 0:00:00", 500), row("6/1/2025 0:00:00"),
            row("12/31/2025 23:59:59", 100)]
    assert prepared(write_release(tmp_path, rows), 2025).near_new_year == 2


def test_an_empty_year_is_prepared_as_none(tmp_path):
    content = readers.prepare_year(readers.ReleaseYear(2025))
    assert (content.records, content.flashes) == ([], 0)
