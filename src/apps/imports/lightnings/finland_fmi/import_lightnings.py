#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import FMI's lightning strokes from the downloader's monthly files.

One command over one or more monthly files, or over the directory holding
them::

    python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \\
        -s ~/data/fmi/fmi_lightning_2018-08.csv.gz

    python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \\
        -d ~/data/fmi --from-year 2018 --to-year 2019

The files are those of
:mod:`src.apps.download.lightnings.finland_fmi.download_lightnings`; the reader
(:mod:`src.apps.imports.lightnings.finland_fmi.readers`) checks and converts them,
and this module writes them. See :mod:`src.providers.finland_fmi` for the
dataset.

The unit is a UTC month
-----------------------

Nothing in a row identifies a stroke, so there is nothing to update in place:
each file's month is **replaced wholesale** — FMI's strokes of that month
deleted and the file's inserted, in one transaction — as the MeteoCat import
does with a year. Other months and other providers' strokes are not touched.

The sidecar
-----------

The downloader's ``.meta.json`` says how many strokes it wrote and whether the
month was complete. A file whose row count disagrees with its sidecar is
incomplete or altered: the month is **refused** and the run ends with an error
after importing the others. A month the sidecar calls incomplete is imported
with a warning — the next download completes it, and importing it again
replaces it. A file with no sidecar is imported with a warning, since nothing
then says it is whole.

Order, identifiers and flashes
------------------------------

The reader sorts each month's strokes by their values, because the service
returns the strokes of one second in no stable order; the identifiers are drawn
from ``lightning``'s sequence **in that order**. Importing a month downloaded
twice gives the same identifiers order, and so the same ties in the thunderstorm
algorithms.

``multiplicity`` and ``stroke_index`` are computed in the database before the
insert, per ``flash_id``: stroke 1 is the stroke FMI marks as first (published
``multiplicity`` not 0), then by instant, then by the month's order. A flash
lasts about a second, so one can straddle two months; the numbering therefore
also takes in the strokes **already stored** for the same flashes within
:data:`FLASH_MARGIN` of the month, and those few stored strokes are updated with
the new numbering. Whichever month is imported first, the flash ends up numbered
whole.

How it writes
-------------

A month is up to about a million strokes, so not through the ORM: the records
are streamed with ``COPY`` into a temporary table, numbered there, and one
``INSERT ... SELECT`` per table moves them across, drawing the identifiers,
building the ETRS89 point, reprojecting it to EPSG:4326 and resolving the
country: the OCHA level-0 boundary the point falls in, tested against the
boundaries subdivided into pieces of at most :data:`SUBDIVIDE_VERTICES`
vertices, as the MeteoCat import does. Strokes at sea get none; so does every
stroke when no boundaries are imported, which is warned about and does not stop
the import.

Thunderstorms built on the strokes
----------------------------------

As for MeteoCat (see :mod:`src.apps.imports.lightnings.common`): a month that
thunderstorm experiments depend on is **refused** — logged and skipped, the
other months imported, the run ending with an error — unless
``--drop-thunderstorms`` deletes those experiments, whole, in the month's
transaction. ``--dry-run --drop-thunderstorms`` connects only to list them.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument. ``--dry-run``
reads, checks and reports without connecting to a database at all, unless
``--drop-thunderstorms`` asks it to list the experiments a real run would drop.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time

from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.common import Spinner
from src.apps.imports.lightnings import common as lightning_common
from src.apps.imports.lightnings.common import PeriodInUse
from src.apps.imports.lightnings.finland_fmi import readers
from src.apps.imports.lightnings.finland_fmi.readers import MonthFile
from src.apps.imports.lightnings.finland_fmi.readers import StrokeRecord
from src.providers import finland_fmi

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: How many individually bad rows are logged per file before the rest are only
#: counted.
MAX_REPORTED_PROBLEMS = 20

#: How finely the boundaries are cut before the lookup, as for MeteoCat.
SUBDIVIDE_VERTICES = 256

#: Degrees added around a month's strokes when choosing the boundaries to cut.
EXTENT_MARGIN = 1.0

