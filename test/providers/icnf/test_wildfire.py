#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`IcnfWildfire` model.

The two things worth pinning down here are what a row is allowed *not* to have —
the 1975-2013 layers publish almost nothing — and that the published EPSG:3763
geometry really is stored in that CRS rather than quietly reprojected.
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
from src.providers import icnf
from src.providers.icnf.fire_cause import IcnfFireCause
from src.providers.icnf.wildfire import IcnfWildfire

UTC = datetime.timezone.utc

#: A square kilometre near the origin of the Portugal TM06 grid, which is in the
#: middle of mainland Portugal.
PERIMETER_3763 = "SRID=3763;MULTIPOLYGON(((0 0, 1000 0, 1000 1000, 0 1000, 0 0)))"


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=icnf.PROVIDER_NAME, product=icnf.PROVIDER_PRODUCT,
                            full_name=icnf.PROVIDER_FULL_NAME)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def cause(db_session):
    cause = IcnfFireCause(code="125", type="Negligente", type_en="Negligent",
                          description="Queimadas para gestão de pasto para gado",
                          description_en="Burning for livestock pasture management")
    db_session.add(cause)
    db_session.commit()
    return cause


def a_wildfire(provider, **overrides) -> IcnfWildfire:
    """A fire from the modern era, with everything the 2014+ layers publish."""
    values = {
        "data_provider": provider,
        "source_layer": "ardida_2024",
        "sgif_code": "20240125102",
        "anepc_code": "20240125102",
        "year": 2024,
        "date_time_precision": icnf.PRECISION_DAY,
        "start_date_time": datetime.datetime(2024, 1, 29, tzinfo=UTC),
        "duration_minutes": 144,
        "dicofre_code": "181620",
        "district_name": "Viseu",
        "area_ha_gis": 2.76886994,
        "perimeter_etrs89_tm06": PERIMETER_3763,
    }
    values.update(overrides)
    return IcnfWildfire(**values)


def an_old_wildfire(provider, **overrides) -> IcnfWildfire:
    """A fire from 1975-2013: a year, an area, a polygon, and nothing else at all."""
    values = {
        "data_provider": provider,
        "source_layer": "ardida_1975_1989",
        "year": 1975,
        "date_time_precision": icnf.PRECISION_YEAR,
        "start_date_time": datetime.datetime(1975, 1, 1, tzinfo=UTC),
        "area_ha_gis": 65.91566807,
        "perimeter_etrs89_tm06": PERIMETER_3763,
    }
    values.update(overrides)
    return IcnfWildfire(**values)


# --------------------------------------------------------------------------
# The two eras
# --------------------------------------------------------------------------

def test_a_modern_fire_stores_everything_it_publishes(db_session, provider, cause):
    db_session.add(a_wildfire(provider, cause_id=cause.id))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(IcnfWildfire))
    assert stored.sgif_code == "20240125102"
    assert stored.duration_minutes == 144
    assert stored.dicofre_code == "181620"
    assert stored.cause.type_en == "Negligent"


