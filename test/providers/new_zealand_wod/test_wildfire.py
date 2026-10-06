#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the WOD models and the provider constants.

What is worth pinning down: that the WOD identifier is a key, repaired where the
export wrote it in scientific notation, and the agency's number is not; that every
published cause spelling lands in exactly one of four classes and an unknown
spelling is an error rather than an *unknown*; that a record always has its point,
stored as published in NZTM2000, the ones in the sea included; that a DOC record's
missing time is a ``NULL`` and not a midnight; and that terrain and weather are one
row each per fire and go with it when it is deleted.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import new_zealand_wod
from src.providers.new_zealand_wod.ignition import WodIgnition
from src.providers.new_zealand_wod.terrain import WodTerrain
from src.providers.new_zealand_wod.weather import WodWeather
from src.providers.new_zealand_wod.wildfire import WodWildfire

UTC = datetime.timezone.utc

#: A published point in NZTM2000 metres, in Auckland (WOD1).
POINT_2193 = "SRID=2193;POINT(1743575 5922720)"

#: The same fire in EPSG:4326.
POINT_4326 = "SRID=4326;POINT(174.610009 -36.830510)"

#: A small square perimeter around it, in NZTM2000.
PERIMETER_2193 = ("SRID=2193;MULTIPOLYGON(((1743500 5922650, 1743650 5922650, "
                  "1743650 5922800, 1743500 5922800, 1743500 5922650)))")

#: The same perimeter, near enough, in EPSG:4326.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((174.6092 -36.8312, 174.6109 -36.8312, "
                  "174.6109 -36.8298, 174.6092 -36.8298, 174.6092 -36.8312)))")

