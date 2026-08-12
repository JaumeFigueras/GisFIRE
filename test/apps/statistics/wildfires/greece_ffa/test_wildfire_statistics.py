#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Greek Fire Service burnt-area statistics application.

The fires are inserted through the ORM rather than imported from a workbook: what has
to be asserted is arithmetic over known areas in known years, and building that by
hand is quicker and clearer than arranging for an importer to produce it.

The fixture carries the two things no other statistics fixture does, because they are
the two things this report has that the others do not: a **year with no coordinates
at all** beside years that have them, which is the shape of the real archive either
side of 2020; and a **false alarm**, which is the one row a count of fires must leave
out — and which sits in the one year that publishes the category, beside twenty-five
whose category is ``NULL`` and which the obvious ``<>`` filter would silently drop.
"""

import argparse
import csv
import datetime
import logging

import pytest

from sqlalchemy import select

from src.apps.statistics.wildfires.greece_ffa import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.providers import greece_ffa
from src.providers.greece_ffa.ignition import GreeceFfaIgnition
from src.providers.greece_ffa.wildfire import GreeceFfaWildfire

logger = logging.getLogger("test-greece-statistics")

UTC = datetime.timezone.utc

#: (year, forest, forest_land, grassland, agricultural, located, category).
#:
#: Areas are in **hectares**, as stored — the import has already divided the published
#: στρέμματα by ten. They are deliberately unequal within a year so a minimum and a
#: maximum are distinguishable from each other and from the total, and they are chosen
#: so that every surface this report offers has a different answer.
#:
#: 2005 stands for the twenty years before 2020: no coordinate on any fire. 2021 and
#: 2025 have them. 2025 also carries the false alarm.
FIRES = [
    # 2005 — no fire of this era publishes a coordinate.
    (2005, 1.0, 2.0, 0.5, 0.0, False, None),
    (2005, 10.0, 0.0, 0.0, 4.0, False, None),
    (2005, 100.0, 50.0, 25.0, 0.0, False, None),
    # 2021 — two of the three are located, which is roughly the real proportion.
    (2021, 3.0, 1.0, 0.0, 0.0, True, None),
    (2021, 30.0, 0.0, 6.0, 2.0, True, None),
    (2021, 300.0, 100.0, 0.0, 0.0, False, None),
    # 2025 — every fire located, and one of them is not a fire at all.
    (2025, 7.0, 3.0, 0.0, 1.0, True, greece_ffa.CATEGORY_SMALL),
    (2025, 70.0, 0.0, 14.0, 0.0, True, greece_ffa.CATEGORY_LARGE),
    (2025, 0.5, 0.5, 0.5, 0.5, True, greece_ffa.CATEGORY_FALSE_ALARM),
]


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=greece_ffa.PROVIDER_NAME,
                            product=greece_ffa.PROVIDER_PRODUCT,
                            full_name=greece_ffa.PROVIDER_FULL_NAME,
                            url=greece_ffa.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def fires(db_session, provider):
    """The nine fires above, stored."""
    for index, (year, forest, forest_land, grassland, agricultural,
                located, category) in enumerate(FIRES):
        start = datetime.datetime(year, 7, 1, 12, 0, tzinfo=UTC)
        ignition_id = None
        if located:
            ignition = GreeceFfaIgnition(
                data_provider=provider, year=year,
                geometry=f"SRID=4326;POINT(23.{index:02d} 38.{index:02d})",
                date_time=start, time_zone=greece_ffa.DEFAULT_TIME_ZONE,
            )
            db_session.add(ignition)
            db_session.flush()
            ignition_id = ignition.id
        db_session.add(GreeceFfaWildfire(
            data_provider=provider, year=year, source_sheet=str(year),
            start_date_time=start, time_zone=greece_ffa.DEFAULT_TIME_ZONE,
            incident_category=category,
            area_ha_forest=forest, area_ha_forest_land=forest_land,
            area_ha_grove=0.0, area_ha_grassland=grassland,
            area_ha_reeds_marsh=0.0, area_ha_agricultural=agricultural,
            area_ha_crop_residue=0.0, area_ha_landfill=0.0,
            ignition_id=ignition_id,
        ))
    db_session.commit()
    return db_session


def rows_by_year(rows):
    return {row.year: row for row in rows}


def run(db_session, **kwargs):
    """Compute the report over the fixture."""
    return app.compute(db_session, kwargs.pop("year", None), logger, **kwargs)


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

def test_the_default_surface_is_every_land_cover_summed(fires):
    """``burnt`` is the nearest thing to the total the service does not publish."""
    rows = rows_by_year(run(fires))

    # 2005: 3.5, 14.0, 175.0 — and the total is their sum.
    assert rows[2005].minimum == pytest.approx(3.5)
    assert rows[2005].maximum == pytest.approx(175.0)
    assert rows[2005].total == pytest.approx(192.5)
    assert rows[2005].fires == 3


def test_a_single_surface_reports_that_column_alone(fires):
    rows = rows_by_year(run(fires, surface=app.SURFACE_FOREST))

    assert rows[2005].minimum == pytest.approx(1.0)
    assert rows[2005].maximum == pytest.approx(100.0)
    assert rows[2005].total == pytest.approx(111.0)


def test_the_woodland_grouping_sums_its_three_classes(fires):
    """Δάση + Δασική Έκταση + Άλση, which is this report's arithmetic, not a figure."""
    rows = rows_by_year(run(fires, surface=app.SURFACE_FOREST_TOTAL))

    # 2005: 3.0, 10.0, 150.0 — the grassland and agricultural columns are excluded.
    assert rows[2005].minimum == pytest.approx(3.0)
    assert rows[2005].maximum == pytest.approx(150.0)
    assert rows[2005].total == pytest.approx(163.0)


