#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAFOR burnt-area statistics application.

The fires here are inserted through the ORM rather than imported from a
shapefile: what has to be asserted is arithmetic over known areas in known years,
and building that by hand is both quicker and clearer than arranging for an
importer to produce it.

The absolute areas are checked against :mod:`pyproj`, which computes the same
geodesic area through PROJ rather than through PostGIS. Two independent
implementations agreeing is worth considerably more than a magic number copied out
of whatever the code returned the first time it ran.

The CONAFOR fixture carries three things no other report's does, because they are
the three facts this one has to get right: **no boundaries at all** (this report
runs no containment test and must work without them), a fire with a **polygon and
no published area** and one with a **published area and no polygon** (the two
methods count different fires, on purpose), and a 2010 fire whose published area
and polygon disagree by a factor of three, which is what the real 2010 layer is
like.
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

from src.apps.statistics.wildfires.mexico_conafor import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import mexico_conafor
from src.providers.mexico_conafor.wildfire import ConaforWildfire

logger = logging.getLogger("test-conafor-statistics")

GEOD = Geod(ellps="WGS84")

UTC = datetime.timezone.utc

#: ``(fire_code, year, perimeter, published_area)``.
#:
#: Sizes are deliberately unequal within a year so a minimum and a maximum are
#: distinguishable from each other and from the total. ``published_area`` is
#: ``None`` where the fixture means "CONAFOR published no AREA_HA", and a number
#: where it means "CONAFOR published this"; a number that is not the polygon's own
#: area is how the 2010 disagreement is reproduced.
FIRES = [
    # 2023: three fires of clearly different sizes, published areas agreeing with
    # their polygons as they do from 2016 on.
    ("23-01-0001", 2023, box(-102.3, 21.8, -102.2, 21.9), None),
    ("23-14-0002", 2023, box(-103.5, 20.0, -103.1, 20.4), None),
    ("23-20-0003", 2023, box(-96.8, 17.5, -96.6, 17.7), None),
    # 2019: one fire, smaller than every 2023 one.
    ("19-01-0001", 2019, box(-102.3, 21.0, -102.25, 21.05), None),
    # 2010: two fires whose published areas do not describe their polygons at all.
    # The real layer's median ratio is 3.0 and its 90th percentile 65, so a third
    # and a hundredfold are both inside what that year actually looks like. They
    # are chosen in opposite directions and on opposite sizes so that the two
    # methods disagree about which of the two fires was the larger.
    ("10-08-0001", 2010, box(-106.2, 28.5, -105.2, 29.5), "third"),
    ("10-09-0002", 2010, box(-99.2, 19.3, -99.1, 19.4), "hundredfold"),
]

#: The 2012 fire that publishes attributes and an empty shape. Nine of the real
#: layer's 224 features are like this. It has an area and no polygon, so it counts
#: under ``reported`` and under neither measured method.
SHAPELESS = ("12-14-0001", 2012, 2.0)

#: The shape of ``21-24-0078``: a polygon and no published area. It counts under
#: the measured methods and not under ``reported`` — the mirror image of the one
#: above, and the reason the two ``Fires`` columns differ.
AREALESS = ("21-24-0078", 2021, box(-101.0, 22.1, -100.9, 22.2))


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def published(geometry, rule) -> float:
    """The ``AREA_HA`` a fixture fire publishes, given its polygon and its rule."""
    measured = hectares(geometry)
    if rule is None:
        return measured
    if rule == "third":
        return measured / 3.0
    if rule == "hundredfold":
        return measured * 100.0
    raise ValueError(rule)


def expected(fire_code: str) -> float:
    """The geodesic area PROJ computes for one fixture fire."""
    for code, _, geometry, _ in FIRES:
        if code == fire_code:
            return hectares(geometry)
    if fire_code == AREALESS[0]:
        return hectares(AREALESS[2])
    raise KeyError(fire_code)


def expected_published(fire_code: str) -> float:
    """The ``AREA_HA`` one fixture fire publishes."""
    for code, _, geometry, rule in FIRES:
        if code == fire_code:
            return published(geometry, rule)
    if fire_code == SHAPELESS[0]:
        return SHAPELESS[2]
    raise KeyError(fire_code)


