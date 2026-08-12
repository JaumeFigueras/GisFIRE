#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NBAC burnt-area statistics application.

The fires are inserted through the ORM rather than imported from a shapefile: what has
to be asserted is arithmetic over known areas in known years, and building that by hand
is quicker and clearer than arranging for an importer to produce it.

The measured areas are checked against :mod:`pyproj`, which computes the same geodesic
area through PROJ rather than through PostGIS — two independent implementations
agreeing being worth considerably more than a magic number copied out of whatever the
code returned the first time it ran.

The fixture carries the three things this report has that its Andalusian twin does not:
a **published area beside the perimeter that agrees with it**, which is what
``--surface published`` is for; a **year most of whose fires carry no date**, which is
the shape of the real 1970s and the reason for the ``Dated`` columns; and a
**prescribed burn**, which is the one row a count of wildfires has to leave out.
"""

import argparse
import csv
import datetime
import logging

import pytest

from pyproj import Geod
from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.canada_nbac import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import canada_nbac
from src.providers.canada_nbac.wildfire import NbacWildfire

logger = logging.getLogger("test-nbac-statistics")

UTC = datetime.timezone.utc

GEOD = Geod(ellps="WGS84")

#: (gid, year, perimeter, cause, precision, prescribed).
#:
#: The perimeters are deliberately unequal within a year, so a minimum and a maximum
#: are distinguishable from each other and from the total. They sit at Canadian
#: latitudes because that is where the projection question this report answers bites.
#:
#: 1977 stands for the early archive: two of its three fires carry no date at all.
#: 2023 stands for the recent one, where all but a handful do — and it holds the
#: prescribed burn.
FIRES = [
    # 1977 — one dated fire and two dated only to the year.
    ("1977_1", 1977, box(-114.0, 54.0, -113.9, 54.1), canada_nbac.CAUSE_NATURAL,
     canada_nbac.PRECISION_DAY, False),
    ("1977_2", 1977, box(-113.0, 54.0, -112.6, 54.4), canada_nbac.CAUSE_UNDETERMINED,
     canada_nbac.PRECISION_YEAR, False),
    ("1977_3", 1977, box(-112.0, 54.0, -111.8, 54.2), canada_nbac.CAUSE_UNDETERMINED,
     canada_nbac.PRECISION_YEAR, False),
    # 2021 — a single fire, the largest in the fixture.
    ("2021_1", 2021, box(-120.0, 58.0, -119.0, 59.0), canada_nbac.CAUSE_NATURAL,
     canada_nbac.PRECISION_DAY, False),
    # 2023 — two wildfires and a prescribed burn, which is also the smallest fire.
    ("2023_1", 2023, box(-100.0, 50.0, -99.8, 50.2), canada_nbac.CAUSE_HUMAN,
     canada_nbac.PRECISION_DAY, False),
    ("2023_2", 2023, box(-99.0, 50.0, -98.5, 50.5), canada_nbac.CAUSE_NATURAL,
     canada_nbac.PRECISION_DAY, False),
    ("2023_3", 2023, box(-98.0, 50.0, -97.99, 50.01), canada_nbac.CAUSE_HUMAN,
     canada_nbac.PRECISION_DAY, True),
]

#: How much smaller the fixture's adjusted area is than its mapped one, on the fires
#: an adjustment model was applied to. A single factor rather than a column of its
#: own: what has to be asserted is that ``--surface adjusted`` reports a different
#: number from ``--surface published``, not what the real models do.
ADJUSTMENT = 0.5

#: Which fixture fires carry an adjustment. Everything else copies ``POLY_HA`` into
#: ``ADJ_HA``, which is what the service does on the 49,306 fires no model reached.
ADJUSTED = {"2021_1"}


def hectares(geometry) -> float:
    """Geodesic area of a shapely polygon in hectares, computed by PROJ."""
    area, _ = GEOD.geometry_area_perimeter(geometry)
    return abs(area) / app.SQUARE_METRES_PER_HECTARE


def expected(gid: str) -> float:
    """The area PROJ computes for one fixture fire."""
    for identifier, _, geometry, _, _, _ in FIRES:
        if identifier == gid:
            return hectares(geometry)
    raise KeyError(gid)


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
    """The seven fires above, stored the way the importer stores them.

    ``POLY_HA`` is set to the geodesic area of the same polygon, because that is what
    the real dataset does — the service computes it on an equal-area projection, and
    the two agree to 0.0000005% over the published archive. A fixture that made them
    differ would be testing a dataset that does not exist.
    """
    for index, (gid, year, geometry, cause, precision, prescribed) in enumerate(FIRES):
        polygon = MultiPolygon([geometry])
        area = hectares(geometry)
        source = (canada_nbac.SOURCE_AGENCY if precision == canada_nbac.PRECISION_DAY
                  else canada_nbac.SOURCE_YEAR)
        db_session.add(NbacWildfire(
            data_provider=provider,
            gid=gid, nfireid=index + 1, year=year,
            start_date_time=datetime.datetime(year, 7, 1, tzinfo=UTC),
            time_zone=canada_nbac.DEFAULT_TIME_ZONE,
            perimeter=f"SRID=4326;{polygon.wkt}",
            perimeter_lambert=None,
            part_count=1, crosses_admin=False, admin_name="AB",
            fire_cause=cause, date_source=source, date_time_precision=precision,
            area_ha_polygon=area,
            area_ha_adjusted=area * ADJUSTMENT if gid in ADJUSTED else area,
            area_adjusted=gid in ADJUSTED,
            prescribed=prescribed,
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

def test_the_default_surface_is_the_measured_perimeter(fires):
    """Checked against PROJ, not against a number this code once returned."""
    rows = rows_by_year(run(fires))

    assert rows[2021].fires == 1
    assert rows[2021].total == pytest.approx(expected("2021_1"), rel=1e-9)


def test_a_year_reports_the_smallest_the_largest_and_the_sum(fires):
    rows = rows_by_year(run(fires))
    areas = [expected("1977_1"), expected("1977_2"), expected("1977_3")]

    assert rows[1977].fires == 3
    assert rows[1977].minimum == pytest.approx(min(areas), rel=1e-9)
    assert rows[1977].maximum == pytest.approx(max(areas), rel=1e-9)
    assert rows[1977].total == pytest.approx(sum(areas), rel=1e-9)


def test_the_published_surface_reports_poly_ha(fires):
    """Which for this dataset is the same quantity as the measured one."""
    measured = rows_by_year(run(fires))
    published = rows_by_year(run(fires, surface=app.SURFACE_PUBLISHED))

    for year in (1977, 2021, 2023):
        assert published[year].total == pytest.approx(measured[year].total, rel=1e-9)


def test_the_adjusted_surface_is_a_different_quantity(fires):
    """ADJ_HA is a model output where the flag is set and a copy of POLY_HA where not."""
    published = rows_by_year(run(fires, surface=app.SURFACE_PUBLISHED))
    adjusted = rows_by_year(run(fires, surface=app.SURFACE_ADJUSTED))

    assert adjusted[2021].total == pytest.approx(published[2021].total * ADJUSTMENT)
    assert adjusted[1977].total == pytest.approx(published[1977].total), \
        "no model reached 1977, so its adjusted area is its mapped one"


def test_the_two_area_methods_agree(fires):
    """Geodesic and EPSG:6933 answer the same question; they must not disagree usefully."""
    geodesic = rows_by_year(run(fires))
    equal_area = rows_by_year(run(fires, method=app.AREA_METHOD_EQUAL_AREA))

    for year in (1977, 2021, 2023):
        assert equal_area[year].total == pytest.approx(geodesic[year].total, rel=1e-3)


def test_an_unknown_surface_or_method_is_refused():
    with pytest.raises(ValueError, match="unknown surface"):
        app.burnt_area("lambert")
    with pytest.raises(ValueError, match="unknown area method"):
        app.burnt_area(app.SURFACE_MEASURED, "utm")


def test_the_published_grid_is_not_an_area_method():
    """EPSG:3978 is conformal: measuring there understates the real archive by 4.2%.

    Stated as a test so that adding it as a third method has to be a decision rather
    than an oversight.
    """
    assert app.AREA_METHODS == (app.AREA_METHOD_GEODESIC, app.AREA_METHOD_EQUAL_AREA)
    assert canada_nbac.SOURCE_SRID not in {app.EQUAL_AREA_SRID, 4326}


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
    assert [row.year for row in run(fires)] == [2023, 2021, 1977, None]


def test_the_country_is_canada_on_every_row(fires):
    assert all(row.country == "Canada" for row in run(fires))


# --------------------------------------------------------------------------
# The Dated columns
# --------------------------------------------------------------------------

def test_an_early_year_is_mostly_undated(fires):
    """Not a broken import: the composite reconstructed those years from imagery."""
    rows = rows_by_year(run(fires))

    assert rows[1977].fires == 3
    assert rows[1977].dated == 1
    assert rows[1977].dated_share == pytest.approx(100.0 / 3)


def test_dated_is_a_column_and_not_a_filter(fires):
    """An undated fire still contributes its hectares."""
    rows = rows_by_year(run(fires))
    areas = [expected("1977_1"), expected("1977_2"), expected("1977_3")]

    assert rows[1977].fires == 3, "all three counted"
    assert rows[1977].total == pytest.approx(sum(areas), rel=1e-9)


def test_the_total_share_is_the_ratio_of_the_totals_not_the_mean_of_the_ratios(fires):
    rows = run(fires)
    total = rows[-1]

    assert total.fires == 6, "the prescribed burn is not one of them"
    assert total.dated == 4
    assert total.dated_share == pytest.approx(100.0 * 4 / 6)


def test_dated_is_the_precision_and_not_the_source():
    """The two answer different questions; only one of them is about the date's reality."""
    condition = str(app.is_dated().compile(compile_kwargs={"literal_binds": True}))
    assert "date_time_precision" in condition
    assert canada_nbac.PRECISION_DAY in condition


