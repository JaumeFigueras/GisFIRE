#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Alaska Lightning Detection Network's strokes from a yearly release.

One command over the release as downloaded, or over the ``.txt`` extracted from
it::

    python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \\
        -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip

    python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \\
        -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip \\
        --from-year 2024 --to-year 2026

The reader (:mod:`src.apps.imports.lightnings.alaska_uswfs.readers`) checks the
release, converts its rows and groups them into flashes; this module writes them.
See :mod:`src.providers.alaska_uswfs` for the release itself.

The unit is a UTC year
----------------------

Nothing in a row identifies a stroke, so there is nothing to update in place:
each year of the release is **replaced wholesale** — the network's strokes of that
year deleted and the release's inserted, in one transaction — as the MeteoCat
import does. Other years and other providers' strokes are not touched. The
release is cumulative and re-published every year, so importing a new release
replaces every year it holds, or only those asked for; its last year may be
incomplete (the 2026-11-06 release ends on 2026-09-28), and importing the next
release completes it.

The whole release is checked first — its header, its row count against the FGDC
metadata, its years each in one piece — so a release that fails is refused before
any year is written.

Order, identifiers and flashes
------------------------------

The reader sorts each year's strokes by their values, because the file's order
within a millisecond is arbitrary, drops the strokes published twice, and groups
the strokes into flashes. The identifiers are drawn from ``lightning``'s sequence
**in that order**, so importing the release again gives the same identifiers
order, and so the same ties in the thunderstorm algorithms. ``flash_id`` is the
identifier of the flash's first stroke — the smallest of the flash, since the
first stroke comes first in that order — which ``alaska_uswfs_lightning``'s CHECKs
verify on every row.

How it writes
-------------

A year is up to a quarter of a million strokes, so not through the ORM: the
records are streamed with ``COPY`` into a temporary table, and one ``INSERT ...
SELECT`` per table moves them across, drawing the identifiers, setting the flash,
building the point (EPSG:4326, as published) and resolving the country: the OCHA
level-0 boundary the point falls in, tested against the boundaries clipped to the
network's area and subdivided into pieces of at most
:data:`~src.apps.imports.lightnings.common.SUBDIVIDE_VERTICES` vertices, cut once
per run by :func:`~src.apps.imports.lightnings.common.ensure_boundary_pieces`. The
area crosses the antimeridian (:data:`~src.providers.alaska_uswfs.NETWORK_AREA`),
so the boundaries are clipped on both sides of it. Strokes at sea get none; so
does every stroke when no boundaries are imported, which is warned about and does
not stop the import.

Thunderstorms built on the strokes
----------------------------------

