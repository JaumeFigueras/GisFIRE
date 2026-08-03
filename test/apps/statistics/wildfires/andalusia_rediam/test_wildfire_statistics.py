#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the REDIAM burnt-area statistics application.

The fires here are inserted through the ORM rather than imported from a shapefile:
what has to be asserted is arithmetic over known areas in known years, and building
that by hand is both quicker and clearer than arranging for an importer to produce it.

The measured areas are checked against :mod:`pyproj`, which computes the same geodesic
area through PROJ rather than through PostGIS. Two independent implementations agreeing
is worth considerably more than a magic number copied out of whatever the code returned
the first time it ran.

This fixture carries two things no other statistics fixture does, because they are the
two things this report has that the others do not: **bindings to EGIF *partes***, of
two different strengths and with a year that has none, and **a published burnt area
beside a measured one**, deliberately disagreeing — which is what ``--surface`` exists
to keep apart.
"""

import argparse
import csv
import datetime
import logging

import pytest

from pyproj import Geod
from shapely.geometry import MultiPolygon
from shapely.geometry import box
from sqlalchemy import select

from src.apps.statistics.wildfires.andalusia_rediam import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import andalusia_rediam
from src.providers import spain_egif
from src.providers.andalusia_rediam.wildfire import MATCH_CODE
from src.providers.andalusia_rediam.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.andalusia_rediam.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.andalusia_rediam.wildfire import RediamWildfire
from src.providers.spain_egif.wildfire import EgifWildfire

logger = logging.getLogger("test-rediam-statistics")

GEOD = Geod(ellps="WGS84")

UTC = datetime.timezone.utc

#: (code, year, match method, perimeter, published hectares). Sizes are deliberately
#: unequal within a year so a minimum and a maximum are distinguishable from each other
#: and from the total. Every box is somewhere in or around Andalusia, which matters for
#: nothing here — nothing is tested against a boundary — but keeps the fixture readable.
#:
#: The match method is ``None`` for a fire the binding left unbound, ``MATCH_CODE`` for
#: one bound on the published identifier and ``MATCH_DATE_PROVINCE_NAME`` for one bound
#: on a date and a municipality name. The three are what ``--min-confidence`` tells
#: apart.
#:
#: The published hectares are ``(wooded, scrub, grassland)`` and are **not** the area of
#: the box beside them. That is the point: the service publishes three vegetation
#: classes and the perimeter encloses more than the three, so the two figures disagree
#: on the real data by 7.8% and must never be silently interchanged.
FIRES = [
    # 2022: three fires of clearly different sizes, two bound and one of those on a
    # name rather than on an identifier.
    ("2022040091", 2022, MATCH_CODE, box(-2.50, 37.00, -2.40, 37.10), (10.0, 20.0, 5.0)),
    ("2022040092", 2022, MATCH_DATE_PROVINCE_NAME,
     box(-2.20, 37.20, -1.80, 37.60), (100.0, 200.0, 50.0)),
    ("2022040093", 2022, None, box(-2.60, 36.90, -2.55, 36.95), (1.0, 2.0, 0.0)),
    # 2012: one bound fire, smaller than every 2022 one.
    ("2012110044", 2012, MATCH_CODE, box(-5.60, 36.10, -5.59, 36.11), (0.5, 1.0, 0.0)),
    # 2008: two fires, one of them the largest of the fixture, neither bound.
    ("2008410097", 2008, None, box(-6.30, 37.10, -5.30, 38.10), (1000.0, 2000.0, 500.0)),
    ("2008410098", 2008, None, box(-6.10, 37.50, -6.00, 37.60), (5.0, 10.0, 1.0)),
]

#: Where a REDIAM year with no EGIF campaign behind it is added: 2025, exactly as on the
#: published data, where the exports stop at 2023.
UNREACHED_YEAR = 2025


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def expected(code: str) -> float:
    """The measured area PROJ computes for one fixture fire."""
    for fire_code, _, _, geometry, _ in FIRES:
        if fire_code == code:
            return hectares(geometry)
    raise KeyError(code)


def published(code: str) -> tuple[float, float, float]:
    """The hectares the fixture publishes for one fire."""
    for fire_code, _, _, _, areas in FIRES:
        if fire_code == code:
            return areas
    raise KeyError(code)


def add_fire(session, provider_ids, code, year, method, geometry, areas,
             fire_date=None) -> RediamWildfire:
    """One Andalusian perimeter, bound to a *parte* of its own where ``method`` says so.

    The *parte* is created here rather than in a fixture of its own because nothing in
    this report reads it: what is under test is the link, not what is on the other end.
    """
    rediam_id, egif_id = provider_ids
    fire_date = fire_date or datetime.date(year, 8, 1)
    wooded, scrub, grassland = areas

    egif_wildfire_id = None
    if method is not None:
        parte = EgifWildfire(
            data_provider_id=egif_id, report_number=code, campaign=year,
            province_ine_code=code[4:6], municipality_name="DALIAS",
            start_date_time=datetime.datetime(fire_date.year, fire_date.month,
                                              fire_date.day, 12, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE)
        session.add(parte)
        session.flush()
        egif_wildfire_id = parte.id

    fire = RediamWildfire(
        data_provider_id=rediam_id, source_layer="PERIMETROS_COR_2008_2025",
        code=code, fire_date=fire_date, year=year, municipality_name="DALIAS",
        province_name="Almería", part_count=1,
        area_ha_wooded=wooded, area_ha_scrub=scrub, area_ha_grassland=grassland,
        # Local midnight, which is all the dataset ever publishes.
        start_date_time=datetime.datetime(fire_date.year, fire_date.month,
                                          fire_date.day, tzinfo=UTC),
        time_zone=andalusia_rediam.DEFAULT_TIME_ZONE,
        perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
        perimeter_etrs89_utm30n=None,
        egif_wildfire_id=egif_wildfire_id,
        match_method=method,
        match_confidence=None if method is None else MATCH_METHOD_CONFIDENCE[method],
        matched_at=None if method is None else datetime.datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(fire)
    session.flush()
    return fire


@pytest.fixture
def provider_ids(db_session):
    """The two providers a bound Andalusian fire needs: REDIAM and MITECO."""
    rediam = DataProvider(name=andalusia_rediam.PROVIDER_NAME,
                          product=andalusia_rediam.PROVIDER_PRODUCT,
                          full_name=andalusia_rediam.PROVIDER_FULL_NAME,
                          url=andalusia_rediam.PROVIDER_URL)
    egif = DataProvider(name=spain_egif.PROVIDER_NAME,
                        product=spain_egif.PROVIDER_PRODUCT,
                        full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add_all([rediam, egif])
    db_session.commit()
    return rediam.id, egif.id


@pytest.fixture
def populated(db_session, provider_ids):
    """Six Andalusian fires across three years, three of them bound to a *parte*."""
    for code, year, method, geometry, areas in FIRES:
        add_fire(db_session, provider_ids, code, year, method, geometry, areas)
    db_session.commit()
    return db_session


@pytest.fixture
def unreached(populated, provider_ids):
    """``populated`` plus a year the EGIF exports do not reach: nothing bound in it."""
    add_fire(populated, provider_ids, "IIFF2025040059", UNREACHED_YEAR, None,
             box(-3.00, 37.00, -2.95, 37.05), (2.0, 3.0, 1.0))
    populated.commit()
    return populated


def rows_for(session, year=None, surface=app.SURFACE_MEASURED,
             method=app.AREA_METHOD_GEODESIC, min_area=None,
             min_confidence=None) -> list[app.Row]:
    return app.compute(session, year, logger, surface, method, min_area, min_confidence)


def halfway(smaller: str, larger: str) -> float:
    """A ``--min-area`` that keeps fire ``larger`` and drops fire ``smaller``.

    Midway between the two rather than equal to either, so that no test turns on whether
    PostGIS and PROJ agree to the last bit on a boundary case. Derived from the fixture
    rather than written as a number of hectares, so that resizing a fixture fire cannot
    quietly turn a threshold into a no-op.

    The fixture's fires by measured area::

        2012110044      98   2022040093    2,458   2008410098    9,819
        2022040091   9,832   2022040092  157,269   2008410097  974,995   ha
    """
    return (expected(smaller) + expected(larger)) / 2


def find(rows: list[app.Row], year: int | None) -> app.Row:
    matches = [row for row in rows if row.year == year]
    assert len(matches) == 1, f"expected one row for {year}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------

def test_an_output_is_required():
    """Computing a report and then printing nothing would be a strange thing to allow."""
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_either_output_alone_is_enough():
    assert app.parse_arguments(["--csv", "out.csv"]).docx is None
    assert app.parse_arguments(["--docx", "out.docx"]).csv is None


def test_the_defaults_are_every_year_measured():
    parsed = app.parse_arguments(["--csv", "out.csv"])
    assert parsed.year is None
    assert parsed.surface == app.SURFACE_MEASURED
    assert parsed.min_area is None
    assert parsed.min_confidence is None


def test_the_area_method_is_unset_rather_than_defaulted():
    """So that passing it with a published surface can be told from not passing it."""
    assert app.parse_arguments(["--csv", "out.csv"]).area_method is None


def test_there_is_no_country_option(capsys):
    """The service publishes Andalusia's fires, so there is nothing to select."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Spain"])

    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_country_source_option(capsys):
    """Asked for and refused, rather than accepted and quietly ignored."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "geometry"])

    assert "no --country-source here" in capsys.readouterr().err


def test_an_area_method_with_a_published_surface_is_refused(capsys):
    """Nothing is measured there, so a choice of how to measure claims too much."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--surface", "scrub",
                             "--area-method", "geodesic"])

    assert "--area-method applies to --surface measured" in capsys.readouterr().err


