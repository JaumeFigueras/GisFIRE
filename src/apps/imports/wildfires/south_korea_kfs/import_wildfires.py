#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Korea Forest Service wildfire statistics from a published release.

One command over the release CSV, or over the directory holding it::

    python3 -m src.apps.imports.wildfires.south_korea_kfs.import_wildfires \\
        -s "/path/to/산불발생통계(20251110).csv"

    python3 -m src.apps.imports.wildfires.south_korea_kfs.import_wildfires \\
        -d /path/to/산불통계데이터/

The reader (:mod:`src.apps.imports.wildfires.south_korea_kfs.readers`) turns the
file into records; this module classifies them, decides what is storable and
writes it. The original CP949 file is what is read — not an English copy, which is
a derived product.

The unit is a year
------------------

Nothing in a row identifies a fire, so there is nothing to update in place: each
year in the file is **replaced wholesale** — its fires deleted and re-inserted in
one transaction — exactly as the Greek import does
(:mod:`src.apps.imports.wildfires.greece_ffa.import_wildfires`). That also suits
how the service publishes: a release holds the last few years and ends part way
through the current one, so the next release revises the last year, and
importing it replaces that year. Years not in the file are not touched.

Causes are checked before anything is written
----------------------------------------------

Every cause text in the file is looked up in
:mod:`src.providers.south_korea_kfs.causes` first, and a single unknown one stops
the import with the list of them, before any year is deleted. A new release with
new spellings therefore leaves the database as it was until they are classified.

What is stored, degraded or refused
-----------------------------------

A row is refused — logged with its line number, counted and skipped — only when a
``NOT NULL`` column would have nothing in it: no valid start, no area, no office,
province, detailed cause or cause text. No row of the 2025 release is.

An end that cannot be right is **degraded**: the fire is stored with no end and
the reason in ``end_date_problem`` — 14 rows of the 2025 release, twelve ending
before they start and two in 2055 and 2223. A weekday that disagrees with the date
is logged and the row stored as published.

What the import converts
------------------------

The two times are naive Korean wall-clock readings, converted to instants by
PostgreSQL with ``AT TIME ZONE`` in
:data:`~src.providers.south_korea_kfs.DEFAULT_TIME_ZONE`. The zone is not resolved
from the fire's location — there is no location — and need not be: South Korea is
one zone.

Each place name is romanized with :func:`~src.providers.south_korea_kfs.romanize`
and each cause text translated and classified with
:func:`~src.providers.south_korea_kfs.cause`.

``admin_boundary_id`` is ``NULL``: it is assigned by a point-in-polygon test, and
these fires have no point.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
``--dry-run`` reads, checks and reports a release without connecting to a
database at all.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from collections import Counter
from collections import defaultdict
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.common import ProgressReporter
from src.apps.imports.wildfires.south_korea_kfs import readers
from src.apps.imports.wildfires.south_korea_kfs.readers import FireRecord
from src.apps.imports.wildfires.south_korea_kfs.readers import Release
from src.providers import south_korea_kfs

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Fires written per round trip. A release is a couple of thousand rows, so this
#: is one batch a year; it is here so a larger release stays bounded.
BATCH_SIZE = 2000

#: How many individually bad rows are logged per file before the rest are only
#: counted.
MAX_REPORTED_PROBLEMS = 20

#: Columns of ``kfs_wildfire``, in the order they are bound.
WILDFIRE_COLUMNS = (
    "year", "source_file", "source_row",
    "office_name", "office_name_rr", "province_name", "province_name_rr",
    "municipality_name", "municipality_name_rr", "township_name", "township_name_rr",
    "village_name", "village_name_rr",
    "cause_category_code", "cause_detail", "cause_text", "cause_text_en",
    "cause_class", "fire_cause", "cause_suspected",
    "area_ha", "end_date_problem",
)

#: Deletes a year from both tables in one statement, so the foreign key from
#: ``kfs_wildfire.id`` to ``wildfire.id`` is checked once, at the end.
DELETE_YEAR_SQL = """
WITH removed_child AS (
    DELETE FROM kfs_wildfire WHERE year = :year RETURNING id
)
DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child)
"""