def test_every_surface_is_queryable(fires):
    """Each of the ten runs and reports a total no greater than the whole burnt area."""
    whole = rows_by_year(run(fires))[2005].total
    for surface in app.SURFACES:
        rows = rows_by_year(run(fires, surface=surface))
        assert 2005 in rows, f"{surface} lost a year"
        assert rows[2005].total <= whole + 1e-9, f"{surface} exceeds the whole"


def test_an_unknown_surface_is_refused():
    with pytest.raises(ValueError, match="unknown surface"):
        app.reported_surface("perimeter")


def test_the_total_row_is_the_sum_of_the_years(fires):
    rows = run(fires)
    total = rows[-1]
    years = rows[:-1]

    assert total.is_total
    assert total.year_label == app.TOTAL_LABEL
    assert total.fires == sum(row.fires for row in years)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))


def test_the_years_are_newest_first(fires):
    rows = run(fires)
    assert [row.year for row in rows] == [2025, 2021, 2005, None]


def test_the_country_is_greece_on_every_row(fires):
    assert all(row.country == "Greece" for row in run(fires))


# --------------------------------------------------------------------------
# The Located columns
# --------------------------------------------------------------------------

def test_a_year_before_2020_has_no_located_fires(fires):
    """Not a broken import: no year before 2020 publishes a coordinate at all."""
    rows = rows_by_year(run(fires))

    assert rows[2005].located == 0
    assert rows[2005].located_share == pytest.approx(0.0)


def test_a_later_year_counts_the_fires_that_publish_a_point(fires):
    rows = rows_by_year(run(fires))

    assert rows[2021].located == 2
    assert rows[2021].fires == 3
    assert rows[2021].located_share == pytest.approx(200.0 / 3)


def test_located_is_a_column_and_not_a_filter(fires):
    """An unlocated fire still contributes its hectares."""
    rows = rows_by_year(run(fires))

    assert rows[2021].fires == 3, "all three counted"
    assert rows[2021].maximum == pytest.approx(400.0), "including the unlocated one"


def test_the_total_share_is_the_ratio_of_the_totals_not_the_mean_of_the_ratios(fires):
    """Twenty years of 0% and six of 94% must not average to 22%."""
    rows = run(fires)
    total = rows[-1]

    assert total.located == 4, "two in 2021 and two in 2025, the false alarm excluded"
    assert total.fires == 8
    assert total.located_share == pytest.approx(50.0)


# --------------------------------------------------------------------------
# The false alarms
# --------------------------------------------------------------------------

def test_a_false_alarm_is_left_out_by_default(fires):
    rows = rows_by_year(run(fires))

    assert rows[2025].fires == 2, "the third 2025 record found no fire"
    assert rows[2025].total == pytest.approx(11.0 + 84.0)


def test_a_false_alarm_can_be_counted_on_request(fires):
    rows = rows_by_year(run(fires, include_false_alarms=True))

    assert rows[2025].fires == 3
    assert rows[2025].minimum == pytest.approx(2.0), "the false alarm is the smallest"


def test_excluding_false_alarms_keeps_the_years_that_publish_no_category(fires):
    """The bug this guards against is silent: ``<>`` would drop 2005 and 2021 entirely.

    ``incident_category`` is NULL for every year before 2025, and ``NULL <> 'x'`` is
    NULL rather than true, so a report built on the obvious filter would still build,
    still total, and simply be of the wrong archive.
    """
    rows = rows_by_year(run(fires))

    assert set(rows) == {2005, 2021, 2025, None}, "no year was dropped by the filter"
    assert rows[2005].fires == 3
    assert rows[2021].fires == 3


def test_the_excluded_false_alarms_are_counted_for_the_log(fires):
    assert app.false_alarm_count(fires) == 1
    assert app.false_alarm_count(fires, year=2025) == 1
    assert app.false_alarm_count(fires, year=2005) == 0


def test_the_filter_is_null_safe_by_construction():
    """Stated against the SQL, so that a rewrite to ``!=`` has to face this test."""
    condition = app.is_a_fire()
    assert "IS DISTINCT FROM" in str(condition.compile()).upper()
    assert app.is_a_fire(include_false_alarms=True) is None


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

