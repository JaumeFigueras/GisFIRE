#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Greek Fire Service workbook reader.

What is being tested is the part of this source that is easy to get wrong and
impossible to notice: that a field is found by *name* in six different column
arrangements, that the header is found wherever it happens to be, that a year is
established for a sheet that does not name itself after one, and that the two
forms of every date and time — Excel value and text — read the same.
"""

import datetime

import pytest

from src.apps.imports.wildfires.greece_ffa import readers
from src.providers import greece_ffa

from .conftest import HEADER_2000
from .conftest import HEADER_2012
from .conftest import HEADER_2022
from .conftest import HEADER_2025
from .conftest import PREAMBLE_2025
from .conftest import a_2005_fire
from .conftest import a_2022_fire
from .conftest import a_2025_fire
from .conftest import fire
from .conftest import write_workbook


def read(path):
    """Every sheet of a workbook, with its records realised."""
    return [(sheet, list(sheet.records)) for sheet in readers.read_workbook(path)]


# --------------------------------------------------------------------------
# Finding the header, and the year
# --------------------------------------------------------------------------

def test_the_header_is_found_under_its_banner(tmp_path):
    """Row 2 for twenty-four of the twenty-six published sheets."""
    path = write_workbook(tmp_path / "y.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire()])})
    (sheet, records), = read(path)

    assert sheet.header_row == 2
    assert sheet.year == 2022
    assert len(records) == 1


def test_the_header_is_found_on_row_one_when_there_is_no_banner(tmp_path):
    """Which is what the 2014 sheet does, alone among the twenty-six."""
    path = write_workbook(tmp_path / "y.xlsx",
                          {"2014": (HEADER_2012, [])}, banner=False)
    (sheet, _), = read(path)

    assert sheet.header_row == 1
    assert sheet.year == 2014


def test_the_header_is_found_under_a_title_and_a_year(tmp_path):
    """The 2025 file puts two more rows above the banner, so the header is row 4."""
    path = write_workbook(tmp_path / "y.xlsx",
                          {"Sheet0": (HEADER_2025, [a_2025_fire()])},
                          preamble={"Sheet0": PREAMBLE_2025})
    (sheet, records), = read(path)

    assert sheet.header_row == 4
    assert len(records) == 1


def test_a_sheet_that_does_not_name_a_year_takes_it_from_above_the_header(tmp_path):
    """``Sheet0`` plus ``Για το ΕΤΟΣ: 2025`` is the whole of the 2025 file's claim."""
    path = write_workbook(tmp_path / "y.xlsx",
                          {"Sheet0": (HEADER_2025, [a_2025_fire()])},
                          preamble={"Sheet0": PREAMBLE_2025})
    (sheet, _), = read(path)

    assert sheet.year == 2025
    assert sheet.name == "Sheet0", "the sheet name is still what gets stored"


def test_a_sheet_with_a_header_and_no_year_is_refused(tmp_path):
    """Refused and not guessed: the year is what an import deletes.

    Guessing it wrong would delete a year of good data and replace it with
    another's, which is the one failure this import must not have.
    """
    path = write_workbook(tmp_path / "y.xlsx",
                          {"Sheet0": (HEADER_2025, [a_2025_fire()])})

    with pytest.raises(RuntimeError, match="no year"):
        read(path)


def test_the_helper_sheets_are_not_read(tmp_path):
    """``engage``/``engagexy`` hold the coordinates the 2022-2024 formulas look up.

    Their values are already cached in the main sheet, so reading them would import
    every coordinate a second time as a fire of its own.
    """
    path = write_workbook(tmp_path / "y.xlsx", {
        "2022": (HEADER_2022, [a_2022_fire()]),
        "engagexy": (("ΗΜΕΡOMHNIA", "INCIDENT_UID", "LONGITUDE", "LATITUDE"), []),
    })
    sheets = read(path)

    assert [sheet.name for sheet, _ in sheets] == ["2022"]


