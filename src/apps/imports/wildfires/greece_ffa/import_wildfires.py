#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Greek Fire Service wildfire statistics from the published workbooks.

One command over a directory of ``.xlsx`` files::

    python3 -m src.apps.imports.wildfires.greece_ffa.import_wildfires -d /path/to/grecia/

260,194 fire records over 2000-2025, in fifteen workbooks — one per year, plus one
holding 2000 to 2012 in thirteen sheets. The reader
(:mod:`src.apps.imports.wildfires.greece_ffa.readers`) turns each sheet into
records; this module decides what is storable, converts it and writes it.

The unit is a year, not a file
-------------------------------

Every sheet is one year, and a year is **replaced wholesale**: its fires are
deleted and re-inserted, in one transaction, so a re-import of a revised
publication supersedes rather than doubles.

That is not a preference. This dataset publishes **nothing that identifies a
fire** — ``Α/Α ΕΓΓΡΑΦΗΣ`` and ``Α/Α ENGAGE`` begin in 2020, and where they exist
512 record numbers are used by more than one row (see
:mod:`src.providers.greece_ffa`). There is no key to upsert on, so the EGIF
importer's "write only the columns this format publishes" trick has nothing to
hang off and the only idempotent operation available is replace-the-year.

A consequence worth stating: importing the 2000-2012 workbook replaces thirteen
years, and importing a single-year file replaces one. Nothing else in the database
is touched, so the years not being imported keep whatever they had.

One transaction per year
------------------------

A sheet is deleted, read to its end and then committed, so a run interrupted half
way through the thirteen-sheet workbook leaves the years it had finished in place
and the year it was in the middle of exactly as it found it.

A *row* that cannot be stored is a different matter: it is logged with its
worksheet row number and the reason, counted, and skipped, and the rest of the
year is still committed. What makes a row unstorable is deliberately short — no
start date, since :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is
``NOT NULL`` and nothing can stand in for it. Everything else is degraded rather
than refused: a row whose coordinate is the ``0``/``0`` the service writes for
*not located* is stored **without an ignition**, which is the normal state of four
rows in five.

The row number is in the message because for 201,948 rows it is the only way to
say which row was refused.

What the import converts
------------------------

Στρέμματα to hectares
    The eight land-cover columns are multiplied by
    :data:`~src.providers.greece_ffa.STREMMA_HA`. Exact, and done here rather than
    in the reader so that a record still says what the file said.

A date and a time to an instant
    Both are published as naive local wall-clock, and Greece is one zone
    (:data:`~src.providers.greece_ffa.DEFAULT_TIME_ZONE`) for the whole country
    and the whole period — so this importer does **not** resolve the zone from the
    fire's location. It could not: three quarters of the archive has no location to
    resolve from. Only the Guatemalan import
    (:mod:`src.apps.imports.wildfires.guatemala_inab.import_wildfires`) is in the
    same position.

    The conversion is done by PostgreSQL with ``AT TIME ZONE``, which resolves
    daylight saving from the date itself.

A coordinate to a point, and only sometimes
    ``X-ENGAGE``/``Y-ENGAGE`` are WGS 84 degrees, so the point is
    ``ST_MakePoint`` and no reprojection. A pair is stored only when
    :func:`~src.providers.greece_ffa.is_located` accepts it — inside Greece's
    bounds, which rejects the ``0``/``0`` of the 3,755 unlocated rows and catches a
    transposed pair.

The country is resolved per point
    ``admin_boundary_id`` comes from a point-in-polygon test against the OCHA
    level 0 boundaries, for the rows that have a point. The other 205,703 get
    ``NULL`` — there is nothing to test, and no Greek administrative boundaries
    are imported that the published prefecture and municipality names could be
    matched against instead.

False alarms are imported
-------------------------

