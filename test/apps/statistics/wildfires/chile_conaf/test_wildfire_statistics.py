#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF burnt-area statistics application (Chile).

The fires are inserted through the ORM rather than imported from a shapefile: what
has to be asserted is arithmetic over known published areas in known seasons, and
building that by hand is quicker and clearer than arranging for an importer to
produce it.

The fixture is built round the two things that make this report different from its
siblings.

**Half the archive has no date.** 49,470 of the 95,868 fires start at 1 July midnight
because that is where the importer put them, so the report carries a ``Dated`` column
beside ``Fires`` and a ``--dated-only`` switch, and saying which half a figure is
about is part of the output rather than a footnote.

**There are four burnt surfaces, not one.** CONAF reports area by what burnt, and the
three subtotals are not interchangeable: a question about the forestry industry is
about ``plantation``, one about ecology is about ``vegetation``, and only ``total``
matches the figure CONAF itself publishes.
"""

import csv
import datetime
import logging

import pytest

from shapely.geometry import MultiPolygon
from shapely.geometry import box

from src.apps.statistics.wildfires.chile_conaf import wildfire_statistics as app
from src.data_model.data_provider import DataProvider
from src.providers import chile_conaf
from src.providers import ocha
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

logger = logging.getLogger("test-conaf-statistics")

UTC = datetime.timezone.utc

#: Two countries that do not overlap, so a point is in one of them or in neither.
#: Argentina is here to catch the fire whose coordinate crossed the cordillera.
COUNTRIES = [
    ("CHL", "Chile", box(-76.0, -56.0, -66.5, -17.0)),
    ("ARG", "Argentina", box(-66.0, -56.0, -53.0, -21.0)),
]

#: ``(season, reporter, longitude, latitude, dated, plantation, vegetation, other)``.
#:
#: The three surface subtotals are deliberately unequal so that a report of one of
#: them cannot accidentally pass as a report of another, and the totals within a
#: season are unequal so a minimum and a maximum are distinguishable from the sum.
FIRES = [
    # 2016-2017: a season with no published dates at all, as eight of fifteen are.
    (2016, "Conaf", -73.05, -36.83, False, 15.0, 21.0, 19.0),
    (2016, "Empresa", -72.50, -37.20, False, 0.0, 2.5, 0.0),
    # A point over the cordillera: a Chilean report of a fire that is not in Chile.
    (2016, "Conaf", -65.00, -37.00, False, 1.0, 1.0, 1.0),
    # A point in the Pacific: inside no country at all, and dropped.
    (2016, "Conaf", -85.00, -37.00, False, 4.0, 0.0, 0.0),
    # 2023-2024: the modern season, dated to the minute.
    (2023, "Conaf", -73.10, -36.90, True, 1.5, 3.5, 0.0),
    (2023, "Empresa", -72.60, -37.30, True, 0.0, 4.0, 0.0),
    (2023, "Conaf", -72.70, -37.40, False, 100.0, 100.0, 100.0),
]


@pytest.fixture
def populated(db_session):
    """The fixture world: two countries and seven CONAF fire reports."""
    ocha_provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                 full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
    conaf_provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                                  product=chile_conaf.PROVIDER_PRODUCT,
                                  full_name=chile_conaf.PROVIDER_FULL_NAME,
                                  url=chile_conaf.PROVIDER_URL)
    db_session.add_all([ocha_provider, conaf_provider])
    db_session.flush()

    boundaries = {}
    for code, name, geometry in COUNTRIES:
        boundary = OchaAdminBoundary(
            data_provider_id=ocha_provider.id, source_id=code, level=0, name=name,
            geometry=f"SRID=4326;{MultiPolygon([geometry]).wkt}",
            source=code, iso_code=1, iso_2=code[:2], iso_3=code, iso_name=name,
            iso_3_group=code, region1_code=1, region1_name="r1", region2_code=2,
            region2_name="r2", region3_code=3, region3_name="r3", status_code=1,
            status_name="State", valid_date=datetime.date(2025, 1, 1),
            update_date=datetime.date(2025, 1, 1), land_source="osm", view="intl",
        )
        db_session.add(boundary)
        db_session.flush()
        boundaries[code] = boundary.id

    for index, (season, reporter, longitude, latitude, dated,
                plantation, vegetation, other) in enumerate(FIRES):
        instant = (datetime.datetime(season + 1, 1, 18, 15, 50, tzinfo=UTC) if dated
                   else datetime.datetime(season, 7, 1, tzinfo=UTC))
        precision = (chile_conaf.PRECISION_MINUTE if dated
                     else chile_conaf.PRECISION_SEASON)
        ignition = ConafIgnition(
            data_provider_id=conaf_provider.id, season_start_year=season,
            number=index, region_code="08",
            geometry=f"SRID=4326;POINT({longitude} {latitude})",
            geometry_utm19s=f"SRID={chile_conaf.SOURCE_SRID_MAINLAND};"
                            f"POINT({670000 + index * 1000} {5920000 + index * 1000})",
            date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE,
        )
        db_session.add(ignition)
        db_session.flush()
        db_session.add(ConafWildfire(
            data_provider_id=conaf_provider.id, ignition_id=ignition.id,
            season=app.season_label(season), season_start_year=season,
            number=index, name=f"FUEGO {index}", reporter=reporter,
            region_code="08", date_time_precision=precision,
            area_ha_plantation=plantation, area_ha_vegetation=vegetation,
            area_ha_other=other,
            area_ha_total=plantation + vegetation + other, area_totals_agree=True,
            start_date_time=instant, time_zone=chile_conaf.DEFAULT_TIME_ZONE,
            # Chile as filed, on every fire, including the two that are not in it.
            admin_boundary_id=boundaries["CHL"],
        ))
    db_session.commit()
    return db_session


def run(session, **kwargs):
    """Compute the report over the fixture."""
    return app.compute(session, kwargs.pop("season", None),
                       kwargs.pop("surface_name", app.DEFAULT_SURFACE),
                       logger, **kwargs)


def find(rows, country, season):
    matches = [row for row in rows if row.country == country and row.season == season]
    assert len(matches) == 1, f"expected one row for {country}/{season}"
    return matches[0]


# --------------------------------------------------------------------------
# The season
# --------------------------------------------------------------------------

def test_a_season_is_named_the_way_conaf_names_it():
    assert app.season_label(2016) == "2016-2017"


def test_the_season_is_the_published_one_and_not_derived_from_the_instant():
    """For half the archive that instant was built *from* the season in the first place.

    Deriving the season back out of it would be circular for 49,470 fires — and it
    would put a fire of 18 January 2017 in "2017", which is not a season CONAF has.
    """
    assert app.SEASON is ConafWildfire.__table__.c.season_start_year

    fires_2016 = [row for row in FIRES if row[0] == 2016]
    assert any(not dated for _, _, _, _, dated, *_ in fires_2016)


# --------------------------------------------------------------------------
# The four surfaces
# --------------------------------------------------------------------------

def test_the_default_surface_is_the_whole_fire(populated):
    """``SUPERFICIE`` is the only one that matches CONAF's own published statistics."""
    assert app.DEFAULT_SURFACE == "total"

    chile = find(run(populated), "Chile", 2016)
    assert chile.total == pytest.approx(57.5), "55 + 2.5, without the two dropped"


