#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`ConaforWildfire` model.

The things worth pinning down: what a row from each end of the series is allowed
*not* to have — 2012 publishes no vegetation, type or impact, and 2022-2023
publish no area strata — that the published key really is unique, and that there
is exactly one perimeter, in the CRS CONAFOR published it in.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import mexico_conafor
from src.providers.mexico_conafor.fire_cause import ConaforFireCause
from src.providers.mexico_conafor.wildfire import ConaforWildfire

UTC = datetime.timezone.utc

#: A small square in Aguascalientes, in the CRS CONAFOR publishes in.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((-102.30 21.88, -102.29 21.88, "
                  "-102.29 21.89, -102.30 21.89, -102.30 21.88)))")


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=mexico_conafor.PROVIDER_NAME,
                            product=mexico_conafor.PROVIDER_PRODUCT,
                            full_name=mexico_conafor.PROVIDER_FULL_NAME)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def cause(db_session):
    cause = ConaforFireCause(cause="Fogatas", cause_normalised="Fogatas",
                             cause_en="Campfires",
                             specific_cause="Fogatas de paseantes",
                             specific_cause_en="Campfires of day trippers")
    db_session.add(cause)
    db_session.commit()
    return cause


def a_wildfire(provider, **overrides) -> ConaforWildfire:
    """A 2019 fire: the richest layer, with everything the series ever publishes."""
    values = {
        "data_provider": provider,
        "fire_code": "19-01-0102",
        "year": 2019,
        "source_layer": "incendios_2019",
        "state_code": 1,
        "state_name": "Aguascalientes",
        "municipality_code": 2,
        "municipality_name": "Asientos",
        "property_name": "Tanque Juarez",
        "date_time_precision": mexico_conafor.PRECISION_DAY,
        # Local midnight in June 2019, when Mexico City was still on summer time at
        # UTC-5. In January 2023, after DST was abolished, the same local midnight
        # is 06:00 UTC — which is why the zone is stored by name and not as an
        # offset. See src/data_model/wildfire.py.
        "start_date_time": datetime.datetime(2019, 6, 7, 5, tzinfo=UTC),
        "end_date_time": datetime.datetime(2019, 6, 8, 5, tzinfo=UTC),
        "time_zone": "America/Mexico_City",
        "fire_type": "Superficial",
        "impact_level": "Impacto Minimo",
        "vegetation_type": "Bosque de Pino-Encino - BPQ",
        "vegetation_type_code": "BPQ",
        "protected_area_name": "Iztaccihuatl-Popocatepetl",
        "area_ha_protected": 12.5,
        "area_ha": 8.53,
        "area_ha_tree": 0.0,
        "area_ha_regeneration": 0.0,
        "area_ha_shrub": 1.28,
        "area_ha_herbaceous": 7.25,
        "area_ha_litter": 0.0,
        "area_ha_organic_soil": 0.0,
        "perimeter": PERIMETER_4326,
    }
    values.update(overrides)
    return ConaforWildfire(**values)


def a_2012_wildfire(provider, **overrides) -> ConaforWildfire:
    """The odd layer out: no ANP, no TIPVEG, no TIPOINC, no TIPIMPAC, CLAVE for the key."""
    values = {
        "data_provider": provider,
        "fire_code": "12-01-0012",
        "year": 2012,
        "source_layer": "incendios_2012",
        "state_code": 1,
        "state_name": "Aguascalientes",
        "municipality_name": "Aguascalientes",
        "property_name": "Cerro de los Gallos",
        "date_time_precision": mexico_conafor.PRECISION_DAY,
        "start_date_time": datetime.datetime(2012, 6, 9, 5, tzinfo=UTC),
        "time_zone": "America/Mexico_City",
        "area_ha": 64.0,
        "perimeter": PERIMETER_4326,
    }
    values.update(overrides)
    return ConaforWildfire(**values)


def a_2023_wildfire(provider, **overrides) -> ConaforWildfire:
    """The newest layer: no PREDIO, none of the six strata, and the only POLIGONO."""
    values = {
        "data_provider": provider,
        "fire_code": "23-01-0001",
        "year": 2023,
        "source_layer": "incendios_2023",
        "state_code": 1,
        "state_name": "Aguascalientes",
        "municipality_code": 1,
        "municipality_name": "Aguascalientes",
        "date_time_precision": mexico_conafor.PRECISION_DAY,
        "start_date_time": datetime.datetime(2023, 1, 10, 6, tzinfo=UTC),
        "time_zone": "America/Mexico_City",
        "fire_type": "Superficial",
        "impact_level": "Impacto Minimo",
        "vegetation_type": "Pastizal Natural",
        "area_ha": 3.41,
        "perimeter_source": mexico_conafor.PERIMETER_SOURCE_IMAGE,
        "perimeter": PERIMETER_4326,
    }
    values.update(overrides)
    return ConaforWildfire(**values)