#: How far outside its month a straddling flash's stored strokes are looked for.
#: FMI's flashes last at most a second or so; this is generous.
FLASH_MARGIN = datetime.timedelta(minutes=1)

#: The staging table's columns, in the order each record is copied.
STAGING_COLUMNS = (
    "ordinal", "line", "date_time", "latitude", "longitude", "flash_id",
    "published_multiplicity", "peak_current", "cloud_to_ground", "number_of_sensors",
    "degrees_of_freedom", "ellipse_angle", "ellipse_major_axis", "ellipse_minor_axis",
    "chi_squared", "rise_time", "peak_to_zero_time", "angle_indicator", "signal_indicator",
    "timing_indicator", "stroke_status",
)

#: One month's records, as read. Temporary and dropped at commit.
CREATE_STAGING_SQL = """
CREATE TEMPORARY TABLE fmi_stroke_staging (
    ordinal integer PRIMARY KEY,
    line integer NOT NULL,
    date_time timestamptz NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    flash_id integer NOT NULL,
    published_multiplicity integer NOT NULL,
    peak_current double precision,
    cloud_to_ground boolean NOT NULL,
    number_of_sensors integer NOT NULL,
    degrees_of_freedom integer NOT NULL,
    ellipse_angle double precision NOT NULL,
    ellipse_major_axis double precision NOT NULL,
    ellipse_minor_axis double precision NOT NULL,
    chi_squared double precision NOT NULL,
    rise_time double precision NOT NULL,
    peak_to_zero_time double precision NOT NULL,
    angle_indicator smallint NOT NULL,
    signal_indicator smallint NOT NULL,
    timing_indicator smallint NOT NULL,
    stroke_status smallint NOT NULL
) ON COMMIT DROP
"""

COPY_SQL = f"COPY fmi_stroke_staging ({', '.join(STAGING_COLUMNS)}) FROM STDIN"

#: Deletes FMI's strokes of one month from both tables in one statement, so the
#: foreign key from ``fmi_lightning.id`` to ``lightning.id`` is checked once.
DELETE_MONTH_SQL = """
WITH removed AS (
    DELETE FROM fmi_lightning AS child
    USING lightning AS parent
    WHERE parent.id = child.id
      AND parent.data_provider_id = :provider_id
      AND parent.date_time >= :start AND parent.date_time < :end
    RETURNING child.id
)
DELETE FROM lightning WHERE id IN (SELECT id FROM removed)
"""

#: Numbers every flash of the month, over the staged strokes and the stored
#: strokes of the same flashes just outside the month. A row is either staged
#: (``ordinal``) or stored (``id``); the two never tie on ``date_time``, since a
#: second belongs to one month.
CREATE_NUMBERING_SQL = """
CREATE TEMPORARY TABLE fmi_flash_numbering ON COMMIT DROP AS
WITH everything AS (
    SELECT staged.ordinal, NULL::integer AS id, staged.flash_id, staged.date_time,
           staged.published_multiplicity
    FROM fmi_stroke_staging AS staged
    UNION ALL
    SELECT NULL::integer, stored.id, stored.flash_id, parent.date_time,
           stored.published_multiplicity
    FROM fmi_lightning AS stored
    JOIN lightning AS parent ON parent.id = stored.id
    WHERE parent.data_provider_id = :provider_id
      AND ((parent.date_time >= :before AND parent.date_time < :start)
           OR (parent.date_time >= :end AND parent.date_time < :after))
      AND stored.flash_id IN (SELECT flash_id FROM fmi_stroke_staging)
)
SELECT ordinal, id,
       CAST(count(*) OVER (PARTITION BY flash_id) AS integer) AS multiplicity,
       CAST(row_number() OVER (PARTITION BY flash_id
                               ORDER BY published_multiplicity > 0 DESC, date_time,
                                        ordinal NULLS LAST, id NULLS LAST) AS integer)
           AS stroke_index
FROM everything
"""