1,255 of the 9,043 rows of 2025 are ``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ`` — a call-out that found
no fire. They are stored, with the category on the row, because a record that says
"this was not a fire" can be filtered afterwards and a discarded one cannot be
recovered. The run reports how many it wrote. See
:mod:`src.providers.greece_ffa.wildfire` for the ``NULL``-safe filter that
excludes them.

Progress
--------

Each sheet gets a :class:`~src.apps.imports.common.ProgressReporter` — a bar on a
terminal, periodic log lines when redirected. The row count is known from the
worksheet dimensions before reading starts, so the bars carry a percentage and an
estimate.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument. Like the EGIF
importer and unlike the four perimeter ones, this needs no ``ogr2ogr``: the source
is a spreadsheet and the only geometry work is a point PostGIS builds from two
numbers.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.common import ProgressReporter
from src.apps.imports.wildfires.greece_ffa import readers
from src.apps.imports.wildfires.greece_ffa.readers import FireRecord
from src.apps.imports.wildfires.greece_ffa.readers import Sheet
from src.providers import greece_ffa

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Fires converted and written per round trip. The same size the EGIF import uses,
#: for the same reason: large enough that the per-batch statements dominate their
#: own overhead, small enough that the parameter lists stay well inside what
#: psycopg will bind in one executemany.
BATCH_SIZE = 2000

#: How many individually bad rows are logged per sheet before the rest are only
#: counted. A sheet that is wrong in some systematic way — a format change, the
#: wrong file — would otherwise write one line per row and bury the summary that
#: says so.
MAX_REPORTED_PROBLEMS = 20

#: Columns of ``greece_ffa_wildfire``, in the order they are bound.
#:
#: One list and not two, unlike the EGIF import: there is only one format here, so
#: there is no second step whose writes could undo the first's, and a year is
#: replaced rather than merged.
WILDFIRE_COLUMNS = (
    "year", "source_sheet", "record_number", "engage_id", "incident_category",
    "station_name", "prefecture_name", "forest_district_name", "municipality_name",
    "locality_name", "address",
    "area_ha_forest", "area_ha_forest_land", "area_ha_grove", "area_ha_grassland",
    "area_ha_reeds_marsh", "area_ha_agricultural", "area_ha_crop_residue",
    "area_ha_landfill",
    "personnel_fire_service", "personnel_infantry_units", "personnel_volunteers",
    "personnel_army", "personnel_other",
    "vehicles_fire_service", "vehicles_public_service", "vehicles_water_tankers",
    "vehicles_machinery",
    "aircraft_helicopters", "aircraft_cl415", "aircraft_cl215", "aircraft_pzl",
    "aircraft_gru", "aircraft_leased_helicopters", "aircraft_leased_planes",
    "aircraft_other_agencies",
    "ignition_id",
)

#: Columns of ``greece_ffa_ignition``.
IGNITION_COLUMNS = ("year", "record_number", "engage_id")

#: Maps the reader's στρέμμα field to the hectare column it becomes.
AREA_COLUMNS = {
    "area_forest": "area_ha_forest",
    "area_forest_land": "area_ha_forest_land",
    "area_grove": "area_ha_grove",
    "area_grassland": "area_ha_grassland",
    "area_reeds_marsh": "area_ha_reeds_marsh",
    "area_agricultural": "area_ha_agricultural",
    "area_crop_residue": "area_ha_crop_residue",
    "area_landfill": "area_ha_landfill",
}

