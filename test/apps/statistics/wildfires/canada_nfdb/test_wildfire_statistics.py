#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NFDB burnt-area statistics application.

The fires are inserted through the ORM rather than imported from a shapefile: what has
to be asserted is arithmetic over known reported areas in known years, and building
that by hand is quicker and clearer than arranging for an importer to produce it.

The fixture is built round the thing this report exists to handle: **the published
points are not all in Canada**. It holds a fire whose coordinate lands over the
American border, a fire whose coordinate lands in the Atlantic, and a fire with no
usable coordinate at all — the three cases ``--country-source`` has to tell apart —
beside ordinary Canadian ones, and it spreads them over two agencies' worth of years
so that the ``Agencies`` column has something to union.
"""

import argparse
import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.canada_nfdb import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import canada_nfdb
from src.providers import ocha
from src.providers.canada_nfdb.ignition import NfdbIgnition
from src.providers.canada_nfdb.wildfire import NfdbWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-nfdb-statistics")

UTC = datetime.timezone.utc

#: Two countries that do not overlap, so that a point is in one of them or in neither
#: and the LATERAL's ``LIMIT 1`` has nothing to choose between. The real Canada-United
#: States border is nine thousand kilometres of shared edge, which is exactly why that
#: ``LIMIT 1`` is there; what this fixture tests is the attribution, not the tie-break.
COUNTRIES = [
    ("CAN", "Canada", box(-141.0, 49.0, -52.0, 84.0)),
    ("USA", "United States of America", box(-125.0, 25.0, -66.0, 48.5)),
]

#: (agency, year, cause, size_ha, point, prescribed).
#:
#: ``point`` is ``None`` for the fire whose published coordinate the import could not
#: use — a real row, with a real reported size, and no ignition to test. The sizes are
#: deliberately unequal within a year so a minimum and a maximum are distinguishable
#: from each other and from the total.
FIRES = [
    # 2023, inside Canada.
    ("BC", 2023, canada_nfdb.CAUSE_NATURAL, 100.0, (-123.0, 54.0), False),
    ("AB", 2023, canada_nfdb.CAUSE_HUMAN, 20.0, (-114.0, 53.0), False),
    # 2023, over the American border: a Canadian agency's report of a point that is
    # not in Canada. Reported as the United States under --country-source geometry.
    ("ON", 2023, canada_nfdb.CAUSE_HUMAN, 5.0, (-85.0, 45.0), False),
    # 2023, in the Atlantic: inside no country at all, and dropped.
    ("BC", 2023, canada_nfdb.CAUSE_UNKNOWN, 7.0, (-60.0, 45.0), False),
    # 2023, no usable published coordinate: also dropped, and for another reason.
    ("BC", 2023, canada_nfdb.CAUSE_HUMAN, 1.0, None, False),
    # 1990, inside Canada. The second is a prescribed burn.
    ("BC", 1990, canada_nfdb.CAUSE_NATURAL, 500.0, (-122.0, 55.0), False),
    ("PC", 1990, canada_nfdb.CAUSE_UNKNOWN, 50.0, (-116.0, 52.0), True),
]


@pytest.fixture
def populated(db_session):
    """The fixture world: two countries and seven agency fire reports."""
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

    for index, (agency, year, cause, size, point, prescribed) in enumerate(FIRES):
        reported = datetime.date(year, 7, 1)
        instant = datetime.datetime(year, 7, 1, tzinfo=UTC)
        ignition_id = None
        if point is not None:
            longitude, latitude = point
            ignition = NfdbIgnition(
                data_provider_id=nfdb_provider.id,
                nfdb_fire_id=f"{agency}-{index}", year=year, src_agency=agency,
                geometry=f"SRID=4326;POINT({longitude} {latitude})",
                # The published grid coordinates. Never read by this report — it is a
                # NOT NULL column because an ignition row exists only where the
                # service published a point, and this is that point.
                geometry_lambert=f"SRID=3978;POINT({index * 1000.0} {index * 1000.0})",
                date_time=instant, time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
            )
            db_session.add(ignition)
            db_session.flush()
            ignition_id = ignition.id
        db_session.add(NfdbWildfire(
            data_provider_id=nfdb_provider.id,
            nfdb_fire_id=f"{agency}-{index}", agency_fire_id=str(index),
            src_agency=agency, year=year, size_ha=size, fire_cause=cause,
            prescribed=prescribed, report_date=reported,
            start_date_time=instant, time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
            ignition_id=ignition_id,
        ))
    db_session.commit()
    return db_session


def run(session, **kwargs):
    """Compute the report over the fixture."""
    return app.compute(session, kwargs.pop("year", None), logger, **kwargs)


def find(rows, country, year):
    matches = [row for row in rows if row.country == country and row.year == year]
    assert len(matches) == 1, f"expected one row for {country}/{year}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Which country a fire counts towards
# --------------------------------------------------------------------------

def test_the_default_tests_the_published_point(populated):
    """Which is the whole reason this report exists, and the opposite of EGIF's default."""
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.country_source == app.COUNTRY_SOURCE_GEOMETRY


