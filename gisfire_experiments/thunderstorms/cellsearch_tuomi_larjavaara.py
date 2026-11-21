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
named after the algorithm, the provider, the country if one is given, and the
period (see :func:`csv_filename`): one row per experiment, with its id, the
parameters swept (C off is an empty cell) and its statistics.

Statistics
----------

Counted in **flashes**, the units Cellsearch clusters, as the article does:

* ``thunderstorms``: how many thunderstorms (cells of at least N_min flashes).
* ``flashes_discarded_error``: flashes discarded before clustering, their
  location error being E_max or more. They are in no other column.
* ``flashes_clustered``: the flashes clustered, after E_max.
* ``flashes_isolated``, ``isolated_pct``: the clustered flashes in no
  thunderstorm (in cells smaller than N_min), and their share of
  ``flashes_clustered``.
* ``density_median_per_100km2``: the median over the thunderstorms of
  ``100 · flashes / area``, the area being the article's (``12·√det Σ``, the
  stored ``thunderstorm.area``, in km²), as in the QGIS views.
* ``diameter_mean_km``: the mean over the thunderstorms of the diameter of the
  circle of the same area, ``2·√(area / π)``.
* ``duration_median_min``: the median over the thunderstorms of the time from
  their first flash to their last, in minutes.

A thunderstorm with no area (its flashes on a line or at one point) counts in
``thunderstorms`` and the duration, not in the density or the diameter. A
statistic with no thunderstorm to take it over is an empty cell.

``--country NAME`` (a level-0 boundary, as named in ``admin_boundary``, e.g.
``Finland``) restricts the statistics to one country, while the runs still
cluster every stroke of the provider's area, so that no storm is cut at the
border. A flash is in the country when the stroke that represents it is; a
thunderstorm is when more than half of its flashes are. The flash counts are
then those of the country's flashes, recounted from the strokes as the builder
groups them; without ``--country`` they are the runs' own summaries.

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
import math
import os
import statistics
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import discard_by_error
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from src.apps.imports import common
from src.apps.thunderstorms import writers
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT
from src.apps.thunderstorms.build_thunderstorms import PIECE_STROKES
from src.apps.thunderstorms.build_thunderstorms import TABLES
from src.apps.thunderstorms.build_thunderstorms import build_thunderstorms
from src.apps.thunderstorms.build_thunderstorms import experiment_configuration
from src.apps.thunderstorms.build_thunderstorms import parse_instant
from src.apps.thunderstorms.build_thunderstorms import pieces
from src.apps.thunderstorms.build_thunderstorms import provider_id
from src.apps.thunderstorms.readers import READERS

#: The algorithm, by its name in the builder's ``ALGORITHMS``.
ALGORITHM = "cellsearch_tuomi_larjavaara"

#: R, the radius of attraction, in km.
ATTRACTION_RADII_KM = [5, 10, 15, 20, 25]

#: T, the maximum waiting time, in minutes.
MAX_WAITING_TIMES_MIN = [5, 10, 15, 20, 25]

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
    parser.add_argument("--country", default=None,
                        help="compute the statistics over this country only (a level-0 "
                             "boundary name, e.g. Finland); the runs still cluster the "
                             "provider's whole area")
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


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Storm:
    """One stored thunderstorm, as the statistics need it.

    Attributes
    ----------
    flashes : int
        Its flashes.
    flashes_in_region : int
        Those whose representative stroke is in the region (all of them
        without one).
    area_km2 : float or None
        The article's area; ``None`` when undefined.
    duration_min : float
        From its first flash to its last, in minutes.
    """

    flashes: int
    flashes_in_region: int
    area_km2: float | None
    duration_min: float


@dataclass(frozen=True)
class FlashCounts:
    """The flashes of a run (or of its region): clustered, and discarded by E_max."""

    clustered: int
    discarded: int


#: Every stored thunderstorm of an experiment, with its flashes (their
#: representative strokes) in the region and its duration from them.
STORMS_SQL = """
SELECT t.number_of_flashes AS flashes,
       count(*) FILTER (WHERE {in_region}) AS flashes_in_region,
       t.area AS area_km2,
       EXTRACT(EPOCH FROM max(l.date_time) - min(l.date_time)) / 60.0 AS duration_min
FROM thunderstorm AS t
JOIN thunderstorm_cellsearch_flash AS f ON f.thunderstorm_id = t.id
JOIN lightning AS l ON l.id = f.lightning_id
WHERE t.experiment_id = :experiment_id
GROUP BY t.id
ORDER BY t.id
"""

