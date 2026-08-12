#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Guatemalan INAB fire reports from the downloaded GeoJSON.

Loads *Monitoreo de Incendios Forestales* — the ``datos_generales`` layer, one row
per fire reported to INAB — into
:class:`~src.providers.guatemala_inab.wildfire.InabWildfire` rows and the point each
was reported at into
:class:`~src.providers.guatemala_inab.ignition.InabIgnition`.

The source is whatever
:mod:`src.apps.download.wildfires.guatemala_inab.download_wildfires` wrote, so point
this at the directory it downloaded into::

    python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \\
        -d ~/data/guatemala

or at named files, or at selected years::

    python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \\
        -s guatemala_inab_fire-reports_2025.geojson

    python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \\
        -s guatemala_inab_fire-reports_all.geojson --year 2025 2026

Only the ``fire-reports`` layer is imported. The other four the downloader can fetch
have no model behind them: ``informes`` is a second, one-to-many model rather than
more columns on this one (see :mod:`src.providers.guatemala_inab.wildfire`), and the
burn-scar layers are a single season rather than an archive.

A year is the unit of work
---------------------------

This dataset is small — 4,615 records, 0.9 MB, the whole of it fetchable in one
request the downloader deliberately does not make — so importing it in one
transaction would work. It is imported **a year at a time** anyway, one transaction
per year, as every other importer in the project does, because the size of a source
is the least durable thing about it: this one has grown from 187 records in 2023 to
1,908 in the first seven months of 2026, and an import whose shape depends on the
data staying small has to be rewritten the year it stops being small.

What that buys, today rather than later: a run interrupted half way keeps the years
it finished; ``--year`` makes re-importing one year a fraction of a second; and the
log says what each year did rather than what the run did.

Every file is read before any year is written, which is what makes the year buckets
complete. A run given both the ``all`` file and a per-year file would otherwise
import the same records twice — the second copy failing on
``inab_wildfire.global_id``, half way through, having already replaced some years.
Reading first also means the duplicate is found and reported rather than hit.

Replacing a year, and why the delete also keys on the identifier
-----------------------------------------------------------------

A year is **replaced wholesale**: the stored fires whose start instant falls in it
are deleted and the file's records inserted, so re-importing a revised publication
supersedes rather than doubles, and a report INAB has withdrawn goes.

The delete removes one more thing than that: every stored row whose ``global_id``
appears in the batch, whatever year it is currently filed under. That clause is
there because *this program* and *the server* need not agree about which year a
record belongs to, and the disagreement is silent.

A year here is the **Guatemalan** calendar year, resolved through
:data:`~src.providers.guatemala_inab.DEFAULT_TIME_ZONE`, because that is the year
the fire happened in and what ``v_inab_wildfire.start_date_time_local`` shows. The
downloader's ``--year`` asks the ArcGIS server for
``EXTRACT(YEAR FROM fecha_hora_incendio)``, which the server evaluates itself. If it
does so in UTC, a fire reported in the last six hours of 31 December is in the
server's *next* year and in this program's *current* one — and without the
identifier clause, importing that record's file would delete the row the other file
had stored and not put it back. With it, the row moves instead of vanishing. It
costs one ``OR`` and it removes the entire class.

The instant is published as UTC, and stored as published
---------------------------------------------------------

``fecha_hora_incendio`` arrives as milliseconds since the Unix epoch — ArcGIS's own
serialisation, which is UTC by definition — or as ISO 8601 if the file was fetched
with the downloader's ``--iso-dates``. Both are read.

So unlike the Greek and Spanish imports there is **no local-to-instant conversion**
here: what the source publishes is already an instant. What this import adds is the
zone name that instant should be read in, and Guatemala is one zone
(:data:`~src.providers.guatemala_inab.DEFAULT_TIME_ZONE`) for the whole country with
no daylight saving since 2006 — so, as for Greece, the zone is a rule rather than
something resolved from each fire's location, and no time zone areas need importing.

The times are worth trusting: in local time the hourly histogram peaks between 13:00
and 16:00, which is the afternoon fire peak rather than a date rounded to midnight.

What is never read
-------------------

The published layer carries the **name and telephone number of whoever reported each
fire** — 1,969 distinct pairs, mostly private individuals — and the INAB accounts
that created and edited each record.
:data:`~src.providers.guatemala_inab.PERSONAL_FIELDS` names all four and neither
model has a column for them.

They are dropped *here*, by never being read out of the feature, rather than by
being left unmapped after a staging load. That is the reason this importer parses
the GeoJSON in Python instead of handing it to ``ogr2ogr``, which would land all
thirty-three published attributes in a real table in the database before the mapping
got a say. Nothing that is not in :data:`IMPORTED_FIELDS` reaches a bind parameter.

The traps this source sets
---------------------------

**An unfilled text field is sometimes ``null`` and sometimes ``""``, in the same
column.** ``nombre_ap_1`` is ``null`` on 80 records and ``""`` on 3,080, so an
import that stores what it is handed reports 3,080 fires inside a protected area
called ``""``. Every text attribute goes through
:func:`~src.providers.guatemala_inab.blank_to_none`; :func:`read_text` is the only
way this module reads one.