def test_one_year_can_be_selected(fires):
    rows = run(fires, year=2021)

    assert [row.year for row in rows] == [2021, None]
    assert rows[0].fires == 3


def test_a_minimum_area_selects_the_fires_not_the_years(fires):
    """The threshold picks which fires the figures come from; it drops no year."""
    rows = rows_by_year(run(fires, min_area=100.0))

    assert rows[2005].fires == 1, "only the 175 ha fire"
    assert rows[2005].total == pytest.approx(175.0)
    assert rows[2021].fires == 1, "only the 400 ha fire"
    assert 2025 not in rows, "no 2025 fire reaches 100 ha, so the year has no row"


def test_a_year_with_no_fires_reports_nothing(fires):
    assert run(fires, year=1999) == []


def test_an_empty_report_has_no_total_row(fires):
    assert app.summarise([]) == []


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_an_output_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--db-name", "x", "--db-user", "y"])


def test_the_country_options_are_refused_with_a_reason(capsys):
    """Copied from another report's command line, which is a reasonable thing to do."""
    for option in ("--country", "--country-source"):
        with pytest.raises(SystemExit):
            app.parse_arguments([option, "Greece", "--csv", "x.csv",
                                 "--db-name", "x", "--db-user", "y"])
        assert "there is no" in capsys.readouterr().err


def test_the_area_method_option_is_refused_with_a_reason(capsys):
    """This dataset publishes no perimeter, so there is nothing to measure."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--area-method", "geodesic", "--csv", "x.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "no --area-method" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["-5", "nan", "inf", "not a number"])
def test_a_nonsense_minimum_area_is_refused(text):
    with pytest.raises(argparse.ArgumentTypeError):
        app.hectares(text)


def test_a_valid_minimum_area_is_accepted():
    assert app.hectares("0") == 0.0
    assert app.hectares("12.5") == 12.5


def test_the_default_surface_is_the_whole_burnt_area():
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.surface == app.SURFACE_BURNT
    assert args.include_false_alarms is False


# --------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------

def test_the_csv_has_the_shared_columns_first(tmp_path, fires):
    path = tmp_path / "burnt.csv"
    app.write_csv(run(fires), path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert tuple(table[0]) == app.COLUMNS
    assert tuple(table[0][:len(app.SHARED_COLUMNS)]) == app.SHARED_COLUMNS
    assert table[-1][1] == app.TOTAL_LABEL
    assert len(table) == 5, "a header, three years and the total"


def test_the_csv_writes_bare_numbers(tmp_path, fires):
    path = tmp_path / "burnt.csv"
    app.write_csv(run(fires), path, logger)
    text = path.read_text(encoding="utf-8")

    assert "," in text, "it is a CSV"
    assert "192.50" in text, "and 2005's total is written unseparated"


def test_the_docx_is_written(tmp_path, fires):
    pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires), path, None, logger)

    assert path.exists() and path.stat().st_size > 0


def test_the_docx_names_the_surface_it_reports(tmp_path, fires):
    """A table of grassland hectares must not read as a table of forest ones."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires, surface=app.SURFACE_GRASSLAND), path, None, logger,
                   surface=app.SURFACE_GRASSLAND)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert app.SURFACE_PROSE[app.SURFACE_GRASSLAND] in text


def test_the_docx_says_there_is_no_cause(tmp_path, fires):
    """The one thing a reader coming from the Spanish or Portuguese report will look for."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "no cause" in text


def test_every_surface_has_prose():
    """So that a surface added later cannot reach the Word writer without a description."""
    assert set(app.SURFACE_PROSE) == set(app.SURFACES)


def test_a_share_of_nothing_is_no_answer():
    assert app.share(0, 0) is None
    assert app.share_label(0, 0) == ""
    assert app.share_label(1, 4) == "25.00"


# --------------------------------------------------------------------------
# What this dataset does not have
# --------------------------------------------------------------------------

def test_there_is_no_causes_companion_application():
    """Portugal and Spain have one; Greece cannot.

    Nothing in the twenty-six published sheets says why a fire started — no cause
    column, no lightning category, no catalogue to seed. This test exists so that the
    absence is a recorded decision rather than something that looks forgotten.
    """
    from pathlib import Path

    from src.settings import ROOT_DIR

    causes = Path(ROOT_DIR) / "src/apps/statistics/wildfires/greece_ffa/wildfire_causes.py"
    assert not causes.exists()
    assert not hasattr(GreeceFfaWildfire, "cause_id")
    assert not hasattr(GreeceFfaWildfire, "cause")


def test_the_ignition_is_what_a_lightning_analysis_would_join_to(fires):
    """The dataset carries no cause, but it does carry points and instants.

    That is the only handle a lightning attribution could ever use here, and it
    reaches the last six years alone — which is what this asserts, so that anyone
    planning such an analysis meets the limit in a test rather than in a result.
    """
    located = fires.scalars(select(Ignition)).all()

    assert {ignition.date_time.year for ignition in located} == {2021, 2025}
    assert all(ignition.geometry is not None for ignition in located)
