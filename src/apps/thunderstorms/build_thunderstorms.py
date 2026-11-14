#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build thunderstorms from one provider's strokes with a clustering algorithm.

::

    python3 -m src.apps.thunderstorms.build_thunderstorms \\
        --provider MeteoCat --from 2020-07-13T00:00Z --to 2020-07-14T00:00Z \\
        --algorithm cellsearch_tuomi_larjavaara [--time-distance-limit 50] ...

One run is one :class:`~src.data_model.thunderstorm.ThunderstormExperiment`:
the provider, the period, the stroke filter, the algorithm and its complete
parameters, the hull settings and the version of :mod:`gisfire_algorithms`.
The algorithm itself lives in :mod:`gisfire_algorithms.thunderstorm`; this
module reads the strokes (:mod:`src.apps.thunderstorms.readers`), runs it and
stores the result (:mod:`src.apps.thunderstorms.writers`).

Algorithms
----------

Each algorithm is one entry of :data:`ALGORITHMS`: its parameters dataclass
(the command-line flags are made from its fields: the name without its unit,
the type, the default), how to run it over a piece of strokes, and the writer
of its own table, if it has one. Pass ``--algorithm NAME --help`` to list an
algorithm's flags.

How a run goes
--------------

1. The parameters are validated and the provider looked up. A run whose whole
   configuration is already stored is refused (whatever that run's status:
   delete it first to run it again).
2. The experiment is inserted ``running`` and committed.
3. The strokes are streamed in time order and cut into **pieces** at quiet
   gaps longer than the algorithm's gap (Cellsearch: T, which closes every
   cell, so the result is the same as one run over everything). Each piece is
   clustered, carrying the label counter, and written and committed on its
   own, so a period of years needs neither the memory nor the transaction of
   all of it.
4. The window is strict, ``[from, to)``: a storm across a boundary becomes cut
   cells. The summary records ``cells_open_at_end`` (cells of any size whose
   latest flash is within the gap of ``to``, so a later flash could have
   joined them) and ``activity_before_start`` (accepted flashes within the
   gap before ``from``), and either one is warned about. Run long periods as
   one experiment.
5. The summary is stored and the experiment marked ``complete``. On any error,
   or an interrupt, its thunderstorms are deleted and it is marked ``failed``.

``--dry-run`` does everything in one transaction and rolls it back.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import logging
import os
import sys
import time
import typing

from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text

import gisfire_algorithms
import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from gisfire_algorithms.thunderstorm import CELLSEARCH_ALGORITHM
from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import cell_area_km2
from gisfire_algorithms.thunderstorm import cellsearch
from gisfire_algorithms.thunderstorm import discard_by_error
from gisfire_algorithms.thunderstorm import merge_summaries
from gisfire_algorithms.thunderstorm import split_at_gaps
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from src.apps.imports import common
from src.apps.thunderstorms import writers
from src.apps.thunderstorms.readers import READERS
from src.apps.thunderstorms.readers import StrokeReader
from src.apps.thunderstorms.readers import strokes_from_rows
from src.apps.thunderstorms.writers import Cells
from src.apps.thunderstorms.writers import CellsearchFlashes
from src.data_model.thunderstorm import DEFAULT_HULL_PARAMETERS

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: About how many strokes a piece holds before it is cut at the next quiet gap.
PIECE_STROKES = 200_000

#: How often, in flashes, the progress is logged.
PROGRESS_EVERY = 100_000

#: The tables a run reads or writes.
TABLES = ["lightning", "data_provider", "thunderstorm_experiment", "thunderstorm",
          "thunderstorm_lightning"]

PROVIDER_ID_SQL = "SELECT id FROM data_provider WHERE name = :name AND product = :product"


class DuplicateExperiment(RuntimeError):
    """The same configuration is already stored."""


# --------------------------------------------------------------------------
# One piece's result, whatever the algorithm
# --------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class Piece:
    """What an algorithm found in one piece of strokes.

    Attributes
    ----------
    cells : Cells
        The kept cells, for the generic tables.
    specific : Any
        The algorithm's own output, for its ``write_specific``.
    summary : dict
        The piece's summary; pieces are added with ``merge_summaries``.
    cell_last_t : numpy.ndarray of float64
        For every cell of the piece, kept or not, the time of its latest flash
        (seconds since the epoch): the cells within the gap of the end of the
        period may have been cut by it.
    next_label : int
        The first label of the next piece.
    flashes : int
        How many flashes (or strokes, for a stroke-based algorithm) the piece
        held, for the progress.
    """

    cells: Cells
    specific: Any
    summary: dict[str, Any]
    cell_last_t: np.ndarray
    next_label: int
    flashes: int


