#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the DARPA burnt-area statistics application.

The fires here are inserted through the ORM rather than imported from a shapefile:
what has to be asserted is arithmetic over known areas in known years, and building
that by hand is both quicker and clearer than arranging for an importer to produce
it.

The absolute areas are checked against :mod:`pyproj`, which computes the same
geodesic area through PROJ rather than through PostGIS. Two independent
implementations agreeing is worth considerably more than a magic number copied out of
whatever the code returned the first time it ran.

The DARPA fixture carries the one thing no other statistics fixture does, because it
is the one thing this report has that they do not: **bindings to EGIF *partes***, of
two different strengths, and a year with none at all — which on the real archive is
2023 and 2024, the years the EGIF exports do not reach.
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

from src.apps.statistics.wildfires.catalonia_darpa import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import catalonia_darpa
from src.providers import spain_egif
from src.providers.catalonia_darpa.wildfire import MATCH_CODE
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.catalonia_darpa.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.catalonia_darpa.wildfire import DarpaWildfire
from src.providers.spain_egif.wildfire import EgifWildfire

logger = logging.getLogger("test-darpa-statistics")

GEOD = Geod(ellps="WGS84")

UTC = datetime.timezone.utc

#: (code, year, match method, perimeter). Sizes are deliberately unequal within a
#: year so a minimum and a maximum are distinguishable from each other and from the
#: total. Every box is somewhere in or around Catalonia, which matters for nothing
#: here — nothing is tested against a boundary — but keeps the fixture readable.
#:
#: The match method is ``None`` for a fire the binding left unbound, ``MATCH_CODE``
#: for one bound on the published identifier and ``MATCH_DATE_PROVINCE_NAME`` for one
#: bound on a date and a municipality name. The three are what ``--min-confidence``
#: has to tell apart.
FIRES = [
    # 2013: three fires of clearly different sizes, two of them bound and one of
    # those on a name rather than on an identifier.
    ("2013080287", 2013, MATCH_CODE, box(1.80, 41.80, 1.90, 41.90)),
    ("2013080288", 2013, MATCH_DATE_PROVINCE_NAME, box(2.00, 41.60, 2.40, 42.00)),
    ("2013080289", 2013, None, box(1.50, 41.50, 1.55, 41.55)),
    # 2012: one bound fire, smaller than every 2013 one.
    ("2012080101", 2012, MATCH_CODE, box(0.80, 41.20, 0.81, 41.21)),
    # 1994: two fires, one of them the largest of the fixture, neither bound — the
    # pre-1997 codes are the ones the cascade has the hardest time with.
    ("894496", 1994, None, box(0.50, 41.00, 1.50, 42.00)),
    ("894497", 1994, None, box(2.60, 42.20, 2.70, 42.30)),
]

#: Where a DARPA year with no EGIF campaign behind it is added: 2024, exactly as on
#: the published data, where the exports stop before it.
UNREACHED_YEAR = 2024


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def expected(code: str) -> float:
    """The area PROJ computes for one fixture fire."""
    for fire_code, _, _, geometry in FIRES:
        if fire_code == code:
            return hectares(geometry)
    raise KeyError(code)