**The municipality code is inside the name.** ``rio_hondo_1903`` is Río Hondo,
department 19, municipality 03. :func:`~src.providers.guatemala_inab.parse_municipality`
takes it apart and validates the code's department against the published one, which
is what rejects the four truncated slugs; the slug itself is stored whole either
way.

**The typed coordinates are not the location.** ``coordenada_x``/``coordenada_y``
are filled on 440 records, a dozen of them with the axes swapped, and are stored as
published without ever being reprojected or used to place a fire. The geometry is
the answer. See :class:`~src.providers.guatemala_inab.ignition.InabIgnition`.

**Three points are not in Guatemala** and all three are already flagged ``falso``.
They are stored as published and counted in the run's report — a coordinate this
import invented would be worse than one the provider got wrong.

What makes a record unusable
-----------------------------

Two things, and both are refusals to invent a value for a ``NOT NULL`` column:

* **no ``fecha_hora_incendio``** — four of the 4,615 records, which carry nothing
  but an identifier and a map tap. There is no second date in this layer to fall
  back on and the year would date them to 1 January, which is an invention;
* **no ``globalid``** — no record published today lacks one, and one that did could
  not be re-imported or matched to anything.

Everything else is degraded rather than refused. A record with no geometry is stored
**without a point**, which the model allows and the view left-joins for; a false
alarm is stored, because a record saying *this was not a fire* can be filtered
afterwards and a discarded one cannot be recovered.

Requires no ``ogr2ogr`` and no time zone areas. Import the
:doc:`OCHA boundaries </applications/ocha_import_admin_boundaries>` first if the
fires are to know which country they are in; the import runs without them and says
so. Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import logging
import sys
import time
import typing
import zoneinfo

from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.providers import guatemala_inab
from src.providers.guatemala_inab import blank_to_none
from src.providers.guatemala_inab import is_false_alarm
from src.providers.guatemala_inab import is_in_guatemala
from src.providers.guatemala_inab import parse_municipality

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: What a downloaded data file is called. The downloader writes its provenance
#: sidecar as ``.meta.json``, so a directory glob for this picks up the data and
#: leaves the sidecars alone.
DATA_SUFFIX = ".geojson"

#: Fires converted and written per round trip.
#:
#: Smaller than the 2,000 the Greek and Spanish imports use, and it makes no
#: measurable difference here: the largest year of this dataset is under 2,000
#: records, so the batch size is a ceiling that is reached at most once a year
#: rather than 130 times a file. It is a number at all so that a source which grows
#: does not turn into one ``executemany`` of arbitrary size.
BATCH_SIZE = 500

#: How many individually bad records are logged per file before the rest are only
#: counted. A file that is wrong in some systematic way — the wrong layer, a format
#: change — would otherwise write one line per record and bury the summary saying so.
MAX_REPORTED_PROBLEMS = 20

#: The published attribute holding the key, as the hosted layer spells it.
FIELD_GLOBAL_ID = "globalid"

#: The published attribute holding the instant, and the two bookkeeping ones.
FIELD_DATE_TIME = "fecha_hora_incendio"
FIELD_CREATED = "created_date"
FIELD_EDITED = "last_edited_date"

#: Every published attribute this import reads.
#:
#: Named as a set rather than left implicit in the reader so that
#: :func:`unknown_fields` can report what a future publication adds, and so that a
#: test can assert the four personal fields are not among them. Nothing outside this
#: set reaches a bind parameter — see the module docstring.
IMPORTED_FIELDS = frozenset({
    FIELD_GLOBAL_ID, "objectid", "ob_id",
    FIELD_DATE_TIME, FIELD_CREATED, FIELD_EDITED,
    "estado_aviso", "forma_comunicacion", "institucion", "institucion_otra",
    "tipo_incendio",
    "departamento", "municipio", "aldea_lugar", "finca",
    "region_inab", "subregion_inab",
    "nombre_ap_1", "nombre_ap_2",
    "coordenada_x", "coordenada_y", "sistema_proyeccion", "zona", "altitud",
})

#: The published attributes that are deliberately **not** stored, and why.
#:
#: Written down rather than merely omitted so that the omission is a decision on the
#: record, in the same spirit as
#: :data:`~src.providers.guatemala_inab.PERSONAL_FIELDS`, and so that these do not
#: show up as *unknown* every time a file is read.
IGNORED_FIELDS = {
    "punto_dentro_ap": "a single constant string; it says nothing "
                       "'nombre_ap_1 IS NOT NULL' does not",
    "link_googlemaps": "a second copy of the coordinate, agreeing with the geometry "
                       "to 1e-10 on 4,508 records and disagreeing by over a "
                       "kilometre on 83 — the geometry is the answer",
    "logoinab": "filled on no record at all",
    "con_aviso": "constant 'Si'",
    "informes_count": "constant '1', and wrong: there are 5,812 informes",
}

#: Every published attribute this import knows about, stored or not.
KNOWN_FIELDS = frozenset(IMPORTED_FIELDS | set(IGNORED_FIELDS)
                         | set(guatemala_inab.PERSONAL_FIELDS))

#: The zone every instant is read in. One rule for the whole country — see the
#: module docstring.
TIME_ZONE = guatemala_inab.DEFAULT_TIME_ZONE

#: The zone as a :mod:`zoneinfo` object, for bucketing an instant into its
#: Guatemalan calendar year.
_ZONE = zoneinfo.ZoneInfo(TIME_ZONE)