#: The countries the month's strokes could fall in, cut into small pieces. With no
#: boundary provider ``:boundary_provider_id`` is NULL and the table is empty.
CREATE_PARTS_SQL = f"""
CREATE TEMPORARY TABLE fmi_boundary_parts ON COMMIT DROP AS
SELECT boundary.id AS admin_boundary_id,
       ST_Subdivide(boundary.geometry, {SUBDIVIDE_VERTICES}) AS geometry
FROM admin_boundary AS boundary
WHERE boundary.level = 0
  AND boundary.data_provider_id = :boundary_provider_id
  AND boundary.geometry && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
"""

CREATE_PARTS_INDEX_SQL = "CREATE INDEX ON fmi_boundary_parts USING gist (geometry)"

#: Temporary tables have no statistics until analysed.
ANALYZE_SQL = "ANALYZE fmi_stroke_staging; ANALYZE fmi_flash_numbering; ANALYZE fmi_boundary_parts"

#: Moves the staged month into both tables, the identifiers drawn in the month's
#: content order — the ordered subquery is not flattened, so ``nextval`` runs over
#: its rows in that order. A point on the seam between two pieces of one country
#: intersects both, and one on a border two countries; ``ORDER BY`` makes the
#: choice deterministic.
INSERT_SQL = """
WITH numbered AS MATERIALIZED (
    SELECT CAST(nextval(pg_get_serial_sequence('lightning', 'id')) AS integer) AS id,
           ordered.*,
           ST_SetSRID(ST_MakePoint(ordered.longitude, ordered.latitude), 4258) AS point_etrs89
    FROM (SELECT staged.*, flash.multiplicity, flash.stroke_index
          FROM fmi_stroke_staging AS staged
          JOIN fmi_flash_numbering AS flash ON flash.ordinal = staged.ordinal
          ORDER BY staged.ordinal) AS ordered
),
located AS MATERIALIZED (
    SELECT numbered.*, ST_Transform(numbered.point_etrs89, 4326) AS point_4326
    FROM numbered
),
bounded AS MATERIALIZED (
    SELECT located.*, country.admin_boundary_id
    FROM located
    LEFT JOIN LATERAL (
        SELECT part.admin_boundary_id
        FROM fmi_boundary_parts AS part
        WHERE ST_Intersects(part.geometry, located.point_4326)
        ORDER BY part.admin_boundary_id
        LIMIT 1
    ) AS country ON TRUE
),
parents AS (
    INSERT INTO lightning (id, type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground, admin_boundary_id)
    SELECT bounded.id, 'fmi_lightning', :provider_id, bounded.date_time,
           bounded.point_4326, bounded.peak_current, bounded.cloud_to_ground,
           bounded.admin_boundary_id
    FROM bounded
    RETURNING id
)
INSERT INTO fmi_lightning (id, flash_id, multiplicity, stroke_index, published_multiplicity,
                           number_of_sensors, degrees_of_freedom, chi_squared,
                           ellipse_major_axis, ellipse_minor_axis, ellipse_angle, rise_time,
                           peak_to_zero_time, stroke_status, angle_indicator,
                           signal_indicator, timing_indicator, geometry_etrs89)
SELECT bounded.id, bounded.flash_id, bounded.multiplicity, bounded.stroke_index,
       bounded.published_multiplicity, bounded.number_of_sensors,
       bounded.degrees_of_freedom, bounded.chi_squared, bounded.ellipse_major_axis,
       bounded.ellipse_minor_axis, bounded.ellipse_angle, bounded.rise_time,
       bounded.peak_to_zero_time, bounded.stroke_status, bounded.angle_indicator,
       bounded.signal_indicator, bounded.timing_indicator, bounded.point_etrs89
FROM bounded
JOIN parents ON parents.id = bounded.id
"""

#: Brings the stored strokes of the straddling flashes up to date.
RENUMBER_STORED_SQL = """
UPDATE fmi_lightning AS stored
SET multiplicity = flash.multiplicity, stroke_index = flash.stroke_index
FROM fmi_flash_numbering AS flash
WHERE flash.id = stored.id
  AND (stored.multiplicity, stored.stroke_index)
      IS DISTINCT FROM (flash.multiplicity, flash.stroke_index)
"""

