#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the Alaska Lightning Detection Network's yearly release.

The U.S. Wildland Fire Service releases the network's strokes once a year, as one
cumulative zip (see :mod:`src.providers.alaska_uswfs`): a CSV of every stroke since
2012 and its FGDC metadata. This module checks the release, streams it a UTC year
at a time and turns each year into converted records grouped into flashes; the
import writes them.

The release is checked before anything is read
-----------------------------------------------

:func:`scan` reads the whole file once, cheaply, before the import writes
anything: the header must be :data:`~src.providers.alaska_uswfs.FILE_COLUMNS`; when
the zip holds the FGDC metadata, the number of rows must be its point count
(``ptvctcnt``) — a release that disagrees is incomplete or altered and is refused
whole; and each year's rows must be together, which lets :func:`read_years` hold
one year in memory at a time (the file is sorted by UTC second). The extracted
``.txt`` alone can be read too, with nothing to check its count against.

What a row becomes
------------------

* ``UTCDATETIME`` + ``MILLISECONDS`` → an aware UTC instant, to the millisecond
  (``MILLISECONDS`` is the fraction of the second, whatever the metadata says).
* ``LATITUDE``/``LONGITUDE`` → degrees of WGS 84, as published.
* ``AMPLITUDE`` → kiloamperes; ``None`` on a cloud stroke, whose amplitude of 0 is
  what makes it one.
* ``STROKETYPE`` → ``cloud_to_ground``.
* ``ERRSEMIMAJOR``/``ERRSEMIMINOR`` → **metres**, from kilometres, rounded to
  0.1 m; a semi-major axis of 0 → ``None`` (no ellipse has one beside a semi-minor
  of 1 km).
* ``NETWORKCODE``, ``GDOP``, ``ERRELIPSEANGLE``, ``STRIKESEQNUMBER`` (empty →
  ``None``) as published.
* ``LOCALDATETIME``, ``STRIKETIME`` and ``POLARITY`` are not kept; a polarity
  that contradicts the amplitude's sign is counted.

A row is refused — counted, its line and reason kept — when a value is not a
number or not a date, a stroke type is unknown, a ground stroke has no amplitude
or a cloud stroke has one, or a value would break a CHECK of
``alaska_uswfs_lightning``. No row of the 2012-2026 release is.

An order of their own, and the flashes
--------------------------------------

Within a millisecond the file's order is arbitrary (40,740 strokes share theirs
with another), so :func:`prepare_year` sorts a year's records by their **values**
(:func:`content_key`) and numbers them (``ordinal``); the import draws the stroke
ids in that order, so the same release imported twice gives the same ids order —
which the thunderstorm algorithms use to break ties. Records identical in every
published value but the sequence number are the same stroke published twice and
only the first is kept (24 in 2012).