# --------------------------------------------------------------------------
# Reading a published record
# --------------------------------------------------------------------------

@dataclasses.dataclass
class FireReport:
    """One published fire report, read out of a GeoJSON feature.

    Attributes
    ----------
    source : str
        The file it came from, for the message that reports a problem with it.
    index : int
        Its position in that file's feature list, 1-based. The only way to point at
        a record whose ``globalid`` is what is missing.
    global_id : str or None
        ``globalid``. ``None`` makes the record unusable — see :func:`usable`.
    start : datetime.datetime or None
        ``fecha_hora_incendio`` as an aware UTC instant. ``None`` likewise.
    longitude, latitude : float or None
        The published point, or ``None`` for a record that carries no geometry.
    problems : list of str
        What could not be read on a record that is still going to be stored.
    """

    source: str
    index: int
    global_id: str | None = None
    object_id: int | None = None
    source_id: int | None = None
    start: datetime.datetime | None = None
    published_at: datetime.datetime | None = None
    edited_at: datetime.datetime | None = None
    report_status: str | None = None
    report_channel: str | None = None
    institution: str | None = None
    institution_other: str | None = None
    fire_location: str | None = None
    department_name: str | None = None
    municipality_name: str | None = None
    municipality_code: int | None = None
    locality_name: str | None = None
    estate_name: str | None = None
    inab_region: str | None = None
    inab_subregion: str | None = None
    protected_area_name: str | None = None
    protected_area_name_secondary: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    reported_x: float | None = None
    reported_y: float | None = None
    reported_crs: str | None = None
    utm_zone: int | None = None
    altitude_m: float | None = None
    problems: list[str] = dataclasses.field(default_factory=list)

    @property
    def located(self) -> bool:
        """Whether the record published a point, and so gets an ignition row."""
        return self.longitude is not None and self.latitude is not None

    @property
    def year(self) -> int | None:
        """The Guatemalan calendar year the fire was reported in.

        Local rather than UTC, and the difference is six hours: see the module
        docstring on why the delete keys on the identifier as well as on this.
        """
        if self.start is None:
            return None
        return self.start.astimezone(_ZONE).year

    def where(self) -> str:
        """How a message names this record."""
        return f"record {self.index}" + (f" ({self.global_id})" if self.global_id else "")


def properties(feature: dict) -> dict[str, Any]:
    """A feature's attributes, keyed in lower case.

    The hosted layer publishes ``objectid`` and ``globalid`` in lower case, but that
    is a property of how this particular view was published rather than of ArcGIS:
    the same fields are ``OBJECTID`` and ``GlobalID`` on a service published another
    way. Folding the keys once here costs nothing and means a republication that
    changes the case is read rather than silently emptied.
    """
    published = feature.get("properties")
    if not isinstance(published, dict):
        return {}
    return {str(key).lower(): value for key, value in published.items()}


def unknown_fields(names: typing.Iterable[str]) -> list[str]:
    """The published attributes this import has never heard of, sorted.

    Reported once per file rather than per record. INAB adding a thirty-fourth
    attribute is not an error — nothing breaks, the column is simply not stored —
    but it is worth being told about, which is the same call the Greek import makes
    about an unknown worksheet column.
    """
    return sorted(set(names) - KNOWN_FIELDS)


def read_text(published: dict[str, Any], name: str) -> str | None:
    """A published text attribute, with both spellings of *unfilled* folded to one.

    The **only** way this module reads a text attribute. This source writes an
    unfilled field as ``null`` on some records and as ``""`` on others of the same
    column — 80 against 3,080 for ``nombre_ap_1`` — so a reader that skipped
    :func:`~src.providers.guatemala_inab.blank_to_none` would store thousands of
    fires as being inside a protected area named ``""``. See the module docstring.
    """
    value = published.get(name)
    if value is None:
        return None
    return blank_to_none(str(value))


def read_number(published: dict[str, Any], name: str,
                problems: list[str]) -> float | None:
    """A published numeric attribute, or ``None`` with a note if it is not one.

    JSON has no empty number, so the ``""``/``null`` problem does not arise here —
    but a value typed into a form and published as text does, and a string that will
    not parse is a problem worth reporting rather than a silent ``NULL``.
    """
    value = published.get(name)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    written = blank_to_none(str(value))
    if written is None:
        return None
    try:
        return float(written)
    except ValueError:
        problems.append(f"{name} is not a number: {written!r}")
        return None


def read_integer(published: dict[str, Any], name: str,
                 problems: list[str]) -> int | None:
    """A published integer attribute.

    Read through :func:`read_number` because these arrive as JSON numbers, and JSON
    has one number type: ``objectid`` is as likely to be ``13.0`` as ``13``. A value
    with a real fractional part is a problem rather than something to round away.
    """
    value = read_number(published, name, problems)
    if value is None:
        return None
    if value != int(value):
        problems.append(f"{name} is not a whole number: {value!r}")
        return None
    return int(value)