def test_a_fire_over_the_border_is_reported_as_that_country(populated):
    """A Canadian agency's report of a point that is not in Canada."""
    rows = run(populated)

    assert find(rows, "United States of America", 2023).fires == 1
    assert find(rows, "United States of America", 2023).total == pytest.approx(5.0)
    assert find(rows, "Canada", 2023).fires == 2, "the border fire is not in Canada's row"


def test_a_fire_in_no_country_is_dropped(populated):
    """A point in the Atlantic is not a fire anywhere."""
    canada = find(run(populated), "Canada", 2023)

    assert canada.total == pytest.approx(120.0), "100 + 20, without the 7 in the sea"


def test_a_fire_with_no_usable_point_is_dropped_too(populated):
    """And for a different reason, which the audit keeps separate."""
    audit = populated.execute(app.location_audit()).one()

    assert audit.no_point == 1
    assert audit.outside == 1


def test_filed_counts_every_fire_including_the_ones_geometry_drops(populated):
    rows = run(populated, country_source=app.COUNTRY_SOURCE_FILED)

    assert {row.country for row in rows} == {"Canada"}
    assert find(rows, "Canada", 2023).fires == 5
    assert find(rows, "Canada", 2023).total == pytest.approx(133.0), \
        "100 + 20 + 5 + 7 + 1: the border fire, the sea fire and the pointless one"


def test_the_audit_follows_the_scope(populated):
    """Its numbers and the Fires column have to account for the same set of fires."""
    audit = populated.execute(app.location_audit(year=1990)).one()

    assert audit.no_point == 0
    assert audit.outside == 0


def test_an_unknown_country_source_is_refused():
    with pytest.raises(ValueError, match="unknown country source"):
        app.country_columns("reported")


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

def test_a_year_reports_the_smallest_the_largest_and_the_sum(populated):
    canada = find(run(populated, include_prescribed=True), "Canada", 1990)

    assert canada.fires == 2
    assert canada.minimum == pytest.approx(50.0)
    assert canada.maximum == pytest.approx(500.0)
    assert canada.total == pytest.approx(550.0)


def test_the_total_row_is_the_sum_of_the_years(populated):
    rows = [row for row in run(populated) if row.country == "Canada"]
    total = rows[-1]
    years = rows[:-1]

    assert total.is_total
    assert total.year_label == app.TOTAL_LABEL
    assert total.fires == sum(row.fires for row in years)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))


def test_each_country_gets_its_years_newest_first_and_then_its_total(populated):
    rows = run(populated)

    assert [(row.country, row.year) for row in rows] == [
        ("Canada", 2023), ("Canada", 1990), ("Canada", None),
        ("United States of America", 2023), ("United States of America", None),
    ]


def test_a_reported_zero_is_a_real_answer(populated):
    """Two thirds of the real archive is under a hectare and 40,000 rows report zero."""
    provider_id = populated.scalars(
        select(DataProvider.id)
        .where(DataProvider.product == canada_nfdb.PROVIDER_PRODUCT)).one()
    populated.add(NfdbWildfire(
        data_provider_id=provider_id,
        src_agency="BC", year=1990, size_ha=0.0, fire_cause=canada_nfdb.CAUSE_HUMAN,
        prescribed=False, report_date=datetime.date(1990, 8, 1),
        start_date_time=datetime.datetime(1990, 8, 1, tzinfo=UTC),
        time_zone=canada_nfdb.DEFAULT_TIME_ZONE,
    ))
    populated.commit()

    canada = find(run(populated, country_source=app.COUNTRY_SOURCE_FILED), "Canada", 1990)
    assert canada.fires == 2, "the zero-hectare fire is counted"
    assert canada.minimum == pytest.approx(0.0)


# --------------------------------------------------------------------------
# The Agencies column
# --------------------------------------------------------------------------

def test_a_year_counts_the_agencies_behind_it(populated):
    rows = run(populated)

    assert find(rows, "Canada", 2023).agencies == frozenset({"BC", "AB"})
    assert find(rows, "Canada", 2023).agency_count == 2


def test_a_summary_row_unions_the_agencies_rather_than_adding_them(populated):
    """Thirteen agencies filing every year for fifty years are thirteen agencies."""
    canada = find(run(populated, include_prescribed=True), "Canada", None)

    assert canada.agencies == frozenset({"BC", "AB", "PC"})
    assert canada.agency_count == 3, "not 2 + 2"


def test_one_agency_makes_the_column_the_constant_one(populated):
    rows = run(populated, agency="BC")

    assert all(row.agency_count == 1 for row in rows)
    assert find(rows, "Canada", 2023).fires == 1, "BC's other 2023 fires are not in Canada"


# --------------------------------------------------------------------------
# Agencies, causes and prescribed burns
# --------------------------------------------------------------------------

def test_an_agency_can_be_resolved_in_any_case(populated):
    assert app.resolve_agency(populated, "bc") == "BC"
    assert app.resolve_agency(populated, " PC ") == "PC"


def test_an_unknown_agency_is_answered_with_the_ones_that_exist(populated):
    with pytest.raises(RuntimeError, match="No agency matches"):
        app.resolve_agency(populated, "XX")