#: How many flashes the month's strokes start: the strokes numbered first.
FIRST_STROKES_SQL = """
SELECT count(*) FROM fmi_flash_numbering WHERE ordinal IS NOT NULL AND stroke_index = 1
"""

#: How many of a month's strokes found no country, once written.
WITHOUT_BOUNDARY_SQL = """
SELECT count(*) FROM lightning
WHERE data_provider_id = :provider_id
  AND date_time >= :start AND date_time < :end
  AND admin_boundary_id IS NULL
"""


# --------------------------------------------------------------------------
# What a month did
# --------------------------------------------------------------------------

class MonthOutcome:
    """What one month did, for the summary."""

    def __init__(self, label: str, name: str) -> None:
        self.label = label
        self.name = name
        self.written = 0
        self.deleted = 0
        #: Flashes started in the month (after a real import) or flash ids in the
        #: file (in a dry run, which numbers nothing).
        self.flashes = 0
        self.renumbered = 0
        self.without_boundary: int | None = None
        #: The thunderstorm experiments dropped (or, in a dry run, that would be).
        self.dropped = 0
        #: Why the month was not imported, if it was not.
        self.refused: str | None = None

    def describe(self) -> str:
        if self.refused is not None:
            return f"{self.label}: not imported ({self.refused})"
        boundary = ("" if self.without_boundary is None
                    else f", {self.without_boundary} with no country")
        renumbered = (f", {self.renumbered} stroke(s) of the neighbouring months renumbered"
                      if self.renumbered else "")
        return f"{self.label}: {self.written} stroke(s) in {self.flashes} flash(es){boundary}{renumbered}"


def month_range(content: MonthFile) -> dict[str, datetime.datetime]:
    """The month as the half-open range the statements bind."""
    return {"start": content.start, "end": content.end}


def extent(records: list[StrokeRecord]) -> dict[str, float]:
    """The box the strokes cover, with :data:`EXTENT_MARGIN` around it."""
    xs = [record.longitude for record in records]
    ys = [record.latitude for record in records]
    return {"xmin": max(min(xs) - EXTENT_MARGIN, -180.0), "ymin": max(min(ys) - EXTENT_MARGIN, -90.0),
            "xmax": min(max(xs) + EXTENT_MARGIN, 180.0), "ymax": min(max(ys) + EXTENT_MARGIN, 90.0)}


# --------------------------------------------------------------------------
# Writing a month
# --------------------------------------------------------------------------

def stage(connection: Connection, records: list[StrokeRecord]) -> None:
    """``COPY`` the records into the staging table, in the open transaction."""
    connection.execute(text(CREATE_STAGING_SQL))
    raw = connection.connection.driver_connection
    with raw.cursor() as cursor, cursor.copy(COPY_SQL) as copy:
        for record in records:
            copy.write_row((
                record.ordinal, record.line, record.date_time, record.latitude,
                record.longitude, record.flash_id, record.published_multiplicity,
                record.peak_current, record.cloud_to_ground, record.number_of_sensors,
                record.degrees_of_freedom, record.ellipse_angle, record.ellipse_major_axis,
                record.ellipse_minor_axis, record.chi_squared, record.rise_time,
                record.peak_to_zero_time, record.angle_indicator, record.signal_indicator,
                record.timing_indicator, record.stroke_status,
            ))