@pytest.mark.parametrize("surface, expected", [
    ("total", 57.5),
    ("plantation", 15.0),
    ("vegetation", 23.5),
    ("other", 19.0),
])
def test_each_surface_is_a_different_question(populated, surface, expected):
    """The subtotals are not interchangeable and are not offered as one number."""
    chile = find(run(populated, surface_name=surface), "Chile", 2016)
    assert chile.total == pytest.approx(expected)


def test_an_unknown_surface_is_refused():
    with pytest.raises(ValueError, match="unknown surface"):
        app.surface_area("eucalyptus")


def test_the_nine_components_are_not_on_the_command_line():
    """They are on the model, and a reader who wants eucalyptus alone can ask in SQL.

    Offering nine more choices here would suggest they are all equally meaningful
    questions of the archive, and they are not.
    """
    assert set(app.SURFACES) == {"total", "plantation", "vegetation", "other"}


# --------------------------------------------------------------------------
# Which country a fire counts towards
# --------------------------------------------------------------------------

def test_the_default_tests_the_published_point(populated):
    """For a single-country archive its job is to catch the fires that are in none."""
    args = app.parse_arguments(["--csv", "x.csv", "--db-name", "x", "--db-user", "y"])
    assert args.country_source == app.COUNTRY_SOURCE_GEOMETRY


def test_a_fire_over_the_cordillera_is_reported_as_that_country(populated):
    rows = run(populated)

    assert find(rows, "Argentina", 2016).fires == 1
    assert find(rows, "Chile", 2016).fires == 2, "the border fire is not in Chile's row"


def test_a_fire_in_the_pacific_is_dropped(populated):
    """A point mis-keyed into the ocean is not a fire anywhere.

    Under ``reported`` it keeps the Chilean ``admin_boundary_id`` the import gave it
    and is silently in the total, which is what the default exists to prevent.
    """
    assert find(run(populated), "Chile", 2016).total == pytest.approx(57.5)


def test_reported_trusts_what_the_import_stored(populated):
    """Far cheaper — a foreign key lookup instead of a point-in-polygon test per fire.

    For 95,865 fires that difference is worth having, and where the boundaries are
    the ones the import used it gives the same answer.
    """
    rows = run(populated, country_source=app.COUNTRY_SOURCE_REPORTED)

    assert {row.country for row in rows} == {"Chile"}
    assert find(rows, "Chile", 2016).fires == 4
    assert find(rows, "Chile", 2016).total == pytest.approx(64.5), \
        "57.5 + 3 over the border + 4 in the sea"