@dataclass(frozen=True)
class Algorithm:
    """One clustering algorithm the application can run.

    Attributes
    ----------
    name : str
        The value of ``thunderstorm_experiment.algorithm``.
    parameters : class
        The frozen parameters dataclass; its fields become the flags.
    run : callable
        ``run(strokes, parameters, first_label) -> Piece``.
    gap_s : callable
        ``gap_s(parameters)``: a quiet gap longer than this (seconds) closes
        everything, so the input can be cut there.
    active : callable
        ``active(strokes, parameters)``: whether these strokes hold anything
        the algorithm would cluster (for the activity before the window).
    write_specific : callable or None
        ``write_specific(connection, experiment_id, piece.specific, srid)``.
    flag_help : dict
        Help text for each parameter's flag.
    """

    name: str
    parameters: type
    run: Callable[[Strokes, Any, int], Piece]
    gap_s: Callable[[Any], float]
    active: Callable[[Strokes, Any], bool]
    write_specific: Callable[[Connection, int, Any, int], None] | None = None
    flag_help: dict[str, str] = dataclasses.field(default_factory=dict)


# --------------------------------------------------------------------------
# Cellsearch (Tuomi & Larjavaara 2005)
# --------------------------------------------------------------------------

def _groups(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """The distinct labels, the stable order sorting by label, and each label's indices."""
    order = np.argsort(labels, kind="stable")
    if not len(labels):
        return labels, order, []
    unique, starts = np.unique(labels[order], return_index=True)
    return unique, order, np.split(order, starts[1:])


def run_cellsearch(strokes: Strokes, params: CellsearchParameters, first_label: int) -> Piece:
    """Cellsearch over one piece: strokes → flashes → cells.

    Every stroke of a flash in a kept cell is linked; the hull and the area are
    drawn over the flashes' representative strokes, the points Cellsearch
    clustered.
    """
    flashes = strokes_to_flashes(strokes)
    result = cellsearch(flashes, params, first_label=first_label)
    kept = result.kept_flash_mask()
    index = np.flatnonzero(kept)
    flash_label = result.label[index]

    labels, _, members = _groups(flash_label)
    x = flashes.x[index]
    y = flashes.y[index]
    area = [cell_area_km2(x[group] / 1000.0, y[group] / 1000.0) for group in members]

    stroke_flash = flashes.stroke_flash_index
    linked = kept[stroke_flash]
    cells = Cells(
        label=labels,
        number_of_flashes=np.array([len(group) for group in members], dtype=np.int64),
        area=area,
        link_label=result.label[stroke_flash[linked]],
        link_lightning_id=strokes.ids[linked],
        hull_label=flash_label,
        hull_x=x,
        hull_y=y,
    )
    specific = CellsearchFlashes(
        label=flash_label,
        sequence=result.sequence[index].astype(np.int64),
        lightning_id=flashes.representative_id[index],
        centre_x=result.centre_x[index],
        centre_y=result.centre_y[index],
    )
    # Every cell's latest flash: the last occurrence of its label (time order).
    assigned = np.flatnonzero(result.label >= 0)
    reversed_labels = result.label[assigned][::-1]
    _, last_from_end = np.unique(reversed_labels, return_index=True)
    cell_last_t = flashes.t[assigned[len(assigned) - 1 - last_from_end]]
    return Piece(cells=cells, specific=specific, summary=result.summary,
                 cell_last_t=cell_last_t, next_label=result.next_label, flashes=len(flashes))


def cellsearch_active(strokes: Strokes, params: CellsearchParameters) -> bool:
    """Whether any flash of these strokes passes the location-error filter."""
    flashes = strokes_to_flashes(strokes)
    kept, _ = discard_by_error(flashes, params.max_location_error_km * 1000.0)
    return bool(kept.any())


#: The algorithms, by the name given to ``--algorithm``.
ALGORITHMS: dict[str, Algorithm] = {
    "cellsearch_tuomi_larjavaara": Algorithm(
        name=CELLSEARCH_ALGORITHM,
        parameters=CellsearchParameters,
        run=run_cellsearch,
        gap_s=lambda params: params.max_waiting_time_min * 60.0,
        active=cellsearch_active,
        write_specific=writers.write_cellsearch_flashes,
        flag_help={
            "attraction_radius_km": "R, the radius of attraction, in km",
            "max_waiting_time_min": "T, the maximum waiting (delay) time, in minutes",
            "time_distance_limit_min_km": "C, the time-distance limit, in min·km; "
                                          "off when not given",
            "inertia": "I, the number of latest flashes the cell centre is the mean of",
            "max_location_error_km": "E_max: flashes with this location error or more "
                                     "are discarded, in km",
            "min_flashes": "N_min: cells with fewer flashes are not stored (at least 3)",
            "srid": "EPSG code of the projected CRS (metres) the algorithm works in",
        },
    ),
}


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

#: Unit suffixes left out of a parameter's flag.
UNIT_SUFFIXES = ("_min_km", "_km", "_min")


def _split_unit(field_name: str) -> tuple[str, str]:
    """``attraction_radius_km`` → ``("attraction_radius", "km")``; no unit → ``""``."""
    for suffix in UNIT_SUFFIXES:
        if field_name.endswith(suffix):
            return field_name[:-len(suffix)], suffix[1:]
    return field_name, ""


def flag_name(field_name: str) -> str:
    """``attraction_radius_km`` → ``--attraction-radius``."""
    return "--" + _split_unit(field_name)[0].replace("_", "-")


def flag_metavar(field_name: str) -> str:
    """``attraction_radius_km`` → ``KM``; ``inertia`` → ``INERTIA``."""
    name, unit = _split_unit(field_name)
    return (unit or name).upper()


def _value_type(annotation: Any) -> type:
    """``float``, ``int`` or ``float | None`` → the type that parses the flag."""
    options = [option for option in typing.get_args(annotation) if option is not type(None)]
    return options[0] if options else annotation


def add_algorithm_arguments(parser: argparse.ArgumentParser, key: str, algorithm: Algorithm) -> None:
    """One flag per field of the algorithm's parameters dataclass."""
    group = parser.add_argument_group(f"{key} parameters")
    hints = typing.get_type_hints(algorithm.parameters)
    for field in dataclasses.fields(algorithm.parameters):
        default = field.default
        description = algorithm.flag_help.get(field.name, field.name)
        group.add_argument(flag_name(field.name), dest=f"param_{field.name}",
                           type=_value_type(hints[field.name]), default=default,
                           metavar=flag_metavar(field.name),
                           help=f"{description} (default: {default})")


def parse_instant(value: str) -> datetime.datetime:
    """An ISO 8601 date or instant; one with no offset is UTC."""
    try:
        instant = datetime.datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not an ISO 8601 date or instant: {value!r}") from error
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=datetime.timezone.utc)
    return instant.astimezone(datetime.timezone.utc)