# --------------------------------------------------------------------------
# Prescribed burns
# --------------------------------------------------------------------------

def test_a_prescribed_burn_is_left_out_by_default(fires):
    rows = rows_by_year(run(fires))

    assert rows[2023].fires == 2
    assert rows[2023].minimum == pytest.approx(expected("2023_1"), rel=1e-9)


def test_a_prescribed_burn_can_be_counted_on_request(fires):
    rows = rows_by_year(run(fires, include_prescribed=True))

    assert rows[2023].fires == 3
    assert rows[2023].minimum == pytest.approx(expected("2023_3"), rel=1e-9), \
        "the prescribed burn is the smallest fire of the year"


def test_the_excluded_prescribed_burns_are_counted_for_the_log(fires):
    assert app.prescribed_count(fires) == 1
    assert app.prescribed_count(fires, year=2023) == 1
    assert app.prescribed_count(fires, year=1977) == 0
    assert app.prescribed_count(fires, cause="natural") == 0, \
        "the fixture's prescribed burn is human-caused"


def test_the_prescribed_filter_needs_no_null_handling():
    """The column is NOT NULL with a default, unlike the Greek report's category."""
    assert app.is_a_wildfire(include_prescribed=True) is None
    assert "IS NOT" not in str(app.is_a_wildfire()).upper()