#: Deletes a year from both tables in one statement.
#:
#: One statement rather than four, for the reason revision e9e992e02a11 gives for
#: the Andalusian one: ``greece_ffa_wildfire.ignition_id`` references ``ignition``
#: and ``greece_ffa_wildfire.id`` references ``wildfire``, so no order of separate
#: statements is safe, while inside one statement the foreign keys are checked once
#: at the end against a consistent final state.
#:
#: The ignition goes with the fire it belongs to: it is that fire's point, read
#: from the same published row, and nothing else references it.
DELETE_YEAR_SQL = """
WITH doomed AS (
    SELECT id, ignition_id FROM greece_ffa_wildfire WHERE year = :year
),
removed_child AS (
    DELETE FROM greece_ffa_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM greece_ffa_ignition
    WHERE id IN (SELECT ignition_id FROM doomed WHERE ignition_id IS NOT NULL)
    RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: Draws ``:count`` identifiers from a table's own sequence in one round trip.
#: The parent row's key has to be known before the child insert, so ``RETURNING``
#: would come too late.
ALLOCATE_SQL = ("SELECT nextval(pg_get_serial_sequence(:table, 'id')) "
                "FROM generate_series(1, :count)")

#: The stored point, straight from the two published numbers.
#:
#: No ``ST_Transform``: the service publishes WGS 84 degrees, which is the CRS the
#: model stores, so the point *is* the published pair — the same position the
#: Guatemalan import is in, and no other. See :mod:`src.providers.greece_ffa.ignition`.
GEOMETRY_SQL = "ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)"

#: The country the point falls in, or ``NULL``.
#:
#: A correlated subquery rather than a join, so that it can sit inside an
#: ``executemany`` over rows that mostly have no point at all. ``ST_Contains`` is
#: strict, so a ``NULL`` point yields no row and the column comes out ``NULL``
#: without a guard — and so does an unimported boundary provider, whose id is then
#: ``NULL`` and matches nothing.
BOUNDARY_SQL = f"""(
    SELECT boundary.id FROM admin_boundary AS boundary
    WHERE boundary.data_provider_id = :boundary_provider_id
      AND boundary.level = 0
      AND ST_Contains(boundary.geometry, {GEOMETRY_SQL})
    LIMIT 1
)"""


def _local(column: str) -> str:
    """SQL resolving a naive published reading against the Greek zone.

    The ``CAST`` is not decoration: ``end_date_time`` is null on 27,183 rows, and
    PostgreSQL cannot infer a bound parameter's type from ``AT TIME ZONE`` alone —
    an untyped null is rejected outright with *could not determine data type of
    parameter*. Naming the type is also why no ``CASE`` is needed:
    ``NULL::timestamp AT TIME ZONE`` is null, which is the wanted answer for a fire
    that was never reported extinguished.
    """
    return f"CAST(:{column} AS timestamp) AT TIME ZONE :time_zone"


INSERT_IGNITION_SQL = f"""
INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                      admin_boundary_id)
VALUES (:ignition_id, 'greece_ffa_ignition', :provider_id, {GEOMETRY_SQL},
        {_local('start_date_time')}, :time_zone, {BOUNDARY_SQL})
"""

INSERT_WILDFIRE_SQL = f"""
INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                      time_zone, admin_boundary_id)
VALUES (:wildfire_id, 'greece_ffa_wildfire', :provider_id,
        {_local('start_date_time')},
        {_local('end_date_time')},
        :time_zone, {BOUNDARY_SQL})
