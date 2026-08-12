#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NFDB models and the provider constants.

Five things are worth pinning down here: that a fire report has no perimeter and
never will, the point living on a row of its own; that the published EPSG:3978 point
is stored in that CRS as well as reprojected, which is where this provider parts
company with Greece; that **nothing identifies a fire**, so neither table constrains
an identifier; that the ``-999`` year sentinel and the coordinates outside Canada are
recognised rather than imported; and that ``N`` is constrained but is not a lightning
category.
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
from src.providers import canada_nfdb
from src.providers.canada_nfdb.ignition import NfdbIgnition
from src.providers.canada_nfdb.wildfire import NfdbWildfire

UTC = datetime.timezone.utc

#: A point in NAD83 / Canada Atlas Lambert metres, somewhere in Alberta.
POINT_3978 = "SRID=3978;POINT(-1200000 1500000)"

#: The same fire in EPSG:4326, near enough for a test that never compares the two.
POINT_4326 = "SRID=4326;POINT(-114.0 55.0)"


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=canada_nfdb.PROVIDER_NAME,
                            product=canada_nfdb.PROVIDER_PRODUCT,
                            full_name=canada_nfdb.PROVIDER_FULL_NAME,
                            url=canada_nfdb.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> NfdbWildfire:
    """One agency fire report, with everything the archive publishes."""
    values = {
        "data_provider": provider,
        "nfdb_fire_id": "AB-2023-0001",
        "agency_fire_id": "LWF-042",
        "fire_name": "Sturgeon Lake",
        "src_agency": "AB",
        "nat_park": None,
        "year": 2023,
        "size_ha": 12345.6,
        "fire_cause": canada_nfdb.CAUSE_NATURAL,
        "fire_cause_detail": canada_nfdb.CAUSE_NATURAL,
        "fire_type": "IFR",
        "response": "Full",
        "protection_zone": "Forest Protection Area",
        "prescribed": False,
        "report_date": datetime.date(2023, 5, 3),
        "attack_date": datetime.date(2023, 5, 3),
        "out_date": datetime.date(2023, 7, 1),
        "acquisition_date": datetime.date(2026, 5, 27),
        "more_info": None,
        "cfs_note1": None,
        "cfs_note2": None,
        "start_date_time": datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
        "end_date_time": datetime.datetime(2023, 7, 1, 6, 0, tzinfo=UTC),
        "time_zone": canada_nfdb.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return NfdbWildfire(**values)


def an_ignition(provider, **overrides) -> NfdbIgnition:
    """One published point, as the shapefile gives it."""
    values = {
        "data_provider": provider,
        "nfdb_fire_id": "AB-2023-0001",
        "year": 2023,
        "src_agency": "AB",
        "geometry": POINT_4326,
        "geometry_lambert": POINT_3978,
        "date_time": datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
        "time_zone": canada_nfdb.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return NfdbIgnition(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_natural_is_the_lightning_proxy_and_is_not_lightning():
    """195,240 fires carry it, and none of them is documented as a lightning fire."""
    assert canada_nfdb.CAUSE_NATURAL == "N"
    assert set(canada_nfdb.FIRE_CAUSES) == {"N", "H", "U"}


def test_the_import_starts_where_the_perimeters_do():
    assert canada_nfdb.FIRST_YEAR == 1973


def test_the_unknown_year_sentinel_is_read_as_nothing():
    """95 rows carry it, and a fire in the year minus 999 is not a fire."""
    assert canada_nfdb.UNKNOWN_YEAR == -999
    assert canada_nfdb.published_year(-999) is None
    assert canada_nfdb.published_year(None) is None
    assert canada_nfdb.published_year(0) is None
    assert canada_nfdb.published_year(2023) == 2023


def test_a_year_before_the_import_cut_is_still_a_year():
    """The cut to 1973 is the import's policy; 1950 is a real published year."""
    assert canada_nfdb.published_year(1950) == 1950


@pytest.mark.parametrize("longitude, latitude", [
    (-114.0, 55.0),      # Alberta
    (-141.0, 60.0),      # the Yukon-Alaska border
    (-52.6, 47.5),       # Cape Spear
    (-95.0, 83.0),       # the high Arctic
])
def test_a_coordinate_inside_canada_is_a_location(longitude, latitude):
    assert canada_nfdb.is_located(longitude, latitude)


@pytest.mark.parametrize("longitude, latitude", [
    (0.0, 0.0),              # 154 rows are null or exactly this
    (-5617700.0, 55.0),      # an easting that leaked into a degrees column
    (-114.0, -115.667),      # the published latitude minimum, which is not a latitude
    (None, 55.0),
    (-114.0, None),
])
def test_what_is_not_a_canadian_location_is_refused(longitude, latitude):
    assert not canada_nfdb.is_located(longitude, latitude)


def test_a_transposed_pair_is_refused():
    """A Canadian latitude used as a longitude lands in Asia, which a zero test misses."""
    assert not canada_nfdb.is_located(55.0, -114.0)


# --------------------------------------------------------------------------
# The wildfire model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert stored.nfdb_fire_id == "AB-2023-0001"
    assert stored.agency_fire_id == "LWF-042"
    assert stored.src_agency == "AB"
    assert stored.size_ha == pytest.approx(12345.6)
    assert stored.fire_cause == canada_nfdb.CAUSE_NATURAL
    assert stored.report_date == datetime.date(2023, 5, 3)


def test_it_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "nfdb_wildfire"
    assert isinstance(parent, NfdbWildfire)


def test_there_is_never_a_perimeter(db_session, provider):
    """The agencies publish a location and a size, not a shape. NBAC has the shapes."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).perimeter is None
    assert "perimeter" not in NfdbWildfire.__table__.columns


def test_a_reported_zero_size_is_an_answer(db_session, provider):
    """40,025 fires carry it: a fire that burnt almost nothing, not a missing value."""
    db_session.add(a_wildfire(provider, size_ha=0.0))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert stored.size_ha == 0.0
    assert stored.size_ha is not None


def test_a_negative_size_is_refused(db_session, provider):
    db_session.add(a_wildfire(provider, size_ha=-1.0))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_missing_out_date_leaves_the_fire_unended(db_session, provider):
    """216,601 rows — 48% of the archive — publish no OUT_DATE."""
    db_session.add(a_wildfire(provider, out_date=None, end_date_time=None))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).end_date_time is None


def test_there_is_no_date_precision_column(db_session, provider):
    """Every stored row has a published day: a row with no REP_DATE is not imported.

    NBAC needs a precision because it has a second date to fall back on and a year to
    fall back to. This dataset has neither, so nothing is invented and the column
    would be the constant ``day``.
    """
    assert "date_time_precision" not in NfdbWildfire.__table__.columns
    assert "date_source" not in NfdbWildfire.__table__.columns


def test_the_agency_is_required(db_session, provider):
    """The most important column after the cause: coverage and accuracy vary by it."""
    assert NfdbWildfire.__table__.c.src_agency.nullable is False


def test_the_year_is_nullable_although_the_instant_is_not(db_session, provider):
    """They come from different published columns and can disagree.

    The year is ``YEAR``, which carries a sentinel; the instant is resolved from
    ``REP_DATE``, which does not.
    """
    db_session.add(a_wildfire(provider, year=None))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert stored.year is None
    assert stored.start_date_time is not None


@pytest.mark.parametrize("cause", canada_nfdb.FIRE_CAUSES)
def test_every_published_cause_is_accepted(db_session, provider, cause):
    db_session.add(a_wildfire(provider, fire_cause=cause))
    db_session.commit()

    assert db_session.scalar(select(NfdbWildfire)).fire_cause == cause


def test_a_cause_outside_the_published_three_is_refused(db_session, provider):
    db_session.add(a_wildfire(provider, fire_cause="L"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_cause_refinement_is_not_constrained(db_session, provider):
    """CAUSE2 adds H-PB and RE today and is the column an agency would extend first."""
    db_session.add(a_wildfire(provider, fire_cause=canada_nfdb.CAUSE_HUMAN,
                              fire_cause_detail=canada_nfdb.CAUSE2_PRESCRIBED_BURN))
    db_session.commit()

    assert db_session.scalar(select(NfdbWildfire)).fire_cause_detail == "H-PB"


def test_the_fire_type_is_stored_uninterpreted(db_session, provider):
    """Thirteen agencies, thirteen vocabularies, and nothing to normalise them to."""
    for index, fire_type in enumerate(("Fire", "IFR", "Wildfire", "Surface", "Crown")):
        db_session.add(a_wildfire(provider, nfdb_fire_id=f"X-{index}",
                                  fire_type=fire_type))
    db_session.commit()

    stored = {row.fire_type for row in db_session.scalars(select(NfdbWildfire))}
    assert stored == {"Fire", "IFR", "Wildfire", "Surface", "Crown"}


@pytest.mark.parametrize("published", ["1", "Yes", "yes", "Y", "true", "TRUE", 1, True])
def test_a_published_affirmative_is_prescribed(published):
    """The agencies do not agree on how to write yes, so all of the spellings count."""
    assert canada_nfdb.is_prescribed(published)


@pytest.mark.parametrize("published", ["0", "No", "no", "N", "false", 0, False,
                                       None, "", "   "])
def test_everything_else_is_not_prescribed(published):
    """Blanks included, and deliberately: a prescribed burn is rare.

    Reading silence as *not prescribed* is wrong far less often than reading it as
    *prescribed* would be, and the column is unpublished on most rows.
    """
    assert not canada_nfdb.is_prescribed(published)


def test_an_unrecognised_spelling_is_false_but_reportable():
    """False, so the conservative rule holds — and visible, so a new value is noticed."""
    assert not canada_nfdb.is_prescribed("Prescribed")
    assert canada_nfdb.is_unrecognised_prescribed("Prescribed")
    # A blank is the normal state of the column, not a new spelling.
    assert not canada_nfdb.is_unrecognised_prescribed("")
    assert not canada_nfdb.is_unrecognised_prescribed(None)
    assert not canada_nfdb.is_unrecognised_prescribed("No")


def test_prescribed_is_a_required_boolean(db_session, provider):
    """NOT NULL, so no query has to decide what a null means."""
    assert NfdbWildfire.__table__.c.prescribed.nullable is False

    db_session.add(a_wildfire(provider, prescribed=True))
    db_session.commit()
    assert db_session.scalar(select(NfdbWildfire)).prescribed is True


# --------------------------------------------------------------------------
# Nothing identifies a fire
# --------------------------------------------------------------------------

def test_the_same_published_identifier_twice_is_accepted(db_session, provider):
    """1,684 of the published NFDBFIREIDs are used by more than one row."""
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, fire_name="Sturgeon Lake East"))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(NfdbWildfire.__table__)) == 2


def test_neither_table_constrains_an_identifier(db_session):
    """Stated against the schema, so that adding a UNIQUE later has to face this test."""
    for table in (NfdbWildfire.__table__, NfdbIgnition.__table__):
        unique = [c for c in table.constraints
                  if c.__class__.__name__ == "UniqueConstraint"]
        assert unique == [], f"{table.name} constrains something the dataset does not identify"
        assert not any(column.unique for column in table.columns)


# --------------------------------------------------------------------------
# The ignition point
# --------------------------------------------------------------------------

def test_an_ignition_round_trips(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(NfdbIgnition))
    assert stored.nfdb_fire_id == "AB-2023-0001"
    assert (stored.year, stored.src_agency) == (2023, "AB")
    assert db_session.scalar(select(Wildfire)) is None, "an ignition is not a wildfire"


def test_an_ignition_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Ignition.__table__)) == 1
    parent = db_session.scalar(select(Ignition))
    assert parent.type == "nfdb_ignition"
    assert isinstance(parent, NfdbIgnition)


def test_the_published_point_keeps_its_own_crs(db_session, provider):
    """3978 stored as 3978 beside the 4326 reprojection.

    This is where Canada parts company with Greece, whose ignition stores no second
    copy: Greece publishes degrees, so its geometry *is* the published pair. Canada
    publishes metres, so the 4326 point is derived and the grid one is the original.
    """
    db_session.add(an_ignition(provider))
    db_session.commit()

    srids = db_session.execute(select(
        func.ST_SRID(NfdbIgnition.geometry_lambert),
        func.ST_SRID(NfdbIgnition.geometry),
    )).one()
    assert tuple(srids) == (3978, 4326)


def test_the_published_point_is_metres(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    x, y = db_session.execute(select(
        func.ST_X(NfdbIgnition.geometry_lambert),
        func.ST_Y(NfdbIgnition.geometry_lambert),
    )).one()
    assert (x, y) == pytest.approx((-1200000.0, 1500000.0))


def test_the_published_lat_lon_columns_are_not_stored(db_session, provider):
    """Deliberate: they are the service's own reprojection and are wrong on 244 rows.

    There is nothing to preserve — the import refuses the rows where they and the
    geometry disagree, which leaves no row whose copies could differ.
    """
    columns = set(NfdbIgnition.__table__.columns.keys())
    assert columns == {"id", "nfdb_fire_id", "year", "src_agency", "geometry_lambert"}


def test_the_published_point_is_required_on_an_ignition(db_session, provider):
    """An ignition row means "this fire has a usable published location"."""
    assert NfdbIgnition.__table__.c.geometry_lambert.nullable is False


def test_a_fire_links_to_its_point(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert isinstance(stored.ignition, NfdbIgnition)
    assert stored.ignition.src_agency == "AB"


def test_a_fire_with_no_usable_point_has_none(db_session, provider):
    """A far smaller share than in Spain or Greece: this dataset is points first."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert stored.ignition_id is None
    assert stored.ignition is None


def test_the_point_and_the_fire_report_the_same_instant(db_session, provider):
    """One published date, not two: REP_DATE serves both rows."""
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    stored = db_session.scalar(select(NfdbWildfire))
    assert stored.ignition.date_time == stored.start_date_time


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    """The cause and the agency above all: every report over this dataset filters on both."""
    inspector = inspect(db_session.get_bind())
    wildfire = {index["name"] for index in inspector.get_indexes("nfdb_wildfire")}
    ignition = {index["name"] for index in inspector.get_indexes("nfdb_ignition")}

    assert {"ix_nfdb_wildfire_year", "ix_nfdb_wildfire_fire_cause",
            "ix_nfdb_wildfire_src_agency", "ix_nfdb_wildfire_nfdb_fire_id",
            "ix_nfdb_wildfire_ignition_id"} <= wildfire
    assert {"ix_nfdb_ignition_year", "ix_nfdb_ignition_nfdb_fire_id",
            "idx_nfdb_ignition_geometry_lambert"} <= ignition