def a_fire(provider_id, fire_code, year, geometry, area_ha) -> ConaforWildfire:
    state_code = int(fire_code.split("-")[1])
    return ConaforWildfire(
        data_provider_id=provider_id,
        fire_code=fire_code, year=year, source_layer=f"incendios_{year}",
        state_code=state_code, state_name="Aguascalientes",
        municipality_name="Aguascalientes",
        date_time_precision=mexico_conafor.PRECISION_DAY,
        start_date_time=datetime.datetime(year, 6, 1, 6, tzinfo=UTC),
        time_zone=mexico_conafor.DEFAULT_TIME_ZONE,
        area_ha=area_ha,
        perimeter=None if geometry is None
                  else f"SRID=4326;{MultiPolygon([geometry]).wkt}",
    )


@pytest.fixture
def populated(db_session):
    """Six consistent Mexican fires across three years, and **no boundaries at all**.

    The absence is the point: this report runs no containment test, so it has to
    work against a database in which the OCHA boundaries were never imported. Every
    fire here has ``admin_boundary_id`` ``NULL``.
    """
    provider = DataProvider(name=mexico_conafor.PROVIDER_NAME,
                            product=mexico_conafor.PROVIDER_PRODUCT,
                            full_name=mexico_conafor.PROVIDER_FULL_NAME,
                            url=mexico_conafor.PROVIDER_URL)
    db_session.add(provider)
    db_session.flush()

    for code, year, geometry, rule in FIRES:
        db_session.add(a_fire(provider.id, code, year, geometry,
                              published(geometry, rule)))
    db_session.commit()
    return db_session


@pytest.fixture
def with_gaps(populated):
    """``populated`` plus the two fires that only one method can measure."""
    provider_id = populated.scalar(
        select(DataProvider.id).where(DataProvider.name == mexico_conafor.PROVIDER_NAME))
    code, year, area = SHAPELESS
    populated.add(a_fire(provider_id, code, year, None, area))
    code, year, geometry = AREALESS
    populated.add(a_fire(provider_id, code, year, geometry, None))
    populated.commit()
    return populated


def rows_for(session, year=None, method=app.AREA_METHOD_GEODESIC,
             min_area=None) -> list[app.Row]:
    return app.compute(session, year, logger, method, min_area)


def find(rows: list[app.Row], year: int | None) -> app.Row:
    matches = [row for row in rows if row.year == year]
    assert len(matches) == 1, f"expected one row for {year}, got {len(matches)}"
    return matches[0]


def halfway(smaller: str, larger: str) -> float:
    """A ``--min-area`` that keeps fire ``larger`` and drops fire ``smaller``."""
    return (expected(smaller) + expected(larger)) / 2


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


def test_the_default_area_method_matches_the_other_reports():
    assert app.parse_arguments(["--csv", "out.csv"]).area_method == app.AREA_METHOD_GEODESIC


