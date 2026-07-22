#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import GWIS GlobFire v3 wildfire perimeters from the published shapefiles.

Loads the *Global Wildfire Database v3* (GlobFire) archives into
:class:`~src.providers.gwis.wildfire.GwisWildfire` rows. The dataset is published
one zipped shapefile per year at
https://doi.pangaea.de/10.1594/PANGAEA.943975, each holding a ``Polygon`` layer
with three attributes and nothing else:

==========  ===========================================================
``Id``      the fire's identifier — *not* unique, see below
``IDate``   the date the fire started — a bare date, no time
``FDate``   the date it was last observed burning — likewise
==========  ===========================================================

Run it over the directory the archives were downloaded into::

    python3 -m src.apps.imports.wildfires.gwis.import_wildfires -d /path/to/zip/

Each archive is read in place by GDAL's ``/vsizip/`` handler and imported in its
own transaction, so a run interrupted after the tenth file keeps those ten
whole.

Re-running is *not* free, though. GWIS ``Id`` values are not unique — they name
different fires in different files, 359 times over the published dataset (see
:class:`~src.providers.gwis.wildfire.GwisWildfire`) — so there is no key by
which a fire already imported could be told from a new one that shares an
identifier, and nothing is skipped. Importing a file twice stores it twice; the
importer warns when the database already holds GWIS fires. After an interrupted
run, restart it from the files that did not get in.

From a date to an instant
-------------------------

``IDate`` and ``FDate`` carry no time, and the convention for the dataset is that
a fire starts at the beginning of its start date and stops at the end of its end
date — *locally*, where it burnt. Storing that as written would leave the
database with times that cannot be compared against any other provider's, so the
importer resolves them into instants the way
:mod:`src.data_model.wildfire` prescribes:

* an interior point of the perimeter is looked up in
  :class:`~src.data_model.geography.time_zone.TimeZone` to get the IANA zone;
* ``00:00:00`` on ``IDate`` and ``23:59:59`` on ``FDate`` are interpreted in that
  zone by PostgreSQL's ``AT TIME ZONE``, which resolves the daylight-saving
  offset in force on each of those two dates — they may well differ;
* the zone name is stored alongside, so the published local reading is
  recoverable.

This needs the time zone table to be populated first, by
:mod:`src.apps.imports.time_zones.timezone_boundary_builder.import_time_zones`.
Without it every fire falls back to UTC, which the importer warns about loudly
rather than doing quietly.

Which country a fire burnt in
-----------------------------

Each fire is attributed to the OCHA administrative boundary it overlaps most,
resolved once here rather than by a spatial join on every later query. Fires
straddling a border therefore go to the country holding the larger share of the
burnt area. This needs the boundaries imported first, by
:mod:`src.apps.imports.admin_boundaries.ocha.import_admin_boundaries`; without
them the fires still import, with no country attached.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency,
not a Python package.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time

from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common

# The plumbing every wildfire importer shares, re-exported so this module reads
# as one application: see :mod:`src.apps.imports.common`.
from src.apps.imports.common import ArchiveLogger  # noqa: F401
from src.apps.imports.common import FALLBACK_TIME_ZONE  # noqa: F401
from src.apps.imports.common import UNKNOWN_TIME_ZONES_SQL  # noqa: F401
from src.apps.imports.common import check_time_zones  # noqa: F401
from src.apps.imports.common import find_boundary_provider  # noqa: F401
from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import gwis
from src.providers import ocha

#: Attributes of the published layer. Overridable, because the dataset has
#: renamed them between versions before.
DEFAULT_ID_FIELD = "id"
DEFAULT_START_FIELD = "idate"
DEFAULT_END_FIELD = "fdate"

DEFAULT_STAGING_TABLE = "gwis_globfire"

