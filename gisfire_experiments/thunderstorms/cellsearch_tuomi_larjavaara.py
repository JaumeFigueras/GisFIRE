#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensitivity analysis of Cellsearch (Tuomi & Larjavaara 2005).

::

    python3 -m gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara \\
        --provider FMI --from 2018-07-01 --to 2018-08-01

Each parameter swept has its own list of values below. The other parameters
(E_max, N_min and the CRS) keep their defaults; the CRS is the provider's. Only
cloud-to-ground strokes are clustered, the builder's default, as in the
article.

Every combination of the lists is one run of the thunderstorm builder
(:mod:`src.apps.thunderstorms.build_thunderstorms`) over the period, stored as
one thunderstorm experiment. A combination already stored for the period, from
an earlier run of this script, is not run again, so an interrupted analysis
goes on where it stopped. A run that fails stops the analysis; it stays stored
as ``failed``, and is reported, until it is deleted.

At the end the experiment ids of all the combinations are read back from the
database, and the complete ones are written to a CSV file in ``--output-dir``,
named after the algorithm, the provider and the period (see
:func:`csv_filename`): one row per experiment, with its id and the parameters
swept (C off is an empty cell).

Database settings come from the environment (``.env``, see
:mod:`src.settings`); every one of them can be overridden with a command-line
argument.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import itertools
import logging
import os
import sys

from pathlib import Path

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from gisfire_algorithms.thunderstorm import CellsearchParameters
from src.apps.imports import common
from src.apps.thunderstorms import writers
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT
from src.apps.thunderstorms.build_thunderstorms import TABLES
from src.apps.thunderstorms.build_thunderstorms import build_thunderstorms
from src.apps.thunderstorms.build_thunderstorms import experiment_configuration
from src.apps.thunderstorms.build_thunderstorms import parse_instant
from src.apps.thunderstorms.build_thunderstorms import provider_id
from src.apps.thunderstorms.readers import READERS

#: The algorithm, by its name in the builder's ``ALGORITHMS``.
ALGORITHM = "cellsearch_tuomi_larjavaara"

#: R, the radius of attraction, in km.
ATTRACTION_RADII_KM = [10, 15, 20]

#: T, the maximum waiting time, in minutes.
MAX_WAITING_TIMES_MIN = [10, 15, 20]

#: I, the inertia: how many of a cell's latest flashes its centre is the mean of.
INERTIAS = [10, 20, 30, 40, 60, 80]

#: C, the time-distance limit, in min·km; ``None`` turns the condition off.
TIME_DISTANCE_LIMITS_MIN_KM = [None, 10, 20, 40, 80, 160]


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The provider, the period and the database settings."""
    parser = argparse.ArgumentParser(
        description="Sensitivity analysis of Cellsearch over one provider's strokes.",
        epilog="The period is half-open, [from, to); an instant with no offset is UTC. "
               "Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("--provider", required=True, choices=sorted(READERS),
                        help="whose strokes to cluster")
    parser.add_argument("--from", dest="start", required=True, type=parse_instant,
                        help="first instant of the period (included)")
    parser.add_argument("--to", dest="end", required=True, type=parse_instant,
                        help="end of the period (excluded)")
    parser.add_argument("--output-dir", type=Path, default=Path("."),
                        help="where the CSV file goes (default: the current directory)")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    common.add_database_arguments(parser)
    return parser.parse_args(argv)


def connect(args: argparse.Namespace, logger: logging.Logger) -> tuple[Engine, int]:
    """The engine and the provider's ``data_provider.id``.

    Raises
    ------
    RuntimeError
        If a database setting is missing, a lightning or thunderstorm table is
        not in the database, or the provider's strokes are not imported.
    """
    engine = create_engine(common.database_url(common.resolve_database_settings(args)))
    common.require_tables(engine, TABLES, logger)
    with engine.connect() as connection:
        identifier = provider_id(connection, READERS[args.provider])
    return engine, identifier


def parameter_grid(srid: int) -> list[CellsearchParameters]:
    """Every combination of the lists, C changing fastest, then I, T and R."""
    return [CellsearchParameters(attraction_radius_km=radius, max_waiting_time_min=waiting,
                                 inertia=inertia, time_distance_limit_min_km=limit, srid=srid)
            for radius, waiting, inertia, limit in itertools.product(
                ATTRACTION_RADII_KM, MAX_WAITING_TIMES_MIN, INERTIAS, TIME_DISTANCE_LIMITS_MIN_KM)]


def describe(parameters: CellsearchParameters) -> str:
    """``R 15 km, T 15 min, I 20, C off`` (or ``C 40 min·km``)."""
    limit = parameters.time_distance_limit_min_km
    return (f"R {parameters.attraction_radius_km:g} km, T {parameters.max_waiting_time_min:g} min, "
            f"I {parameters.inertia}, C " + ("off" if limit is None else f"{limit:g} min·km"))


def stored_experiment(connection: Connection, data_provider_id: int, provider: str,
                      parameters: CellsearchParameters, start: datetime.datetime,
                      end: datetime.datetime) -> tuple[int, str] | None:
    """The ``(id, status)`` of the experiment of this combination and period, if stored."""
    return writers.find_experiment(connection, experiment_configuration(
        data_provider_id, provider, ALGORITHM, parameters, start, end))


def run_grid(engine: Engine, data_provider_id: int, provider: str,
             grid: list[CellsearchParameters], start: datetime.datetime,
             end: datetime.datetime, logger: logging.Logger) -> None:
    """Run every combination not stored yet; a failed run raises."""
    for number, parameters in enumerate(grid, start=1):
        with engine.connect() as connection:
            existing = stored_experiment(connection, data_provider_id, provider, parameters,
                                         start, end)
        if existing is not None:
            logger.info("Combination %d of %d (%s): already stored as experiment %d (%s), "
                        "skipped", number, len(grid), describe(parameters), *existing)
            continue
        logger.info("Combination %d of %d (%s)", number, len(grid), describe(parameters))
        try:
            build_thunderstorms(engine, provider, ALGORITHM, parameters, start, end, logger)
        except Exception as error:
            raise RuntimeError(f"Combination {number} ({describe(parameters)}) failed: "
                               f"{error}") from error


def experiment_ids(engine: Engine, data_provider_id: int, provider: str,
                   grid: list[CellsearchParameters], start: datetime.datetime,
                   end: datetime.datetime) -> dict[CellsearchParameters, tuple[int, str] | None]:
    """For every combination, its experiment's ``(id, status)``; ``None`` if not stored."""
    with engine.connect() as connection:
        return {parameters: stored_experiment(connection, data_provider_id, provider, parameters,
                                              start, end)
                for parameters in grid}


