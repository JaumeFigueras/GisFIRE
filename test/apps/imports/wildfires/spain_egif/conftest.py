#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the EGIF import tests.

The fixtures are **built the way the service publishes**, not the way a
spreadsheet library would write them, because two of the things that go wrong
with this source are properties of the published encoding rather than of the
data:

* the Excel writes text through a shared-string table and gives every cell an
  ``r`` reference, and it **omits a cell entirely** when its value is empty —
  which is what makes two real fires shift a column under a positional reader;
* the XML export begins with ~37 KB of inline XSD schema before the first
  ``<Pif>``, so a reader that assumes the document starts with data would find
  nothing.

Both are reproduced here. A fixture written with ``openpyxl`` would test neither.
"""

from __future__ import annotations

import zipfile

from pathlib import Path

from src.apps.imports.wildfires.spain_egif.readers import EXCEL_COLUMNS

#: A minimal but valid workbook part set, namespaced the way the exports are
#: (``x:`` prefixed) so the readers are exercised against the real shape.
CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK = """<?xml version="1.0" encoding="utf-8"?>
<x:workbook xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<x:sheets><x:sheet name="Hoja1" sheetId="1" r:id="rId1"/></x:sheets></x:workbook>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""


def column_reference(index: int) -> str:
    """``0`` -> ``"A"``, ``26`` -> ``"AA"``, ``30`` -> ``"AE"``."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def excel_row(values: dict[str, str | None]) -> dict[str, str | None]:
    """One fire's row, defaulting every unnamed column to the export's blanks.

    The defaults are the ones the real exports use — a non-breaking space for an
    unset value, ``Sin determinar`` for the interface question that did not exist
    before 2017 — so a test that names three columns still exercises the blank
    handling on the other twenty-eight.
    """
    row = {name: "\xa0" for name in EXCEL_COLUMNS}
    row["AfectoZonasInterfazUrbanoForestal"] = "Sin determinar"
    row.update(values)
    return row


def write_excel(path: Path, rows: list[dict[str, str | None]],
                header: tuple[str, ...] = EXCEL_COLUMNS) -> Path:
    """Write a workbook in the shape the EGIF service exports.

    A cell whose value is ``None`` is **left out of the row entirely**, ``r``
    references and all, which is exactly what the 2008-2010 export does for the
    two fires with no extinction time.
    """
    strings: list[str] = []
    index_of: dict[str, int] = {}

    def shared(value: str) -> int:
        if value not in index_of:
            index_of[value] = len(strings)
            strings.append(value)
        return index_of[value]

    body = []
    for number, row in enumerate([dict(zip(header, header)), *rows], start=1):
        cells = []
        for column, name in enumerate(header):
            value = row.get(name)
            if value is None:
                continue  # the omitted-cell case
            reference = f"{column_reference(column)}{number}"
            cells.append(f'<x:c r="{reference}" t="s"><x:v>{shared(str(value))}</x:v></x:c>')
        body.append(f'<x:row r="{number}">{"".join(cells)}</x:row>')

    def escape(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    sheet = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<x:worksheet xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<x:sheetData>{"".join(body)}</x:sheetData></x:worksheet>'
    )
    shared_strings = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<x:sst xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">'
        + "".join(f"<x:si><x:t>{escape(value)}</x:t></x:si>" for value in strings)
        + "</x:sst>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet.xml", sheet)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
    return path


#: Stands in for the ~37 KB of inline XSD every real export begins with. Shorter,
#: but structurally the same thing: elements in another namespace, before the
#: first ``<Pif>``, that the reader has to walk past.
INLINE_SCHEMA = (
    '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" id="Pifs">'
    '<xsd:element name="Pif"><xsd:complexType><xsd:sequence>'
    '<xsd:element name="numeroparte" type="xsd:int"/>'
    '</xsd:sequence></xsd:complexType></xsd:element></xsd:schema>'
)


def element(name: str, value: object) -> str:
    """One element, or nothing at all when the value is ``None``.

    Absence rather than emptiness is how the XML says "not published" for most of
    the archive — ``iddatum`` before 2014, the coordinate on 22,855 fires — so the
    fixtures have to be able to leave an element out.
    """
    return "" if value is None else f"<{name}>{value}</{name}>"


def block(name: str, fields: dict[str, object],
          relations: str = "") -> str:
    """One ``pif_*`` block, omitting the fields that are ``None``."""
    inner = "".join(element(key, value) for key, value in fields.items())
    return f"<{name}>{inner}{relations}</{name}>"


def code_list(relation: str, field: str, codes: list[str]) -> str:
    """A repeated ``Rel*`` element carrying one bare code each."""
    return "".join(f"<{relation}><{field}>{code}</{field}></{relation}>" for code in codes)


def write_xml(path: Path, pifs: list[str]) -> Path:
    """Write an export: the inline schema, then the fires."""
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<pifs>{INLINE_SCHEMA}{''.join(pifs)}</pifs>",
        encoding="utf-8-sig",
    )
    return path
