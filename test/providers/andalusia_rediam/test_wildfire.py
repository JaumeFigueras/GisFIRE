#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the REDIAM models and the provider constants.

Four things are worth pinning down here, and each is a decision that would be
invisible in the column list alone: that ``CODIGO`` really is an EGIF
``report_number`` and that :func:`egif_report_number` reads all three of its published
shapes; that the published EPSG:25830 geometry is stored in that CRS rather than
quietly reprojected — and in **25830** rather than the 3042 the ``.prj`` resolves to;
that the ignition point is a row of its own, linked and not embedded; and that the
link to EGIF is a nullable column the import never fills, with the account of how it
was made attached to it.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import andalusia_rediam
from src.providers import spain_egif
from src.providers.andalusia_rediam.ignition import RediamIgnition
from src.providers.andalusia_rediam.wildfire import RediamWildfire
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

#: A square kilometre in ETRS89 / UTM 30N metres, somewhere in western Andalusia.
PERIMETER_25830 = ("SRID=25830;MULTIPOLYGON(((215000 4117000, 216000 4117000, "
                   "216000 4118000, 215000 4118000, 215000 4117000)))")

#: The same fire in EPSG:4326, near enough for a test that never compares the two.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((-6.30 37.17, -6.29 37.17, -6.29 37.18, "
                  "-6.30 37.18, -6.30 37.17)))")


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=andalusia_rediam.PROVIDER_NAME,
                            product=andalusia_rediam.PROVIDER_PRODUCT,
                            full_name=andalusia_rediam.PROVIDER_FULL_NAME,
                            url=andalusia_rediam.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> RediamWildfire:
    """One Andalusian fire, with everything the combined layer publishes."""
    values = {
        "data_provider": provider,
        "source_layer": "PERIMETROS_COR_2008_2025",
        "code": "2008410097",
        "fire_date": datetime.date(2008, 9, 11),
        "year": 2008,
        "municipality_name": "AZNALCAZAR",
        "province_name": "Sevilla",
        "part_count": 1,
        "area_ha_wooded": 0.0,
        "area_ha_scrub": 1.6,
        "area_ha_grassland": 26.9,
        "start_date_time": datetime.datetime(2008, 9, 10, 22, 0, tzinfo=UTC),
        "time_zone": andalusia_rediam.DEFAULT_TIME_ZONE,
        "perimeter": PERIMETER_4326,
        "perimeter_etrs89_utm30n": PERIMETER_25830,
    }
    values.update(overrides)
    return RediamWildfire(**values)


