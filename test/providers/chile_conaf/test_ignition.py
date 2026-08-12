#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`ConafIgnition`, the point a Chilean fire was reported at.

What is worth pinning here is the two-grid arrangement, which no other provider in
GisFIRE has. Chile publishes on UTM 19S for the mainland and UTM 12S for Easter
Island — 5,000 kilometres and seven zones apart — so there are two projected
columns and a ``CHECK`` that says **exactly one** of them is filled. Both halves of
that matter: neither is a fire with no published geometry, and both is a fire
claiming to be in two places.

Beside it, the published ``UTM_E``/``UTM_N``/``HUSO`` triple, which is provenance
and not a second geometry, and which is absent on more than half the archive.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import chile_conaf
from src.providers.chile_conaf.ignition import ConafIgnition

UTC = datetime.timezone.utc

#: A fire near Concepción, on the mainland grid.
POINT_32719 = "SRID=32719;POINT(670000 5920000)"

#: The same fire in EPSG:4326, near enough for a test that never compares the two.
POINT_4326 = "SRID=4326;POINT(-73.05 -36.83)"

#: A fire on Rapa Nui, on the Easter Island grid. 243 of the 95,868 are here.
POINT_32712 = "SRID=32712;POINT(660000 6997000)"

POINT_EASTER_4326 = "SRID=4326;POINT(-109.36 -27.12)"


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                            product=chile_conaf.PROVIDER_PRODUCT,
                            full_name=chile_conaf.PROVIDER_FULL_NAME,
                            url=chile_conaf.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def an_ignition(provider, **overrides) -> ConafIgnition:
    """One published point, with the coordinate triple beside it."""
    values = {
        "data_provider": provider,
        "season_start_year": 2016,
        "number": 402,
        "region_code": "08",
        "utm_easting": 670000.0,
        "utm_northing": 5920000.0,
        "utm_zone": 19,
        "utm_band": "H",
        "geometry": POINT_4326,
        "geometry_utm19s": POINT_32719,
        "geometry_utm12s": None,
        "date_time": datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        "time_zone": chile_conaf.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return ConafIgnition(**values)


def an_easter_ignition(provider, **overrides) -> ConafIgnition:
    return an_ignition(provider, geometry=POINT_EASTER_4326, geometry_utm19s=None,
                       geometry_utm12s=POINT_32712, utm_easting=660000.0,
                       utm_northing=6997000.0, utm_zone=12, utm_band=None,
                       region_code="05", time_zone=chile_conaf.EASTER_TIME_ZONE,
                       **overrides)


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------

def test_an_ignition_round_trips(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(ConafIgnition))
    assert stored.season_start_year == 2016
    assert (stored.number, stored.region_code) == (402, "08")
    assert (stored.utm_zone, stored.utm_band) == (19, "H")
    assert db_session.scalar(select(Wildfire)) is None, "an ignition is not a wildfire"


def test_it_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Ignition.__table__)) == 1
    parent = db_session.scalar(select(Ignition))
    assert parent.type == "conaf_ignition"
    assert isinstance(parent, ConafIgnition)