def test_an_agency_is_never_matched_by_prefix(populated):
    """Two-letter codes: a prefix match would make 'N' mean four different things."""
    with pytest.raises(RuntimeError, match="No agency matches"):
        app.resolve_agency(populated, "B")


def test_the_agencies_are_read_from_the_database(populated):
    assert app.available_agencies(populated) == ["AB", "BC", "ON", "PC"]


def test_one_cause_can_be_selected(populated):
    canada = find(run(populated, cause="natural"), "Canada", 2023)

    assert canada.fires == 1
    assert canada.total == pytest.approx(100.0)


def test_the_three_causes_partition_the_archive(populated):
    whole = find(run(populated, country_source=app.COUNTRY_SOURCE_FILED),
                 "Canada", None).fires
    counted = sum(
        find(rows, "Canada", None).fires
        for rows in (run(populated, cause=cause,
                         country_source=app.COUNTRY_SOURCE_FILED)
                     for cause in app.CAUSES)
        if rows
    )

    assert counted == whole


def test_the_cause_vocabulary_is_the_providers(populated):
    assert set(app.CAUSES.values()) == set(canada_nfdb.FIRE_CAUSES)


def test_an_unknown_cause_is_refused():
    with pytest.raises(ValueError, match="unknown cause"):
        app.cause_condition("lightning")
    assert app.cause_condition(None) is None


def test_a_prescribed_burn_is_left_out_by_default(populated):
    rows = run(populated)

    assert find(rows, "Canada", 1990).fires == 1
    assert find(rows, "Canada", 1990).total == pytest.approx(500.0)


def test_a_prescribed_burn_can_be_counted_on_request(populated):
    canada = find(run(populated, include_prescribed=True), "Canada", 1990)

    assert canada.fires == 2
    assert canada.total == pytest.approx(550.0)


def test_the_prescribed_filter_needs_no_null_handling():
    assert app.is_a_wildfire(include_prescribed=True) is None
    assert "IS NOT" not in str(app.is_a_wildfire()).upper()


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

def test_one_year_can_be_selected(populated):
    rows = run(populated, year=1990)

    assert [(row.country, row.year) for row in rows] == [("Canada", 1990),
                                                         ("Canada", None)]


def test_a_minimum_area_selects_the_fires_not_the_years(populated):
    rows = run(populated, min_area=50.0)

    assert find(rows, "Canada", 2023).fires == 1, "only the 100 ha fire clears it"
    assert find(rows, "Canada", 1990).fires == 1


def test_a_year_with_no_fires_reports_nothing(populated):
    assert run(populated, year=1975) == []


def test_an_empty_report_has_no_total_row():
    assert app.summarise([], ["Canada"]) == []


def test_a_fire_with_no_year_is_reported_rather_than_silently_lost(populated):
    """The import cannot write one; a database written by something else could."""
    assert app.unknown_year_count(populated) == 0


def test_the_years_query_carries_the_scope(populated):
    assert list(populated.scalars(app.years_query())) == [2023, 1990]
    assert list(populated.scalars(app.years_query(agency="PC"))) == []
    assert list(populated.scalars(
        app.years_query(agency="PC", include_prescribed=True))) == [1990]


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


@pytest.mark.parametrize("option, value", [("--area-method", "geodesic"),
                                           ("--surface", "measured")])
def test_the_perimeter_options_are_refused_with_a_reason(capsys, option, value):
    """This dataset publishes no perimeter, so there is nothing to measure or choose."""
    with pytest.raises(SystemExit):
        app.parse_arguments([option, value, "--csv", "x.csv",
                             "--db-name", "x", "--db-user", "y"])
    assert "there is no" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["-5", "nan", "inf", "not a number"])
def test_a_nonsense_minimum_area_is_refused(text):
    with pytest.raises(argparse.ArgumentTypeError):
        app.hectares(text)


def test_a_valid_minimum_area_is_accepted():
    assert app.hectares("0") == 0.0
    assert app.hectares("200") == 200.0


def test_the_defaults():
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])

    assert args.country_source == app.COUNTRY_SOURCE_GEOMETRY
    assert args.include_prescribed is False
    assert args.cause is None
    assert args.agency is None


# --------------------------------------------------------------------------
# The outputs
# --------------------------------------------------------------------------

def test_the_csv_has_the_shared_columns_first(tmp_path, populated):
    path = tmp_path / "burnt.csv"
    app.write_csv(run(populated), path, logger)

    with path.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert tuple(table[0]) == app.COLUMNS
    assert tuple(table[0][:len(app.SHARED_COLUMNS)]) == app.SHARED_COLUMNS
    assert table[-1][1] == app.TOTAL_LABEL


def test_the_docx_is_written(tmp_path, populated):
    pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(populated), path, None, logger)

    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_these_are_not_the_nbac_figures(tmp_path, populated):
    """The single easiest mistake to make with this dataset."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(populated), path, None, logger)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "NBAC" in text
    assert "Do not add them" in text


def test_the_docx_says_what_the_point_test_did(tmp_path, populated):
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(populated), path, None, logger,
                   country_source=app.COUNTRY_SOURCE_GEOMETRY)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "inside no country" in text