#: 1998-07-30 23:35 in Auckland (NZST, +12) is 11:35 UTC.
REPORTED = datetime.datetime(1998, 7, 30, 11, 35, tzinfo=UTC)


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=new_zealand_wod.PROVIDER_NAME,
                            product=new_zealand_wod.PROVIDER_PRODUCT,
                            full_name=new_zealand_wod.PROVIDER_FULL_NAME,
                            description=new_zealand_wod.PROVIDER_DESCRIPTION,
                            url=new_zealand_wod.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def an_ignition(provider, **overrides) -> WodIgnition:
    """One published point, as the shapefile gives it."""
    values = {
        "data_provider": provider,
        "wod_id": "WOD1",
        "year": 1998,
        "source": new_zealand_wod.SOURCE_FENZ,
        "geometry": POINT_4326,
        "geometry_nztm": POINT_2193,
        "date_time": REPORTED,
        "time_zone": new_zealand_wod.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return WodIgnition(**values)


def a_wildfire(provider, ignition=None, **overrides) -> WodWildfire:
    """One WOD record, as WOD1 publishes it."""
    values = {
        "data_provider": provider,
        "ignition": ignition if ignition is not None else an_ignition(provider),
        "wod_id": "WOD1",
        "source": new_zealand_wod.SOURCE_FENZ,
        "org_id": "A000379",
        "dropped_fenz_org_id": None,
        "year": 1998,
        "report_date": datetime.date(1998, 7, 30),
        "report_time": datetime.time(23, 35),
        "season": "Winter",
        "financial_year": 1998,
        "area_ha": 0.0,
        "area_category": "< 1",
        "ignition_source": "Matches",
        "fire_cause": new_zealand_wod.CAUSE_HUMAN,
        "original_vegetation": None,
        "fenz_district": "Auckland",
        "start_date_time": REPORTED,
        "time_zone": new_zealand_wod.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return WodWildfire(**values)


def committed_fails(db_session) -> None:
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_provider_is_the_paper_and_the_figshare_release():
    assert new_zealand_wod.PROVIDER_URL == "https://doi.org/10.6084/m9.figshare.30854057"
    assert "10.1038/s41597-026-07859-z" in new_zealand_wod.PROVIDER_DESCRIPTION
    assert "CC BY 4.0" in new_zealand_wod.PROVIDER_DESCRIPTION


def test_the_import_starts_where_the_fenz_records_do():
    """Before 1998 the WOD is DOC alone, and the paper says coverage is poor."""
    assert new_zealand_wod.FIRST_YEAR == 1998
    assert new_zealand_wod.PUBLISHED_FIRST_YEAR == 1931


def test_the_published_crs_is_nztm2000():
    assert new_zealand_wod.SOURCE_SRID == 2193


def test_there_are_four_cause_classes_and_lightning_is_one():
    assert set(new_zealand_wod.FIRE_CAUSES) == {"lightning", "natural", "human", "unknown"}


def test_every_mapped_cause_is_a_class():
    assert set(new_zealand_wod.CAUSE_MAP.values()) <= set(new_zealand_wod.FIRE_CAUSES)


def test_no_two_spellings_normalise_to_different_classes():
    """Normalising must merge spellings, never reclassify one."""
    normalised = {}
    for spelling, cause in new_zealand_wod.CAUSE_MAP.items():
        key = new_zealand_wod.normalise_cause(spelling)
        assert normalised.setdefault(key, cause) == cause, spelling


@pytest.mark.parametrize("published", [
    "Lightning discharge",      # FENZ, 467 records
    "Lightning",                # DOC, 32
    "Lightening Strike",        # DOC, 39, misspelt as published
])
def test_the_three_lightning_spellings_are_lightning(published):
    assert new_zealand_wod.fire_cause(published) == new_zealand_wod.CAUSE_LIGHTNING


def test_geothermal_activity_is_natural_and_not_lightning():
    assert new_zealand_wod.fire_cause("Geothermal Activity") == new_zealand_wod.CAUSE_NATURAL


@pytest.mark.parametrize("published, cause", [
    ("Spontaneous ignition, chemical reaction", "human"),
    ("Solar heat: Sun (magnified through glass etc)", "human"),
    ("Trees", "unknown"),
    ("Animals", "unknown"),
    ("Birds nest", "unknown"),
    ("Static electrical discharge", "unknown"),
    ("Exposure Fire - unable to classify", "unknown"),
    ("Re-ignition, Rekindle from previous fire", "unknown"),
    ("Information not recorded/Unknown", "unknown"),
    ("Flare: Warning, Safety, Boat", "human"),
    ("Burn Breakaway - Authorised", "human"),
    ("Arson/ Incendiarism", "human"),
])
def test_the_calls_that_could_go_either_way(published, cause):
    assert new_zealand_wod.fire_cause(published) == cause


@pytest.mark.parametrize("published", [
    "Burn Breakaway - authorised",   # case
    "Electrical Fence ",             # trailing space, as published
    "other",                         # DOC writes both Other and other
    "  Matches  ",
])
def test_spellings_differing_in_case_or_space_are_the_same_cause(published):
    assert new_zealand_wod.fire_cause(published) in new_zealand_wod.FIRE_CAUSES


@pytest.mark.parametrize("published", [None, "", "-9999", "Null", " null "])
def test_no_published_cause_is_unknown_and_stored_as_nothing(published):
    assert new_zealand_wod.published_ignition_source(published) is None
    assert new_zealand_wod.fire_cause(published) == new_zealand_wod.CAUSE_UNKNOWN


def test_a_published_cause_is_stored_stripped_and_otherwise_verbatim():
    assert new_zealand_wod.published_ignition_source("Electrical Fence ") == "Electrical Fence"
    assert new_zealand_wod.published_ignition_source("Lightening Strike") == "Lightening Strike"


def test_an_unmapped_cause_is_an_error_not_an_unknown():
    """A new release's new cause must be classified by a person."""
    with pytest.raises(new_zealand_wod.UnmappedCauseError):
        new_zealand_wod.fire_cause("Volcanic eruption")


@pytest.mark.parametrize("published, expected", [
    ("WOD1", "WOD1"),
    ("WOD128036", "WOD128036"),
    (" WOD42 ", "WOD42"),
    ("WOD1e+05", "WOD100000"),       # the one the export wrote in scientific notation
    ("WOD1.2e+05", "WOD120000"),
])
def test_a_wod_identifier_is_repaired_where_needed(published, expected):
    assert new_zealand_wod.wod_id(published) == expected


@pytest.mark.parametrize("published", ["WOD", "A000379", "WOD1.23456e+02", "WOD0e+00", "1e+05"])
def test_what_is_not_a_wod_identifier_is_refused(published):
    with pytest.raises(ValueError):
        new_zealand_wod.wod_id(published)


# --------------------------------------------------------------------------
# The wildfire model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(WodWildfire))
    assert stored.wod_id == "WOD1"
    assert stored.org_id == "A000379"
    assert stored.report_date == datetime.date(1998, 7, 30)
    assert stored.report_time == datetime.time(23, 35)
    assert stored.financial_year == 1998
    assert stored.fire_cause == new_zealand_wod.CAUSE_HUMAN
    assert stored.ignition_source == "Matches"


def test_it_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "wod_wildfire"
    assert isinstance(parent, WodWildfire)


def test_the_wod_identifier_is_unique(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, ignition=an_ignition(provider, wod_id="WOD2")))
    committed_fails(db_session)


def test_the_agency_number_is_not_unique(db_session, provider):
    """23 DOC numbers occur twice in the published archive."""
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, wod_id="WOD2",
                              ignition=an_ignition(provider, wod_id="WOD2")))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(WodWildfire.__table__)) == 2


