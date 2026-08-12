#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the readers and vocabularies in :mod:`src.providers.guatemala_inab`.

Every value pinned here was taken from the 4,615 published records rather than
invented, and the vocabulary tests assert *coverage*: each of the four closed
lists holds every value the publication actually uses, which is the property that
breaks first when INAB adds one.
"""

import pytest

from src.providers import guatemala_inab
from src.providers.guatemala_inab import DEPARTMENT_CODES
from src.providers.guatemala_inab import FIRE_LOCATIONS
from src.providers.guatemala_inab import PERSONAL_FIELDS
from src.providers.guatemala_inab import REPORT_CHANNELS
from src.providers.guatemala_inab import REPORT_STATUSES
from src.providers.guatemala_inab import blank_to_none
from src.providers.guatemala_inab import is_false_alarm
from src.providers.guatemala_inab import is_in_guatemala
from src.providers.guatemala_inab import national_municipality_code
from src.providers.guatemala_inab import parse_municipality


# --------------------------------------------------------------------------
# The vocabularies
# --------------------------------------------------------------------------

def test_every_published_report_status_is_known():
    """The five values estado_aviso takes across the 4,615 records."""
    assert set(REPORT_STATUSES) == {
        "cierre_operaciones", "falso", "no_verificado", "verdadero", "activo",
    }


def test_every_published_channel_is_known():
    assert set(REPORT_CHANNELS) == {
        "telefono", "personal", "app", "redes_sociales", "radio",
    }


def test_the_two_fire_locations_are_known():
    assert set(FIRE_LOCATIONS) == {"dentro_de_bosque", "fuera_de_bosque"}


def test_all_twenty_two_departments_are_mapped():
    """Guatemala has 22 departments and all 22 appear in the data."""
    assert len(DEPARTMENT_CODES) == 22
    assert sorted(DEPARTMENT_CODES.values()) == list(range(1, 23))


def test_the_department_codes_are_the_ine_ones():
    assert DEPARTMENT_CODES["guatemala"] == 1
    assert DEPARTMENT_CODES["huehuetenango"] == 13
    assert DEPARTMENT_CODES["peten"] == 17
    assert DEPARTMENT_CODES["zacapa"] == 19
    assert DEPARTMENT_CODES["jutiapa"] == 22


# --------------------------------------------------------------------------
# False alarms
# --------------------------------------------------------------------------

def test_falso_is_a_false_alarm():
    """140 of the 4,615 records. Any count of fires has to exclude them."""
    assert is_false_alarm(guatemala_inab.STATUS_FALSE)
    assert is_false_alarm("falso")


@pytest.mark.parametrize("status", [
    "cierre_operaciones", "no_verificado", "verdadero", "activo", None, "",
])
def test_nothing_else_is(status):
    assert not is_false_alarm(status)


def test_unverified_is_not_folded_into_false():
    """'Nobody checked' is a different claim from 'there was no fire'.

    90 records are no_verificado. Folding them in would turn 90 unknowns into 90
    non-events; they stay reachable on their own.
    """
    assert not is_false_alarm(guatemala_inab.STATUS_UNVERIFIED)
    assert guatemala_inab.STATUS_UNVERIFIED not in guatemala_inab.NON_FIRE_STATUSES
    assert guatemala_inab.NON_FIRE_STATUSES == (guatemala_inab.STATUS_FALSE,)


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("longitude,latitude", [
    (-90.5, 15.0),      # the middle of the country
    (-92.2, 14.6),      # the Mexican border
    (-88.3, 15.8),      # the Belize border
])
def test_a_guatemalan_point_is_recognised(longitude, latitude):
    assert is_in_guatemala(longitude, latitude)


@pytest.mark.parametrize("longitude,latitude,what", [
    (90.4735, 14.5007, "a longitude that lost its minus sign: Cambodia"),
    (91.7531, 15.7531, "the same again"),
    (-86.5239, 15.1300, "200 km inside Honduras"),
])
def test_the_three_published_strays_are_caught(longitude, latitude, what):
    """All three are already estado_aviso='falso' in the published data."""
    assert not is_in_guatemala(longitude, latitude), what


def test_a_missing_coordinate_is_not_in_guatemala():
    assert not is_in_guatemala(None, 15.0)
    assert not is_in_guatemala(-90.5, None)


def test_the_national_grid_has_no_epsg_code_and_is_defined_here():
    """GTM is a transverse Mercator on WGS 84 and is not in the EPSG registry.

    The registry's Guatemalan projected systems are the Ocotepeque 1935 Lambert
    zones, which this is not. The definition is verified against the data — see
    the constant's own documentation.
    """
    assert "+proj=tmerc" in guatemala_inab.GTM_PROJ
    assert "+lon_0=-90.5" in guatemala_inab.GTM_PROJ
    assert "+k=0.9998" in guatemala_inab.GTM_PROJ
    assert "+x_0=500000" in guatemala_inab.GTM_PROJ
    assert "+datum=WGS84" in guatemala_inab.GTM_PROJ


@pytest.mark.parametrize("longitude,latitude,easting,northing", [
    # Three published records that typed their GTM coordinates and were also
    # located on the map. Reprojecting the point reproduces the typed pair to the
    # metre — exactly, not approximately — which is what makes GTM_PROJ a
    # measurement rather than a guess.
    (-90.41411399999998, 17.383463000000063, 509125, 1922363),   # OBJECTID 4247
    (-89.67722199999995, 15.097217000000030, 588435, 1669578),   # OBJECTID 207
    (-90.42941299999997, 17.447390000000047, 507497, 1929436),   # OBJECTID 4657
])
def test_the_gtm_definition_reproduces_the_published_pairs(longitude, latitude,
                                                           easting, northing):
    """The typed GTM coordinates of real records, against their published points.

    If the projection were wrong this would be out by hundreds of kilometres,
    which is exactly what the three sign-flipped points elsewhere in this dataset
    look like. It is out by less than a metre.
    """
    pyproj = pytest.importorskip("pyproj")
    transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", guatemala_inab.GTM_PROJ, always_xy=True)

    x, y = transformer.transform(longitude, latitude)
    assert x == pytest.approx(easting, abs=1.0)
    assert y == pytest.approx(northing, abs=1.0)


# --------------------------------------------------------------------------
# The municipality code
# --------------------------------------------------------------------------

def test_a_four_digit_code_is_read():
    assert parse_municipality("rio_hondo_1903", "zacapa") == ("rio_hondo_1903", 1903)


def test_a_three_digit_code_is_read():
    """Department 01 publishes its codes without the leading zero."""
    assert parse_municipality("amatitlan_114", "guatemala") == ("amatitlan_114", 114)


def test_the_slug_is_returned_whole_with_its_code_still_on_it():
    """The provider's text is stored as published; the code is added beside it."""
    name, code = parse_municipality("san_andres_xecul_804", "totonicapan")
    assert name == "san_andres_xecul_804"
    assert code == 804


