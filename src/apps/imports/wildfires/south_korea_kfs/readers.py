#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read a Korea Forest Service wildfire statistics release into records.

A release is one CSV (see :mod:`src.providers.south_korea_kfs`): CP949, a header
of the 18 names in :data:`~src.providers.south_korea_kfs.COLUMNS`, one row per
fire. This module decodes it, checks the header and turns each row into a
:class:`FireRecord` holding what was published, parsed but not yet classified:
the cause lookup and the romanization are the import's job, so a record still
says what the file said.

What can go wrong in a row is collected on :attr:`FireRecord.problems` rather
than raised, so that the import can report every bad row of a release and not
only the first.
"""

from __future__ import annotations

import csv
import datetime
import re

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from src.providers import south_korea_kfs

_TIME = re.compile(r"(\d{1,2}):(\d{2})")


@dataclass
class FireRecord:
    """One published row.

    ``start`` and ``end`` are naive local wall-clock readings; the zone is applied
    by the import. ``start`` is ``None`` only for a row that cannot be stored.
    ``end`` is the published end even when it is wrong; ``end_date_problem`` says
    whether it is.
    """

    row: int
    year: int | None
    start: datetime.datetime | None
    end: datetime.datetime | None
    end_date_problem: str | None
    office: str | None
    province: str | None
    municipality: str | None
    township: str | None
    village: str | None
    cause_category_code: str | None
    cause_detail: str | None
    cause_text: str | None
    area_ha: float | None
    problems: list[str] = field(default_factory=list)


@dataclass
class Release:
    """A decoded release: its name, encoding and records."""

    name: str
    encoding: str
    records: list[FireRecord]


def decode(raw: bytes) -> tuple[str, str]:
    """Decode a release in the first of :data:`~src.providers.south_korea_kfs.ENCODINGS` that fits.

    Returns
    -------
    tuple of str
        The text and the encoding it was read in.
    """
    for encoding in south_korea_kfs.ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise RuntimeError(
        f"not decodable as any of {', '.join(south_korea_kfs.ENCODINGS)}"
    )


def check_header(header: list[str]) -> None:
    """Refuse a file whose header is not the published one.

    Compared after trimming, in order. A different header is a different format —
    or a different file — and reading it by position would put values in the wrong
    columns, so it is an error rather than a warning.
    """
    found = tuple(name.strip() for name in header)
    if not set(found) & set(south_korea_kfs.COLUMNS):
        raise RuntimeError("not a KFS wildfire statistics file: no column of its "
                           "header is one of the published ones")
    if found != south_korea_kfs.COLUMNS:
        missing = [name for name in south_korea_kfs.COLUMNS if name not in found]
        unknown = [name for name in found if name not in south_korea_kfs.COLUMNS]
        raise RuntimeError(
            "not a KFS wildfire statistics header"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(unknown)}" if unknown else "")
            + ("; same columns in another order" if not missing and not unknown else "")
        )


def parse_datetime(year: str, month: str, day: str,
                   time: str) -> datetime.datetime | None:
    """A published date and ``HH:MM`` as a naive datetime, or ``None`` if not one."""
    match = _TIME.fullmatch(time.strip())
    if match is None:
        return None
    try:
        return datetime.datetime(int(year), int(month), int(day),
                                 int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def parse_area(value: str) -> float | None:
    """The published area in hectares, or ``None`` if blank, not a number or negative."""
    try:
        area = float(value.strip())
    except ValueError:
        return None
    return area if area >= 0 else None


def read_row(row: int, values: dict[str, str]) -> FireRecord:
    """Turn one published row into a record, collecting what is wrong with it."""
    problems: list[str] = []
    start = parse_datetime(values["발생일시_년"], values["발생일시_월"],
                           values["발생일시_일"], values["발생일시_시간"])
    if start is None:
        problems.append("no valid start date and time")
    end = parse_datetime(values["진화종료시간_년"], values["진화종료시간_월"],
                         values["진화종료시간_일"], values["진화종료시간_시간"])
    end_problem = None if start is None else south_korea_kfs.end_date_problem(start, end)
    if end_problem is not None:
        problems.append(f"end {end_problem}")

    weekday = values["발생일시_요일"].strip()
    if start is not None and south_korea_kfs.WEEKDAYS.get(weekday) != start.isoweekday():
        problems.append(f"weekday {weekday!r} does not match the start date")

    area = parse_area(values["피해면적_합계"])
    if area is None:
        problems.append(f"no valid area: {values['피해면적_합계']!r}")

    clean = south_korea_kfs.clean
    record = FireRecord(
        row=row,
        year=start.year if start is not None else None,
        start=start,
        end=end,
        end_date_problem=end_problem,
        office=clean(values["발생장소_관서"]),
        province=clean(values["발생장소_시도"]),
        municipality=clean(values["발생장소_시군구"]),
        township=clean(values["발생장소_읍면"]),
        village=clean(values["발생장소_동리"]),
        cause_category_code=clean(values["발생원인_구분"]),
        cause_detail=clean(values["발생원인_세부원인"]),
        cause_text=clean(values["발생원인_기타"]),
        area_ha=area,
        problems=problems,
    )
    for name, value in (("office", record.office), ("province", record.province),
                        ("detailed cause", record.cause_detail),
                        ("cause text", record.cause_text)):
        if value is None:
            problems.append(f"no {name}")
    return record


def read_release(path: Path) -> Release:
    """Read a release file.

    Raises
    ------
    RuntimeError
        If it cannot be decoded, has no header, or its header is not the
        published one.
    """
    text, encoding = decode(path.read_bytes())
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        raise RuntimeError(f"{path.name} is empty") from None
    check_header(header)

    records = []
    # The header is line 1, so the first fire is on line 2.
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) != len(south_korea_kfs.COLUMNS):
            raise RuntimeError(
                f"{path.name}, line {line}: {len(cells)} fields, expected "
                f"{len(south_korea_kfs.COLUMNS)}"
            )
        records.append(read_row(line, dict(zip(south_korea_kfs.COLUMNS, cells))))
    return Release(name=path.name, encoding=encoding, records=records)
