#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NBAC model and the provider constants.

Five things are worth pinning down here, and each is a decision that would be
invisible in the column list alone: that the published EPSG:3978 geometry is stored
in that CRS rather than quietly reprojected; that a fire is a ``GID`` and not a
polygon, so the dissolve of the boundary-split features has a unique key to land on
and a list of administrations to carry; that the resolved start date records both
where it came from and how much of it is real; that ``Natural`` is constrained but
is *not* a lightning category; and that the link to NFDB is a nullable column the
import never fills, with the account of how it was made attached to it.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import canada_nbac
from src.providers import canada_nfdb
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_DAY
from src.providers.canada_nbac.wildfire import MATCH_METHODS
from src.providers.canada_nbac.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.canada_nbac.wildfire import NbacWildfire
from src.providers.canada_nfdb.wildfire import NfdbWildfire

UTC = datetime.timezone.utc

#: A square kilometre in NAD83 / Canada Atlas Lambert metres, somewhere in Alberta.
PERIMETER_3978 = ("SRID=3978;MULTIPOLYGON(((-1200000 1500000, -1199000 1500000, "
                  "-1199000 1501000, -1200000 1501000, -1200000 1500000)))")

#: The same fire in EPSG:4326, near enough for a test that never compares the two.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((-114.00 55.00, -113.98 55.00, "
                  "-113.98 55.01, -114.00 55.01, -114.00 55.00)))")


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=canada_nbac.PROVIDER_NAME,
                            product=canada_nbac.PROVIDER_PRODUCT,
                            full_name=canada_nbac.PROVIDER_FULL_NAME,
                            url=canada_nbac.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> NbacWildfire:
    """One Canadian fire event, with everything a yearly archive publishes."""
    values = {
        "data_provider": provider,
        "gid": "20231234",
        "nfireid": 1234,
        "year": 2023,
        "part_count": 1,
        "crosses_admin": False,
        "admin_name": "AB",
        "admin_div": None,
        "fire_cause": canada_nbac.CAUSE_NATURAL,
        "ba_source": "MAFiMS",
        "detection_source": "Landsat",
        "mapping_method": "Processed imagery",
        "hotspot_start_date": datetime.date(2023, 5, 4),
        "hotspot_end_date": datetime.date(2023, 6, 12),
        "agency_start_date": datetime.date(2023, 5, 3),
        "agency_end_date": datetime.date(2023, 7, 1),
        "capture_date": datetime.date(2023, 9, 20),
        "date_source": canada_nbac.SOURCE_AGENCY,
        "date_time_precision": canada_nbac.PRECISION_DAY,
        "area_ha_polygon": 12345.6,
        "area_ha_adjusted": 13000.0,
        "area_adjusted": True,
        "prescribed": False,
        "version": "20260513",
        "start_date_time": datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
        "end_date_time": datetime.datetime(2023, 7, 1, 6, 0, tzinfo=UTC),
        "time_zone": canada_nbac.DEFAULT_TIME_ZONE,
        "perimeter": PERIMETER_4326,
        "perimeter_lambert": PERIMETER_3978,
    }
    values.update(overrides)
    return NbacWildfire(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_two_canadian_providers_share_a_name():
    """One agency, two products — which is what (name, product) uniqueness is for."""
    assert canada_nbac.PROVIDER_NAME == canada_nfdb.PROVIDER_NAME
    assert canada_nbac.PROVIDER_PRODUCT != canada_nfdb.PROVIDER_PRODUCT


def test_the_source_crs_is_the_canadian_national_grid():
    """3978, which the .prj carries the parameters of and does not name."""
    assert canada_nbac.SOURCE_SRID == 3978
    assert canada_nbac.SOURCE_SRID == canada_nfdb.SOURCE_SRID


def test_the_archive_starts_in_1973():
    """The metadata describes 1972-2025; the service distributes no 1972 archive."""
    assert canada_nbac.FIRST_YEAR == 1973


def test_natural_is_the_lightning_proxy_and_is_not_lightning():
    """The metadata says "most often lightning", which is not the same as lightning.

    Stated as a test because the whole point of the causes report that will read this
    column is that it must not claim more than the source does.
    """
    assert canada_nbac.CAUSE_NATURAL == "Natural"
    assert set(canada_nbac.FIRE_CAUSES) == {"Natural", "Human", "Undetermined"}
    assert not any("ightning" in cause for cause in canada_nbac.FIRE_CAUSES)


def test_the_date_sources_are_ordered_by_preference():
    """Agency first, then hotspot, then the bare year — the import's fallback chain."""
    assert canada_nbac.DATE_SOURCES == ("agency", "hotspot", "year")


def test_there_is_no_minute_precision():
    """Every date this dataset publishes is a bare date, unlike ICNF's."""
    assert canada_nbac.DATE_TIME_PRECISIONS == ("year", "day")
    assert "minute" not in canada_nbac.DATE_TIME_PRECISIONS


def test_the_admin_separator_is_semicolon_space():
    assert canada_nbac.ADMIN_SEPARATOR == "; "


# --------------------------------------------------------------------------
# The wildfire model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.gid == "20231234"
    assert (stored.nfireid, stored.year) == (1234, 2023)
    assert stored.fire_cause == canada_nbac.CAUSE_NATURAL
    assert stored.ba_source == "MAFiMS"
    assert stored.mapping_method == "Processed imagery"
    assert stored.area_ha_polygon == pytest.approx(12345.6)
    assert stored.area_adjusted is True
    assert stored.hotspot_start_date == datetime.date(2023, 5, 4)
    assert stored.agency_start_date == datetime.date(2023, 5, 3)


def test_it_is_stored_across_the_two_tables(db_session, provider):
    """Joined table inheritance: the generic columns in wildfire, the Canadian ones here."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    assert db_session.scalar(select(func.count()).select_from(NbacWildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "nbac_wildfire"
    assert isinstance(parent, NbacWildfire)


def test_the_published_geometry_keeps_its_own_crs(db_session, provider):
    """3978 stored as 3978, not silently reprojected to the generic model's 4326."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    srids = db_session.execute(select(
        func.ST_SRID(NbacWildfire.perimeter_lambert),
        func.ST_SRID(NbacWildfire.perimeter),
    )).one()
    assert tuple(srids) == (3978, 4326)