"""


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    """Build the child ``INSERT`` for one of the two provider tables."""
    names = ("id", *columns)
    values = ", ".join(f":{name}" for name in names)
    return f"INSERT INTO {table} ({', '.join(names)}) VALUES ({values})"


INSERT_GREECE_IGNITION_SQL = _insert_sql("greece_ffa_ignition", IGNITION_COLUMNS)
INSERT_GREECE_WILDFIRE_SQL = _insert_sql("greece_ffa_wildfire", WILDFIRE_COLUMNS)


# --------------------------------------------------------------------------
# Converting a record into the parameters the statements bind
# --------------------------------------------------------------------------

def hectares(stremmata: float | None) -> float | None:
    """A published στρέμμα figure in hectares, or ``None`` if none was published.

    ``None`` and not ``0.0``: a column its year does not publish is not a report
    of nothing burning. See :mod:`src.providers.greece_ffa.wildfire`.
    """
    if stremmata is None:
        return None
    return stremmata * greece_ffa.STREMMA_HA


def wildfire_parameters(record: FireRecord, sheet: Sheet, provider_id: int,
                        boundary_provider_id: int | None) -> dict[str, object]:
    """Everything the four statements bind for one fire, ids excepted."""
    parameters: dict[str, object] = {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "time_zone": greece_ffa.DEFAULT_TIME_ZONE,
        "start_date_time": record.start_datetime,
        "end_date_time": record.end_datetime,
        "longitude": record.longitude if record.located else None,
        "latitude": record.latitude if record.located else None,
        "year": sheet.year,
        "source_sheet": sheet.name,
        "record_number": record.record_number,
        "engage_id": record.engage_id,
        "incident_category": record.incident_category,
    }
    for field in ("station_name", "prefecture_name", "forest_district_name",
                  "municipality_name", "locality_name", "address"):
        parameters[field] = getattr(record, field)
    for field, column in AREA_COLUMNS.items():
        parameters[column] = hectares(getattr(record, field))
    for field in readers.COUNT_FIELDS:
        parameters[field] = getattr(record, field)
    return parameters


# --------------------------------------------------------------------------
# Writing a batch
# --------------------------------------------------------------------------

class SheetOutcome:
    """What one year did, for the summary line and the exit status."""

    def __init__(self, year: int, name: str) -> None:
        self.year = year
        self.name = name
        self.read = 0
        self.written = 0
        self.skipped = 0
        self.located = 0
        self.false_alarms = 0
        self.problems = 0
        self.deleted = 0


def allocate(session: Session, table: str, count: int) -> list[int]:
    """Draw ``count`` primary keys from a table's own sequence."""
    if count <= 0:
        return []
    return list(session.scalars(text(ALLOCATE_SQL),
                                {"table": table, "count": count}).all())


def write_batch(session: Session, batch: list[FireRecord], sheet: Sheet,
                provider_id: int, boundary_provider_id: int | None,
                outcome: SheetOutcome) -> None:
    """Insert one batch of fires, parents before children.

    Four statements at most, each an ``executemany`` over the whole batch:
    ``ignition`` and ``greece_ffa_ignition`` for the rows that have a point, then
    ``wildfire`` and ``greece_ffa_wildfire`` for all of them.

    Plain inserts and not upserts, because the year was deleted first — see the
    module docstring for why there is nothing to upsert on.
    """
    if not batch:
        return

    located = [record for record in batch if record.located]
    wildfire_ids = allocate(session, "wildfire", len(batch))
    ignition_ids = allocate(session, "ignition", len(located))

    ignitions: list[dict[str, object]] = []
    greece_ignitions: list[dict[str, object]] = []
    wildfires: list[dict[str, object]] = []
    greece_wildfires: list[dict[str, object]] = []

    for record in batch:
        parameters = wildfire_parameters(record, sheet, provider_id,
                                         boundary_provider_id)
        wildfire_id = wildfire_ids.pop()
        ignition_id = None
        if record.located:
            ignition_id = ignition_ids.pop()
            outcome.located += 1
            ignitions.append(dict(parameters, ignition_id=ignition_id))
            greece_ignitions.append(
                {"id": ignition_id,
                 **{name: parameters[name] for name in IGNITION_COLUMNS}}
            )
        if record.incident_category == greece_ffa.CATEGORY_FALSE_ALARM:
            outcome.false_alarms += 1

        parameters["ignition_id"] = ignition_id
        wildfires.append(dict(parameters, wildfire_id=wildfire_id))
        greece_wildfires.append(
            {"id": wildfire_id,
             **{name: parameters[name] for name in WILDFIRE_COLUMNS}}
        )
        outcome.written += 1

    if ignitions:
        session.execute(text(INSERT_IGNITION_SQL), ignitions)
        session.execute(text(INSERT_GREECE_IGNITION_SQL), greece_ignitions)
    session.execute(text(INSERT_WILDFIRE_SQL), wildfires)
    session.execute(text(INSERT_GREECE_WILDFIRE_SQL), greece_wildfires)


# --------------------------------------------------------------------------
# Importing one sheet
# --------------------------------------------------------------------------

