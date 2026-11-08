#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import MeteoCat's XDDE lightning strokes from the yearly CSV extracts.

One command over one or more extracts, or over the directory holding them::

    python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \\
        -s /path/to/DATMET-12706_cg_cm_2014.csv

    python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \\
        -d /path/to/meteocat/

The reader (:mod:`src.apps.imports.lightnings.catalonia_meteocat.readers`) turns a
file into records — parsed, checked, "not recorded" made ``NULL`` and every flash
numbered; this module writes them.

The unit is a UTC year
----------------------

Nothing in a row identifies a stroke (see :mod:`src.providers.catalonia_meteocat`),
so there is nothing to update in place: each UTC year found in a file is **replaced
wholesale** — MeteoCat's strokes of that year deleted and the file's inserted, in
one transaction — as the KFS and Greek imports do with theirs. The delivery is one
file per UTC year, so importing a file replaces exactly what it holds. Years not in
the file are not touched, and nor are other providers' strokes. A future API import
writes to the same tables: re-importing a year from a CSV replaces whatever the API
stored for it.

The flash numbering is the reader's, done over the whole file before it is split
into years, so ``multiplicity`` and ``stroke_index`` never depend on the year
filter.

How it writes
-------------

About 6.2 million strokes over 2006-2020, up to 860,000 in a year, rule out the
ORM. Each year's records are streamed with ``COPY`` into a temporary table, and one
``INSERT ... SELECT`` per table moves them across: drawing the identifiers from
``lightning``'s sequence, building the ETRS89 point, reprojecting it to EPSG:4326
and resolving the country.

The country is the OCHA level-0 boundary the EPSG:4326 point falls in, as for every
other dataset, tested against the boundaries **subdivided** into pieces of at most
:data:`SUBDIVIDE_VERTICES` vertices: a whole country polygon is hundreds of
thousands of vertices, and testing six million points against it would take days.
Strokes at sea, most of them, get none; so does every stroke when no boundaries are
imported, which is warned about and does not stop the import.

What is refused
---------------

A row is refused — logged with its line number, counted and skipped — when it is
not a reading of the format or would break a constraint of ``meteocat_lightning``.
No row of the 2006-2020 delivery is. A file whose header is not the extract header
stops the run before anything is written when named with ``--source``, and is
skipped with a warning in a ``--directory``.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument. ``--dry-run``
reads, checks and reports without connecting to a database at all.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from collections import Counter
from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.common import Spinner
from src.apps.imports.lightnings.catalonia_meteocat import readers
from src.apps.imports.lightnings.catalonia_meteocat.readers import Extract
from src.apps.imports.lightnings.catalonia_meteocat.readers import StrokeRecord
from src.providers import catalonia_meteocat

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: How many individually bad rows are logged per file before the rest are only
#: counted.
MAX_REPORTED_PROBLEMS = 20

#: How finely the boundaries are cut before the lookup: the CSIRO and CONAF
#: imports' number, from the PostGIS recipe.
SUBDIVIDE_VERTICES = 256

#: Degrees added around a year's strokes when choosing the boundaries to cut.
EXTENT_MARGIN = 1.0

#: The staging table's columns, in the order each record is copied.
STAGING_COLUMNS = (
    "source_row", "flash_id", "date_time", "peak_current", "chi_squared",
    "ellipse_major_axis", "ellipse_minor_axis", "number_of_sensors", "cloud_to_ground",
    "municipality_code", "longitude", "latitude", "network_version", "multiplicity",
    "stroke_index",
)

#: One year's records, as read. Temporary and dropped at commit: it lives only for
#: the transaction that replaces the year.
CREATE_STAGING_SQL = """
CREATE TEMPORARY TABLE meteocat_stroke_staging (
    source_row integer NOT NULL,
    flash_id integer NOT NULL,
    date_time timestamptz NOT NULL,
    peak_current double precision NOT NULL,
    chi_squared double precision,
    ellipse_major_axis double precision NOT NULL,
    ellipse_minor_axis double precision NOT NULL,
    number_of_sensors integer,
    cloud_to_ground boolean NOT NULL,
    municipality_code text,
    longitude double precision NOT NULL,
    latitude double precision NOT NULL,
    network_version integer NOT NULL,
    multiplicity integer NOT NULL,
    stroke_index integer NOT NULL
) ON COMMIT DROP
"""

COPY_SQL = f"COPY meteocat_stroke_staging ({', '.join(STAGING_COLUMNS)}) FROM STDIN"