def test_the_published_geometry_is_metres_not_degrees(db_session, provider):
    """A square kilometre measures a square kilometre on the grid it was published on."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    area = db_session.scalar(select(func.ST_Area(NbacWildfire.perimeter_lambert)))
    assert area == pytest.approx(1_000_000.0)


def test_the_reported_area_is_not_reconciled_with_the_geometry(db_session, provider):
    """POLY_HA is the service's own measurement, on a third projection entirely.

    It is 12,345 ha here against a one-square-kilometre polygon — 100 ha — and the
    model must not object, because the two are different measurements of different
    things and neither is derived from the other.
    """
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    measured_ha = db_session.scalar(
        select(func.ST_Area(NbacWildfire.perimeter_lambert) / 10000.0))
    assert stored.area_ha_polygon != pytest.approx(measured_ha)


# --------------------------------------------------------------------------
# A fire is a GID, not a polygon
# --------------------------------------------------------------------------

def test_the_same_gid_twice_is_refused(db_session, provider):
    """Which is what makes the import dissolve the boundary-split polygons."""
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.add(a_wildfire(provider, nfireid=9999))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_same_year_and_nfireid_twice_is_refused(db_session, provider):
    """The pair the service's own change logs address a fire by."""
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.add(a_wildfire(provider, gid="something-else"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_same_nfireid_in_two_years_is_two_fires(db_session, provider):
    """NFIREID identifies a fire within a year and repeats across them."""
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, gid="20221234", year=2022))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(NbacWildfire.__table__)) == 2


def test_a_dissolved_fire_carries_its_parts_and_their_administrations(db_session, provider):
    """One fire that crossed a provincial line: two polygons, one row, a joined list."""
    db_session.add(a_wildfire(provider, part_count=2, crosses_admin=True,
                              admin_name="AB; SK", area_ha_polygon=20000.0))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.part_count == 2
    assert stored.crosses_admin is True
    assert stored.admin_name.split(canada_nbac.ADMIN_SEPARATOR) == ["AB", "SK"]


def test_a_single_part_fire_says_it_is_not_a_list(db_session, provider):
    """99.1% of the archive: one polygon, one administration, no separator."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.crosses_admin is False
    assert canada_nbac.ADMIN_SEPARATOR not in stored.admin_name


def test_a_part_count_below_one_is_refused(db_session, provider):
    """A dissolved fire is made of at least the polygon it came from."""
    db_session.add(a_wildfire(provider, part_count=0))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The dates
# --------------------------------------------------------------------------

def test_a_fire_with_no_published_date_falls_back_to_the_year(db_session, provider):
    """102 of 1980's 530 fires publish neither an agency date nor a hotspot."""
    db_session.add(a_wildfire(provider, gid="19800001", year=1980, nfireid=1,
                              hotspot_start_date=None, hotspot_end_date=None,
                              agency_start_date=None, agency_end_date=None,
                              date_source=canada_nbac.SOURCE_YEAR,
                              date_time_precision=canada_nbac.PRECISION_YEAR,
                              start_date_time=datetime.datetime(1980, 1, 1, 7, 0,
                                                                tzinfo=UTC),
                              end_date_time=None))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.date_source == "year"
    assert stored.date_time_precision == "year"
    assert stored.start_date_time.month == 1, "1 January, and the precision says so"


def test_a_fire_dated_from_a_hotspot_records_that(db_session, provider):
    """No agency date, so the first satellite hotspot is what the start rests on."""
    db_session.add(a_wildfire(provider, agency_start_date=None,
                              date_source=canada_nbac.SOURCE_HOTSPOT))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.date_source == "hotspot"
    assert stored.date_time_precision == "day", "a hotspot date is still a real day"