def add_fire(session, provider_ids, code, year, method, geometry,
             fire_date=None) -> DarpaWildfire:
    """One Catalan perimeter, bound to a *parte* of its own where ``method`` says so.

    The *parte* is created here rather than in a fixture of its own because nothing
    in this report reads it: what is under test is the link, not what is on the other
    end of it.
    """
    darpa_id, egif_id = provider_ids
    fire_date = fire_date or datetime.date(year, 7, 15)

    egif_wildfire_id = None
    if method is not None:
        parte = EgifWildfire(
            data_provider_id=egif_id, report_number=f"{year:04d}08{code[-4:]}",
            campaign=year, province_ine_code="08", municipality_name="Bellprat",
            start_date_time=datetime.datetime(fire_date.year, fire_date.month,
                                              fire_date.day, 12, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE)
        session.add(parte)
        session.flush()
        egif_wildfire_id = parte.id

    fire = DarpaWildfire(
        data_provider_id=darpa_id, source_layer=catalonia_darpa.source_layer_name(year),
        code=code, fire_date=fire_date, year=year, municipality_name="Bellprat",
        part_count=1,
        # Local midnight, which is all the dataset ever publishes: there is no time
        # of day anywhere in it.
        start_date_time=datetime.datetime(fire_date.year, fire_date.month,
                                          fire_date.day, tzinfo=UTC),
        time_zone=catalonia_darpa.DEFAULT_TIME_ZONE,
        perimeter=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
        perimeter_etrs89_utm31n=None,
        egif_wildfire_id=egif_wildfire_id,
        match_method=method,
        match_confidence=None if method is None else MATCH_METHOD_CONFIDENCE[method],
        matched_at=None if method is None
        else datetime.datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(fire)
    session.flush()
    return fire


@pytest.fixture
def provider_ids(db_session):
    """The two providers a bound Catalan fire needs: the department and MITECO."""
    darpa = DataProvider(name=catalonia_darpa.PROVIDER_NAME,
                         product=catalonia_darpa.PROVIDER_PRODUCT,
                         full_name=catalonia_darpa.PROVIDER_FULL_NAME,
                         url=catalonia_darpa.PROVIDER_URL)
    egif = DataProvider(name=spain_egif.PROVIDER_NAME,
                        product=spain_egif.PROVIDER_PRODUCT,
                        full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add_all([darpa, egif])
    db_session.commit()
    return darpa.id, egif.id


@pytest.fixture
def populated(db_session, provider_ids):
    """Six Catalan fires across three years, three of them bound to a *parte*."""
    for code, year, method, geometry in FIRES:
        add_fire(db_session, provider_ids, code, year, method, geometry)
    db_session.commit()
    return db_session


@pytest.fixture
def unreached(populated, provider_ids):
    """``populated`` plus a year the EGIF exports do not reach: nothing bound in it."""
    add_fire(populated, provider_ids, "210_24N", UNREACHED_YEAR, None,
             box(1.00, 41.00, 1.05, 41.05))
    populated.commit()
    return populated


def rows_for(session, year=None, method=app.AREA_METHOD_GEODESIC,
             min_area=None, min_confidence=None) -> list[app.Row]:
    return app.compute(session, year, logger, method, min_area, min_confidence)


def halfway(smaller: str, larger: str) -> float:
    """A ``--min-area`` that keeps fire ``larger`` and drops fire ``smaller``.

    Midway between the two rather than equal to either, so that no test turns on
    whether PostGIS and PROJ agree to the last bit on a boundary case. Derived from
    the fixture rather than written as a number of hectares, so that resizing a
    fixture fire cannot quietly turn a threshold into a no-op.

    The fixture's fires sorted by area::

        2012080101      93   2013080289    2,317   894497        9,167
        2013080287   9,224   2013080288  147,695   894496      927,319   ha
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


def test_the_scope_defaults_to_every_year():
    assert app.parse_arguments(["--csv", "out.csv"]).year is None


def test_the_area_method_defaults_to_the_other_reports():
    assert app.parse_arguments(["--csv", "out.csv"]).area_method == app.AREA_METHOD_GEODESIC


def test_there_is_no_country_option(capsys):
    """The department publishes Catalonia's fires, so there is nothing to select."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Spain"])

    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_country_source_option(capsys):
    """Asked for and refused, rather than accepted and quietly ignored.

    The shapefiles are the department's own cartography of its own territory: there
    is nothing for a containment test to find, and a report that accepted the option
    would be claiming it had done one.
    """
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "geometry"])

    assert "no --country-source here" in capsys.readouterr().err


def test_there_is_no_minimum_area_unless_one_is_asked_for():
    assert app.parse_arguments(["--csv", "out.csv"]).min_area is None


def test_a_minimum_area_is_read_as_hectares():
    assert app.parse_arguments(["--csv", "out.csv", "--min-area", "5"]).min_area == 5.0
    assert app.parse_arguments(["--csv", "out.csv", "--min-area", "0.5"]).min_area == 0.5


@pytest.mark.parametrize("value", ["five", "", "5ha"])
def test_a_minimum_area_that_is_not_a_number_is_refused(value):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-area", value])
    with pytest.raises(argparse.ArgumentTypeError, match="not a number"):
        app.hectares(value)


def test_a_negative_minimum_area_is_refused():
    """A typo that would otherwise pass silently: no area is below zero."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-area", "-5"])
    with pytest.raises(argparse.ArgumentTypeError, match="cannot be negative"):
        app.hectares("-5")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_a_minimum_area_that_is_not_finite_is_refused(value):
    """``float`` accepts all three; none of them is a size a fire can have."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-area", value])
    with pytest.raises(argparse.ArgumentTypeError, match="finite"):
        app.hectares(value)