def test_an_area_method_with_the_measured_surface_is_fine():
    parsed = app.parse_arguments(["--csv", "out.csv", "--area-method", "equal-area"])
    assert parsed.area_method == app.AREA_METHOD_EQUAL_AREA


def test_an_unknown_surface_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--surface", "hectares"])
    with pytest.raises(ValueError, match="unknown surface"):
        app.burnt_area("hectares")


def test_an_unknown_area_method_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--area-method", "utm30n"])
    with pytest.raises(ValueError, match="unknown area method"):
        app.burnt_area(app.SURFACE_MEASURED, "utm30n")


@pytest.mark.parametrize("value", ["five", "", "5ha"])
def test_a_minimum_area_that_is_not_a_number_is_refused(value):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-area", value])
    with pytest.raises(argparse.ArgumentTypeError, match="not a number"):
        app.hectares(value)


def test_a_negative_minimum_area_is_refused():
    with pytest.raises(argparse.ArgumentTypeError, match="cannot be negative"):
        app.hectares("-5")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_a_minimum_area_that_is_not_finite_is_refused(value):
    """``nan`` is the one worth refusing loudest: it would produce an empty report."""
    with pytest.raises(argparse.ArgumentTypeError, match="finite"):
        app.hectares(value)


def test_zero_is_a_threshold_and_not_a_missing_one():
    """Falsy, and so exactly what a truthiness test would get wrong."""
    assert app.parse_arguments(["--csv", "out.csv", "--min-area", "0"]).min_area == 0.0


