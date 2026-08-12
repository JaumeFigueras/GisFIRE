#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NBAC counts-by-cause application.

The arithmetic here is easy and the *denominator* is not, so that is what most of these
tests are about. ``Undetermined`` is a published category in this dataset rather than a
missing value, and it is far commoner in the early years — 3,777 of the 1970s' 5,386
fires — so a percentage taken over all fires would measure how much of the archive was
ever investigated rather than what caused the fires.

The fixture is built to make that visible: a year where most causes were determined and
a year where most were not, with the same natural share among the fires that *were*.
A report that divided by the wrong thing would give those two years different answers.

The area columns are here because the two Canadian datasets disagree by twenty-one
points about the share of natural *fires* and agree to two tenths of a point about the
share of natural *hectares*, so a report that counted only fires would hide the one
thing they corroborate.
"""

import csv
import datetime
import logging

import pytest

from src.apps.statistics.wildfires.canada_nbac import wildfire_causes as app
from src.apps.statistics.wildfires.canada_nbac import wildfire_statistics as statistics
from src.data_model.data_provider import DataProvider
from src.providers import canada_nbac
from src.providers.canada_nbac.wildfire import NbacWildfire

logger = logging.getLogger("test-nbac-causes")

UTC = datetime.timezone.utc

#: (year, cause, hectares, prescribed).
#:
#: 2023 has every cause determined; 1977 has one determined fire in four, which is the
#: shape of the real early archive. Both years are 50% natural **among the determined
#: fires**, and 50% / 12.5% among all of them — which is the difference the denominator
#: decision is about.
#:
#: The hectares are deliberately lopsided: the natural fires are much the larger, as
#: they are in the real data, so the area share and the count share are different
#: numbers and a test can tell them apart.
FIRES = [
    (2023, canada_nbac.CAUSE_NATURAL, 1000.0, False),
    (2023, canada_nbac.CAUSE_NATURAL, 3000.0, False),
    (2023, canada_nbac.CAUSE_HUMAN, 100.0, False),
    (2023, canada_nbac.CAUSE_HUMAN, 300.0, False),
    (1977, canada_nbac.CAUSE_NATURAL, 5000.0, False),
    (1977, canada_nbac.CAUSE_HUMAN, 500.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 700.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 900.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 1100.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 1300.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 1500.0, False),
    (1977, canada_nbac.CAUSE_UNDETERMINED, 1700.0, False),
    # A prescribed burn, excluded by default exactly as in the companion report.
    (2023, canada_nbac.CAUSE_HUMAN, 50.0, True),
]


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=canada_nbac.PROVIDER_NAME,
                            product=canada_nbac.PROVIDER_PRODUCT,
                            full_name=canada_nbac.PROVIDER_FULL_NAME,
                            url=canada_nbac.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def fires(db_session, provider):
    """The thirteen fires above, stored."""
    for index, (year, cause, hectares, prescribed) in enumerate(FIRES):
        db_session.add(NbacWildfire(
            data_provider=provider, gid=f"{year}_{index}", nfireid=index + 1, year=year,
            start_date_time=datetime.datetime(year, 7, 1, tzinfo=UTC),
            time_zone=canada_nbac.DEFAULT_TIME_ZONE,
            perimeter=f"SRID=4326;MULTIPOLYGON((({-114 + index * 0.1} 55, "
                      f"{-113.9 + index * 0.1} 55, {-113.9 + index * 0.1} 55.1, "
                      f"{-114 + index * 0.1} 55.1, {-114 + index * 0.1} 55)))",
            part_count=1, crosses_admin=False, admin_name="AB",
            fire_cause=cause,
            date_source=canada_nbac.SOURCE_AGENCY,
            date_time_precision=canada_nbac.PRECISION_DAY,
            agency_start_date=datetime.date(year, 7, 1),
            area_ha_polygon=hectares, area_ha_adjusted=hectares,
            area_adjusted=False, prescribed=prescribed,
        ))
    db_session.commit()
    return db_session


def rows_by_year(rows):
    return {row.year: row for row in rows}


def run(db_session, **kwargs):
    return app.compute(db_session, kwargs.pop("year", None), logger, **kwargs)


# --------------------------------------------------------------------------
# The counts
# --------------------------------------------------------------------------

def test_a_year_counts_its_fires_its_determined_and_its_natural(fires):
    rows = rows_by_year(run(fires))

    assert rows[2023].fires == 4, "the prescribed burn is not one of them"
    assert rows[2023].determined == 4
    assert rows[2023].matching == 2
    assert rows[2023].share == pytest.approx(50.0)


def test_the_percentage_is_of_the_determined_fires_and_not_of_all(fires):
    """The whole point of the denominator: 1977 is 50% natural, not 12.5%."""
    rows = rows_by_year(run(fires))

    assert rows[1977].fires == 8
    assert rows[1977].determined == 2, "six of the eight are Undetermined"
    assert rows[1977].matching == 1
    assert rows[1977].share == pytest.approx(50.0)
    assert rows[1977].share != pytest.approx(100.0 * 1 / 8)


def test_the_two_years_agree_because_the_denominator_is_right(fires):
    """Same natural share among determined fires, wildly different investigation rates.

    A report dividing by all fires would report 50% and 12.5% and read as a change in
    fire regime, which is exactly the artefact this denominator exists to avoid.
    """
    rows = rows_by_year(run(fires))
    assert rows[2023].share == pytest.approx(rows[1977].share)


def test_the_undetermined_count_is_derivable_from_the_table(fires):
    rows = rows_by_year(run(fires))

    assert rows[1977].undetermined == 6
    assert rows[2023].undetermined == 0


def test_the_human_cause_can_be_counted_instead(fires):
    rows = rows_by_year(run(fires, cause="human"))

    assert rows[2023].matching == 2
    assert rows[1977].matching == 1


def test_an_unknown_cause_is_refused():
    with pytest.raises(ValueError, match="unknown cause"):
        app.counts_query(2023, "lightning")


def test_undetermined_is_not_a_countable_cause():
    """It is the complement of the denominator, so its share would be zero by construction.

    Stated as a test so that adding it has to be a decision rather than an oversight.
    """
    assert canada_nbac.CAUSE_UNDETERMINED not in app.COUNTABLE_CAUSES.values()
    assert set(app.COUNTABLE_CAUSES.values()) == set(app.DETERMINED_CAUSES)


# --------------------------------------------------------------------------
# The hectares
# --------------------------------------------------------------------------

def test_the_area_columns_count_the_hectares_of_the_matching_fires(fires):
    rows = rows_by_year(run(fires))

    assert rows[2023].hectares == pytest.approx(4000.0), "1000 + 3000"
    assert rows[2023].determined_hectares == pytest.approx(4400.0)
    assert rows[2023].area_share == pytest.approx(100.0 * 4000 / 4400)


def test_the_area_share_and_the_count_share_are_different_numbers(fires):
    """Natural fires are fewer than the area suggests and very much larger.

    Over the real archive it is 67.18% of fires against 90.54% of hectares, and a
    report carrying only the first would hide the one figure the points report
    corroborates.
    """
    rows = rows_by_year(run(fires))

    assert rows[2023].share == pytest.approx(50.0)
    assert rows[2023].area_share > 90.0


def test_the_undetermined_hectares_are_in_neither_figure(fires):
    """The denominator's hectares are the determined ones, for the same reason."""
    rows = rows_by_year(run(fires))

    assert rows[1977].determined_hectares == pytest.approx(5500.0), "5000 + 500"
    assert rows[1977].area_share == pytest.approx(100.0 * 5000 / 5500)