def import_month(connection: Connection, content: MonthFile, provider_id: int,
                 boundary_provider_id: int | None, log: logging.LoggerAdapter,
                 drop: bool = False) -> MonthOutcome:
    """Replace one UTC month with its records, in one transaction.

    The thunderstorm experiments depending on the month are dropped first when
    ``drop`` is set, in the same transaction.

    Raises
    ------
    PeriodInUse
        If experiments depend on the month and ``drop`` is not set — or if one
        holding its strokes was missed and ``RESTRICT`` refused the delete. The
        transaction is rolled back either way: nothing of the month changes.
    """
    outcome = MonthOutcome(content.label, content.name)
    bounds = month_range(content)
    try:
        with connection.begin():
            covering = lightning_common.covering_experiments(connection, provider_id, **bounds)
            if covering and not drop:
                for experiment in covering:
                    log.warning("%s is used by thunderstorm experiment %s", content.label,
                                experiment.describe())
                raise PeriodInUse(content.label, [experiment.id for experiment in covering])
            outcome.dropped = lightning_common.drop_experiments(connection, covering, log)
            _replace_month(connection, content, provider_id, boundary_provider_id, bounds,
                           outcome, log)
    except IntegrityError as error:
        if "thunderstorm_lightning" not in str(error.orig):
            raise
        with connection.begin():
            holding = lightning_common.holding_experiments(connection, provider_id, **bounds)
        ids = ", ".join(str(identifier) for identifier in holding)
        raise PeriodInUse(content.label, holding, (
            f"{content.label} not replaced: its strokes are in thunderstorms of experiment(s) "
            f"{ids}, which the check for dependent experiments did not find; nothing was "
            f"deleted"
        )) from error
    outcome.written = len(content.records)
    return outcome


def _replace_month(connection: Connection, content: MonthFile, provider_id: int,
                   boundary_provider_id: int | None, bounds: dict[str, datetime.datetime],
                   outcome: MonthOutcome, log: logging.LoggerAdapter) -> None:
    """Delete the stored month and write its records, in the open transaction."""
    outcome.deleted = connection.execute(
        text(DELETE_MONTH_SQL), {"provider_id": provider_id, **bounds}).rowcount
    if outcome.deleted:
        log.info("Replacing %d stroke(s) already stored for %s", outcome.deleted, content.label)
    if not content.records:
        return
    stage(connection, content.records)
    connection.execute(text(CREATE_NUMBERING_SQL), {
        "provider_id": provider_id, **bounds,
        "before": bounds["start"] - FLASH_MARGIN, "after": bounds["end"] + FLASH_MARGIN})
    connection.execute(text(CREATE_PARTS_SQL),
                       {"boundary_provider_id": boundary_provider_id, **extent(content.records)})
    connection.execute(text(CREATE_PARTS_INDEX_SQL))
    connection.execute(text(ANALYZE_SQL))
    with Spinner(f"{content.name}: writing {len(content.records):,} stroke(s)", log.logger):
        connection.execute(text(INSERT_SQL), {"provider_id": provider_id})
    outcome.renumbered = connection.execute(text(RENUMBER_STORED_SQL)).rowcount
    if outcome.renumbered:
        log.info("%d stored stroke(s) of flashes straddling %s renumbered", outcome.renumbered,
                 content.label)
    outcome.flashes = connection.execute(text(FIRST_STROKES_SQL)).scalar()
    outcome.without_boundary = connection.execute(
        text(WITHOUT_BOUNDARY_SQL), {"provider_id": provider_id, **bounds}).scalar()


# --------------------------------------------------------------------------
# Importing one file
# --------------------------------------------------------------------------

def report_problems(content: MonthFile, log: logging.LoggerAdapter) -> None:
    """Log the refused rows of a file, the first few one by one."""
    for index, (line, reason) in enumerate(content.problems):
        if index == MAX_REPORTED_PROBLEMS:
            log.warning("Further refused rows in this file are counted, not logged")
            break
        log.warning("Line %d skipped: %s", line, reason)
    if content.problems:
        log.warning("%d row(s) refused", len(content.problems))


def sidecar_problem(content: MonthFile, log: logging.LoggerAdapter) -> str | None:
    """Why the sidecar says the file cannot be imported, or ``None``.

    A missing sidecar, or one calling the month incomplete, is only warned about.
    """
    sidecar = content.sidecar
    if sidecar is None:
        log.warning("No sidecar: nothing says this file is whole")
        return None
    if sidecar.get("month") != content.label:
        return f"its sidecar is for {sidecar.get('month')!r}"
    if sidecar.get("strokes") != content.rows:
        return (f"the file holds {content.rows} row(s) and its sidecar says "
                f"{sidecar.get('strokes')}: it is incomplete or altered; download the month "
                f"again")
    if sidecar.get("complete") is not True:
        log.warning("The sidecar says %s was not complete when downloaded; download it again "
                    "and import it once more to complete it", content.label)
    return None


