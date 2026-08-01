#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two EGIF export formats, each read into the same record.

:func:`read_excel` and :func:`read_xml` both yield :class:`PifRecord` — one per
fire, with the fields each format publishes filled in and the rest ``None``. That
is what lets the two import steps share one upsert: the difference between the
formats becomes which keys are set, not which code path runs.

Both readers **stream**. The XML exports run to 285 MB and the largest Excel to
6 MB of compressed XML, and neither is read into memory whole: the XML through
:func:`xml.etree.ElementTree.iterparse` with each ``<Pif>`` cleared once it has
been converted, the Excel through the same mechanism over the worksheet part
inside the ``.xlsx`` zip.

Why the Excel is not read with a library
----------------------------------------

``openpyxl`` in ``read_only`` mode would do it, at the cost of a dependency used
for exactly one file format in one importer. What is needed here is small: one
sheet, a header row, string cells resolved through the shared-string table. That
is forty lines against the stored XML, and it avoids a version of the "empty
cell" problem that a general reader has to guess at — see :data:`BLANKS`.

Nothing is validated here
-------------------------

A reader's job is to say what the file contains, not whether it is usable. A
fire with an unparseable date arrives with ``start_date_time`` set to ``None``
and the raw string in :attr:`PifRecord.problems`, and it is the importer that
decides such a fire cannot be stored. Keeping the two apart is what lets the
importer report *which* fire was dropped and why, rather than the reader raising
somewhere inside a 30,000-fire file.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
import typing
import xml.etree.ElementTree as ElementTree
import zipfile

from pathlib import Path

from src.providers import spain_egif

#: Cell values that mean "no value" in the Excel export.
#:
#: The export never leaves a cell truly empty. It writes a non-breaking space, a
#: run of ordinary spaces, or a hyphen, and which one it uses depends on the
#: column and the campaign: ``Datum`` is two spaces throughout 2002-2016,
#: ``NumeroPuntosInicioIncendio`` a non-breaking space, ``Motivacion`` a hyphen on
#: the 88,000 fires that are not intentional. A general-purpose reader hands all
#: three through as strings.
BLANKS = frozenset({"", "-", "\xa0"})

#: How the Excel prints a coded value: ``[213]  Quema de restos agrícolas``.
#:
#: The separator is two spaces in every file checked, but it is matched loosely
#: because nothing guarantees it and a label that arrived with one space would
#: otherwise be stored with a leading one — which would then be a *second*
#: catalogue entry for the same code, since the catalogue is unique on
#: ``(code, label)``.
CODED_LABEL = re.compile(r"^\[(?P<code>[^]]+)]\s*(?P<label>.*)$")

#: ``dd/mm/yyyy HH:MM:SS``, the only datetime format either export uses. Naive
#: local wall-clock in both; the zone is resolved by the importer.
EXCEL_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"

#: The XML's ``TipoInterfazAfectado`` / ``afectadourbanoforestalsi`` flags, which
#: arrive concatenated — ``"1"``, ``"23"``, ``"123"`` — one character per
#: interface type affected.
WUI_FLAGS = {"1": "wui_compact", "2": "wui_scattered", "3": "wui_isolated"}

#: ``Si`` / ``No``, and the third value the pre-2017 exports use.
#:
#: ``Sin determinar`` is not a missing value dressed up: it is what every fire
#: from 2002 to 2016 carries in ``AfectoZonasInterfazUrbanoForestal``, because the
#: question was not on the form then. It maps to ``None`` — unknown — rather than
#: to ``False``, which would assert that a quarter of a million fires reached no
#: wildland-urban interface.
BOOLEANS = {"si": True, "sí": True, "no": False, "sin determinar": None}