def build_parser(algorithm: str | None) -> argparse.ArgumentParser:
    """The parser, with the flags of ``algorithm`` if one is chosen."""
    parser = argparse.ArgumentParser(
        description="Cluster one provider's lightning strokes into thunderstorms and store "
                    "the run as a thunderstorm experiment.",
        epilog="Pass --algorithm NAME --help to see that algorithm's parameters. The period "
               "is half-open, [from, to); an instant with no offset is UTC. Database "
               "settings not given here are read from the environment (.env).",
    )
    parser.add_argument("--provider", required=True, choices=sorted(READERS),
                        help="whose strokes to cluster")
    parser.add_argument("--from", dest="start", required=True, type=parse_instant,
                        help="first instant of the period (included)")
    parser.add_argument("--to", dest="end", required=True, type=parse_instant,
                        help="end of the period (excluded)")
    parser.add_argument("--algorithm", required=True, choices=sorted(ALGORITHMS),
                        help="the clustering algorithm")
    parser.add_argument("--dry-run", action="store_true",
                        help="run everything and roll it back: nothing is stored")
    parser.add_argument("--log-file", type=str, default=None,
                        help="also write the log to this file")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    common.add_database_arguments(parser)
    if algorithm in ALGORITHMS:
        add_algorithm_arguments(parser, algorithm, ALGORITHMS[algorithm])
    return parser


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line in two steps: the algorithm, then its flags."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--algorithm")
    known, _ = pre.parse_known_args(argv)
    return build_parser(known.algorithm).parse_args(argv)


def parameters_from(args: argparse.Namespace, algorithm: Algorithm) -> Any:
    """The algorithm's parameters from the flags; ``ValueError`` if invalid."""
    values = {field.name: getattr(args, f"param_{field.name}")
              for field in dataclasses.fields(algorithm.parameters)}
    return algorithm.parameters(**values)


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------

def _take(strokes: Strokes, part: slice) -> Strokes:
    return Strokes(ids=strokes.ids[part], flash_keys=strokes.flash_keys[part], t=strokes.t[part],
                   x=strokes.x[part], y=strokes.y[part], error=strokes.error[part])


