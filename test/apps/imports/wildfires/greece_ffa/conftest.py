#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the Greek Fire Service import tests.

The workbooks are written with ``openpyxl``, which is also what reads them — so
unlike the EGIF fixtures next door, which hand-write the stored XML because the
*encoding* is what goes wrong there, these fixtures are about **shape**. What goes
wrong with this source is the shape of the sheet, and all of it is reproduced here:

* the header is two rows deep (four in the 2025 file), and which row it is on
  varies by year;
* the column set changes six times over twenty-six years, so
  :func:`sheet_columns` builds the header a given year really published;
* the same field is spelled differently in different years — the line-break
  hyphen of ``ΒΥΤΙΟ- ΦΟΡΑ``, and the **Latin** ``A`` of the 2025 ``A/A ENGAGE``;
* dates are Excel datetimes except in 2025, where they are ``dd/mm/yyyy`` text,
  and times are ``datetime.time`` in some years and ``HH:MM`` text in others;
* an unlocated fire is written ``0``/``0``, not blank.

A fixture that wrote one tidy modern sheet would exercise none of that.
"""

from __future__ import annotations

import datetime

from pathlib import Path

import openpyxl

#: The 2000-2008 header: sixteen columns, no municipality, no deployment block.
HEADER_2000 = (
    "Υπηρεσία", "Δασαρχείο", "Περιοχή - Τοποθεσία", "Νομός",
    "Ημερ/νία Έναρξης", "Ώρα Έναρξης", "Ημερ/νία Κατασβεσης", "Ώρα Κατάσβεσης",
    "Δάση", "Δασική Έκταση", "Άλση", "Χορτ/κές Εκτάσεις", "Καλάμια - Βάλτοι",
    "Γεωργικές Εκτάσεις", "Υπολλείματα Καλλιεργειών", "Σκουπιδότοποι",
)

#: The 2012-2019 header: the locality has split, and the deployment block is
#: there. Written with the hyphenated spellings the real sheets use.
HEADER_2012 = (
    "Υπηρεσία", "Νομός", "Ημερ/νία Έναρξης", "Ώρα Έναρξης",
    "Ημερ/νία Κατασβεσης", "Ώρα Κατάσβεσης", "Δασαρχείο", "Δήμος", "Περιοχή",
    "Διεύθυνση",
    "Δάση", "Δασική Έκταση", "Άλση", "Χορτ/κές Εκτάσεις", "Καλάμια - Βάλτοι",
    "Γεωργικές Εκτάσεις", "Υπολλείματα Καλλιεργειών", "Σκουπι-δότοποι",
    "ΠΥΡΟΣ. ΣΩΜΑ", "ΠΕΖΟΠΟΡΑ ΤΜΗΜΑΤΑ", "ΕΘΕΛΟ-ΝΤΕΣ", "ΣΤΡΑΤΟΣ", "ΑΛΛΕΣ ΔΥΝΑΜΕΙΣ",
    "ΠΥΡΟΣ. ΟΧΗΜ.", "ΟΧΗΜ. ΟΤΑ", "ΒΥΤΙΟ- ΦΟΡΑ", "ΜΗΧΑΝΗ-ΜΑΤΑ",
    "ΕΛΙΚΟ- ΠΤΕΡΑ", "Α/Φ CL415", "Α/Φ CL215", "Α/Φ PZL", "Α/Φ GRU.",
)

#: The 2022-2024 header: the identifiers and the coordinates are there, the
#: municipal vehicles have been renamed, and the leased aircraft have arrived.
HEADER_2022 = (
    "Α/Α ΕΓΓΡΑΦΗΣ", "Α/Α ENGAGE", "X-ENGAGE", "Y-ENGAGE",
    "Υπηρεσία", "Νομός", "Ημερ/νία Έναρξης", "Ώρα Έναρξης",
    "Ημερ/νία Κατασβεσης", "Ώρα Κατάσβεσης", "Δασαρχείο", "Δήμος", "Περιοχή",
    "Διεύθυνση",
    "Δάση", "Δασική Έκταση", "Άλση", "Χορτ/κές Εκτάσεις", "Καλάμια - Βάλτοι",
    "Γεωργικές Εκτάσεις", "Υπολλείματα Καλλιεργειών", "Σκουπι-δότοποι",
    "ΠΥΡΟΣ. ΣΩΜΑ", "ΠΕΖΟΠΟΡΑ ΤΜΗΜΑΤΑ", "ΕΘΕΛΟ-ΝΤΕΣ", "ΣΤΡΑΤΟΣ", "ΑΛΛΕΣ ΔΥΝΑΜΕΙΣ",
    "ΠΥΡΟΣ. ΟΧΗΜ.", "ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ", "ΒΥΤΙΟ- ΦΟΡΑ", "ΜΗΧΑΝΗ-ΜΑΤΑ",
    "ΕΛΙΚΟ- ΠΤΕΡΑ", "Α/Φ CL415", "Α/Φ CL215", "Α/Φ PZL", "Α/Φ GRU.",
    "ΜΙΣΘ. ΕΛΙΚΟΠΤ.", "ΜΙΣΘ. ΑΕΡΟΣΚ.",
)

#: The 2025 header. ``A/A ENGAGE`` is written with a **Latin** ``A`` here and with
#: the Greek ``Α`` (U+0391) in every other year — the two render identically. The
#: incident category arrives, ``Α/Φ GRU.`` is gone, and the hyphenated spellings
#: have been tidied up.
HEADER_2025 = (
    "Α/Α ΕΓΓΡΑΦΗΣ", "A/A ENGAGE", "X-ENGAGE", "Y-ENGAGE",
    "Υπηρεσία", "Νομός", "Ημερ/νία Έναρξης", "Ώρα Έναρξης",
    "Ημερ/νία Κατασβεσης", "Ώρα Κατάσβεσης", "Δασαρχείο", "Δήμος", "Περιοχή",
    "Κατηγορία Συμβάντος", "Διεύθυνση",
    "Δάση", "Δασική Έκταση", "Άλση", "Χορτ/κές Εκτάσεις", "Καλάμια - Βάλτοι",
    "Γεωργικές Εκτάσεις", "Υπολλείματα Καλλιεργειών", "Σκουπιδότοποι",
    "ΠΥΡΟΣ. ΣΩΜΑ", "ΠΕΖΟΠΟΡΑ ΤΜΗΜΑΤΑ", "ΕΘΕΛΟΝΤΕΣ", "ΣΤΡΑΤΟΣ", "ΑΛΛΕΣ ΔΥΝΑΜΕΙΣ",
    "ΠΥΡΟΣ. ΟΧΗΜ.", "ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ", "ΒΥΤΙΟΦΟΡΑ", "ΜΗΧΑΝΗΜΑΤΑ",
    "ΕΛΙΚΟΠΤΕΡΑ", "Α/Φ CL415", "Α/Φ CL215", "Α/Φ PZL",
    "ΜΙΣΘ. ΕΛΙΚΟΠΤ.", "ΜΙΣΘ. ΑΕΡΟΣΚ.", "ΑΛΛΩΝ ΦΟΡΕΩΝ",
)

#: The banner row that sits above every real header, grouping the columns. None of
#: its four labels is a column name, which is what the header search relies on.
BANNER = {
    "ΚΑΜΜΕΝΗ ΕΚΤΑΣΗ (Σε Στρέμματα)": "Δάση",
    "ΠΡΟΣΩΠΙΚΟ": "ΠΥΡΟΣ. ΣΩΜΑ",
    "ΟΧΗΜΑΤΑ": "ΠΥΡΟΣ. ΟΧΗΜ.",
    "ΕΝΑΕΡΙΑ": "ΕΛΙΚΟ- ΠΤΕΡΑ",
}


def banner_row(header: tuple[str, ...]) -> list[str | None]:
    """The grouping row a sheet carries above its column names.

    Each label sits over the first column of its group, exactly as published, and
    every other cell is empty — which is what makes the row look like a header to
    a naive reader and like nothing at all to this one.
    """
    row: list[str | None] = [None] * len(header)
    for label, first in BANNER.items():
        for column, name in enumerate(header):
            if name == first or (first == "ΕΛΙΚΟ- ΠΤΕΡΑ" and name == "ΕΛΙΚΟΠΤΕΡΑ"):
                row[column] = label
                break
    return row


def fire(header: tuple[str, ...], **values) -> list[object]:
    """One data row, keyed by published header name.

    Unnamed columns are left ``None`` — a genuinely empty cell, which is what these
    workbooks write and what a year that does not publish a column leaves behind.
    """
    row: list[object] = [None] * len(header)
    for name, value in values.items():
        row[header.index(name)] = value
    return row


def write_workbook(path: Path, sheets: dict[str, tuple[tuple[str, ...], list[list[object]]]],
                   preamble: dict[str, list[list[object]]] | None = None,
                   banner: bool = True) -> Path:
    """Write a workbook in the shape the service publishes.

    Parameters
    ----------
    path : pathlib.Path
        Where to write it.
    sheets : dict
        Sheet name to ``(header, rows)``. A sheet named with four digits is a year
        the way every file but one names it.
    preamble : dict, optional
        Sheet name to rows written **above** the banner, which is how the 2025 file
        states its year (``Για το ΕΤΟΣ:``, then ``2025``).
    banner : bool
        Whether to write the grouping row above the header. True for every real
        sheet; the tests turn it off to check the header search does not depend on
        it.

    Returns
    -------
    pathlib.Path
        ``path``, for chaining.
    """
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, (header, rows) in sheets.items():
        worksheet = workbook.create_sheet(title=name)
        for row in (preamble or {}).get(name, []):
            worksheet.append(row)
        if banner:
            worksheet.append(banner_row(header))
        worksheet.append(list(header))
        for row in rows:
            worksheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def a_2022_fire(**overrides) -> list[object]:
    """The first row of the real 2022 sheet: a fire near Kalamos, Attica."""
    values = {
        "Α/Α ΕΓΓΡΑΦΗΣ": 1799346, "Α/Α ENGAGE": 970757,
        "X-ENGAGE": 23.86, "Y-ENGAGE": 38.28,
        "Υπηρεσία": "Π.Κ. ΚΑΛΑΜΟΥ", "Νομός": "ΑΤΤΙΚΗΣ",
        "Ημερ/νία Έναρξης": datetime.datetime(2022, 6, 14),
        "Ώρα Έναρξης": "13:24",
        "Ημερ/νία Κατασβεσης": datetime.datetime(2022, 6, 16),
        "Ώρα Κατάσβεσης": "20:59",
        "Δασαρχείο": None, "Δήμος": "Δ. ΩΡΩΠΟΥ", "Περιοχή": "ΚΑΛΑΜΟΣ",
        "Διεύθυνση": "ΘΕΣΗ ΧΙΛΙΟΠΟΤΑΜΟΣ",
        "Δάση": 0, "Δασική Έκταση": 3, "Άλση": 0, "Χορτ/κές Εκτάσεις": 1,
        "Καλάμια - Βάλτοι": 0, "Γεωργικές Εκτάσεις": 17,
        "Υπολλείματα Καλλιεργειών": 0.9, "Σκουπι-δότοποι": 0,
        "ΠΥΡΟΣ. ΣΩΜΑ": 28, "ΠΕΖΟΠΟΡΑ ΤΜΗΜΑΤΑ": 22, "ΕΘΕΛΟ-ΝΤΕΣ": 15,
        "ΣΤΡΑΤΟΣ": 0, "ΑΛΛΕΣ ΔΥΝΑΜΕΙΣ": 9,
        "ΠΥΡΟΣ. ΟΧΗΜ.": 15, "ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ": 9, "ΒΥΤΙΟ- ΦΟΡΑ": 2,
        "ΜΗΧΑΝΗ-ΜΑΤΑ": 1,
        "ΕΛΙΚΟ- ΠΤΕΡΑ": 0, "Α/Φ CL415": 0, "Α/Φ CL215": 0, "Α/Φ PZL": 0,
        "Α/Φ GRU.": 0, "ΜΙΣΘ. ΕΛΙΚΟΠΤ.": 2, "ΜΙΣΘ. ΑΕΡΟΣΚ.": 0,
    }
    values.update(overrides)
    return fire(HEADER_2022, **values)


def a_2005_fire(**overrides) -> list[object]:
    """A row from the oldest shape: no identifier, no coordinate, no deployment.

    The times are real ``datetime.time`` objects here, which is how 2000-2006 and
    2008-2010 store them; every other year writes ``HH:MM`` text.
    """
    values = {
        "Υπηρεσία": "Π.Κ. ΑΧΑΡΝΩΝ", "Δασαρχείο": "ΠΕΝΤΕΛΗΣ",
        "Περιοχή - Τοποθεσία": "ΚΡΥΟΝΕΡΙ", "Νομός": "ΑΤΤΙΚΗΣ",
        "Ημερ/νία Έναρξης": datetime.datetime(2005, 6, 8),
        "Ώρα Έναρξης": datetime.time(13, 30),
        "Ημερ/νία Κατασβεσης": datetime.datetime(2005, 6, 8),
        "Ώρα Κατάσβεσης": datetime.time(15, 0),
        "Δάση": 3, "Δασική Έκταση": 3, "Άλση": 0, "Χορτ/κές Εκτάσεις": 0,
        "Καλάμια - Βάλτοι": 0, "Γεωργικές Εκτάσεις": 0,
        "Υπολλείματα Καλλιεργειών": 0, "Σκουπιδότοποι": 0,
    }
    values.update(overrides)
    return fire(HEADER_2000, **values)


def a_2025_fire(**overrides) -> list[object]:
    """A row from the 2025 file: text dates, and an incident category."""
    values = {
        "Α/Α ΕΓΓΡΑΦΗΣ": 30000, "A/A ENGAGE": 1272497,
        "X-ENGAGE": 23.73308781150604, "Y-ENGAGE": 35.403909003469096,
        "Υπηρεσία": "Π.Κ. ΚΑΝΔΑΝΟΥ", "Νομός": "ΧΑΝΙΩΝ",
        "Ημερ/νία Έναρξης": "12/03/2025", "Ώρα Έναρξης": "11:23",
        "Ημερ/νία Κατασβεσης": "12/03/2025", "Ώρα Κατάσβεσης": "19:34",
        "Δασαρχείο": "ΧΑΝΙΩΝ Δ.Δ", "Δήμος": "ΠΛΑΤΑΝΙΑ", "Περιοχή": "ΒΟΥΚΟΛΙΩΝ",
        "Κατηγορία Συμβάντος": "ΜΙΚΡΗ", "Διεύθυνση": "  ΜΕΣΑΥΛΙΑ",
        "Δάση": 0, "Δασική Έκταση": 0, "Άλση": 0, "Χορτ/κές Εκτάσεις": 0.1,
        "Καλάμια - Βάλτοι": 0, "Γεωργικές Εκτάσεις": 0,
        "Υπολλείματα Καλλιεργειών": 0, "Σκουπιδότοποι": 0,
        "ΠΥΡΟΣ. ΣΩΜΑ": 11, "ΠΥΡΟΣ. ΟΧΗΜ.": 2, "ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ": 2,
        "ΑΛΛΩΝ ΦΟΡΕΩΝ": 0,
    }
    values.update(overrides)
    return fire(HEADER_2025, **values)


#: The rows the 2025 file writes above its banner: a title, then the year.
PREAMBLE_2025 = [["Δασικές πυρκαγιές"], ["Για το ΕΤΟΣ:", 2025]]