@pytest.mark.parametrize("value", ["90", "-0.1", "1.5"])
def test_a_confidence_outside_the_range_is_refused(value):
    with pytest.raises(argparse.ArgumentTypeError, match="between 0 and 1"):
        app.confidence(value)


def test_a_zero_confidence_is_a_threshold_and_not_a_missing_one():
    assert app.parse_arguments(
        ["--csv", "out.csv", "--min-confidence", "0"]).min_confidence == 0.0


def test_the_shared_columns_match_the_other_reports():
    """So the CSVs can still be concatenated on the six columns they have in common."""
    from src.apps.statistics.wildfires.catalonia_darpa import wildfire_statistics as darpa
    from src.apps.statistics.wildfires.gfa import wildfire_statistics as gfa_app
    from src.apps.statistics.wildfires.gwis import wildfire_statistics as gwis_app
    from src.apps.statistics.wildfires.portugal_icnf import wildfire_statistics as icnf_app
    from src.apps.statistics.wildfires.spain_egif import wildfire_statistics as egif_app

    assert app.SHARED_COLUMNS == gfa_app.COLUMNS == gwis_app.COLUMNS == \
           icnf_app.COLUMNS == egif_app.COLUMNS
    assert app.COLUMNS == darpa.COLUMNS, "the two regional reports are read side by side"