def _concat(a: Strokes, b: Strokes) -> Strokes:
    return Strokes(*(np.concatenate((getattr(a, name), getattr(b, name)))
                     for name in ("ids", "flash_keys", "t", "x", "y", "error")))


def _cut(strokes: Strokes, gap_s: float) -> int:
    """Where to cut: the start of the last stretch after a gap longer than ``gap_s``.

    Zero (do not cut) when there is no such gap, or when a flash would be cut in
    two: a flash whose strokes lie more than ``gap_s`` apart.
    """
    slices = split_at_gaps(strokes.t, gap_s)
    for part in reversed(slices[1:]):
        cut = part.start
        if not np.intersect1d(strokes.flash_keys[:cut], strokes.flash_keys[cut:]).size:
            return cut
    return 0


def split_before(batches: Iterator[Strokes], start_s: float,
                 before: list[Strokes]) -> Iterator[Strokes]:
    """The batches from ``start_s`` on; the strokes before it go to ``before``.

    The batches are in time order, so the strokes before ``start_s`` are a
    prefix of the stream. Both times are the same microsecond instant rounded
    to the nearest double, so a stroke exactly at ``start_s`` is not before it.
    """
    for strokes in batches:
        cut = int(np.searchsorted(strokes.t, start_s, side="left"))
        if cut:
            before.append(_take(strokes, slice(0, cut)))
        if cut < len(strokes):
            yield _take(strokes, slice(cut, None))


def pieces(batches: Iterator[Strokes], gap_s: float, piece_strokes: int) -> Iterator[Strokes]:
    """Group stroke batches into pieces of about ``piece_strokes``, cut at quiet gaps.

    No flash is split between pieces, and a piece ends only where the next one
    starts more than ``gap_s`` later.
    """
    pending: Strokes | None = None
    for batch in batches:
        pending = batch if pending is None else _concat(pending, batch)
        if len(pending) >= piece_strokes:
            cut = _cut(pending, gap_s)
            if cut:
                yield _take(pending, slice(0, cut))
                pending = _take(pending, slice(cut, None))
    if pending is not None and len(pending):
        yield pending


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def provider_id(connection: Connection, reader: StrokeReader) -> int:
    """The provider's ``data_provider.id``; ``RuntimeError`` if it is not there."""
    identifier = connection.execute(text(PROVIDER_ID_SQL), {
        "name": reader.provider_name, "product": reader.provider_product}).scalar()
    if identifier is None:
        raise RuntimeError(f"No data provider {reader.provider_name!r} ({reader.provider_product}) "
                           f"in the database: import its strokes first")
    return identifier


def build_thunderstorms(engine: Engine, provider: str, algorithm_key: str, parameters: Any,
                        start: datetime.datetime, end: datetime.datetime,
                        logger: logging.Logger, dry_run: bool = False,
                        piece_strokes: int | None = None) -> dict[str, Any]:
    """Run one experiment and store it; its summary.

    Raises
    ------
    DuplicateExperiment
        If the configuration is already stored.
    RuntimeError
        If the provider is not in the database or a table is missing.
    """
    if end <= start:
        raise ValueError("--to must be later than --from")
    reader = READERS[provider]
    algorithm = ALGORITHMS[algorithm_key]
    srid = parameters.srid
    hull_parameters = {**DEFAULT_HULL_PARAMETERS, "srid": srid}
    gap_s = algorithm.gap_s(parameters)
    piece_strokes = piece_strokes or PIECE_STROKES
    common.require_tables(engine, TABLES, logger)

    with engine.connect() as reading, engine.connect() as writing:
        data_provider_id = provider_id(writing, reader)
        configuration = {
            "data_provider_id": data_provider_id,
            "algorithm": algorithm.name,
            "parameters": parameters.to_dict(),
            "lightning_filter": dict(reader.lightning_filter),
            "hull_parameters": hull_parameters,
            "date_time_start": start,
            "date_time_end": end,
            "software_version": gisfire_algorithms.__version__,
        }
        existing = writers.find_experiment(writing, configuration)
        if existing is not None:
            writing.rollback()
            raise DuplicateExperiment(
                f"This configuration is already stored as thunderstorm experiment {existing[0]} "
                f"({existing[1]}); delete it first to run it again")
        experiment_id = writers.insert_experiment(writing, configuration)
        if not dry_run:
            writing.commit()
        logger.info("%s experiment %d: %s on %s strokes, %s to %s, %s",
                    "Dry-run" if dry_run else "Running", experiment_id, algorithm.name, provider,
                    start.isoformat(), end.isoformat(), parameters.to_dict())

        try:
            summary = _run(reading, writing, reader, algorithm, parameters, data_provider_id,
                           experiment_id, start, end, gap_s, hull_parameters, piece_strokes,
                           logger, dry_run)
            writers.complete_experiment(writing, experiment_id, summary)
            if dry_run:
                writing.rollback()
            else:
                writing.commit()
        except BaseException:
            writing.rollback()
            if not dry_run:
                writers.fail_experiment(writing, experiment_id)
                writing.commit()
                logger.error("Experiment %d failed: its thunderstorms were deleted", experiment_id)
            raise
        finally:
            reading.rollback()
    return summary