def read_instant(published: dict[str, Any], name: str,
                 problems: list[str]) -> datetime.datetime | None:
    """A published date attribute as an aware UTC instant.

    Two written forms, both produced by the downloader: **milliseconds since the
    Unix epoch**, which is ArcGIS's own serialisation and UTC by definition, and
    **ISO 8601**, which is what ``--iso-dates`` rewrites them to. Reading both is
    what lets a file be imported however it was fetched.

    A naive ISO reading is taken as UTC. The downloader always writes an offset, so
    this can only be reached by a hand-edited file, and UTC is what every other form
    of this field means.
    """
    value = published.get(name)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(value / 1000.0,
                                                   datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            problems.append(f"{name} is not a readable epoch: {value!r}")
            return None

    written = blank_to_none(str(value))
    if written is None:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(written)
    except ValueError:
        problems.append(f"{name} is not a readable date: {written!r}")
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def read_point(feature: dict, problems: list[str]) -> tuple[float | None, float | None]:
    """The published longitude and latitude, or ``(None, None)``.

    The geometry is the authoritative location of an INAB fire: all 4,615 published
    records carry one and it is EPSG:4326 already, so there is nothing to reproject
    and nothing to reconstruct. A record without one is stored without a point
    rather than dropped.

    Anything that is not a well-formed ``Point`` is refused with a note. This layer
    publishes nothing else, so the note means the wrong layer is being imported —
    which is worth saying out loud rather than turning into a missing coordinate.
    """
    geometry = feature.get("geometry")
    if geometry is None:
        return None, None
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        kind = geometry.get("type") if isinstance(geometry, dict) else type(geometry).__name__
        problems.append(f"geometry is a {kind}, not a Point")
        return None, None

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        problems.append(f"geometry has no usable coordinates: {coordinates!r}")
        return None, None
    try:
        return float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        problems.append(f"geometry coordinates are not numbers: {coordinates[:2]!r}")
        return None, None


def read_report(feature: dict, source: str, index: int) -> FireReport:
    """Turn one GeoJSON feature into a record.

    Every attribute is fetched by name from :data:`IMPORTED_FIELDS`; there is no
    ``**properties`` anywhere in this function, which is what makes *the four
    personal fields are never read* a property of the code rather than of a mapping
    that happens not to mention them.
    """
    published = properties(feature)
    problems: list[str] = []
    report = FireReport(source=source, index=index, problems=problems)

    report.global_id = read_text(published, FIELD_GLOBAL_ID)
    report.object_id = read_integer(published, "objectid", problems)
    if report.object_id is None and isinstance(feature.get("id"), (int, float)):
        # ArcGIS writes the object id onto the feature as well as into its
        # properties, and an export that dropped the attribute would still carry it
        # there. Only a numeric one is read: some GeoJSON writers put a string key
        # in "id", and that is not this layer's ``objectid``.
        report.object_id = read_integer({"id": feature["id"]}, "id", problems)
    report.source_id = read_integer(published, "ob_id", problems)

    report.start = read_instant(published, FIELD_DATE_TIME, problems)
    report.published_at = read_instant(published, FIELD_CREATED, problems)
    report.edited_at = read_instant(published, FIELD_EDITED, problems)

    report.report_status = read_text(published, "estado_aviso")
    report.report_channel = read_text(published, "forma_comunicacion")
    report.institution = read_text(published, "institucion")
    report.institution_other = read_text(published, "institucion_otra")
    report.fire_location = read_text(published, "tipo_incendio")

    report.department_name = read_text(published, "departamento")
    report.municipality_name, report.municipality_code = parse_municipality(
        read_text(published, "municipio"), report.department_name)
    report.locality_name = read_text(published, "aldea_lugar")
    report.estate_name = read_text(published, "finca")
    report.inab_region = read_text(published, "region_inab")
    report.inab_subregion = read_text(published, "subregion_inab")
    report.protected_area_name = read_text(published, "nombre_ap_1")
    report.protected_area_name_secondary = read_text(published, "nombre_ap_2")

    report.longitude, report.latitude = read_point(feature, problems)
    report.reported_x = read_number(published, "coordenada_x", problems)
    report.reported_y = read_number(published, "coordenada_y", problems)
    report.reported_crs = read_text(published, "sistema_proyeccion")
    report.utm_zone = read_integer(published, "zona", problems)
    report.altitude_m = read_number(published, "altitud", problems)
    return report


def read_file(path: Path, logger: logging.Logger) -> list[FireReport]:
    """Every record of one downloaded file.

    Raises
    ------
    RuntimeError
        If the file is not JSON, or is not a GeoJSON ``FeatureCollection``. Both
        mean the wrong file is being imported, which is worth stopping for: the
        alternative is a run that reports importing nothing and looks like an empty
        year.
    """
    log = ArchiveLogger(logger, {"archive": path.name})
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{path} is not readable JSON: {error}") from error

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        kind = document.get("type") if isinstance(document, dict) else type(document).__name__
        raise RuntimeError(
            f"{path} is not a GeoJSON FeatureCollection (it is a {kind!r}). This "
            f"import reads what "
            f"src.apps.download.wildfires.guatemala_inab.download_wildfires writes."
        )

    features = document.get("features")
    if not isinstance(features, list):
        raise RuntimeError(f"{path} has no list of features")

    names: set[str] = set()
    reports: list[FireReport] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            raise RuntimeError(f"{path}: feature {index} is not an object")
        names.update(properties(feature))
        reports.append(read_report(feature, path.name, index))

    # Over every feature rather than the first: a hosted view omits an attribute it
    # has no value for on a given record, so a new field could be absent from the
    # first thousand and present on the last.
    unknown = unknown_fields(names)
    if unknown:
        log.warning(
            "%d published attribute(s) this import does not know and will not store: "
            "%s. Add them to IMPORTED_FIELDS (and a column to the model) if they are "
            "wanted, or to IGNORED_FIELDS if they are not.",
            len(unknown), ", ".join(unknown),
        )
    log.info("%d record(s) read", len(reports))
    return reports


def read_files(paths: list[Path], logger: logging.Logger) -> list[FireReport]:
    """Every record of every file, read before anything is written.

    See the module docstring: the years are only complete once every file has been
    read, and a run given both the ``all`` file and a per-year file has to find the
    duplicate rather than hit it half way through.
    """
    reports: list[FireReport] = []
    for index, path in enumerate(paths, start=1):
        logger.info("[%d/%d] %s", index, len(paths), path.name)
        reports += read_file(path, logger)
    return reports


# --------------------------------------------------------------------------
# Deciding what is storable, and which year it belongs to
# --------------------------------------------------------------------------

class RunOutcome:
    """What the whole run did, for the summary line and the exit status."""

    def __init__(self) -> None:
        self.read = 0
        self.written = 0
        self.skipped = 0
        self.duplicates = 0
        self.problems = 0
        self.located = 0
        self.false_alarms = 0
        self.unverified = 0
        self.outside_guatemala = 0
        self.deleted = 0
        self.years: list[int] = []


def report_problems(report: FireReport, outcome: RunOutcome,
                    logger: logging.Logger) -> None:
    """Log what could not be read on a record that is still going to be stored."""
    if not report.problems:
        return
    outcome.problems += 1
    if outcome.problems <= MAX_REPORTED_PROBLEMS:
        logger.warning("%s: %s: %s", report.source, report.where(),
                       "; ".join(report.problems))
    elif outcome.problems == MAX_REPORTED_PROBLEMS + 1:
        logger.warning("Further per-record problems are counted, not logged")


def usable(report: FireReport, outcome: RunOutcome, logger: logging.Logger) -> bool:
    """Whether a record can be stored at all.

    Two conditions, both of them a refusal to invent a ``NOT NULL`` value rather
    than a judgement about the record's quality — see the module docstring. Four of
    the 4,615 published records fail the first and none fails the second.
    """
    missing = []
    if report.global_id is None:
        missing.append(f"no {FIELD_GLOBAL_ID}")
    if report.start is None:
        missing.append(f"no {FIELD_DATE_TIME}")
    if not missing:
        return True

    outcome.skipped += 1
    if outcome.skipped <= MAX_REPORTED_PROBLEMS:
        logger.warning("%s: %s skipped: %s", report.source, report.where(),
                       " and ".join(missing))
    elif outcome.skipped == MAX_REPORTED_PROBLEMS + 1:
        logger.warning("Further skipped records are counted, not logged")
    return False


def bucket_by_year(reports: list[FireReport], years: set[int] | None,
                   outcome: RunOutcome,
                   logger: logging.Logger) -> dict[int, list[FireReport]]:
    """Group the storable records by the year they will replace.

    A record whose ``globalid`` has already been seen in this run is dropped with a
    warning and counted. The published data has none — 4,615 distinct keys in 4,615
    records — so this only fires when a run is given two files that overlap, which
    is what asking for the ``all`` file *and* a year does. Keeping the first is
    arbitrary and stated: the two copies are the same record, and if they are not,
    the run has been given files from two different downloads and the log says so.

    Records are ordered within their year by instant so that a run's inserts do not
    depend on the order the server happened to page them in.
    """
    buckets: dict[int, list[FireReport]] = {}
    seen: dict[str, FireReport] = {}

    for report in reports:
        outcome.read += 1
        report_problems(report, outcome, logger)
        if not usable(report, outcome, logger):
            continue

        first = seen.get(report.global_id)
        if first is not None:
            outcome.duplicates += 1
            logger.warning(
                "%s: %s is already in this run, from %s (%s); the first was kept",
                report.source, report.where(), first.source, first.where(),
            )
            continue
        seen[report.global_id] = report

        year = report.year
        if years is not None and year not in years:
            continue
        buckets.setdefault(year, []).append(report)

    for year, bucket in buckets.items():
        bucket.sort(key=lambda item: (item.start, item.global_id))
        logger.debug("%d: %d record(s) to write", year, len(bucket))
    return dict(sorted(buckets.items()))


# --------------------------------------------------------------------------
# The statements
# --------------------------------------------------------------------------

#: Removes a year's fires and their points in one statement.
#:
#: One statement rather than four, for the reason the Greek and Andalusian imports
#: give: ``inab_wildfire.ignition_id`` references ``ignition`` and
#: ``inab_wildfire.id`` references ``wildfire``, so no order of separate statements
#: is safe, while inside one statement the foreign keys are checked once at the end
#: against a consistent final state. The data-modifying CTEs all run to completion
#: whether or not the outer query reads them, which is what makes this work.
#:
#: The ``OR`` on ``global_id`` is the point of interest — see the module docstring.
#: It makes the delete *at least* a replacement of the year and never less than a
#: replacement of the records about to be written, so a record the server and this
#: program disagree about the year of moves rather than disappearing.
#:
#: The bounds are half-open instants rather than a ``date_part``: the column is
#: indexed (``ix_wildfire_start_date_time``) and an expression on it would not use
#: that index, which matters once this table shares the database with 448,602
#: Canadian fire reports.
DELETE_YEAR_SQL = """
WITH doomed AS (
    SELECT n.id AS id, n.ignition_id AS ignition_id
    FROM inab_wildfire n
    JOIN wildfire w ON w.id = n.id
    WHERE (w.start_date_time >= :year_start AND w.start_date_time < :year_end)
       OR n.global_id = ANY(CAST(:global_ids AS text[]))
),
removed_child AS (
    DELETE FROM inab_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM inab_ignition
    WHERE id IN (SELECT ignition_id FROM doomed WHERE ignition_id IS NOT NULL)
    RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: How many fires the statement above is about to remove. Asked separately because
#: the outer ``DELETE`` of that statement is the one on ``ignition``, so its
#: ``rowcount`` counts points rather than fires.
COUNT_DOOMED_SQL = """
SELECT count(*)
FROM inab_wildfire n
JOIN wildfire w ON w.id = n.id
WHERE (w.start_date_time >= :year_start AND w.start_date_time < :year_end)
   OR n.global_id = ANY(CAST(:global_ids AS text[]))
"""

#: Draws ``:count`` identifiers from a table's own sequence in one round trip. The
#: parent row's key has to be known before the child insert, so ``RETURNING`` would
#: come too late.
ALLOCATE_SQL = ("SELECT nextval(pg_get_serial_sequence(:table, 'id')) "
                "FROM generate_series(1, :count)")

#: The stored point, straight from the two published numbers.
#:
#: No ``ST_Transform``: the service publishes EPSG:4326 degrees, which is the CRS
#: the model stores, so the point *is* the published pair — the same position the
#: Greek import is in.
GEOMETRY_SQL = "ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)"

#: The country the point falls in, or ``NULL``.
#:
#: A correlated subquery rather than a join, so it can sit inside an ``executemany``.
#: ``ST_Contains`` is strict, so a record with no point yields no row and the column
#: comes out ``NULL`` without a guard — and so does an unimported boundary provider,
#: whose id is then ``NULL`` and matches nothing.
BOUNDARY_SQL = f"""(
    SELECT boundary.id FROM admin_boundary AS boundary
    WHERE boundary.data_provider_id = :boundary_provider_id
      AND boundary.level = 0
      AND ST_Contains(boundary.geometry, {GEOMETRY_SQL})
    LIMIT 1
)"""

INSERT_IGNITION_SQL = f"""
INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                      admin_boundary_id)
VALUES (:ignition_id, 'inab_ignition', :provider_id, {GEOMETRY_SQL},
        :start_date_time, :time_zone, {BOUNDARY_SQL})