@dataclasses.dataclass(slots=True)
class PifRecord:
    """One *parte de incendio forestal*, as read from either export.

    Every field is optional except :attr:`report_number`, which is the key both
    formats share and the only thing the importer cannot proceed without. The
    fields a format does not publish stay ``None`` and the importer writes only
    the ones its step is responsible for — which is what stops an Excel re-import
    blanking the ``municipality_ine_code`` an XML import filled in.

    Attributes
    ----------
    report_number : str
        ``numeroparte``, ten characters.
    problems : list of str
        What could not be read, in words, for the importer to log against this
        fire. Empty for a clean record. A record with problems is not necessarily
        unusable: only the importer knows which fields it cannot do without.
    """

    report_number: str
    problems: list[str] = dataclasses.field(default_factory=list)

    # -- identity and filing
    egif_id: int | None = None
    campaign: int | None = None
    status: str | None = None

    # -- administrative location
    ccaa_name: str | None = None
    province_name: str | None = None
    province_ine_code: str | None = None
    municipality_name: str | None = None
    municipality_ine_code: str | None = None
    comarca_name: str | None = None
    minor_entity_name: str | None = None
    affected_municipality_count: int | None = None

    # -- the point
    utm_zone: int | None = None
    utm_x: float | None = None
    utm_y: float | None = None
    datum: str | None = None
    datum_code: str | None = None
    start_point_count: int | None = None
    mtn_sheet: str | None = None
    mtn_grid: str | None = None
    place_name: str | None = None

    # -- when
    start_date_time: datetime.datetime | None = None
    end_date_time: datetime.datetime | None = None

    # -- classification, as published: code plus label where the format has it
    cause_code: str | None = None
    cause_label: str | None = None
    motivation_code: str | None = None
    motivation_label: str | None = None

    # -- what burnt
    area_ha_wooded: float | None = None
    area_ha_non_wooded: float | None = None
    area_ha_forest_total: float | None = None
    area_ha_agricultural: float | None = None
    area_ha_other_non_forest: float | None = None

    # -- what it reached
    wui_affected: bool | None = None
    wui_compact: bool | None = None
    wui_scattered: bool | None = None
    wui_isolated: bool | None = None
    protected_space_affected: bool | None = None
    agricultural_land_affected: bool | None = None
    zar_affected: bool | None = None
    pss_report_number: str | None = None

    # -- the XML-only report
    has_report: bool = False
    control_date_time: datetime.datetime | None = None
    first_ground_response_date_time: datetime.datetime | None = None
    first_aerial_response_date_time: datetime.datetime | None = None
    first_helitransported_response_date_time: datetime.datetime | None = None
    first_coordination_response_date_time: datetime.datetime | None = None
    first_notification_from_112: bool | None = None
    detected_by_code: str | None = None
    started_next_to_other: str | None = None
    responsibility_grade_code: str | None = None
    days_since_storm: int | None = None
    cause_investigated_code: str | None = None
    cause_certainty_code: str | None = None
    offender_identified_code: str | None = None
    activity_authorisation_code: str | None = None
    day_class_code: str | None = None
    weather_station_code: str | None = None
    weather_observation_time: datetime.time | None = None
    days_since_rain: int | None = None
    max_temperature_celsius: float | None = None
    relative_humidity_percent: float | None = None
    wind_speed_km_h: float | None = None
    wind_direction_degrees: int | None = None
    max_severity_level: int | None = None
    fuel_model_codes: list[str] | None = None
    fire_type_codes: list[str] | None = None
    start_area_type_codes: list[str] | None = None
    started_next_to_codes: list[str] | None = None


# --------------------------------------------------------------------------
# Scalar conversion
# --------------------------------------------------------------------------

