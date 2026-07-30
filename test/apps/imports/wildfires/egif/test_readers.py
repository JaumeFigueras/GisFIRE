#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the two EGIF export readers.

The integration tests in ``test_import_wildfires`` cover what the readers produce
once it has been through the database. These cover the conversions themselves,
where the interesting cases are all things the *published files* do rather than
things a caller could do wrong.
"""

import datetime

import pytest

from src.apps.imports.wildfires.egif import readers

from .conftest import block
from .conftest import code_list
from .conftest import excel_row
from .conftest import write_excel
from .conftest import write_xml


# --------------------------------------------------------------------------
# Scalar conversion
# --------------------------------------------------------------------------

@pytest.mark.parametrize("published", ["", "-", "\xa0", "  ", " \xa0 "])
def test_every_way_the_export_writes_nothing_reads_as_nothing(published):
    """The exports never leave a cell empty; which filler they use varies.

    ``Datum`` is two spaces throughout 2002-2016, ``NumeroPuntosInicioIncendio`` a
    non-breaking space, ``Motivacion`` a hyphen on the 88,000 fires that are not
    intentional.
    """
    assert readers.clean(published) is None


def test_a_value_that_only_looks_blank_is_kept():
    assert readers.clean(" 30 ") == "30"


@pytest.mark.parametrize("published,expected", [
    ("3,5000", 3.5),      # the Excel writes comma decimals
    ("3.5000", 3.5),      # the XML writes point decimals
    ("0,0000", 0.0),
    ("-", None),
    ("no", None),
])
def test_areas_are_read_with_either_decimal_separator(published, expected):
    """One record type serves both formats, so both separators have to work."""
    assert readers.as_float(published) == expected


@pytest.mark.parametrize("published,expected", [
    ("Si", True), ("No", False), ("True", True), ("False", False),
    ("Sin determinar", None), ("\xa0", None),
])
def test_sin_determinar_is_unknown_and_not_false(published, expected):
    """Every fire from 2002 to 2016 carries it: the question was not on the form.

    Reading it as ``False`` would assert that a quarter of a million fires reached
    no wildland-urban interface, which the export does not say.
    """
    assert readers.as_bool(published) is expected


@pytest.mark.parametrize("published,code,label", [
    ("[213]  Quema de restos agrícolas", "213", "Quema de restos agrícolas"),
    ("[100] Rayo", "100", "Rayo"),                    # one space, not two
    ("-", None, None),
    ("0,3500", None, "0,3500"),                       # present but not a coded label
])
def test_a_coded_label_is_split_into_its_parts(published, code, label):
    assert readers.split_coded_label(published) == (code, label)


def test_a_column_reference_becomes_its_index():
    assert readers.column_index("A") == 0
    assert readers.column_index("Z") == 25
    assert readers.column_index("AA") == 26
    assert readers.column_index("AE") == 30   # the last published column


# --------------------------------------------------------------------------
# The Excel
# --------------------------------------------------------------------------

def test_an_omitted_cell_does_not_shift_the_rest_of_the_row(tmp_path):
    """The 2008-2010 export omits the cell for an empty ``Extinguido``.

    Read by position everything after column R moves one left and the row still
    parses — into a fire whose cause is its extinction time. Read by reference it
    is one null in the right place.
    """
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "NumeroParte": "2010100090", "Detectado": "06/05/2010 12:27:00",
        "Extinguido": None,
        "Causa": "[400]  Intencionado", "SuperficieArbolada": "0,3500",
        "AfectoZar": "No",
    })])

    record, = readers.read_excel(tmp_path / "e.xlsx")
    assert record.start_date_time == datetime.datetime(2010, 5, 6, 12, 27)
    assert record.end_date_time is None
    assert record.cause_code == "400"
    assert record.area_ha_wooded == pytest.approx(0.35)
    assert record.zar_affected is False


def test_the_province_code_comes_from_the_report_number(tmp_path):
    """Characters 5-6 of every ``numeroparte``, and the leading zero matters."""
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "NumeroParte": "2022010001", "Detectado": "01/01/2022 10:00:00"})])

    record, = readers.read_excel(tmp_path / "e.xlsx")
    assert record.province_ine_code == "01"


def test_a_workbook_whose_columns_moved_is_refused(tmp_path):
    write_excel(tmp_path / "e.xlsx", [{"NumeroParte": "1"}],
                header=("NumeroParte", "Campania"))

    with pytest.raises(RuntimeError, match="unexpected columns"):
        list(readers.read_excel(tmp_path / "e.xlsx"))


def test_the_rows_can_be_counted_without_converting_them(tmp_path):
    """Which is what lets the Excel bars carry a percentage and an estimate."""
    rows = [excel_row({"NumeroParte": f"20200800{n:02d}",
                       "Detectado": "01/01/2020 10:00:00"}) for n in range(7)]
    write_excel(tmp_path / "e.xlsx", rows)

    assert readers.count_excel_rows(tmp_path / "e.xlsx") == 7


def test_counting_a_file_that_is_not_a_workbook_says_so_quietly(tmp_path):
    """The count is only for the bar, so it defers the real complaint to the read."""
    (tmp_path / "e.xlsx").write_text("not a zip at all")
    assert readers.count_excel_rows(tmp_path / "e.xlsx") is None


# --------------------------------------------------------------------------
# The XML
# --------------------------------------------------------------------------

def minimal_pif(report_number: str = "2020080001", **blocks) -> str:
    parts = [f"<numeroparte>{report_number}</numeroparte>"]
    parts.append(block("pif_tiempos",
                       {"deteccion": blocks.get("deteccion", "2020-01-01T16:30:00")}))
    parts.extend(blocks.get("extra", []))
    return "<Pif>" + "".join(parts) + "</Pif>"


def test_the_inline_schema_is_walked_past(tmp_path):
    """Every real export begins with ~37 KB of XSD before the first fire."""
    write_xml(tmp_path / "e.xml", [minimal_pif()])

    records = list(readers.read_xml(tmp_path / "e.xml"))
    assert [record.report_number for record in records] == ["2020080001"]


def test_the_ine_municipal_code_is_the_two_padded_ids_joined(tmp_path):
    """``8`` and ``91`` make ``"08091"`` — checked against the Excel names."""
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_localizacion", {"idprovincia": 8, "idmunicipio": 91})])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.province_ine_code == "08"
    assert record.municipality_ine_code == "08091"


def test_the_code_lists_are_read_as_sorted_sets(tmp_path):
    """They are sets — no fire repeats a code — and sorting makes them comparable."""
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_condiciones", {},
              code_list("RelModeloCombustionPif", "idmodelocombustion",
                        ["3", "2", "3"]))])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.fuel_model_codes == ["2", "3"]


def test_an_absent_code_list_is_none_rather_than_an_empty_list(tmp_path):
    """"The export said nothing" and "the report said none" are different facts."""
    write_xml(tmp_path / "e.xml", [minimal_pif()])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.fuel_model_codes is None
    assert record.fire_type_codes is None


def test_the_weather_observation_keeps_only_its_time_of_day(tmp_path):
    """The published date is the data-entry date, three years after the fire."""
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_condiciones", {"hora": "2023-12-18T16:35:00"})])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.weather_observation_time == datetime.time(16, 35)


def test_the_forest_total_is_derived_from_its_two_parts(tmp_path):
    """``pif_perdidas`` publishes the parts; only the Excel prints the sum."""
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_perdidas", {"superficiearboladatotal": "2.5200",
                               "superficienoarboladatotal": "6.1400"})])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.area_ha_forest_total == pytest.approx(8.66)


def test_the_interface_flags_arrive_concatenated(tmp_path):
    """``"13"`` means compact and isolated, not thirteen of anything."""
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_incidencias", {"afectadourbanoforestalsi": "13"})])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert (record.wui_compact, record.wui_scattered, record.wui_isolated) == (
        True, False, True)


def test_an_unmappable_datum_code_is_reported_and_kept(tmp_path):
    write_xml(tmp_path / "e.xml", [minimal_pif(extra=[
        block("pif_localizacion", {"idprovincia": 8, "iddatum": 3})])])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.datum_code == "3"
    assert record.datum is None
    assert any("iddatum" in problem for problem in record.problems)


def test_a_fire_with_no_detection_says_so(tmp_path):
    write_xml(tmp_path / "e.xml", ["<Pif><numeroparte>2020080001</numeroparte></Pif>"])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.start_date_time is None
    assert "no deteccion" in record.problems


def test_a_pif_with_no_report_number_is_not_a_fire(tmp_path):
    write_xml(tmp_path / "e.xml", ["<Pif><idpif>1</idpif></Pif>", minimal_pif()])

    records = list(readers.read_xml(tmp_path / "e.xml"))
    assert [record.report_number for record in records] == ["2020080001"]


def test_every_xml_record_carries_the_report_flag(tmp_path):
    """Which is what makes ``egif_wildfire_report``'s existence the provenance."""
    write_xml(tmp_path / "e.xml", [minimal_pif()])

    record, = readers.read_xml(tmp_path / "e.xml")
    assert record.has_report is True
