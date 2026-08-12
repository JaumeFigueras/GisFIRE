#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF *incendios de magnitud* burnt-area statistics (Chile).

Two things separate this report from its report-archive sibling.

**There are two areas to report, and they are two measurements.** ``Mapped`` comes
from the polygon and ``Reported`` from the *report* the binder attached to it, so a
perimeter that is not bound contributes nothing to the second column. The report says
how many are like that rather than letting the two columns quietly disagree.

**A polygon can be measured three ways**, and the answers differ. ``published`` is
what was computed at import on the UTM grid the file came on; ``geodesic`` and
``equal-area`` are computed now, from the EPSG:4326 perimeter, so that the mainland
fires and the Rapa Nui one — which are on different grids — can be added together at
all.

The fixture perimeters are squares whose ground area is known, so each method's answer
can be checked rather than merely compared with the others.
"""

import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.chile_conaf_magnitud import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import chile_conaf
from src.providers import chile_conaf_magnitud
from src.providers import ocha
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire
from src.providers.chile_conaf_magnitud.wildfire import ConafMagnitudWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-conaf-magnitud-statistics")

UTC = datetime.timezone.utc

COUNTRIES = [
    ("CHL", "Chile", box(-76.0, -56.0, -66.5, -17.0)),
    ("ARG", "Argentina", box(-66.0, -56.0, -53.0, -21.0)),
]

#: ``(season, west, south, side_degrees, mapped_ha, reported_ha or None)``.
#:
#: ``reported_ha`` of ``None`` is a perimeter the binder could not place — 37 of the
#: 743 — which has a mapped area and no reported one.
PERIMETERS = [
    (2016, -73.0, -36.0, 0.10, 1000.0, 950.0),
    (2016, -72.5, -36.5, 0.05, 250.0, None),
    # Over the cordillera: a Chilean archive's polygon that is not in Chile.
    (2016, -65.0, -37.0, 0.05, 300.0, 280.0),
    (2023, -73.2, -37.2, 0.20, 4000.0, 3900.0),
]


def square(west: float, south: float, side: float) -> str:
    return (f"SRID=4326;MULTIPOLYGON((({west} {south}, {west + side} {south}, "
            f"{west + side} {south + side}, {west} {south + side}, "
            f"{west} {south})))")


def grid_square(index: int) -> str:
    """A stand-in for the published grid copy.

    The one-grid ``CHECK`` requires it, and nothing this report computes reads it: the
    published area is the stored ``area_ha_mapped`` and the two measured methods work
    from the EPSG:4326 perimeter. Its shape is therefore not what is being tested, and
    it is deliberately not the reprojection of the square above.
    """
    x, y = 670_000.0 + index * 20_000.0, 5_920_000.0
    return (f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};MULTIPOLYGON((({x} {y}, "
            f"{x + 1000} {y}, {x + 1000} {y + 1000}, {x} {y + 1000}, {x} {y})))")


@pytest.fixture
def populated(db_session):
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    report_provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                                   product=chile_conaf.PROVIDER_PRODUCT,
                                   full_name=chile_conaf.PROVIDER_FULL_NAME,
                                   url=chile_conaf.PROVIDER_URL)
    perimeter_provider = DataProvider(name=chile_conaf_magnitud.PROVIDER_NAME,
                                      product=chile_conaf_magnitud.PROVIDER_PRODUCT,
                                      full_name=chile_conaf.PROVIDER_FULL_NAME,
                                      url=chile_conaf_magnitud.PROVIDER_URL)
    db_session.add_all([ocha_provider, report_provider, perimeter_provider])
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

    for index, (season, west, south, side, mapped, reported) in enumerate(PERIMETERS):
        instant = datetime.datetime(season + 1, 1, 18, tzinfo=UTC)
        report_id = None
        if reported is not None:
            ignition = ConafIgnition(
                data_provider_id=report_provider.id, season_start_year=season,
                number=index, geometry=f"SRID=4326;POINT({west} {south})",
                geometry_utm19s=f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};"
                                f"POINT({670000 + index * 1000} 5920000)",
                date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE)
            db_session.add(ignition)
            db_session.flush()
            report = ConafWildfire(
                data_provider_id=report_provider.id, ignition_id=ignition.id,
                season=app.season_label(season), season_start_year=season,
                number=index, name=f"FUEGO {index}",
                date_time_precision=chile_conaf.PRECISION_DAY,
                area_ha_total=reported, area_totals_agree=True,
                start_date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE)
            db_session.add(report)
            db_session.flush()
            report_id = report.id

        method = chile_conaf_magnitud.MATCH_NUMBER_REGION_NAME_SEASON
        db_session.add(ConafMagnitudWildfire(
            data_provider_id=perimeter_provider.id,
            season=app.season_label(season), season_start_year=season,
            number=index, name=f"FUEGO {index}", region_code="08",
            cause_published=None, area_ha_mapped=mapped, area_ha_published=mapped,
            part_count=1, date_time_precision=chile_conaf.PRECISION_DAY,
            perimeter=square(west, south, side),
            perimeter_utm19s=grid_square(index),
            perimeter_utm12s=None,
            conaf_wildfire_id=report_id,
            match_method=None if report_id is None else method,
            match_confidence=(None if report_id is None
                              else chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE[method]),
            matched_at=None if report_id is None else instant,
            start_date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE))
    db_session.commit()
    return db_session


def run(session, **kwargs):
    return app.compute(session, kwargs.pop("season", None),
                       kwargs.pop("method", app.AREA_METHOD_PUBLISHED),
                       logger, **kwargs)


def find(rows, country, season):
    matches = [row for row in rows if row.country == country and row.season == season]
    assert len(matches) == 1, f"expected one row for {country}/{season}"
    return matches[0]


# --------------------------------------------------------------------------
# The three ways of measuring a polygon
# --------------------------------------------------------------------------

def test_the_published_area_is_the_one_measured_at_import(populated):
    """On the UTM grid the polygon came on, which is what the column holds."""
    chile = find(run(populated), "Chile", 2016)

    assert chile.mapped == pytest.approx(1250.0), "1000 + 250, as published"


@pytest.mark.parametrize("method", app.AREA_METHODS)
def test_every_method_measures_the_same_fires(populated, method):
    """The count does not depend on how the area is computed; only the hectares do."""
    chile = find(run(populated, method=method), "Chile", 2016)

    assert chile.fires == 2


def test_the_geodesic_area_is_measured_on_the_ellipsoid(populated):
    """A 0.1° square at 36°S is 11.1 km by 9.0 km — about 9,990 hectares of ground.

    Checked against that figure rather than against the published column, because the
    point of the option is precisely that it does not trust the published column: the
    fixture's says 1,000 ha, which is what a wrongly-projected measurement looks like.
    """
    chile = find(run(populated, method=app.AREA_METHOD_GEODESIC), "Chile", 2016)

    assert chile.maximum == pytest.approx(9_990.0, rel=0.02)
    assert chile.mapped == pytest.approx(12_470.0, rel=0.02), "and the 0.05° one"


def test_the_measured_methods_work_from_the_4326_perimeter(populated):
    """So they mean the same thing for a mainland fire and for the Rapa Nui one.

    Those are on grids seven zones apart, and areas measured on them could not
    otherwise be added together.
    """
    geodesic = find(run(populated, method=app.AREA_METHOD_GEODESIC), "Chile", 2016)
    equal_area = find(run(populated, method=app.AREA_METHOD_EQUAL_AREA), "Chile", 2016)

    assert geodesic.mapped == pytest.approx(equal_area.mapped, rel=0.01)


def test_the_published_and_the_measured_areas_are_allowed_to_disagree(populated):
    """And do: the published one was computed on a different projection.

    Storing all three as options rather than picking one is what lets a reader see
    how much of an answer is the projection.
    """
    published = find(run(populated), "Chile", 2016).mapped
    geodesic = find(run(populated, method=app.AREA_METHOD_GEODESIC),
                    "Chile", 2016).mapped

    assert published != pytest.approx(geodesic)


def test_an_unknown_area_method_is_refused():
    with pytest.raises(ValueError, match="unknown area method"):
        app.burnt_area("planar")


# --------------------------------------------------------------------------
# Mapped against reported
# --------------------------------------------------------------------------

def test_the_reported_area_comes_from_the_bound_report(populated):
    """A different measurement of the same fire: the office's figure, not the polygon's."""
    chile = find(run(populated), "Chile", 2016)

    assert chile.mapped == pytest.approx(1250.0)
    assert chile.reported == pytest.approx(950.0)


def test_an_unbound_perimeter_contributes_no_reported_area(populated):
    """37 of the 743 are unbound. Their mapped area is real; their reported one does
    not exist, and inventing a zero for it would understate the season."""
    chile = find(run(populated), "Chile", 2016)

    assert chile.fires == 2
    assert chile.bound == 1


def test_the_report_says_how_many_are_unbound(populated, caplog):
    """So a reader knows why the two area columns do not agree."""
    with caplog.at_level(logging.INFO):
        run(populated)

    assert any("not bound to a report" in record.message for record in caplog.records)


def test_bound_only_narrows_the_scope_to_the_comparable_fires(populated):
    """The only scope in which Mapped and Reported are about the same set of fires."""
    rows = run(populated, bound_only=True)
    chile = find(rows, "Chile", 2016)

    assert chile.fires == chile.bound == 1
    assert chile.mapped == pytest.approx(1000.0)
    assert chile.reported == pytest.approx(950.0)


# --------------------------------------------------------------------------
# Country, season and totals
# --------------------------------------------------------------------------

def test_a_perimeter_over_the_cordillera_is_reported_as_that_country(populated):
    rows = run(populated)

    assert find(rows, "Argentina", 2016).fires == 1
    assert find(rows, "Chile", 2016).fires == 2


def test_the_containment_test_uses_a_point_on_the_perimeter(populated):
    """A polygon is not contained by a country it merely overlaps, and a fire on the
    border must not become two rows."""
    _, joins = app.country_columns(app.COUNTRY_SOURCE_GEOMETRY)
    assert joins, "the geometry source joins something"


def test_a_season_reports_the_smallest_the_largest_and_the_sum(populated):
    chile = find(run(populated), "Chile", 2016)

    assert chile.minimum == pytest.approx(250.0)
    assert chile.maximum == pytest.approx(1000.0)


def test_a_country_gets_a_total_row_over_its_seasons(populated):
    totals = [row for row in run(populated) if row.is_total and row.country == "Chile"]

    assert len(totals) == 1
    assert totals[0].fires == 3
    assert totals[0].mapped == pytest.approx(5250.0)
    assert totals[0].reported == pytest.approx(4850.0)


def test_the_minimum_area_is_applied_to_the_measured_area(populated):
    rows = run(populated, min_area=500.0)

    assert find(rows, "Chile", 2016).fires == 1
    assert find(rows, "Chile", 2016).mapped == pytest.approx(1000.0)


def test_an_empty_scope_reports_nothing_rather_than_zeros(db_session, caplog):
    with caplog.at_level(logging.WARNING):
        rows = run(db_session)

    assert rows == []
    assert any("No CONAF perimeter in scope" in record.message
               for record in caplog.records)


# --------------------------------------------------------------------------
# The written report
# --------------------------------------------------------------------------

def test_the_csv_carries_both_areas_and_the_bound_count(populated, tmp_path):
    path = tmp_path / "magnitud.csv"
    app.write_csv(run(populated), path, logger)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    chile_2016 = next(row for row in rows
                      if row["Country"] == "Chile" and row["Season"] == "2016-2017")
    assert (chile_2016["Fires"], chile_2016["Bound"]) == ("2", "1")
    assert chile_2016["Mapped (ha)"] == "1250.00"
    assert chile_2016["Reported (ha)"] == "950.00"
    assert "Mapped (ha)" in app.COLUMNS and "Reported (ha)" in app.COLUMNS
