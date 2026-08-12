#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`ConafWildfire`, a fire as CONAF's seasonal archive reports it.

Four things are pinned here.

The **perimeter is always NULL** and always will be: the polygons are a different
published product with a different ``data_provider_id``, and writing one onto a
report row would make the provenance a lie.

The **point is required**, unlike every other provider that has one. 95,868 of
95,868 published features carry a geometry, so ``ignition_id`` is ``NOT NULL`` —
a constraint the data supports, stated rather than left to a reader to wonder about.

**Half the archive has no date**, so ``date_time_precision`` is not decoration: a
``season``-precision fire starts at 1 July midnight because that is where the
importer put it, and any statistic that treats it as an observation is wrong for
49,470 fires.

And the **fourteen area columns are stored as published**, drift included, with
``area_totals_agree`` recording whether the office's own arithmetic holds.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import chile_conaf
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire

UTC = datetime.timezone.utc

POINT_4326 = "SRID=4326;POINT(-73.05 -36.83)"
POINT_32719 = "SRID=32719;POINT(670000 5920000)"


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                            product=chile_conaf.PROVIDER_PRODUCT,
                            full_name=chile_conaf.PROVIDER_FULL_NAME,
                            url=chile_conaf.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def ignition(db_session, provider):
    ignition = ConafIgnition(
        data_provider=provider, season_start_year=2016, number=402,
        region_code="08", geometry=POINT_4326, geometry_utm19s=POINT_32719,
        date_time=datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    db_session.add(ignition)
    db_session.commit()
    return ignition


@pytest.fixture
def cause(db_session):
    cause = ConafFireCause(
        cause="1.7. Tránsito de personas, vehículos o aeronaves", cause_code="1.7",
        cause_normalised="Tránsito de personas, vehículos o aeronaves",
        cause_en="Movement of people, vehicles or aircraft",
        specific_cause="1.7.1. Uso de fuego por transeúntes",
        specific_cause_code="1.7.1", scheme="pre_2023")
    db_session.add(cause)
    db_session.commit()
    return cause


def a_wildfire(provider, ignition, **overrides) -> ConafWildfire:
    """One seasonal report, with everything the archive publishes."""
    values = {
        "data_provider": provider,
        "ignition_id": ignition.id,
        "season": "2016-2017",
        "season_start_year": 2016,
        "number": 402,
        "name": "SAN GUILLERMO",
        "reporter": chile_conaf.REPORTER_CONAF,
        "region": "Biobío",
        "province": "Concepción",
        "commune": "Tomé",
        "region_code": "08",
        "province_code": "081",
        "commune_code": "08111",
        "start_place": "Camino principal",
        "fuel": "Pastizal",
        "date_time_precision": chile_conaf.PRECISION_MINUTE,
        "area_ha_pine_0_10": 1.0,
        "area_ha_pine_11_17": 2.0,
        "area_ha_pine_18_plus": 3.0,
        "area_ha_eucalyptus": 4.0,
        "area_ha_other_plantation": 5.0,
        "area_ha_plantation": 15.0,
        "area_ha_native_forest": 6.0,
        "area_ha_scrub": 7.0,
        "area_ha_grassland": 8.0,
        "area_ha_vegetation": 21.0,
        "area_ha_agricultural": 9.0,
        "area_ha_debris": 10.0,
        "area_ha_other": 19.0,
        "area_ha_total": 55.0,
        "area_totals_agree": True,
        "start_date_time": datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        "end_date_time": datetime.datetime(2017, 1, 20, 9, 0, tzinfo=UTC),
        "time_zone": chile_conaf.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return ConafWildfire(**values)


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.season == "2016-2017"
    assert (stored.number, stored.name) == (402, "SAN GUILLERMO")
    assert stored.reporter == "Conaf"
    assert (stored.region_code, stored.province_code, stored.commune_code) \
        == ("08", "081", "08111")
    assert stored.start_place == "Camino principal"
    assert stored.fuel == "Pastizal"


def test_it_is_stored_across_the_two_tables(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "conaf_wildfire"
    assert isinstance(parent, ConafWildfire)


def test_the_season_is_kept_as_published_beside_its_first_year(db_session,
                                                               provider, ignition):
    """``"2016-2017"`` is what the file says; ``2016`` is what a query groups on."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.season == "2016-2017"
    assert stored.season_start_year == chile_conaf.season_start_year(stored.season)


# --------------------------------------------------------------------------
# The perimeter, and the point
# --------------------------------------------------------------------------

def test_there_is_never_a_perimeter(db_session, provider, ignition):
    """The polygons are :mod:`src.providers.chile_conaf_magnitud`, a different product.

    They are linked the other way, from perimeter to report, which is the direction
    NBAC and REDIAM point in too: the perimeter archive is the sparse one.
    """
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).perimeter is None
    assert "perimeter" not in ConafWildfire.__table__.columns


def test_the_point_is_required(db_session, provider, ignition):
    """95,868 of 95,868 published features carry a geometry — checked, no exceptions.

    Unlike :class:`~src.providers.canada_nfdb.wildfire.NfdbWildfire`, where a handful
    do not, and unlike Spain and Greece, where most do not. It is a constraint the
    data supports, so it is stated rather than left as an accident.
    """
    assert ConafWildfire.__table__.c.ignition_id.nullable is False

    db_session.add(a_wildfire(provider, ignition, ignition_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_fire_links_to_its_point(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert isinstance(stored.ignition, ConafIgnition)
    assert stored.ignition.region_code == "08"


def test_the_point_and_the_report_carry_the_same_instant(db_session, provider,
                                                         ignition):
    """One published start serves both rows; CONAF does not publish two."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.ignition.date_time == stored.start_date_time


# --------------------------------------------------------------------------
# How much of the instant is real
# --------------------------------------------------------------------------

@pytest.mark.parametrize("precision", chile_conaf.DATE_TIME_PRECISIONS)
def test_every_documented_precision_is_accepted(db_session, provider, ignition,
                                                precision):
    db_session.add(a_wildfire(provider, ignition, date_time_precision=precision))
    db_session.commit()

    assert db_session.scalar(select(ConafWildfire)).date_time_precision == precision


def test_a_precision_outside_the_documented_three_is_refused(db_session, provider,
                                                             ignition):
    db_session.add(a_wildfire(provider, ignition, date_time_precision="hour"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_precision_is_required(db_session, provider, ignition):
    """No default and no NULL: a report that does not filter on it reports on 1 July."""
    assert ConafWildfire.__table__.c.date_time_precision.nullable is False


def test_a_season_precision_fire_starts_at_the_first_instant_of_its_season(
        db_session, provider, ignition):
    """49,470 fires. Their start is a placeholder, not an observation.

    Grouping these by month puts half the archive in July; subtracting the start
    from an end date gives durations of up to a year. The column beside it is the
    only thing that says so.
    """
    start, _ = chile_conaf.season_window(2016)
    db_session.add(a_wildfire(
        provider, ignition,
        date_time_precision=chile_conaf.PRECISION_SEASON,
        start_date_time=start.replace(tzinfo=UTC), end_date_time=None))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    started = stored.start_date_time.astimezone(UTC)
    assert (started.month, started.day) == (7, 1)
    assert stored.date_time_precision != chile_conaf.PRECISION_MINUTE


def test_a_day_precision_fire_keeps_its_midnight(db_session, provider, ignition):
    """Local midnight is a perfectly good instant and a completely invented time of day.

    The stored value is an instant, so it comes back in whatever zone the session is
    in; what the precision column promises is about the *published* cell, not about
    what hour a reader's clock shows.
    """
    midnight = datetime.datetime(2017, 1, 18, 0, 0, tzinfo=UTC)
    db_session.add(a_wildfire(
        provider, ignition, date_time_precision=chile_conaf.PRECISION_DAY,
        start_date_time=midnight))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.start_date_time.astimezone(UTC) == midnight
    assert stored.date_time_precision == chile_conaf.PRECISION_DAY


def test_a_fire_that_was_never_declared_out_has_no_end(db_session, provider, ignition):
    """2017-2018 publishes starts and no ends at all."""
    db_session.add(a_wildfire(provider, ignition, end_date_time=None))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).end_date_time is None


# --------------------------------------------------------------------------
# Who filed it
# --------------------------------------------------------------------------

@pytest.mark.parametrize("reporter", chile_conaf.REPORTERS)
def test_both_reporting_systems_are_accepted(db_session, provider, ignition, reporter):
    """CONAF's regional offices and the forestry companies' own brigades."""
    db_session.add(a_wildfire(provider, ignition, reporter=reporter))
    db_session.commit()

    assert db_session.scalar(select(ConafWildfire)).reporter == reporter


def test_a_reporter_outside_the_published_two_is_refused(db_session, provider,
                                                         ignition):
    db_session.add(a_wildfire(provider, ignition, reporter="Bomberos"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_unpublished_reporter_is_allowed(db_session, provider, ignition):
    """``AMBITO`` is not published in every season, and silence is not a third system."""
    db_session.add(a_wildfire(provider, ignition, reporter=None))
    db_session.commit()

    assert db_session.scalar(select(ConafWildfire)).reporter is None


# --------------------------------------------------------------------------
# Where it burnt
# --------------------------------------------------------------------------

def test_the_administrative_names_may_be_absent_while_the_codes_are_not(
        db_session, provider, ignition):
    """Six of the fifteen mainland seasons publish the codes and not the names."""
    db_session.add(a_wildfire(provider, ignition, region=None, province=None,
                              commune=None))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.region is None
    assert stored.commune_code == "08111"


def test_the_published_codes_nest(db_session, provider, ignition):
    """A comuna's first three digits are its provincia and its first two its región.

    Which is what makes the zero-padding matter rather than being cosmetic: unpadded,
    ``'5801'`` and ``'05801'`` are two comunas instead of one.
    """
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.commune_code.startswith(stored.province_code)
    assert stored.province_code.startswith(stored.region_code)


def test_conafs_own_codes_are_not_the_resolved_boundary(db_session, provider,
                                                        ignition):
    """``region_code`` comes from the file; ``admin_boundary_id`` from a spatial join.

    A cross-provider query uses the second. Conflating them would make Chile's
    boundaries answerable only in Chile's own vocabulary.
    """
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.region_code == "08"
    assert stored.admin_boundary_id is None


# --------------------------------------------------------------------------
# The fourteen areas
# --------------------------------------------------------------------------

def test_the_published_areas_round_trip(db_session, provider, ignition):
    """The pine bands are stand ages in years — 0-10, 11-17, 18 or more — not sizes."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.area_ha_pine_0_10 == pytest.approx(1.0)
    assert stored.area_ha_pine_11_17 == pytest.approx(2.0)
    assert stored.area_ha_pine_18_plus == pytest.approx(3.0)
    assert stored.area_ha_grassland == pytest.approx(8.0)
    assert stored.area_ha_total == pytest.approx(55.0)


def test_the_subtotals_are_stored_and_not_recomputed(db_session, provider, ignition):
    """``SUPERFICIE`` is the office's own figure for the fire, drift and all.

    The arithmetic holds on 90,128 of the 95,831 readable rows and drifts on the
    rest, almost all in 2010-2011, 2011-2012 and 2015-2016. Where it drifts, the
    disagreement is the datum.
    """
    db_session.add(a_wildfire(provider, ignition, area_ha_total=999.0,
                              area_totals_agree=False))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.area_ha_total == pytest.approx(999.0)
    assert stored.area_ha_plantation == pytest.approx(15.0)
    assert stored.area_totals_agree is False


def test_whether_the_office_arithmetic_holds_is_recorded_not_derived(
        db_session, provider, ignition):
    """The cheapest possible answer to *how much of this total can I stand on*.

    Deriving it means summing four nullable numerics in every query that cares.
    """
    assert ConafWildfire.__table__.c.area_totals_agree.nullable is False

    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()
    stored = db_session.scalar(select(ConafWildfire))
    assert stored.area_totals_agree is True
    assert (stored.area_ha_plantation + stored.area_ha_vegetation
            + stored.area_ha_other) == stored.area_ha_total


def test_a_reported_zero_area_is_an_answer(db_session, provider, ignition):
    """Zero hectares of eucalyptus is a measurement, not a missing value."""
    db_session.add(a_wildfire(provider, ignition, area_ha_eucalyptus=0.0,
                              area_ha_total=0.0, area_totals_agree=False))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.area_ha_eucalyptus == 0
    assert stored.area_ha_eucalyptus is not None


def test_a_negative_total_is_refused(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition, area_ha_total=-1.0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_unpublished_area_is_null_rather_than_zero(db_session, provider, ignition):
    """Not every season publishes every component."""
    db_session.add(a_wildfire(provider, ignition, area_ha_debris=None))
    db_session.commit()

    assert db_session.scalar(select(ConafWildfire)).area_ha_debris is None


# --------------------------------------------------------------------------
# The cause
# --------------------------------------------------------------------------

def test_a_fire_carries_its_published_classification(db_session, provider, ignition,
                                                     cause):
    db_session.add(a_wildfire(provider, ignition, cause_id=cause.id))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.cause.cause_normalised == "Tránsito de personas, vehículos o aeronaves"
    assert stored.cause.scheme == "pre_2023"


def test_a_fire_that_publishes_no_cause_at_all_has_none(db_session, provider,
                                                        ignition):
    """840 fires publish neither half of the classification."""
    db_session.add(a_wildfire(provider, ignition, cause_id=None))
    db_session.commit()

    stored = db_session.scalar(select(ConafWildfire))
    assert stored.cause_id is None and stored.cause is None


def test_many_fires_share_one_classification(db_session, provider, ignition, cause):
    """The catalogue is a lookup table, not a per-fire row."""
    for _ in range(3):
        db_session.add(a_wildfire(provider, ignition, cause_id=cause.id))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(ConafFireCause.__table__)) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ConafWildfire.__table__)) == 3


# --------------------------------------------------------------------------
# Nothing identifies a fire
# --------------------------------------------------------------------------

def test_the_same_season_number_and_name_twice_is_accepted(db_session, provider,
                                                           ignition):
    """Only 2023-2024 is unique on ``(CODREG, NUMERO_REG)``; no season before it is."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(ConafWildfire.__table__)) == 2


def test_the_table_constrains_no_identifier(db_session):
    unique = [c for c in ConafWildfire.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert unique == []
    assert not any(column.unique for column in ConafWildfire.__table__.columns)


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    """The season, the cause and the precision: every report over this dataset uses all three."""
    indexes = {index["name"]
               for index in inspect(db_session.get_bind()).get_indexes("conaf_wildfire")}
    assert {"ix_conaf_wildfire_season_start_year", "ix_conaf_wildfire_number",
            "ix_conaf_wildfire_reporter", "ix_conaf_wildfire_cause_id",
            "ix_conaf_wildfire_date_time_precision",
            "ix_conaf_wildfire_ignition_id"} <= indexes


def test_repr_before_persist(provider, ignition):
    assert repr(a_wildfire(provider, ignition)) == (
        "ConafWildfire(id=None, season='2016-2017', number=402, name='SAN GUILLERMO')")