def clean(value: object) -> str | None:
    """Strip a published value, returning ``None`` for the blanks of :data:`BLANKS`."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    return None if text in BLANKS or not text else text


def as_int(value: object) -> int | None:
    """Read an integer, or ``None`` if it is blank or not one."""
    text = clean(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def as_float(value: object) -> float | None:
    """Read a number written with either decimal separator.

    The Excel writes areas as comma-decimal strings — ``"3,5000"`` — and the XML
    writes the same quantity with a point. Accepting both here is what lets one
    record type serve both readers.
    """
    text = clean(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def as_bool(value: object) -> bool | None:
    """Read ``Si``/``No``/``Sin determinar`` or the XML's ``True``/``False``."""
    text = clean(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in BOOLEANS:
        return BOOLEANS[lowered]
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    return None


def split_coded_label(value: object) -> tuple[str | None, str | None]:
    """Split ``"[213]  Quema de restos agrícolas"`` into its code and its label.

    Returns ``(None, None)`` for a blank cell, which is what the 88,000
    non-intentional fires carry in ``Motivacion``. A value that is present but not
    in this shape returns ``(None, text)`` — the label is kept, because an
    unparseable label is still evidence, and the importer reports it.
    """
    text = clean(value)
    if text is None:
        return None, None
    match = CODED_LABEL.match(text)
    if match is None:
        return None, text
    return match.group("code").strip(), match.group("label").strip()


def parse_excel_datetime(value: object) -> datetime.datetime | None:
    """Read ``dd/mm/yyyy HH:MM:SS`` as a naive local datetime."""
    text = clean(value)
    if text is None:
        return None
    try:
        return datetime.datetime.strptime(text, EXCEL_DATE_FORMAT)
    except ValueError:
        return None


def parse_xml_datetime(value: object) -> datetime.datetime | None:
    """Read the XML's ``xsd:dateTime`` as a naive local datetime.

    The published values carry no offset — ``2020-01-01T16:30:00`` — and are local
    wall-clock like the Excel's. One is discarded deliberately if it ever appears
    with a zone: the zone EGIF means is resolved from the fire's province, not
    from a string that has never been anything but naive.
    """
    text = clean(value)
    if text is None:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


# --------------------------------------------------------------------------
# The Excel export
# --------------------------------------------------------------------------

#: The worksheet XML namespace, and the only one either sheet part uses.
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Read the workbook's shared-string table.

    Every text cell in the sheet is an index into this, so it has to be read
    whole — but it is the *distinct* strings, which for even the largest export is
    a few hundred thousand short municipality and cause names rather than a row
    per fire.
    """
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{SHEET_NS}t"))
        for item in root.iter(f"{SHEET_NS}si")
    ]


def _worksheet_name(archive: zipfile.ZipFile) -> str:
    """The single worksheet part.

    Every EGIF export has exactly one sheet, but it is not always called
    ``sheet1.xml`` — the 2020-2023 export names it ``sheet.xml`` — so it is found
    rather than assumed.

    Raises
    ------
    RuntimeError
        If the workbook has no worksheet, or more than one and so no unambiguous
        choice.
    """
    sheets = sorted(
        name for name in archive.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    if not sheets:
        raise RuntimeError("workbook contains no worksheet")
    if len(sheets) > 1:
        raise RuntimeError(f"workbook contains {len(sheets)} worksheets ({', '.join(sheets)})")
    return sheets[0]


def column_index(reference: str) -> int:
    """Turn a cell reference's column letters into a zero-based index.

    ``"A"`` is 0, ``"Z"`` 25, ``"AA"`` 26 and ``"AE"`` — the last of the 31
    published columns — is 30.
    """
    index = 0
    for character in reference:
        if not character.isalpha():
            break
        index = index * 26 + (ord(character.upper()) - ord("A") + 1)
    return index - 1


def _rows(archive: zipfile.ZipFile, shared: list[str],
          width: int) -> typing.Iterator[list[str | None]]:
    """Yield each row of the worksheet as a list of ``width`` cell values.

    **Cells are placed by their ``r`` reference, not by document order**, and this
    is not defensive programming — reading by position silently corrupts real
    fires in this archive.

    The exports normally write all 31 cells of every row including the empty ones,
    but not always: two fires in the 2008-2010 export have no extinction time and
    the writer omitted the empty cell for it altogether, leaving those rows with
    30 cells running ``A``-``Q``, ``S``-``AE``. Read by position, everything from
    ``Extinguido`` on shifts one column left, and the result is a fire whose
    extinction time is its cause, whose cause is its motivation and whose burnt
    area is an interface flag — all of it well-formed enough to import without
    complaint. Placing each cell where its own reference says it goes gives the
    two rows a null ``Extinguido`` and leaves the other 483,000 unchanged.
    """
    with archive.open(_worksheet_name(archive)) as sheet:
        for _, row in ElementTree.iterparse(sheet, events=("end",)):
            if row.tag != f"{SHEET_NS}row":
                continue
            values: list[str | None] = [None] * width
            for position, cell in enumerate(row.iter(f"{SHEET_NS}c")):
                value = cell.find(f"{SHEET_NS}v")
                text = value.text if value is not None else None
                if cell.get("t") == "s" and text is not None:
                    text = shared[int(text)]
                elif cell.get("t") == "inlineStr":
                    inline = cell.find(f"{SHEET_NS}is")
                    text = "".join(node.text or "" for node in inline.iter(f"{SHEET_NS}t")) \
                        if inline is not None else None
                reference = cell.get("r")
                index = column_index(reference) if reference else position
                if 0 <= index < width:
                    values[index] = text
            yield values
            row.clear()


#: The 31 columns of the Excel "resumen", in published order.
#:
#: Identical in all eight exports from 2002 to 2023, which is checked on every
#: import: a file whose header differs is refused rather than read by position
#: into the wrong fields.
EXCEL_COLUMNS = (
    "Campania", "NumeroParte", "Estado", "Comunidad", "Provincia", "Municipio",
    "ComarcaIsla", "EntidadMenor", "NumeroMunicipiosAfectados", "Hoja", "Cuadricula",
    "Huso", "CoordenadaX", "CoordenadaY", "Datum", "NumeroPuntosInicioIncendio",
    "Detectado", "Extinguido", "Causa", "Motivacion", "SuperficieArbolada",
    "SuperficieNoArbolada", "SuperficieTotalForestal", "SuperficieAgricola",
    "OtrasSuperficiesNoforestales", "AfectoZonasInterfazUrbanoForestal",
    "TipoInterfazAfectado", "AfectoEspacioProtegido", "AfectoTierrasAgrarias",
    "AfectoZar", "NumeroPartePss",
)


def count_excel_rows(path: Path) -> int | None:
    """Count the fires in an export without converting them, for the progress bar.

    Counting is a second pass over the same file, which for a 6 MB workbook costs
    a fraction of a second and buys a bar with a percentage and an estimate rather
    than a bare running count. ``None`` if the file cannot be read at all, which
    :func:`read_excel` will report properly a moment later.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open(_worksheet_name(archive)) as sheet:
                rows = 0
                for _, element in ElementTree.iterparse(sheet, events=("end",)):
                    if element.tag == f"{SHEET_NS}row":
                        rows += 1
                        element.clear()
        return max(rows - 1, 0)  # less the header
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError):
        return None


