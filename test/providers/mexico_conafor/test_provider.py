#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the readers in :mod:`src.providers.mexico_conafor`.

These five functions are the whole of what stands between fourteen shapefiles
that disagree with each other and one set of columns, so each is pinned against
values taken from the published archives rather than invented ones.
"""

import datetime

import pytest

from src.providers import mexico_conafor
from src.providers.mexico_conafor import DATE_FORMATS
from src.providers.mexico_conafor import FIELD_ALIASES
from src.providers.mexico_conafor import PUBLISHED_YEARS
from src.providers.mexico_conafor import VEGETATION_CODES
from src.providers.mexico_conafor import field_value
from src.providers.mexico_conafor import is_missing
from src.providers.mexico_conafor import normalise
from src.providers.mexico_conafor import parse_date
from src.providers.mexico_conafor import parse_fire_code
from src.providers.mexico_conafor import split_vegetation_type


# --------------------------------------------------------------------------
# The series
# --------------------------------------------------------------------------

def test_the_series_runs_from_2010_to_2023_without_a_gap():
    assert PUBLISHED_YEARS == tuple(range(2010, 2024))
    assert len(PUBLISHED_YEARS) == 14


# --------------------------------------------------------------------------
# normalise()
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published", [
    "Impacto Minimo", "impacto minimo", "Impacto Mínimo", "IMPACTO  MINIMO",
    "Impacto Minimo\n", " Impacto Minimo ",
])
def test_every_spelling_of_impacto_minimo_folds_together(published):
    """Fourteen published spellings of three values; folding gets them to eight."""
    assert normalise(published) == "impacto minimo"


def test_normalise_strips_the_trailing_newlines_the_files_carry():
    """'Fogatas\\n' and 'Desconocidas\\n' are real values in the 2022 layer."""
    assert normalise("Fogatas\n") == normalise("Fogatas") == "fogatas"


def test_normalise_does_not_repair_mojibake():
    """The corruption is in the published file; guessing past it would be a guess."""
    assert normalise("BolaÃ±os") != normalise("Bolaños")


def test_normalise_of_none_is_empty():
    assert normalise(None) == ""


# --------------------------------------------------------------------------
# is_missing()
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published", [
    "", "0", "N/A", "Sin dato", "No", "Ninguna / No aplica", "n/d", None,
])
def test_the_null_tokens_are_recognised(published):
    """The archives have no single one, and every one of them has to become NULL."""
    assert is_missing(published)


@pytest.mark.parametrize("published", [
    "Fogatas", "Superficial", "Impacto Minimo", "Bosque de Pino", "0.0",
])
def test_a_real_value_is_not_missing(published):
    assert not is_missing(published)


# --------------------------------------------------------------------------
# field_value()
# --------------------------------------------------------------------------

def test_a_field_is_found_under_whichever_name_the_year_uses():
    """TIPVEG in 2010, TIPVEGE in 2011, TIP_VEG in 2016, TIPO_DE_VE in 2015."""
    for published in ("TIPVEG", "TIPVEGE", "TIP_VEG", "TIPO_DE_VE"):
        assert field_value({published: "Bosque de Pino"},
                           "vegetation_type") == "Bosque de Pino"


def test_the_2015_layer_reads_through_the_same_aliases():
    """It renames almost everything, the key included: CLAVE_DEL, not CLAVEINC."""
    row = {"OBJECTID": "1074", "ESTADO": "32.0", "CLAVE_DEL": "15-32-0007",
           "ESTADO_1": "Zacatecas", "ESTADO_DE": "Zacatecas",
           "TIPO_DE_IN": "Superficial", "TIPO_DE_VE": "Pastizal Natural - PN",
           "TIPO_DE_IM": "Impacto Minimo", "ANP_HECTAR": "0.0",
           "ARBADULTO": "0.0", "RENUEVO": "0.0", "ARBUSTIVO": "2.34",
           "HERBACEO": "28.42", "SUELOORG": "0.0", "AREA_HA": "30.76"}
    assert field_value(row, "fire_code") == "15-32-0007"
    assert field_value(row, "fire_type") == "Superficial"
    assert field_value(row, "vegetation_type") == "Pastizal Natural - PN"
    assert field_value(row, "impact_level") == "Impacto Minimo"
    assert field_value(row, "area_ha_shrub") == "2.34"
    assert field_value(row, "area_ha_herbaceous") == "28.42"
    assert field_value(row, "area_ha_organic_soil") == "0.0"


def test_the_state_name_is_taken_from_the_name_column_not_the_numeric_one():
    """In 2015 ``ESTADO`` is a **number** and the name is in ``ESTADO_1``.

    Reversing the alias order would silently store "32.0" as the name of a
    Mexican state for 1,105 fires, which no constraint would catch.
    """
    row_2015 = {"ESTADO": "32.0", "ESTADO_1": "Zacatecas",
                "ESTADO_DE": "Zacatecas de ..."}
    assert field_value(row_2015, "state_name") == "Zacatecas"
    # And every other layer, where ESTADO is the name and the only one there is.
    assert field_value({"ESTADO": "Zacatecas"}, "state_name") == "Zacatecas"


def test_the_2012_layer_reads_through_the_same_aliases():
    """A different file in every respect: CLAVE for the key, TOTAL for the area."""
    row = {"CLAVE": "12-01-0012", "TOTAL": "64", "ARB_ADUL": "0.64",
           "CAUSA_ESPE": "Fogatas de paseantes"}
    assert field_value(row, "fire_code") == "12-01-0012"
    assert field_value(row, "area_ha") == "64"
    assert field_value(row, "area_ha_tree") == "0.64"
    assert field_value(row, "specific_cause") == "Fogatas de paseantes"


def test_a_field_the_layer_does_not_publish_is_none():
    """2022 and 2023 publish a total and none of the six strata."""
    assert field_value({"AREA_HA": "3.41"}, "area_ha_tree") is None
    assert field_value({"AREA_HA": "3.41"}, "specific_cause") is None


def test_a_published_but_empty_field_is_not_none():
    """'This layer has no such field' and 'this row left it blank' stay distinct."""
    assert field_value({"CAUSAESP": ""}, "specific_cause") == ""


def test_an_unknown_attribute_raises():
    with pytest.raises(KeyError):
        field_value({}, "not_an_attribute")


def test_every_alias_tuple_is_non_empty():
    assert all(aliases for aliases in FIELD_ALIASES.values())


# --------------------------------------------------------------------------
# parse_fire_code()
# --------------------------------------------------------------------------

def test_the_key_splits_into_year_state_and_sequence():
    assert parse_fire_code("23-01-0001") == (23, 1, 1)
    assert parse_fire_code("21-20-0140") == (21, 20, 140)
    assert parse_fire_code("10-32-0004") == (10, 32, 4)


def test_the_state_code_keeps_its_leading_zero_as_a_number():
    """01 is Aguascalientes, and 1 is the integer that says so."""
    assert parse_fire_code("16-01-0102")[1] == 1


@pytest.mark.parametrize("bad", ["", "23-1-1", "2023-01-0001", "23/01/0001", None])
def test_a_malformed_key_yields_none(bad):
    assert parse_fire_code(bad) is None


# --------------------------------------------------------------------------
# parse_date()
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published,expected", [
    ("2010/05/29", datetime.date(2010, 5, 29)),   # 2010, 2013, 2014, 2016, 2017, 2020
    ("2011-08-22", datetime.date(2011, 8, 22)),   # 2011, 2012, 2018, 2019, 2021, 2023
    ("24/04/2022", datetime.date(2022, 4, 24)),   # 2022, slashed day-first
    ("10-02-2022", datetime.date(2022, 2, 10)),   # 2022, dashed day-first
])
def test_every_published_format_is_read(published, expected):
    assert parse_date(published) == expected


def test_an_ambiguous_date_is_read_day_first():
    """12/05/2022 is the 12th of May. The archive's day-first fields reach 31."""
    assert parse_date("12/05/2022") == datetime.date(2022, 5, 12)