def test_a_doc_record_has_no_time_and_starts_at_local_midnight(db_session, provider):
    """The project's convention for a bare date; the NULL is what says so."""
    midnight = datetime.datetime(2009, 2, 5, 11, 0, tzinfo=UTC)  # 2009-02-06 00:00 NZDT
    ignition = an_ignition(provider, source=new_zealand_wod.SOURCE_DOC, year=2009,
                           date_time=midnight)
    db_session.add(a_wildfire(provider, ignition=ignition, source=new_zealand_wod.SOURCE_DOC,
                              year=2009, report_date=datetime.date(2009, 2, 6),
                              report_time=None, season="Summer", financial_year=2008,
                              start_date_time=midnight))
    db_session.commit()

    local = db_session.scalar(select(
        func.timezone(Wildfire.time_zone, Wildfire.start_date_time)))
    stored = db_session.scalar(select(WodWildfire))
    assert stored.report_time is None
    assert local == datetime.datetime(2009, 2, 6, 0, 0)


def test_there_is_never_an_end(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).end_date_time is None


@pytest.mark.parametrize("cause", new_zealand_wod.FIRE_CAUSES)
def test_every_cause_class_is_accepted(db_session, provider, cause):
    db_session.add(a_wildfire(provider, fire_cause=cause))
    db_session.commit()

    assert db_session.scalar(select(WodWildfire)).fire_cause == cause


@pytest.mark.parametrize("column, value", [
    ("fire_cause", "Lightning discharge"),   # the published text, not the class
    ("source", "Scion"),
    ("season", "Wet"),
    ("area_category", "< 2"),
    ("area_ha", -0.0001),                     # the one published negative is clamped to 0
])
def test_values_outside_the_published_vocabulary_are_refused(db_session, provider, column, value):
    db_session.add(a_wildfire(provider, **{column: value}))
    committed_fails(db_session)


def test_a_reported_zero_area_is_an_answer(db_session, provider):
    """28,273 records carry it."""
    db_session.add(a_wildfire(provider, area_ha=0.0))
    db_session.commit()

    assert db_session.scalar(select(WodWildfire)).area_ha == 0.0


def test_the_year_must_be_the_report_date_year(db_session, provider):
    db_session.add(a_wildfire(provider, year=1999))
    committed_fails(db_session)


@pytest.mark.parametrize("financial_year, accepted", [(1998, True), (1997, True),
                                                      (1999, False), (1990, False)])
def test_the_financial_year_starts_in_the_year_or_the_one_before(db_session, provider,
                                                                  financial_year, accepted):
    db_session.add(a_wildfire(provider, financial_year=financial_year))
    if accepted:
        db_session.commit()
    else:
        committed_fails(db_session)