def test_the_season_is_required(db_session, provider):
    """It is how a season is re-imported and what every report groups on."""
    assert ConafIgnition.__table__.c.season_start_year.nullable is False

    db_session.add(an_ignition(provider, season_start_year=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The two grids
# --------------------------------------------------------------------------

def test_a_mainland_point_keeps_its_own_crs(db_session, provider):
    """32719 stored as 32719, beside the 4326 reprojection the parent holds.

    CONAF publishes metres, so the EPSG:4326 point is derived and the grid one is
    the original — the same argument :class:`~src.providers.canada_nfdb.ignition.
    NfdbIgnition` makes for EPSG:3978.
    """
    db_session.add(an_ignition(provider))
    db_session.commit()

    srids = db_session.execute(select(
        func.ST_SRID(ConafIgnition.geometry_utm19s),
        func.ST_SRID(ConafIgnition.geometry),
    )).one()
    assert tuple(srids) == (chile_conaf.SOURCE_SRID_MAINLAND, 4326)

    x, y = db_session.execute(select(
        func.ST_X(ConafIgnition.geometry_utm19s),
        func.ST_Y(ConafIgnition.geometry_utm19s),
    )).one()
    assert (x, y) == pytest.approx((670000.0, 5920000.0))


def test_an_easter_island_point_lives_on_the_other_grid(db_session, provider):
    """243 fires, on a grid seven zones west of the mainland's."""
    db_session.add(an_easter_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(ConafIgnition))
    assert stored.geometry_utm19s is None
    assert db_session.scalar(select(func.ST_SRID(ConafIgnition.geometry_utm12s))) \
        == chile_conaf.SOURCE_SRID_EASTER


def test_a_point_belongs_to_exactly_one_grid(db_session, provider):
    """Both filled is a fire claiming to be in two places 5,000 km apart."""
    db_session.add(an_ignition(provider, geometry_utm12s=POINT_32712))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_point_on_neither_grid_is_not_a_thinner_row(db_session, provider):
    """It is a row that should not have been written.

    The point is the reason a ``conaf_ignition`` exists; a report with no usable
    published geometry would simply have no ignition — except that in this archive
    there is no such report, which is why
    :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.ignition_id` is
    ``NOT NULL``.
    """
    db_session.add(an_ignition(provider, geometry_utm19s=None, geometry_utm12s=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_two_grids_are_not_coalesced(db_session, provider):
    """Metres on different grids; adding them would be adding apples to kilometres.

    A query that wants both territories at once wants the parent's EPSG:4326 point,
    which is what it is for — and which both rows carry.
    """
    db_session.add(an_ignition(provider))
    db_session.add(an_easter_ignition(provider))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(ConafIgnition.__table__)) == 2
    assert db_session.scalar(select(func.count()).where(
        func.ST_SRID(Ignition.geometry) == 4326).select_from(Ignition.__table__)) == 2


# --------------------------------------------------------------------------
# The published coordinate triple
# --------------------------------------------------------------------------

def test_the_published_triple_is_provenance_and_may_be_absent(db_session, provider):
    """52,232 of the 95,868 features publish no readable triple.

    No ``HUSO`` at all in eight mainland seasons, a zeroed pair in 2013-2014 and part
    of 2019-2020. The geometry is still there, because the geometry is the truth and
    these columns are the record of what the office typed.
    """
    db_session.add(an_ignition(provider, utm_easting=None, utm_northing=None,
                               utm_zone=None, utm_band=None))
    db_session.commit()

    stored = db_session.scalar(select(ConafIgnition))
    assert stored.utm_easting is None and stored.utm_zone is None
    assert stored.geometry_utm19s is not None


@pytest.mark.parametrize("zone", chile_conaf.UTM_ZONES)
def test_every_zone_chile_publishes_is_accepted(db_session, provider, zone):
    db_session.add(an_ignition(provider, utm_zone=zone))
    db_session.commit()

    assert db_session.scalar(select(ConafIgnition)).utm_zone == zone


def test_a_zone_chile_is_not_in_is_refused(db_session, provider):
    db_session.add(an_ignition(provider, utm_zone=31))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_published_zone_is_not_the_grid_the_geometry_is_on(db_session, provider):
    """A zone 18 fire is reprojected into zone 19 to sit in its mainland layer.

    :attr:`utm_zone` is the only record of which grid the office actually worked on,
    which is the reason for keeping a coordinate that is otherwise redundant.
    """
    db_session.add(an_ignition(provider, utm_zone=18, utm_band="H",
                               utm_easting=734013.0, utm_northing=6072270.0))
    db_session.commit()

    stored = db_session.scalar(select(ConafIgnition))
    assert stored.utm_zone == 18
    assert db_session.scalar(select(func.ST_SRID(ConafIgnition.geometry_utm19s))) \
        == chile_conaf.SOURCE_SRID_MAINLAND


def test_the_band_is_absent_where_the_season_publishes_a_bare_zone(db_session, provider):
    """``'19'`` and ``'12.0'`` carry no letter; ``'19K'`` does."""
    db_session.add(an_ignition(provider, utm_band=None))
    db_session.commit()

    assert db_session.scalar(select(ConafIgnition)).utm_band is None


# --------------------------------------------------------------------------
# Nothing identifies a fire
# --------------------------------------------------------------------------

def test_the_same_season_and_number_twice_is_accepted(db_session, provider):
    """``NUMERO_REG`` repeats within a season and even within a región.

    2021-2022 has 6,884 fires and 5,975 distinct ``(CODREG, NUMERO_REG)`` pairs. Any
    constraint here would be a claim the published data does not support.
    """
    db_session.add(an_ignition(provider))
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(ConafIgnition.__table__)) == 2


def test_the_table_constrains_no_identifier(db_session):
    """Stated against the schema, so that adding a UNIQUE later has to face this test."""
    unique = [c for c in ConafIgnition.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert unique == []
    assert not any(column.unique for column in ConafIgnition.__table__.columns)


def test_a_fire_with_no_office_number_still_has_a_point(db_session, provider):
    """Every fire of 2010-2011 and 2013-2014 publishes zero or nothing."""
    db_session.add(an_ignition(provider, number=None))
    db_session.commit()

    assert db_session.scalar(select(ConafIgnition)).number is None


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    """The season above all: it is the unit of the archives, the imports and the reports."""
    indexes = {index["name"]
               for index in inspect(db_session.get_bind()).get_indexes("conaf_ignition")}
    assert {"ix_conaf_ignition_season_start_year", "ix_conaf_ignition_number",
            "idx_conaf_ignition_geometry_utm19s",
            "idx_conaf_ignition_geometry_utm12s"} <= indexes


def test_repr_before_persist(provider):
    assert repr(an_ignition(provider)) == (
        "ConafIgnition(id=None, season_start_year=2016, number=402)")