# --------------------------------------------------------------------------
# The measured statistics
# --------------------------------------------------------------------------

def test_the_area_matches_an_independent_geodesic_computation(populated):
    """PostGIS on the ellipsoid against PROJ on the ellipsoid: two implementations."""
    year_2022 = find(rows_for(populated), 2022)

    assert year_2022.maximum == pytest.approx(expected("2022040092"), rel=1e-6)
    assert year_2022.minimum == pytest.approx(expected("2022040093"), rel=1e-6)
    assert year_2022.total == pytest.approx(
        expected("2022040091") + expected("2022040092") + expected("2022040093"), rel=1e-6)


def test_the_areas_are_in_hectares(populated):
    """An order-of-magnitude check, to catch a missing or doubled unit conversion.

    ``2008410097`` is a one-degree square at 37-38°N. A degree of latitude is about
    111 km; a degree of longitude there is 111 km x cos(37.5°), about 88 km. So roughly
    111 x 88 = 9,800 km², which is ~980,000 ha — not 98 and not 9.8e9.
    """
    assert 900_000 < find(rows_for(populated), 2008).maximum < 1_100_000


def test_each_year_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Spain", "2022"), ("Spain", "2012"), ("Spain", "2008"), ("Spain", "Total"),
    ]


def test_the_country_is_a_constant_and_nothing_is_tested_against_a_boundary(populated):
    """No OCHA boundary is imported by the fixture, and the report does not want one."""
    assert {row.country for row in rows_for(populated)} == {app.COUNTRY_NAME}


def test_the_total_row_summarises_every_year(populated):
    """Fires, hectares and matches are sums; the minimum and maximum are not."""
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2022, 2012, 2008)]

    assert total.fires == sum(row.fires for row in years) == len(FIRES)
    assert total.matched == sum(row.matched for row in years)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))
    # The two ends come from different years, which a per-year total could not give.
    assert total.minimum == pytest.approx(expected("2012110044"), rel=1e-6)
    assert total.maximum == pytest.approx(expected("2008410097"), rel=1e-6)


def test_the_two_area_methods_agree(populated):
    geodesic = rows_for(populated, method=app.AREA_METHOD_GEODESIC)
    projected = rows_for(populated, method=app.AREA_METHOD_EQUAL_AREA)

    for measured, transformed in zip(geodesic, projected):
        assert (measured.country, measured.year) == (transformed.country, transformed.year)
        for figure in ("minimum", "maximum", "total"):
            assert getattr(transformed, figure) == pytest.approx(
                getattr(measured, figure), rel=1e-3), f"{measured.year} {figure}"


def test_the_published_grid_is_not_offered():
    """EPSG:25830 is what the service measures on, and it is conformal.

    Andalusia is wide for one UTM zone — 1.6°W to 7.5°W against a central meridian at
    3°W — so the distortion is not uniform across it. Asserted here so the omission
    stays deliberate.
    """
    assert andalusia_rediam.SOURCE_SRID == 25830
    assert str(andalusia_rediam.SOURCE_SRID) not in " ".join(app.AREA_METHODS)
    assert app.EQUAL_AREA_SRID != andalusia_rediam.SOURCE_SRID


