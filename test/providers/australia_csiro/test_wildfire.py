#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CSIRO model and the provider constants.

Six things are worth pinning down here, and every one of them is a decision that
would be invisible in the column list alone: that a prescribed burn is stored and is
told apart by ``fire_type`` rather than dropped; that ``fire_id`` is not a key and
its sentinels are recognised as sentinels; that **nothing is merged**, so two fires
may share every published column and still be two rows; that both feature classes'
spellings of a state, a type and a cause normalise to one value; that a published
date can be an epoch artefact, a fire from the year 200 or an end before its start,
and is flagged rather than corrected; and that nothing here stores a second
geometry.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import australia_csiro
from src.providers.australia_csiro.wildfire import CsiroWildfire

UTC = datetime.timezone.utc

#: A square somewhere in the Victorian mallee, in the CRS the generic model stores.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((141.50 -35.10, 141.52 -35.10, "
                  "141.52 -35.08, 141.50 -35.08, 141.50 -35.10)))")


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=australia_csiro.PROVIDER_NAME,
                            product=australia_csiro.PROVIDER_PRODUCT,
                            full_name=australia_csiro.PROVIDER_FULL_NAME,
                            url=australia_csiro.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> CsiroWildfire:
    """One Australian mapped burn, with everything the geodatabase publishes."""
    values = {
        "data_provider": provider,
        "source_layer": australia_csiro.LAYER_NATIONAL,
        "object_id": 705270,
        "year": 2018,
        "fire_id": "705270",
        "fire_id_is_sentinel": False,
        "fire_name": "Murray Sunset - Cowra Wilderness",
        "state_published": "VIC (Victoria)",
        "state_code": australia_csiro.STATE_VIC,
        "agency": "VIC DEECA",
        "fire_type_published": "Prescribed Burn",
        "fire_type": australia_csiro.FIRE_TYPE_PRESCRIBED_BURN,
        "cause_published": "Undetermined",
        "cause": australia_csiro.CAUSE_UNDETERMINED,
        "capture_method_published": "Landsat",
        "capture_method": "landsat",
        "ignition_date": datetime.date(2018, 5, 26),
        "extinguish_date": datetime.date(2018, 6, 2),
        "capture_date": None,
        "date_source": australia_csiro.SOURCE_IGNITION,
        "date_time_precision": australia_csiro.PRECISION_DAY,
        "dates_plausible": True,
        "area_ha": 474.0,
        "perim_km": 812.0,
        "start_date_time": datetime.datetime(2018, 5, 25, 14, 0, tzinfo=UTC),
        "end_date_time": datetime.datetime(2018, 6, 1, 14, 0, tzinfo=UTC),
        "time_zone": "Australia/Melbourne",
        "perimeter": PERIMETER_4326,
    }
    values.update(overrides)
    return CsiroWildfire(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_provider_is_named_from_the_distribution_and_not_from_the_file():
    """The geodatabase carries no publisher; these four values come from the page."""
    assert australia_csiro.PROVIDER_NAME == "CSIRO"
    assert australia_csiro.PROVIDER_FULL_NAME.startswith("Commonwealth Scientific")
    assert australia_csiro.PROVIDER_URL.startswith("https://digital.atlas.gov.au/")


def test_the_source_crs_is_gda94():
    """4283, and geographic — which is why no second geometry is stored."""
    assert australia_csiro.SOURCE_SRID == 4283


def test_both_feature_classes_are_named():
    """One provider, two published classes, told apart by source_layer."""
    assert set(australia_csiro.SOURCE_LAYERS) == {"national", "nt"}
    assert australia_csiro.LAYER_FEATURE_CLASSES[australia_csiro.LAYER_NATIONAL] == (
        "National_Historical_Bushfire_Extents_v4")
    assert australia_csiro.LAYER_FEATURE_CLASSES[australia_csiro.LAYER_NT] == (
        "NT_Historical_Bushfire_Extents_v1")


def test_a_prescribed_burn_is_a_type_and_not_an_exclusion():
    """Half the archive is deliberate burning and all of it is stored."""
    assert australia_csiro.FIRE_TYPE_PRESCRIBED_BURN in australia_csiro.FIRE_TYPES
    assert australia_csiro.FIRE_TYPE_BUSHFIRE in australia_csiro.FIRE_TYPES
    assert australia_csiro.FIRE_TYPE_UNKNOWN in australia_csiro.FIRE_TYPES


@pytest.mark.parametrize("published, expected", [
    ("Prescribed Burn", australia_csiro.FIRE_TYPE_PRESCRIBED_BURN),
    ("Prescribed burn", australia_csiro.FIRE_TYPE_PRESCRIBED_BURN),
    ("Bushfire", australia_csiro.FIRE_TYPE_BUSHFIRE),
    ("Unknown", australia_csiro.FIRE_TYPE_UNKNOWN),
    (None, australia_csiro.FIRE_TYPE_UNKNOWN),
])
def test_the_two_spellings_of_prescribed_burn_are_one_type(published, expected):
    """154,891 features say "Prescribed Burn" and 11,157 say "Prescribed burn"."""
    assert australia_csiro.normalise_fire_type(published) == expected


@pytest.mark.parametrize("published, expected", [
    ("WA (Western Australia)", australia_csiro.STATE_WA),
    ("WA", australia_csiro.STATE_WA),
    ("Qld", australia_csiro.STATE_QLD),
    ("NT", australia_csiro.STATE_NT),
    ("ACT (Australian Capital Territory)", australia_csiro.STATE_ACT),
    ("Nowhere", None),
])
def test_the_two_state_vocabularies_normalise_to_one(published, expected):
    """The national class writes the long name, the NT class writes the code."""
    assert australia_csiro.normalise_state(published) == expected


@pytest.mark.parametrize("published, expected", [
    ("Undetermined", australia_csiro.CAUSE_UNDETERMINED),
    ("NOT DETERMINED", australia_csiro.CAUSE_UNDETERMINED),
    ("WF - unknown", australia_csiro.CAUSE_UNDETERMINED),
    ("Natural", australia_csiro.CAUSE_NATURAL),
    ("Incendiary", australia_csiro.CAUSE_INCENDIARY),
    ("Accidental", australia_csiro.CAUSE_ACCIDENTAL),
    # A fifth category with no canonical form here: the row keeps it in
    # cause_published and cause stays NULL, rather than being forced into one of
    # the four it is not.
    ("OTHER", None),
    (None, None),
])
def test_the_causes_normalise_and_other_stays_unreconciled(published, expected):
    assert australia_csiro.normalise_cause(published) == expected


def test_natural_is_the_lightning_proxy_and_is_not_lightning():
    """As in NBAC and ICNF: the nearest thing to lightning, and not lightning."""
    assert australia_csiro.CAUSE_NATURAL == "natural"
    assert not any("ightning" in cause for cause in australia_csiro.FIRE_CAUSES)


def test_the_date_sources_are_ordered_by_preference():
    """Ignition, then the day it was declared out, then the day it was mapped."""
    assert australia_csiro.DATE_SOURCES == ("ignition", "extinguish", "capture")


def test_there_is_only_day_precision():
    """Every timestamp in both classes is at 00:00:00; there is no minute and no year."""
    assert australia_csiro.DATE_TIME_PRECISIONS == ("day",)


@pytest.mark.parametrize("published", ["999", "0", "-1", "", "   ", None])
def test_a_sentinel_fire_id_is_recognised(published):
    """186,632 national features have no usable identifier; none may be grouped on."""
    assert australia_csiro.is_sentinel_fire_id(published) is True


@pytest.mark.parametrize("published", ["705270", "WKM_023", "12731"])
def test_a_real_fire_id_is_not_a_sentinel(published):
    assert australia_csiro.is_sentinel_fire_id(published) is False


@pytest.mark.parametrize("ignition, extinguish, expected", [
    (datetime.date(2018, 5, 26), datetime.date(2018, 6, 2), True),
    (datetime.date(2018, 5, 26), None, True),
    (None, None, True),
    # The ArcGIS epoch, written out: 127 features.
    (datetime.date(1899, 12, 30), None, False),
    (datetime.date(1900, 1, 1), None, False),
    # The year 200 and the year 2525, both published as extinguish dates.
    (datetime.date(2018, 5, 26), datetime.date(200, 8, 14), False),
    (datetime.date(2025, 5, 1), datetime.date(2525, 5, 15), False),
    # Extinguished before it ignited: 341 national features and 24 NT ones.
    (datetime.date(2018, 6, 2), datetime.date(2018, 5, 26), False),
])
def test_the_implausible_dates_are_recognised(ignition, extinguish, expected):
    """A flag and not a fix — the dates are stored as published either way."""
    assert australia_csiro.dates_are_plausible(ignition, extinguish) is expected


def test_the_state_time_zones_cover_every_state():
    """The fallback when a perimeter matches no time zone area."""
    assert set(australia_csiro.STATE_TIME_ZONES) == set(australia_csiro.STATE_CODES)
    assert all(zone.startswith("Australia/")
               for zone in australia_csiro.STATE_TIME_ZONES.values())


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_wildfire_is_stored_and_read_back(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    fire = db_session.scalar(select(CsiroWildfire))
    assert fire.fire_name == "Murray Sunset - Cowra Wilderness"
    assert fire.state_code == australia_csiro.STATE_VIC
    assert fire.fire_type == australia_csiro.FIRE_TYPE_PRESCRIBED_BURN
    assert fire.perimeter is not None


def test_it_is_a_wildfire_of_its_own_type(db_session, provider):
    """Joined table inheritance: the generic query finds it, typed."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    fire = db_session.scalar(select(Wildfire))
    assert isinstance(fire, CsiroWildfire)
    assert fire.type == "csiro_wildfire"


def test_the_published_value_survives_beside_the_normalised_one(db_session, provider):
    """Both halves are stored: the spelling a reader recognises, and the one used."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    fire = db_session.scalar(select(CsiroWildfire))
    assert fire.state_published == "VIC (Victoria)"
    assert fire.state_code == "VIC"
    assert fire.fire_type_published == "Prescribed Burn"
    assert fire.fire_type == "prescribed_burn"


def test_a_layer_and_object_id_identify_one_row(db_session, provider):
    """Every published feature belongs to exactly one row, so its OBJECTID is a key."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    db_session.add(a_wildfire(provider, fire_id="999999", ignition_date=None,
                              date_source=australia_csiro.SOURCE_CAPTURE,
                              capture_date=datetime.date(2019, 1, 1)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_same_object_id_in_the_other_layer_is_a_different_row(db_session, provider):
    """The two feature classes number their features independently."""
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, source_layer=australia_csiro.LAYER_NT,
                              state_published="NT",
                              state_code=australia_csiro.STATE_NT,
                              fire_id="14085"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(CsiroWildfire)) == 2


def test_two_features_of_one_burn_are_two_rows(db_session, provider):
    """Nothing is merged, and nothing refuses the second patch.

    An earlier revision had a unique index over
    ``(source_layer, state_code, fire_id, ignition_date)``, on the reading that those
    four identify a fire. They do not — Western Australian district numbers are
    reused across the state, putting features 2,400 km apart under one value — so the
    archive is stored one row per published polygon and this is the test that says
    the constraint is gone.
    """
    db_session.add(a_wildfire(provider))
    db_session.add(a_wildfire(provider, object_id=705271))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(CsiroWildfire)) == 2


def test_the_same_fire_id_on_another_day_is_another_row(db_session, provider):
    """541342 is 3,496 features over three ignition dates."""
    db_session.add(a_wildfire(provider, fire_id="541342", year=2021,
                              ignition_date=datetime.date(2021, 4, 29)))
    db_session.add(a_wildfire(provider, object_id=705271, fire_id="541342", year=2023,
                              ignition_date=datetime.date(2023, 3, 23)))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(CsiroWildfire)) == 2


def test_the_same_fire_id_in_another_state_is_another_row(db_session, provider):
    """Fourteen (fire_id, date) pairs are used by both NSW and the ACT."""
    db_session.add(a_wildfire(provider, fire_id="11566.0",
                              state_published="NSW (New South Wales)",
                              state_code=australia_csiro.STATE_NSW))
    db_session.add(a_wildfire(provider, object_id=705271, fire_id="11566.0",
                              state_published="ACT (Australian Capital Territory)",
                              state_code=australia_csiro.STATE_ACT))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(CsiroWildfire)) == 2


def test_the_sentinel_rows_do_not_collide_either(db_session, provider):
    """145,694 features publish '999'; every one of them is its own row."""
    for object_id in (331619, 331620, 331621):
        db_session.add(a_wildfire(provider, object_id=object_id, fire_id="999",
                                  fire_id_is_sentinel=True, year=2017,
                                  ignition_date=datetime.date(2017, 12, 15),
                                  state_published="WA (Western Australia)",
                                  state_code=australia_csiro.STATE_WA))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(CsiroWildfire)) == 3


def test_a_null_fire_id_has_to_say_it_is_a_sentinel(db_session, provider):
    """Every Queensland feature publishes none, and a missing number is a placeholder."""
    db_session.add(a_wildfire(provider, fire_id=None, fire_id_is_sentinel=False))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("column, value", [
    ("source_layer", "queensland"),
    ("state_code", "QLDX"),
    ("fire_type", "planned"),
    ("cause", "arson"),
    ("date_source", "guessed"),
    ("date_time_precision", "minute"),
])
def test_the_vocabularies_are_constrained(db_session, provider, column, value):
    db_session.add(a_wildfire(provider, **{column: value}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_an_unpublished_cause_and_an_unreconciled_one_are_both_null(db_session, provider):
    """NULL cause means two different things, and cause_published tells them apart."""
    db_session.add(a_wildfire(provider, cause_published=None, cause=None))
    db_session.add(a_wildfire(provider, object_id=705271, fire_id="705271",
                              cause_published="OTHER", cause=None))
    db_session.commit()

    published = {fire.cause_published
                 for fire in db_session.scalars(select(CsiroWildfire))}
    assert published == {None, "OTHER"}


def test_an_implausible_fire_is_stored_as_published(db_session, provider):
    """The year 2525 is kept, flagged, and not corrected."""
    db_session.add(a_wildfire(provider, extinguish_date=datetime.date(2525, 5, 15),
                              dates_plausible=False))
    db_session.commit()

    fire = db_session.scalar(select(CsiroWildfire))
    assert fire.extinguish_date == datetime.date(2525, 5, 15)
    assert fire.dates_plausible is False


def test_the_year_is_what_an_import_replaces(db_session, provider):
    """Not a published attribute: the year of the resolved start, and NOT NULL.

    The archive is one geodatabase read a year at a time, one transaction each, so
    the year is the unit that gets deleted and rewritten — which only works if every
    row has one.
    """
    db_session.add(a_wildfire(provider, year=2018))
    db_session.add(a_wildfire(provider, object_id=705271, fire_id="705271", year=2019,
                              ignition_date=datetime.date(2019, 4, 29)))
    db_session.commit()

    kept = db_session.scalars(
        select(CsiroWildfire).where(CsiroWildfire.year == 2019)).all()
    assert [fire.object_id for fire in kept] == [705271]


def test_a_fire_without_a_year_is_refused(db_session, provider):
    db_session.add(a_wildfire(provider, year=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_there_is_no_second_geometry_column():
    """EPSG:4283 is degrees; a copy of the 4326 perimeter would answer nothing.

    Stated as a test because every other perimeter provider in the project keeps a
    second geometry, and the reason this one does not is a property of the published
    CRS rather than an oversight.
    """
    columns = set(CsiroWildfire.__table__.columns.keys())
    assert not any("perimeter" in column or "geometry" in column for column in columns)
