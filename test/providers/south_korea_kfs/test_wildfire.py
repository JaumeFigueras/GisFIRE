#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service model and the provider module.

The provider module carries what the importer leans on: the romanization, the
cause table and its classification, and the rule for an end that cannot be
right. The model is checked for the constraints that keep the two cause
vocabularies and the end-date reasons closed, and for the absence of anything
spatial.
"""

import datetime

import pytest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import south_korea_kfs
from src.providers.south_korea_kfs.causes import CAUSES
from src.providers.south_korea_kfs.wildfire import KfsWildfire

UTC = datetime.timezone.utc


# --------------------------------------------------------------------------
# Romanization
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("의성", "Uiseong"),
    ("안계", "Angye"),          # no liaison across ㄴ + ㄱ
    ("안평", "Anpyeong"),
    ("울진", "Uljin"),
    ("홍성", "Hongseong"),
    ("봉화", "Bonghwa"),
    ("강릉", "Gangneung"),      # ㅇ + ㄹ: the ㄹ is read n
    ("신라", "Silla"),          # ㄴ + ㄹ: ll
    ("종로", "Jongno"),
    ("선릉", "Seolleung"),
    ("독립문", "Dongnimmun"),   # nasalisation twice
    ("백마", "Baengma"),
    ("정선", "Jeongseon"),
    ("경북", "Gyeongbuk"),
    ("천안 서북", "Cheonan Seobuk"),  # each word capitalised
    ("남산2리", "Namsan2ri"),    # digits kept
])
def test_romanize_follows_the_revised_romanization(name, expected):
    assert south_korea_kfs.romanize(name) == expected


@pytest.mark.parametrize("value", [None, "", "  "])
def test_romanize_of_nothing_is_none(value):
    assert south_korea_kfs.romanize(value) is None


def test_romanize_trims_the_published_trailing_space():
    assert south_korea_kfs.romanize("강릉 ") == "Gangneung"


# --------------------------------------------------------------------------
# Causes
# --------------------------------------------------------------------------

def test_every_cause_has_a_translation_and_a_known_class():
    for text, (english, cause_class) in CAUSES.items():
        assert english, text
        assert cause_class in south_korea_kfs.CAUSE_CLASSES, text


def test_every_class_is_used():
    assert {cause_class for _, cause_class in CAUSES.values()} == set(
        south_korea_kfs.CAUSE_CLASSES)


def test_the_cause_table_is_keyed_by_normalised_text():
    for text in CAUSES:
        assert south_korea_kfs.normalise_cause(text) == text


def test_cause_translates_and_classifies():
    assert south_korea_kfs.cause("입산자실화") == ("Forest visitor negligence", "visitor")
    assert south_korea_kfs.cause("낙뢰")[1] == "lightning"


@pytest.mark.parametrize("published", [" 입산자실화", "입산자실화 ", "`입산자실화"])
def test_cause_ignores_the_published_stray_space_and_backtick(published):
    assert south_korea_kfs.cause(published)[1] == "visitor"


def test_an_unknown_cause_is_an_error_not_unknown():
    with pytest.raises(south_korea_kfs.UnmappedCauseError, match="외계인"):
        south_korea_kfs.cause("외계인")


@pytest.mark.parametrize("cause_class, expected", [
    ("lightning", "lightning"),
    ("unknown", "unknown"),
    ("rekindle", "unknown"),
    ("arson", "human"),
    ("visitor", "human"),
    ("other", "human"),
])
def test_fire_cause(cause_class, expected):
    assert south_korea_kfs.fire_cause(cause_class) == expected


def test_every_class_has_a_fire_cause():
    for cause_class in south_korea_kfs.CAUSE_CLASSES:
        assert south_korea_kfs.fire_cause(cause_class) in south_korea_kfs.FIRE_CAUSES


@pytest.mark.parametrize("text, expected", [
    ("입산자실화추정", True),
    ("방화의심", True),
    ("원인미상(수사중)", True),
    ("입산자실화", False),
])
def test_is_suspected(text, expected):
    assert south_korea_kfs.is_suspected(text) is expected


# --------------------------------------------------------------------------
# End dates
# --------------------------------------------------------------------------

START = datetime.datetime(2025, 3, 22, 11, 25)


@pytest.mark.parametrize("end, expected", [
    (datetime.datetime(2025, 3, 22, 18, 0), None),
    (START, None),
    (datetime.datetime(2026, 1, 2, 1, 0), None),       # into the next year
    (datetime.datetime(2025, 3, 22, 0, 0), "extinguish_before_start"),
    (datetime.datetime(2055, 3, 22, 18, 0), "extinguish_year_invalid"),
    (datetime.datetime(2223, 3, 22, 18, 0), "extinguish_year_invalid"),
    (None, "extinguish_year_invalid"),
])
def test_end_date_problem(end, expected):
    assert south_korea_kfs.end_date_problem(START, end) == expected


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=south_korea_kfs.PROVIDER_NAME,
                            product=south_korea_kfs.PROVIDER_PRODUCT,
                            full_name=south_korea_kfs.PROVIDER_FULL_NAME,
                            url=south_korea_kfs.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> KfsWildfire:
    """The Uiseong Angye fire of 22 March 2025."""
    values = {
        "data_provider": provider,
        "start_date_time": datetime.datetime(2025, 3, 22, 2, 25, tzinfo=UTC),
        "end_date_time": datetime.datetime(2025, 3, 28, 8, 0, tzinfo=UTC),
        "time_zone": "Asia/Seoul",
        "year": 2025,
        "source_file": "산불발생통계(20251110).csv",
        "source_row": 200,
        "office_name": "경북", "office_name_rr": "Gyeongbuk",
        "province_name": "경북", "province_name_rr": "Gyeongbuk",
        "municipality_name": "의성", "municipality_name_rr": "Uiseong",
        "township_name": "안계", "township_name_rr": "Angye",
        "village_name": "용기", "village_name_rr": "Yonggi",
        "cause_category_code": None,
        "cause_detail": "논밭두렁소각",
        "cause_text": "논밭두렁소각",
        "cause_text_en": "Rice-paddy and field-edge burning",
        "cause_class": "agricultural_burning",
        "fire_cause": "human",
        "cause_suspected": False,
        "area_ha": 52707.3,
        "end_date_problem": None,
    }
    values.update(overrides)
    return KfsWildfire(**values)


def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    fire = db_session.scalars(select(KfsWildfire)).one()
    assert fire.type == "kfs_wildfire"
    assert fire.municipality_name_rr == "Uiseong"
    assert fire.area_ha == 52707.3
    assert fire.perimeter is None
    assert fire.admin_boundary_id is None
    # Joined inheritance: the generic query sees it too.
    assert db_session.scalars(select(Wildfire)).one().id == fire.id


def test_names_below_the_province_may_be_null(db_session, provider):
    """Sejong has no municipality, and a city neighbourhood no township."""
    db_session.add(a_wildfire(provider, municipality_name=None, municipality_name_rr=None,
                              township_name=None, township_name_rr=None))
    db_session.commit()


def test_a_fire_with_a_bad_end_is_stored_without_one(db_session, provider):
    db_session.add(a_wildfire(provider, end_date_time=None,
                              end_date_problem="extinguish_before_start"))
    db_session.commit()


@pytest.mark.parametrize("overrides", [
    {"cause_class": "aliens"},
    {"fire_cause": "volcano"},
    {"end_date_problem": "late"},
    {"area_ha": -0.1},
])
def test_the_constraints_reject(db_session, provider, overrides):
    db_session.add(a_wildfire(provider, **overrides))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_published_cause_code_is_not_constrained(db_session, provider):
    db_session.add(a_wildfire(provider, cause_category_code="새"))
    db_session.commit()