def read_excel(path: Path) -> typing.Iterator[PifRecord]:
    """Yield one :class:`PifRecord` per fire in an Excel "resumen" export.

    Raises
    ------
    RuntimeError
        If the workbook's header is not :data:`EXCEL_COLUMNS`. Reading a sheet by
        position when the columns have moved would import every fire with its
        fields shuffled, and every one of them would look plausible.
    """
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        rows = _rows(archive, shared, len(EXCEL_COLUMNS))

        try:
            header = [clean(value) for value in next(rows)]
        except StopIteration:
            raise RuntimeError("workbook is empty") from None
        if tuple(header) != EXCEL_COLUMNS:
            unexpected = [name for name in header if name not in EXCEL_COLUMNS]
            missing = [name for name in EXCEL_COLUMNS if name not in header]
            raise RuntimeError(
                f"unexpected columns: the export should have the {len(EXCEL_COLUMNS)} "
                f"published ones and has {len(header)}"
                + (f"; missing {', '.join(missing)}" if missing else "")
                + (f"; unknown {', '.join(str(name) for name in unexpected)}" if unexpected else "")
            )

        for values in rows:
            row = dict(zip(EXCEL_COLUMNS, values))
            report_number = clean(row.get("NumeroParte"))
            if report_number is None:
                continue  # a trailing blank row, which some exports carry
            yield _excel_record(report_number, row)


