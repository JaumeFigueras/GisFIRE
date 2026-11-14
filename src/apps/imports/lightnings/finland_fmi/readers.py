#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the monthly files of the FMI lightning downloader.

:mod:`src.apps.download.lightnings.finland_fmi.download_lightnings` writes one
``fmi_lightning_YYYY-MM.csv.gz`` per UTC month — a header
(:data:`~src.providers.finland_fmi.FILE_COLUMNS`), then one row per stroke with
every value as the service sent it — and a ``.meta.json`` sidecar beside it. This
module turns a file into checked, converted records; the import writes them.

What a row becomes
------------------

* ``unixtime`` → an aware UTC instant; it must fall inside the file's month.
* ``latitude``/``longitude`` → kept as degrees of ETRS89 for the published point.
* ``peak_current`` → kiloamperes, ``0`` → ``None`` (not recorded, 2005-2008).
* ``cloud_indicator`` → ``cloud_to_ground``: 0 is cloud-to-ground, 1 intra-cloud.
* ``ellipse_major``/``ellipse_minor`` → **metres**, from kilometres, rounded to
  0.1 m so that ``0.3`` km is ``300.0`` and not ``300.00000000000006``.
* ``multiplicity`` → ``published_multiplicity``, as published.
* every other field as published, as a number.

A row is refused — counted, its line and reason kept — when a value is not a
number, is ``NaN`` or infinite, or would break a CHECK of ``fmi_lightning``. No
row of the samples from 1998 to 2025 is.

An order of their own
---------------------

FMI publishes whole seconds, and strokes of the same second come in an order
that is not stable between requests: two downloads of one month hold the same
rows in a different order. :func:`read_month` therefore sorts the records by
their **values** (:func:`content_key`) and numbers them in that order
(``ordinal``). The import draws the stroke ids in that order, so a month
downloaded twice is imported with the same ids order, the same
``stroke_index`` and, because the thunderstorm algorithms break ties between
strokes of the same second by id, the same thunderstorms.
"""

from __future__ import annotations

import csv
import datetime
import gzip
import json
import math
import re

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from src.providers import finland_fmi

UTC = datetime.timezone.utc

#: A monthly file of the downloader, with its year and month.
FILE_NAME = re.compile(rf"{re.escape(finland_fmi.FILE_STEM)}_(\d{{4}})-(\d{{2}})\.csv\.gz")

#: The range of a PostgreSQL ``smallint``, for the indicators and the status.
SMALLINT = (-32768, 32767)


@dataclass(slots=True)
class StrokeRecord:
    """One published row, read and converted.

    ``ordinal`` is the record's position once the month is sorted by
    :func:`content_key`; ``line`` its line in the file, for messages.
    """

    line: int
    date_time: datetime.datetime
    latitude: float
    longitude: float
    flash_id: int
    published_multiplicity: int
    peak_current: float | None
    cloud_to_ground: bool
    number_of_sensors: int
    degrees_of_freedom: int
    ellipse_angle: float
    ellipse_major_axis: float
    ellipse_minor_axis: float
    chi_squared: float
    rise_time: float
    peak_to_zero_time: float
    angle_indicator: int
    signal_indicator: int
    timing_indicator: int
    stroke_status: int
    ordinal: int = 0


@dataclass
class MonthFile:
    """One monthly file, read.

    Attributes
    ----------
    path : pathlib.Path
        The file.
    year, month : int
        The UTC month, from the file name.
    records : list of StrokeRecord
        The rows that can be stored, in content order (see :func:`content_key`).
    problems : list of (int, str)
        The rows left out, as ``(line, reason)``.
    sidecar : dict or None
        The downloader's ``.meta.json``, or ``None`` if there is none.
    """

    path: Path
    year: int
    month: int
    records: list[StrokeRecord] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)
    sidecar: dict | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def label(self) -> str:
        """``YYYY-MM``."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def rows(self) -> int:
        """The data rows in the file, refused ones included."""
        return len(self.records) + len(self.problems)

    @property
    def start(self) -> datetime.datetime:
        return datetime.datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime.datetime:
        """The first instant of the next month: the month is ``[start, end)``."""
        if self.month == 12:
            return datetime.datetime(self.year + 1, 1, 1, tzinfo=UTC)
        return datetime.datetime(self.year, self.month + 1, 1, tzinfo=UTC)


class RowError(ValueError):
    """Why one row cannot be stored. The message names the column."""


def month_of(path: Path) -> tuple[int, int] | None:
    """The ``(year, month)`` a file name says, or ``None`` if it is not a monthly file."""
    match = FILE_NAME.fullmatch(path.name)
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return (year, month) if 1 <= month <= 12 else None


def sidecar_path(path: Path) -> Path:
    """The ``.meta.json`` beside a monthly file."""
    return path.with_name(path.name.removesuffix(".csv.gz") + ".meta.json")


def header_problem(path: Path) -> str | None:
    """Why ``path`` is not a monthly file, or ``None`` if its name and header say it is."""
    if month_of(path) is None:
        return f"not named {finland_fmi.FILE_STEM}_YYYY-MM.csv.gz"
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            header = handle.readline().strip()
    except (OSError, EOFError, UnicodeDecodeError) as error:
        return f"not a readable gzip file ({error})"
    if tuple(header.split(",")) != finland_fmi.FILE_COLUMNS:
        return "not a monthly file of the FMI downloader (unexpected header)"
    return None