# --------------------------------------------------------------------------
# Causes
# --------------------------------------------------------------------------

def test_one_cause_can_be_selected(fires):
    rows = rows_by_year(run(fires, cause="natural"))

    assert rows[1977].fires == 1
    assert rows[2023].fires == 1
    assert rows[2021].fires == 1


def test_the_three_causes_partition_the_archive(fires):
    """Every fire has exactly one cause, so the three runs must add up to the whole."""
    whole = run(fires)[-1].fires
    counted = sum(rows[-1].fires
                  for rows in (run(fires, cause=cause) for cause in app.CAUSES)
                  if rows)

    assert counted == whole


def test_the_cause_vocabulary_is_the_providers(fires):
    """So that a value renamed in the provider module cannot leave this report behind."""
    assert set(app.CAUSES.values()) == set(canada_nbac.FIRE_CAUSES)


def test_an_unknown_cause_is_refused():
    with pytest.raises(ValueError, match="unknown cause"):
        app.cause_condition("lightning")
    assert app.cause_condition(None) is None


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

def test_one_year_can_be_selected(fires):
    rows = run(fires, year=2021)

    assert [row.year for row in rows] == [2021, None]
    assert rows[0].fires == 1


def test_a_minimum_area_selects_the_fires_not_the_years(fires):
    """The threshold picks which fires the figures come from; it drops no year."""
    threshold = expected("1977_2") - 1.0
    rows = rows_by_year(run(fires, min_area=threshold))

    assert rows[1977].fires == 1, "only the largest 1977 fire clears it"
    assert rows[1977].total == pytest.approx(expected("1977_2"), rel=1e-9)