As for MeteoCat and FMI (see :mod:`src.apps.imports.lightnings.common`): a year
that thunderstorm experiments depend on is **refused** — logged and skipped, the
other years imported, the run ending with an error — unless
``--drop-thunderstorms`` deletes those experiments, whole, in the year's
transaction. ``--dry-run --drop-thunderstorms`` connects only to list them.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument. ``--dry-run``
reads, checks and reports without connecting to a database at all, unless
``--drop-thunderstorms`` asks it to list the experiments a real run would drop.
"""

from __future__ import annotations

import argparse
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
from src.apps.imports.lightnings.alaska_uswfs import readers
from src.apps.imports.lightnings.alaska_uswfs.readers import Release
from src.apps.imports.lightnings.alaska_uswfs.readers import ReleaseYear
from src.apps.imports.lightnings.alaska_uswfs.readers import StrokeRecord
from src.apps.imports.lightnings.common import YearInUse
from src.providers import alaska_uswfs
from src.providers.alaska_uswfs.lightning import IDENTITY

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: How many individually bad rows are logged per year before the rest are only
#: counted.
MAX_REPORTED_PROBLEMS = 20

#: Degrees added around the network's area when clipping the boundaries.
EXTENT_MARGIN = 1.0

#: The staging table's columns, in the order each record is copied.
STAGING_COLUMNS = (
    "ordinal", "line", "date_time", "latitude", "longitude", "peak_current",
    "cloud_to_ground", "network_code", "sequence_number", "gdop", "ellipse_semi_major_axis",
    "ellipse_semi_minor_axis", "ellipse_angle", "first_ordinal", "multiplicity",
    "stroke_index",
)

#: One year's records, as prepared. Temporary and dropped at commit.
CREATE_STAGING_SQL = """
CREATE TEMPORARY TABLE alaska_uswfs_stroke_staging (
    ordinal integer PRIMARY KEY,
    line integer NOT NULL,
    date_time timestamptz NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    peak_current double precision,
    cloud_to_ground boolean NOT NULL,
    network_code smallint NOT NULL,
    sequence_number integer,
    gdop smallint NOT NULL,
    ellipse_semi_major_axis double precision,
    ellipse_semi_minor_axis double precision NOT NULL,
    ellipse_angle double precision NOT NULL,
    first_ordinal integer NOT NULL,
    multiplicity integer NOT NULL,
    stroke_index integer NOT NULL
) ON COMMIT DROP
"""

COPY_SQL = f"COPY alaska_uswfs_stroke_staging ({', '.join(STAGING_COLUMNS)}) FROM STDIN"

#: Deletes the network's strokes of one year from both tables in one statement, so
#: the foreign key from ``alaska_uswfs_lightning.id`` to ``lightning.id`` is checked
#: once.
DELETE_YEAR_SQL = """
WITH removed AS (
    DELETE FROM alaska_uswfs_lightning AS child
    USING lightning AS parent
    WHERE parent.id = child.id
      AND parent.data_provider_id = :provider_id
      AND parent.date_time >= :start AND parent.date_time < :end
    RETURNING child.id
)
DELETE FROM lightning WHERE id IN (SELECT id FROM removed)
"""

#: The session's boundary pieces, cut once per run by
#: :func:`~src.apps.imports.lightnings.common.ensure_boundary_pieces`.
PIECES_TABLE = "alaska_uswfs_boundary_parts"

#: Whether this session has the pieces.
PARTS_EXIST_SQL = f"SELECT to_regclass('pg_temp.{PIECES_TABLE}') IS NOT NULL"

#: Temporary tables have no statistics until analysed.
ANALYZE_SQL = "ANALYZE alaska_uswfs_stroke_staging"

#: Moves the staged year into both tables, the identifiers drawn in the year's
#: content order — the ordered subquery is not flattened, so ``nextval`` runs over
#: its rows in that order — and each flash given the identifier of its first
#: stroke, the smallest of the flash. A point on the seam between two pieces of one
#: country intersects both, and one on a border two countries; ``ORDER BY`` makes
#: the choice deterministic.
INSERT_SQL = f"""
WITH numbered AS MATERIALIZED (
    SELECT CAST(nextval(pg_get_serial_sequence('lightning', 'id')) AS integer) AS id,
           ordered.*,
           ST_SetSRID(ST_MakePoint(ordered.longitude, ordered.latitude), 4326) AS point_4326
    FROM (SELECT * FROM alaska_uswfs_stroke_staging ORDER BY ordinal) AS ordered
),
flashed AS MATERIALIZED (
    SELECT numbered.*,
           CAST(min(numbered.id) OVER (PARTITION BY numbered.first_ordinal) AS integer)
               AS flash_id
    FROM numbered
),
bounded AS MATERIALIZED (
    SELECT flashed.*, country.admin_boundary_id
    FROM flashed
    LEFT JOIN LATERAL (
        SELECT part.admin_boundary_id
        FROM {PIECES_TABLE} AS part
        WHERE ST_Intersects(part.geometry, flashed.point_4326)
        ORDER BY part.admin_boundary_id
        LIMIT 1
    ) AS country ON TRUE
),
parents AS (
    INSERT INTO lightning (id, type, data_provider_id, date_time, geometry, peak_current,
                           cloud_to_ground, admin_boundary_id)
    SELECT bounded.id, '{IDENTITY}', :provider_id, bounded.date_time, bounded.point_4326,
           bounded.peak_current, bounded.cloud_to_ground, bounded.admin_boundary_id
    FROM bounded
    RETURNING id
)
INSERT INTO alaska_uswfs_lightning (id, flash_id, multiplicity, stroke_index, network_code,
                                    sequence_number, gdop, ellipse_semi_major_axis,
                                    ellipse_semi_minor_axis, ellipse_angle)