#: The countries the year's strokes could fall in, cut into small pieces. With no
#: boundary provider ``:boundary_provider_id`` is NULL and the table is empty, so
#: the insert below is the same statement either way.
CREATE_PARTS_SQL = f"""
CREATE TEMPORARY TABLE meteocat_boundary_parts ON COMMIT DROP AS
SELECT boundary.id AS admin_boundary_id,
       ST_Subdivide(boundary.geometry, {SUBDIVIDE_VERTICES}) AS geometry
FROM admin_boundary AS boundary
WHERE boundary.level = 0
  AND boundary.data_provider_id = :boundary_provider_id
  AND boundary.geometry && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
"""

CREATE_PARTS_INDEX_SQL = "CREATE INDEX ON meteocat_boundary_parts USING gist (geometry)"

#: Temporary tables have no statistics until analysed, and a planner that thinks
#: the staging table is empty picks a plan for an empty table.
ANALYZE_SQL = "ANALYZE meteocat_stroke_staging; ANALYZE meteocat_boundary_parts"

#: Deletes MeteoCat's strokes of one UTC year from both tables in one statement, so
#: the foreign key from ``meteocat_lightning.id`` to ``lightning.id`` is checked
#: once, at the end.
DELETE_YEAR_SQL = """
WITH removed AS (
    DELETE FROM meteocat_lightning AS child
    USING lightning AS parent
    WHERE parent.id = child.id
      AND parent.data_provider_id = :provider_id
      AND parent.date_time >= :start AND parent.date_time < :end
    RETURNING child.id
)
DELETE FROM lightning WHERE id IN (SELECT id FROM removed)
"""

#: Moves the staged year into both tables. A point on the seam between two pieces
#: of one country intersects both, and one on a border two countries; ``ORDER BY``
#: makes the choice deterministic.
INSERT_SQL = """
WITH numbered AS MATERIALIZED (
    SELECT CAST(nextval(pg_get_serial_sequence('lightning', 'id')) AS integer) AS id,
           staged.*,
           ST_SetSRID(ST_MakePoint(staged.longitude, staged.latitude), 4258) AS point_etrs89
    FROM meteocat_stroke_staging AS staged
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
        FROM meteocat_boundary_parts AS part
        WHERE ST_Intersects(part.geometry, located.point_4326)
        ORDER BY part.admin_boundary_id
        LIMIT 1
    ) AS country ON TRUE
),
parents AS (
    INSERT INTO lightning (id, type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground, admin_boundary_id)
    SELECT bounded.id, 'meteocat_lightning', :provider_id, bounded.date_time,
           bounded.point_4326, bounded.peak_current, bounded.cloud_to_ground,
           bounded.admin_boundary_id
    FROM bounded
    RETURNING id
)
INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, stroke_index,
                                chi_squared, ellipse_major_axis, ellipse_minor_axis,
                                ellipse_angle, number_of_sensors, municipality_code,
                                geometry_etrs89)
SELECT bounded.id, bounded.network_version, bounded.flash_id, bounded.multiplicity,
       bounded.stroke_index, bounded.chi_squared, bounded.ellipse_major_axis,
       bounded.ellipse_minor_axis, NULL, bounded.number_of_sensors,
       bounded.municipality_code, bounded.point_etrs89
FROM bounded
JOIN parents ON parents.id = bounded.id
"""

#: How many of a year's strokes found no country, once written.
WITHOUT_BOUNDARY_SQL = """
SELECT count(*) FROM lightning
WHERE data_provider_id = :provider_id
  AND date_time >= :start AND date_time < :end
  AND admin_boundary_id IS NULL
"""


# --------------------------------------------------------------------------
# What a year did
# --------------------------------------------------------------------------

class YearOutcome:
    """What one year did, for the summary."""

    def __init__(self, year: int, name: str) -> None:
        self.year = year
        self.name = name
        self.written = 0
        self.deleted = 0
        self.flashes = 0
        self.without_boundary: int | None = None
        self.versions: Counter[int] = Counter()

    def count(self, records: list[StrokeRecord]) -> None:
        """Count the records written (or, in a dry run, that would be)."""
        self.written += len(records)
        self.flashes += sum(record.stroke_index == 1 for record in records)
        self.versions.update(record.network_version for record in records)

    def describe(self) -> str:
        versions = ", ".join(f"version {version}: {count}"
                             for version, count in sorted(self.versions.items()))
        boundary = ("" if self.without_boundary is None
                    else f", {self.without_boundary} with no country")
        return (f"{self.year}: {self.written} stroke(s) in {self.flashes} flash(es) "
                f"({versions}){boundary}")