#: How many of the given strokes are in the region.
STROKES_IN_REGION_SQL = """
SELECT count(*) FROM lightning WHERE id = ANY(:ids) AND admin_boundary_id = ANY(:region)
"""


def country_ids(connection: Connection, name: str) -> list[int]:
    """The ``admin_boundary`` ids of the level-0 boundary ``name``; ``RuntimeError`` if none."""
    ids = list(connection.execute(text(
        "SELECT id FROM admin_boundary WHERE name = :name AND level = 0 ORDER BY id"),
        {"name": name}).scalars())
    if not ids:
        raise RuntimeError(f"No country named {name!r} in admin_boundary (level 0)")
    return ids


def stored_storms(connection: Connection, experiment_id: int,
                  region: list[int] | None) -> list[Storm]:
    """The experiment's thunderstorms, their flashes counted in ``region`` (ids)."""
    in_region = "l.admin_boundary_id = ANY(:region)" if region else "TRUE"
    rows = connection.execute(text(STORMS_SQL.format(in_region=in_region)),
                              {"experiment_id": experiment_id, "region": region or []})
    return [Storm(flashes=row.flashes, flashes_in_region=row.flashes_in_region,
                  area_km2=None if row.area_km2 is None else float(row.area_km2),
                  duration_min=float(row.duration_min)) for row in rows]


def summary_flash_counts(connection: Connection, experiment_id: int) -> FlashCounts:
    """The run's own flash counts, from its stored summary."""
    summary = connection.execute(text(
        "SELECT summary FROM thunderstorm_experiment WHERE id = :id"),
        {"id": experiment_id}).scalar_one()
    discarded = summary["flashes_discarded_error"]
    return FlashCounts(clustered=summary["flashes_total"] - discarded, discarded=discarded)


def region_flash_counts(connection: Connection, data_provider_id: int, provider: str,
                        start: datetime.datetime, end: datetime.datetime,
                        max_error_km: float, region: list[int]) -> FlashCounts:
    """The flashes of ``[start, end)`` whose representative stroke is in ``region``.

    The strokes are read and grouped as the builder does (its reader, ground
    strokes only, the same flashes and representatives), so the counts are
    those of the runs; E_max decides which are clustered and which discarded.
    """
    reader = READERS[provider]
    batches = reader.read(connection, data_provider_id, start, end, reader.default_srid)
    kept_ids: list[np.ndarray] = []
    discarded_ids: list[np.ndarray] = []
    # Pieces never cut a flash in two; the gap only says where they may be cut.
    gap_s = CellsearchParameters().max_waiting_time_min * 60.0
    for strokes in pieces(batches, gap_s, PIECE_STROKES):
        flashes = strokes_to_flashes(strokes)
        kept, _ = discard_by_error(flashes, max_error_km * 1000.0)
        kept_ids.append(flashes.representative_id[kept])
        discarded_ids.append(flashes.representative_id[~kept])

    def in_region(ids: list[np.ndarray]) -> int:
        if not ids:
            return 0
        return connection.execute(text(STROKES_IN_REGION_SQL), {
            "ids": np.concatenate(ids).tolist(), "region": region}).scalar_one()

    return FlashCounts(clustered=in_region(kept_ids), discarded=in_region(discarded_ids))


def thunderstorm_statistics(storms: list[Storm], counts: FlashCounts) -> dict[str, Any]:
    """The statistics of one experiment (see the module's docstring).

    A flash is isolated when it is clustered and in no thunderstorm: so every
    thunderstorm's flashes in the region count as not isolated, whether the
    thunderstorm itself is in the region (more than half its flashes) or not.
    """
    in_storms = sum(storm.flashes_in_region for storm in storms)
    isolated = counts.clustered - in_storms
    kept = [storm for storm in storms if 2 * storm.flashes_in_region > storm.flashes]
    with_area = [storm for storm in kept if storm.area_km2]
    return {
        "thunderstorms": len(kept),
        "flashes_discarded_error": counts.discarded,
        "flashes_clustered": counts.clustered,
        "flashes_isolated": isolated,
        "isolated_pct": 100.0 * isolated / counts.clustered if counts.clustered else None,
        "density_median_per_100km2": statistics.median(
            100.0 * storm.flashes / storm.area_km2 for storm in with_area) if with_area else None,
        "diameter_mean_km": statistics.fmean(
            2.0 * math.sqrt(storm.area_km2 / math.pi) for storm in with_area) if with_area else None,
        "duration_median_min": statistics.median(
            storm.duration_min for storm in kept) if kept else None,
    }