def test_zero_is_a_threshold_and_not_a_missing_one():
    """Falsy, and so exactly what a truthiness test would get wrong."""
    assert app.parse_arguments(["--csv", "out.csv", "--min-area", "0"]).min_area == 0.0


def test_every_binding_counts_unless_a_confidence_is_asked_for():
    assert app.parse_arguments(["--csv", "out.csv"]).min_confidence is None


def test_a_confidence_is_read_as_a_number():
    parsed = app.parse_arguments(["--csv", "out.csv", "--min-confidence", "0.9"])
    assert parsed.min_confidence == 0.9


@pytest.mark.parametrize("value", ["0", "1"])
def test_both_ends_of_the_confidence_range_are_accepted(value):
    """``0`` is the default said out loud; ``1`` is the exact-identifier matches."""
    assert app.parse_arguments(
        ["--csv", "out.csv", "--min-confidence", value]).min_confidence == float(value)


@pytest.mark.parametrize("value", ["90", "-0.1", "1.5"])
def test_a_confidence_outside_the_range_is_refused(value):
    """``90`` means ninety percent, and would otherwise count nothing in silence."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-confidence", value])
    with pytest.raises(argparse.ArgumentTypeError, match="between 0 and 1"):
        app.confidence(value)


@pytest.mark.parametrize("value", ["high", "", "nan"])
def test_a_confidence_that_is_not_a_finite_number_is_refused(value):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--min-confidence", value])
    with pytest.raises(argparse.ArgumentTypeError):
        app.confidence(value)


def test_the_shared_columns_match_the_other_reports():
    """So the CSVs can still be concatenated on the six columns they have in common."""
    from src.apps.statistics.wildfires.gfa import wildfire_statistics as gfa_app
    from src.apps.statistics.wildfires.gwis import wildfire_statistics as gwis_app
    from src.apps.statistics.wildfires.portugal_icnf import wildfire_statistics as icnf_app
    from src.apps.statistics.wildfires.spain_egif import wildfire_statistics as egif_app

    assert app.SHARED_COLUMNS == gfa_app.COLUMNS == gwis_app.COLUMNS == \
           icnf_app.COLUMNS == egif_app.COLUMNS
    assert app.COLUMNS[:len(app.SHARED_COLUMNS)] == app.SHARED_COLUMNS


# --------------------------------------------------------------------------
# The statistics themselves
# --------------------------------------------------------------------------

def test_the_area_matches_an_independent_geodesic_computation(populated):
    """PostGIS on the ellipsoid against PROJ on the ellipsoid: two implementations."""
    year_2013 = find(rows_for(populated), 2013)

    assert year_2013.maximum == pytest.approx(expected("2013080288"), rel=1e-6)
    assert year_2013.minimum == pytest.approx(expected("2013080289"), rel=1e-6)
    assert year_2013.total == pytest.approx(
        expected("2013080287") + expected("2013080288") + expected("2013080289"), rel=1e-6)


def test_the_areas_are_in_hectares(populated):
    """An order-of-magnitude check, to catch a missing or doubled unit conversion.

    ``894496`` is a one-degree square at 41-42°N. A degree of latitude is about
    111 km; a degree of longitude there is 111 km x cos(41.5°), about 83 km. So
    roughly 111 x 83 = 9,200 km², which is ~920,000 ha — not 92 (m² mistaken for ha)
    and not 9.2e9 (m² left unconverted).
    """
    assert 850_000 < find(rows_for(populated), 1994).maximum < 1_000_000


def test_each_year_gets_a_row_newest_first_with_the_total_last(populated):
    assert [(row.country, row.year_label) for row in rows_for(populated)] == [
        ("Spain", "2013"), ("Spain", "2012"), ("Spain", "1994"), ("Spain", "Total"),
    ]


def test_the_country_is_a_constant_and_nothing_is_tested_against_a_boundary(populated):
    """No OCHA boundary is imported by the fixture, and the report does not want one."""
    assert {row.country for row in rows_for(populated)} == {app.COUNTRY_NAME}


def test_the_total_row_summarises_every_year(populated):
    """Fires, hectares and matches are sums; the minimum and maximum are not."""
    rows = rows_for(populated)
    total = find(rows, None)
    years = [find(rows, year) for year in (2013, 2012, 1994)]

    assert total.fires == sum(row.fires for row in years) == len(FIRES)
    assert total.matched == sum(row.matched for row in years)
    assert total.total == pytest.approx(sum(row.total for row in years))
    assert total.minimum == pytest.approx(min(row.minimum for row in years))
    assert total.maximum == pytest.approx(max(row.maximum for row in years))
    # The two ends come from different years, which a per-year total could not give.
    assert total.minimum == pytest.approx(expected("2012080101"), rel=1e-6)
    assert total.maximum == pytest.approx(expected("894496"), rel=1e-6)


def test_each_row_counts_its_own_fires(populated):
    rows = rows_for(populated)
    assert find(rows, 2013).fires == 3
    assert find(rows, 2012).fires == 1
    assert find(rows, 1994).fires == 2


# --------------------------------------------------------------------------
# The year: published, not derived
# --------------------------------------------------------------------------

def test_the_published_year_is_used_even_when_the_date_disagrees(populated, provider_ids):
    """A fire filed in one layer whose date falls in another follows the layer.

    The import checks that the two agree and they do on all 4,533 published
    features, so this is a fire the archive does not contain — which is exactly why
    it is worth asserting that the report reads the column it says it reads.
    """
    add_fire(populated, provider_ids, "straddler", 2011, None,
             box(1.20, 41.20, 1.25, 41.25),
             fire_date=datetime.date(2010, 12, 31))
    populated.commit()

    rows = rows_for(populated)
    assert find(rows, 2011).fires == 1
    assert 2010 not in {row.year for row in rows}


def test_a_single_year_can_be_selected(populated):
    rows = rows_for(populated, year=1994)
    assert [row.year_label for row in rows] == ["1994", "Total"]
    assert rows[0].total == pytest.approx(rows[1].total)


def test_a_year_with_no_fires_yields_nothing(populated):
    assert rows_for(populated, year=1999) == []


def test_an_empty_report_is_an_error(populated, tmp_path):
    args = app.parse_arguments(["--year", "1999", "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="No wildfires matched"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


# --------------------------------------------------------------------------
# How the area is measured
# --------------------------------------------------------------------------

def test_the_two_area_methods_agree(populated):
    geodesic = rows_for(populated, method=app.AREA_METHOD_GEODESIC)
    projected = rows_for(populated, method=app.AREA_METHOD_EQUAL_AREA)

    for measured, transformed in zip(geodesic, projected):
        assert (measured.country, measured.year) == (transformed.country, transformed.year)
        for figure in ("minimum", "maximum", "total"):
            assert getattr(transformed, figure) == pytest.approx(
                getattr(measured, figure), rel=1e-3), f"{measured.year} {figure}"


def test_an_unknown_area_method_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--area-method", "utm31n"])
    with pytest.raises(ValueError, match="unknown area method"):
        app.burnt_area("utm31n")


def test_the_published_grid_is_not_offered():
    """EPSG:25831 is what the department measures on, and it is conformal.

    A tenth of a percent across Catalonia, and it varies with longitude — positive in
    the west, negative near the central meridian — so it does not cancel over a year
    whose fires are not evenly spread. Asserted here so the omission stays deliberate.
    """
    assert catalonia_darpa.SOURCE_SRID == 25831
    assert str(catalonia_darpa.SOURCE_SRID) not in " ".join(app.AREA_METHODS)
    assert app.EQUAL_AREA_SRID != catalonia_darpa.SOURCE_SRID


# --------------------------------------------------------------------------
# The minimum burnt area
# --------------------------------------------------------------------------

def test_no_minimum_area_counts_every_fire(populated):
    """The default has to leave the report exactly as it was."""
    assert rows_for(populated, min_area=None) == rows_for(populated)


def test_the_smaller_fires_stop_being_counted(populated):
    """2013 has fires of 2,317, 9,224 and 147,695 ha; keep the largest two."""
    rows = rows_for(populated, min_area=halfway("2013080289", "2013080287"))
    year_2013 = find(rows, 2013)

    assert year_2013.fires == 2
    assert year_2013.minimum == pytest.approx(expected("2013080287"), rel=1e-6)
    assert year_2013.maximum == pytest.approx(expected("2013080288"), rel=1e-6)
    assert year_2013.total == pytest.approx(
        expected("2013080287") + expected("2013080288"), rel=1e-6)


def test_a_year_whose_fires_are_all_too_small_drops_out(populated):
    """2012 holds one fire of 93 ha and nothing else, so the year goes with it.

    Not a zero row: a year the threshold emptied has no minimum and no maximum to
    report, and printing 0.00 for them would be a claim about a fire that was not
    counted.
    """
    rows = rows_for(populated, min_area=halfway("2012080101", "2013080289"))

    assert 2012 not in {row.year for row in rows}
    assert [row.year_label for row in rows] == ["2013", "1994", "Total"]
    assert find(rows, 2013).fires == 3
    assert find(rows, 1994).fires == 2


def test_the_total_row_summarises_only_the_fires_counted(populated):
    """The summary is arithmetic over what was measured, so it follows the threshold."""
    threshold = halfway("2012080101", "2013080289")
    rows = rows_for(populated, min_area=threshold)
    total = find(rows, None)

    assert total.fires == len(FIRES) - 1
    assert total.minimum > threshold
    assert total.minimum == pytest.approx(expected("2013080289"), rel=1e-6)
    assert total.maximum == pytest.approx(expected("894496"), rel=1e-6)
    assert total.total == pytest.approx(
        sum(expected(code) for code, *_ in FIRES) - expected("2012080101"), rel=1e-6)


def test_a_threshold_above_every_fire_reports_nothing(populated):
    assert rows_for(populated, min_area=expected("894496") * 2) == []


def test_an_empty_report_names_the_threshold(populated, tmp_path):
    """Because then the threshold is at least as likely to be the reason as the data."""
    args = app.parse_arguments(["--min-area", "100000000",
                                "--csv", str(tmp_path / "out.csv")])

    with pytest.raises(RuntimeError, match="--min-area"):
        app.report(args, populated.get_bind(), logger)
    assert not (tmp_path / "out.csv").exists()


def test_the_threshold_is_not_a_filter_on_the_totals(populated):
    """A HAVING would have dropped years, not fires.

    1994 holds a 9,167 ha fire and a 927,319 ha one. A threshold between them must
    leave the year with one fire, not remove the year for having had a small one —
    nor keep both for having a large total.
    """
    year_1994 = find(rows_for(populated, min_area=halfway("894497", "894496")), 1994)

    assert year_1994.fires == 1
    assert year_1994.total == pytest.approx(expected("894496"), rel=1e-6)
    assert year_1994.minimum == pytest.approx(year_1994.maximum)


def test_the_threshold_and_a_single_year_combine(populated):
    rows = rows_for(populated, year=2013, min_area=halfway("2013080289", "2013080287"))

    assert [row.year_label for row in rows] == ["2013", "Total"]
    assert rows[0].fires == 2


# --------------------------------------------------------------------------
# How many matched the EGIF data
# --------------------------------------------------------------------------

def test_each_year_reports_how_many_of_its_fires_are_bound(populated):
    rows = rows_for(populated)

    assert find(rows, 2013).matched == 2
    assert find(rows, 2012).matched == 1
    assert find(rows, 1994).matched == 0
    assert find(rows, None).matched == 3


def test_the_share_is_of_the_fires_counted_beside_it(populated):
    rows = rows_for(populated)

    assert find(rows, 2013).matched_share == pytest.approx(200.0 / 3)
    assert find(rows, 2012).matched_share == 100.0
    assert find(rows, 1994).matched_share == 0.0


def test_the_total_share_is_the_ratio_of_the_totals(populated):
    """And not the mean of the years' shares, which would weigh 1994 like 2013."""
    rows = rows_for(populated)
    years = [row for row in rows if not row.is_total]
    total = find(rows, None)

    assert total.matched_share == pytest.approx(100.0 * 3 / 6)
    mean_of_shares = sum(row.matched_share for row in years) / len(years)
    assert total.matched_share != pytest.approx(mean_of_shares)


