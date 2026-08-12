#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Greek Fire Service models and the provider constants.

Five things are worth pinning down here, and each is a decision that would be
invisible in the column list alone: that the published headers really do fold onto
one name each, Latin homoglyph and line-break hyphen included; that a published
pair of zeros is *not* a location; that neither table constrains an identifier,
because the dataset has none; that the ignition deliberately stores no coordinate
columns of its own, being already in EPSG:4326; and that the 2025 false alarms are
kept rather than dropped, with the ``NULL``-safe filter that excludes them.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy import text

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import greece_ffa
from src.providers.greece_ffa.ignition import GreeceFfaIgnition
from src.providers.greece_ffa.wildfire import GreeceFfaWildfire

UTC = datetime.timezone.utc

#: A fire near Kalamos, Attica — the first row of the 2022 sheet.
POINT_4326 = "SRID=4326;POINT(23.86 38.28)"


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=greece_ffa.PROVIDER_NAME,
                            product=greece_ffa.PROVIDER_PRODUCT,
                            full_name=greece_ffa.PROVIDER_FULL_NAME,
                            url=greece_ffa.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> GreeceFfaWildfire:
    """One Greek fire record, with everything a 2022 sheet publishes."""
    values = {
        "data_provider": provider,
        "year": 2022,
        "source_sheet": "2022",
        "record_number": 1799346,
        "engage_id": 970757,
        "station_name": "Π.Κ. ΚΑΛΑΜΟΥ",
        "prefecture_name": "ΑΤΤΙΚΗΣ",
        "forest_district_name": None,
        "municipality_name": "Δ. ΩΡΩΠΟΥ",
        "locality_name": "ΚΑΛΑΜΟΣ",
        "address": "ΘΕΣΗ ΧΙΛΙΟΠΟΤΑΜΟΣ",
        # 0, 3, 0, 1, 0, 17, 0.9 and 0 στρέμματα as published.
        "area_ha_forest": 0.0,
        "area_ha_forest_land": 0.3,
        "area_ha_grove": 0.0,
        "area_ha_grassland": 0.1,
        "area_ha_reeds_marsh": 0.0,
        "area_ha_agricultural": 1.7,
        "area_ha_crop_residue": 0.09,
        "area_ha_landfill": 0.0,
        "personnel_fire_service": 28,
        "personnel_infantry_units": 22,
        "personnel_volunteers": 15,
        "personnel_army": 0,
        "personnel_other": 9,
        "vehicles_fire_service": 15,
        "vehicles_public_service": 9,
        "vehicles_water_tankers": 2,
        "vehicles_machinery": 1,
        "aircraft_helicopters": 0,
        "aircraft_cl415": 0,
        "aircraft_cl215": 0,
        "aircraft_pzl": 0,
        "aircraft_gru": 0,
        "aircraft_leased_helicopters": 2,
        "aircraft_leased_planes": 0,
        "start_date_time": datetime.datetime(2022, 6, 14, 10, 24, tzinfo=UTC),
        "end_date_time": datetime.datetime(2022, 6, 16, 17, 59, tzinfo=UTC),
        "time_zone": greece_ffa.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return GreeceFfaWildfire(**values)


def an_ignition(provider, **overrides) -> GreeceFfaIgnition:
    """One published point, as the sheets from 2020 on give it."""
    values = {
        "data_provider": provider,
        "year": 2022,
        "record_number": 1799346,
        "engage_id": 970757,
        "geometry": POINT_4326,
        "date_time": datetime.datetime(2022, 6, 14, 10, 24, tzinfo=UTC),
        "time_zone": greece_ffa.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return GreeceFfaIgnition(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_source_crs_is_plain_wgs84():
    """Not a national grid: the service publishes decimal degrees.

    This is what makes the ignition's lack of coordinate columns correct rather
    than an omission — see the test further down.
    """
    assert greece_ffa.SOURCE_SRID == 4326


def test_greece_is_one_time_zone():
    """Not a fallback, unlike every other importer's: there is nothing to resolve."""
    assert greece_ffa.DEFAULT_TIME_ZONE == "Europe/Athens"


def test_a_stremma_is_a_tenth_of_a_hectare():
    """Defined, not measured: a στρέμμα is 1,000 m² and a hectare is 10,000."""
    assert greece_ffa.STREMMA_HA == 0.1
    assert 17 * greece_ffa.STREMMA_HA == pytest.approx(1.7)


def test_the_first_coordinates_and_the_first_identifiers_arrive_together():
    """2020 for both — the same year, and two different facts about the archive."""
    assert greece_ffa.FIRST_YEAR == 2000
    assert greece_ffa.FIRST_YEAR_WITH_COORDINATES == 2020
    assert greece_ffa.FIRST_YEAR_WITH_IDENTIFIERS == 2020


def test_the_false_alarm_category_is_one_of_the_published_four():
    assert greece_ffa.CATEGORY_FALSE_ALARM in greece_ffa.INCIDENT_CATEGORIES
    assert len(greece_ffa.INCIDENT_CATEGORIES) == 4


# --------------------------------------------------------------------------
# Reading the published headers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published, normalised", [
    # The line-break hyphen the spreadsheet wraps long headers with.
    ("ΒΥΤΙΟ- ΦΟΡΑ", "ΒΥΤΙΟΦΟΡΑ"),
    ("ΒΥΤΙΟΦΟΡΑ", "ΒΥΤΙΟΦΟΡΑ"),
    ("ΜΗΧΑΝΗ-ΜΑΤΑ", "ΜΗΧΑΝΗΜΑΤΑ"),
    ("ΜΗΧΑΝΗΜΑΤΑ", "ΜΗΧΑΝΗΜΑΤΑ"),
    ("ΕΘΕΛΟ-ΝΤΕΣ", "ΕΘΕΛΟΝΤΕΣ"),
    ("ΕΘΕΛΟΝΤΕΣ", "ΕΘΕΛΟΝΤΕΣ"),
    ("ΕΛΙΚΟ- ΠΤΕΡΑ", "ΕΛΙΚΟΠΤΕΡΑ"),
    ("ΕΛΙΚΟΠΤΕΡΑ", "ΕΛΙΚΟΠΤΕΡΑ"),
    ("Σκουπι-δότοποι", "ΣΚΟΥΠΙΔΟΤΟΠΟΙ"),
    ("Σκουπιδότοποι", "ΣΚΟΥΠΙΔΟΤΟΠΟΙ"),
    # Case and the accents the sheets are inconsistent about.
    ("Υπηρεσία", "ΥΠΗΡΕΣΙΑ"),
    ("  Νομός  ", "ΝΟΜΟΣ"),
    ("Ημερ/νία Έναρξης", "ΗΜΕΡ/ΝΙΑΕΝΑΡΞΗΣ"),
    (None, ""),
])
def test_a_published_header_folds_onto_one_name(published, normalised):
    assert greece_ffa.normalise_column(published) == normalised


def test_the_latin_and_greek_spellings_of_engage_are_one_column():
    """The 2025 file writes A/A with a Latin A; every other year uses U+0391.

    They render identically and compare unequal, which is exactly the kind of bug
    that imports a whole year with an empty column and no error.
    """
    greek = greece_ffa.normalise_column("Α/Α ENGAGE")   # U+0391
    latin = greece_ffa.normalise_column("A/A ENGAGE")   # U+0041
    assert "Α/Α ENGAGE" != "A/A ENGAGE", "the fixture itself must use both characters"
    assert greek == latin


# --------------------------------------------------------------------------
# A published coordinate, and a published pair of zeros
# --------------------------------------------------------------------------

@pytest.mark.parametrize("longitude, latitude", [
    (23.86, 38.28),      # Attica
    (19.3874, 41.7284),  # the north-western and northern extremes of the archive
    (29.5731, 34.9392),  # the eastern and southern ones
])
def test_a_coordinate_inside_greece_is_a_location(longitude, latitude):
    assert greece_ffa.is_located(longitude, latitude)


@pytest.mark.parametrize("longitude, latitude", [
    (0.0, 0.0),          # what the service writes for "not located": 3,755 rows
    (0.0, 38.28),
    (23.86, 0.0),
    (None, 38.28),
    (23.86, None),
    (None, None),
])
def test_a_zero_or_a_missing_number_is_not_a_location(longitude, latitude):
    """Null island is in the Gulf of Guinea, and 3,755 Greek fires are not."""
    assert not greece_ffa.is_located(longitude, latitude)


def test_a_transposed_pair_is_refused():
    """Bounds and not ``!= 0``, so that latitude-as-longitude is caught.

    A Greek latitude used as a longitude lands at 38°E, in eastern Turkey — which a
    zero test would accept and store as a Greek fire.
    """
    assert not greece_ffa.is_located(38.28, 23.86)


# --------------------------------------------------------------------------
# The wildfire model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.year == 2022
    assert stored.source_sheet == "2022"
    assert stored.record_number == 1799346
    assert stored.engage_id == 970757
    assert stored.prefecture_name == "ΑΤΤΙΚΗΣ"
    assert stored.municipality_name == "Δ. ΩΡΩΠΟΥ"
    assert stored.address == "ΘΕΣΗ ΧΙΛΙΟΠΟΤΑΜΟΣ"
    assert stored.area_ha_agricultural == pytest.approx(1.7)
    assert stored.personnel_fire_service == 28
    assert stored.aircraft_leased_helicopters == 2


def test_it_is_stored_across_the_two_tables(db_session, provider):
    """Joined table inheritance: the generic columns in wildfire, the Greek ones here."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    assert db_session.scalar(select(func.count()).select_from(GreeceFfaWildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "greece_ffa_wildfire"
    assert isinstance(parent, GreeceFfaWildfire)


def test_there_is_never_a_perimeter(db_session, provider):
    """An administrative statistic, like EGIF: no polygon is published in any year."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).perimeter is None
    assert "perimeter" not in GreeceFfaWildfire.__table__.columns


def test_the_areas_are_stored_in_hectares_not_stremmata(db_session, provider):
    """Every column is ``area_ha_*``; the source publishes tenths of these numbers."""
    areas = [name for name in GreeceFfaWildfire.__table__.columns.keys()
             if name.startswith("area_")]
    assert len(areas) == 8
    assert all(name.startswith("area_ha_") for name in areas)
    assert not any("stremma" in name for name in GreeceFfaWildfire.__table__.columns.keys())


def test_there_is_no_stored_total(db_session, provider):
    """The eight areas are stored and their sum is not: a stored sum can drift."""
    assert "area_ha_total" not in GreeceFfaWildfire.__table__.columns
    assert "area_ha_forest_total" not in GreeceFfaWildfire.__table__.columns


def test_a_reported_zero_area_is_not_a_missing_one(db_session, provider):
    """``Δάση`` of 0 means no forest burnt, which is an answer."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.area_ha_forest == 0.0
    assert stored.area_ha_forest is not None


def test_a_year_that_publishes_no_deployment_leaves_it_null(db_session, provider):
    """2000-2010 have no deployment block at all, and NULL says so.

    A zero would say "nothing was sent to this fire", which is a different claim and
    a false one.
    """
    db_session.add(a_wildfire(provider, year=2005, source_sheet="2005",
                              record_number=None, engage_id=None,
                              municipality_name=None, address=None,
                              personnel_fire_service=None, personnel_infantry_units=None,
                              personnel_volunteers=None, personnel_army=None,
                              personnel_other=None, vehicles_fire_service=None,
                              vehicles_public_service=None, vehicles_water_tankers=None,
                              vehicles_machinery=None, aircraft_helicopters=None,
                              aircraft_cl415=None, aircraft_cl215=None, aircraft_pzl=None,
                              aircraft_gru=None, aircraft_leased_helicopters=None,
                              aircraft_leased_planes=None))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.personnel_fire_service is None
    assert stored.aircraft_cl415 is None
    # And the columns that arrive later than 2000 are equally absent.
    assert stored.municipality_name is None, "Δήμος is not published before 2009"
    assert stored.address is None, "Διεύθυνση is not published before 2012"


def test_a_missing_extinction_is_allowed(db_session, provider):
    """27,183 records — 10.4% — publish no extinction date."""
    db_session.add(a_wildfire(provider, end_date_time=None))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).end_date_time is None


# --------------------------------------------------------------------------
# Nothing identifies a fire
# --------------------------------------------------------------------------

def test_the_same_record_number_twice_is_accepted(db_session, provider):
    """512 record numbers in the archive are used by more than one row.

    A ``UNIQUE`` would be the natural-looking choice and would reject records the
    service really published, which is why this test exists rather than a
    constraint.
    """
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, locality_name="ΑΓΙΟΙ ΑΠΟΣΤΟΛΟΙ"))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(GreeceFfaWildfire.__table__)) == 2


def test_a_fire_with_no_identifier_at_all_is_storable(db_session, provider):
    """201,948 of the 260,194 rows: every year before 2020 publishes neither."""
    db_session.add(a_wildfire(provider, year=2003, source_sheet="2003",
                              record_number=None, engage_id=None))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert (stored.record_number, stored.engage_id) == (None, None)
    assert stored.year == 2003, "the year is the only handle such a row has"


def test_neither_table_constrains_an_identifier(db_session):
    """Stated against the schema, so that adding a UNIQUE later has to face this test.

    The unique constraints that do exist are the primary keys, which are the
    inherited surrogate ids and not anything the service published.
    """
    for table in (GreeceFfaWildfire.__table__, GreeceFfaIgnition.__table__):
        assert table.constraints is not None
        unique = [c for c in table.constraints
                  if c.__class__.__name__ == "UniqueConstraint"]
        assert unique == [], f"{table.name} constrains something the dataset does not identify"
        assert not any(column.unique for column in table.columns)


# --------------------------------------------------------------------------
# The false alarms
# --------------------------------------------------------------------------

def test_a_false_alarm_is_stored_rather_than_dropped(db_session, provider):
    """A row that says "this was not a fire" can be filtered; a dropped one cannot."""
    db_session.add(a_wildfire(provider, year=2025, source_sheet="Sheet0",
                              incident_category=greece_ffa.CATEGORY_FALSE_ALARM))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.incident_category == greece_ffa.CATEGORY_FALSE_ALARM


def test_excluding_the_false_alarms_keeps_the_years_that_publish_no_category(db_session,
                                                                            provider):
    """``IS DISTINCT FROM`` and not ``<>`` — the difference is twenty-five years.

    ``incident_category`` is NULL for 2000-2024, and ``<> 'ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ'``
    evaluates to NULL there, so the obvious filter silently drops 96% of the
    archive.
    """
    db_session.add(a_wildfire(provider))                                  # 2022, NULL
    db_session.add(a_wildfire(provider, year=2025, source_sheet="Sheet0",
                              incident_category=greece_ffa.CATEGORY_SMALL))
    db_session.add(a_wildfire(provider, year=2025, source_sheet="Sheet0",
                              incident_category=greece_ffa.CATEGORY_FALSE_ALARM))
    db_session.commit()

    right = db_session.scalar(text(
        "SELECT count(*) FROM greece_ffa_wildfire "
        "WHERE incident_category IS DISTINCT FROM :category"
    ).bindparams(category=greece_ffa.CATEGORY_FALSE_ALARM))
    wrong = db_session.scalar(text(
        "SELECT count(*) FROM greece_ffa_wildfire WHERE incident_category <> :category"
    ).bindparams(category=greece_ffa.CATEGORY_FALSE_ALARM))

    assert right == 2, "the 2022 fire and the small 2025 one"
    assert wrong == 1, "the NULL year is silently dropped, which is the point"


def test_the_category_has_no_check_constraint(db_session, provider):
    """One year of one file observed once is not a vocabulary to freeze into DDL."""
    db_session.add(a_wildfire(provider, year=2026, source_sheet="Sheet0",
                              incident_category="ΝΕΑ ΚΑΤΗΓΟΡΙΑ"))
    db_session.commit()

    assert db_session.scalar(select(GreeceFfaWildfire)).incident_category == "ΝΕΑ ΚΑΤΗΓΟΡΙΑ"


# --------------------------------------------------------------------------
# The ignition point
# --------------------------------------------------------------------------

def test_an_ignition_round_trips(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaIgnition))
    assert stored.year == 2022
    assert (stored.record_number, stored.engage_id) == (1799346, 970757)
    assert db_session.scalar(select(Wildfire)) is None, "an ignition is not a wildfire"


def test_an_ignition_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Ignition.__table__)) == 1
    parent = db_session.scalar(select(Ignition))
    assert parent.type == "greece_ffa_ignition"
    assert isinstance(parent, GreeceFfaIgnition)


def test_the_ignition_stores_no_coordinate_columns_of_its_own(db_session, provider):
    """Deliberate, and the one place this provider departs from Spain and Andalusia.

    Those two keep the published easting and northing because the geometry is a
    *reprojection* of them. Here the published pair is already EPSG:4326, so the
    geometry is the pair — and a copy would be two doubles stored twice, with two
    places to disagree and no rule for which wins.
    """
    columns = set(GreeceFfaIgnition.__table__.columns.keys())
    assert columns == {"id", "year", "record_number", "engage_id"}


def test_the_published_pair_comes_back_out_of_the_geometry(db_session, provider):
    """Which is what makes storing it a second time redundant rather than merely tidy."""
    db_session.add(an_ignition(provider))
    db_session.commit()

    longitude, latitude, srid = db_session.execute(select(
        func.ST_X(Ignition.geometry), func.ST_Y(Ignition.geometry),
        func.ST_SRID(Ignition.geometry),
    )).one()
    assert (longitude, latitude) == pytest.approx((23.86, 38.28))
    assert srid == greece_ffa.SOURCE_SRID


def test_a_fire_links_to_its_point(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert isinstance(stored.ignition, GreeceFfaIgnition)
    assert stored.ignition.engage_id == 970757


def test_a_fire_with_no_published_point_has_none(db_session, provider):
    """205,703 fires of 260,194: every year before 2020, and the zero pairs after it."""
    db_session.add(a_wildfire(provider, year=2003, source_sheet="2003",
                              record_number=None, engage_id=None))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.ignition_id is None
    assert stored.ignition is None


def test_the_point_and_the_fire_report_the_same_instant(db_session, provider):
    """One published time, not two: ``Ημερ/νία Έναρξης`` serves both rows."""
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    stored = db_session.scalar(select(GreeceFfaWildfire))
    assert stored.ignition.date_time == stored.start_date_time


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    """Year on both tables, and the three filters a report over this dataset applies."""
    inspector = inspect(db_session.get_bind())
    wildfire = {index["name"] for index in inspector.get_indexes("greece_ffa_wildfire")}
    ignition = {index["name"] for index in inspector.get_indexes("greece_ffa_ignition")}

    assert {"ix_greece_ffa_wildfire_year",
            "ix_greece_ffa_wildfire_record_number",
            "ix_greece_ffa_wildfire_incident_category",
            "ix_greece_ffa_wildfire_ignition_id",
            "ix_greece_ffa_wildfire_prefecture_name"} <= wildfire
    assert {"ix_greece_ffa_ignition_year",
            "ix_greece_ffa_ignition_record_number"} <= ignition