# --------------------------------------------------------------------------
# Measured against published
# --------------------------------------------------------------------------

def test_a_published_surface_reports_what_the_service_published(populated):
    """Not the polygon: the number on the service's own figures."""
    year_2022 = find(rows_for(populated, surface=app.SURFACE_SCRUB), 2022)

    assert year_2022.fires == 3
    assert year_2022.total == pytest.approx(
        published("2022040091")[1] + published("2022040092")[1]
        + published("2022040093")[1])
    assert year_2022.maximum == pytest.approx(published("2022040092")[1])


def test_the_published_surface_adds_the_three_classes(populated):
    year_2022 = find(rows_for(populated, surface=app.SURFACE_PUBLISHED), 2022)

    assert year_2022.total == pytest.approx(
        sum(sum(published(code)) for code in
            ("2022040091", "2022040092", "2022040093")))


def test_the_three_classes_add_up_to_the_published_total(populated):
    """Only in the total column — a minimum of minima over three columns is not one."""
    parts = [find(rows_for(populated, surface=surface), None).total
             for surface in (app.SURFACE_WOODED, app.SURFACE_SCRUB, app.SURFACE_GRASSLAND)]
    whole = find(rows_for(populated, surface=app.SURFACE_PUBLISHED), None).total

    assert sum(parts) == pytest.approx(whole)


def test_the_published_and_the_measured_are_different_numbers(populated):
    """The whole reason ``--surface`` exists, and the fixture is built to show it."""
    measured = find(rows_for(populated), None).total
    reported = find(rows_for(populated, surface=app.SURFACE_PUBLISHED), None).total

    assert measured != pytest.approx(reported)


def test_a_published_zero_is_counted_and_is_not_a_missing_value(populated):
    """A fire that burnt no grassland has SUP_PASTIZ of 0.00, which is an answer."""
    year_2022 = find(rows_for(populated, surface=app.SURFACE_GRASSLAND), 2022)

    assert year_2022.fires == 3, "the fire with 0.0 ha of grassland still counts"
    assert year_2022.minimum == 0.0


def test_a_fire_that_does_not_report_a_surface_is_left_out(populated, provider_ids):
    """A NULL is a form that does not say, not a fire that burnt none of it."""
    add_fire(populated, provider_ids, "2022040094", 2022, None,
             box(-2.0, 37.0, -1.99, 37.01), (None, 1.0, 1.0))
    populated.commit()

    assert find(rows_for(populated, surface=app.SURFACE_WOODED), 2022).fires == 3
    assert find(rows_for(populated, surface=app.SURFACE_SCRUB), 2022).fires == 4
    # And it is counted under 'published', where one reported component is enough.
    assert find(rows_for(populated, surface=app.SURFACE_PUBLISHED), 2022).fires == 4


def test_the_fires_left_out_are_reported(populated, provider_ids, caplog):
    """Zero on the whole published archive, which is why it is asked rather than assumed."""
    add_fire(populated, provider_ids, "2022040094", 2022, None,
             box(-2.0, 37.0, -1.99, 37.01), (None, 1.0, 1.0))
    populated.commit()

    with caplog.at_level(logging.WARNING):
        rows_for(populated, surface=app.SURFACE_WOODED)

    assert "do not report a wooded area" in caplog.text


def test_nothing_is_left_out_of_the_published_archive(populated, caplog):
    with caplog.at_level(logging.WARNING):
        for surface in app.SURFACES:
            rows_for(populated, surface=surface)

    assert "do not report" not in caplog.text


# --------------------------------------------------------------------------
# The year, the threshold and the scope
# --------------------------------------------------------------------------