def test_the_one_month_first_date_in_the_archive_is_recovered():
    """22-29-0003's '01/15/2022': no day-first reading exists, so this one is safe."""
    assert parse_date("01/15/2022") == datetime.date(2022, 1, 15)


def test_the_month_first_format_is_the_last_resort():
    """Order is what stops it stealing dates a day-first format can read."""
    assert DATE_FORMATS[-1] == "%m/%d/%Y"
    assert DATE_FORMATS.index("%d/%m/%Y") < DATE_FORMATS.index("%m/%d/%Y")


@pytest.mark.parametrize("bad", [
    "22/12/202",    # 21-19-0051: a three-digit year
    "22/20/2021",   # 21-21-0082: month 20
    "", "   ", None,
])
def test_an_unreadable_date_yields_none(bad):
    assert parse_date(bad) is None


def test_a_date_is_a_date_and_not_a_datetime():
    """No layer of any year publishes a time; the type should not pretend otherwise."""
    parsed = parse_date("2023-01-10")
    assert isinstance(parsed, datetime.date)
    assert not isinstance(parsed, datetime.datetime)


# --------------------------------------------------------------------------
# split_vegetation_type()
# --------------------------------------------------------------------------

def test_the_inegi_code_is_read_out_and_the_name_is_left_whole():
    """The published string is stored byte for byte; the code is added beside it."""
    assert split_vegetation_type("Bosque de Pino-Encino - BPQ") == (
        "Bosque de Pino-Encino - BPQ", "BPQ")


def test_a_name_without_a_code_yields_no_code():
    assert split_vegetation_type("Bosque de Pino") == ("Bosque de Pino", None)


def test_the_pino_of_bosque_de_encino_pino_is_not_read_as_a_code():
    """Twenty-two rows spell the mixture this way; only the fixed set tells them apart."""
    name, code = split_vegetation_type("Bosque de Encino - Pino")
    assert name == "Bosque de Encino - Pino"
    assert code is None
    assert "PINO" not in VEGETATION_CODES


def test_a_missing_vegetation_type_yields_nothing():
    """2011 writes '0' into TIPVEGE for 178 rows."""
    assert split_vegetation_type("0") == (None, None)
    assert split_vegetation_type(None) == (None, None)


def test_the_code_is_upper_cased():
    assert split_vegetation_type("Selva Baja Caducifolia - sbc")[1] == "SBC"


def test_the_code_set_is_what_the_archive_publishes():
    assert len(VEGETATION_CODES) == 50
    assert {"BP", "BPQ", "BQ", "BQP", "SBC", "MC", "PN"} <= VEGETATION_CODES
    # The eight that appear in the 2015 layer and nowhere else.
    assert {"BG", "MJ", "MK", "MKE", "MSCC", "MSN", "PT", "VM"} <= VEGETATION_CODES


# --------------------------------------------------------------------------
# Provider identity
# --------------------------------------------------------------------------

def test_the_published_crs_is_wgs84():
    """All thirteen archives carry a byte-identical .prj, and it is EPSG:4326."""
    assert mexico_conafor.SOURCE_SRID == 4326


def test_the_date_precisions_are_day_and_year_only():
    """No layer publishes a time, so there is no minute to declare."""
    assert mexico_conafor.DATE_TIME_PRECISIONS == ("year", "day")