"""

#: ``end_date_time`` is a literal ``NULL`` rather than a bound parameter because
#: this layer publishes no end time for any fire, ever: the instants a fire was
#: controlled and extinguished are in the ``informes`` layer, which is a second
#: model rather than two more columns. Writing it as a literal says so at the point
#: where a reader would otherwise look for the parameter.
INSERT_WILDFIRE_SQL = f"""
INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                      time_zone, admin_boundary_id)
VALUES (:wildfire_id, 'inab_wildfire', :provider_id, :start_date_time, NULL,
        :time_zone, {BOUNDARY_SQL})
"""

#: Columns of ``inab_ignition``, in the order they are bound.
IGNITION_COLUMNS = ("global_id", "reported_x", "reported_y", "reported_crs",
                    "utm_zone", "altitude_m")

#: Columns of ``inab_wildfire``, in the order they are bound.
WILDFIRE_COLUMNS = ("global_id", "object_id", "source_id", "report_status",
                    "report_channel", "institution", "institution_other",
                    "fire_location", "department_name", "municipality_name",
                    "municipality_code", "locality_name", "estate_name",
                    "inab_region", "inab_subregion", "protected_area_name",
                    "protected_area_name_secondary", "published_at", "edited_at",
                    "ignition_id")


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    """Build the child ``INSERT`` for one of the two provider tables."""
    names = ("id", *columns)
    values = ", ".join(f":{name}" for name in names)
    return f"INSERT INTO {table} ({', '.join(names)}) VALUES ({values})"


INSERT_INAB_IGNITION_SQL = _insert_sql("inab_ignition", IGNITION_COLUMNS)
INSERT_INAB_WILDFIRE_SQL = _insert_sql("inab_wildfire", WILDFIRE_COLUMNS)

#: Whether this PostgreSQL server knows the Guatemalan zone name.
#:
#: Checked rather than assumed because the two views resolve
#: ``start_date_time AT TIME ZONE time_zone``, which raises on a name the server's
#: tzdata does not carry — and it would raise in whatever query first selected from
#: the view, months later, rather than here.
KNOWN_TIME_ZONE_SQL = "SELECT count(*) FROM pg_timezone_names WHERE name = :zone"


# --------------------------------------------------------------------------
# Writing a year
# --------------------------------------------------------------------------

def year_bounds(year: int) -> tuple[datetime.datetime, datetime.datetime]:
    """The half-open instant range of one Guatemalan calendar year.

    Computed in Python from :data:`TIME_ZONE` rather than with ``AT TIME ZONE`` in
    SQL so that the bound is a plain ``timestamptz`` comparison the index on
    ``wildfire.start_date_time`` can use, and so that the year a record is *placed*
    in (:attr:`FireReport.year`) and the year it is *deleted* from are the same
    arithmetic rather than two implementations that have to agree.
    """
    start = datetime.datetime(year, 1, 1, tzinfo=_ZONE)
    end = datetime.datetime(year + 1, 1, 1, tzinfo=_ZONE)
    return start.astimezone(datetime.timezone.utc), end.astimezone(datetime.timezone.utc)


def allocate(session: Session, table: str, count: int) -> list[int]:
    """Draw ``count`` primary keys from a table's own sequence."""
    if count <= 0:
        return []
    return list(session.scalars(text(ALLOCATE_SQL),
                                {"table": table, "count": count}).all())