def _excel_record(report_number: str, row: dict[str, str | None]) -> PifRecord:
    """Convert one worksheet row."""
    record = PifRecord(report_number=report_number)

    record.campaign = as_int(row.get("Campania"))
    record.status = clean(row.get("Estado"))
    record.ccaa_name = clean(row.get("Comunidad"))
    record.province_name = clean(row.get("Provincia"))
    record.municipality_name = clean(row.get("Municipio"))
    record.comarca_name = clean(row.get("ComarcaIsla"))
    record.minor_entity_name = clean(row.get("EntidadMenor"))
    record.affected_municipality_count = as_int(row.get("NumeroMunicipiosAfectados"))

    # The province code is taken from the report number, not from the province
    # name: it is characters 5-6 of every numeroparte and needs no lookup, and the
    # names are not unique enough to invert.
    if len(report_number) >= 6 and report_number[4:6].isdigit():
        record.province_ine_code = report_number[4:6]
    else:
        record.problems.append(f"report number {report_number!r} carries no province code")

    record.mtn_sheet = clean(row.get("Hoja"))
    record.mtn_grid = clean(row.get("Cuadricula"))
    record.utm_zone = as_int(row.get("Huso"))
    record.utm_x = as_float(row.get("CoordenadaX"))
    record.utm_y = as_float(row.get("CoordenadaY"))
    record.datum = clean(row.get("Datum"))
    record.start_point_count = as_int(row.get("NumeroPuntosInicioIncendio"))

    record.start_date_time = parse_excel_datetime(row.get("Detectado"))
    if record.start_date_time is None:
        record.problems.append(f"unreadable Detectado {clean(row.get('Detectado'))!r}")
    record.end_date_time = parse_excel_datetime(row.get("Extinguido"))

    record.cause_code, record.cause_label = split_coded_label(row.get("Causa"))
    record.motivation_code, record.motivation_label = split_coded_label(row.get("Motivacion"))
    if record.cause_label is not None and record.cause_code is None:
        record.problems.append(f"unreadable Causa {clean(row.get('Causa'))!r}")

    record.area_ha_wooded = as_float(row.get("SuperficieArbolada"))
    record.area_ha_non_wooded = as_float(row.get("SuperficieNoArbolada"))
    record.area_ha_forest_total = as_float(row.get("SuperficieTotalForestal"))
    record.area_ha_agricultural = as_float(row.get("SuperficieAgricola"))
    record.area_ha_other_non_forest = as_float(row.get("OtrasSuperficiesNoforestales"))

    record.wui_affected = as_bool(row.get("AfectoZonasInterfazUrbanoForestal"))
    for flag, attribute in WUI_FLAGS.items():
        setattr(record, attribute, flag in (clean(row.get("TipoInterfazAfectado")) or ""))
    if clean(row.get("TipoInterfazAfectado")) is None:
        record.wui_compact = record.wui_scattered = record.wui_isolated = None

    record.protected_space_affected = as_bool(row.get("AfectoEspacioProtegido"))
    record.agricultural_land_affected = as_bool(row.get("AfectoTierrasAgrarias"))
    record.zar_affected = as_bool(row.get("AfectoZar"))
    record.pss_report_number = clean(row.get("NumeroPartePss"))
    return record


# --------------------------------------------------------------------------
# The XML export
# --------------------------------------------------------------------------

#: The blocks of one ``<Pif>`` this import reads, and the scalar fields it takes
#: from each, as ``published name -> record attribute``.
#:
#: What is absent is as deliberate as what is here: ``pif_medios``,
#: ``pif_tecnicas``, ``pif_anexo`` and ``ParteMonte`` are not read at all. See
#: :mod:`src.providers.spain_egif` for the scope decision behind that.
XML_SCALARS: dict[str, dict[str, str]] = {
    "pif_comun": {"idpif": "egif_id", "anio": "campaign"},
    "pif_localizacion": {
        "paraje": "place_name",
        "nummunicipiosafectados": "affected_municipality_count",
        "puntosinicioincendio": "start_point_count",
        "huso": "utm_zone", "x": "utm_x", "y": "utm_y", "iddatum": "datum_code",
        "hoja": "mtn_sheet", "cuadricula": "mtn_grid",
    },
    "pif_tiempos": {
        "deteccion": "start_date_time",
        "extinguido": "end_date_time",
        "controlado": "control_date_time",
        "llegadapmt": "first_ground_response_date_time",
        "llegadapmae": "first_aerial_response_date_time",
        "llegadapbh": "first_helitransported_response_date_time",
        "llegadapac": "first_coordination_response_date_time",
    },
    "pif_deteccion": {
        "primeranotificaciondesde112": "first_notification_from_112",
        "iddetectadopor": "detected_by_code",
        "iniciadojuntootros": "started_next_to_other",
    },
    "pif_causa": {
        "idcausa": "cause_code", "idmotivacion": "motivation_code",
        "idgradoresponsabilidad": "responsibility_grade_code",
        "diastormenta": "days_since_storm",
        "idinvestigacioncausa": "cause_investigated_code",
        "idcertidumbrecausa": "cause_certainty_code",
        "idcausante": "offender_identified_code",
        "idautorizacionactividad": "activity_authorisation_code",
        "idclasedia": "day_class_code",
    },
    "pif_condiciones": {
        "idestacionmeteorologica": "weather_station_code",
        "diasultimalluvia": "days_since_rain",
        "tempmaxima": "max_temperature_celsius",
        "humrelativa": "relative_humidity_percent",
        "velocidadviento": "wind_speed_km_h",
        "direccionviento": "wind_direction_degrees",
    },
    "pif_perdidas": {
        "superficiearboladatotal": "area_ha_wooded",
        "superficienoarboladatotal": "area_ha_non_wooded",
        "superficienoarboladaagricola": "area_ha_agricultural",
        "superficienoarboladaotras": "area_ha_other_non_forest",
    },
    "pif_incidencias": {
        "afectozonasinterfazurbanoforestal": "wui_affected",
        "afectoespacionnatprot": "protected_space_affected",
        "afectotierraagrariarefores": "agricultural_land_affected",
        "afectozar": "zar_affected",
        "idnivelgravedadmaximo": "max_severity_level",
    },
}