SELECT bounded.id, bounded.flash_id, bounded.multiplicity, bounded.stroke_index,
       bounded.network_code, bounded.sequence_number, bounded.gdop,
       bounded.ellipse_semi_major_axis, bounded.ellipse_semi_minor_axis, bounded.ellipse_angle
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

    def __init__(self, year: int) -> None:
        self.year = year
        self.written = 0
        self.deleted = 0
        self.flashes = 0
        self.cloud_flashes = 0
        self.without_boundary: int | None = None
        #: The thunderstorm experiments dropped (or, in a dry run, that would be).
        self.dropped = 0
        #: The experiments that stopped the year, if they did.
        self.refused: list[int] | None = None

    def count(self, content: ReleaseYear) -> None:
        """Count the records written (or, in a dry run, that would be)."""
        self.written = len(content.records)
        self.flashes = content.flashes
        self.cloud_flashes = content.cloud_flashes

    def describe(self) -> str:
        if self.refused is not None:
            return f"{self.year}: not imported"
        boundary = ("" if self.without_boundary is None
                    else f", {self.without_boundary} with no country")
        return (f"{self.year}: {self.written} stroke(s) in {self.flashes} flash(es) "
                f"({self.flashes - self.cloud_flashes} ground, {self.cloud_flashes} cloud)"
                f"{boundary}")


def year_range(year: int) -> dict[str, str]:
    """The UTC year as the half-open range the statements bind."""
    return {"start": f"{year}-01-01T00:00:00Z", "end": f"{year + 1}-01-01T00:00:00Z"}


def clipping_box(records: list[StrokeRecord]) -> dict[str, float]:
    """The network's area joined with ``records``, with :data:`EXTENT_MARGIN` around it."""
    return lightning_common.clipping_box(alaska_uswfs.NETWORK_AREA, records, EXTENT_MARGIN)


def ensure_boundary_parts(connection: Connection, boundary_provider_id: int | None,
                          log: logging.LoggerAdapter, records: list[StrokeRecord] = ()) -> bool:
    """Cut the session's boundary pieces unless it has them for the box needed; whether
    they were cut. See :func:`~src.apps.imports.lightnings.common.ensure_boundary_pieces`.
    """
    return lightning_common.ensure_boundary_pieces(
        connection, PIECES_TABLE, boundary_provider_id, clipping_box(list(records)), log)


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
                record.ordinal, record.line, record.date_time, record.latitude,
                record.longitude, record.peak_current, record.cloud_to_ground,
                record.network_code, record.sequence_number, record.gdop,
                record.ellipse_semi_major_axis, record.ellipse_semi_minor_axis,
                record.ellipse_angle, record.first_ordinal, record.multiplicity,
                record.stroke_index,
            ))


def import_year(connection: Connection, content: ReleaseYear, provider_id: int,
                boundary_provider_id: int | None, log: logging.LoggerAdapter,
                drop: bool = False) -> YearOutcome:
    """Replace one UTC year with its records, in one transaction.

    The thunderstorm experiments depending on the year are dropped first when
    ``drop`` is set, in the same transaction.

    Raises
    ------
    YearInUse
        If experiments depend on the year and ``drop`` is not set — or if one
        holding its strokes was missed and ``RESTRICT`` refused the delete. The
        transaction is rolled back either way: nothing of the year changes.
    """
    outcome = YearOutcome(content.year)
    bounds = year_range(content.year)
    try:
        with connection.begin():
            covering = lightning_common.covering_experiments(connection, provider_id, **bounds)
            if covering and not drop:
                for experiment in covering:
                    log.warning("%d is used by thunderstorm experiment %s", content.year,
                                experiment.describe())
                raise YearInUse(content.year, [experiment.id for experiment in covering])
            outcome.dropped = lightning_common.drop_experiments(connection, covering, log)
            _replace_year(connection, content, provider_id, boundary_provider_id, bounds,
                          outcome, log)
    except IntegrityError as error:
        if "thunderstorm_lightning" not in str(error.orig):
            raise
        with connection.begin():
            holding = lightning_common.holding_experiments(connection, provider_id, **bounds)
        ids = ", ".join(str(identifier) for identifier in holding)
        raise YearInUse(content.year, holding, (
            f"{content.year} not replaced: its strokes are in thunderstorms of experiment(s) "
            f"{ids}, which the check for dependent experiments did not find; nothing was "
            f"deleted"
        )) from error
    outcome.count(content)
    return outcome


def _replace_year(connection: Connection, content: ReleaseYear, provider_id: int,
                  boundary_provider_id: int | None, bounds: dict[str, str],
                  outcome: YearOutcome, log: logging.LoggerAdapter) -> None:
    """Delete the stored year and write its records, in the open transaction."""
    outcome.deleted = connection.execute(
        text(DELETE_YEAR_SQL), {"provider_id": provider_id, **bounds}).rowcount
    if outcome.deleted:
        log.info("Replacing %d stroke(s) already stored for %d", outcome.deleted, content.year)
    if not content.records:
        return
    stage(connection, content.records)
    ensure_boundary_parts(connection, boundary_provider_id, log, content.records)
    connection.execute(text(ANALYZE_SQL))
    with Spinner(f"{content.year}: writing {len(content.records):,} stroke(s)", log.logger):
        connection.execute(text(INSERT_SQL), {"provider_id": provider_id})
    outcome.without_boundary = connection.execute(
        text(WITHOUT_BOUNDARY_SQL), {"provider_id": provider_id, **bounds}).scalar()