def test_the_containment_test_uses_the_point_and_not_a_perimeter(populated):
    """There is no perimeter on this archive: it is ``NULL`` on every row.

    Every other perimeter-bearing provider's version of this tests
    ``ST_PointOnSurface`` of the polygon; here the point *is* the published location.
    """
    _, joins = app.country_columns(app.COUNTRY_SOURCE_GEOMETRY)
    assert any("ignition" in str(target) for target, _ in joins)


def test_an_unknown_country_source_is_refused():
    with pytest.raises(ValueError, match="unknown country source"):
        app.country_columns("filed")


# --------------------------------------------------------------------------
# The dated half
# --------------------------------------------------------------------------

def test_the_dated_column_counts_the_fires_with_a_real_start(populated):
    """51.6% of the archive has none, and a report that hides that is misleading."""
    rows = run(populated)

    assert find(rows, "Chile", 2016).dated == 0, "no season before 2017-2018 has dates"
    assert find(rows, "Chile", 2023).fires == 3
    assert find(rows, "Chile", 2023).dated == 2


def test_dated_only_narrows_the_scope_to_the_computable_half(populated):
    """Any month-of-year, hour or duration statistic is about this half only."""
    rows = run(populated, dated_only=True)

    assert find(rows, "Chile", 2023).fires == 2
    assert find(rows, "Chile", 2023).total == pytest.approx(9.0)
    assert not [row for row in rows if row.season == 2016], \
        "a season with no dated fire has no row at all"


# --------------------------------------------------------------------------
# The other filters
# --------------------------------------------------------------------------

def test_the_reporter_splits_two_reporting_systems(populated):
    """CONAF's regional offices and the forestry companies' own brigades.

    A count over both is a count of two different systems, so it can be asked of one.
    """
    rows = run(populated, reporter=chile_conaf.REPORTER_COMPANY)

    assert find(rows, "Chile", 2016).fires == 1
    assert find(rows, "Chile", 2016).total == pytest.approx(2.5)


def test_the_minimum_area_is_applied_to_the_surface_being_measured(populated):
    """Asking for plantations of 10 ha or more must not return every fire whose
    *whole* burn reached 10 ha: that is a different question with the same command
    line."""
    rows = run(populated, surface_name="plantation", min_area=10.0)

    assert find(rows, "Chile", 2016).fires == 1
    assert find(rows, "Chile", 2016).total == pytest.approx(15.0)


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

def test_a_season_reports_the_smallest_the_largest_and_the_sum(populated):
    chile = find(run(populated), "Chile", 2023)

    assert chile.fires == 3
    assert chile.minimum == pytest.approx(4.0)
    assert chile.maximum == pytest.approx(300.0)
    assert chile.total == pytest.approx(309.0)


def test_a_country_gets_a_total_row_over_its_seasons(populated):
    rows = run(populated)
    totals = [row for row in rows if row.is_total and row.country == "Chile"]

    assert len(totals) == 1
    assert totals[0].fires == 5
    assert totals[0].total == pytest.approx(366.5)
    assert totals[0].season_label == app.TOTAL_LABEL


def test_the_total_rows_extremes_are_the_extremes_of_its_seasons(populated):
    """Order statistics over a partition, so taking them over the seasons is exact."""
    total = next(row for row in run(populated) if row.is_total and row.country == "Chile")

    assert total.minimum == pytest.approx(2.5)
    assert total.maximum == pytest.approx(300.0)


def test_one_season_reports_only_that_season(populated):
    rows = run(populated, season=2023)

    assert {row.season for row in rows if not row.is_total} == {2023}


def test_an_empty_scope_reports_nothing_rather_than_zeros(populated, caplog):
    """And says where the fires would have come from, rather than printing a zero."""
    with caplog.at_level(logging.WARNING):
        rows = run(populated, min_area=1_000_000.0)

    assert rows == []
    assert any("No CONAF fire in scope" in record.message for record in caplog.records)


# --------------------------------------------------------------------------
# The written report
# --------------------------------------------------------------------------

def test_the_csv_carries_the_dated_column_beside_the_count(populated, tmp_path):
    """Because the two are different numbers for half of this archive."""
    path = tmp_path / "conaf.csv"
    app.write_csv(run(populated), path, logger)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert "Dated" in rows[0]
    chile_2016 = next(row for row in rows
                      if row["Country"] == "Chile" and row["Season"] == "2016-2017")
    assert (chile_2016["Fires"], chile_2016["Dated"]) == ("2", "0")


def test_the_scope_sentence_says_what_was_measured():
    sentence = app.scope_sentence(2016, "plantation", True, 5.0, "Conaf")

    assert "2016-2017" in sentence
    assert "published start date" in sentence
    assert "5 ha" in sentence
    assert "Conaf" in sentence
