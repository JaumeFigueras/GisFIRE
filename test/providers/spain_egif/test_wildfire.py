#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`EgifWildfire` model.

Three properties are worth holding still: an EGIF fire never has a perimeter, the
same fire can be filled in from two different exports without becoming two rows,
and cause and motivation are two code spaces that must not be confused.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import spain_egif
from src.providers.spain_egif.fire_cause import EgifFireCause
from src.providers.spain_egif.fire_motivation import EgifFireMotivation
from src.providers.spain_egif.ignition import EgifIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=spain_egif.PROVIDER_NAME, product=spain_egif.PROVIDER_PRODUCT,
                            full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def ignition(db_session, provider):
    ignition = EgifIgnition(
        data_provider=provider, report_number="2022010001",
        geometry="SRID=4326;POINT(-2.35 42.66)",
        date_time=datetime.datetime(2022, 1, 29, 14, 22, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE,
        utm_zone=30, utm_x=549122.0, utm_y=4727399.0, datum=spain_egif.DATUM_ETRS89,
        start_point_count=1)
    db_session.add(ignition)
    db_session.commit()
    return ignition


@pytest.fixture
def cause(db_session):
    cause = EgifFireCause(code="213", label="Quema de restos agrícolas (viñas,etc)")
    db_session.add(cause)
    db_session.commit()
    return cause


@pytest.fixture
def motivation(db_session):
    motivation = EgifFireMotivation(
        code="405",
        label="Incendios provocados para mantener libre de vegetación el monte")
    db_session.add(motivation)
    db_session.commit()
    return motivation


def a_wildfire(provider, ignition, **overrides) -> EgifWildfire:
    """The first fire of the 2022 Excel export: Kanpezu/Campezo, Álava."""
    values = {
        "data_provider": provider,
        "report_number": "2022010001",
        "campaign": 2022,
        "status": "Cerrado Revisión",
        "ignition": ignition,
        "start_date_time": datetime.datetime(2022, 1, 29, 14, 22, tzinfo=UTC),
        "end_date_time": datetime.datetime(2022, 1, 29, 15, 44, tzinfo=UTC),
        "time_zone": spain_egif.DEFAULT_TIME_ZONE,
        "ccaa_name": "EUSKADI",
        "province_name": "ALAVA",
        "province_ine_code": "01",
        "municipality_name": "KANPEZU/CAMPEZO",
        "comarca_name": "MONTAÑA",
        "minor_entity_name": "ANTOÑANA",
        "affected_municipality_count": 1,
        "area_ha_wooded": 0.19,
        "area_ha_non_wooded": 0.0,
        "area_ha_forest_total": 0.19,
        "area_ha_agricultural": 0.02,
        "area_ha_other_non_forest": 0.0,
        "wui_affected": False,
        "protected_space_affected": False,
        "agricultural_land_affected": False,
        "zar_affected": False,
    }
    values.update(overrides)
    return EgifWildfire(**values)


# --------------------------------------------------------------------------
# No perimeter, ever
# --------------------------------------------------------------------------

def test_an_egif_fire_has_no_perimeter(db_session, provider, ignition):
    """EGIF is an administrative statistic and publishes no polygon in any export.

    The column is on the generic model and stays NULL. A regional perimeter must
    never be written here — it would belong to a different provider than the row's
    ``data_provider_id`` says.
    """
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()
    db_session.expunge_all()

    assert db_session.scalar(select(EgifWildfire)).perimeter is None


def test_the_fire_is_located_by_its_ignition(db_session, provider, ignition):
    """The point is the only geometry an EGIF fire has."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.ignition.report_number == "2022010001"
    assert stored.ignition.utm_zone == 30


def test_a_fire_may_have_no_published_coordinate(db_session, provider):
    """293,710 of the 586,157 fires in the 1982-2023 archive have none.

    They are real *partes* of real fires that nobody located — 8,872 in 2004-2005,
    987 in 2011-2013, none from 2017 on. Requiring the link would have made the
    historical series unimportable, and would have cost 9% of the archive for a
    tidier column.
    """
    db_session.add(a_wildfire(provider, None))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.ignition is None
    assert stored.report_number == "2022010001"


# --------------------------------------------------------------------------
# Identity and the two exports
# --------------------------------------------------------------------------

def test_the_report_number_is_unique(db_session, provider, ignition):
    """It is the key both exports share, which is what keeps them on one row."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.add(a_wildfire(provider, ignition))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_fire_from_the_excel_export_has_no_internal_identifier(
        db_session, provider, ignition):
    """``idpif`` is published in the XML only, so it has to be nullable."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.egif_id is None
    assert stored.municipality_ine_code is None


def test_the_internal_identifier_is_unique_where_present(db_session, provider, ignition):
    second = EgifIgnition(
        data_provider=provider, report_number="2022010002",
        geometry="SRID=4326;POINT(-2.5 42.5)",
        date_time=datetime.datetime(2022, 2, 11, 16, 0, tzinfo=UTC),
        utm_zone=30, utm_x=540789.0, utm_y=4711612.0, datum=spain_egif.DATUM_ETRS89)
    db_session.add(second)
    db_session.add(a_wildfire(provider, ignition, egif_id=1205341))
    db_session.add(a_wildfire(provider, second, report_number="2022010002",
                              egif_id=1205341))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_many_fires_may_have_no_internal_identifier(db_session, provider, ignition):
    """A whole Excel-only database has none, so repeated NULLs must be allowed."""
    second = EgifIgnition(
        data_provider=provider, report_number="2022010002",
        geometry="SRID=4326;POINT(-2.5 42.5)",
        date_time=datetime.datetime(2022, 2, 11, 16, 0, tzinfo=UTC),
        utm_zone=30, utm_x=540789.0, utm_y=4711612.0, datum=spain_egif.DATUM_ETRS89)
    db_session.add(second)
    db_session.add(a_wildfire(provider, ignition))
    db_session.add(a_wildfire(provider, second, report_number="2022010002"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(EgifWildfire)) == 2


# --------------------------------------------------------------------------
# Administrative location
# --------------------------------------------------------------------------

def test_the_province_code_is_required(db_session, provider, ignition):
    """It is a pure function of the report number, so a missing one is a parser bug."""
    db_session.add(a_wildfire(provider, ignition, province_ine_code=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_province_code_is_the_middle_field_of_the_report_number(
        db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.province_ine_code == stored.report_number[4:6]


def test_the_municipal_code_may_be_absent_while_the_name_is_not(
        db_session, provider, ignition):
    """From the Excel there is only a name, and it needs a fuzzy match to become a code."""
    db_session.add(a_wildfire(provider, ignition,
                              municipality_name="MOLAR, EL", municipality_ine_code=None))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.municipality_name == "MOLAR, EL"
    assert stored.municipality_ine_code is None


def test_a_fire_may_cross_municipalities(db_session, provider, ignition):
    """354 of 13,656 do; the single municipality name is where it is *filed*."""
    db_session.add(a_wildfire(provider, ignition, affected_municipality_count=11))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfire)).affected_municipality_count == 11


# --------------------------------------------------------------------------
# Cause and motivation
# --------------------------------------------------------------------------

def test_a_fire_links_to_its_cause(db_session, provider, ignition, cause):
    db_session.add(a_wildfire(provider, ignition, cause=cause))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.cause.code == "213"
    assert stored.cause.label.startswith("Quema de restos")
    assert stored.motivation is None


def test_an_intentional_fire_carries_a_motivation_as_well(
        db_session, provider, ignition, motivation):
    """A motivation is published on cause 400 fires and on no others.

    The two are separate foreign keys because they are separate code spaces: this
    fire's cause code and motivation code are both in the 400s and mean unrelated
    things.
    """
    intentional = EgifFireCause(code=spain_egif.CAUSE_INTENTIONAL, label="Intencionado")
    db_session.add(intentional)
    db_session.add(a_wildfire(provider, ignition, cause=intentional, motivation=motivation))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.cause.code == "400"
    assert stored.motivation.code == "405"
    assert stored.cause.label != stored.motivation.label


def test_the_cause_may_be_unresolved(db_session, provider, ignition):
    """An XML import into a database with no seeded catalogue cannot resolve one."""
    db_session.add(a_wildfire(provider, ignition, cause=None, motivation=None))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.cause_id is None
    assert stored.motivation_id is None


# --------------------------------------------------------------------------
# Burnt areas
# --------------------------------------------------------------------------

def test_the_forest_areas_are_stored_as_published_even_though_they_add_up(
        db_session, provider, ignition):
    """wooded + non-wooded = total on all 13,656 rows of the sample.

    The total is stored anyway so a row can be compared with the source without
    doing arithmetic first.
    """
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.area_ha_wooded + stored.area_ha_non_wooded == stored.area_ha_forest_total


def test_the_agricultural_area_is_outside_the_forest_total(db_session, provider, ignition):
    """EGIF counts forest and non-forest separately; adding them double-counts nothing
    but produces a number that matches no published figure."""
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.area_ha_agricultural == 0.02
    assert stored.area_ha_forest_total == 0.19


def test_a_fire_may_publish_no_areas_at_all(db_session, provider, ignition):
    db_session.add(a_wildfire(
        provider, ignition, area_ha_wooded=None, area_ha_non_wooded=None,
        area_ha_forest_total=None, area_ha_agricultural=None,
        area_ha_other_non_forest=None))
    db_session.commit()

    assert db_session.scalar(select(EgifWildfire)).area_ha_forest_total is None


# --------------------------------------------------------------------------
# The wildland-urban interface flags
# --------------------------------------------------------------------------

def test_a_fire_may_affect_several_interface_types_at_once(db_session, provider, ignition):
    """The export publishes them concatenated (``"123"``); 51 fires have more than one."""
    db_session.add(a_wildfire(provider, ignition, wui_affected=True,
                              wui_compact=True, wui_scattered=True, wui_isolated=True))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert (stored.wui_compact, stored.wui_scattered, stored.wui_isolated) == (
        True, True, True)


def test_the_interface_types_are_unknown_rather_than_false_when_unpublished(
        db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()

    stored = db_session.scalar(select(EgifWildfire))
    assert stored.wui_affected is False
    assert stored.wui_compact is None


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_querying_the_parent_returns_the_subclass(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert isinstance(stored, EgifWildfire)
    assert stored.type == "egif_wildfire"


def test_the_campaign_is_required(db_session, provider, ignition):
    db_session.add(a_wildfire(provider, ignition, campaign=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repr_before_persist(provider, ignition):
    assert repr(a_wildfire(provider, ignition)) == (
        "EgifWildfire(id=None, report_number='2022010001', campaign=2022)")
