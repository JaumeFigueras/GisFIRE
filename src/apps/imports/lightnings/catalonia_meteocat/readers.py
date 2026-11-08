#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read a MeteoCat XDDE CSV extract into stroke records.

An extract is one CSV (see :mod:`src.providers.catalonia_meteocat`): ASCII,
``;``-separated, the header of :data:`~src.providers.catalonia_meteocat.COLUMNS`,
one row per stroke. This module checks the header, turns each row into a
:class:`StrokeRecord` and numbers the strokes of every flash.

A record is what was published, with two readings applied that the database
needs and the file does not say: the instant is made timezone-aware in UTC, and a
version-1 ``0`` sensor count and chi-squared — "not recorded" — become ``None``.

A row that cannot be stored is not raised: it is left out of
:attr:`Extract.records` and listed in :attr:`Extract.problems` with its line and
the reason, so that the import can report every bad row of a file and still store
the rest. "Cannot be stored" means a ``NOT NULL`` or ``CHECK`` of
``meteocat_lightning`` would refuse it, or it is not a reading of the format at
all. No row of the 2006-2020 delivery is one.
"""

from __future__ import annotations

import csv
import datetime
import re

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from src.providers import catalonia_meteocat

UTC = datetime.timezone.utc

#: A municipality code as published: the six-digit INE code.
_MUNICIPALITY = re.compile(r"\d{6}")

#: What ``nuvolterra`` holds, and what it means for ``cloud_to_ground``.
_GROUND = {"t": True, "f": False}


@dataclass(slots=True)
class StrokeRecord:
    """One published row, read.

    ``chi_squared`` and ``number_of_sensors`` are ``None`` for a version-1 stroke.
    ``multiplicity`` and ``stroke_index`` are ``None`` until
    :func:`number_flashes` has run, which :func:`read_extract` does.
    """

    row: int
    flash_id: int
    date_time: datetime.datetime
    peak_current: float
    chi_squared: float | None
    ellipse_major_axis: float
    ellipse_minor_axis: float
    number_of_sensors: int | None
    cloud_to_ground: bool
    municipality_code: str | None
    longitude: float
    latitude: float
    network_version: int
    multiplicity: int | None = None
    stroke_index: int | None = None


@dataclass
class Extract:
    """One file, read.

    ``problems`` lists the rows left out, as ``(line, reason)``.
    """

    path: Path
    records: list[StrokeRecord] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


class RowError(ValueError):
    """Why one row cannot be stored. The message names the column."""


def _number(value: str, column: str, kind: type = float):
    try:
        return kind(value)
    except ValueError:
        raise RowError(f"{column} is not a number: {value!r}") from None


def _instant(value: str) -> datetime.datetime:
    """The published ``data``, a naive UTC reading, as an aware instant."""
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise RowError(f"data is not a date and time: {value!r}") from None
    if moment.tzinfo is not None:
        raise RowError(f"data carries a zone, the format does not: {value!r}")
    return moment.replace(tzinfo=UTC)


def parse_row(values: list[str], line: int) -> StrokeRecord:
    """Turn one published row into a record.

    Raises
    ------
    RowError
        If the row cannot be stored, naming the column at fault.
    """
    if len(values) != len(catalonia_meteocat.COLUMNS):
        raise RowError(f"{len(values)} columns instead of {len(catalonia_meteocat.COLUMNS)}")
    (secidx, data, current, chi2, major, minor, sensors,
     ground, municipality, longitude, latitude) = values

    flash_id = _number(secidx, "secidx", int)
    date_time = _instant(data)
    peak_current = _number(current, "correntpic")
    chi_squared = _number(chi2, "chi2")
    major_axis = _number(major, "eixmajor")
    minor_axis = _number(minor, "eixmenor")
    number_of_sensors = _number(sensors, "numsensors", int)
    x = _number(longitude, "longitud")
    y = _number(latitude, "latitud")

    if number_of_sensors < 0:
        raise RowError(f"numsensors is negative: {number_of_sensors}")
    version = catalonia_meteocat.network_version(number_of_sensors)
    if version == 1:
        # The first generation published 0 for both; a chi-squared beside a
        # sensor count of 0 is not a reading of either generation.
        if chi_squared != 0:
            raise RowError(f"chi2 is {chi_squared} on a stroke with no sensor count")
        chi_squared = None
        number_of_sensors = None
    elif chi_squared < 0:
        raise RowError(f"chi2 is negative: {chi_squared}")

    if minor_axis < 0 or minor_axis > major_axis:
        raise RowError(f"eixmenor {minor_axis} is negative or larger than eixmajor {major_axis}")
    if ground not in _GROUND:
        raise RowError(f"nuvolterra is neither 't' nor 'f': {ground!r}")
    if municipality and not _MUNICIPALITY.fullmatch(municipality):
        raise RowError(f"idmunicipi is not a six-digit code: {municipality!r}")
    if not -180 <= x <= 180:
        raise RowError(f"longitud out of range: {x}")
    if not -90 <= y <= 90:
        raise RowError(f"latitud out of range: {y}")

    return StrokeRecord(
        row=line, flash_id=flash_id, date_time=date_time, peak_current=peak_current,
        chi_squared=chi_squared, ellipse_major_axis=major_axis,
        ellipse_minor_axis=minor_axis, number_of_sensors=number_of_sensors,
        cloud_to_ground=_GROUND[ground], municipality_code=municipality or None,
        longitude=x, latitude=y, network_version=version,
    )


def number_flashes(records: list[StrokeRecord]) -> None:
    """Set ``multiplicity`` and ``stroke_index`` on every record, in place.

    A flash is ``(network_version, flash_id)``: the two generations number their
    flashes independently. Its strokes are ordered by instant, and strokes at the
    same instant by their line in the file, which is the only order left.
    """
    flashes: dict[tuple[int, int], list[StrokeRecord]] = defaultdict(list)
    for record in records:
        flashes[(record.network_version, record.flash_id)].append(record)
    for strokes in flashes.values():
        strokes.sort(key=lambda record: (record.date_time, record.row))
        for index, record in enumerate(strokes, start=1):
            record.multiplicity = len(strokes)
            record.stroke_index = index


def read_extract(path: Path) -> Extract:
    """Read one extract, numbering its flashes.

    Raises
    ------
    RuntimeError
        If the file is empty or its header is not the extract header — it is then
        not an extract, and nothing of it is read.
    """
    extract = Extract(path)
    with path.open(newline="", encoding="ascii", errors="replace") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader, None)
        if header is None:
            raise RuntimeError("empty file, not an XDDE extract")
        if tuple(name.strip() for name in header) != catalonia_meteocat.COLUMNS:
            raise RuntimeError(f"header {';'.join(header)!r} is not the XDDE extract header")
        for line, values in enumerate(reader, start=2):
            if not values:
                continue
            try:
                extract.records.append(parse_row(values, line))
            except RowError as error:
                extract.problems.append((line, str(error)))
    number_flashes(extract.records)
    return extract


def by_year(records: list[StrokeRecord]) -> dict[int, list[StrokeRecord]]:
    """The records grouped by UTC year, years in order, records in file order."""
    years: dict[int, list[StrokeRecord]] = defaultdict(list)
    for record in records:
        years[record.date_time.year].append(record)
    return dict(sorted(years.items()))