def _number(value: str, column: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise RowError(f"{column} is not a number: {value!r}") from None
    if not math.isfinite(number):
        raise RowError(f"{column} is {value}")
    return number


def _integer(value: str, column: str, lowest: int | None = None,
             highest: int | None = None) -> int:
    number = _number(value, column)
    if number != int(number):
        raise RowError(f"{column} is not an integer: {value!r}")
    number = int(number)
    if lowest is not None and number < lowest:
        raise RowError(f"{column} is below {lowest}: {number}")
    if highest is not None and number > highest:
        raise RowError(f"{column} is above {highest}: {number}")
    return number


def _at_least_zero(value: str, column: str) -> float:
    number = _number(value, column)
    if number < 0:
        raise RowError(f"{column} is negative: {number}")
    return number


def parse_row(values: list[str], line: int, start: datetime.datetime,
              end: datetime.datetime) -> StrokeRecord:
    """Turn one row of the month ``[start, end)`` into a record.

    Raises
    ------
    RowError
        If the row cannot be stored, naming the column at fault.
    """
    if len(values) != len(finland_fmi.FILE_COLUMNS):
        raise RowError(f"{len(values)} columns instead of {len(finland_fmi.FILE_COLUMNS)}")
    row = dict(zip(finland_fmi.FILE_COLUMNS, values))

    seconds = _integer(row["unixtime"], "unixtime")
    date_time = datetime.datetime.fromtimestamp(seconds, UTC)
    if not start <= date_time < end:
        raise RowError(f"unixtime {seconds} ({date_time:%Y-%m-%dT%H:%M:%SZ}) is outside "
                       f"the file's month")
    latitude = _number(row["latitude"], "latitude")
    longitude = _number(row["longitude"], "longitude")
    if not -90 <= latitude <= 90:
        raise RowError(f"latitude out of range: {latitude}")
    if not -180 <= longitude <= 180:
        raise RowError(f"longitude out of range: {longitude}")

    peak_current = _number(row["peak_current"], "peak_current")
    cloud = _integer(row["cloud_indicator"], "cloud_indicator", 0, 1)
    angle = _number(row["ellipse_angle"], "ellipse_angle")
    if not 0 <= angle <= 180:
        raise RowError(f"ellipse_angle is outside 0-180: {angle}")
    major = _at_least_zero(row["ellipse_major"], "ellipse_major")
    minor = _at_least_zero(row["ellipse_minor"], "ellipse_minor")
    if minor > major:
        raise RowError(f"ellipse_minor {minor} is larger than ellipse_major {major}")

    return StrokeRecord(
        line=line,
        date_time=date_time,
        latitude=latitude,
        longitude=longitude,
        flash_id=_integer(row["flash_id"], "flash_id", 0),
        published_multiplicity=_integer(row["multiplicity"], "multiplicity", 0),
        peak_current=None if peak_current == 0 else peak_current,
        cloud_to_ground=cloud == 0,
        number_of_sensors=_integer(row["sensors"], "sensors", 1),
        degrees_of_freedom=_integer(row["freedom_degree"], "freedom_degree", 0),
        ellipse_angle=angle,
        ellipse_major_axis=round(major * finland_fmi.ELLIPSE_AXIS_FACTOR, 1),
        ellipse_minor_axis=round(minor * finland_fmi.ELLIPSE_AXIS_FACTOR, 1),
        chi_squared=_at_least_zero(row["chi_square"], "chi_square"),
        rise_time=_at_least_zero(row["rise_time"], "rise_time"),
        peak_to_zero_time=_at_least_zero(row["ptz_time"], "ptz_time"),
        angle_indicator=_integer(row["angle_indicator"], "angle_indicator", *SMALLINT),
        signal_indicator=_integer(row["signal_indicator"], "signal_indicator", *SMALLINT),
        timing_indicator=_integer(row["timing_indicator"], "timing_indicator", *SMALLINT),
        stroke_status=_integer(row["stroke_status"], "stroke_status", *SMALLINT),
    )


def content_key(record: StrokeRecord) -> tuple:
    """The order of a month's strokes, from their values alone.

    By instant, then flash, then the flash's first stroke first, then every other
    value. Two records with the same key are the same values, so which of them
    comes first changes nothing that is stored.
    """
    return (record.date_time, record.flash_id, record.published_multiplicity == 0,
            record.latitude, record.longitude,
            record.peak_current if record.peak_current is not None else 0.0,
            record.cloud_to_ground, record.number_of_sensors, record.degrees_of_freedom,
            record.ellipse_angle, record.ellipse_major_axis, record.ellipse_minor_axis,
            record.chi_squared, record.rise_time, record.peak_to_zero_time,
            record.angle_indicator, record.signal_indicator, record.timing_indicator,
            record.stroke_status)


def read_sidecar(path: Path) -> dict | None:
    """The downloader's sidecar of a monthly file, or ``None`` if there is none.

    Raises
    ------
    RuntimeError
        If the sidecar exists but is not JSON.
    """
    meta = sidecar_path(path)
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"{meta.name} is not readable JSON ({error})") from None


def read_month(path: Path) -> MonthFile:
    """Read one monthly file and its sidecar, records in content order.

    Raises
    ------
    RuntimeError
        If the file is not a monthly file of the downloader (see
        :func:`header_problem`), or its sidecar is not JSON — nothing of it is
        read then.
    """
    problem = header_problem(path)
    if problem is not None:
        raise RuntimeError(problem)
    year, month = month_of(path)
    content = MonthFile(path=path, year=year, month=month, sidecar=read_sidecar(path))

    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        for line, values in enumerate(reader, start=2):
            if not values:
                continue
            try:
                content.records.append(parse_row(values, line, content.start, content.end))
            except RowError as error:
                content.problems.append((line, str(error)))

    content.records.sort(key=content_key)
    for ordinal, record in enumerate(content.records, start=1):
        record.ordinal = ordinal
    return content
