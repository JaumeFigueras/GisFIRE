#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`InabWildfire` and :class:`InabIgnition` models.

What has to be pinned down here is mostly what this provider does **not** have —
no perimeter, no burnt area, no end date — because those absences are the shape
of the dataset rather than gaps in it, and a later edit that "fixes" one would be
inventing data.

The rest is the key: ``global_id`` is unique because a *report* is unique, while
two reports of one fire are a thing the published data really contains.
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
from src.providers import guatemala_inab
from src.providers.guatemala_inab.ignition import InabIgnition
from src.providers.guatemala_inab.wildfire import InabWildfire

UTC = datetime.timezone.utc

#: A point in Petén, where a third of these fires are.
POINT = "SRID=4326;POINT(-90.414114 17.383463)"

#: Local midnight-plus-afternoon: 14:30 in Guatemala, which is UTC-6 all year.
REPORTED_AT = datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC)


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=guatemala_inab.PROVIDER_NAME,
                            product=guatemala_inab.PROVIDER_PRODUCT,
                            full_name=guatemala_inab.PROVIDER_FULL_NAME,
                            url=guatemala_inab.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def an_ignition(provider, **overrides) -> InabIgnition:
    values = {
        "data_provider": provider,
        "global_id": "{49585C0C-4FE2-45A3-A50C-405E6C4EF418}",
        "geometry": POINT,
        "date_time": REPORTED_AT,
        "time_zone": guatemala_inab.DEFAULT_TIME_ZONE,
        "reported_x": 509125.0,
        "reported_y": 1922363.0,
        "reported_crs": guatemala_inab.CRS_GTM,
        "altitude_m": 180.0,
    }
    values.update(overrides)
    return InabIgnition(**values)


def a_wildfire(provider, **overrides) -> InabWildfire:
    """A fully-filled report — richer than most, since 89% lack a fire type."""
    values = {
        "data_provider": provider,
        "global_id": "{49585C0C-4FE2-45A3-A50C-405E6C4EF418}",
        "object_id": 4247,
        "source_id": 3912,
        "start_date_time": REPORTED_AT,
        "time_zone": guatemala_inab.DEFAULT_TIME_ZONE,
        "report_status": guatemala_inab.STATUS_CLOSED,
        "report_channel": "telefono",
        "institution": "conap",
        "fire_location": guatemala_inab.LOCATION_IN_FOREST,
        "department_name": "peten",
        "municipality_name": "flores_1701",
        "municipality_code": 1701,
        "locality_name": "Sacluc-PNLT",
        "estate_name": "Finca San Diego",
        "inab_region": "viii",
        "inab_subregion": "viii_1",
        "protected_area_name": "Reserva de la Biosfera Maya",
        "protected_area_name_secondary": "Parque Nacional Sierra del Lacandón",
        "published_at": datetime.datetime(2025, 3, 14, 21, 4, tzinfo=UTC),
        "edited_at": datetime.datetime(2025, 3, 20, 15, 12, tzinfo=UTC),
    }
    values.update(overrides)
    return InabWildfire(**values)


# --------------------------------------------------------------------------
# What this provider does not publish
# --------------------------------------------------------------------------

def test_there_is_no_burnt_area_column_anywhere():
    """The first provider in the project publishing neither a shape nor a size.

    EGIF and the Greek Fire Service publish no perimeter but do publish hectares.
    INAB publishes thirty-three attributes and not one of them is a size, so
    inventing a column for one would be inventing the data to go in it.
    """
    columns = {column.name for column in InabWildfire.__table__.columns}
    assert not [name for name in columns if "area_ha" in name or name == "area"]
    assert not [name for name in columns if "hectare" in name or "size" in name]


def test_a_fire_is_stored_with_no_perimeter(db_session, provider):
    """wildfire.perimeter is NULL on every INAB row, and has to be allowed to be."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(InabWildfire))
    assert stored.perimeter is None


def test_a_fire_is_stored_with_no_end_date(db_session, provider):
    """The control and extinction times are in the informes layer, not modelled."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).end_date_time is None


def test_there_is_no_date_time_precision_column():
    """Every published instant is a real minute, so the column would say nothing.

    ICNF and CONAFOR carry one because their precision genuinely varies; here it
    does not.
    """
    assert "date_time_precision" not in {
        column.name for column in InabWildfire.__table__.columns}


# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------