# --------------------------------------------------------------------------
# Totals
# --------------------------------------------------------------------------

def test_the_total_row_adds_the_counts_and_the_hectares(fires):
    rows = run(fires)
    total = rows[-1]
    years = rows[:-1]

    assert total.is_total
    assert total.fires == sum(row.fires for row in years)
    assert total.determined == sum(row.determined for row in years)
    assert total.matching == sum(row.matching for row in years)
    assert total.hectares == pytest.approx(sum(row.hectares for row in years))


def test_the_total_share_is_the_ratio_of_the_totals_not_the_mean_of_the_ratios(fires):
    """A year with two determined fires and a year with four must not weigh the same."""
    rows = run(fires)
    total = rows[-1]

    assert total.determined == 6
    assert total.matching == 3
    assert total.share == pytest.approx(50.0)


def test_a_share_of_nothing_is_no_answer():
    row = app.Row(country="Canada", year=1977, fires=5, determined=0, matching=0,
                  hectares=0.0, determined_hectares=0.0)
    assert row.share is None
    assert row.area_share is None
    assert row.values[5] == ""
    assert row.values[7] == ""


def test_the_years_are_newest_first(fires):
    assert [row.year for row in run(fires)] == [2023, 1977, None]


def test_an_empty_report_has_no_total_row():
    assert app.summarise([]) == []