def year_range(year: int) -> dict[str, str]:
    """The UTC year as the half-open range the statements bind."""
    return {"start": f"{year}-01-01T00:00:00Z", "end": f"{year + 1}-01-01T00:00:00Z"}


def extent(records: list[StrokeRecord]) -> dict[str, float]:
    """The box the strokes cover, with :data:`EXTENT_MARGIN` around it."""
    xs = [record.longitude for record in records]
    ys = [record.latitude for record in records]
    return {"xmin": max(min(xs) - EXTENT_MARGIN, -180.0), "ymin": max(min(ys) - EXTENT_MARGIN, -90.0),
            "xmax": min(max(xs) + EXTENT_MARGIN, 180.0), "ymax": min(max(ys) + EXTENT_MARGIN, 90.0)}


# --------------------------------------------------------------------------
# Writing a year
# --------------------------------------------------------------------------

def stage(connection: Connection, records: list[StrokeRecord]) -> None:
    """``COPY`` the records into the staging table, in the open transaction."""
    connection.execute(text(CREATE_STAGING_SQL))
    raw = connection.connection.driver_connection
    with raw.cursor() as cursor, cursor.copy(COPY_SQL) as copy:
        for record in records:
            copy.write_row((
                record.row, record.flash_id, record.date_time, record.peak_current,
                record.chi_squared, record.ellipse_major_axis, record.ellipse_minor_axis,
                record.number_of_sensors, record.cloud_to_ground, record.municipality_code,
                record.longitude, record.latitude, record.network_version,
                record.multiplicity, record.stroke_index,
            ))


def import_year(connection: Connection, year: int, records: list[StrokeRecord], name: str,
                provider_id: int, boundary_provider_id: int | None,
                log: logging.LoggerAdapter) -> YearOutcome:
    """Replace one UTC year with its records, in one transaction."""
    outcome = YearOutcome(year, name)
    bounds = year_range(year)
    with connection.begin():
        outcome.deleted = connection.execute(
            text(DELETE_YEAR_SQL), {"provider_id": provider_id, **bounds}).rowcount
        if outcome.deleted:
            log.info("Replacing %d stroke(s) already stored for %d", outcome.deleted, year)
        stage(connection, records)
        connection.execute(text(CREATE_PARTS_SQL),
                           {"boundary_provider_id": boundary_provider_id, **extent(records)})
        connection.execute(text(CREATE_PARTS_INDEX_SQL))
        connection.execute(text(ANALYZE_SQL))
        with Spinner(f"{name}: writing {len(records):,} stroke(s) of {year}", log.logger):
            connection.execute(text(INSERT_SQL), {"provider_id": provider_id})
        outcome.without_boundary = connection.execute(
            text(WITHOUT_BOUNDARY_SQL), {"provider_id": provider_id, **bounds}).scalar()
    outcome.count(records)
    return outcome


# --------------------------------------------------------------------------
# Importing one extract
# --------------------------------------------------------------------------

def report_problems(extract: Extract, log: logging.LoggerAdapter) -> None:
    """Log the refused rows of an extract, the first few one by one."""
    for index, (line, reason) in enumerate(extract.problems):
        if index == MAX_REPORTED_PROBLEMS:
            log.warning("Further refused rows in this file are counted, not logged")
            break
        log.warning("Line %d skipped: %s", line, reason)
    if extract.problems:
        log.warning("%d row(s) refused", len(extract.problems))