def test_an_unbound_fire_is_still_a_fire(populated):
    """The matches are a column and not a filter: 1994 is bound to nothing at all."""
    year_1994 = find(rows_for(populated), 1994)

    assert year_1994.matched == 0
    assert year_1994.fires == 2
    assert year_1994.total == pytest.approx(
        expected("894496") + expected("894497"), rel=1e-6)


def test_a_year_the_egif_exports_do_not_reach_matches_nothing(unreached):
    """2023 and 2024 on the real archive: 45 perimeters and no campaign behind them."""
    year = find(rows_for(unreached), UNREACHED_YEAR)

    assert year.fires == 1
    assert year.matched == 0
    assert year.matched_share == 0.0


def test_a_confidence_threshold_keeps_only_the_stronger_bindings(populated):
    """2013's two bindings are one identifier match and one name match."""
    rows = rows_for(populated, min_confidence=app.IDENTIFIER_CONFIDENCE)

    assert find(rows, 2013).matched == 1
    assert find(rows, 2012).matched == 1
    assert find(rows, None).matched == 2


def test_the_strictest_threshold_keeps_the_exact_identifier_matches(populated):
    """A confidence of 1 is inclusive: ``MATCH_CODE`` is exactly 1.00 and stays."""
    rows = rows_for(populated, min_confidence=1.0)

    assert MATCH_METHOD_CONFIDENCE[MATCH_CODE] == 1.00
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
    rows = rows_for(populated, min_area=halfway("2013080289", "2013080287"))
    year_2013 = find(rows, 2013)

    assert year_2013.fires == 2
    assert year_2013.matched == 2
    assert year_2013.matched_share == 100.0