def test_a_sheet_with_no_recognisable_header_is_skipped(tmp_path):
    """The 2023 file ships a one-cell ``SQL Statement`` tab, and others may too."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2022": (HEADER_2022, [a_2022_fire()]),
        "Notes": (("published", "by"), [["2023-01-01", "PS"]]),
    })
    sheets = read(path)

    assert [sheet.year for sheet, _ in sheets] == [2022]


def test_every_year_of_a_multi_year_workbook_is_its_own_sheet(tmp_path):
    """The 2000-2012 file is thirteen years in one workbook, and thirteen units."""
    path = write_workbook(tmp_path / "many.xlsx", {
        "2000": (HEADER_2000, [a_2005_fire()]),
        "2001": (HEADER_2000, [a_2005_fire(), a_2005_fire()]),
        "2012": (HEADER_2012, []),
    })
    sheets = read(path)

    assert [sheet.year for sheet, _ in sheets] == [2000, 2001, 2012]
    assert [len(records) for _, records in sheets] == [1, 2, 0]


# --------------------------------------------------------------------------
# Finding the columns
# --------------------------------------------------------------------------

def test_a_column_is_found_by_name_in_every_arrangement(tmp_path):
    """The prefecture is column 3 in 2000, column 1 in 2012 and column 5 in 2022.

    Nothing is read by position, which is the whole reason this reader exists.
    """
    path = write_workbook(tmp_path / "y.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire()]),
        "2012": (HEADER_2012, [fire(HEADER_2012, **{
            "Νομός": "ΑΤΤΙΚΗΣ",
            "Ημερ/νία Έναρξης": datetime.datetime(2012, 6, 4),
            "Ώρα Έναρξης": "07:23"})]),
        "2022": (HEADER_2022, [a_2022_fire()]),
    })
    for _, records in read(path):
        assert records[0].prefecture_name == "ΑΤΤΙΚΗΣ"


def test_the_hyphenated_and_plain_spellings_are_one_column(tmp_path):
    """``ΒΥΤΙΟ- ΦΟΡΑ`` (2011-2024) and ``ΒΥΤΙΟΦΟΡΑ`` (2025) are the same field."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2022": (HEADER_2022, [a_2022_fire(**{"ΒΥΤΙΟ- ΦΟΡΑ": 7})]),
        "Sheet0": (HEADER_2025, [a_2025_fire(**{"ΒΥΤΙΟΦΟΡΑ": 7})]),
    }, preamble={"Sheet0": PREAMBLE_2025})

    for _, records in read(path):
        assert records[0].vehicles_water_tankers == 7


def test_the_latin_and_greek_engage_headers_are_one_column(tmp_path):
    """The 2025 file writes ``A/A ENGAGE`` with a Latin A; every other year does not.

    They render identically, so a reader matching on ``==`` would import 2025 with
    an empty column and no error at all.
    """
    path = write_workbook(tmp_path / "y.xlsx", {
        "2022": (HEADER_2022, [a_2022_fire(**{"Α/Α ENGAGE": 4242})]),
        "Sheet0": (HEADER_2025, [a_2025_fire(**{"A/A ENGAGE": 4242})]),
    }, preamble={"Sheet0": PREAMBLE_2025})

    for _, records in read(path):
        assert records[0].engage_id == 4242


def test_the_renamed_vehicle_column_lands_in_one_field(tmp_path):
    """``ΟΧΗΜ. ΟΤΑ`` became ``ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ`` in 2022: one slot, renamed."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2012": (HEADER_2012, [fire(HEADER_2012, **{
            "Ημερ/νία Έναρξης": datetime.datetime(2012, 6, 4), "Ώρα Έναρξης": "07:23",
            "ΟΧΗΜ. ΟΤΑ": 5})]),
        "2022": (HEADER_2022, [a_2022_fire(**{"ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ": 5})]),
    })

    for _, records in read(path):
        assert records[0].vehicles_public_service == 5


def test_the_split_locality_column_lands_in_one_field(tmp_path):
    """``Περιοχή - Τοποθεσία`` (to 2011) is what ``Περιοχή`` (from 2012) continues."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire(**{"Περιοχή - Τοποθεσία": "ΚΑΛΑΜΟΣ"})]),
        "2022": (HEADER_2022, [a_2022_fire(**{"Περιοχή": "ΚΑΛΑΜΟΣ"})]),
    })

    for _, records in read(path):
        assert records[0].locality_name == "ΚΑΛΑΜΟΣ"