#: Which record attribute each scalar needs converting with. Anything not named
#: here is read as text, which is right for the bare ``id*`` codes: they are
#: identifiers, and one of them is zero-padded (``idestacionmeteorologica`` is
#: ``"080055"``).
XML_CONVERTERS: dict[str, typing.Callable[[object], object]] = {
    "egif_id": as_int,
    "campaign": as_int,
    "affected_municipality_count": as_int,
    "start_point_count": as_int,
    "utm_zone": as_int,
    "utm_x": as_float,
    "utm_y": as_float,
    "days_since_storm": as_int,
    "days_since_rain": as_int,
    "max_temperature_celsius": as_float,
    "relative_humidity_percent": as_float,
    "wind_speed_km_h": as_float,
    "wind_direction_degrees": as_int,
    "max_severity_level": as_int,
    "area_ha_wooded": as_float,
    "area_ha_non_wooded": as_float,
    "area_ha_agricultural": as_float,
    "area_ha_other_non_forest": as_float,
    "first_notification_from_112": as_bool,
    "wui_affected": as_bool,
    "protected_space_affected": as_bool,
    "agricultural_land_affected": as_bool,
    "zar_affected": as_bool,
    "start_date_time": parse_xml_datetime,
    "end_date_time": parse_xml_datetime,
    "control_date_time": parse_xml_datetime,
    "first_ground_response_date_time": parse_xml_datetime,
    "first_aerial_response_date_time": parse_xml_datetime,
    "first_helitransported_response_date_time": parse_xml_datetime,
    "first_coordination_response_date_time": parse_xml_datetime,
}

#: The four multi-valued code lists, as ``block -> relation -> (field, attribute)``.
#:
#: Each is read into a sorted list of distinct codes. Sorting is not cosmetic:
#: these are sets — verified duplicate-free within a fire across 29,926 fires —
#: and storing them in document order would make two identical sets compare
#: unequal in any test or diff that looks at the array.
XML_CODE_LISTS: dict[str, dict[str, tuple[str, str]]] = {
    "pif_condiciones": {
        "RelModeloCombustionPif": ("idmodelocombustion", "fuel_model_codes"),
    },
    "pif_propagacion": {
        "RelTipoFuegoPif": ("idtipofuego", "fire_type_codes"),
    },
    "pif_deteccion": {
        "RelTipoAreaIniciadoPif": ("idtipoarea", "start_area_type_codes"),
        "RelIniciadoJuntoAPif": ("idiniciadojuntoa", "started_next_to_codes"),
    },
}


def read_xml(path: Path) -> typing.Iterator[PifRecord]:
    """Yield one :class:`PifRecord` per ``<Pif>`` in an XML export.

    The first ~37 KB of an export is an inline XSD schema.
    :func:`xml.etree.ElementTree.iterparse` walks straight past it: the schema's
    elements are in the XSD namespace and only ``<Pif>`` is acted on, so it costs
    a parse of 37 KB and no special handling.

    Each ``<Pif>`` is cleared as soon as it has been converted, which is what
    keeps a 285 MB export inside a few megabytes of memory.
    """
    for _, element in ElementTree.iterparse(str(path), events=("end",)):
        if element.tag != "Pif":
            continue
        record = _xml_record(element)
        element.clear()
        if record is not None:
            yield record