#: Draws ``:count`` identifiers from ``wildfire``'s sequence in one round trip.
ALLOCATE_SQL = ("SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) "
                "FROM generate_series(1, :count)")


def _local(column: str) -> str:
    """SQL resolving a naive published reading against the Korean zone.

    The ``CAST`` names the parameter's type, which ``AT TIME ZONE`` alone does not
    let PostgreSQL infer for a ``NULL`` end.
    """
    return f"CAST(:{column} AS timestamp) AT TIME ZONE :time_zone"


INSERT_WILDFIRE_SQL = f"""
INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                      time_zone, admin_boundary_id)
VALUES (:wildfire_id, 'kfs_wildfire', :provider_id,
        {_local('start_date_time')}, {_local('end_date_time')},
        :time_zone, NULL)
"""

INSERT_KFS_WILDFIRE_SQL = (
    f"INSERT INTO kfs_wildfire (id, {', '.join(WILDFIRE_COLUMNS)}) "
    f"VALUES (:wildfire_id, {', '.join(':' + name for name in WILDFIRE_COLUMNS)})"
)


# --------------------------------------------------------------------------
# Checking a release
# --------------------------------------------------------------------------

def unmapped_causes(release: Release) -> list[str]:
    """The cause texts of a release that the cause table does not list, sorted."""
    unknown = set()
    for record in release.records:
        if record.cause_text is None:
            continue
        try:
            south_korea_kfs.cause(record.cause_text)
        except south_korea_kfs.UnmappedCauseError:
            unknown.add(record.cause_text)
    return sorted(unknown)


def unstorable(record: FireRecord) -> str | None:
    """Why a record cannot be stored, or ``None`` if it can."""
    if record.start is None:
        return "no valid start"
    if record.area_ha is None:
        return "no valid area"
    for name, value in (("office", record.office), ("province", record.province),
                        ("detailed cause", record.cause_detail),
                        ("cause text", record.cause_text)):
        if value is None:
            return f"no {name}"
    return None


# --------------------------------------------------------------------------
# Converting a record into the parameters the statements bind
# --------------------------------------------------------------------------

def wildfire_parameters(record: FireRecord, release: Release,
                        provider_id: int) -> dict[str, object]:
    """Everything the two statements bind for one fire, the id excepted."""
    cause_text_en, cause_class = south_korea_kfs.cause(record.cause_text)
    romanize = south_korea_kfs.romanize
    return {
        "provider_id": provider_id,
        "time_zone": south_korea_kfs.DEFAULT_TIME_ZONE,
        "start_date_time": record.start,
        "end_date_time": None if record.end_date_problem else record.end,
        "year": record.year,
        "source_file": release.name,
        "source_row": record.row,
        "office_name": record.office,
        "office_name_rr": romanize(record.office),
        "province_name": record.province,
        "province_name_rr": romanize(record.province),
        "municipality_name": record.municipality,
        "municipality_name_rr": romanize(record.municipality),
        "township_name": record.township,
        "township_name_rr": romanize(record.township),
        "village_name": record.village,
        "village_name_rr": romanize(record.village),
        "cause_category_code": record.cause_category_code,
        "cause_detail": record.cause_detail,
        "cause_text": record.cause_text,
        "cause_text_en": cause_text_en,
        "cause_class": cause_class,
        "fire_cause": south_korea_kfs.fire_cause(cause_class),
        "cause_suspected": south_korea_kfs.is_suspected(record.cause_text),
        "area_ha": record.area_ha,
        "end_date_problem": record.end_date_problem,
    }


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

class YearOutcome:
    """What one year did, for the summary."""

    def __init__(self, year: int, name: str) -> None:
        self.year = year
        self.name = name
        self.written = 0
        self.area_ha = 0.0
        self.end_problems = 0
        self.suspected = 0
        self.deleted = 0
        self.causes: Counter[str] = Counter()

    def count(self, record: FireRecord, parameters: dict[str, object]) -> None:
        """Count one fire written (or, in a dry run, that would be)."""
        self.written += 1
        self.area_ha += record.area_ha
        self.end_problems += record.end_date_problem is not None
        self.suspected += parameters["cause_suspected"]
        self.causes[parameters["cause_class"]] += 1