def test_a_year_with_no_fires_reports_nothing(fires):
    assert run(fires, year=1990) == []


def test_an_empty_report_has_no_total_row():
    assert app.summarise([]) == []


def test_the_years_query_carries_the_scope(fires):
    """A year whose only fire is out of scope must not open a statement of its own."""
    every = list(fires.scalars(app.years_query()))
    natural = list(fires.scalars(app.years_query(cause="natural")))

    assert every == [2023, 2021, 1977]
    assert natural == [2023, 2021, 1977]


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
            app.parse_arguments([option, "Canada", "--csv", "x.csv",
                                 "--db-name", "x", "--db-user", "y"])
        assert "there is no" in capsys.readouterr().err


def test_an_area_method_on_a_published_surface_is_refused(capsys):
    """Nothing is measured there, so a choice of how to measure would be a claim."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["--surface", app.SURFACE_PUBLISHED,
                             "--area-method", app.AREA_METHOD_GEODESIC,
                             "--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert "--area-method applies to" in capsys.readouterr().err


def test_an_area_method_on_the_measured_surface_is_accepted():
    args = app.parse_arguments(["--area-method", app.AREA_METHOD_EQUAL_AREA,
                                "--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.area_method == app.AREA_METHOD_EQUAL_AREA


@pytest.mark.parametrize("text", ["-5", "nan", "inf", "not a number"])
def test_a_nonsense_minimum_area_is_refused(text):
    with pytest.raises(argparse.ArgumentTypeError):
        app.hectares(text)


def test_a_valid_minimum_area_is_accepted():
    assert app.hectares("0") == 0.0
    assert app.hectares("200") == 200.0


def test_the_defaults(fires):
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])

    assert args.surface == app.SURFACE_MEASURED
    assert args.area_method is None, "resolved to geodesic by report()"
    assert args.include_prescribed is False
    assert args.cause is None


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


def test_the_docx_is_written(tmp_path, fires):
    pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires), path, None, logger)

    assert path.exists() and path.stat().st_size > 0


def test_the_docx_names_the_surface_it_reports(tmp_path, fires):
    """A table of adjusted hectares must not read as a table of mapped ones."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires, surface=app.SURFACE_ADJUSTED), path, None, logger,
                   surface=app.SURFACE_ADJUSTED)

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert app.SURFACE_PROSE[app.SURFACE_ADJUSTED] in text


def test_the_docx_warns_about_the_natural_cause(tmp_path, fires):
    """The reason most readers will reach for --cause, and not what they assume."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "burnt.docx"
    app.write_docx(run(fires, cause="natural"), path, None, logger, cause="natural")

    text = "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)
    assert "not a lightning" in text or "is not one" in text


def test_every_surface_has_prose():
    """So that a surface added later cannot reach the Word writer without a description."""
    assert set(app.SURFACE_PROSE) == set(app.SURFACES)


def test_a_share_of_nothing_is_no_answer():
    assert app.share(0, 0) is None
    assert app.share_label(0, 0) == ""
    assert app.share_label(1, 4) == "25.00"