def import_file(path: Path, engine: Engine | None, provider_id: int | None,
                boundary_provider_id: int | None, logger: logging.Logger, drop: bool = False,
                lookup: Engine | None = None) -> MonthOutcome:
    """Read one monthly file and import its month.

    With no ``engine`` nothing is written: the outcome is what an import would
    write, for ``--dry-run``; with a ``lookup`` engine as well, the thunderstorm
    experiments a real run would drop are listed from it. A month that the
    sidecar or experiments stop is logged and returned refused.
    """
    log = ArchiveLogger(logger, {"archive": path.name})
    with Spinner(f"{path.name}: reading", logger):
        content = readers.read_month(path)
    log.info("%d stroke(s) read", len(content.records))
    report_problems(content, log)

    refusal = sidecar_problem(content, log)
    if refusal is not None:
        log.error("%s not imported: %s", content.label, refusal)
        outcome = MonthOutcome(content.label, content.name)
        outcome.refused = refusal
        return outcome

    if engine is None:
        outcome = MonthOutcome(content.label, content.name)
        outcome.written = len(content.records)
        outcome.flashes = len({record.flash_id for record in content.records})
        if lookup is not None and provider_id is not None:
            with lookup.connect() as connection:
                covering = lightning_common.covering_experiments(
                    connection, provider_id, **month_range(content))
            for experiment in covering:
                log.info("Would drop thunderstorm experiment %s", experiment.describe())
            outcome.dropped = len(covering)
    else:
        with engine.connect() as connection:
            try:
                outcome = import_month(connection, content, provider_id, boundary_provider_id,
                                       log, drop)
            except PeriodInUse as error:
                log.error("%s", error)
                outcome = MonthOutcome(content.label, content.name)
                outcome.refused = (f"thunderstorm experiment(s) "
                                   f"{', '.join(map(str, error.experiment_ids))} depend on it")
    log.info("%s", outcome.describe())
    return outcome


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Finnish Meteorological Institute's lightning strokes from "
                    "the monthly files of the FMI downloader.",
        epilog="Each file's UTC month is replaced wholesale, so importing a file again "
               "revises its month and leaves the others alone. Database settings not "
               "given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help=f"directory holding the monthly files; every "
                             f"{finland_fmi.FILE_STEM}_YYYY-MM.csv.gz is imported, in month "
                             f"order")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more monthly files to import")

    parser.add_argument("--from-year", type=int, metavar="YEAR",
                        help="import only the months of this year and later")
    parser.add_argument("--to-year", type=int, metavar="YEAR",
                        help="import only the months of this year and earlier")
    parser.add_argument("--dry-run", action="store_true",
                        help="read, check and report without touching the database")
    parser.add_argument(lightning_common.DROP_FLAG, action="store_true",
                        dest="drop_thunderstorms",
                        help="delete, whole, the thunderstorm experiments that depend on a "
                             "month before replacing it; without it such a month is refused. "
                             "With --dry-run, connect only to list them")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    arguments = parser.parse_args(argv)
    if (arguments.from_year is not None and arguments.to_year is not None
            and arguments.to_year < arguments.from_year):
        parser.error("--to-year cannot be before --from-year")
    return arguments


def in_years(path: Path, args: argparse.Namespace) -> bool:
    """Whether a monthly file's year is within ``--from-year``/``--to-year``."""
    year, _ = readers.month_of(path)
    return ((args.from_year is None or year >= args.from_year)
            and (args.to_year is None or year <= args.to_year))


def find_files(args: argparse.Namespace, logger: logging.Logger) -> list[Path]:
    """The monthly files to import, checked by name and header before any is read.

    Raises
    ------
    RuntimeError
        If no file is left to import, or a file named with ``--source`` is not a
        monthly file.
    """
    if args.directory is not None:
        paths = []
        for path in sorted(args.directory.glob(f"{finland_fmi.FILE_STEM}_*.csv.gz")):
            reason = readers.header_problem(path)
            if reason is None:
                paths.append(path)
            else:
                logger.warning("Skipping %s: %s", path.name, reason)
        if not paths:
            raise RuntimeError(f"{args.directory} holds no monthly file of the FMI downloader")
    else:
        for path in args.source:
            reason = readers.header_problem(path)
            if reason is not None:
                raise RuntimeError(f"{path}: {reason}")
        paths = sorted(set(args.source), key=lambda path: readers.month_of(path))

    selected = [path for path in paths if in_years(path, args)]
    if not selected:
        raise RuntimeError("no monthly file in the years asked for")
    return selected