def an_ignition(provider, **overrides) -> RediamIgnition:
    """One published ignition point, as the 2021-2024 yearly layers give it."""
    values = {
        "data_provider": provider,
        "source_layer": "PERIMETROS_COR_2022",
        "code": "2022040091",
        "fire_date": datetime.date(2022, 8, 1),
        "utm_x": 500000.0,
        "utm_y": 4100000.0,
        "geometry": "SRID=4326;POINT(-3.0 37.03)",
        "date_time": datetime.datetime(2022, 7, 31, 22, 0, tzinfo=UTC),
        "time_zone": andalusia_rediam.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return RediamIgnition(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_source_crs_is_the_western_spanish_grid():
    """25830, the axis order the files follow — not the 3042 the .prj resolves to."""
    assert andalusia_rediam.SOURCE_SRID == 25830
    assert andalusia_rediam.DECLARED_SRID == 3042
    assert andalusia_rediam.SOURCE_SRID != andalusia_rediam.DECLARED_SRID


def test_the_provinces_are_the_eight_andalusian_ones():
    assert andalusia_rediam.PROVINCE_INE_CODES == ("04", "11", "14", "18", "21", "23",
                                                   "29", "41")


@pytest.mark.parametrize("layer, year", [
    ("PERIMETROS_COR_2008", 2008),
    ("PERIMETROS_COR_2025", 2025),
    ("perimetros_cor_2021", 2021),
])
def test_a_yearly_layer_carries_its_year(layer, year):
    assert andalusia_rediam.layer_year(layer) == year


@pytest.mark.parametrize("layer", [
    "PERIMETROS_COR_2008_2025",   # the combined layer, which is not a yearly one
    "PERIMETROS_COR",
    "incendis2024",
    "",
])
def test_what_is_not_a_yearly_layer_has_no_year(layer):
    """``None`` and not an exception: a directory legitimately holds both kinds."""
    assert andalusia_rediam.layer_year(layer) is None


def test_the_combined_layer_is_recognised_by_shape_not_by_name():
    """The range in the name grows every publication, so the name cannot be the rule."""
    assert andalusia_rediam.is_combined_layer("PERIMETROS_COR_2008_2025")
    assert andalusia_rediam.is_combined_layer("PERIMETROS_COR_2008_2026")
    assert andalusia_rediam.is_combined_layer("PERIMETROS_COR_2009_2030")
    assert not andalusia_rediam.is_combined_layer("PERIMETROS_COR_2025")


def test_the_combined_layer_reports_the_range_it_claims():
    assert andalusia_rediam.combined_layer_years("PERIMETROS_COR_2008_2025") == (2008, 2025)
    assert andalusia_rediam.combined_layer_years("PERIMETROS_COR_2025") is None


def test_a_layer_name_is_stored_upper_cased():
    assert andalusia_rediam.source_layer_name("perimetros_cor_2008_2025") == \
        "PERIMETROS_COR_2008_2025"


# --------------------------------------------------------------------------
# The code is an EGIF report number
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code, report_number", [
    # 2008-2024: the report number, plainly.
    ("2008410097", "2008410097"),
    ("2013180011", "2013180011"),
    # 2025: the same number behind the IIFF label.
    ("IIFF2025040059", "2025040059"),
    ("iiff2025110038", "2025110038"),
    # Six 2019 codes write the sequence with three digits instead of four.
    ("201918023", "2019180023"),
])
def test_a_published_code_decodes_to_a_report_number(code, report_number):
    assert andalusia_rediam.egif_report_number(code) == report_number


@pytest.mark.parametrize("code", [
    "303/22N",          # a Catalan internal reference, not an EGIF code at all
    "2008990097",       # province 99 is not Andalusian — nor anything else
    "2008080097",       # Barcelona: a real INE province, and not one of these eight
    "20084100",         # too short to be either published shape
    "20084100970",      # too long
    "",
    "IIFF",
])
def test_what_is_not_a_report_number_is_refused(code):
    """Rather than turned into a plausible-looking one, which is the failure that hurts."""
    assert andalusia_rediam.egif_report_number(code) is None


def test_the_decode_does_not_check_the_year_against_anything():
    """Deliberately: the caller has the published date and can make a stronger test.

    A code naming a year the dataset does not cover still decodes — it is a
    well-formed report number — and comparing it with ``FECHA_INC`` is the binding
    application's job.
    """
    assert andalusia_rediam.egif_report_number("1975410097") == "1975410097"


# --------------------------------------------------------------------------
# The wildfire model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert stored.code == "2008410097"
    assert stored.fire_date == datetime.date(2008, 9, 11)
    assert stored.year == 2008
    assert stored.municipality_name == "AZNALCAZAR"
    assert stored.province_name == "Sevilla"
    assert stored.part_count == 1
    assert (stored.area_ha_wooded, stored.area_ha_scrub, stored.area_ha_grassland) == \
        (0.0, 1.6, 26.9)


def test_it_is_stored_across_the_two_tables(db_session, provider):
    """Joined table inheritance: the generic columns in wildfire, the Andalusian ones here."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    assert db_session.scalar(select(func.count()).select_from(RediamWildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "rediam_wildfire"
    assert isinstance(parent, RediamWildfire)


def test_the_published_geometry_keeps_its_own_crs(db_session, provider):
    """25830 stored as 25830, not silently reprojected to the generic model's 4326."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    srids = db_session.execute(select(
        func.ST_SRID(RediamWildfire.perimeter_etrs89_utm30n),
        func.ST_SRID(RediamWildfire.perimeter),
    )).one()
    assert tuple(srids) == (25830, 4326)