def report_problems(record: FireRecord, outcome: SheetOutcome,
                    log: logging.LoggerAdapter) -> None:
    """Log what could not be read on a row that is still going to be stored."""
    if not record.problems:
        return
    outcome.problems += 1
    if outcome.problems <= MAX_REPORTED_PROBLEMS:
        log.warning("Row %d: %s", record.row, "; ".join(record.problems))
    elif outcome.problems == MAX_REPORTED_PROBLEMS + 1:
        log.warning("Further per-row problems in this sheet are counted, not logged")


def usable(record: FireRecord, outcome: SheetOutcome,
           log: logging.LoggerAdapter) -> bool:
    """Whether a row can be stored at all.

    One condition: it names a start date. ``wildfire.start_date_time`` is
    ``NOT NULL`` and there is nothing to put in it otherwise — not the year, which
    would date every such fire to 1 January, and not the extinction, which 27,183
    rows do not publish either.

    Every row of the twenty-six published sheets passes, so this guards against a
    future publication rather than against the archive.
    """
    if record.start_date is None:
        outcome.skipped += 1
        if outcome.skipped <= MAX_REPORTED_PROBLEMS:
            log.warning("Row %d skipped: no start date", record.row)
        return False
    return True


def delete_year(session: Session, year: int) -> int:
    """Remove a year's fires and their points, returning how many rows went.

    The count is of the **fires**, not of the four tables' rows together: the outer
    ``DELETE`` is the one on ``ignition``, so what ``rowcount`` reports is the
    points, and the fires are counted separately before the statement runs.
    """
    fires = session.scalar(
        text("SELECT count(*) FROM greece_ffa_wildfire WHERE year = :year"),
        {"year": year},
    ) or 0
    session.execute(text(DELETE_YEAR_SQL), {"year": year})
    return fires


def import_sheet(sheet: Sheet, session: Session, provider_id: int,
                 boundary_provider_id: int | None,
                 log: logging.LoggerAdapter) -> SheetOutcome:
    """Replace one year with the records of one sheet, in the caller's transaction."""
    outcome = SheetOutcome(sheet.year, sheet.name)

    if sheet.unknown_columns:
        log.warning(
            "Sheet %r has %d column(s) this import does not know and will not store: "
            "%s. Add them to src.apps.imports.wildfires.greece_ffa.readers.COLUMNS "
            "if they are wanted.",
            sheet.name, len(sheet.unknown_columns), ", ".join(sheet.unknown_columns),
        )
    missing = [field for field in ("start_date", "start_time")
               if field not in sheet.columns]
    if missing:
        raise RuntimeError(
            f"sheet {sheet.name!r} publishes no {' and no '.join(missing)} column; "
            f"refusing to import a year whose fires would have no start instant"
        )

    outcome.deleted = delete_year(session, sheet.year)
    if outcome.deleted:
        log.info("Replacing %d row(s) already stored for %d", outcome.deleted, sheet.year)

    progress = ProgressReporter(sheet.rows or None, f"{sheet.name} ({sheet.year})",
                                log.logger)
    batch: list[FireRecord] = []
    for record in sheet.records:
        outcome.read += 1
        progress.advance()
        report_problems(record, outcome, log)
        if not usable(record, outcome, log):
            continue
        batch.append(record)
        if len(batch) >= BATCH_SIZE:
            write_batch(session, batch, sheet, provider_id, boundary_provider_id,
                        outcome)
            batch = []
    write_batch(session, batch, sheet, provider_id, boundary_provider_id, outcome)
    progress.finish()
    return outcome