def test_the_published_year_is_used_even_when_the_date_disagrees(populated, provider_ids):
    """The import checks the two agree; this checks the report reads the column it says."""
    add_fire(populated, provider_ids, "2011110001", 2011, None,
             box(-4.0, 37.0, -3.99, 37.01), (1.0, 1.0, 1.0),
             fire_date=datetime.date(2010, 12, 31))
    populated.commit()

    rows = rows_for(populated)
    assert find(rows, 2011).fires == 1
    assert 2010 not in {row.year for row in rows}


def test_a_single_year_can_be_selected(populated):
    rows = rows_for(populated, year=2008)
    assert [row.year_label for row in rows] == ["2008", "Total"]
    assert rows[0].total == pytest.approx(rows[1].total)


def test_a_year_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


def test_no_minimum_area_counts_every_fire(populated):
    assert rows_for(populated, min_area=None) == rows_for(populated)


def test_the_smaller_fires_stop_being_counted(populated):
    """2022 has fires of 2,458, 9,832 and 157,269 ha; keep the largest two."""
    rows = rows_for(populated, min_area=halfway("2022040093", "2022040091"))
    year_2022 = find(rows, 2022)

    assert year_2022.fires == 2
    assert year_2022.minimum == pytest.approx(expected("2022040091"), rel=1e-6)
    assert year_2022.maximum == pytest.approx(expected("2022040092"), rel=1e-6)


def test_a_year_whose_fires_are_all_too_small_drops_out(populated):
    """2012 holds one fire of 98 ha and nothing else, so the year goes with it."""
    rows = rows_for(populated, min_area=halfway("2012110044", "2022040093"))

    assert 2012 not in {row.year for row in rows}
    assert [row.year_label for row in rows] == ["2022", "2008", "Total"]


def test_the_threshold_applies_to_the_surface_being_reported(populated):
    """5 ha of scrub is not 5 ha of perimeter, and the threshold follows the column."""
    rows = rows_for(populated, surface=app.SURFACE_SCRUB, min_area=15.0)
    year_2022 = find(rows, 2022)

    # Only the fires publishing 20 and 200 ha of scrub survive.
    assert year_2022.fires == 2
    assert year_2022.minimum == pytest.approx(published("2022040091")[1])


def test_the_threshold_is_not_a_filter_on_the_totals(populated):
    """A HAVING would have dropped years, not fires."""
    year_2008 = find(rows_for(populated, min_area=halfway("2008410098", "2008410097")),
                     2008)

    assert year_2008.fires == 1
    assert year_2008.total == pytest.approx(expected("2008410097"), rel=1e-6)
    assert year_2008.minimum == pytest.approx(year_2008.maximum)


# --------------------------------------------------------------------------
# How many matched the EGIF data
# --------------------------------------------------------------------------

def test_each_year_reports_how_many_of_its_fires_are_bound(populated):
    rows = rows_for(populated)

    assert find(rows, 2022).matched == 2
    assert find(rows, 2012).matched == 1
    assert find(rows, 2008).matched == 0
    assert find(rows, None).matched == 3


def test_the_share_is_of_the_fires_counted_beside_it(populated):
    rows = rows_for(populated)

    assert find(rows, 2022).matched_share == pytest.approx(200.0 / 3)
    assert find(rows, 2012).matched_share == 100.0
    assert find(rows, 2008).matched_share == 0.0


def test_the_total_share_is_the_ratio_of_the_totals(populated):
    """And not the mean of the years' shares, which would weigh 2012 like 2022."""
    rows = rows_for(populated)
    years = [row for row in rows if not row.is_total]
    total = find(rows, None)

    assert total.matched_share == pytest.approx(100.0 * 3 / 6)
    mean_of_shares = sum(row.matched_share for row in years) / len(years)
    assert total.matched_share != pytest.approx(mean_of_shares)


def test_an_unbound_fire_is_still_a_fire(populated):
    """The matches are a column and not a filter: 2008 is bound to nothing at all."""
    year_2008 = find(rows_for(populated), 2008)

    assert year_2008.matched == 0
    assert year_2008.fires == 2
    assert year_2008.total == pytest.approx(
        expected("2008410097") + expected("2008410098"), rel=1e-6)