def test_the_published_geometry_is_metres_not_degrees(db_session, provider):
    """A square kilometre measures a square kilometre on the grid it was published on."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    area = db_session.scalar(select(func.ST_Area(RediamWildfire.perimeter_etrs89_utm30n)))
    assert area == pytest.approx(1_000_000.0)


def test_a_reported_zero_area_is_not_a_missing_one(db_session, provider):
    """``SUP_ARBOLA`` of 0.00 means no wooded land burnt, which is an answer."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert stored.area_ha_wooded == 0.0
    assert stored.area_ha_wooded is not None


def test_there_is_no_stored_total(db_session, provider):
    """The three areas are stored and their sum is not: a stored sum can drift."""
    assert "area_ha_total" not in RediamWildfire.__table__.columns
    assert "area_ha_published_total" not in RediamWildfire.__table__.columns


# --------------------------------------------------------------------------
# The natural key
# --------------------------------------------------------------------------

def test_the_same_code_twice_on_one_date_is_refused(db_session, provider):
    """Which is what makes the import dissolve the 55 duplicates rather than store them."""
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.add(a_wildfire(provider, municipality_name="Aznalcázar"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_same_code_on_two_dates_is_two_fires(db_session, provider):
    """No Andalusian code does this today; the key is the pair so that one could.

    It is also the key ``darpa_wildfire`` uses, where a code really does name two
    fires, so a query over both regional datasets is one query.
    """
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, fire_date=datetime.date(2008, 9, 12)))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(RediamWildfire.__table__)) == 2


# --------------------------------------------------------------------------
# The ignition point
# --------------------------------------------------------------------------

def test_an_ignition_round_trips(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    stored = db_session.scalar(select(RediamIgnition))
    assert stored.code == "2022040091"
    assert stored.fire_date == datetime.date(2022, 8, 1)
    assert (stored.utm_x, stored.utm_y) == (500000.0, 4100000.0)
    assert db_session.scalar(select(Wildfire)) is None, "an ignition is not a wildfire"


def test_an_ignition_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Ignition.__table__)) == 1
    parent = db_session.scalar(select(Ignition))
    assert parent.type == "rediam_ignition"
    assert isinstance(parent, RediamIgnition)


def test_a_fire_links_to_its_point(db_session, provider):
    ignition = an_ignition(provider)
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert isinstance(stored.ignition, RediamIgnition)
    assert (stored.ignition.utm_x, stored.ignition.utm_y) == (500000.0, 4100000.0)


def test_a_fire_with_no_published_point_has_none(db_session, provider):
    """Four fires in five: the service published no coordinate before 2021."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert stored.ignition_id is None
    assert stored.ignition is None


def test_the_point_need_not_be_inside_the_perimeter(db_session, provider):
    """113 of the 201 published points are not, and the model must not object.

    The point here is in the Atlantic, some way from the fixture's fire. Nothing in
    the model relates the two geometries, which is the whole reason the ignition is a
    row rather than two columns on the perimeter.
    """
    ignition = an_ignition(provider, utm_x=100000.0, utm_y=4000000.0,
                           geometry="SRID=4326;POINT(-7.5 36.1)")
    db_session.add(ignition)
    db_session.flush()
    db_session.add(a_wildfire(provider, ignition_id=ignition.id))
    db_session.commit()

    inside = db_session.scalar(select(func.ST_Contains(
        RediamWildfire.perimeter_etrs89_utm30n,
        func.ST_SetSRID(func.ST_MakePoint(RediamIgnition.utm_x, RediamIgnition.utm_y),
                        andalusia_rediam.SOURCE_SRID),
    )).where(RediamWildfire.ignition_id == RediamIgnition.id))
    assert inside is False


def test_one_point_per_fire(db_session, provider):
    db_session.add(an_ignition(provider))
    db_session.commit()
    db_session.add(an_ignition(provider, utm_x=1.0, utm_y=2.0))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The EGIF relation
# --------------------------------------------------------------------------

def test_the_egif_link_is_empty_as_imported(db_session, provider):
    """The import never fills it in; the column exists so a binding is an UPDATE."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert stored.egif_wildfire_id is None
    assert stored.egif_wildfire is None
    assert (stored.match_method, stored.match_confidence, stored.matched_at) == \
        (None, None, None)