def import_extract(path: Path, engine: Engine | None, provider_id: int | None,
                   boundary_provider_id: int | None, years: set[int] | None,
                   logger: logging.Logger) -> list[YearOutcome]:
    """Read one extract and import each of its years.

    With no ``engine`` nothing is written: the outcomes are what an import would
    write, for ``--dry-run``.
    """
    log = ArchiveLogger(logger, {"archive": path.name})
    with Spinner(f"{path.name}: reading", logger):
        extract = readers.read_extract(path)
    log.info("%d stroke(s) read", len(extract.records))
    report_problems(extract, log)

    outcomes = []
    grouped = readers.by_year(extract.records)
    if engine is None:
        for year, records in grouped.items():
            if years is not None and year not in years:
                continue
            outcome = YearOutcome(year, extract.name)
            outcome.count(records)
            outcomes.append(outcome)
            log.info("%s", outcome.describe())
    else:
        with engine.connect() as connection:
            for year, records in grouped.items():
                if years is not None and year not in years:
                    continue
                outcome = import_year(connection, year, records, extract.name, provider_id,
                                      boundary_provider_id, log)
                outcomes.append(outcome)
                log.info("%s", outcome.describe())
    if not outcomes:
        log.warning("No strokes to import in this file")
    return outcomes


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the lightning strokes of MeteoCat's XDDE network from its "
                    "yearly CSV extracts.",
        epilog="Each UTC year found is replaced wholesale, so importing a file again "
               "revises the year it holds and leaves the others alone. Database "
               "settings not given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the extracts; every .csv with the "
                             "extract header is imported, others are skipped")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more extract files to import")

    parser.add_argument("-y", "--year", type=int, nargs="+", dest="years",
                        help="import only these UTC years")
    parser.add_argument("--dry-run", action="store_true",
                        help="read, check and report without touching the database")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def is_extract(path: Path) -> str | None:
    """Why ``path`` is not an extract, or ``None`` if its header says it is."""
    try:
        with path.open(newline="", encoding="ascii", errors="replace") as handle:
            header = handle.readline().strip()
    except OSError as error:
        return str(error)
    names = tuple(name.strip().strip('"') for name in header.split(";"))
    if names != catalonia_meteocat.COLUMNS:
        return "not an XDDE extract (unexpected header)"
    return None


def find_extracts(args: argparse.Namespace, logger: logging.Logger) -> list[Path]:
    """The extracts named on the command line, checked by header before any is read.

    Checking every header first is what lets a bad file named with ``--source``
    stop the run before anything is written, without reading half a gigabyte up
    front.

    Raises
    ------
    RuntimeError
        If no extract was found, or a named file is not one.
    """
    if args.directory is not None:
        paths = []
        for path in sorted(args.directory.glob("*.csv")):
            reason = is_extract(path)
            if reason is None:
                paths.append(path)
            else:
                logger.warning("Skipping %s: %s", path.name, reason)
        if not paths:
            raise RuntimeError(f"{args.directory} holds no XDDE extract")
        return paths

    for path in args.source:
        reason = is_extract(path)
        if reason is not None:
            raise RuntimeError(f"{path}: {reason}")
    return sorted(args.source)


def import_lightnings(args: argparse.Namespace, engine: Engine | None,
                      logger: logging.Logger) -> int:
    """Import every extract against ``engine``, returning the strokes written.

    With no ``engine`` this is a dry run.
    """
    paths = find_extracts(args, logger)
    years = set(args.years) if args.years else None

    provider_id = None
    boundary_provider_id = None
    if engine is not None:
        common.require_tables(engine, ["lightning", "meteocat_lightning", "data_provider",
                                       "admin_boundary"], logger)
        with Session(engine) as session:
            provider = common.get_or_create_data_provider(
                session, catalonia_meteocat.PROVIDER_NAME, catalonia_meteocat.PROVIDER_PRODUCT,
                catalonia_meteocat.PROVIDER_FULL_NAME, catalonia_meteocat.PROVIDER_URL, logger,
            )
            # The description, which the shared helper has no argument for.
            provider.description = catalonia_meteocat.PROVIDER_DESCRIPTION
            boundary_provider = common.find_boundary_provider(session, logger)
            session.commit()
            provider_id = provider.id
            boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    started = time.monotonic()
    outcomes: list[YearOutcome] = []
    for index, path in enumerate(paths, start=1):
        logger.info("[%d/%d] %s", index, len(paths), path.name)
        outcomes += import_extract(path, engine, provider_id, boundary_provider_id, years, logger)

    seen: dict[int, str] = {}
    for outcome in outcomes:
        if outcome.year in seen:
            logger.warning("Year %d was imported twice in this run, from %r and then %r; "
                           "the second replaced the first",
                           outcome.year, seen[outcome.year], outcome.name)
        seen[outcome.year] = outcome.name

    written = sum(outcome.written for outcome in outcomes)
    versions = sum((outcome.versions for outcome in outcomes), Counter())
    logger.info(
        "%s %d stroke(s) in %d flash(es) over %d year(s) from %d file(s) in %.0fs (%s)",
        "Would import" if engine is None else "Imported", written,
        sum(outcome.flashes for outcome in outcomes), len(outcomes), len(paths),
        time.monotonic() - started,
        ", ".join(f"version {version}: {count}" for version, count in sorted(versions.items())),
    )
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("meteocat-lightning-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.source or []:
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    if args.dry_run:
        try:
            import_lightnings(args, None, logger)
        except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
            logger.error("Check failed: %s", error)
            return 1
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