def delete_year(session: Session, year: int, global_ids: list[str]) -> int:
    """Remove a year's fires and their points, returning how many fires went."""
    start, end = year_bounds(year)
    parameters = {"year_start": start, "year_end": end, "global_ids": global_ids}
    fires = session.scalar(text(COUNT_DOOMED_SQL), parameters) or 0
    session.execute(text(DELETE_YEAR_SQL), parameters)
    return fires


def report_parameters(report: FireReport, provider_id: int,
                      boundary_provider_id: int | None) -> dict[str, object]:
    """Everything the four statements bind for one record, ids excepted."""
    parameters: dict[str, object] = {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "time_zone": TIME_ZONE,
        "start_date_time": report.start,
        "longitude": report.longitude,
        "latitude": report.latitude,
    }
    for column in IGNITION_COLUMNS:
        parameters[column] = getattr(report, column)
    for column in WILDFIRE_COLUMNS:
        if column != "ignition_id":
            parameters[column] = getattr(report, column)
    return parameters


def write_batch(session: Session, batch: list[FireReport], provider_id: int,
                boundary_provider_id: int | None, outcome: RunOutcome) -> None:
    """Insert one batch of fires, parents before children.

    Four statements at most, each an ``executemany`` over the whole batch:
    ``ignition`` and ``inab_ignition`` for the records that have a point, then
    ``wildfire`` and ``inab_wildfire`` for all of them.

    Plain inserts and not upserts, the year having been deleted first.
    """
    if not batch:
        return

    located = [report for report in batch if report.located]
    wildfire_ids = allocate(session, "wildfire", len(batch))
    ignition_ids = allocate(session, "ignition", len(located))

    ignitions: list[dict[str, object]] = []
    inab_ignitions: list[dict[str, object]] = []
    wildfires: list[dict[str, object]] = []
    inab_wildfires: list[dict[str, object]] = []

    for report in batch:
        parameters = report_parameters(report, provider_id, boundary_provider_id)
        wildfire_id = wildfire_ids.pop()
        ignition_id = None

        if report.located:
            ignition_id = ignition_ids.pop()
            outcome.located += 1
            if not is_in_guatemala(report.longitude, report.latitude):
                outcome.outside_guatemala += 1
            ignitions.append(dict(parameters, ignition_id=ignition_id))
            inab_ignitions.append(
                {"id": ignition_id,
                 **{name: parameters[name] for name in IGNITION_COLUMNS}}
            )

        if is_false_alarm(report.report_status):
            outcome.false_alarms += 1
        elif report.report_status == guatemala_inab.STATUS_UNVERIFIED:
            outcome.unverified += 1

        parameters["ignition_id"] = ignition_id
        wildfires.append(dict(parameters, wildfire_id=wildfire_id))
        inab_wildfires.append(
            {"id": wildfire_id,
             **{name: parameters[name] for name in WILDFIRE_COLUMNS}}
        )
        outcome.written += 1

    if ignitions:
        session.execute(text(INSERT_IGNITION_SQL), ignitions)
        session.execute(text(INSERT_INAB_IGNITION_SQL), inab_ignitions)
    session.execute(text(INSERT_WILDFIRE_SQL), wildfires)
    session.execute(text(INSERT_INAB_WILDFIRE_SQL), inab_wildfires)