def test_a_bound_fire_carries_the_account_of_how(db_session, provider):
    egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                 product=spain_egif.PROVIDER_PRODUCT,
                                 full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add(egif_provider)
    db_session.flush()
    parte = EgifWildfire(
        data_provider=egif_provider, report_number="2008410097", campaign=2008,
        province_ine_code="41",
        start_date_time=datetime.datetime(2008, 9, 11, 12, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    db_session.add(parte)
    db_session.flush()

    fire = a_wildfire(provider, egif_wildfire_id=parte.id, match_method="code",
                      match_confidence=1.0,
                      matched_at=datetime.datetime(2026, 8, 3, tzinfo=UTC))
    db_session.add(fire)
    db_session.commit()

    stored = db_session.scalar(select(RediamWildfire))
    assert stored.egif_wildfire.report_number == "2008410097"
    assert stored.match_method == "code"


def test_a_link_with_no_method_is_refused(db_session, provider):
    """A binding is the link *and* the account of how it was made, or neither."""
    egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                 product=spain_egif.PROVIDER_PRODUCT,
                                 full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add(egif_provider)
    db_session.flush()
    parte = EgifWildfire(
        data_provider=egif_provider, report_number="2008410097", campaign=2008,
        province_ine_code="41",
        start_date_time=datetime.datetime(2008, 9, 11, 12, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    db_session.add(parte)
    db_session.flush()
    db_session.add(a_wildfire(provider, egif_wildfire_id=parte.id))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_method_with_no_link_is_refused(db_session, provider):
    db_session.add(a_wildfire(provider, match_method="code", match_confidence=1.0))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_method_outside_the_vocabulary_is_refused(db_session, provider):
    """The rules were agreed after the table was created, so the list came later.

    Revision b1c47d9e3f52 is the constraint that was promised when e9e992e02a11
    deliberately created the column without one.
    """
    egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                 product=spain_egif.PROVIDER_PRODUCT,
                                 full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add(egif_provider)
    db_session.flush()
    parte = EgifWildfire(
        data_provider=egif_provider, report_number="2008410097", campaign=2008,
        province_ine_code="41",
        start_date_time=datetime.datetime(2008, 9, 11, 12, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    db_session.add(parte)
    db_session.flush()
    db_session.add(a_wildfire(provider, egif_wildfire_id=parte.id,
                              match_method="vibes", match_confidence=0.5))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_two_rules_a_date_alone_could_write_are_not_in_the_vocabulary():
    """``date`` and ``date_name`` are Catalan-only, and refused here rather than unused.

    They are the branches that cascade takes when a code carries no province, and
    every Andalusian code carries one — so a database that accepted them would be
    accepting a binding the Andalusian cascade must never write.
    """
    from src.providers.catalonia_darpa.wildfire import MATCH_METHODS as DARPA_METHODS
    from src.providers.andalusia_rediam.wildfire import MATCH_METHODS

    assert set(MATCH_METHODS) < set(DARPA_METHODS)
    assert set(DARPA_METHODS) - set(MATCH_METHODS) == {"date", "date_name"}


def test_every_method_has_a_confidence_and_they_match_catalonia():
    """``match_confidence >= 0.9`` has to mean the same thing on both datasets."""
    from src.providers.catalonia_darpa.wildfire import (
        MATCH_METHOD_CONFIDENCE as DARPA_CONFIDENCE)
    from src.providers.andalusia_rediam.wildfire import MATCH_METHODS
    from src.providers.andalusia_rediam.wildfire import MATCH_METHOD_CONFIDENCE

    assert set(MATCH_METHODS) == set(MATCH_METHOD_CONFIDENCE)
    for method, confidence in MATCH_METHOD_CONFIDENCE.items():
        assert confidence == DARPA_CONFIDENCE[method], method