# --------------------------------------------------------------------------
# Agreement with the companion report
# --------------------------------------------------------------------------

def test_the_fires_column_matches_the_companion_report(fires):
    """Two reports over one dataset that disagreed about scope would be worse than one."""
    causes = rows_by_year(run(fires))
    burnt = rows_by_year(statistics.compute(fires, None, logger))

    assert set(causes) == set(burnt)
    for year in causes:
        assert causes[year].fires == burnt[year].fires, year


def test_the_prescribed_burn_can_be_counted_as_in_the_companion(fires):
    rows = rows_by_year(run(fires, include_prescribed=True))
    assert rows[2023].fires == 5
    assert rows[2023].determined == 5


def test_the_scope_helpers_are_the_companions(fires):
    """Imported rather than copied, because a copy is a thing that drifts."""
    assert app.years_query is statistics.years_query
    assert app.scope_conditions is statistics.scope_conditions
    assert app.COUNTRY_NAME == statistics.COUNTRY_NAME


def test_one_year_can_be_selected(fires):
    rows = run(fires, year=1977)
    assert [row.year for row in rows] == [1977, None]


# --------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------

def test_the_columns_name_the_cause_being_counted(fires):
    """A file of Human counts under a heading saying Natural would be a trap."""
    assert app.columns("natural")[4] == "Natural"
    assert app.columns("human")[4] == "Human"
    assert app.columns("human")[5] == "Human (%)"
    assert app.columns("natural")[:3] == ("Country", "Year", "Fires")


def test_the_csv_has_the_companion_reports_first_three_columns(tmp_path, fires):
    path = tmp_path / "causes.csv"
    app.write_csv(run(fires), path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert tuple(table[0]) == app.columns()
    assert tuple(table[0][:3]) == statistics.SHARED_COLUMNS[:3]
    assert table[-1][1] == app.TOTAL_LABEL
    assert len(table) == 4, "a header, two years and the total"


def test_the_docx_is_written(tmp_path, fires):
    pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(fires), path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_natural_is_not_lightning(tmp_path, fires):
    """The one thing a reader of a lightning analysis must not get wrong."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(fires), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "no lightning category" in text
    assert "not Lightning" in text


def test_the_docx_explains_the_denominator(tmp_path, fires):
    docx = pytest.importorskip("docx")
    path = tmp_path / "causes.docx"
    app.write_docx(run(fires), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "determined" in text
    assert "Undetermined" in text


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--db-name", "x", "--db-user", "y"])


def test_the_country_options_are_refused_with_a_reason(capsys):
    for option in ("--country", "--country-source"):
        with pytest.raises(SystemExit):
            app.parse_arguments([option, "Canada", "--csv", "x.csv",
                                 "--db-name", "x", "--db-user", "y"])
        assert "there is no --country" in capsys.readouterr().err


def test_undetermined_is_not_offered_on_the_command_line(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--cause", "undetermined", "--csv", "x.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "invalid choice" in capsys.readouterr().err


def test_the_defaults():
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.cause == app.DEFAULT_CAUSE == "natural"
    assert args.include_prescribed is False