def _run(reading: Connection, writing: Connection, reader: StrokeReader, algorithm: Algorithm,
         parameters: Any, data_provider_id: int, experiment_id: int, start: datetime.datetime,
         end: datetime.datetime, gap_s: float, hull_parameters: dict[str, Any],
         piece_strokes: int, logger: logging.Logger, dry_run: bool) -> dict[str, Any]:
    """Stream, cluster and write every piece; the run's summary."""
    srid = parameters.srid
    started = time.monotonic()
    summary: dict[str, Any] | None = None
    next_label = 1
    open_at_end = 0
    open_from = end.timestamp() - gap_s
    strokes_total = 0
    flashes_done = 0
    next_report = PROGRESS_EVERY
    stored = 0

    # One read from ``start - gap``: the strokes before ``start`` only tell
    # whether the period may cut a cell at its start (``activity_before_start``).
    lookback = start - datetime.timedelta(seconds=gap_s)
    before: list[Strokes] = []
    batches = split_before(reader.read(reading, data_provider_id, lookback, end, srid),
                           start.timestamp(), before)
    for strokes in pieces(batches, gap_s, piece_strokes):
        piece = algorithm.run(strokes, parameters, next_label)
        writers.write_cells(writing, experiment_id, piece.cells, hull_parameters)
        if algorithm.write_specific is not None:
            algorithm.write_specific(writing, experiment_id, piece.specific, srid)
        if not dry_run:
            writing.commit()
        summary = piece.summary if summary is None else merge_summaries(summary, piece.summary)
        next_label = piece.next_label
        open_at_end += int(np.count_nonzero(piece.cell_last_t >= open_from))
        strokes_total += len(strokes)
        flashes_done += piece.flashes
        stored += len(piece.cells)
        if flashes_done >= next_report:
            logger.info("%d stroke(s), %d flash(es) so far, %d thunderstorm(s) stored",
                        strokes_total, flashes_done, stored)
            next_report = (flashes_done // PROGRESS_EVERY + 1) * PROGRESS_EVERY

    if summary is None:
        # No strokes: the algorithm's empty summary.
        summary = algorithm.run(strokes_from_rows([]), parameters, 1).summary
        logger.warning("No strokes in the period")

    activity_before_start = any(algorithm.active(strokes, parameters) for strokes in before)

    summary = {**summary, "strokes_total": strokes_total, "cells_open_at_end": open_at_end,
               "activity_before_start": activity_before_start}
    if open_at_end:
        logger.warning("%d cell(s) still open at the end of the period (a flash within "
                       "%.0f min of it) may have been cut by it", open_at_end, gap_s / 60.0)
    if activity_before_start:
        logger.warning("There is activity within %.0f min before the start of the period: cells "
                       "at its start may have been cut by it", gap_s / 60.0)
    logger.info("%s %d stroke(s) into %d thunderstorm(s) in %.0fs: %s",
                "Would cluster" if dry_run else "Clustered", strokes_total, stored,
                time.monotonic() - started,
                {key: value for key, value in summary.items() if key != "size_classes"})
    return summary


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("build-thunderstorms")
    logger.setLevel(args.log_level)
    file_handler = None
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)
    try:
        return _main(args, logger)
    finally:
        if file_handler is not None:
            logger.removeHandler(file_handler)
            file_handler.close()


def _main(args: argparse.Namespace, logger: logging.Logger) -> int:

    algorithm = ALGORITHMS[args.algorithm]
    try:
        parameters = parameters_from(args, algorithm)
        if args.end <= args.start:
            raise ValueError("--to must be later than --from")
        settings = common.resolve_database_settings(args)
    except (ValueError, RuntimeError) as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        build_thunderstorms(engine, args.provider, args.algorithm, parameters, args.start,
                            args.end, logger, dry_run=args.dry_run)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Build failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