def import_year(year: int, reports: list[FireReport], engine: Engine,
                provider_id: int, boundary_provider_id: int | None,
                outcome: RunOutcome, dry_run: bool,
                logger: logging.Logger) -> None:
    """Replace one year, in a transaction of its own.

    Committed here rather than by the caller, which is what makes a run interrupted
    half way through leave the years it finished in place and the year it was in the
    middle of exactly as it found it. ``--dry-run`` rolls the same work back, so it
    exercises every statement including the deletes.
    """
    before = outcome.written
    with Session(engine) as session:
        outcome.deleted += delete_year(session, year,
                                       [report.global_id for report in reports])
        batch: list[FireReport] = []
        for report in reports:
            batch.append(report)
            if len(batch) >= BATCH_SIZE:
                write_batch(session, batch, provider_id, boundary_provider_id, outcome)
                batch = []
        write_batch(session, batch, provider_id, boundary_provider_id, outcome)

        if dry_run:
            session.rollback()
        else:
            session.commit()

    outcome.years.append(year)
    logger.info("%d: %d fire(s) written%s", year, outcome.written - before,
                " (rolled back: --dry-run)" if dry_run else "")


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def require_known_time_zone(session: Session, logger: logging.Logger) -> None:
    """Refuse to import if the server cannot resolve the Guatemalan zone.

    Deliberately **not** :func:`~src.apps.imports.common.check_time_zones`, which
    every other wildfire importer calls. That function warns when no time zone areas
    are loaded, on the grounds that the fires will then be dated in a fallback zone
    instead of one resolved from their own location — and here that warning would be
    false. Guatemala is one zone for the whole country with no daylight saving since
    2006, so :data:`TIME_ZONE` is a rule rather than a fallback and the
    ``time_zone`` table is not consulted at all.

    What does have to be true is that PostgreSQL knows the name, because the two
    ``v_inab_*`` views resolve ``AT TIME ZONE`` with it.

    Raises
    ------
    RuntimeError
        If the server does not know the zone.
    """
    known = session.scalar(text(KNOWN_TIME_ZONE_SQL), {"zone": TIME_ZONE})
    if not known:
        raise RuntimeError(
            f"This PostgreSQL server does not know the time zone {TIME_ZONE!r}, so "
            f"the stored fires could not be read back in local time. Its tzdata is "
            f"broken or very old; update the server."
        )
    logger.debug("Storing every fire against %s", TIME_ZONE)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Guatemalan INAB fire reports from the GeoJSON files "
                    "written by the INAB download application.",
        epilog="Import the OCHA country boundaries first if the fires are to know "
               "which country they are in. No time zone areas are needed: Guatemala "
               "is one zone. Each year found is replaced wholesale, so re-importing "
               "a revised publication supersedes rather than doubles. Database "
               "settings not given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help=f"directory holding the downloaded files; every "
                             f"*{DATA_SUFFIX} in it is read")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more files to import instead of a whole directory")

    parser.add_argument("-y", "--year", type=int, nargs="+", dest="years",
                        help="import only these years, ignoring the other records of "
                             "a file that holds several")
    parser.add_argument("--dry-run", action="store_true",
                        help="do everything and roll it back, reporting what would "
                             "have been written and replaced")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def find_files(args: argparse.Namespace) -> list[Path]:
    """List the files to read, sorted.

    Raises
    ------
    RuntimeError
        If nothing was found — far more likely a wrong path than an empty download —
        or if a named file is not one of the downloader's.
    """
    if args.directory is not None:
        files = sorted(args.directory.glob(f"*{DATA_SUFFIX}"))
        if not files:
            raise RuntimeError(
                f"{args.directory} holds no *{DATA_SUFFIX} file. Fetch one with "
                f"src.apps.download.wildfires.guatemala_inab.download_wildfires."
            )
        return files

    unknown = [path for path in args.source if path.suffix.lower() != DATA_SUFFIX]
    if unknown:
        raise RuntimeError(
            f"not a downloaded INAB file (expected {DATA_SUFFIX}): "
            f"{', '.join(str(path) for path in unknown)}"
        )
    return sorted(args.source)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Import every file against ``engine``, returning the fires written."""
    files = find_files(args)
    years = set(args.years) if args.years else None

    common.require_tables(engine, ["wildfire", "ignition", "inab_wildfire",
                                   "inab_ignition", "admin_boundary",
                                   "data_provider"], logger)

    with Session(engine) as session:
        require_known_time_zone(session, logger)
        provider = common.get_or_create_data_provider(
            session, guatemala_inab.PROVIDER_NAME, guatemala_inab.PROVIDER_PRODUCT,
            guatemala_inab.PROVIDER_FULL_NAME, guatemala_inab.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    started = time.monotonic()
    outcome = RunOutcome()
    logger.info("%d file(s) to import", len(files))

    reports = read_files(files, logger)
    buckets = bucket_by_year(reports, years, outcome, logger)
    if not buckets:
        logger.warning("No storable fire report found in %d file(s)", len(files))
        return 0

    logger.info("%d year(s) to write: %s", len(buckets),
                ", ".join(str(year) for year in buckets))
    for year, bucket in buckets.items():
        import_year(year, bucket, engine, provider_id, boundary_provider_id,
                    outcome, args.dry_run, logger)

    logger.info(
        "Imported %d fire(s) over %d year(s) from %d file(s) in %.0fs: %d with a "
        "point, %d false alarm(s), %d unverified, %d skipped, %d duplicate(s), "
        "%d with problems, replacing %d stored fire(s)%s",
        outcome.written, len(outcome.years), len(files), time.monotonic() - started,
        outcome.located, outcome.false_alarms, outcome.unverified, outcome.skipped,
        outcome.duplicates, outcome.problems, outcome.deleted,
        " — ROLLED BACK, nothing was written (--dry-run)" if args.dry_run else "",
    )
    if outcome.outside_guatemala:
        logger.warning(
            "%d stored point(s) are outside Guatemala. They are the provider's data "
            "and are stored as published, not repaired; every one published today is "
            "already flagged %r.",
            outcome.outside_guatemala, guatemala_inab.STATUS_FALSE,
        )
    return outcome.written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("inab-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.source or []:
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        import_wildfires(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