def experiment_statistics(engine: Engine, data_provider_id: int, provider: str,
                          experiments: dict[CellsearchParameters, int], start: datetime.datetime,
                          end: datetime.datetime, region: list[int] | None,
                          logger: logging.Logger) -> dict[CellsearchParameters, dict[str, Any]]:
    """For every experiment, its statistics, over ``region`` (ids) or the whole run."""
    results = {}
    region_counts: dict[float, FlashCounts] = {}
    with engine.connect() as connection:
        for parameters, experiment_id in experiments.items():
            if region:
                error_km = parameters.max_location_error_km
                if error_km not in region_counts:
                    region_counts[error_km] = region_flash_counts(
                        connection, data_provider_id, provider, start, end, error_km, region)
                counts = region_counts[error_km]
            else:
                counts = summary_flash_counts(connection, experiment_id)
            results[parameters] = thunderstorm_statistics(
                stored_storms(connection, experiment_id, region), counts)
        connection.rollback()
    logger.info("Statistics of %d experiment(s) computed", len(results))
    return results


# --------------------------------------------------------------------------
# The CSV file
# --------------------------------------------------------------------------

def csv_filename(provider: str, start: datetime.datetime, end: datetime.datetime,
                 country: str | None = None) -> str:
    """``cellsearch_tuomi_larjavaara_FMI_20180703T000000Z_20180704T000000Z.csv``.

    The algorithm, the provider as given to ``--provider``, the country if one
    is given (spaces as ``_``: ``..._FMI_Finland_...``), and the period
    ``[start, end)`` in UTC, in the ISO 8601 basic format (no colons).
    """
    def instant(value: datetime.datetime) -> str:
        return value.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    where = provider if country is None else f"{provider}_{country.replace(' ', '_')}"
    return f"{ALGORITHM}_{where}_{instant(start)}_{instant(end)}.csv"


#: The parameters swept, as the CSV file's columns.
PARAMETER_COLUMNS = ["attraction_radius_km", "max_waiting_time_min", "inertia",
                     "time_distance_limit_min_km"]

#: The statistics, as the CSV file's columns (see the module's docstring).
STATISTIC_COLUMNS = ["thunderstorms", "flashes_discarded_error", "flashes_clustered",
                     "flashes_isolated", "isolated_pct", "density_median_per_100km2",
                     "diameter_mean_km", "duration_median_min"]

#: The CSV file's columns: the experiment, the parameters swept, its statistics.
CSV_COLUMNS = ["experiment_id", *PARAMETER_COLUMNS, *STATISTIC_COLUMNS]


def _cell(value: Any) -> str:
    """A CSV cell: empty for ``None``, a float to 4 decimals, anything else as is."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_csv(path: Path, experiments: dict[CellsearchParameters, int],
              results: dict[CellsearchParameters, dict[str, Any]]) -> None:
    """One row per experiment, in the order given; C off is an empty cell."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_COLUMNS)
        for parameters, experiment_id in experiments.items():
            limit = parameters.time_distance_limit_min_km
            writer.writerow([experiment_id, f"{parameters.attraction_radius_km:g}",
                             f"{parameters.max_waiting_time_min:g}", parameters.inertia,
                             "" if limit is None else f"{limit:g}",
                             *(_cell(results[parameters][column]) for column in STATISTIC_COLUMNS)])


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
        region = None
        if args.country is not None:
            try:
                with engine.connect() as connection:
                    region = country_ids(connection, args.country)
            except RuntimeError as error:
                logger.error("%s", error)
                return 1
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
        results = experiment_statistics(engine, data_provider_id, args.provider, complete,
                                        args.start, args.end, region, logger)
        path = args.output_dir / csv_filename(args.provider, args.start, args.end, args.country)
        try:
            write_csv(path, complete, results)
        except OSError as error:
            logger.error("Cannot write %s: %s", path, error)
            return 1
        logger.info("Wrote %s (%d experiments)", path, len(complete))
    finally:
        engine.dispose()
    return 1 if unfinished else 0


if __name__ == "__main__":
    sys.exit(main())