def test_a_1975_fire_needs_only_a_year_an_area_and_a_polygon(db_session, provider):
    """Everything the old layers do not publish has to be nullable, or they cannot load."""
    db_session.add(an_old_wildfire(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(IcnfWildfire))
    assert stored.year == 1975
    assert stored.sgif_code is None
    assert stored.anepc_code is None
    assert stored.duration_minutes is None
    assert stored.cause_id is None
    assert stored.dicofre_code is None
    assert stored.district_name is None
    assert stored.area_ha_sgif is None
    assert stored.edition_date_time is None


def test_the_year_is_required(db_session, provider):
    """The one attribute every layer of every era publishes."""
    db_session.add(a_wildfire(provider, year=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_source_layer_is_required(db_session, provider):
    """It is the only thing identifying a fire from the years with no identifier."""
    db_session.add(a_wildfire(provider, source_layer=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_gis_area_is_required(db_session, provider):
    db_session.add(a_wildfire(provider, area_ha_gis=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

def test_the_sgif_code_is_unique(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_many_fires_may_have_no_sgif_code(db_session, provider):
    """48,861 of them do not, so the unique constraint must tolerate repeated NULLs."""
    for _ in range(3):
        db_session.add(an_old_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(IcnfWildfire)) == 3


def test_the_anepc_code_is_not_unique(db_session, provider):
    """The other agency's key, stored for traceability, not used as one."""
    db_session.add(a_wildfire(provider, sgif_code="a", anepc_code="2024010004987"))
    db_session.add(a_wildfire(provider, sgif_code="b", anepc_code="2024010004987"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(IcnfWildfire)) == 2


# --------------------------------------------------------------------------
# Date precision
# --------------------------------------------------------------------------

@pytest.mark.parametrize("precision", icnf.DATE_TIME_PRECISIONS)
def test_every_declared_precision_is_accepted(db_session, provider, precision):
    db_session.add(a_wildfire(provider, date_time_precision=precision))
    db_session.commit()

    assert db_session.scalar(select(IcnfWildfire)).date_time_precision == precision


def test_an_unknown_precision_is_rejected(db_session, provider):
    """The column is the only thing standing between a placeholder date and a real one."""
    db_session.add(a_wildfire(provider, date_time_precision="hour"))
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.commit()


def test_the_precision_is_required(db_session, provider):
    db_session.add(a_wildfire(provider, date_time_precision=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# The published geometry
# --------------------------------------------------------------------------

def test_the_published_perimeter_keeps_the_national_grid(db_session, provider):
    """3763, not 4326: a projected grid in metres is the point of storing it."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    srid = db_session.scalar(select(func.ST_SRID(IcnfWildfire.perimeter_etrs89_tm06)))
    assert srid == icnf.SOURCE_SRID == 3763


def test_the_national_grid_measures_area_in_metres(db_session, provider):
    """A square kilometre of TM06 is a square kilometre, with no geodesic function."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    area = db_session.scalar(select(func.ST_Area(IcnfWildfire.perimeter_etrs89_tm06)))
    assert area == pytest.approx(1_000_000.0)


def test_the_published_perimeter_reprojects_into_portugal(db_session, provider):
    """The TM06 origin is in the middle of the mainland, which is the sanity check."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    point = func.ST_PointOnSurface(
        func.ST_Transform(IcnfWildfire.perimeter_etrs89_tm06, 4326))
    longitude, latitude = db_session.execute(
        select(func.ST_X(point), func.ST_Y(point))).one()
    assert -10 < longitude < -6
    assert 36 < latitude < 43


def test_the_published_perimeter_may_be_absent(db_session, provider):
    """Repairing a degenerate polygon can leave nothing to store."""
    db_session.add(a_wildfire(provider, perimeter_etrs89_tm06=None))
    db_session.commit()

    assert db_session.scalar(select(IcnfWildfire)).perimeter_etrs89_tm06 is None


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_joined_table_inheritance_splits_the_columns(db_session):
    assert IcnfWildfire.__tablename__ == "icnf_wildfire"
    columns = {column["name"]
               for column in inspect(db_session.get_bind()).get_columns("icnf_wildfire")}
    assert "perimeter_etrs89_tm06" in columns
    assert "area_ha_shrubland" in columns
    # The EPSG:4326 perimeter is the generic model's and is not repeated here.
    assert "perimeter" not in columns
    assert "start_date_time" not in columns


def test_querying_the_parent_returns_the_subclass(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert isinstance(stored, IcnfWildfire)
    assert stored.year == 2024


def test_the_cause_link_must_exist(db_session, provider, cause):
    db_session.add(a_wildfire(provider, cause_id=cause.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist():
    fire = IcnfWildfire(sgif_code="20240125102", year=2024)
    assert repr(fire) == "IcnfWildfire(id=None, sgif_code='20240125102', year=2024)"