def test_the_global_id_is_required_and_unique(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, object_id=9999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_fire_needs_a_global_id(db_session, provider):
    db_session.add(a_wildfire(provider, global_id=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_two_reports_of_one_fire_are_two_rows(db_session, provider):
    """57 published pairs share an exact coordinate and an exact minute.

    They are the same fire called in by two institutions, sometimes reaching two
    different outcomes. The model has to hold both, because deciding which to
    believe is an analysis and not an import.
    """
    db_session.add(a_wildfire(
        provider, global_id="{AAAA0000-0000-0000-0000-000000000001}",
        institution="particular", report_status=guatemala_inab.STATUS_UNVERIFIED))
    db_session.add(a_wildfire(
        provider, global_id="{AAAA0000-0000-0000-0000-000000000002}",
        institution="otra", report_status=guatemala_inab.STATUS_CLOSED))
    db_session.commit()

    stored = db_session.scalars(select(InabWildfire)).all()
    assert len(stored) == 2
    assert {row.start_date_time for row in stored} == {REPORTED_AT}
    assert {row.report_status for row in stored} == {
        guatemala_inab.STATUS_UNVERIFIED, guatemala_inab.STATUS_CLOSED}


def test_the_object_id_is_not_unique(db_session, provider):
    """It is a hosted-view artefact, reassigned on republication. Never a key."""
    db_session.add(a_wildfire(provider, global_id="{A}", object_id=13))
    db_session.add(a_wildfire(provider, global_id="{B}", object_id=13))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(InabWildfire)) == 2


def test_the_source_id_may_be_absent(db_session, provider):
    """161 of the 4,615 records have no ob_id."""
    db_session.add(a_wildfire(provider, source_id=None))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).source_id is None


# --------------------------------------------------------------------------
# What a sparse record is allowed to omit
# --------------------------------------------------------------------------

@pytest.mark.parametrize("column", [
    "report_status", "report_channel", "institution", "institution_other",
    "fire_location", "department_name", "municipality_name", "municipality_code",
    "locality_name", "estate_name", "inab_region", "inab_subregion",
    "protected_area_name", "protected_area_name_secondary",
    "published_at", "edited_at", "object_id", "source_id",
])
def test_every_published_attribute_is_optional(db_session, provider, column):
    """Four published records carry nothing but an identifier and a map tap.

    Only the global id, the provider and the start instant are required; every
    descriptive attribute has to be allowed to be absent, or those records cannot
    be stored at all.
    """
    db_session.add(a_wildfire(provider, **{column: None}))
    db_session.commit()

    assert getattr(db_session.scalar(select(InabWildfire)), column) is None


def test_the_fire_location_is_usually_absent(db_session, provider):
    """tipo_incendio is filled on 489 of 4,615 — 89% of records have none."""
    db_session.add(a_wildfire(provider, fire_location=None))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).fire_location is None


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", guatemala_inab.REPORT_STATUSES)
def test_every_published_status_is_storable(db_session, provider, status):
    """No CHECK constraint: one publication's vocabulary observed once."""
    db_session.add(a_wildfire(provider, report_status=status))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).report_status == status


def test_a_status_the_provider_invents_is_storable(db_session, provider):
    """Which is the point of there being no constraint."""
    db_session.add(a_wildfire(provider, report_status="reabierto"))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).report_status == "reabierto"


def test_the_false_alarms_can_be_filtered_out(db_session, provider):
    """140 of the 4,615 say there was no fire. Any count must exclude them."""
    db_session.add(a_wildfire(provider, global_id="{A}",
                              report_status=guatemala_inab.STATUS_CLOSED))
    db_session.add(a_wildfire(provider, global_id="{B}",
                              report_status=guatemala_inab.STATUS_FALSE))
    db_session.add(a_wildfire(provider, global_id="{C}",
                              report_status=guatemala_inab.STATUS_UNVERIFIED))
    db_session.commit()

    real = db_session.scalars(
        select(InabWildfire).where(
            InabWildfire.report_status.is_distinct_from(guatemala_inab.STATUS_FALSE))).all()
    assert len(real) == 2, "the false alarm is excluded, the unverified one is not"


# --------------------------------------------------------------------------
# The ignition
# --------------------------------------------------------------------------