def allocate(session: Session, count: int) -> list[int]:
    """Draw ``count`` primary keys from ``wildfire``'s sequence."""
    if count <= 0:
        return []
    return list(session.scalars(text(ALLOCATE_SQL), {"count": count}).all())


def write_batch(session: Session, batch: list[FireRecord], release: Release,
                provider_id: int, outcome: YearOutcome) -> None:
    """Insert one batch of fires: ``wildfire`` rows, then ``kfs_wildfire`` ones."""
    if not batch:
        return
    ids = allocate(session, len(batch))
    rows = []
    for record, wildfire_id in zip(batch, ids):
        parameters = wildfire_parameters(record, release, provider_id)
        parameters["wildfire_id"] = wildfire_id
        rows.append(parameters)
        outcome.count(record, parameters)
    session.execute(text(INSERT_WILDFIRE_SQL), rows)
    session.execute(text(INSERT_KFS_WILDFIRE_SQL), rows)


def delete_year(session: Session, year: int) -> int:
    """Remove a year's fires, returning how many there were."""
    fires = session.scalar(
        text("SELECT count(*) FROM kfs_wildfire WHERE year = :year"), {"year": year},
    ) or 0
    session.execute(text(DELETE_YEAR_SQL), {"year": year})
    return fires


def import_year(year: int, records: list[FireRecord], release: Release,
                session: Session, provider_id: int,
                log: logging.LoggerAdapter) -> YearOutcome:
    """Replace one year with its records, in the caller's transaction."""
    outcome = YearOutcome(year, release.name)
    outcome.deleted = delete_year(session, year)
    if outcome.deleted:
        log.info("Replacing %d fire(s) already stored for %d", outcome.deleted, year)
    progress = ProgressReporter(len(records), f"{release.name} ({year})", log.logger)
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        write_batch(session, batch, release, provider_id, outcome)
        progress.advance(len(batch))
    progress.finish()
    return outcome


# --------------------------------------------------------------------------
# Importing one release
# --------------------------------------------------------------------------

def storable_by_year(release: Release, years: set[int] | None,
                     log: logging.LoggerAdapter) -> tuple[dict[int, list[FireRecord]], int]:
    """Group the storable records by year, logging the problems of the rest.

    Returns
    -------
    tuple
        The records by year, in the order published, and how many were skipped.
    """
    by_year: dict[int, list[FireRecord]] = defaultdict(list)
    reported = 0
    skipped = 0
    for record in release.records:
        reason = unstorable(record)
        if record.problems:
            reported += 1
            if reported <= MAX_REPORTED_PROBLEMS:
                log.warning("Line %d%s: %s", record.row,
                            " skipped" if reason else "", "; ".join(record.problems))
            elif reported == MAX_REPORTED_PROBLEMS + 1:
                log.warning("Further per-row problems in this file are counted, not logged")
        if reason is not None:
            skipped += 1
            continue
        if years is not None and record.year not in years:
            continue
        by_year[record.year].append(record)
    return dict(sorted(by_year.items())), skipped