#: Shared by the parent and by every worker process, so a parallel run's output
#: is one stream in one shape. Worker lines name their archive (see
#: :class:`ArchiveLogger`), which is what keeps interleaved lines readable —
#: the process id would not, since it says nothing about what is being imported.
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Maps one staging table onto the two tables of the model in a single statement.
#:
#: Reading it from the bottom up: the last two inserts are the joined-inheritance
#: split — the generic columns into ``wildfire``, the GWIS identifier into
#: ``gwis_wildfire`` — and everything above them works out what to put in them.
#:
#: The primary keys are drawn from the sequence up front, in ``source``, instead
#: of being generated by the insert. The OCHA importer can let the database
#: assign them and recover them with ``RETURNING``, because a boundary carries a
#: ``source_id`` on the parent row to correlate them back to; a wildfire carries
#: its provider identifier on the *child* row, so there would be nothing to
#: correlate on. Taking the ids from the sequence first sidesteps the problem
#: and, unlike relying on the order ``RETURNING`` happens to emit, is guaranteed
#: rather than observed.
#:
#: The CTEs deliberately carry no geometry, only ``staging_fid``, and join back
#: to the staging table wherever a geometry is needed. Carrying perimeters
#: through would mean a second copy of a 300 MB layer in the query's working set.
#:
#: There is deliberately no "skip what is already imported" clause. GWIS ``Id``
#: values repeat across genuinely different fires (see
#: :class:`~src.providers.gwis.wildfire.GwisWildfire`), so filtering on them
#: would discard the second fire of every colliding pair — real data — to save
#: re-importing a file. Rows with no id, no start date or no geometry are
#: dropped, because none of the three can be reconstructed and
#: ``start_date_time`` is NOT NULL.
TRANSFORM_SQL = """
WITH source AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS id,
           staging.fid                        AS staging_fid,
           staging.{id_field}::text           AS gwis_id,
           staging.{start_field}              AS start_date,
           staging.{end_field}                AS end_date
    FROM {staging_table} AS staging
    WHERE staging.{id_field} IS NOT NULL
      AND staging.{start_field} IS NOT NULL
      AND staging.geom IS NOT NULL
),
-- The zone of an interior point of the perimeter. ST_PointOnSurface rather than
-- ST_Centroid: the centroid of a C-shaped or multipart burn can land outside the
-- burn itself, and so in the wrong zone or in no zone at all.
located AS MATERIALIZED (
    SELECT source.*, zone.name AS time_zone
    FROM source
    JOIN {staging_table} AS staging ON staging.fid = source.staging_fid
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE ST_Contains(time_zone.geometry, ST_PointOnSurface(staging.geom))
        LIMIT 1
    ) AS zone ON TRUE
),
-- Every boundary the fire touches at all. Ids only: this is the cheap,
-- index-backed part, and the great majority of fires come out of it with exactly
-- one row.
candidate AS (
    SELECT located.id AS wildfire_id, boundary.id AS boundary_id
    FROM located
    JOIN {staging_table} AS staging ON staging.fid = located.staging_fid
    JOIN admin_boundary AS boundary
      ON boundary.data_provider_id = :boundary_provider_id
     AND boundary.level = 0
     AND ST_Intersects(boundary.geometry, staging.geom)
),
counted AS (
    SELECT wildfire_id, count(*) AS candidates, min(boundary_id) AS single_boundary_id
    FROM candidate GROUP BY wildfire_id
),
-- Of the boundaries a fire touches, the one holding most of it. The subquery in
-- the ELSE branch is what actually intersects the polygons, and CASE evaluates
-- only the branch it takes, so that cost is paid solely for the handful of fires
-- that really do straddle a border rather than for every fire in the file.
--
-- The areas are planar, in square degrees. That is meaningless as an area but
-- perfectly good as a comparison: the candidates are being ranked against each
-- other over one small fire, across which the degree-to-metre scale barely moves.
country AS (
    SELECT counted.wildfire_id,
           CASE WHEN counted.candidates = 1 THEN counted.single_boundary_id
                ELSE (SELECT candidate.boundary_id
                      FROM candidate
                      JOIN admin_boundary AS boundary ON boundary.id = candidate.boundary_id
                      JOIN located ON located.id = candidate.wildfire_id
                      JOIN {staging_table} AS staging ON staging.fid = located.staging_fid
                      WHERE candidate.wildfire_id = counted.wildfire_id
                      ORDER BY ST_Area(ST_Intersection(boundary.geometry, staging.geom)) DESC
                      LIMIT 1)
           END AS boundary_id
    FROM counted
),
inserted AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT located.id,
           'gwis_wildfire',
           :provider_id,
           (located.start_date::timestamp)
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           (located.end_date::timestamp + interval '23:59:59')
               AT TIME ZONE COALESCE(located.time_zone, :fallback_time_zone),
           located.time_zone,
           ST_Multi(staging.geom),
           country.boundary_id
    FROM located
    JOIN {staging_table} AS staging ON staging.fid = located.staging_fid
    LEFT JOIN country ON country.wildfire_id = located.id
    RETURNING id
),
written AS (
    INSERT INTO gwis_wildfire (id, gwis_id)
    SELECT located.id, located.gwis_id
    FROM located JOIN inserted ON inserted.id = located.id
    RETURNING id
)
SELECT count(*) FROM written
"""


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import GWIS GlobFire v3 wildfire perimeters into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Database settings not given here "
               "are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the published .zip archives, one per year")
    source.add_argument("-s", "--shapefile", type=Path,
                        help="a single archive, directory or .shp to import instead of a whole directory")

    fields = parser.add_argument_group("layer", "attribute names, should the dataset rename them")
    fields.add_argument("--id-field", default=DEFAULT_ID_FIELD,
                        help=f"attribute holding the fire id (default: {DEFAULT_ID_FIELD})")
    fields.add_argument("--start-field", default=DEFAULT_START_FIELD,
                        help=f"attribute holding the start date (default: {DEFAULT_START_FIELD})")
    fields.add_argument("--end-field", default=DEFAULT_END_FIELD,
                        help=f"attribute holding the end date (default: {DEFAULT_END_FIELD})")

    parser.add_argument("-j", "--jobs", type=positive_int, default=1,
                        help="archives to import at the same time, in separate processes "
                             "(default: 1). Each is another connection doing spatial joins, "
                             "so raise the server's work_mem and shared_buffers before "
                             "raising this, and expect little past 3-4")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)

    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    """Parse ``--jobs``, rejecting zero and negatives at the command line."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {number}")
    return number


def find_archives(args: argparse.Namespace) -> list[Path]:
    """List the files to import, sorted, so the years go in in order.

    Raises
    ------
    RuntimeError
        If the directory holds no archive at all — far more likely a wrong path
        than an empty download, and silently importing nothing would hide it.
    """
    if args.shapefile is not None:
        return [args.shapefile]

    archives = sorted(args.directory.glob("*.zip"))
    if not archives:
        raise RuntimeError(f"No .zip archives found in {args.directory}")
    return archives


def warn_if_already_imported(session: Session, provider: DataProvider,
                             logger: logging.Logger) -> bool:
    """Warn that a re-run duplicates, returning whether any GWIS fire is already in.

    GWIS ``Id`` values are not unique (see
    :class:`~src.providers.gwis.wildfire.GwisWildfire`), so the importer has no
    way to tell a fire it has already loaded from a different fire that happens
    to share an identifier, and cannot skip either. Importing the same file twice
    therefore stores it twice. Nothing here prevents that — it is the user's
    call, and a re-run may well be the intent after a partial failure — but it
    should never come as a surprise.

    Asks only whether *any* row exists rather than how many. The interesting
    answer is yes or no, and by the time the answer is yes the table can hold
    twenty million rows, which is a long time to spend counting them to print a
    number nothing acts on.
    """
    existing = session.scalar(
        select(Wildfire.id).where(Wildfire.data_provider_id == provider.id).limit(1)
    ) is not None
    if existing:
        logger.warning(
            "GWIS wildfires are already imported. GWIS ids are not unique, so this run "
            "cannot skip what it has seen before: importing a file again will store it "
            "again. Delete the previous rows first if that is not what you want."
        )
    return existing


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, args: argparse.Namespace, logger: logging.Logger) -> int:
    """Map the staging table onto the model, returning the number of fires imported.

    The count is computed by the statement itself rather than by counting the ids
    it returns: a year's file is a million rows, and pulling a million ids back
    only to call ``len`` on them would cost more memory than the import.

    Providers arrive as ids rather than as ORM objects because a parallel run
    hands them to a worker process, and an id survives being pickled and used
    against a different connection where a detached instance would not.
    """
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        id_field=args.id_field,
        start_field=args.start_field,
        end_field=args.end_field,
    )
    return session.scalar(text(statement), {
        "provider_id": provider_id,
        # -1 matches no provider, so with no boundaries imported the join simply
        # finds nothing and every fire gets a NULL country — no separate query.
        "boundary_provider_id": boundary_provider_id if boundary_provider_id is not None else -1,
        "fallback_time_zone": FALLBACK_TIME_ZONE,
    })


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger, staging_table: str | None = None,
                   progress: bool | None = None) -> int:
    """Import one archive in its own transaction, returning the fires imported.

    The two slow phases are announced as they start. ``ogr2ogr`` draws its own
    progress bar for the first, but the second is a single statement and
    PostgreSQL reports nothing at all until it commits, so the only feedback that
    can honestly be given is how much work went into it and when it began.

    ``staging_table`` is what makes a parallel run possible: the table is loaded
    with ``-overwrite``, so two archives sharing one would destroy each other's
    work. Workers are each given their own; a serial run keeps the plain name.
    """
    staging_table = staging_table or f"{args.staging_schema}.{args.staging_table}"
    datasource, layer = common.shapefile_datasource(archive)
    log = ArchiveLogger(logger, {"archive": archive.name})

    started = time.monotonic()
    common.load_staging_table(datasource, layer, staging_table, args,
                              common.resolve_database_settings(args), log, progress=progress)

    with Session(engine) as session:
        # ogr2ogr leaves the table with no statistics at all, so without this the
        # planner sizes a million-row staging table as if it held a handful and
        # picks nested loops over the spatial joins below.
        session.execute(text(f"ANALYZE {staging_table}"))

        staged = session.scalar(text(f"SELECT count(*) FROM {staging_table}"))
        log.info("staged %d features in %.0fs, now mapping them onto the model",
                 staged, time.monotonic() - started)

        imported = transform(session, provider_id, boundary_provider_id, staging_table, args, log)
        if not args.keep_staging:
            common.drop_staging_table(session, staging_table, log)
        session.commit()

    log.info("imported %d wildfires in %.0fs", imported, time.monotonic() - started)
    return imported


#: Per-process state of a parallel worker. A module global because a pool
#: initializer is the only place a worker can build something once and reuse it
#: across the archives it is handed, and an :class:`~sqlalchemy.engine.Engine`
#: must not be inherited across a fork: its pooled connections would be shared by
#: two processes writing over each other's protocol state.
_WORKER: dict[str, object] = {}


def _worker_init(args: argparse.Namespace, provider_id: int,
                 boundary_provider_id: int | None) -> None:
    """Give this worker process its own engine and the ids every archive needs."""
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    _WORKER["args"] = args
    _WORKER["provider_id"] = provider_id
    _WORKER["boundary_provider_id"] = boundary_provider_id
    _WORKER["engine"] = create_engine(common.database_url(common.resolve_database_settings(args)))


def _worker_import(task: tuple[Path, str]) -> tuple[str, int, str | None]:
    """Import one archive in this worker, returning the failure instead of raising.

    A raise would come back as a pickled exception and stop the whole pool. One
    archive that cannot be read is not a reason to throw away the others — each
    is its own transaction — so the error is carried back as text and reported
    together with the rest at the end.
    """
    archive, staging_table = task
    logger = logging.getLogger("gwis-import")
    try:
        imported = import_archive(archive, _WORKER["engine"], _WORKER["args"],
                                  _WORKER["provider_id"], _WORKER["boundary_provider_id"],
                                  logger, staging_table=staging_table, progress=False)
        return archive.name, imported, None
    except Exception as error:  # noqa: BLE001  (carried back to the parent, not swallowed)
        return archive.name, 0, str(error)


def import_in_parallel(archives: list[Path], args: argparse.Namespace, provider_id: int,
                       boundary_provider_id: int | None, jobs: int,
                       logger: logging.Logger) -> int:
    """Import the archives across ``jobs`` processes, returning the fires imported.

    Processes rather than threads, but not for the usual reason: both slow phases
    release the GIL anyway, since one waits on a subprocess and the other on a
    socket. What parallelism buys is server-side — PostgreSQL will not use a
    parallel plan for a statement that writes, so the transform runs on a single
    core however the client is built, and the only way to get more cores onto it
    is more connections doing it at once.

    Raises
    ------
    RuntimeError
        If any archive failed, after every other one has finished.
    """
    tasks = [(archive, f"{args.staging_schema}.{args.staging_table}_{index:02d}")
             for index, archive in enumerate(archives)]
    logger.info("Importing %d archive(s) across %d process(es)", len(archives), jobs)

    imported = 0
    failures: list[tuple[str, str]] = []
    with ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init,
                             initargs=(args, provider_id, boundary_provider_id)) as pool:
        futures = [pool.submit(_worker_import, task) for task in tasks]
        for finished, future in enumerate(as_completed(futures), start=1):
            name, count, error = future.result()
            if error is None:
                imported += count
            else:
                failures.append((name, error))
                logger.error("%s: failed: %s", name, error)
            logger.info("[%d/%d archives done]", finished, len(archives))

    if failures:
        raise RuntimeError(
            f"{len(failures)} of {len(archives)} archive(s) failed: "
            + "; ".join(f"{name} ({error})" for name, error in failures)
        )
    return imported


def import_wildfires(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> int:
    """Run the whole import against ``engine``, returning the fires imported.

    Each archive is a transaction of its own: a year is either wholly in or
    wholly out, and a failure on the fifteenth file does not throw away the
    fourteen before it.
    """
    archives = find_archives(args)
    common.require_tables(engine, ["wildfire", "gwis_wildfire", "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        check_time_zones(session, logger)
        provider = common.get_or_create_data_provider(
            session, gwis.PROVIDER_NAME, gwis.PROVIDER_PRODUCT,
            gwis.PROVIDER_FULL_NAME, gwis.PROVIDER_URL, logger,
        )
        warn_if_already_imported(session, provider, logger)
        boundary_provider = find_boundary_provider(session, logger)
        session.commit()
        # Read back after the commit: the objects are expired and the ids are
        # what the archives — and any worker process — actually need.
        provider_id, boundary_provider_id = provider.id, (
            boundary_provider.id if boundary_provider is not None else None
        )

    started = time.monotonic()
    # More workers than archives would just be idle processes, and one archive is
    # a serial run whatever was asked for.
    jobs = min(args.jobs, len(archives))
    if jobs > 1:
        imported = import_in_parallel(archives, args, provider_id, boundary_provider_id,
                                      jobs, logger)
    else:
        imported = 0
        logger.info("Importing %d archive(s)", len(archives))
        for index, archive in enumerate(archives, start=1):
            logger.info("[%d/%d] %s", index, len(archives), archive.name)
            imported += import_archive(archive, engine, args, provider_id,
                                       boundary_provider_id, logger)

    logger.info("Imported %d wildfires from %d archive(s) in %.0fs", imported, len(archives),
                time.monotonic() - started)
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("gwis-import")

    source = args.directory if args.directory is not None else args.shapefile
    if not source.exists():
        logger.error("Not found: %s", source)
        return 1
    if args.directory is not None and not args.directory.is_dir():
        logger.error("Not a directory: %s", args.directory)
        return 1
    if shutil.which(args.ogr2ogr) is None:
        logger.error("ogr2ogr not found (looked for %r). It comes with GDAL and must be on PATH.",
                     args.ogr2ogr)
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


if __name__ == "__main__":  # pragma nocover
    sys.exit(main())