def test_the_matches_follow_a_single_year(populated):
    rows = rows_for(populated, year=2012)
    assert [(row.fires, row.matched) for row in rows] == [(1, 1), (1, 1)]


def test_a_report_with_no_bindings_at_all_warns(db_session, provider_ids, caplog):
    """A column of zeros is what an unrun binding looks like, and what no match does."""
    add_fire(db_session, provider_ids, "894498", 1994, None, box(0.5, 41.0, 0.6, 41.1))
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
    """A percentage of nothing is not zero percent, and the writers leave it empty."""
    assert app.share(0, 0) is None
    assert app.share_label(0, 0) == ""
    assert app.share(1, 4) == 25.0
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
    assert [line[1] for line in table[1:]] == ["2013", "2012", "1994", "Total"]
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

    assert rows["2013"]["EGIF matched"] == "2"
    assert rows["1994"]["EGIF matched"] == "0"
    assert rows["1994"]["EGIF matched (%)"] == "0.00"
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
    """A DARPA report must not be mistakable for the Spanish one it sits beside."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, year=2013), target, 2013, logger)

    document = docx.Document(str(target))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    prose = "\n".join(p.text for p in document.paragraphs)
    assert any(app.REGION_NAME in heading for heading in headings)
    assert "2013" in prose and "hectares" in prose
    # The two things a reader must not have to remember are on the page itself.
    assert "not a Spanish total" in prose
    assert "EGIF matched" in prose


def test_the_docx_names_the_minimum_area(populated, tmp_path):
    """A table of the fires over 5 ha and a table of every fire look exactly alike."""
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, min_area=5.0), target, None, logger, min_area=5.0)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "5 ha or more" in prose


def test_the_docx_names_the_confidence_threshold(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, min_confidence=0.9), target, None, logger,
                   min_confidence=0.9)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "confidence 0.9 or more" in prose


def test_the_docx_claims_no_threshold_when_there_is_none(populated, tmp_path):
    docx = pytest.importorskip("docx")
    target = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated), target, None, logger)

    prose = "\n".join(p.text for p in docx.Document(str(target)).paragraphs)
    assert "or more" not in prose
    assert "all years" in prose


def test_both_outputs_are_written_together(populated, tmp_path):
    pytest.importorskip("docx")
    args = app.parse_arguments(["--csv", str(tmp_path / "b.csv"),
                                "--docx", str(tmp_path / "b.docx")])
    app.report(args, populated.get_bind(), logger)

    assert (tmp_path / "b.csv").exists()
    assert (tmp_path / "b.docx").exists()


def test_a_missing_output_directory_is_created(populated, tmp_path):
    target = tmp_path / "reports" / "2013" / "burnt.csv"
    app.write_csv(rows_for(populated), target, logger)

    assert target.exists()


# --------------------------------------------------------------------------
# One statement
# --------------------------------------------------------------------------

def test_the_whole_report_is_one_statement(populated, monkeypatch):
    """860 fires and no boundary test: none of the per-year machinery is needed."""
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
        select(DarpaWildfire.matched_at).where(DarpaWildfire.code == "2013080287"))
    rows_for(populated)
    populated.expire_all()

    assert populated.scalar(
        select(DarpaWildfire.matched_at).where(DarpaWildfire.code == "2013080287")) == before
    assert populated.scalar(select(DarpaWildfire.egif_wildfire_id)
                            .where(DarpaWildfire.code == "894496")) is None