Then the strokes are grouped into flashes, which the network does not publish,
with :func:`~gisfire_algorithms.thunderstorm.flash_grouping.group_strokes` and the
provider's limits, on EPSG:3338 metres, ground and cloud strokes apart; each record
gets the ordinal of its flash's first stroke, the flash's multiplicity and its own
place in it. A flash is grouped within its UTC year: a stroke within a flash's
duration of New Year is counted, since a flash could be cut there (none in
2012-2026).
"""

from __future__ import annotations

import csv
import datetime
import io
import math
import re
import zipfile

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path

import numpy as np

from gisfire_algorithms.thunderstorm import FlashGroupingParameters
from gisfire_algorithms.thunderstorm import group_strokes
from src.providers import alaska_uswfs

UTC = datetime.timezone.utc

#: The strokes in the zip: ``Historical_Lightning_2012_2026_TOA_WGS84.txt`` in 2026.
DATA_MEMBER = re.compile(r"(?:.*/)?[^/]*_TOA_WGS84\.txt")

#: The FGDC metadata in the zip: ``TOALightning_2012_2026_FGDC_metadata.xml`` in 2026.
METADATA_MEMBER = re.compile(r"(?:.*/)?[^/]*_FGDC_metadata\.xml")

#: The number of points the metadata declares.
POINT_COUNT = re.compile(rb"<ptvctcnt>\s*(\d+)\s*</ptvctcnt>")

#: The published stroke types, and whether each reached the ground.
STROKE_TYPES = {"GROUND_STROKE": True, "CLOUD_STROKE": False}

#: The ``POLARITY`` the sign of the amplitude implies.
POLARITIES = {-1: "Negative", 0: "Cloud To Cloud", 1: "Positive"}

#: The range of a PostgreSQL ``smallint`` and ``integer``.
SMALLINT = (-32768, 32767)
INTEGER = (-2147483648, 2147483647)

#: The kinds of stroke grouped apart.
GROUND, CLOUD = 0, 1

#: The provider's flash rule.
FLASH_RULE = FlashGroupingParameters(max_duration_s=alaska_uswfs.FLASH_MAX_DURATION_S,
                                     max_interval_s=alaska_uswfs.FLASH_MAX_INTERVAL_S,
                                     max_distance_km=alaska_uswfs.FLASH_MAX_DISTANCE_KM)


@dataclass(slots=True)
class StrokeRecord:
    """One published row, read and converted.

    ``line`` is its line in the file, for messages. ``ordinal`` is its position
    once its year is in content order; ``first_ordinal``, ``multiplicity`` and
    ``stroke_index`` its flash, set by :func:`prepare_year`.
    """

    line: int
    date_time: datetime.datetime
    latitude: float
    longitude: float
    peak_current: float | None
    cloud_to_ground: bool
    network_code: int
    sequence_number: int | None
    gdop: int
    ellipse_semi_major_axis: float | None
    ellipse_semi_minor_axis: float
    ellipse_angle: float
    polarity_contradicted: bool = False
    ordinal: int = 0
    first_ordinal: int = 0
    multiplicity: int = 0
    stroke_index: int = 0


@dataclass
class Release:
    """A release, scanned.

    Attributes
    ----------
    path : pathlib.Path
        The zip, or the extracted ``.txt``.
    member : str or None
        The strokes' member of the zip; ``None`` for a ``.txt``.
    point_count : int or None
        The metadata's point count, or ``None`` with no metadata to read.
    rows : int
        The data rows in the file.
    years : dict of int to int
        The rows of each UTC year, in file order.
    """

    path: Path
    member: str | None
    point_count: int | None
    rows: int = 0
    years: dict[int, int] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path.name if self.member is None else f"{self.path.name}:{self.member}"


@dataclass
class ReleaseYear:
    """One UTC year of a release, read.

    Attributes
    ----------
    year : int
        The year.
    records : list of StrokeRecord
        The rows that can be stored; after :func:`prepare_year`, in content order,
        without duplicates and grouped into flashes.
    problems : list of (int, str)
        The rows left out, as ``(line, reason)``.
    duplicates : int
        The strokes published twice, dropped by :func:`prepare_year`.
    flashes : int
        The flashes, ground and cloud, after :func:`prepare_year`.
    cloud_flashes : int
        Of those, the cloud ones.
    near_new_year : int
        Strokes within a flash's duration of the year's start or end.
    """

    year: int
    records: list[StrokeRecord] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)
    duplicates: int = 0
    flashes: int = 0
    cloud_flashes: int = 0
    near_new_year: int = 0

    @property
    def start(self) -> datetime.datetime:
        return datetime.datetime(self.year, 1, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime.datetime:
        """The first instant of the next year: the year is ``[start, end)``."""
        return datetime.datetime(self.year + 1, 1, 1, tzinfo=UTC)

    @property
    def unknown_semi_major(self) -> int:
        """Strokes whose semi-major axis was published as 0."""
        return sum(record.ellipse_semi_major_axis is None for record in self.records)

    @property
    def polarity_contradictions(self) -> int:
        return sum(record.polarity_contradicted for record in self.records)


class RowError(ValueError):
    """Why one row cannot be stored. The message names the column."""


# --------------------------------------------------------------------------
# Opening and scanning a release
# --------------------------------------------------------------------------

def _members(path: Path) -> tuple[str | None, str | None]:
    """The strokes' and the metadata's members of a zip.

    Raises
    ------
    RuntimeError
        If the zip holds no strokes file, or more than one.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    data = [name for name in names if DATA_MEMBER.fullmatch(name)]
    metadata = [name for name in names if METADATA_MEMBER.fullmatch(name)]
    if len(data) != 1:
        raise RuntimeError(f"{path.name} holds {len(data)} file(s) named *_TOA_WGS84.txt "
                           f"instead of one")
    return data[0], metadata[0] if len(metadata) == 1 else None