def test_a_year_the_egif_exports_do_not_reach_matches_nothing(unreached):
    """2024 and 2025 on the real archive: 133 perimeters and no campaign behind them."""
    year = find(rows_for(unreached), UNREACHED_YEAR)

    assert year.fires == 1
    assert year.matched == 0
    assert year.matched_share == 0.0


def test_a_confidence_threshold_keeps_only_the_stronger_bindings(populated):
    """2022's two bindings are one identifier match and one name match."""
    rows = rows_for(populated, min_confidence=app.IDENTIFIER_CONFIDENCE)

    assert find(rows, 2022).matched == 1
    assert find(rows, 2012).matched == 1
    assert find(rows, None).matched == 2


def test_a_zero_confidence_counts_every_binding(populated):
    """Falsy, and so exactly what a truthiness test would get wrong."""
    assert [row.matched for row in rows_for(populated, min_confidence=0.0)] == \
           [row.matched for row in rows_for(populated)]


def test_a_confidence_threshold_changes_no_area(populated):
    """It selects what counts as matched, not what counts as a fire."""
    for strict, every in zip(rows_for(populated, min_confidence=1.0), rows_for(populated)):
        assert (strict.year, strict.fires) == (every.year, every.fires)
        assert strict.total == pytest.approx(every.total)


def test_the_matches_follow_the_minimum_area(populated):
    """Counted over the same rows, so the share always has Fires as its denominator."""
    rows = rows_for(populated, min_area=halfway("2022040093", "2022040091"))
    year_2022 = find(rows, 2022)

    assert year_2022.fires == 2
    assert year_2022.matched == 2
    assert year_2022.matched_share == 100.0


def test_the_matches_follow_the_surface(populated, provider_ids):
    """A fire dropped for not reporting the surface takes its binding with it."""
    add_fire(populated, provider_ids, "2022040094", 2022, MATCH_CODE,
             box(-2.0, 37.0, -1.99, 37.01), (None, 1.0, 1.0))
    populated.commit()

    assert find(rows_for(populated, surface=app.SURFACE_SCRUB), 2022).matched == 3
    assert find(rows_for(populated, surface=app.SURFACE_WOODED), 2022).matched == 2


def test_a_report_with_no_bindings_at_all_warns(db_session, provider_ids, caplog):
    """A column of zeros is what an unrun binding looks like, and what no match does."""
    add_fire(db_session, provider_ids, "2008410099", 2008, None,
             box(-6.0, 37.0, -5.9, 37.1), (1.0, 1.0, 1.0))
    db_session.commit()

    with caplog.at_level(logging.WARNING):
        rows = rows_for(db_session)

    assert find(rows, None).matched == 0
    assert "bind_egif_wildfires" in caplog.text


def test_a_report_with_bindings_does_not_warn(populated, caplog):
    with caplog.at_level(logging.WARNING):
        rows_for(populated)

    assert "bind_egif_wildfires" not in caplog.text