def _xml_record(element: ElementTree.Element) -> PifRecord | None:
    """Convert one ``<Pif>``, or ``None`` if it carries no report number."""
    report_number = clean(element.findtext("numeroparte"))
    if report_number is None:
        return None

    record = PifRecord(report_number=report_number, has_report=True)

    for block_name, fields in XML_SCALARS.items():
        block = element.find(block_name)
        if block is None:
            continue
        for published, attribute in fields.items():
            raw = block.findtext(published)
            converter = XML_CONVERTERS.get(attribute, clean)
            value = converter(raw)
            if value is not None:
                setattr(record, attribute, value)

    for block_name, relations in XML_CODE_LISTS.items():
        block = element.find(block_name)
        if block is None:
            continue
        for relation, (published, attribute) in relations.items():
            codes = {
                code for code in (
                    clean(child.findtext(published)) for child in block.findall(relation)
                ) if code is not None
            }
            if codes:
                setattr(record, attribute, sorted(codes))

    _xml_location(element, record)
    _xml_conditions(element, record)
    _xml_incidences(element, record)

    # The forest total is the one published area the XML does not carry: the Excel
    # prints ``SuperficieTotalForestal`` and ``pif_perdidas`` has only the two
    # parts. It is exactly their sum on all 13,656 rows checked, so it is derived
    # rather than left null — which is what lets an XML-only import be compared
    # against the published national figures.
    if record.area_ha_wooded is not None and record.area_ha_non_wooded is not None:
        record.area_ha_forest_total = record.area_ha_wooded + record.area_ha_non_wooded

    if record.start_date_time is None:
        record.problems.append("no deteccion")
    return record


def _xml_location(element: ElementTree.Element, record: PifRecord) -> None:
    """Derive the two INE codes and the forest total from ``pif_localizacion``.

    ``idprovincia`` and ``idmunicipio`` are published as bare integers and the
    five-digit INE municipal code is the two of them zero-padded and joined —
    ``8`` and ``91`` make ``"08091"``. That this really is the INE code and not an
    internal numbering was checked against the Excel export of the same fires: the
    5,264 codes it produces map one-to-one onto the Excel's
    ``(Provincia, Municipio)`` name pairs across all 29,926 fires of 2020-2023,
    with no code naming two municipalities and no municipality carrying two codes.
    """
    block = element.find("pif_localizacion")
    if block is None:
        return

    province = clean(block.findtext("idprovincia"))
    municipality = clean(block.findtext("idmunicipio"))
    if province is not None and province.isdigit():
        record.province_ine_code = province.zfill(2)
        if municipality is not None and municipality.isdigit():
            record.municipality_ine_code = province.zfill(2) + municipality.zfill(3)
    elif len(record.report_number) >= 6 and record.report_number[4:6].isdigit():
        record.province_ine_code = record.report_number[4:6]

    record.datum = spain_egif.DATUM_CODES.get(record.datum_code or "")
    if record.datum_code is not None and record.datum is None:
        record.problems.append(f"unknown iddatum {record.datum_code!r}, datum left unset")


def _xml_conditions(element: ElementTree.Element, record: PifRecord) -> None:
    """Take the time of day, and only the time, from ``pif_condiciones/hora``.

    The published value is a full datetime whose date is the data-entry date, not
    the observation's: a fire detected on 2020-01-01 at 16:30 carries an
    observation stamped 2023-12-18 at 16:35. The time of day is the observation's
    and is kept; the date is dropped rather than stored as a falsehood with the
    truth inside it.
    """
    block = element.find("pif_condiciones")
    if block is None:
        return
    stamped = parse_xml_datetime(block.findtext("hora"))
    if stamped is not None:
        record.weather_observation_time = stamped.time()


def _xml_incidences(element: ElementTree.Element, record: PifRecord) -> None:
    """Split ``afectadourbanoforestalsi`` into the three interface flags.

    Published as one concatenated string of digits — ``"1"``, ``"23"``, ``"123"``
    — because a fire can reach any combination of the three, and 51 fires in the
    sample reach more than one. Absent where no interface was affected, which is
    ``None`` for all three rather than ``False``: the field says which *were*
    affected and is silent when the answer is none, and
    :attr:`PifRecord.wui_affected` already carries that.
    """
    block = element.find("pif_incidencias")
    if block is None:
        return
    flags = clean(block.findtext("afectadourbanoforestalsi"))
    if flags is None:
        return
    for flag, attribute in WUI_FLAGS.items():
        setattr(record, attribute, flag in flags)