@contextmanager
def open_strokes(path: Path, member: str | None) -> Iterator[io.TextIOBase]:
    """The strokes file as text, the byte-order mark dropped."""
    if member is None:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            yield handle
    else:
        with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
            yield io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")


def _year_of(values: list[str]) -> int | None:
    """The year of a row's ``UTCDATETIME`` (``M/D/YYYY H:MM:SS``), or ``None``."""
    if len(values) < 3:
        return None
    try:
        return int(values[2].split(" ", 1)[0].rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None


def scan(path: Path) -> Release:
    """Check a release, the zip or its ``.txt``, without converting a row.

    Raises
    ------
    RuntimeError
        If it is neither a zip holding the strokes nor a readable text file; its
        header is not the release's; its rows disagree with the metadata's point
        count; or a year's rows are not together.
    """
    if zipfile.is_zipfile(path):
        member, metadata = _members(path)
        point_count = None
        if metadata is not None:
            with zipfile.ZipFile(path) as archive:
                match = POINT_COUNT.search(archive.read(metadata))
            point_count = int(match.group(1)) if match else None
    else:
        member, point_count = None, None
    release = Release(path=path, member=member, point_count=point_count)

    try:
        with open_strokes(path, member) as handle:
            reader = csv.reader(handle)
            header = tuple(next(reader, ()))
            if header != alaska_uswfs.FILE_COLUMNS:
                raise RuntimeError(f"{release.name} is not a release of the Alaska network's "
                                   f"strokes (unexpected header)")
            current = None
            for line, values in enumerate(reader, start=2):
                if not values:
                    continue
                release.rows += 1
                year = _year_of(values)
                if year is None or year == current:
                    if year is not None:
                        release.years[year] += 1
                    continue
                if year in release.years:
                    raise RuntimeError(f"{release.name}: the rows of {year} are not together "
                                       f"(line {line} goes back to it after {current})")
                release.years[year] = 1
                current = year
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, csv.Error) as error:
        raise RuntimeError(f"{release.name} is not readable ({error})") from None

    if point_count is not None and point_count != release.rows:
        raise RuntimeError(f"{release.name} holds {release.rows} row(s) and its metadata "
                           f"declares {point_count} point(s): the release is incomplete or "
                           f"altered; download it again")
    return release


# --------------------------------------------------------------------------
# A row
# --------------------------------------------------------------------------

def _number(value: str, column: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise RowError(f"{column} is not a number: {value!r}") from None
    if not math.isfinite(number):
        raise RowError(f"{column} is {value}")
    return number


def _integer(value: str, column: str, lowest: int, highest: int) -> int:
    number = _number(value, column)
    if number != int(number):
        raise RowError(f"{column} is not an integer: {value!r}")
    number = int(number)
    if number < lowest:
        raise RowError(f"{column} is below {lowest}: {number}")
    if number > highest:
        raise RowError(f"{column} is above {highest}: {number}")
    return number


def _instant(value: str, milliseconds: int) -> datetime.datetime:
    """``M/D/YYYY H:MM:SS`` plus milliseconds, in UTC."""
    try:
        date, time = value.split(" ")
        month, day, year = date.split("/")
        hour, minute, second = time.split(":")
        return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute),
                                 int(second), milliseconds * 1000, tzinfo=UTC)
    except ValueError:
        raise RowError(f"UTCDATETIME is not a date: {value!r}") from None