# --------------------------------------------------------------------------
# Reading a year
# --------------------------------------------------------------------------

def report_year(content: ReleaseYear, last: bool, log: logging.LoggerAdapter) -> None:
    """Log what reading a year found: refused rows, the first few one by one, and what
    was dropped, left unknown or may be incomplete."""
    for index, (line, reason) in enumerate(content.problems):
        if index == MAX_REPORTED_PROBLEMS:
            log.warning("Further refused rows of %d are counted, not logged", content.year)
            break
        log.warning("Line %d skipped: %s", line, reason)
    if content.problems:
        log.warning("%d: %d row(s) refused", content.year, len(content.problems))
    if content.duplicates:
        log.info("%d: %d stroke(s) published twice, kept once", content.year,
                 content.duplicates)
    if content.unknown_semi_major:
        log.info("%d: %d stroke(s) with a semi-major axis of 0, stored as unknown",
                 content.year, content.unknown_semi_major)
    if content.polarity_contradictions:
        log.info("%d: %d stroke(s) whose POLARITY contradicts the amplitude (not stored; "
                 "the amplitude's sign is kept)", content.year, content.polarity_contradictions)
    if content.near_new_year:
        log.warning("%d: %d stroke(s) within %g s of the year's start or end: a flash may be "
                    "cut in two there", content.year, content.near_new_year,
                    alaska_uswfs.FLASH_MAX_DURATION_S)
    if last and content.records:
        log.info("%d is the release's last year and ends on %s: it may be incomplete; "
                 "importing the next release completes it", content.year,
                 f"{content.records[-1].date_time:%Y-%m-%d}")


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the strokes of the Alaska Lightning Detection Network (U.S. "
                    "Wildland Fire Service) from its yearly release.",
        epilog="Each UTC year of the release is replaced wholesale, so importing a release "
               "again revises its years and leaves the others alone. Database settings not "
               "given here are read from the environment (.env).",
    )
    parser.add_argument("-s", "--source", type=Path, required=True,
                        help="the release as downloaded (Historical_Lightning_2012_forward_"
                             "as_txt.zip) or the .txt extracted from it")
    parser.add_argument("--from-year", type=int, metavar="YEAR",
                        help="import only this year and later")
    parser.add_argument("--to-year", type=int, metavar="YEAR",
                        help="import only this year and earlier")
    parser.add_argument("--dry-run", action="store_true",
                        help="read, check and report without touching the database")
    parser.add_argument(lightning_common.DROP_FLAG, action="store_true",
                        dest="drop_thunderstorms",
                        help="delete, whole, the thunderstorm experiments that depend on a "
                             "year before replacing it; without it such a year is refused. "
                             "With --dry-run, connect only to list them")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    arguments = parser.parse_args(argv)
    if (arguments.from_year is not None and arguments.to_year is not None
            and arguments.to_year < arguments.from_year):
        parser.error("--to-year cannot be before --from-year")
    return arguments


def selected_years(release: Release, args: argparse.Namespace) -> set[int]:
    """The release's years within ``--from-year``/``--to-year``.

    Raises
    ------
    RuntimeError
        If none is.
    """
    years = {year for year in release.years
             if (args.from_year is None or year >= args.from_year)
             and (args.to_year is None or year <= args.to_year)}
    if not years:
        raise RuntimeError(f"the release holds no stroke in the years asked for (it holds "
                           f"{min(release.years)}-{max(release.years)})" if release.years
                           else "the release holds no stroke")
    return years


#: The tables a run reads or writes.
TABLES = ["lightning", "alaska_uswfs_lightning", "data_provider", "admin_boundary",
          "thunderstorm_experiment", "thunderstorm", "thunderstorm_lightning",
          "thunderstorm_tracking"]

#: The network's row, for a dry run, which creates nothing.
PROVIDER_ID_SQL = "SELECT id FROM data_provider WHERE name = :name AND product = :product"


