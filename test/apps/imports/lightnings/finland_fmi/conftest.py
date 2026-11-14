#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the FMI lightning import tests.

The monthly files are written the way the downloader writes them — a gzip CSV
with :data:`~src.providers.finland_fmi.FILE_COLUMNS` as header, every value the
text the service sent, and a ``.meta.json`` sidecar. July 2023 starts from the 17
real strokes of 2023-07-01 12:00-12:01 UTC, turned into rows by the downloader's
own parser from the saved response, so these tests also check that the importer
reads what the downloader writes. Source: Finnish Meteorological Institute (FMI),
open data, CC BY 4.0.

Then one row per case the import has to get right:

* a flash **straddling June and July**: its first stroke at 23:59:59 on 30 June
  (in the June file), its second at midnight (in the July file);
* a stroke from the years when the peak current was **not recorded** (published
  ``0``), with the old ``stroke_status`` and indicators of ``0``;
* a **lone subsequent stroke**: published multiplicity ``0``, its first stroke
  dropped by FMI's filter;
* two strokes of one flash at the **same second and position**, differing only in
  their peak current — FMI publishes them in no stable order;
* a first stroke **announcing two strokes** of which only one was published.

The test boundary is a rough box over Finland, so that some real strokes fall in
it and others — in Sweden, in Russia — do not.
"""

from __future__ import annotations

import datetime
import gzip
import json

from pathlib import Path

from src.apps.download.lightnings.finland_fmi import download_lightnings as downloader
from src.providers import finland_fmi
from src.settings import ROOT_DIR

UTC = datetime.timezone.utc

HEADER = ",".join(finland_fmi.FILE_COLUMNS)

_STROKES_XML = ROOT_DIR / "test" / "fixtures" / "data" / "fmi_wfs" / "strokes_2023-07-01T1200_1201.xml"

#: The 17 real strokes of 2023-07-01 12:00-12:01, as the downloader writes them.
REAL_ROWS = downloader.parse_response(
    _STROKES_XML.read_bytes(),
    datetime.datetime(2023, 7, 1, 12, 0, tzinfo=UTC),
    datetime.datetime(2023, 7, 1, 12, 1, tzinfo=UTC)).rows


def row(unixtime: int, flash_id: int, multiplicity: int, peak: str, *, latitude: str = "61.5",
        longitude: str = "25.5", cloud: str = "0", sensors: str = "4", dof: str = "5",
        angle: str = "45.0", major: str = "0.3", minor: str = "0.1", chi: str = "0.5",
        rise: str = "5.0", ptz: str = "20.0", indicators: str = "1,0,1",
        status: str = "17") -> str:
    """One row as the downloader writes it."""
    return (f"{unixtime},{latitude},{longitude},{flash_id},{multiplicity},{peak},{cloud},"
            f"{sensors},{dof},{angle},{major},{minor},{chi},{rise},{ptz},{indicators},{status}")


#: 2023-06-30 23:59:59 and 2023-07-01 00:00:00 UTC.
LAST_SECOND_OF_JUNE = 1688169599
MIDNIGHT = 1688169600
#: 2023-07-15 15:30:00 UTC.
MID_JULY = 1689435000

#: The straddling flash's first stroke, in the June file.
STRADDLING_FIRST = row(LAST_SECOND_OF_JUNE, 30600000, 2, "-21", latitude="62.1", longitude="25.7")
#: ...and its second stroke, in the July file.
STRADDLING_SECOND = row(MIDNIGHT, 30600000, 0, "-14", latitude="62.11", longitude="25.71")

#: The July 2023 file: the real strokes, then one row per case.
ROWS_2023_07 = [
    *REAL_ROWS,
    STRADDLING_SECOND,
    # Peak current not recorded, an old status and indicators of 0.
    row(MID_JULY, 30700000, 1, "0", indicators="0,0,0", status="0"),
    # A lone subsequent stroke.
    row(MID_JULY + 60, 30700001, 0, "-9", latitude="61.6"),
    # Same flash, same second, same position, two currents; published second first.
    row(MID_JULY + 120, 30700002, 0, "-11"),
    row(MID_JULY + 120, 30700002, 2, "-35"),
    # A first stroke announcing two strokes, one published.
    row(MID_JULY + 180, 30700003, 2, "-40", latitude="61.7"),
]

#: The June 2023 file: an ordinary stroke and the straddling flash's first stroke.
ROWS_2023_06 = [
    row(1686391200, 30500000, 1, "-12"),
    STRADDLING_FIRST,
]

#: The July 2022 file, for the year filter: one stroke.
ROWS_2022_07 = [row(1657899000, 28000000, 1, "-18")]

#: A rough box over Finland, (lon lat). Of the real strokes, those in Finland fall
#: inside; those in Sweden (13-14 E) and in Russia (59.7 N) do not.
FINLAND_WKT = "MULTIPOLYGON(((20 59.8, 31.5 59.8, 31.5 70, 20 70, 20 59.8)))"


def write_month(directory: Path, year: int, month: int, rows: list[str], *,
                sidecar: bool | dict = True, complete: bool = True,
                header: str = HEADER) -> Path:
    """Write a monthly file and, unless told not to, its sidecar.

    ``sidecar`` may be a dict, written as the sidecar instead of the usual one.
    """
    path = directory / f"{finland_fmi.FILE_STEM}_{year:04d}-{month:02d}.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("\n".join([header, *rows]) + "\n")
    if sidecar is not False:
        meta = sidecar if isinstance(sidecar, dict) else {
            "month": f"{year:04d}-{month:02d}", "complete": complete, "strokes": len(rows)}
        (directory / f"{finland_fmi.FILE_STEM}_{year:04d}-{month:02d}.meta.json").write_text(
            json.dumps(meta), encoding="utf-8")
    return path


def july_2023(directory: Path, **options) -> Path:
    return write_month(directory, 2023, 7, ROWS_2023_07, **options)


def june_2023(directory: Path, **options) -> Path:
    return write_month(directory, 2023, 6, ROWS_2023_06, **options)


def july_2022(directory: Path, **options) -> Path:
    return write_month(directory, 2022, 7, ROWS_2022_07, **options)
