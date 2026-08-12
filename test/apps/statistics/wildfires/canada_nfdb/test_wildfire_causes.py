#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NFDB counts-by-cause application.

The twin of the NBAC counts-by-cause tests, over the other Canadian dataset, and the
denominator argument is the same one: ``U`` is a published category rather than a
missing value, so the percentages are of the fires whose cause somebody determined.

What is different here, and what these tests concentrate on:

* the natural share is a property of the **agency** far more than of the year — 83% in
  the Northwest Territories against 2.6% in Nova Scotia — so the national figure is a
  weighted average of thirteen fire regimes and ``--agency`` is how to get one that
  means one thing;
* a fire is counted under the country its **published point** falls in, so a report
  can have a United States row, and the two country sources count different fires;
* the column headings are the *word* and not the published letter, which is what lets
  this report's CSV be concatenated with NBAC's.
"""

import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.canada_nfdb import wildfire_causes as app
from src.apps.statistics.wildfires.canada_nfdb import wildfire_statistics as statistics
from src.data_model.data_provider import DataProvider
from src.providers import canada_nfdb
from src.providers import ocha
from src.providers.canada_nfdb.ignition import NfdbIgnition
from src.providers.canada_nfdb.wildfire import NfdbWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-nfdb-causes")

UTC = datetime.timezone.utc

#: Two countries that do not overlap, as in the companion statistics tests.
COUNTRIES = [
    ("CAN", "Canada", box(-141.0, 49.0, -52.0, 84.0)),
    ("USA", "United States of America", box(-125.0, 25.0, -66.0, 48.5)),
]

#: (agency, year, cause, size_ha, point).
#:
#: NT is almost all natural and NS almost none, which is the real shape and the reason
#: ``--agency`` exists. 1990 has an ``U`` fire so the denominator can be told from the
#: count of fires. One 2023 fire sits over the American border.
FIRES = [
    ("NT", 2023, canada_nfdb.CAUSE_NATURAL, 5000.0, (-114.0, 62.0)),
    ("NT", 2023, canada_nfdb.CAUSE_NATURAL, 3000.0, (-115.0, 62.0)),
    ("NT", 2023, canada_nfdb.CAUSE_HUMAN, 100.0, (-116.0, 62.0)),
    ("NS", 2023, canada_nfdb.CAUSE_HUMAN, 20.0, (-63.0, 55.0)),
    ("NS", 2023, canada_nfdb.CAUSE_HUMAN, 10.0, (-63.5, 55.0)),
    # Over the border: a Canadian agency's report of a point that is not in Canada.
    ("ON", 2023, canada_nfdb.CAUSE_NATURAL, 700.0, (-85.0, 45.0)),
    ("BC", 1990, canada_nfdb.CAUSE_NATURAL, 900.0, (-122.0, 55.0)),
    ("BC", 1990, canada_nfdb.CAUSE_HUMAN, 40.0, (-123.0, 55.0)),
    ("BC", 1990, canada_nfdb.CAUSE_UNKNOWN, 60.0, (-124.0, 55.0)),
]


@pytest.fixture
def populated(db_session):
    """Two countries and nine agency fire reports."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    nfdb_provider = DataProvider(name=canada_nfdb.PROVIDER_NAME,
                                 product=canada_nfdb.PROVIDER_PRODUCT,
                                 full_name=canada_nfdb.PROVIDER_FULL_NAME,
                                 url=canada_nfdb.PROVIDER_URL)
    db_session.add_all([ocha_provider, nfdb_provider])
    db_session.flush()

    for code, name, geometry in COUNTRIES:
        db_session.add(OchaAdminBoundary(
            data_provider_id=ocha_provider.id, source_id=code, level=0, name=name,
            geometry=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            source=code, iso_code=1, iso_2=code[:2], iso_3=code, iso_name=name,
            iso_3_group=code, region1_code=1, region1_name="r1", region2_code=2,
            region2_name="r2", region3_code=3, region3_name="r3", status_code=1,
            status_name="State", valid_date=datetime.date(2025, 1, 1),
            update_date=datetime.date(2025, 1, 1), land_source="osm", view="intl",
        ))

    for index, (agency, year, cause, size, point) in enumerate(FIRES):
        longitude, latitude = point
        instant = datetime.datetime(year, 7, 1, tzinfo=UTC)
        ignition = NfdbIgnition(
            data_provider_id=nfdb_provider.id, nfdb_fire_id=f"{agency}-{index}",
            year=year, src_agency=agency,
            geometry=f"SRID=4326;POINT({longitude} {latitude})",
            geometry_lambert=f"SRID=3978;POINT({index * 1000.0} {index * 1000.0})",
            date_time=instant, time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
        )
        db_session.add(ignition)
        db_session.flush()
        db_session.add(NfdbWildfire(
            data_provider_id=nfdb_provider.id, nfdb_fire_id=f"{agency}-{index}",
            agency_fire_id=str(index), src_agency=agency, year=year, size_ha=size,
            fire_cause=cause, prescribed=False, report_date=datetime.date(year, 7, 1),
            start_date_time=instant, time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
            ignition_id=ignition.id,
        ))
    db_session.commit()
    return db_session