#: The tables a run reads or writes.
TABLES = ["lightning", "fmi_lightning", "data_provider", "admin_boundary",
          "thunderstorm_experiment", "thunderstorm", "thunderstorm_lightning",
          "thunderstorm_tracking"]

#: FMI's row, for a dry run, which creates nothing.
PROVIDER_ID_SQL = "SELECT id FROM data_provider WHERE name = :name AND product = :product"


def import_lightnings(args: argparse.Namespace, engine: Engine | None,
                      logger: logging.Logger, lookup: Engine | None = None) -> int:
    """Import every monthly file against ``engine``, returning the strokes written.

    With no ``engine`` this is a dry run, which reads ``lookup``, if given, to list
    the thunderstorm experiments a real run would drop.

    Raises
    ------
    RuntimeError
        After importing every other month, if any month was refused.
    """
    paths = find_files(args, logger)
    drop = getattr(args, "drop_thunderstorms", False)

    provider_id = None
    boundary_provider_id = None
    if engine is None and lookup is not None:
        common.require_tables(lookup, TABLES, logger)
        with lookup.connect() as connection:
            provider_id = connection.execute(text(PROVIDER_ID_SQL), {
                "name": finland_fmi.PROVIDER_NAME,
                "product": finland_fmi.PROVIDER_PRODUCT}).scalar()
    if engine is not None:
        common.require_tables(engine, TABLES, logger)
        with Session(engine) as session:
            provider = common.get_or_create_data_provider(
                session, finland_fmi.PROVIDER_NAME, finland_fmi.PROVIDER_PRODUCT,
                finland_fmi.PROVIDER_FULL_NAME, finland_fmi.PROVIDER_URL, logger,
            )
            # The description, which the shared helper has no argument for.
            provider.description = finland_fmi.PROVIDER_DESCRIPTION
            boundary_provider = common.find_boundary_provider(session, logger)
            session.commit()
            provider_id = provider.id
            boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    started = time.monotonic()
    outcomes: list[MonthOutcome] = []
    for index, path in enumerate(paths, start=1):
        logger.info("[%d/%d] %s", index, len(paths), path.name)
        outcomes.append(import_file(path, engine, provider_id, boundary_provider_id, logger,
                                    drop, lookup))

    refused = [outcome for outcome in outcomes if outcome.refused is not None]
    imported = [outcome for outcome in outcomes if outcome.refused is None]
    written = sum(outcome.written for outcome in imported)
    logger.info("%s %d stroke(s) in %d flash(es) over %d month(s) in %.0fs",
                "Would import" if engine is None else "Imported", written,
                sum(outcome.flashes for outcome in imported), len(imported),
                time.monotonic() - started)
    dropped = sum(outcome.dropped for outcome in imported)
    if dropped:
        logger.info("%s %d thunderstorm experiment(s)",
                    "Would have dropped" if engine is None else "Also dropped", dropped)
    if refused:
        raise RuntimeError(
            f"{len(refused)} month(s) not imported: "
            + "; ".join(f"{outcome.label} ({outcome.refused})" for outcome in refused)
            + (f". For thunderstorm experiments, delete them first or run again with "
               f"{lightning_common.DROP_FLAG}"
               if any("experiment" in outcome.refused for outcome in refused) else ""))
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("fmi-lightning-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.source or []:
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    if args.dry_run:
        lookup = None
        try:
            if args.drop_thunderstorms:
                lookup = create_engine(common.database_url(common.resolve_database_settings(args)))
            import_lightnings(args, None, logger, lookup)
        except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
            logger.error("Check failed: %s", error)
            return 1
        finally:
            if lookup is not None:
                lookup.dispose()
        return 0

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        import_lightnings(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