def test_the_point_is_stored_in_4326(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    kind, srid = db_session.execute(
        select(func.ST_GeometryType(Ignition.geometry), func.ST_SRID(Ignition.geometry))).one()
    assert kind == "ST_Point"
    assert srid == guatemala_inab.SOURCE_SRID == 4326


def test_the_point_lands_in_guatemala(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    longitude, latitude = db_session.execute(
        select(func.ST_X(Ignition.geometry), func.ST_Y(Ignition.geometry))).one()
    assert guatemala_inab.is_in_guatemala(longitude, latitude)


def test_a_point_outside_guatemala_is_still_stored(db_session, provider):
    """Three published points are not in the country and all three are 'falso'.

    They are stored as published: a sign flip is an obvious guess, and obvious
    guesses about coordinates are how a database acquires plausible wrong answers.
    """
    db_session.add(an_ignition(provider, geometry="SRID=4326;POINT(90.4735 14.5007)"))
    db_session.commit()

    longitude, latitude = db_session.execute(
        select(func.ST_X(Ignition.geometry), func.ST_Y(Ignition.geometry))).one()
    assert not guatemala_inab.is_in_guatemala(longitude, latitude)


def test_the_typed_coordinates_are_kept_as_published(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(InabIgnition))
    assert stored.reported_x == 509125.0
    assert stored.reported_y == 1922363.0
    assert stored.reported_crs == "GTM"


def test_the_typed_coordinates_are_usually_absent(db_session, provider):
    """Only 440 of the 4,615 records typed any, against 4,615 with a point."""
    db_session.add(an_ignition(provider, reported_x=None, reported_y=None,
                               reported_crs=None, utm_zone=None, altitude_m=None))
    db_session.commit()

    stored = db_session.scalar(select(InabIgnition))
    assert stored.reported_x is None
    assert stored.reported_crs is None
    assert stored.geometry is not None, "the point is what locates the fire"


def test_the_ignition_global_id_is_unique(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.add(an_ignition(provider))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_local_reading_comes_back_through_the_stored_zone(db_session, provider):
    """Guatemala is UTC-6 all year and has observed no DST since 2006."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    local = db_session.scalar(
        select(func.timezone(Wildfire.time_zone, Wildfire.start_date_time)))
    assert local == datetime.datetime(2025, 3, 14, 14, 30)


# --------------------------------------------------------------------------
# The link between them
# --------------------------------------------------------------------------

def test_a_fire_links_to_its_point(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(InabWildfire))
    assert stored.ignition is not None
    assert stored.ignition.id == stored.ignition_id


def test_the_two_rows_share_the_published_global_id(db_session, provider):
    """Stored on both so a point can be matched to a record without a join."""
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    fire = db_session.scalar(select(InabWildfire))
    point = db_session.scalar(select(InabIgnition))
    assert fire.global_id == point.global_id


def test_a_fire_may_have_no_point(db_session, provider):
    """Every record published today has one; a record without one is storable.

    Four published records carry nothing but an identifier, two timestamps and a
    map tap — a record with the tap missing is the same kind of thing, and a NOT
    NULL would mean dropping it rather than storing what it does say.
    """
    db_session.add(a_wildfire(provider, ignition_id=None))
    db_session.commit()

    assert db_session.scalar(select(InabWildfire)).ignition is None


def test_the_ignition_link_must_exist(db_session, provider):
    db_session.add(a_wildfire(provider, ignition_id=999_999))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_joined_table_inheritance_splits_the_columns(db_session):
    assert InabWildfire.__tablename__ == "inab_wildfire"
    assert InabIgnition.__tablename__ == "inab_ignition"

    columns = {column["name"]
               for column in inspect(db_session.get_bind()).get_columns("inab_wildfire")}
    assert "global_id" in columns and "report_status" in columns
    # The dates and the geometry are the generic models' and are not repeated.
    assert "start_date_time" not in columns
    assert "perimeter" not in columns


def test_neither_table_carries_a_geometry_of_its_own(db_session):
    """The point is the generic ignition's; INAB publishes it in the stored CRS."""
    for table in ("inab_wildfire", "inab_ignition"):
        columns = inspect(db_session.get_bind()).get_columns(table)
        assert not [c for c in columns
                    if c["type"].__class__.__name__.lower().startswith("geometry")]


def test_querying_the_parents_returns_the_subclasses(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()
    db_session.expunge_all()

    assert isinstance(db_session.scalar(select(Wildfire)), InabWildfire)
    assert isinstance(db_session.scalar(select(Ignition)), InabIgnition)


def test_repr_before_persist():
    fire = InabWildfire(global_id="{A}", report_status="falso")
    assert repr(fire) == "InabWildfire(id=None, global_id='{A}', report_status='falso')"
    point = InabIgnition(global_id="{A}")
    assert repr(point) == "InabIgnition(id=None, global_id='{A}')"