def import_file(path: Path, engine: Engine, provider_id: int,
                boundary_provider_id: int | None, years: set[int] | None,
                logger: logging.Logger) -> list[SheetOutcome]:
    """Import every year of one workbook, one transaction per year.

    A sheet is committed on its own, so the thirteen-year workbook is thirteen
    transactions and an interrupted run keeps the years it had finished.
    """
    log = ArchiveLogger(logger, {"archive": path.name})
    outcomes: list[SheetOutcome] = []

    for sheet in readers.read_workbook(path):
        if years is not None and sheet.year not in years:
            log.debug("Skipping %d: not among the years requested", sheet.year)
            continue
        with Session(engine) as session:
            outcome = import_sheet(sheet, session, provider_id, boundary_provider_id,
                                   log)
            session.commit()
        outcomes.append(outcome)
        log.info(
            "%d: %d row(s) read, %d written (%d with a point, %d false alarm(s)), "
            "%d skipped, %d with problems",
            outcome.year, outcome.read, outcome.written, outcome.located,
            outcome.false_alarms, outcome.skipped, outcome.problems,
        )
    if not outcomes:
        log.warning("No year of fires found in this workbook")
    return outcomes


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Greek Fire Service wildfire statistics from the "
                    "published Excel workbooks.",
        epilog="Import the OCHA country boundaries and the time zone areas first. "
               "Each year found is replaced wholesale, so re-importing a revised "
               "publication supersedes rather than doubles. Database settings not "
               "given here are read from the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the workbooks; every .xlsx is imported")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more workbooks to import instead of a whole "
                             "directory")

    parser.add_argument("-y", "--year", type=int, nargs="+", dest="years",
                        help="import only these years, skipping the other sheets of a "
                             "multi-year workbook")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def find_workbooks(args: argparse.Namespace) -> list[Path]:
    """List the workbooks to read, sorted.

    Raises
    ------
    RuntimeError
        If nothing was found — far more likely a wrong path than an empty
        download — or if a named file is not a workbook.
    """
    if args.directory is not None:
        workbooks = sorted(args.directory.glob("*.xlsx"))
        if not workbooks:
            raise RuntimeError(f"{args.directory} holds no .xlsx workbook")
        return workbooks

    unknown = [path for path in args.source if path.suffix.lower() != ".xlsx"]
    if unknown:
        raise RuntimeError(
            f"not a Greek Fire Service workbook: "
            f"{', '.join(str(path) for path in unknown)}"
        )
    return sorted(args.source)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Import every workbook against ``engine``, returning the fires written."""
    workbooks = find_workbooks(args)
    years = set(args.years) if args.years else None

    common.require_tables(engine, ["wildfire", "ignition", "greece_ffa_wildfire",
                                   "greece_ffa_ignition", "admin_boundary",
                                   "time_zone", "data_provider"], logger)

    with Session(engine) as session:
        common.check_time_zones(session, logger, greece_ffa.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, greece_ffa.PROVIDER_NAME, greece_ffa.PROVIDER_PRODUCT,
            greece_ffa.PROVIDER_FULL_NAME, greece_ffa.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    started = time.monotonic()
    outcomes: list[SheetOutcome] = []
    logger.info("%d workbook(s) to import", len(workbooks))
    for index, path in enumerate(workbooks, start=1):
        logger.info("[%d/%d] %s", index, len(workbooks), path.name)
        outcomes += import_file(path, engine, provider_id, boundary_provider_id,
                                years, logger)

    written = sum(outcome.written for outcome in outcomes)
    seen: dict[int, str] = {}
    for outcome in outcomes:
        if outcome.year in seen:
            logger.warning(
                "Year %d was imported twice in this run, from %r and then %r; the "
                "second replaced the first",
                outcome.year, seen[outcome.year], outcome.name,
            )
        seen[outcome.year] = outcome.name

    logger.info(
        "Imported %d fire(s) over %d year(s) from %d workbook(s) in %.0fs: "
        "%d with a point, %d false alarm(s), %d skipped",
        written, len(outcomes), len(workbooks), time.monotonic() - started,
        sum(outcome.located for outcome in outcomes),
        sum(outcome.false_alarms for outcome in outcomes),
        sum(outcome.skipped for outcome in outcomes),
    )
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("greece-ffa-import")

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