def parse_row(values: list[str], line: int) -> StrokeRecord:
    """Turn one row into a record.

    Raises
    ------
    RowError
        If the row cannot be stored, naming the column at fault.
    """
    if len(values) != len(alaska_uswfs.FILE_COLUMNS):
        raise RowError(f"{len(values)} columns instead of {len(alaska_uswfs.FILE_COLUMNS)}")
    row = dict(zip(alaska_uswfs.FILE_COLUMNS, values))

    if row["STROKETYPE"] not in STROKE_TYPES:
        raise RowError(f"STROKETYPE is unknown: {row['STROKETYPE']!r}")
    ground = STROKE_TYPES[row["STROKETYPE"]]
    milliseconds = _integer(row["MILLISECONDS"], "MILLISECONDS", 0, 999)
    date_time = _instant(row["UTCDATETIME"], milliseconds)

    latitude = _number(row["LATITUDE"], "LATITUDE")
    longitude = _number(row["LONGITUDE"], "LONGITUDE")
    if not -90 <= latitude <= 90:
        raise RowError(f"LATITUDE out of range: {latitude}")
    if not -180 <= longitude <= 180:
        raise RowError(f"LONGITUDE out of range: {longitude}")

    amplitude = _number(row["AMPLITUDE"], "AMPLITUDE")
    if ground and amplitude == 0:
        raise RowError("AMPLITUDE is 0 on a GROUND_STROKE")
    if not ground and amplitude != 0:
        raise RowError(f"AMPLITUDE is {amplitude} on a CLOUD_STROKE")

    semi_major = _number(row["ERRSEMIMAJOR"], "ERRSEMIMAJOR")
    semi_minor = _number(row["ERRSEMIMINOR"], "ERRSEMIMINOR")
    if semi_minor <= 0:
        raise RowError(f"ERRSEMIMINOR is not positive: {semi_minor}")
    if semi_major < 0:
        raise RowError(f"ERRSEMIMAJOR is negative: {semi_major}")
    if semi_major != 0 and semi_minor > semi_major:
        raise RowError(f"ERRSEMIMINOR {semi_minor} is larger than ERRSEMIMAJOR {semi_major}")
    angle = _number(row["ERRELIPSEANGLE"], "ERRELIPSEANGLE")
    if not -90 <= angle <= 90:
        raise RowError(f"ERRELIPSEANGLE is outside -90 to 90: {angle}")

    sequence = row["STRIKESEQNUMBER"]
    polarity = row["POLARITY"]
    return StrokeRecord(
        line=line,
        date_time=date_time,
        latitude=latitude,
        longitude=longitude,
        peak_current=amplitude / alaska_uswfs.AMPERES_PER_KILOAMPERE if ground else None,
        cloud_to_ground=ground,
        network_code=_integer(row["NETWORKCODE"], "NETWORKCODE", 0, SMALLINT[1]),
        sequence_number=(None if sequence == ""
                         else _integer(sequence, "STRIKESEQNUMBER", 0, INTEGER[1])),
        gdop=_integer(row["GDOP"], "GDOP", 1, SMALLINT[1]),
        ellipse_semi_major_axis=(None if semi_major == 0
                                 else round(semi_major * alaska_uswfs.ELLIPSE_AXIS_FACTOR, 1)),
        ellipse_semi_minor_axis=round(semi_minor * alaska_uswfs.ELLIPSE_AXIS_FACTOR, 1),
        ellipse_angle=angle,
        polarity_contradicted=polarity != "" and polarity != POLARITIES[
            (amplitude > 0) - (amplitude < 0)],
    )