def test_every_fire_has_a_point(db_session, provider):
    assert WodWildfire.__table__.c.ignition_id.nullable is False


def test_two_fires_cannot_share_a_point(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(a_wildfire(provider, ignition=ignition))
    db_session.add(a_wildfire(provider, ignition=ignition, wod_id="WOD2"))
    committed_fails(db_session)


def test_a_point_record_has_no_perimeter(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(WodWildfire))
    assert stored.perimeter is None
    assert stored.perimeter_nztm is None


def test_a_polygon_record_keeps_its_published_crs(db_session, provider):
    db_session.add(a_wildfire(provider, perimeter=PERIMETER_4326,
                              perimeter_nztm=PERIMETER_2193))
    db_session.commit()

    srids = db_session.execute(select(func.ST_SRID(WodWildfire.perimeter_nztm),
                                      func.ST_SRID(WodWildfire.perimeter))).one()
    area = db_session.scalar(select(func.ST_Area(WodWildfire.perimeter_nztm)))
    assert tuple(srids) == (2193, 4326)
    assert area == pytest.approx(150 * 150)


# --------------------------------------------------------------------------
# The ignition point
# --------------------------------------------------------------------------

def test_an_ignition_round_trips(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(WodIgnition))
    assert (stored.wod_id, stored.year, stored.source) == ("WOD1", 1998, "FENZ")
    assert db_session.scalar(select(Wildfire)) is None, "an ignition is not a wildfire"
    assert db_session.scalar(select(Ignition)).type == "wod_ignition"


def test_the_published_point_is_nztm_metres(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    x, y, srid = db_session.execute(select(
        func.ST_X(WodIgnition.geometry_nztm), func.ST_Y(WodIgnition.geometry_nztm),
        func.ST_SRID(WodIgnition.geometry_nztm))).one()
    assert (x, y, srid) == (1743575.0, 5922720.0, 2193)


def test_a_point_in_the_sea_is_stored_as_published(db_session, provider):
    """The 15 FENZ points on the placeholder coordinate are reports of real fires."""
    x, y = new_zealand_wod.PLACEHOLDER_X, new_zealand_wod.PLACEHOLDER_Y
    db_session.add(an_ignition(provider, geometry_nztm=f"SRID=2193;POINT({x} {y})"))
    db_session.commit()

    stored = db_session.execute(select(func.ST_X(WodIgnition.geometry_nztm),
                                       func.ST_Y(WodIgnition.geometry_nztm))).one()
    assert tuple(stored) == (x, y)
    assert db_session.scalar(select(Ignition)).admin_boundary_id is None


def test_the_published_lat_lon_columns_are_not_stored():
    """They are the 4326 reprojection to 1e-9 degrees: a copy, not an observation."""
    assert set(WodIgnition.__table__.columns.keys()) == {
        "id", "wod_id", "year", "source", "geometry_nztm"}


def test_one_record_has_one_point(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.add(an_ignition(provider))
    committed_fails(db_session)


# --------------------------------------------------------------------------
# Terrain and weather
# --------------------------------------------------------------------------

def test_terrain_and_weather_round_trip_with_their_fire(db_session, provider):
    wildfire = a_wildfire(provider)
    wildfire.terrain = WodTerrain(elev=80.95, slope=3.0, aspect_deg=33.9,
                                  aspect_car="Northeast", land_cvr="Built-up Area (settlement)",
                                  fuel_type="Non-Fuel", fuel_class="Non Fuel",
                                  landform="Plateau")
    wildfire.weather = WodWeather(wx_name="Cornwallis Depot Raws", wx_id="42910435",
                                  wx_dist=18.92, temp_noon=16.0, rh_noon=60.0,
                                  ws_noon=5.59, ffmc_noon=64.48, fdc_noon=1,
                                  soi=5.3, enso="La Nina")
    db_session.add(wildfire)
    db_session.commit()

    stored = db_session.scalar(select(WodWildfire))
    assert stored.terrain.land_cvr == "Built-up Area (settlement)"
    assert stored.terrain.min_elev is None
    assert stored.weather.wx_id == "42910435"
    assert stored.weather.fdc_noon == 1
    assert stored.weather.clim_zn_name is None


def test_a_fire_with_no_weather_at_all_is_an_empty_row(db_session, provider):
    """Nothing before 1995 has weather; the row still says what was published."""
    wildfire = a_wildfire(provider)
    wildfire.weather = WodWeather()
    db_session.add(wildfire)
    db_session.commit()

    assert db_session.scalar(select(WodWeather)).temp is None


def test_deleting_a_fire_in_sql_deletes_its_terrain_and_weather(db_session, provider):
    """The import replaces a year with SQL DELETEs, not through the ORM."""
    wildfire = a_wildfire(provider)
    wildfire.terrain = WodTerrain(elev=1.0)
    wildfire.weather = WodWeather(temp=1.0)
    db_session.add(wildfire)
    db_session.commit()

    db_session.execute(text("DELETE FROM wod_wildfire"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(WodTerrain.__table__)) == 0
    assert db_session.scalar(select(func.count()).select_from(WodWeather.__table__)) == 0


@pytest.mark.parametrize("column", ["fdc", "fdc_noon", "fdc_8b", "fdc_8a"])
@pytest.mark.parametrize("value, accepted", [(1, True), (5, True), (0, False), (6, False)])
def test_a_fire_danger_class_is_one_to_five(db_session, provider, column, value, accepted):
    wildfire = a_wildfire(provider)
    wildfire.weather = WodWeather(**{column: value})
    db_session.add(wildfire)
    if accepted:
        db_session.commit()
    else:
        committed_fails(db_session)


def test_an_unknown_enso_phase_is_refused(db_session, provider):
    wildfire = a_wildfire(provider)
    wildfire.weather = WodWeather(enso="La Niña")    # published without the tilde
    db_session.add(wildfire)
    committed_fails(db_session)


def test_terrain_keeps_every_published_column():
    assert set(WodTerrain.__table__.columns.keys()) == {
        "id", "elev", "min_elev", "max_elev", "slope", "min_slope", "max_slope",
        "aspect_deg", "aspect_car", "aspect_car_2", "aspect_car_3",
        "land_cvr", "land_cvr_2", "land_cvr_3", "fuel_type", "fuel_class",
        "landform", "landform_2", "landform_3"}


def test_weather_keeps_every_published_column():
    """68 published columns, from ClimZnName to ENSO."""
    columns = set(WodWeather.__table__.columns.keys()) - {"id"}
    windowed = {f"{name}_{stat}_{window}" for name in ("temp", "rh", "ws")
                for stat in ("max", "min", "avg") for window in ("8b", "8a")}
    indexed = {f"{name}{suffix}" for name in ("ffmc", "isi", "fwi", "fdc", "hfi", "ros")
               for suffix in ("", "_noon", "_8b", "_8a")}
    expected = (windowed | indexed
                | {"temp", "temp_noon", "rh", "rh_noon", "ws", "ws_noon", "wd",
                   "soil_moist", "soil_temp", "dmc_noon", "dc_noon", "bui_noon", "dsr_noon",
                   "precip_noon", "precip_24hr", "precip_48hr", "precip_72hr",
                   "no_rain_1", "no_rain_2", "no_rain_3", "soi", "enso",
                   "clim_zn_name", "wx_name", "wx_id", "wx_dist"})
    assert columns == expected
    assert len(columns) == 68


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    inspector = inspect(db_session.get_bind())
    wildfire = {index["name"] for index in inspector.get_indexes("wod_wildfire")}
    ignition = {index["name"] for index in inspector.get_indexes("wod_ignition")}

    assert {"ix_wod_wildfire_year", "ix_wod_wildfire_source", "ix_wod_wildfire_fire_cause",
            "ix_wod_wildfire_org_id", "idx_wod_wildfire_perimeter_nztm"} <= wildfire
    assert {"ix_wod_ignition_year", "idx_wod_ignition_geometry_nztm"} <= ignition