def test_a_column_a_year_does_not_publish_stays_none(tmp_path):
    """Not zero. 2000-2010 publish no deployment block, which is not "nothing came"."""
    path = write_workbook(tmp_path / "y.xlsx", {"2005": (HEADER_2000, [a_2005_fire()])})
    (_, records), = read(path)

    assert records[0].personnel_fire_service is None
    assert records[0].aircraft_cl415 is None
    assert records[0].municipality_name is None, "Δήμος is not published before 2009"
    assert records[0].record_number is None, "nothing identifies a fire before 2020"


def test_an_unknown_column_is_reported_and_not_stored(tmp_path):
    """A new column is a reason to look, not a reason to refuse a year."""
    header = HEADER_2022 + ("ΚΑΤΙ ΚΑΙΝΟΥΡΓΙΟ",)
    path = write_workbook(tmp_path / "y.xlsx",
                          {"2026": (header, [fire(header, **{
                              "Ημερ/νία Έναρξης": datetime.datetime(2026, 7, 1),
                              "Ώρα Έναρξης": "10:00",
                              "ΚΑΤΙ ΚΑΙΝΟΥΡΓΙΟ": "x"})])})
    (sheet, records), = read(path)

    assert sheet.unknown_columns == ["ΚΑΤΙ ΚΑΙΝΟΥΡΓΙΟ"]
    assert len(records) == 1, "the year is still read"


# --------------------------------------------------------------------------
# Dates and times
# --------------------------------------------------------------------------

def test_an_excel_date_and_a_text_date_read_the_same(tmp_path):
    """2000-2024 store a real datetime; 2025 stores ``dd/mm/yyyy`` text."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2022": (HEADER_2022, [a_2022_fire(**{
            "Ημερ/νία Έναρξης": datetime.datetime(2022, 3, 12), "Ώρα Έναρξης": "11:23"})]),
        "Sheet0": (HEADER_2025, [a_2025_fire(**{
            "Ημερ/νία Έναρξης": "12/03/2025", "Ώρα Έναρξης": "11:23"})]),
    }, preamble={"Sheet0": PREAMBLE_2025})
    sheets = read(path)

    assert sheets[0][1][0].start_date == datetime.date(2022, 3, 12)
    assert sheets[1][1][0].start_date == datetime.date(2025, 3, 12)
    assert all(records[0].start_time == datetime.time(11, 23) for _, records in sheets)


def test_a_time_object_and_a_text_time_read_the_same(tmp_path):
    """2000-2006 and 2008-2010 store a ``datetime.time``; the rest store ``HH:MM``."""
    path = write_workbook(tmp_path / "y.xlsx", {
        "2005": (HEADER_2000, [a_2005_fire(**{"Ώρα Έναρξης": datetime.time(13, 30)})]),
        "2022": (HEADER_2022, [a_2022_fire(**{"Ώρα Έναρξης": "13:30"})]),
    })

    for _, records in read(path):
        assert records[0].start_time == datetime.time(13, 30)


def test_the_start_is_one_naive_local_reading(tmp_path):
    """The date and the time are published apart and mean one wall-clock instant."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire()])})
    (_, records), = read(path)

    assert records[0].start_datetime == datetime.datetime(2022, 6, 14, 13, 24)
    assert records[0].start_datetime.tzinfo is None, "the zone is the importer's job"


def test_a_missing_extinction_is_none_and_not_a_guess(tmp_path):
    """26,597 rows publish neither an end date nor an end time."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Ημερ/νία Κατασβεσης": None, "Ώρα Κατάσβεσης": None})])})
    (_, records), = read(path)

    assert records[0].end_datetime is None


def test_an_extinction_time_with_no_date_is_not_an_instant(tmp_path):
    """586 rows publish one. A time alone cannot name a moment, so the end is null."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Ημερ/νία Κατασβεσης": None, "Ώρα Κατάσβεσης": "20:59"})])})
    (_, records), = read(path)

    assert records[0].end_time == datetime.time(20, 59)
    assert records[0].end_datetime is None