# --------------------------------------------------------------------------
# Years
# --------------------------------------------------------------------------

def read_years(release: Release, years: set[int] | None = None) -> Iterator[ReleaseYear]:
    """The release's years, one at a time, in file order, records as read.

    Only the ``years`` asked for are converted (all when ``None``). A refused row
    whose year cannot be read is counted with the year being read.
    """
    current: ReleaseYear | None = None
    pending: list[tuple[int, str]] = []
    with open_strokes(release.path, release.member) as handle:
        reader = csv.reader(handle)
        next(reader)
        for line, values in enumerate(reader, start=2):
            if not values:
                continue
            year = _year_of(values)
            if year is not None and (current is None or year != current.year):
                if current is not None and (years is None or current.year in years):
                    yield current
                current = ReleaseYear(year)
                current.problems, pending = pending, []
            if years is not None and (current is None or current.year not in years):
                continue
            try:
                record = parse_row(values, line)
            except RowError as error:
                (pending if current is None else current.problems).append((line, str(error)))
                continue
            current.records.append(record)
    if current is not None and (years is None or current.year in years):
        yield current


def content_key(record: StrokeRecord) -> tuple:
    """The order of a year's strokes, from their values alone.

    By instant, then every other published value, the sequence number last. Two
    records with the same key are the same values, so which comes first changes
    nothing that is stored; two that differ only in the sequence number are the
    same stroke published twice, and end up side by side.
    """
    return published_key(record) + (
        -1 if record.sequence_number is None else record.sequence_number,)


def published_key(record: StrokeRecord) -> tuple:
    """Every published value but the sequence number, the instant first."""
    return (record.date_time, record.cloud_to_ground, record.latitude, record.longitude,
            0.0 if record.peak_current is None else record.peak_current, record.gdop,
            -1.0 if record.ellipse_semi_major_axis is None else record.ellipse_semi_major_axis,
            record.ellipse_semi_minor_axis, record.ellipse_angle, record.network_code)


@lru_cache(maxsize=1)
def _to_alaska_albers():
    from pyproj import Transformer
    return Transformer.from_crs(alaska_uswfs.SOURCE_SRID, alaska_uswfs.PROJECTED_SRID,
                                always_xy=True)


def prepare_year(content: ReleaseYear) -> ReleaseYear:
    """Put a year's records in content order, drop duplicates and group the flashes.

    In place; returns ``content``.
    """
    records = sorted(content.records, key=content_key)
    kept: list[StrokeRecord] = []
    for record in records:
        if kept and published_key(kept[-1]) == published_key(record):
            content.duplicates += 1
            continue
        kept.append(record)
    content.records = kept
    if not kept:
        return content

    for ordinal, record in enumerate(kept, start=1):
        record.ordinal = ordinal
    t = np.array([record.date_time.timestamp() for record in kept])
    x, y = _to_alaska_albers().transform(np.array([record.longitude for record in kept]),
                                         np.array([record.latitude for record in kept]))
    kind = np.array([GROUND if record.cloud_to_ground else CLOUD for record in kept])
    flash = group_strokes(t, x, y, FLASH_RULE, kind=kind)

    sizes = np.bincount(flash)
    first: dict[int, int] = {}
    seen: dict[int, int] = {}
    for record, number in zip(kept, flash.tolist()):
        first.setdefault(number, record.ordinal)
        seen[number] = seen.get(number, 0) + 1
        record.first_ordinal = first[number]
        record.multiplicity = int(sizes[number])
        record.stroke_index = seen[number]
    content.flashes = len(sizes)
    content.cloud_flashes = len({number for number, k in zip(flash.tolist(), kind.tolist())
                                 if k == CLOUD})

    margin = datetime.timedelta(seconds=alaska_uswfs.FLASH_MAX_DURATION_S)
    content.near_new_year = sum(
        record.date_time < content.start + margin or record.date_time >= content.end - margin
        for record in kept)
    return content