def test_both_published_date_pairs_are_kept(db_session, provider):
    """So the resolution can be checked, and the other observation stays available."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.agency_start_date == datetime.date(2023, 5, 3)
    assert stored.hotspot_start_date == datetime.date(2023, 5, 4)
    assert stored.agency_start_date != stored.hotspot_start_date


def test_a_missing_agency_end_leaves_the_fire_unended(db_session, provider):
    """939 of 2023's 2,244 fires. The last hotspot is deliberately not used for it."""
    db_session.add(a_wildfire(provider, agency_end_date=None, end_date_time=None))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.end_date_time is None
    assert stored.hotspot_end_date is not None, "which is a different event, not a stand-in"


@pytest.mark.parametrize("column, value", [
    ("date_source", "guessed"),
    ("date_time_precision", "minute"),
])
def test_an_unknown_date_vocabulary_is_refused(db_session, provider, column, value):
    db_session.add(a_wildfire(provider, **{column: value}))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The cause
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cause", canada_nbac.FIRE_CAUSES)
def test_every_published_cause_is_accepted(db_session, provider, cause):
    db_session.add(a_wildfire(provider, fire_cause=cause))
    db_session.commit()

    assert db_session.scalar(select(NbacWildfire)).fire_cause == cause


def test_a_cause_outside_the_published_three_is_refused(db_session, provider):
    """Three values, defined in the metadata and stable — worth stating in the schema."""
    db_session.add(a_wildfire(provider, fire_cause="Lightning"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_fire_with_no_cause_is_allowed(db_session, provider):
    """FIRECAUS can be absent; ``Undetermined`` is a statement and NULL is a silence."""
    db_session.add(a_wildfire(provider, fire_cause=None))
    db_session.commit()

    assert db_session.scalar(select(NbacWildfire)).fire_cause is None


# --------------------------------------------------------------------------
# The NFDB link
# --------------------------------------------------------------------------

def test_a_fire_starts_unbound(db_session, provider):
    """The import never fills the link in; a later application does."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert stored.nfdb_wildfire_id is None
    assert stored.nfdb_wildfire is None
    assert stored.match_method is None


def test_a_link_without_an_account_of_it_is_refused(db_session, provider):
    """A binding that does not say how it was made is unusable, so it cannot exist."""
    report = NfdbWildfire(data_provider=provider, src_agency="AB", year=2023,
                          fire_cause=canada_nfdb.CAUSE_NATURAL,
                          start_date_time=datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
                          time_zone=canada_nfdb.DEFAULT_TIME_ZONE)
    db_session.add(report)
    db_session.flush()
    db_session.add(a_wildfire(provider, nfdb_wildfire_id=report.id))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_account_without_a_link_is_refused_too(db_session, provider):
    """The constraint is an equivalence, not an implication."""
    db_session.add(a_wildfire(provider, match_method="date_place"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_bound_fire_carries_how_it_was_bound(db_session, provider):
    report = NfdbWildfire(data_provider=provider, src_agency="AB", year=2023,
                          nfdb_fire_id="AB-2023-0001",
                          fire_cause=canada_nfdb.CAUSE_NATURAL,
                          start_date_time=datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
                          time_zone=canada_nfdb.DEFAULT_TIME_ZONE)
    db_session.add(report)
    db_session.flush()
    matched = datetime.datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    db_session.add(a_wildfire(provider, nfdb_wildfire_id=report.id,
                              match_method=MATCH_INSIDE_AGENCY_DAY,
                              match_confidence=0.95, matched_at=matched))
    db_session.commit()

    stored = db_session.scalar(select(NbacWildfire))
    assert isinstance(stored.nfdb_wildfire, NfdbWildfire)
    assert stored.nfdb_wildfire.nfdb_fire_id == "AB-2023-0001"
    assert (stored.match_method, stored.match_confidence) == (MATCH_INSIDE_AGENCY_DAY,
                                                              0.95)
    assert stored.matched_at == matched


def test_the_match_method_vocabulary_is_constrained(db_session, provider):
    """It was not, deliberately, until the Canadian rules had been worked out.

    They have been — see
    :mod:`src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires` — so the CHECK
    the model docstring promised is now there, taken in a revision of its own exactly
    as REDIAM's was.
    """
    report = NfdbWildfire(data_provider=provider, src_agency="AB", year=2023,
                          fire_cause=canada_nfdb.CAUSE_NATURAL,
                          start_date_time=datetime.datetime(2023, 5, 3, 6, 0, tzinfo=UTC),
                          time_zone=canada_nfdb.DEFAULT_TIME_ZONE)
    db_session.add(report)
    db_session.flush()
    db_session.add(a_wildfire(provider, nfdb_wildfire_id=report.id,
                              match_method="a rule nobody has invented yet"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_no_binding_method_claims_certainty():
    """The Catalan and Andalusian models open at 1.00 on a published identifier.

    NBAC and NFDB share none, so every rule here is an inference and the vocabulary
    says so. A later edit scoring one of them 1.00 would be claiming something the
    data cannot support.
    """
    assert set(MATCH_METHOD_CONFIDENCE) == set(MATCH_METHODS)
    assert max(MATCH_METHOD_CONFIDENCE.values()) < 1.0