@pytest.mark.parametrize("slug,department", [
    ("san_rafael_la_independencia_131", "huehuetenango"),   # should be 1331
    ("san_sebastian_huehuetenango_132", "huehuetenango"),   # should be 1332
    ("fray_bartolome_de_las_casas_161", "alta_verapaz"),    # should be 1615
    ("san_rafael_pie_de_la_cuesta_121", "san_marcos"),      # should be 1221
])
def test_the_four_truncated_codes_are_rejected(slug, department):
    """Each has lost a digit, and a different one, so there is no rule to apply.

    22 records carry these. The code is rejected rather than guessed at; their
    department is still known from the department column.
    """
    name, code = parse_municipality(slug, department)
    assert name == slug, "the published slug is still stored"
    assert code is None, "a code naming the wrong department is not a code"


def test_a_code_is_believed_without_a_department_to_check_it_against():
    """Which is why the department should always be passed.

    '0131' is a perfectly well-formed code. It is simply not Huehuetenango, and
    only the department column can say so.
    """
    assert parse_municipality("san_rafael_la_independencia_131")[1] == 131


def test_a_slug_with_no_code_yields_none():
    assert parse_municipality("sin_codigo", "peten") == ("sin_codigo", None)


def test_nothing_yields_nothing():
    assert parse_municipality(None) == (None, None)
    assert parse_municipality("", "peten") == (None, None)
    assert parse_municipality("   ", "peten") == (None, None)