# --------------------------------------------------------------------------
# The three eras of the schema
# --------------------------------------------------------------------------

def test_a_2019_fire_stores_everything_the_series_publishes(db_session, provider, cause):
    db_session.add(a_wildfire(provider, cause_id=cause.id))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(ConaforWildfire))
    assert stored.fire_code == "19-01-0102"
    assert stored.state_code == 1
    assert stored.municipality_code == 2
    assert stored.vegetation_type_code == "BPQ"
    assert stored.area_ha_organic_soil == 0.0
    assert stored.cause.cause_en == "Campfires"


def test_a_2012_fire_needs_only_a_key_a_place_a_date_and_an_area(db_session, provider):
    """2012 publishes none of the classification attributes; it still has to load."""
    db_session.add(a_2012_wildfire(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(ConaforWildfire))
    assert stored.year == 2012
    assert stored.municipality_code is None
    assert stored.fire_type is None
    assert stored.impact_level is None
    assert stored.vegetation_type is None
    assert stored.protected_area_name is None
    assert stored.cause_id is None


def test_a_2023_fire_has_a_total_and_none_of_the_six_strata(db_session, provider):
    """14,231 fires of 2022-2023 publish an area with no breakdown at all."""
    db_session.add(a_2023_wildfire(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(ConaforWildfire))
    assert stored.area_ha == 3.41
    assert stored.area_ha_tree is None
    assert stored.area_ha_regeneration is None
    assert stored.area_ha_shrub is None
    assert stored.area_ha_herbaceous is None
    assert stored.area_ha_litter is None
    assert stored.area_ha_organic_soil is None
    # ...and no PREDIO either, which only 2023 drops.
    assert stored.property_name is None


def test_only_2023_says_how_its_perimeter_was_drawn(db_session, provider):
    """POLIGONO is published by one layer, so it is NULL on 38,401 of 45,914 rows."""
    db_session.add(a_2023_wildfire(provider))
    db_session.add(a_wildfire(provider))
    db_session.commit()

    sources = {row.fire_code: row.perimeter_source
               for row in db_session.scalars(select(ConaforWildfire))}
    assert sources["23-01-0001"] == "IMAGEN"
    assert sources["19-01-0102"] is None


def test_a_fire_may_have_no_perimeter(db_session, provider):
    """Nine features of the 2012 layer carry attributes and an empty shape."""
    db_session.add(a_2012_wildfire(provider, perimeter=None))
    db_session.commit()

    assert db_session.scalar(select(ConaforWildfire)).perimeter is None


# --------------------------------------------------------------------------
# What a row cannot do without
# --------------------------------------------------------------------------

@pytest.mark.parametrize("column", [
    "fire_code", "year", "source_layer", "state_code", "state_name",
    "municipality_name", "date_time_precision",
])
def test_the_required_columns_are_required(db_session, provider, column):
    db_session.add(a_wildfire(provider, **{column: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_burnt_area_may_be_absent(db_session, provider):
    """One fire in 45,914 leaves AREA_HA empty and publishes everything else.

    ``21-24-0078``, San Luis Potosí, December 2021: a key, a municipality, a
    *predio*, a cause, both dates, a 6.41 ha herbaceous stratum and a polygon. A
    NOT NULL here would delete it.
    """
    db_session.add(a_wildfire(provider, fire_code="21-24-0078", area_ha=None))
    db_session.commit()

    stored = db_session.scalar(select(ConaforWildfire))
    assert stored.area_ha is None
    assert stored.area_ha_herbaceous == pytest.approx(7.25)


# --------------------------------------------------------------------------
# The published key
# --------------------------------------------------------------------------

def test_the_fire_code_is_unique(db_session, provider):
    """45,909 distinct values in 45,914 rows; the five repeats are exact duplicates."""
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_same_sequence_in_two_states_is_two_fires(db_session, provider):
    """The state code is inside the key, which is why it does not collide."""
    db_session.add(a_wildfire(provider, fire_code="19-01-0102"))
    db_session.add(a_wildfire(provider, fire_code="19-20-0102", state_code=20,
                              state_name="Oaxaca", municipality_name="Atatlahuca"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(ConaforWildfire)) == 2


def test_the_same_sequence_in_two_years_is_two_fires(db_session, provider):
    db_session.add(a_wildfire(provider, fire_code="19-01-0102", year=2019))
    db_session.add(a_wildfire(provider, fire_code="20-01-0102", year=2020,
                              source_layer="incendios_2020"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(ConaforWildfire)) == 2


def test_the_state_name_is_not_the_key(db_session, provider):
    """Distrito Federal and Ciudad de México are one state either side of 2016."""
    db_session.add(a_wildfire(provider, fire_code="14-09-0001", year=2014,
                              source_layer="incendios_2014",
                              state_code=9, state_name="Distrito Federal",
                              municipality_name="Tlalpan"))
    db_session.add(a_wildfire(provider, fire_code="20-09-0001", year=2020,
                              source_layer="incendios_2020",
                              state_code=9, state_name="Ciudad de Mexico",
                              municipality_name="Tlalpan"))
    db_session.commit()

    grouped = db_session.scalars(
        select(ConaforWildfire).where(ConaforWildfire.state_code == 9)).all()
    assert len(grouped) == 2
    assert len({row.state_name for row in grouped}) == 2


# --------------------------------------------------------------------------
# Date precision
# --------------------------------------------------------------------------

@pytest.mark.parametrize("precision", mexico_conafor.DATE_TIME_PRECISIONS)
def test_every_declared_precision_is_accepted(db_session, provider, precision):
    db_session.add(a_wildfire(provider, date_time_precision=precision))
    db_session.commit()

    assert db_session.scalar(select(ConaforWildfire)).date_time_precision == precision


def test_an_unknown_precision_is_rejected(db_session, provider):
    """No layer publishes a time, so 'minute' is not a thing this dataset can claim."""
    db_session.add(a_wildfire(provider, date_time_precision="minute"))
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.commit()


def test_an_end_date_is_optional(db_session, provider):
    """Two published FECHALIQ values in the archive cannot be read at all."""
    db_session.add(a_wildfire(provider, end_date_time=None))
    db_session.commit()

    assert db_session.scalar(select(ConaforWildfire)).end_date_time is None


def test_the_local_reading_comes_back_through_the_stored_zone(db_session, provider):
    """Local midnight is the placeholder for the hours the archive never publishes.

    And it comes back as midnight across the 2022 abolition of daylight saving
    only because the zone is stored by name: the 2019 fire is at UTC-5 and the
    2023 one at UTC-6, on the same published wall clock.
    """
    db_session.add(a_wildfire(provider))
    db_session.add(a_2023_wildfire(provider))
    db_session.commit()

    local = dict(db_session.execute(
        select(ConaforWildfire.fire_code,
               func.timezone(Wildfire.time_zone, Wildfire.start_date_time))).all())
    assert local["19-01-0102"] == datetime.datetime(2019, 6, 7, 0, 0)
    assert local["23-01-0001"] == datetime.datetime(2023, 1, 10, 0, 0)


# --------------------------------------------------------------------------
# The perimeter
# --------------------------------------------------------------------------

def test_the_perimeter_is_stored_in_the_crs_conafor_publishes(db_session, provider):
    """4326, and there is no second one: there is no national grid to keep."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    srid = db_session.scalar(select(func.ST_SRID(Wildfire.perimeter)))
    assert srid == mexico_conafor.SOURCE_SRID == 4326


def test_the_perimeter_lands_in_mexico(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    point = func.ST_PointOnSurface(Wildfire.perimeter)
    longitude, latitude = db_session.execute(
        select(func.ST_X(point), func.ST_Y(point))).one()
    assert -118 < longitude < -86
    assert 14 < latitude < 33


def test_a_multipart_perimeter_is_storable(db_session, provider):
    """6,661 of the 45,914 published polygons are multipart."""
    two_parts = ("SRID=4326;MULTIPOLYGON("
                 "((-102.30 21.88, -102.29 21.88, -102.29 21.89, -102.30 21.89, -102.30 21.88)),"
                 "((-102.20 21.78, -102.19 21.78, -102.19 21.79, -102.20 21.79, -102.20 21.78)))")
    db_session.add(a_wildfire(provider, perimeter=two_parts))
    db_session.commit()

    assert db_session.scalar(select(func.ST_NumGeometries(Wildfire.perimeter))) == 2


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_joined_table_inheritance_splits_the_columns(db_session):
    assert ConaforWildfire.__tablename__ == "conafor_wildfire"
    columns = {column["name"]
               for column in inspect(db_session.get_bind()).get_columns("conafor_wildfire")}
    assert "fire_code" in columns
    assert "area_ha_organic_soil" in columns
    # The perimeter and the dates are the generic model's and are not repeated here.
    assert "perimeter" not in columns
    assert "start_date_time" not in columns


def test_the_table_carries_no_second_geometry(db_session):
    """Unlike ICNF, NBAC, DARPA and REDIAM: CONAFOR publishes in 4326 already."""
    columns = inspect(db_session.get_bind()).get_columns("conafor_wildfire")
    assert not [column for column in columns
                if column["type"].__class__.__name__.lower().startswith("geometry")]


def test_querying_the_parent_returns_the_subclass(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert isinstance(stored, ConaforWildfire)
    assert stored.year == 2019


def test_the_cause_link_must_exist(db_session, provider, cause):
    db_session.add(a_wildfire(provider, cause_id=cause.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    fire = ConaforWildfire(fire_code="23-01-0001", year=2023)
    assert repr(fire) == "ConaforWildfire(id=None, fire_code='23-01-0001', year=2023)"
