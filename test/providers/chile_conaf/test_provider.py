#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF provider helpers (Chile).

These functions are where the archive's dirt is dealt with, and every one of them
exists because the published files really are like this. What is pinned here is the
behaviour each was written for:

* the fire season is 1 July to 30 June, and a season is two *consecutive* years;
* four published date formats are read and each reports how much of it was real;
* the published UTM triple is read out of ``'317709 E'``, ``'19K'`` and ``'12.0'``,
  and a zeroed pair is *unpublished* rather than a coordinate;
* administrative codes are zero-padded, including out of ``'6.00000000000'``;
* the fold removes the soft hyphens two seasons are littered with, and does not
  invent repairs for the rest of the mojibake;
* a record whose text fields are binary is recognised.

No database: these are pure functions, and the point of having them as functions is
that they can be tested without one.
"""

import datetime

import pytest

from src.providers import chile_conaf


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published, expected", [
    ("2010-2011", 2010),
    ("2024-2025", 2024),
    (" 2016-2017 ", 2016),
    ("2016/2017", 2016),
])
def test_a_season_is_two_consecutive_years(published, expected):
    assert chile_conaf.season_start_year(published) == expected


@pytest.mark.parametrize("published", ["", None, "2023-2025", "2010", "temporada",
                                       "2011-2010", "??AJ??l???"])
def test_a_season_that_is_not_two_consecutive_years_is_refused(published):
    """``'2023-2025'`` is a typing error one perimeter really publishes.

    Reading its first half as a season would store the fire under 2023-2024 while
    hiding that the cell is wrong. Returning ``None`` makes the import fall back to
    the archive's own season *and count the fallback*, which is the difference
    between a documented repair and a silent one.
    """
    assert chile_conaf.season_start_year(published) is None


def test_the_season_window_runs_july_to_july():
    """Measured, not conventional: every dated feature of the archive falls inside.

    The end is exclusive and is 1 July of the following year, so the two windows of
    consecutive seasons abut exactly and no instant is in both or in neither.
    """
    start, end = chile_conaf.season_window(2016)
    assert start == datetime.datetime(2016, 7, 1)
    assert end == datetime.datetime(2017, 7, 1)
    assert chile_conaf.season_window(2017)[0] == end


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published, expected, precision", [
    ("18-ene-2023 15:50", datetime.datetime(2023, 1, 18, 15, 50), "minute"),
    ("5-dic-2024 13:03", datetime.datetime(2024, 12, 5, 13, 3), "minute"),
    # The doubled space one feature of if_magnitud_2022_2023 really publishes.
    ("6-abr-2023  11:51", datetime.datetime(2023, 4, 6, 11, 51), "minute"),
    ("2023/07/07", datetime.datetime(2023, 7, 7), "day"),
    ("2024-01-12", datetime.datetime(2024, 1, 12), "day"),
    # Day-month-year, which if_isla_pascua_2019_2020 publishes.
    ("08-09-2019 12:10", datetime.datetime(2019, 9, 8, 12, 10), "minute"),
])
def test_the_four_published_date_formats_are_read(published, expected, precision):
    assert chile_conaf.parse_published_datetime(published) == (expected, precision)


@pytest.mark.parametrize("published", ["", None, "   ", "not a date", "31-feb-2023 10:00",
                                       "18-xxx-2023 15:50", "2023/13/45"])
def test_an_unreadable_date_is_no_date_rather_than_a_guess(published):
    assert chile_conaf.parse_published_datetime(published) == (None, None)


def test_a_bare_date_never_claims_a_time():
    """``2023/07/07`` becomes midnight, and says it is only good to the day.

    The instant and the precision are returned together for exactly this: local
    midnight is a perfectly good instant and a completely invented time of day, and
    only the second value distinguishes it from one CONAF actually observed.
    """
    parsed, precision = chile_conaf.parse_published_datetime("2023/07/07")
    assert parsed.hour == 0 and parsed.minute == 0
    assert precision == chile_conaf.PRECISION_DAY
    assert precision != chile_conaf.PRECISION_MINUTE


def test_the_reader_never_returns_the_season_precision():
    """:data:`PRECISION_SEASON` is not a reading of a cell.

    It is what the importer records when there is *no* cell, so the reader has no
    business producing it — a cell that parsed to the first of July is still a
    published date.
    """
    parsed, precision = chile_conaf.parse_published_datetime("1-jul-2016 00:00")
    assert parsed == datetime.datetime(2016, 7, 1)
    assert precision != chile_conaf.PRECISION_SEASON


# --------------------------------------------------------------------------
# The published coordinate
# --------------------------------------------------------------------------

@pytest.mark.parametrize("easting, northing, huso, expected", [
    (537703.0, 7847784.0, "19K", (537703.0, 7847784.0, 19, "K")),
    (734013.0, 6072270.0, "18H", (734013.0, 6072270.0, 18, "H")),
    # The bare zone number the 2020-2021 and 2021-2022 layers publish.
    (693261, 5948110, "19", (693261.0, 5948110.0, 19, None)),
    # The float one Easter Island layer publishes.
    (654520, 6994384, "12.0", (654520.0, 6994384.0, 12, None)),
    # The suffixed text 2023-2024 publishes.
    ("317709 E", "6350587 S", "19H", (317709.0, 6350587.0, 19, "H")),
])
def test_the_published_utm_triple_is_read(easting, northing, huso, expected):
    assert chile_conaf.published_utm(easting, northing, huso) == expected


@pytest.mark.parametrize("easting, northing, huso", [
    # if_temporada_2013_2014 publishes (0, 0) on all 6,297 of its rows.
    (0, 0, "19"),
    (0.0, 5948110.0, "19"),
    # Eight mainland seasons publish no HUSO at all.
    (537703.0, 7847784.0, None),
    (537703.0, 7847784.0, ""),
    # A zone Chile is not in.
    (537703.0, 7847784.0, "31T"),
    (None, None, "19"),
])
def test_an_unreadable_utm_triple_is_none(easting, northing, huso):
    """A zero easting is *unpublished*, not a coordinate.

    Easting zero is 500 km west of the zone's central meridian, in the Pacific, and
    2013-2014 writes it on every row it has. Reading it as a number would put a whole
    season's provenance columns 500 km out to sea.
    """
    assert chile_conaf.published_utm(easting, northing, huso) is None


# --------------------------------------------------------------------------
# Administrative codes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published, kind, expected", [
    ("08", "region", "08"),
    ("5", "region", "05"),
    # 2024-2025 publishes its región code as a float.
    ("6.00000000000", "region", "06"),
    ("081", "province", "081"),
    ("58", "province", "058"),
    ("08111", "commune", "08111"),
    ("5801", "commune", "05801"),
    ("", "region", None),
    (None, "region", None),
    ("no", "region", None),
])
def test_administrative_codes_are_zero_padded(published, kind, expected):
    """Codes and not quantities: región 08 is Biobío, and there is no región 8.

    Padding is what keeps ``'5801'`` and ``'05801'`` one comuna rather than two, which
    matters because 2022-2023 publishes the first form and every other season the
    second.
    """
    assert chile_conaf.admin_code(published, kind) == expected


def test_a_code_longer_than_its_width_keeps_its_digits():
    """Truncating would turn a malformed code into a plausible wrong one.

    Losing the leading digits of ``'123456'`` gives ``'23456'``, which is a comuna
    somewhere. Keeping it whole makes the row visibly wrong instead.
    """
    assert chile_conaf.admin_code("123456", "commune") == "123456"


def test_an_unknown_kind_of_code_is_a_programming_error():
    with pytest.raises(KeyError):
        chile_conaf.admin_code("08", "department")


# --------------------------------------------------------------------------
# Folding
# --------------------------------------------------------------------------

def test_the_fold_removes_the_soft_hyphens_two_seasons_are_littered_with():
    """``U+00AD`` is invisible, appears 6,809 times, and would split every spelling.

    ``if_temporada_2015_2016`` and ``if_temporada_2018_2019`` write the letter and
    then a soft hyphen in the middle of otherwise intact words. Leaving it in would
    put those two seasons' fires in a category of their own in every cause series.
    """
    damaged = "Tránsito de personas, vehí\xadculos o aeronaves"
    intact = "TRANSITO DE PERSONAS, VEHICULOS O AERONAVES"
    assert chile_conaf.normalise(damaged) == chile_conaf.normalise(intact)


@pytest.mark.parametrize("published, expected", [
    ("Incendios Intencionales", "incendios intencionales"),
    ("INCENDIOS  INTENCIONALES", "incendios intencionales"),
    ("  Incendios\nintencionales ", "incendios intencionales"),
    ("Faenas agrícolas", "faenas agricolas"),
    (None, ""),
])
def test_the_fold_removes_case_accents_and_whitespace(published, expected):
    assert chile_conaf.normalise(published) == expected


def test_the_fold_does_not_repair_mojibake():
    """``'TRANSEONTES'`` folds to itself and stays apart from ``'transeuntes'``.

    Guessing which letter a bad decode lost would be a guess, and this project's rule
    is that a guess belongs in a table where it can be argued with — see
    :mod:`src.providers.chile_conaf.fire_cause` — rather than in a string function
    where it cannot be seen.
    """
    assert chile_conaf.normalise("TRANSEONTES") != chile_conaf.normalise("transeuntes")


@pytest.mark.parametrize("published", ["", "0", "N/A", "S/I", "Sin informacion",
                                       "(en blanco)", "  ", None])
def test_the_archives_many_null_tokens_are_all_missing(published):
    assert chile_conaf.is_missing(published) is True


@pytest.mark.parametrize("published", ["Conaf", "Pastizal", "2.1.11. Otros", "0.5"])
def test_a_real_value_is_not_missing(published):
    assert chile_conaf.is_missing(published) is False


# --------------------------------------------------------------------------
# Corruption
# --------------------------------------------------------------------------

def test_a_record_with_binary_in_its_text_is_corrupt():
    """Three records of ``if_temporada_2010_2011`` are like this.

    Their DBF has come apart, so nothing in them can be trusted — including the parts
    that still look readable, one of which turns up as a plausible-looking
    ``CAUSA_GENE``. Dropping them keeps three permanent entries of garbage out of the
    cause classification.
    """
    assert chile_conaf.is_corrupt("Conaf", "?2\x0bI??k\x15???\x08?y\x10?g") is True


@pytest.mark.parametrize("values", [
    ("Conaf", "TOME", "2010-2011"),
    ("Conaf", None, "Tránsito de personas"),
    ("line one\nline two", "with\ttab", "with\r\n"),
])
def test_whitespace_is_not_corruption(values):
    """Tabs, newlines and carriage returns appear in legitimately typed cells.

    They are whitespace, :func:`normalise` collapses them, and treating them as
    corruption would drop real fires.
    """
    assert chile_conaf.is_corrupt(*values) is False


def test_the_season_and_the_precisions_are_the_documented_vocabularies():
    """The constants the ``CHECK`` constraints are built from, pinned.

    A value added to either tuple without a migration would be accepted by the model
    and rejected by the database, which is the kind of drift that only shows up on a
    real import.
    """
    assert chile_conaf.DATE_TIME_PRECISIONS == ("minute", "day", "season")
    assert chile_conaf.REPORTERS == ("Conaf", "Empresa")
    assert chile_conaf.UTM_ZONES == (12, 18, 19)
    assert chile_conaf.SEASON_START_MONTH == 7
