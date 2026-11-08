#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture builders for the MeteoCat lightning import tests.

The extracts are written the way the delivery publishes them: ``;``-separated, the
header and the two text columns (``data``, ``idmunicipi``) quoted, everything else
bare. The rows reproduce what makes the delivery hard, one case each:

* a version-1 flash of three strokes **published out of order**, with the
  ``0`` sensor count and chi-squared of a network that did not record them;
* the same flash id used by **both networks** in September 2009 for two unrelated
  flashes;
* two version-2 strokes of one flash at **the same microsecond**, five kilometres
  apart (the 2014 case, moved to 2009);
* strokes on land (inside the test boundary) and at sea (outside it), one with a
  municipality code;
* in 2010, the first instant of the year and an intra-cloud stroke, which the
  delivery never has but the API will.

The test boundary is a rough outline of Catalonia's coast, so that "at sea" means
what it means in the real data.
"""

from __future__ import annotations

from pathlib import Path

from src.providers.catalonia_meteocat import COLUMNS

HEADER = ";".join(f'"{name}"' for name in COLUMNS)


def row(secidx: int, data: str, current: str, chi2: str, major: str, minor: str,
        sensors: str, ground: str = "t", municipality: str = "",
        longitude: str = "2", latitude: str = "41") -> str:
    """One published line."""
    return (f'{secidx};"{data}";{current};{chi2};{major};{minor};{sensors};{ground};'
            f'"{municipality}";{longitude};{latitude}')


#: The 2009 extract. File line numbers in the comments (the header is line 1).
ROWS_2009 = [
    # 2: version 1, a single stroke on land in Barcelona, with its municipality.
    row(905014, "2009-01-02 05:32:19.003386", "12.198", "0", "5250", "5250", "0",
        municipality="080193", longitude="2.17", latitude="41.39"),
    # 3-5: version 1, one flash of three strokes at sea, published 2nd, 1st, 3rd.
    row(910429, "2009-01-09 19:01:06.009261", "-1.532", "0", "550", "550", "0",
        longitude="2", latitude="41.0991"),
    row(910429, "2009-01-09 19:01:06.008626", "-2.241", "0", "550", "550", "0",
        longitude="2", latitude="41.0991"),
    row(910429, "2009-01-09 19:01:06.009294", "0.71", "0", "550", "550", "0",
        longitude="2", latitude="41.0991"),
    # 6: version 1, flash 1832764 on land...
    row(1832764, "2009-09-15 14:02:11.120000", "-15.2", "0", "2000", "2000", "0",
        longitude="1.5", latitude="41.6"),
    # 7-8: ...and version 2's own flash 1832764, unrelated, two strokes.
    row(1832764, "2009-09-15 14:02:11.500000", "-30.5", "1.2", "1800", "500", "3",
        longitude="1.51", latitude="41.61"),
    row(1832764, "2009-09-15 14:02:11.580000", "-18.1", "0.8", "1900", "600", "4",
        longitude="1.52", latitude="41.62"),
    # 9-10: version 2, two strokes of one flash at the same microsecond, at sea.
    row(2056000, "2009-10-02 08:29:25.737483", "22.4405", "1.5", "1500", "400", "2",
        longitude="2.1812854", latitude="40.942856"),
    row(2056000, "2009-10-02 08:29:25.737483", "-22.903", "4", "1800", "500", "2",
        longitude="2.132422", latitude="40.963436"),
    # 11: version 2, far out at sea, the last instant of the year.
    row(2056001, "2009-12-31 23:58:47.365022", "24.7715", "7", "47300", "2200", "2",
        longitude="5.853937", latitude="40.859905"),
]

#: The 2010 extract.
ROWS_2010 = [
    # 2: the first instant of the year, on land.
    row(814353, "2010-01-01 00:00:00.000022", "-10.5", "2.1", "3000", "800", "2",
        longitude="1.0", latitude="41.2"),
    # 3: an intra-cloud stroke, on land.
    row(814354, "2010-06-01 12:00:00.500000", "40.1", "0.5", "400", "200", "5",
        ground="f", longitude="1.1", latitude="41.3"),
]

#: A rough outline of Catalonia: the coast from the Ebre delta to Cap de Creus, then
#: inland. Points south-east of the coast line are at sea.
CATALONIA_WKT = ("MULTIPOLYGON(((0.2 40.5, 0.9 40.7, 2.0 41.25, 3.2 41.9, 3.3 42.5, "
                 "0.7 42.9, 0.2 41.5, 0.2 40.5)))")


def write_extract(path: Path, rows: list[str], header: str = HEADER) -> Path:
    """Write an extract as the delivery publishes it (LF line ends, no BOM)."""
    path.write_text("\n".join([header, *rows]) + "\n", encoding="ascii")
    return path


def extract_2009(directory: Path) -> Path:
    return write_extract(directory / "DATMET-12706_cg_cm_2009.csv", ROWS_2009)


def extract_2010(directory: Path) -> Path:
    return write_extract(directory / "DATMET-12706_cg_cm_2010.csv", ROWS_2010)