# --------------------------------------------------------------------------
# Blank handling
# --------------------------------------------------------------------------

def test_both_ways_of_being_unfilled_become_none():
    """The source marks 'not filled' as null *and* as "" in the same column.

    nombre_ap_1 alone is null on 80 records and "" on 3,080. Storing the second
    would report 3,080 fires inside a protected area named "".
    """
    assert blank_to_none(None) is None
    assert blank_to_none("") is None
    assert blank_to_none("   ") is None


def test_a_real_value_survives_with_its_padding_removed():
    """Published values carry trailing spaces: 'Josefinos ' and 'Josefinos'."""
    assert blank_to_none("Reserva de la Biosfera Maya") == "Reserva de la Biosfera Maya"
    assert blank_to_none("Josefinos ") == "Josefinos"
    assert blank_to_none(" Roger Agustin ") == "Roger Agustin"


def test_two_spellings_of_one_locality_fold_together():
    assert blank_to_none("Josefinos ") == blank_to_none("Josefinos")


def test_the_national_code_is_zero_padded_to_four():
    """A Guatemalan boundary layer publishes it as text; 114 will not match '0114'."""
    assert national_municipality_code(114) == "0114"
    assert national_municipality_code(1903) == "1903"
    assert national_municipality_code(None) is None


def test_the_padded_code_starts_with_its_department():
    for slug, department in (("rio_hondo_1903", "zacapa"),
                             ("amatitlan_114", "guatemala"),
                             ("flores_1701", "peten")):
        _, code = parse_municipality(slug, department)
        padded = national_municipality_code(code)
        assert int(padded[:2]) == DEPARTMENT_CODES[department]


# --------------------------------------------------------------------------
# Personal data
# --------------------------------------------------------------------------

def test_the_personal_columns_are_named_so_the_omission_is_deliberate():
    """1,969 distinct (name, phone) pairs are published; none is imported.

    Named rather than merely absent so the decision is on the record and a test
    can assert no model grew a column for one.
    """
    assert set(PERSONAL_FIELDS) == {
        "reportado_por", "telefono", "created_user", "last_edited_user",
    }


def test_no_model_column_holds_personal_data():
    """The guard on the decision: none of the four reached a column, under any name."""
    from src.providers.guatemala_inab.ignition import InabIgnition
    from src.providers.guatemala_inab.wildfire import InabWildfire

    columns = ({column.name for column in InabWildfire.__table__.columns}
               | {column.name for column in InabIgnition.__table__.columns})
    for field in PERSONAL_FIELDS:
        assert field not in columns
    # And the obvious English renamings of the same things.
    for banned in ("reported_by", "reporter", "reporter_name", "phone",
                   "telephone", "phone_number", "created_user", "edited_user"):
        assert banned not in columns


def test_the_institution_is_kept_because_it_is_not_a_person():
    from src.providers.guatemala_inab.wildfire import InabWildfire

    columns = {column.name for column in InabWildfire.__table__.columns}
    assert "institution" in columns
    assert "institution_other" in columns


# --------------------------------------------------------------------------
# Provider identity
# --------------------------------------------------------------------------

def test_the_published_crs_is_wgs84():
    assert guatemala_inab.SOURCE_SRID == 4326


def test_guatemala_is_one_time_zone_all_year():
    """No DST since 2006, so the zone is a rule here rather than a fallback."""
    assert guatemala_inab.DEFAULT_TIME_ZONE == "America/Guatemala"
