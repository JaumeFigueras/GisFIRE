#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`EgifWildfireReport` detail model.

The table exists for two reasons and both are checked here: its presence records
that a fire has been read from the XML export, and it is the only place the
holdover interval is stored.
"""

import datetime

import pytest

from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.providers import egif
from src.providers.egif.ignition import EgifIgnition
from src.providers.egif.wildfire import EgifWildfire
from src.providers.egif.wildfire_report import EgifWildfireReport

UTC = datetime.timezone.utc


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=egif.PROVIDER_NAME, product=egif.PROVIDER_PRODUCT,
                            full_name=egif.PROVIDER_FULL_NAME)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def wildfire(db_session, provider):
    """The first fire of the Barcelona 2020 XML sample."""
    ignition = EgifIgnition(
        data_provider=provider, report_number="2020080001",
        geometry="SRID=4326;POINT(1.85254312549163 41.4441304358167)",
        date_time=datetime.datetime(2020, 1, 1, 15, 30, tzinfo=UTC),
        time_zone=egif.DEFAULT_TIME_ZONE,
        utm_zone=31, utm_x=404147.0, utm_y=4588697.0, datum=egif.DATUM_ETRS89)
    wildfire = EgifWildfire(
        data_provider=provider, report_number="2020080001", campaign=2020,
        ignition=ignition, province_ine_code="08",
        start_date_time=datetime.datetime(2020, 1, 1, 15, 30, tzinfo=UTC),
        end_date_time=datetime.datetime(2020, 1, 1, 16, 30, tzinfo=UTC),
        time_zone=egif.DEFAULT_TIME_ZONE)
    db_session.add(ignition)
    db_session.add(wildfire)
    db_session.commit()
    return wildfire


def a_report(wildfire, **overrides) -> EgifWildfireReport:
    values = {
        "id": wildfire.id,
        "control_date_time": datetime.datetime(2020, 1, 1, 16, 15, tzinfo=UTC),
        "first_ground_response_date_time": datetime.datetime(2020, 1, 1, 15, 35, tzinfo=UTC),
        "first_notification_from_112": True,
        "detected_by_code": "5",
        "responsibility_grade_code": "2",
        "days_since_storm": 0,
        "cause_investigated_code": "1",
        "cause_certainty_code": "2",
        "offender_identified_code": "2",
        "activity_authorisation_code": "2",
        "day_class_code": "1",
        "weather_station_code": "080055",
        "weather_observation_time": datetime.time(16, 35),
        "days_since_rain": 27,
        "max_temperature_celsius": 8.0,
        "relative_humidity_percent": 80.0,
        "wind_speed_km_h": 8.0,
        "wind_direction_degrees": 310,
        "max_severity_level": 0,
    }
    values.update(overrides)
    return EgifWildfireReport(**values)


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

def test_a_fire_read_only_from_the_excel_export_has_no_report(db_session, wildfire):
    """Which is the whole provenance mechanism: no flag column, just no row."""
    assert db_session.scalar(select(EgifWildfireReport)) is None


def test_a_fire_read_from_the_xml_gains_one(db_session, wildfire):
    db_session.add(a_report(wildfire))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.wildfire.report_number == "2020080001"


def test_a_fire_can_have_at_most_one_report(db_session, wildfire):
    """The primary key is also the foreign key, so the 1:1 is structural."""
    db_session.add(a_report(wildfire))
    db_session.commit()
    db_session.add(a_report(wildfire, days_since_storm=3))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_report_cannot_exist_without_its_fire(db_session):
    db_session.add(EgifWildfireReport(id=999999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_finding_the_fires_still_waiting_for_their_xml(db_session, provider, wildfire):
    """``LEFT JOIN ... WHERE report IS NULL`` is how a partial import is resumed."""
    ignition = EgifIgnition(
        data_provider=provider, report_number="2020080002",
        geometry="SRID=4326;POINT(1.9 41.5)",
        date_time=datetime.datetime(2020, 2, 1, 12, 0, tzinfo=UTC),
        utm_zone=31, utm_x=404000.0, utm_y=4588000.0, datum=egif.DATUM_ETRS89)
    second = EgifWildfire(
        data_provider=provider, report_number="2020080002", campaign=2020,
        ignition=ignition, province_ine_code="08",
        start_date_time=datetime.datetime(2020, 2, 1, 12, 0, tzinfo=UTC))
    db_session.add_all([ignition, second])
    db_session.add(a_report(wildfire))
    db_session.commit()

    missing = db_session.scalars(
        select(EgifWildfire)
        .outerjoin(EgifWildfireReport, EgifWildfireReport.id == EgifWildfire.id)
        .where(EgifWildfireReport.id.is_(None))
    ).all()
    assert [row.report_number for row in missing] == ["2020080002"]


# --------------------------------------------------------------------------
# The holdover interval
# --------------------------------------------------------------------------

def test_the_holdover_interval_is_stored(db_session, wildfire):
    """Published nowhere else — not in the Excel, not in the ICNF, GWIS or GFA data."""
    db_session.add(a_report(wildfire, days_since_storm=12))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfireReport)).days_since_storm == 12


def test_zero_days_since_storm_means_no_storm_rather_than_the_same_day(
        db_session, wildfire):
    """90 of the 98 fires in the Barcelona sample carry 0, and none of them is a
    lightning fire. A query for holdovers has to exclude zero, not include it as
    an interval of nought days — which is why the column is stored as published
    and not normalised to NULL."""
    db_session.add(a_report(wildfire, days_since_storm=0))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfireReport)).days_since_storm == 0


# --------------------------------------------------------------------------
# Weather
# --------------------------------------------------------------------------

def test_the_weather_observation_keeps_only_its_time_of_day(db_session, wildfire):
    """The published date is the data-entry date, not the observation's.

    A fire detected on 2020-01-01 carries an observation stamped 2023-12-18. The
    time of day is right and the date is not, so only the time is stored — a
    column that cannot hold the wrong part.
    """
    assert isinstance(
        inspect(db_session.get_bind()).get_columns("egif_wildfire_report"), list)
    db_session.add(a_report(wildfire))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.weather_observation_time == datetime.time(16, 35)
    assert not hasattr(stored.weather_observation_time, "year")


def test_the_weather_block_may_be_missing_entirely(db_session, wildfire):
    db_session.add(a_report(
        wildfire, weather_station_code=None, weather_observation_time=None,
        days_since_rain=None, max_temperature_celsius=None,
        relative_humidity_percent=None, wind_speed_km_h=None,
        wind_direction_degrees=None))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfireReport)).max_temperature_celsius is None


# --------------------------------------------------------------------------
# Times and codes
# --------------------------------------------------------------------------

def test_the_control_instant_sits_between_the_parents_two(db_session, wildfire):
    """Contained but not out — the instant most fire-behaviour work wants, and one
    the Excel export drops."""
    db_session.add(a_report(wildfire))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.wildfire.start_date_time <= stored.control_date_time
    assert stored.control_date_time <= stored.wildfire.end_date_time


def test_the_response_times_are_optional(db_session, wildfire):
    """Only ``llegadapmt`` is filled on the sample's first fire; the other three
    arrivals are empty elements."""
    db_session.add(a_report(wildfire))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.first_ground_response_date_time is not None
    assert stored.first_aerial_response_date_time is None
    assert stored.first_helitransported_response_date_time is None
    assert stored.first_coordination_response_date_time is None


def test_the_unlabelled_codes_are_stored_as_text(db_session, wildfire):
    """They point into catalogues behind a login, so they are kept bare and
    labelled later. Text because they are identifiers, and because one field in
    this family is 0-based while its neighbours are 1-based."""
    db_session.add(a_report(wildfire, detected_by_code="05"))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfireReport)).detected_by_code == "05"


def test_the_severity_level_is_an_ordinal_not_a_lookup(db_session, wildfire):
    """``idnivelgravedadmaximo`` is the *Índice de Gravedad Potencial* itself, 0-3,
    despite the ``id`` prefix every other field in the block shares."""
    db_session.add(a_report(wildfire, max_severity_level=3))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.max_severity_level == 3
    assert isinstance(stored.max_severity_level, int)


# --------------------------------------------------------------------------
# The multi-valued code lists
# --------------------------------------------------------------------------

def test_the_fuel_model_is_a_set_of_codes(db_session, wildfire):
    """``RelModeloCombustionPif`` is one-to-many and carries a code and nothing else.

    Across the 29,926 fires of the 2020-2023 export no fire ever repeats a code
    within the relation, so it is a set and an array holds it losslessly — instead
    of a child table and a join to answer "what was burning".
    """
    db_session.add(a_report(wildfire, fuel_model_codes=["2", "3"]))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.fuel_model_codes == ["2", "3"]


def test_a_ground_fire_is_queryable_beside_the_holdover_interval(db_session, wildfire):
    """The pair this migration exists for.

    ``fire_type_codes`` containing ``'3'`` is *de subsuelo* — a fire smouldering
    below the litter, which is the mechanism by which a strike becomes a fire days
    later. Together with a non-zero ``days_since_storm`` it makes a long holdover
    testable instead of merely asserted.
    """
    db_session.add(a_report(wildfire, days_since_storm=12,
                            fire_type_codes=["1", "3"]))
    db_session.commit()

    found = db_session.scalars(
        select(EgifWildfireReport)
        .where(EgifWildfireReport.fire_type_codes.any("3"))
        .where(EgifWildfireReport.days_since_storm > 0)
    ).all()
    assert [row.days_since_storm for row in found] == [12]


def test_a_single_valued_list_is_still_a_list(db_session, wildfire):
    """Most fires have one fire type; the column does not special-case that."""
    db_session.add(a_report(wildfire, fire_type_codes=["1"]))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfireReport)).fire_type_codes == ["1"]


@pytest.mark.parametrize("column", ["fuel_model_codes", "fire_type_codes",
                                    "start_area_type_codes", "started_next_to_codes"])
def test_a_code_list_may_be_absent(db_session, wildfire, column):
    """``RelTipoAreaIniciadoPif`` is on 5,480 fires in 2004-2005 and 38,267 in
    2020-2023, so an empty list and a missing block are both normal — and NULL is
    kept distinct from ``[]`` because "the export said nothing" is not "the report
    said none"."""
    db_session.add(a_report(wildfire, **{column: None}))
    db_session.commit()

    assert getattr(db_session.scalar(select(EgifWildfireReport)), column) is None


def test_the_code_lists_are_text_like_their_scalar_neighbours(db_session, wildfire):
    """They are identifiers, not quantities — the reason every other code column on
    this table is text too. ``10`` occurs in ``started_next_to_codes`` and is not on
    the 2011 form at all, which is exactly the kind of value that must survive
    unexamined."""
    db_session.add(a_report(wildfire, started_next_to_codes=["10"],
                            started_next_to_other="Ribera del río"))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfireReport))
    assert stored.started_next_to_codes == ["10"]
    assert all(isinstance(code, str) for code in stored.started_next_to_codes)
    assert stored.started_next_to_other == "Ribera del río"


def test_repr_before_persist(wildfire):
    assert repr(a_report(wildfire)) == f"EgifWildfireReport(id={wildfire.id})"
