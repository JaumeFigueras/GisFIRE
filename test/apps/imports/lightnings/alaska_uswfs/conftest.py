#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the Alaska (USWFS) lightning import tests.

The release is built the way the U.S. Wildland Fire Service ships it: a zip holding
the strokes file — UTF-8 with a byte-order mark, the release's header — and an
FGDC metadata file declaring the number of points. The strokes are the 42 real rows
of ``test/fixtures/data/alaska_uswfs/strokes_sample.txt`` (USWFS, Alaska Lightning
Detection Network, public domain; see its README), plus, where a test needs one, a
row made up with :func:`row` in the same format.
"""

from __future__ import annotations

import zipfile

from pathlib import Path

from src.providers import alaska_uswfs
from src.settings import ROOT_DIR

SAMPLE = ROOT_DIR / "test" / "fixtures" / "data" / "alaska_uswfs" / "strokes_sample.txt"

HEADER = ",".join(alaska_uswfs.FILE_COLUMNS)

#: The 42 real rows, as text, in file order.
REAL_ROWS = SAMPLE.read_text(encoding="utf-8-sig").splitlines()[1:]

#: The members, named as in the 2026 release.
DATA_MEMBER = "Historical_Lightning_2012_2026_TOA_WGS84.txt"
METADATA_MEMBER = "TOALightning_2012_2026_FGDC_metadata.xml"

#: What the 42 rows come to, per year, once the four strokes published twice are
#: dropped: strokes, then ground and cloud flashes.
SAMPLE_YEARS = {2012: (20, 19, 1), 2014: (3, 3, 0), 2019: (3, 3, 0), 2025: (9, 3, 2),
                2026: (3, 3, 0)}


def row(utc: str, milliseconds: int = 0, *, latitude: str = "64.8", longitude: str = "-147.7",
        amplitude: str = "-20000.000000000000000", cloud: bool = False, network: str = "0",
        gdop: str = "2", semi_major: str = "2", semi_minor: str = "1", angle: str = "10",
        sequence: str = "100", polarity: str | None = None) -> str:
    """One row in the release's format; ``utc`` as ``M/D/YYYY H:MM:SS``.

    The local time and ``STRIKETIME`` are filled with placeholders: the import
    reads neither.
    """
    if cloud:
        amplitude = "0.000000000000000"
    if polarity is None:
        polarity = ("Cloud To Cloud" if cloud
                    else "Negative" if amplitude.startswith("-") else "Positive")
    kind = "CLOUD_STROKE" if cloud else "GROUND_STROKE"
    return (f"{kind},{network},{utc},{utc},{milliseconds},{latitude},{longitude},{amplitude},"
            f"{gdop},{semi_major},{semi_minor},{angle},2000/01/01 00:00,{sequence},{polarity}")


def metadata(points: int) -> str:
    """A minimal FGDC metadata file declaring ``points``."""
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><metadata><spdoinfo><direct>Vector"
            "</direct><ptvctinf><sdtsterm><sdtstype>Entity point</sdtstype>"
            f"<ptvctcnt>{points}</ptvctcnt></sdtsterm></ptvctinf></spdoinfo></metadata>")


def strokes_text(rows: list[str], header: str = HEADER) -> bytes:
    """The strokes file: a byte-order mark, the header and the rows."""
    return ("﻿" + "\n".join([header, *rows]) + "\n").encode("utf-8")


def write_release(directory: Path, rows: list[str] | None = None, *, points: int | None | bool = True,
                  header: str = HEADER, name: str = "Historical_Lightning_2012_forward_as_txt.zip",
                  data_member: str = DATA_MEMBER) -> Path:
    """Write a release zip.

    ``points`` is the metadata's point count: ``True`` for the number of rows,
    ``False`` for no metadata file, or a number to disagree with them.
    """
    rows = REAL_ROWS if rows is None else rows
    path = directory / name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(data_member, strokes_text(rows, header))
        if points is not False:
            archive.writestr(METADATA_MEMBER, metadata(len(rows) if points is True else points))
    return path


def write_text(directory: Path, rows: list[str] | None = None) -> Path:
    """The strokes file alone, as extracted from the zip."""
    path = directory / DATA_MEMBER
    path.write_bytes(strokes_text(REAL_ROWS if rows is None else rows))
    return path