def test_an_extinction_date_with_no_time_is_local_midnight(tmp_path):
    """641 rows publish one, and the project's rule for a bare date is midnight."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Ημερ/νία Κατασβεσης": datetime.datetime(2022, 6, 16),
        "Ώρα Κατάσβεσης": None})])})
    (_, records), = read(path)

    assert records[0].end_datetime == datetime.datetime(2022, 6, 16, 0, 0)


def test_a_published_24_00_is_midnight(tmp_path):
    """``datetime.time`` refuses hour 24, and the service means the end of the day."""
    assert readers.to_time("24:00") == datetime.time(0, 0)


def test_an_unparseable_date_is_reported_rather_than_raised(tmp_path):
    """The reader says what the file holds; the importer decides what to do."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Ημερ/νία Έναρξης": "the fourteenth"})])})
    (_, records), = read(path)

    assert records[0].start_date is None
    assert records[0].problems and "not a date" in records[0].problems[0]


# --------------------------------------------------------------------------
# Coordinates, identifiers and areas
# --------------------------------------------------------------------------

def test_a_published_coordinate_is_read_as_degrees(tmp_path):
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire()])})
    (_, records), = read(path)

    assert (records[0].longitude, records[0].latitude) == (23.86, 38.28)
    assert records[0].located


def test_a_zero_pair_is_not_a_location(tmp_path):
    """3,755 rows of 2020-2025 carry it, and null island is in the Gulf of Guinea."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "X-ENGAGE": 0, "Y-ENGAGE": 0})])})
    (_, records), = read(path)

    assert not records[0].located


def test_a_zero_identifier_is_no_identifier(tmp_path):
    """``Α/Α ENGAGE`` of 0 means the dispatch system has no incident for this row.

    Stored as a literal zero it would make thousands of unrelated fires share one.
    """
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Α/Α ENGAGE": 0})])})
    (_, records), = read(path)

    assert records[0].engage_id is None


def test_a_zero_count_is_a_count(tmp_path):
    """Unlike an identifier: no aircraft flew to this fire is an answer."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire()])})
    (_, records), = read(path)

    assert records[0].aircraft_cl415 == 0
    assert records[0].personnel_army == 0


def test_areas_are_read_as_published_in_stremmata(tmp_path):
    """The reader does not convert. The record still says what the file said."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire()])})
    (_, records), = read(path)

    assert records[0].area_agricultural == 17.0
    assert records[0].area_crop_residue == pytest.approx(0.9)


def test_a_comma_decimal_is_read_as_a_decimal():
    """Greek locale writes 0,9 — and a single re-typed cell should not lose a year."""
    assert readers.to_number("0,9") == pytest.approx(0.9)
    assert readers.to_number("  ") is None
    assert readers.to_number("not a number") is None


def test_whitespace_only_text_is_nothing(tmp_path):
    """``Δασαρχείο`` is blank on most rows and is sometimes a run of spaces."""
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [a_2022_fire(**{
        "Δασαρχείο": "   "})])})
    (_, records), = read(path)

    assert records[0].forest_district_name is None
    assert records[0].address == "ΘΕΣΗ ΧΙΛΙΟΠΟΤΑΜΟΣ", "real text is kept, stripped"


def test_a_wholly_empty_row_is_not_a_record(tmp_path):
    path = write_workbook(tmp_path / "y.xlsx", {"2022": (HEADER_2022, [
        a_2022_fire(), [None] * len(HEADER_2022), a_2022_fire()])})
    (_, records), = read(path)

    assert len(records) == 2


def test_the_row_number_is_the_worksheet_row(tmp_path):
    """For 201,948 rows it is the only way to say which one was refused."""
    path = write_workbook(tmp_path / "y.xlsx",
                          {"2022": (HEADER_2022, [a_2022_fire(), a_2022_fire()])})
    (sheet, records), = read(path)

    assert sheet.header_row == 2
    assert [record.row for record in records] == [3, 4]


def test_an_unreadable_file_is_refused_by_name(tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"this is not a zip archive")

    with pytest.raises(RuntimeError, match="broken.xlsx is not a readable"):
        read(path)


def test_the_reader_agrees_with_the_provider_on_what_is_located():
    """One rule, in one place: the reader does not have its own bounds test."""
    assert readers.FireRecord(row=1, longitude=23.86, latitude=38.28).located
    assert greece_ffa.is_located(23.86, 38.28)
    assert not readers.FireRecord(row=1, longitude=0.0, latitude=0.0).located