def test_there_is_no_country_option(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country", "Mexico"])
    assert "no --country here" in capsys.readouterr().err


def test_there_is_no_country_source_option(capsys):
    """Every CONAFOR perimeter is inside Mexico, so there is nothing to test.

    Refused with a message that says so, rather than argparse reporting an
    unrecognised argument — which is what anyone copying an ICNF command line
    would otherwise see.
    """
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--country-source", "geometry"])
    assert "no --country-source here" in capsys.readouterr().err


def test_the_reported_area_is_offered_as_a_method():
    """The only report in the project that does not have to measure anything."""
    assert app.AREA_METHOD_REPORTED in app.AREA_METHODS
    parsed = app.parse_arguments(["--csv", "out.csv", "--area-method", "reported"])
    assert parsed.area_method == app.AREA_METHOD_REPORTED


def test_an_unknown_area_method_is_refused():
    with pytest.raises(SystemExit):
        app.parse_arguments(["--csv", "out.csv", "--area-method", "epsg6362"])


@pytest.mark.parametrize("value", ["five", "", "5ha"])
def test_a_minimum_area_that_is_not_a_number_is_refused(value):
    with pytest.raises(argparse.ArgumentTypeError, match="not a number"):
        app.hectares(value)


def test_a_negative_minimum_area_is_refused():
    with pytest.raises(argparse.ArgumentTypeError, match="cannot be negative"):
        app.hectares("-5")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_a_minimum_area_that_is_not_finite_is_refused(value):
    with pytest.raises(argparse.ArgumentTypeError, match="finite"):
        app.hectares(value)


# --------------------------------------------------------------------------
# The years
# --------------------------------------------------------------------------

def test_only_the_years_with_fires_are_reported(populated):
    """DISTINCT and not a range: a year with no imported fires is a gap, not a zero.

    The fixture jumps 2010 to 2019 to 2023, and the report must not invent the
    years in between — a row reading zero would say nothing burnt in Mexico that
    year, when what it means is that the archive was not imported.
    """
    rows = rows_for(populated)
    assert [row.year for row in rows] == [2023, 2019, 2010, None]


def test_a_year_with_no_imported_fires_finds_nothing(populated):
    assert rows_for(populated, year=2015) == []


def test_one_year_may_be_asked_for(populated):
    rows = rows_for(populated, year=2023)
    assert [row.year for row in rows] == [2023, None]
    assert find(rows, 2023).fires == 3


# --------------------------------------------------------------------------
# No boundaries, no country test
# --------------------------------------------------------------------------

def test_the_report_works_with_no_boundaries_imported(populated):
    """Nothing here has an admin_boundary_id, and every fire is still counted."""
    rows = rows_for(populated)
    assert find(rows, None).fires == len(FIRES)


def test_every_row_is_reported_under_mexico(populated):
    rows = rows_for(populated)
    assert {row.country for row in rows} == {app.COUNTRY_NAME} == {"Mexico"}


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

def test_the_geodesic_areas_agree_with_proj(populated):
    """PostGIS and PROJ, two implementations of the same geodesic measurement."""
    row = find(rows_for(populated), 2023)
    assert row.minimum == pytest.approx(expected("23-01-0001"), rel=1e-9)
    assert row.maximum == pytest.approx(expected("23-14-0002"), rel=1e-9)
    assert row.total == pytest.approx(
        sum(expected(code) for code in ("23-01-0001", "23-14-0002", "23-20-0003")),
        rel=1e-9)


def test_the_total_row_is_over_every_year(populated):
    rows = rows_for(populated)
    total = find(rows, None)
    assert total.fires == len(FIRES)
    assert total.total == pytest.approx(
        sum(hectares(geometry) for _, _, geometry, _ in FIRES), rel=1e-9)
    assert total.minimum == min(find(rows, year).minimum for year in (2023, 2019, 2010))
    assert total.maximum == max(find(rows, year).maximum for year in (2023, 2019, 2010))


def test_the_equal_area_projection_agrees_with_the_geodesic_one(populated):
    """They differ by thousandths of a percent, which is the documented claim."""
    geodesic = find(rows_for(populated, method=app.AREA_METHOD_GEODESIC), None)
    projected = find(rows_for(populated, method=app.AREA_METHOD_EQUAL_AREA), None)
    assert projected.total == pytest.approx(geodesic.total, rel=1e-3)
    assert projected.fires == geodesic.fires


# --------------------------------------------------------------------------
# The reported area, which is what makes this report different
# --------------------------------------------------------------------------

def test_the_reported_method_uses_the_published_figure_untouched(populated):
    row = find(rows_for(populated, year=2023, method=app.AREA_METHOD_REPORTED), 2023)
    assert row.total == pytest.approx(
        sum(expected_published(code)
            for code in ("23-01-0001", "23-14-0002", "23-20-0003")), rel=1e-9)


def test_from_2016_the_published_figure_and_the_polygon_agree(populated):
    """The real archive agrees to three decimals from 2016; the fixture exactly."""
    measured = find(rows_for(populated, year=2023), 2023)
    reported = find(rows_for(populated, year=2023, method=app.AREA_METHOD_REPORTED), 2023)
    assert reported.total == pytest.approx(measured.total, rel=1e-9)


def test_in_2010_the_published_figure_and_the_polygon_do_not_agree(populated):
    """The whole reason --area-method reported exists, made into a number.

    The real 2010 layer's median ratio is 3.0 and its 90th percentile 65. Running
    the report both ways is how that stops being a claim in a docstring.
    """
    measured = find(rows_for(populated, year=2010), 2010)
    reported = find(rows_for(populated, year=2010, method=app.AREA_METHOD_REPORTED), 2010)
    assert reported.total != pytest.approx(measured.total, rel=0.01)
    # 10-08-0001 publishes a third of its polygon and 10-09-0002 a hundred times
    # its own, and the second is by far the smaller polygon — so the two methods
    # disagree about which fire of 2010 was the largest. Under the polygons it is
    # the big one; under the published figures it is the small one.
    assert measured.maximum == pytest.approx(expected("10-08-0001"), rel=1e-9)
    assert reported.maximum == pytest.approx(expected_published("10-09-0002"), rel=1e-9)


# --------------------------------------------------------------------------
# The two methods count different fires, on purpose
# --------------------------------------------------------------------------

def test_a_fire_with_no_polygon_is_counted_only_by_the_reported_method(with_gaps):
    """Nine 2012 features publish attributes and an empty shape."""
    measured = rows_for(with_gaps, year=2012)
    reported = rows_for(with_gaps, year=2012, method=app.AREA_METHOD_REPORTED)
    assert measured == []
    assert find(reported, 2012).fires == 1
    assert find(reported, 2012).total == pytest.approx(SHAPELESS[2])


def test_a_fire_with_no_published_area_is_counted_only_by_a_measured_method(with_gaps):
    """21-24-0078 publishes everything but AREA_HA."""
    measured = rows_for(with_gaps, year=2021)
    reported = rows_for(with_gaps, year=2021, method=app.AREA_METHOD_REPORTED)
    assert find(measured, 2021).fires == 1
    assert find(measured, 2021).total == pytest.approx(expected(AREALESS[0]), rel=1e-9)
    assert reported == []


def test_the_two_methods_report_different_fire_counts(with_gaps):
    """Stated in the docstring rather than engineered away; asserted here."""
    measured = find(rows_for(with_gaps), None)
    reported = find(rows_for(with_gaps, method=app.AREA_METHOD_REPORTED), None)
    assert measured.fires == len(FIRES) + 1     # + the one with no published area
    assert reported.fires == len(FIRES) + 1     # + the one with no polygon
    assert {row.year for row in rows_for(with_gaps) if not row.is_total} != {
        row.year for row in rows_for(with_gaps, method=app.AREA_METHOD_REPORTED)
        if not row.is_total}


# --------------------------------------------------------------------------
# --min-area
# --------------------------------------------------------------------------

def test_a_minimum_area_drops_the_smaller_fires(populated):
    threshold = halfway("23-01-0001", "23-20-0003")
    row = find(rows_for(populated, year=2023, min_area=threshold), 2023)
    assert row.fires == 2
    assert row.minimum == pytest.approx(expected("23-20-0003"), rel=1e-9)


def test_a_minimum_area_that_excludes_a_whole_year_drops_the_year(populated):
    """The year is measured and returns nothing, rather than being predicted away."""
    threshold = halfway("19-01-0001", "23-01-0001")
    rows = rows_for(populated, min_area=threshold)
    assert 2019 not in {row.year for row in rows}
    assert 2023 in {row.year for row in rows}


def test_a_minimum_area_applies_to_the_method_in_use(populated):
    """The threshold selects the fires the figures beside it are computed from."""
    threshold = expected("10-09-0002") * 5
    measured = rows_for(populated, year=2010, min_area=threshold)
    reported = rows_for(populated, year=2010, method=app.AREA_METHOD_REPORTED,
                        min_area=threshold)
    # Under the polygons only the big fire clears it; under the published figures
    # the small fire's tenfold claim clears it too.
    assert find(measured, 2010).fires == 1
    assert find(reported, 2010).fires == 2


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def test_the_csv_has_the_same_columns_as_the_other_reports(populated, tmp_path):
    path = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), path, logger)

    with path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))
    assert tuple(written[0]) == app.COLUMNS
    assert written[0] == ["Country", "Year", "Fires",
                          "Minimum (ha)", "Maximum (ha)", "Total (ha)"]


def test_the_csv_writes_a_total_row_last(populated, tmp_path):
    path = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), path, logger)

    with path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))
    assert written[-1][1] == app.TOTAL_LABEL
    assert written[-1][2] == str(len(FIRES))


def test_the_csv_numbers_carry_no_thousands_separator(populated, tmp_path):
    """A CSV is read by a program more often than by a person."""
    path = tmp_path / "burnt.csv"
    app.write_csv(rows_for(populated), path, logger)
    assert "," not in path.read_text(encoding="utf-8").split("\n")[1].split(",")[5]


def test_the_docx_is_written(populated, tmp_path):
    pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated), path, None, logger)
    assert path.exists() and path.stat().st_size > 0


def test_the_docx_says_which_method_produced_it(populated, tmp_path):
    """A table of published areas and a table of measured ones look alike."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated, method=app.AREA_METHOD_REPORTED), path, None,
                   logger, method=app.AREA_METHOD_REPORTED)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "as published by CONAFOR" in text
    assert "a year missing from the table is a year not imported" in text
    assert "2010" in text


def test_the_docx_names_the_minimum_area(populated, tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(rows_for(populated), path, None, logger, min_area=5.0)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "5 ha or more" in text