def csv_filename(provider: str, start: datetime.datetime, end: datetime.datetime) -> str:
    """``cellsearch_tuomi_larjavaara_FMI_20180703T000000Z_20180704T000000Z.csv``.

    The algorithm, the provider as given to ``--provider``, and the period
    ``[start, end)`` in UTC, in the ISO 8601 basic format (no colons).
    """
    def instant(value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return f"{ALGORITHM}_{provider}_{instant(start)}_{instant(end)}.csv"


#: The CSV file's columns: the experiment, then the parameters swept.
CSV_COLUMNS = ["experiment_id", "attraction_radius_km", "max_waiting_time_min", "inertia",
               "time_distance_limit_min_km"]


def write_csv(path: Path, experiments: dict[CellsearchParameters, int]) -> None:
    """One row per experiment, in the order given; C off is an empty cell."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_COLUMNS)
        for parameters, experiment_id in experiments.items():
            limit = parameters.time_distance_limit_min_km
            writer.writerow([experiment_id, f"{parameters.attraction_radius_km:g}",
                             f"{parameters.max_waiting_time_min:g}", parameters.inertia,
                             "" if limit is None else f"{limit:g}"])


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("cellsearch-sensitivity")
    if args.end <= args.start:
        logger.error("--to must be later than --from")
        return 1
    try:
        engine, data_provider_id = connect(args, logger)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    try:
        grid = parameter_grid(READERS[args.provider].default_srid)
        logger.info("%d combinations over %s strokes (data provider %d), %s to %s", len(grid),
                    args.provider, data_provider_id, args.start.isoformat(), args.end.isoformat())
        try:
            run_grid(engine, data_provider_id, args.provider, grid, args.start, args.end, logger)
        except RuntimeError as error:
            logger.error("%s", error)
            return 1

        experiments = experiment_ids(engine, data_provider_id, args.provider, grid,
                                     args.start, args.end)
        unfinished = {parameters: stored for parameters, stored in experiments.items()
                      if stored is None or stored[1] != "complete"}
        for parameters, stored in unfinished.items():
            logger.warning("%s: %s", describe(parameters),
                           "not stored" if stored is None else f"experiment {stored[0]} is {stored[1]}")
        complete = {parameters: stored[0] for parameters, stored in experiments.items()
                    if parameters not in unfinished}
        logger.info("%d of %d combinations complete; their experiment ids: %s", len(complete),
                    len(grid), sorted(complete.values()))
        path = args.output_dir / csv_filename(args.provider, args.start, args.end)
        try:
            write_csv(path, complete)
        except OSError as error:
            logger.error("Cannot write %s: %s", path, error)
            return 1
        logger.info("Wrote %s (%d experiments)", path, len(complete))
    finally:
        engine.dispose()
    return 1 if unfinished else 0


if __name__ == "__main__":
    sys.exit(main())