def run(session, **kwargs):
    return app.compute(session, kwargs.pop("year", None), logger, **kwargs)


def find(rows, country, year):
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}"
    return matches[0]


# --------------------------------------------------------------------------
# The counts and the denominator
# --------------------------------------------------------------------------

def test_a_year_counts_its_fires_its_determined_and_its_natural(populated):
    canada = find(run(populated), "Canada", 1990)

    assert canada.fires == 3
    assert canada.determined == 2, "the U fire is not determined"
    assert canada.matching == 1
    assert canada.share == pytest.approx(50.0)


def test_the_percentage_is_of_the_determined_fires_and_not_of_all(populated):
    canada = find(run(populated), "Canada", 1990)

    assert canada.share == pytest.approx(50.0)
    assert canada.share != pytest.approx(100.0 / 3)


def test_the_unknown_count_is_derivable_from_the_table(populated):
    assert find(run(populated), "Canada", 1990).unknown == 1
    assert find(run(populated), "Canada", 2023).unknown == 0


def test_unknown_is_not_a_countable_cause():
    assert canada_nfdb.CAUSE_UNKNOWN not in app.COUNTABLE_CAUSES.values()
    assert set(app.COUNTABLE_CAUSES.values()) == set(app.DETERMINED_CAUSES)


def test_an_unknown_cause_is_refused():
    with pytest.raises(ValueError, match="unknown cause"):
        app.counts_query(2023, "lightning")


def test_the_human_cause_can_be_counted_instead(populated):
    canada = find(run(populated, cause="human"), "Canada", 2023)
    assert canada.matching == 3, "one NT and two NS"


# --------------------------------------------------------------------------
# The hectares
# --------------------------------------------------------------------------

def test_the_area_columns_count_the_reported_hectares(populated):
    canada = find(run(populated), "Canada", 2023)

    assert canada.hectares == pytest.approx(8000.0), "the two NT natural fires"
    assert canada.determined_hectares == pytest.approx(8130.0)


def test_the_area_share_and_the_count_share_are_different_numbers(populated):
    """Half the fires, nine tenths of the hectares — the finding the report exists for."""
    canada = find(run(populated), "Canada", 2023)

    assert canada.share == pytest.approx(40.0), "two natural of five determined"
    assert canada.area_share > 98.0


def test_the_unknown_hectares_are_in_neither_figure(populated):
    canada = find(run(populated), "Canada", 1990)
    assert canada.determined_hectares == pytest.approx(940.0), "900 + 40, not the 60"


# --------------------------------------------------------------------------
# Countries and agencies
# --------------------------------------------------------------------------

def test_a_fire_over_the_border_is_counted_under_that_country(populated):
    rows = run(populated)

    assert find(rows, "United States of America", 2023).matching == 1
    assert find(rows, "Canada", 2023).fires == 5, "the border fire is not Canada's"


def test_filed_counts_every_fire_as_canadian(populated):
    rows = run(populated, country_source=statistics.COUNTRY_SOURCE_FILED)

    assert {row.country for row in rows} == {"Canada"}
    assert find(rows, "Canada", 2023).fires == 6


def test_one_agency_can_be_selected(populated):
    """The natural share is a property of the agency far more than of the year."""
    northwest = find(run(populated, agency="NT"), "Canada", 2023)
    nova_scotia = find(run(populated, agency="NS"), "Canada", 2023)

    assert northwest.share == pytest.approx(100.0 * 2 / 3)
    assert nova_scotia.share == pytest.approx(0.0)