def import_release(release: Release, engine: Engine | None, provider_id: int | None,
                   years: set[int] | None, logger: logging.Logger) -> list[YearOutcome]:
    """Import every year of one release, one transaction per year.

    With no ``engine`` nothing is written: the outcomes are what an import would
    write, for ``--dry-run``.

    Raises
    ------
    RuntimeError
        If the release holds a cause text the cause table does not list. Raised
        before any year is touched.
    """
    log = ArchiveLogger(logger, {"archive": release.name})
    log.info("%d row(s) read (%s)", len(release.records), release.encoding)

    unknown = unmapped_causes(release)
    if unknown:
        raise RuntimeError(
            f"{release.name} holds {len(unknown)} cause text(s) not in "
            f"src.providers.south_korea_kfs.causes; translate and classify them "
            f"there first: {', '.join(repr(value) for value in unknown)}"
        )

    by_year, skipped = storable_by_year(release, years, log)
    if skipped:
        log.warning("%d row(s) skipped as unstorable", skipped)

    outcomes = []
    for year, records in by_year.items():
        if engine is None:
            outcome = YearOutcome(year, release.name)
            for record in records:
                outcome.count(record, wildfire_parameters(record, release, 0))
        else:
            with Session(engine) as session:
                outcome = import_year(year, records, release, session, provider_id, log)
                session.commit()
        outcomes.append(outcome)
        log.info("%d: %d fire(s), %.2f ha, %d with no stored end, %d with a "
                 "suspected cause", year, outcome.written, outcome.area_ha,
                 outcome.end_problems, outcome.suspected)
    if not outcomes:
        log.warning("No fires to import in this file")
    return outcomes


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Korea Forest Service wildfire statistics "
                    "(산불통계데이터, data.go.kr 15121380) from the published CSV.",
        epilog="Each year found is replaced wholesale, so importing a newer release "
               "revises the years it holds and leaves the others alone. Database "
               "settings not given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the release; every .csv with the "
                             "statistics header is imported, others are skipped")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more release files to import")

    parser.add_argument("-y", "--year", type=int, nargs="+", dest="years",
                        help="import only these years")
    parser.add_argument("--dry-run", action="store_true",
                        help="read, check and report without touching the database")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def read_releases(args: argparse.Namespace, logger: logging.Logger) -> list[Release]:
    """Read every release named on the command line.

    A file named with ``--source`` must be a release; in a ``--directory`` a CSV
    that is not one — the data dictionary shipped beside it — is skipped with a
    warning.

    Raises
    ------
    RuntimeError
        If no release was found, or a named file is not one.
    """
    if args.directory is not None:
        releases = []
        for path in sorted(args.directory.glob("*.csv")):
            try:
                releases.append(readers.read_release(path))
            except RuntimeError as error:
                logger.warning("Skipping %s: %s", path.name, error)
        if not releases:
            raise RuntimeError(f"{args.directory} holds no KFS wildfire statistics CSV")
        return releases

    releases = []
    for path in sorted(args.source):
        try:
            releases.append(readers.read_release(path))
        except RuntimeError as error:
            raise RuntimeError(f"{path}: {error}") from None
    return releases


def import_wildfires(args: argparse.Namespace, engine: Engine | None,
                     logger: logging.Logger) -> int:
    """Import every release against ``engine``, returning the fires written.

    With no ``engine`` this is a dry run.
    """
    releases = read_releases(args, logger)
    years = set(args.years) if args.years else None

    provider_id = None
    if engine is not None:
        common.require_tables(engine, ["wildfire", "kfs_wildfire", "data_provider"], logger)
        with Session(engine) as session:
            provider = common.get_or_create_data_provider(
                session, south_korea_kfs.PROVIDER_NAME, south_korea_kfs.PROVIDER_PRODUCT,
                south_korea_kfs.PROVIDER_FULL_NAME, south_korea_kfs.PROVIDER_URL, logger,
            )
            session.commit()
            provider_id = provider.id

    started = time.monotonic()
    outcomes: list[YearOutcome] = []
    for index, release in enumerate(releases, start=1):
        logger.info("[%d/%d] %s", index, len(releases), release.name)
        outcomes += import_release(release, engine, provider_id, years, logger)

    seen: dict[int, str] = {}
    for outcome in outcomes:
        if outcome.year in seen:
            logger.warning("Year %d was imported twice in this run, from %r and then "
                           "%r; the second replaced the first",
                           outcome.year, seen[outcome.year], outcome.name)
        seen[outcome.year] = outcome.name

    written = sum(outcome.written for outcome in outcomes)
    causes = sum((outcome.causes for outcome in outcomes), Counter())
    logger.info(
        "%s %d fire(s) over %d year(s) from %d file(s) in %.0fs: %.2f ha, %d with no "
        "stored end, %d with a suspected cause",
        "Would import" if engine is None else "Imported", written, len(outcomes),
        len(releases), time.monotonic() - started,
        sum(outcome.area_ha for outcome in outcomes),
        sum(outcome.end_problems for outcome in outcomes),
        sum(outcome.suspected for outcome in outcomes),
    )
    logger.info("Cause classes: %s",
                ", ".join(f"{name} {count}" for name, count in causes.most_common()))
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("south-korea-kfs-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.source or []:
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    if args.dry_run:
        try:
            import_wildfires(args, None, logger)
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
        import_wildfires(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