def test_a_share_of_nothing_is_no_answer_rather_than_zero():
    assert app.share(0, 0) is None
    assert app.share_label(0, 0) == ""
    assert app.share_label(1, 4) == "25.00"


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_asked_for_columns(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        table = list(csv.reader(handle))

    assert table[0] == list(app.COLUMNS)
    assert [line[1] for line in table[1:]] == ["2022", "2012", "2008", "Total"]
    assert {line[0] for line in table[1:]} == {"Spain"}


def test_the_csv_numbers_are_machine_readable(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for column in app.COLUMNS[app.FIRST_NUMERIC_COLUMN:]:
            assert "," not in row[column]
            float(row[column])


def test_the_csv_reports_the_matches_per_year(populated, tmp_path):
    target = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    with target.open(encoding="utf-8") as handle:
        rows = {line["Year"]: line for line in csv.DictReader(handle)}

    assert rows["2022"]["EGIF matched"] == "2"
    assert rows["2008"]["EGIF matched"] == "0"
    assert rows["2008"]["EGIF matched (%)"] == "0.00"
    assert rows["Total"]["EGIF matched"] == "3"
    assert rows["Total"]["EGIF matched (%)"] == "50.00"


def test_the_docx_is_a_word_table_with_every_row(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    assert len(table.rows) == len(computed) + 1
    assert [cell.text for cell in table.rows[0].cells] == list(app.COLUMNS)


def test_the_docx_total_row_is_bold(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    computed = rows_for(populated)
    app.write_docx(computed, target, None, logger)

    table = docx.Document(str(target)).tables[0]
    for row, written in zip(computed, table.rows[1:]):
        bold = [run.bold for cell in written.cells for run in cell.paragraphs[0].runs]
        assert all(value is row.is_total for value in bold), row.year_label


def test_the_docx_names_the_region_and_the_scope(populated, tmp_path):
    """A REDIAM report must not be mistakable for the Spanish one it sits beside."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, year=2022), target, 2022, logger)

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    prose = "\n".join(p.text for p in document.paragraphs)
    assert any(app.REGION_NAME in heading for heading in headings)
    assert "2022" in prose and "hectares" in prose
    assert "not a Spanish total" in prose
    assert "EGIF matched" in prose


def test_the_docx_says_which_kind_of_hectare_it_is_of(populated, tmp_path):
    """A table of published hectares and a table of measured ones look exactly alike."""
    docx = pytest.importorskip("docx")
    measured_file, published_file = tmp_path / "m.docx", tmp_path / "p.docx"
    app.write_docx(rows_for(populated), measured_file, None, logger)
    app.write_docx(rows_for(populated, surface=app.SURFACE_PUBLISHED), published_file,
                   None, logger, surface=app.SURFACE_PUBLISHED)

    measured = "\n".join(p.text for p in docx.Document(str(measured_file)).paragraphs)
    reported = "\n".join(p.text for p in docx.Document(str(published_file)).paragraphs)
    assert "the area of the published perimeter" in measured
    assert "geodesically" in measured
    assert "wooded plus scrub plus grassland" in reported
    assert "not measured from the perimeter" in reported
    # And both warn that the two kinds of number are not interchangeable.
    for prose in (measured, reported):
        assert "must not be added" in prose


def test_the_docx_names_the_thresholds(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, min_area=5.0, min_confidence=0.9), target, None,
                   logger, min_area=5.0, min_confidence=0.9)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "5 ha or more" in prose
    assert "confidence 0.9 or more" in prose


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "b.csv"),
                                "--docx", str(tmp_path / "b.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "b.csv").exists()
    assert (tmp_path / "b.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2022" / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()


# --------------------------------------------------------------------------
# One statement
# --------------------------------------------------------------------------

def test_the_whole_report_is_one_statement(populated, monkeypatch):
    """907 fires and no boundary test: none of the per-year machinery is needed."""
    built = []
    original = app.statistics_query

    def spy(*arguments, **keywords):
        built.append(arguments)
        return original(*arguments, **keywords)

    monkeypatch.setattr(app, "statistics_query", spy)
    rows_for(populated)

    assert len(built) == 1


def test_the_total_row_is_combined_from_the_years_measured(populated):
    """The summary row comes from no statement of its own: it is arithmetic."""
    rows = rows_for(populated)
    years = [row for row in rows if not row.is_total]

    assert find(rows, None) == app.combine(years)


def test_the_report_reads_and_writes_nothing(populated):
    """It is a statistics application: the bindings it counts are not its to touch."""
    before = populated.scalar(
        select(RediamWildfire.matched_at).where(RediamWildfire.code == "2022040091"))
    rows_for(populated)
    populated.expire_all()

    assert populated.scalar(
        select(RediamWildfire.matched_at)
        .where(RediamWildfire.code == "2022040091")) == before
    assert populated.scalar(select(RediamWildfire.egif_wildfire_id)
                            .where(RediamWildfire.code == "2008410097")) is None