def test_the_national_figure_is_between_its_agencies(populated):
    """And is weighted by how much each files, which is what the warning is about."""
    national = find(run(populated), "Canada", 2023).share
    assert 0.0 < national < 100.0 * 2 / 3


# --------------------------------------------------------------------------
# Totals and agreement with the companion report
# --------------------------------------------------------------------------

def test_each_country_gets_its_years_then_its_total(populated):
    rows = run(populated)

    assert [(row.country, row.year) for row in rows] == [
        ("Canada", 2023), ("Canada", 1990), ("Canada", None),
        ("United States of America", 2023), ("United States of America", None),
    ]


def test_the_total_share_is_the_ratio_of_the_totals(populated):
    rows = [row for row in run(populated) if row.country == "Canada"]
    total = rows[-1]
    years = rows[:-1]

    assert total.determined == sum(row.determined for row in years)
    assert total.matching == sum(row.matching for row in years)
    assert total.share == pytest.approx(100.0 * total.matching / total.determined)


def test_a_share_of_nothing_is_no_answer():
    row = app.Row(country="Canada", year=1990, fires=3, determined=0, matching=0,
                  hectares=0.0, determined_hectares=0.0)
    assert row.share is None
    assert row.area_share is None
    assert row.values[5] == ""


def test_the_fires_column_matches_the_companion_report(populated):
    causes = {(row.country, row.year): row for row in run(populated)}
    burnt = {(row.country, row.year): row
             for row in statistics.compute(populated, None, logger)}

    assert set(causes) == set(burnt)
    for key in causes:
        assert causes[key].fires == burnt[key].fires, key


def test_the_scope_helpers_are_the_companions(populated):
    assert app.years_query is statistics.years_query
    assert app.scope_conditions is statistics.scope_conditions
    assert app.country_columns is statistics.country_columns
    assert app.resolve_agency is statistics.resolve_agency


def test_one_year_can_be_selected(populated):
    rows = run(populated, year=1990)
    assert [(row.country, row.year) for row in rows] == [("Canada", 1990),
                                                         ("Canada", None)]


# --------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------

def test_the_headings_are_the_word_and_not_the_published_letter(populated):
    """A column headed ``N`` says nothing, and NBAC's says ``Natural``.

    The two Canadian reports have to carry the same headings or their CSVs cannot be
    concatenated, which is most of the reason for reading them as a pair.
    """
    assert app.columns("natural")[4] == "Natural"
    assert app.columns("human")[4] == "Human"
    assert app.COUNTABLE_CAUSES["natural"] == canada_nfdb.CAUSE_NATURAL == "N"


def test_the_csv_has_the_companion_reports_first_three_columns(tmp_path, populated):
    path = tmp_path / "causes.csv"
    app.write_csv(run(populated), path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert tuple(table[0]) == app.columns()
    assert tuple(table[0][:3]) == statistics.SHARED_COLUMNS[:3]
    assert table[-1][1] == app.TOTAL_LABEL


def test_the_docx_is_written(tmp_path, populated):
    pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(populated), path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_natural_is_not_lightning(tmp_path, populated):
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(populated), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "no lightning category" in text
    assert "not defined as lightning" in text


def test_the_docx_warns_that_the_national_figure_is_an_average_of_agencies(tmp_path,
                                                                          populated):
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(populated), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "weighted average" in text


def test_the_docx_for_one_agency_does_not_carry_that_warning(tmp_path, populated):
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(populated, agency="NT"), path, None, logger, agency="NT")

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "weighted average" not in text
    assert "NT" in text


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--db-name", "x", "--db-user", "y"])


def test_the_country_option_is_refused_with_a_reason(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--country", "Canada", "--csv", "x.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "there is no --country here" in capsys.readouterr().err


def test_unknown_is_not_offered_on_the_command_line(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--cause", "unknown", "--csv", "x.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "invalid choice" in capsys.readouterr().err


def test_the_defaults():
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.cause == app.DEFAULT_CAUSE == "natural"
    assert args.country_source == statistics.COUNTRY_SOURCE_GEOMETRY
    assert args.agency is None
    assert args.include_prescribed is False