def import_lightnings(args: argparse.Namespace, engine: Engine | None,
                      logger: logging.Logger, lookup: Engine | None = None) -> int:
    """Import the release's years against ``engine``, returning the strokes written.

    With no ``engine`` this is a dry run, which reads ``lookup``, if given, to list
    the thunderstorm experiments a real run would drop.

    Raises
    ------
    RuntimeError
        If the release fails its checks (nothing is written then), or, after
        importing every other year, if any year was refused.
    """
    with Spinner(f"{args.source.name}: checking", logger):
        release = readers.scan(args.source)
    logger.info("%s: %d row(s) over %d year(s)%s", release.name, release.rows,
                len(release.years),
                "" if release.point_count is None
                else f", as many as the metadata declares")
    if release.point_count is None:
        logger.warning("No FGDC metadata beside the strokes: nothing says the release is "
                       "whole")
    years = selected_years(release, args)
    drop = getattr(args, "drop_thunderstorms", False)

    provider_id = None
    boundary_provider_id = None
    if engine is None and lookup is not None:
        common.require_tables(lookup, TABLES, logger)
        with lookup.connect() as connection:
            provider_id = connection.execute(text(PROVIDER_ID_SQL), {
                "name": alaska_uswfs.PROVIDER_NAME,
                "product": alaska_uswfs.PROVIDER_PRODUCT}).scalar()
    if engine is not None:
        common.require_tables(engine, TABLES, logger)
        with Session(engine) as session:
            provider = common.get_or_create_data_provider(
                session, alaska_uswfs.PROVIDER_NAME, alaska_uswfs.PROVIDER_PRODUCT,
                alaska_uswfs.PROVIDER_FULL_NAME, alaska_uswfs.PROVIDER_URL, logger,
            )
            # The description, which the shared helper has no argument for.
            provider.description = alaska_uswfs.PROVIDER_DESCRIPTION
            boundary_provider = common.find_boundary_provider(session, logger)
            session.commit()
            provider_id = provider.id
            boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    log = ArchiveLogger(logger, {"archive": args.source.name})
    last_year = max(release.years)
    started = time.monotonic()
    outcomes: list[YearOutcome] = []
    # One connection for the whole run: the boundary pieces are a temporary table
    # of its session, cut once and used by every year.
    connection = engine.connect() if engine is not None else None
    try:
        for content in readers.read_years(release, years):
            with Spinner(f"{content.year}: sorting {len(content.records):,} stroke(s) and "
                         f"grouping them into flashes", logger):
                readers.prepare_year(content)
            report_year(content, content.year == last_year, log)
            outcome = YearOutcome(content.year)
            if connection is None:
                outcome.count(content)
                if lookup is not None and provider_id is not None:
                    with lookup.connect() as reading:
                        covering = lightning_common.covering_experiments(
                            reading, provider_id, **year_range(content.year))
                    for experiment in covering:
                        log.info("Would drop thunderstorm experiment %s", experiment.describe())
                    outcome.dropped = len(covering)
            else:
                try:
                    outcome = import_year(connection, content, provider_id,
                                          boundary_provider_id, log, drop)
                except YearInUse as refusal:
                    log.error("%s", refusal)
                    outcome.refused = refusal.experiment_ids
            outcomes.append(outcome)
            log.info("%s", outcome.describe())
    finally:
        if connection is not None:
            connection.rollback()
            lightning_common.drop_boundary_pieces(connection, PIECES_TABLE)
            connection.commit()
            connection.close()

    refused = [outcome for outcome in outcomes if outcome.refused is not None]
    imported = [outcome for outcome in outcomes if outcome.refused is None]
    written = sum(outcome.written for outcome in imported)
    logger.info("%s %d stroke(s) in %d flash(es) over %d year(s) in %.0fs",
                "Would import" if engine is None else "Imported", written,
                sum(outcome.flashes for outcome in imported), len(imported),
                time.monotonic() - started)
    dropped = sum(outcome.dropped for outcome in imported)
    if dropped:
        logger.info("%s %d thunderstorm experiment(s)",
                    "Would have dropped" if engine is None else "Also dropped", dropped)
    if refused:
        raise RuntimeError(
            f"{len(refused)} year(s) not imported: "
            + "; ".join(f"{outcome.year} (thunderstorm experiment(s) "
                        f"{', '.join(map(str, outcome.refused))} depend on it)"
                        for outcome in refused)
            + f". Delete them first or run again with {lightning_common.DROP_FLAG}")
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("alaska-uswfs-lightning-import")

    if not args.source.exists():
        logger.error("Not found: %s", args.source)
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
