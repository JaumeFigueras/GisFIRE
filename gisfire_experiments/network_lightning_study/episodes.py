#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The lightning episodes of a network over its zone, and their flash counts.

::

    python3 -m gisfire_experiments.network_lightning_study.episodes \\
        --provider FMI --from 2018-01-01 --to 2019-01-01 --gap 5 --csv fmi_2018.csv

Computes the episodes of rule 1 of :doc:`/algorithms/thunderstorm_rules`, counts
the flashes and strokes of each, and writes two CSV files: one row per episode in
``--csv``, and the quartiles of the episodes' flashes beside it. Nothing is
written to the database.

Command line
------------

``--provider``
    The network: ``FMI``, ``MeteoCat`` or ``USWFS``, as the thunderstorm builder
    names them. It also chooses the nominal region (see `The zone`_).
``--from``, ``--to``
    The period an episode must start in, half-open; an ISO 8601 date or instant,
    UTC when it has no offset (a date alone is 00:00).
``--gap``
    G, in hours: the silence of the zone that ends an episode. Required, since the
    rules leave its value to a study.
``--min-flashes``
    Leave out of both files the episodes with fewer zone flashes (default
    :data:`MIN_FLASHES`, 100).
``--csv``
    The episodes file; the quartiles file goes beside it (see `The files`_).

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument (``--db-host``,
``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``).

The zone
--------

Each network has a fixed nominal region (:data:`REGIONS`): FMI OCHA's Finland,
MeteoCat IGN's Catalonia, USWFS the Census Bureau's Alaska. Finland is OCHA's
``FIN`` alone: the Åland Islands, which OCHA publishes as an entity of their own
(``ALA``), are not part of the region, and count only where they lie within 50 km
of it (decided on 2026-11-22). The **zone** is
everything within 50 km of it (:data:`ZONE_BUFFER_M`), measured in the network's
projected CRS (the reader's ``default_srid``: EPSG:3067, 25831, 3338). A stroke is
in the zone when its distance to the region is at most 50 km, tested with shapely
on the region's polygon: exact, with no buffer polygon to approximate it (a 50 km
buffer of OCHA's Finland, 3.75 M vertices, takes PostGIS more than 10 minutes).

Flashes and episodes
--------------------

- Only cloud-to-ground strokes are read, with the thunderstorm builder's readers
  (MeteoCat: its newest network), and the **flashes are those published** (for
  Alaska, the import's NLDN grouping): this study does not regroup the flashes
  that last more than 2 s.
- A **zone flash** has at least one stroke in the zone. Its time is that of its
  representative stroke, the most accurate
  (:func:`~gisfire_algorithms.thunderstorm.flashes.strokes_to_flashes`), even when
  that stroke lies outside the zone.
- An **episode** is cut wherever two consecutive zone flashes are more than G
  (``--gap``) apart: :func:`~gisfire_algorithms.thunderstorm.chunking.split_at_gaps`
  over the zone flashes' times. A gap of exactly G does not cut.
- An episode's ``flashes`` are its zone flashes and its ``strokes`` the strokes of
  those flashes that are **inside the zone**.

The ends of the period
----------------------

An episode belongs to the run when its first zone flash is in ``[--from, --to)``.
The strokes are read from ``--from`` − G, so an episode already running at
``--from`` is recognised and left out: it belongs to the previous period. An
episode still running at ``--to`` is followed past it, a day at a time
(:data:`FOLLOW_STEP`), until G passes with no zone flash. Consecutive runs (year
after year, say) therefore give every episode once, and whole. If the data end
before the last episode could close, it ends at its last flash and the log warns.

Episodes with fewer than ``--min-flashes`` zone flashes (default 100) are left out
of both files; they still count as episodes for the rule, so they still separate
the episodes on either side of them.

The files
---------

``--csv``: one row per kept episode, in time order — ``episode`` (numbered from 1),
``start`` and ``end`` (its first and last zone flashes, UTC, ISO 8601),
``duration_s``, ``flashes`` and ``strokes``.

``<stem>_quartiles.csv`` beside it: one row, the number of kept ``episodes``, the
minimum, quartiles and maximum of their flashes (``flashes_min``, ``flashes_q1``,
``flashes_median``, ``flashes_q3``, ``flashes_max``), with NumPy's default method
(linear interpolation, Hyndman & Fan's type 7), and how many episodes each quarter
holds: ``episodes_to_q1`` (flashes ≤ Q1), ``episodes_q1_to_median`` (Q1 < flashes ≤
median), ``episodes_median_to_q3`` (median < flashes ≤ Q3) and
``episodes_q3_to_max`` (flashes > Q3). An episode on a quartile is in the lower
quarter. Each quarter holds about a quarter of the episodes by construction; the
counts differ when the number of episodes is not a multiple of 4, or when episodes
tie at a quartile. Empty cells when no episode is kept.

All the strokes of the period are held in memory: a year at a time is the natural
run. While they are read, the progress is shown in hours of the period read
(``Hours read: ...``), since the strokes come in time order: a bar redrawn in
place on a terminal; a log line every 30 days of the period
(:data:`PROGRESS_EVERY_H`), and one at the end, when the output goes to a file. The
reads past ``--to`` log a line each.

An example: FMI 2018
--------------------

FMI's 2018 with G = 5 h, run on 2026-11-22: 1 046 016 ground strokes read from
2017-12-31 19:00 UTC (``--from`` − G), 274 147 of them in the zone, and 96
episodes starting in 2018, 38 of them with at least 100 zone flashes, in 28 s.
The first rows of ``fmi_2018.csv``::

    episode,start,end,duration_s,flashes,strokes
    1,2018-04-20T20:01:53.000+00:00,2018-04-21T02:04:11.000+00:00,21738.000,126,177
    2,2018-05-14T03:36:56.000+00:00,2018-05-14T20:50:22.000+00:00,62006.000,172,232
    3,2018-05-16T09:12:19.000+00:00,2018-05-18T12:54:54.000+00:00,186155.000,4890,7380

and ``fmi_2018_quartiles.csv``::

    episodes,flashes_min,flashes_q1,flashes_median,flashes_q3,flashes_max,episodes_to_q1,episodes_q1_to_median,episodes_median_to_q3,episodes_q3_to_max
    38,110.00,180.75,619.50,2425.00,68377.00,10,9,9,10

The largest episode, 2018-08-01 06:56 to 08-06 18:03 UTC, holds 68 377 zone
flashes over five and a half days: with G = 5 h the zone was never silent for
long enough to end it.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import math
import os
import sys

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely

from sqlalchemy import Connection
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from gisfire_algorithms.thunderstorm import Strokes
from gisfire_algorithms.thunderstorm import split_at_gaps
from gisfire_algorithms.thunderstorm import strokes_to_flashes
from src.apps.imports import common
from src.apps.thunderstorms.build_thunderstorms import LOG_FORMAT
from src.apps.thunderstorms.build_thunderstorms import parse_instant
from src.apps.thunderstorms.build_thunderstorms import provider_id
from src.apps.thunderstorms.readers import READERS
from src.apps.thunderstorms.readers import strokes_from_rows
from src.providers import alaska_uswfs
from src.providers import catalonia_meteocat
from src.providers import finland_fmi

UTC = datetime.timezone.utc

#: The zone: everything within this distance of the region, in metres of the
#: network's projected CRS.
ZONE_BUFFER_M = 50_000.0

#: Episodes with fewer zone flashes are left out of both files, unless
#: ``--min-flashes`` says otherwise.
MIN_FLASHES = 100

#: How much further each read reaches when an episode is still running at ``--to``.
FOLLOW_STEP = datetime.timedelta(days=1)

#: Hours of the period read between two progress log lines, when the output is not a
#: terminal (on a terminal the bar is redrawn in place instead).
PROGRESS_EVERY_H = 30 * 24


@dataclass(frozen=True)
class Region:
    """A network's nominal region: one boundary row, found by one column of its source.

    Attributes
    ----------
    table : str
        The boundary's provider table (``ocha_admin_boundary``, ...), joined to
        ``admin_boundary`` as ``p``.
    column : str
        The column that identifies the boundary, qualified: ``p.`` for the
        provider table, ``b.`` for ``admin_boundary``.
    value : str
        Its value.
    description : str
        What the boundary is, for the messages.
    """

    table: str
    column: str
    value: str
    description: str


#: Each network's nominal region (see the thunderstorm rules), by the name given to
#: ``--provider``.
REGIONS = {
    # OCHA's Finland alone: the Åland Islands are an OCHA entity of their own (ALA),
    # and are not part of the region (decided on 2026-11-22).
    finland_fmi.PROVIDER_NAME: Region(
        "ocha_admin_boundary", "p.iso_3", "FIN", "OCHA's Finland (iso_3 FIN)"),
    catalonia_meteocat.PROVIDER_NAME: Region(
        "ign_admin_boundary", "b.source_id", "34090000000",
        "IGN's Catalonia (NATCODE 34090000000)"),
    alaska_uswfs.PROVIDER_NAME: Region(
        "census_admin_boundary", "b.source_id", "02", "the Census Bureau's Alaska (GEOID 02)"),
}

#: The region's polygon in the network's projected CRS.
REGION_SQL = """
SELECT b.id, ST_AsBinary(ST_Transform(b.geometry, :srid)) AS wkb
FROM admin_boundary AS b
JOIN {table} AS p ON p.id = b.id
WHERE {column} = :value
ORDER BY b.id
"""

#: Whether the provider has any stroke at or after an instant.
DATA_AFTER_SQL = """
SELECT EXISTS (SELECT 1 FROM lightning WHERE data_provider_id = :provider_id AND date_time >= :at)
"""

#: The episodes file's columns.
EPISODE_COLUMNS = ["episode", "start", "end", "duration_s", "flashes", "strokes"]

#: The quartiles file's columns.
QUARTILE_COLUMNS = ["episodes", "flashes_min", "flashes_q1", "flashes_median", "flashes_q3",
                    "flashes_max", "episodes_to_q1", "episodes_q1_to_median",
                    "episodes_median_to_q3", "episodes_q3_to_max"]


@dataclass(frozen=True)
class Episode:
    """One episode: its first and last zone flashes (seconds since the epoch), its zone
    flashes and their strokes inside the zone."""

    start_s: float
    end_s: float
    flashes: int
    strokes: int


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The provider, the period, G, the minimum, the file and the database settings."""
    parser = argparse.ArgumentParser(
        description="The lightning episodes of a network over its zone, and the quartiles of "
                    "their flashes.",
        epilog="The period is half-open, [from, to); an instant with no offset is UTC. "
               "Database settings not given here are read from the environment (.env).",
    )
    parser.add_argument("--provider", required=True, choices=sorted(READERS),
                        help="whose strokes, and so which nominal region")
    parser.add_argument("--from", dest="start", required=True, type=parse_instant,
                        help="first instant an episode may start at (included)")
    parser.add_argument("--to", dest="end", required=True, type=parse_instant,
                        help="end of the period an episode must start in (excluded)")
    parser.add_argument("--gap", required=True, type=float, metavar="HOURS",
                        help="G, in hours: a longer silence of the zone ends an episode")
    parser.add_argument("--min-flashes", type=int, default=MIN_FLASHES, metavar="N",
                        help=f"leave out the episodes with fewer zone flashes "
                             f"(default: {MIN_FLASHES})")
    parser.add_argument("--csv", required=True, type=Path, metavar="FILE",
                        help="the episodes file; the quartiles go to FILE's stem + _quartiles")
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    common.add_database_arguments(parser)
    args = parser.parse_args(argv)
    if args.end <= args.start:
        parser.error("--to must be later than --from")
    if not args.gap > 0:
        parser.error("--gap must be positive")
    if args.min_flashes < 1:
        parser.error("--min-flashes must be at least 1")
    return args


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def read_region(connection: Connection, provider: str) -> shapely.Geometry:
    """The provider's nominal region, in its projected CRS, prepared for the zone test.

    Raises
    ------
    RuntimeError
        If the boundary is not in the database, or more than one row matches (two
        editions of its source, say).
    """
    region = REGIONS[provider]
    rows = connection.execute(text(REGION_SQL.format(table=region.table, column=region.column)),
                              {"srid": READERS[provider].default_srid,
                               "value": region.value}).all()
    if not rows:
        raise RuntimeError(f"No boundary for {region.description} in the database: import it first")
    if len(rows) > 1:
        raise RuntimeError(f"{len(rows)} boundaries match {region.description} (admin_boundary "
                           f"ids {', '.join(str(row.id) for row in rows)}): keep one")
    geometry = shapely.from_wkb(bytes(rows[0].wkb))
    shapely.prepare(geometry)
    return geometry


def concatenate(parts: list[Strokes]) -> Strokes:
    """The strokes of consecutive reads as one :class:`Strokes`."""
    if not parts:
        return strokes_from_rows([])
    return Strokes(*(np.concatenate([getattr(part, name) for part in parts])
                     for name in ("ids", "flash_keys", "t", "x", "y", "error")))


def read_strokes(connection: Connection, provider: str, data_provider_id: int,
                 start: datetime.datetime, end: datetime.datetime, region: shapely.Geometry,
                 progress: common.ProgressReporter | None = None) -> tuple[Strokes, np.ndarray]:
    """The ground strokes of ``[start, end)`` and, for each, whether it is in the zone.

    ``progress``, if given, counts the whole hours from ``start`` that the batches have
    reached (they come in time order), and is finished at ``end``.
    """
    reader = READERS[provider]
    parts, inside = [], []
    for batch in reader.read(connection, data_provider_id, start, end, reader.default_srid):
        parts.append(batch)
        inside.append(shapely.dwithin(region, shapely.points(batch.x, batch.y), ZONE_BUFFER_M))
        if progress is not None:
            progress.advance(int((batch.t[-1] - start.timestamp()) // 3600) - progress.count)
    if progress is not None:
        progress.advance(progress.total - progress.count)
        progress.finish()
    return concatenate(parts), (np.concatenate(inside) if inside else np.empty(0, dtype=bool))


# --------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------

def zone_flashes(strokes: Strokes, inside: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The zone flashes' times, in order, and how many of each one's strokes are in the zone.

    A flash is a zone flash when at least one of its strokes is in the zone; its time is
    its representative stroke's.
    """
    flashes = strokes_to_flashes(strokes)
    counts = np.bincount(flashes.stroke_flash_index, weights=inside.astype(np.float64),
                         minlength=len(flashes)).astype(np.int64)
    zone = counts > 0
    return flashes.t[zone], counts[zone]


def find_episodes(times: np.ndarray, zone_strokes: np.ndarray, gap_s: float) -> list[Episode]:
    """The episodes of rule 1: the zone flashes cut wherever two are more than ``gap_s`` apart."""
    return [Episode(start_s=float(times[piece.start]), end_s=float(times[piece.stop - 1]),
                    flashes=piece.stop - piece.start, strokes=int(zone_strokes[piece].sum()))
            for piece in split_at_gaps(times, gap_s)]


def follow(episodes: list[Episode], start_s: float, end_s: float, read_end_s: float,
           gap_s: float) -> bool:
    """Whether the last episode starts in the period and may not have ended by ``read_end_s``.

    It has ended once G has passed after its last flash with no zone flash: a zone flash
    exactly G later would still belong to it.
    """
    if not episodes:
        return False
    last = episodes[-1]
    return start_s <= last.start_s < end_s and last.end_s + gap_s >= read_end_s


def period_episodes(engine: Engine, provider: str, data_provider_id: int,
                    region: shapely.Geometry, start: datetime.datetime, end: datetime.datetime,
                    gap: datetime.timedelta, logger: logging.Logger) -> list[Episode]:
    """The episodes that start in ``[start, end)``, followed past ``end`` until they end.

    Read in a read-only transaction, from ``start`` − G; the episode already running at
    ``start``, if any, is left out (and logged).
    """
    gap_s = gap.total_seconds()
    start_s, end_s = start.timestamp(), end.timestamp()
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        hours = math.ceil((end - (start - gap)).total_seconds() / 3600)
        progress = common.ProgressReporter(hours, "Hours read", logger,
                                           log_every=PROGRESS_EVERY_H)
        strokes, inside = read_strokes(connection, provider, data_provider_id, start - gap, end,
                                       region, progress)
        logger.info("%d ground stroke(s) read from %s, %d in the zone", len(strokes),
                    (start - gap).isoformat(), int(inside.sum()))
        read_end = end
        while True:
            episodes = find_episodes(*zone_flashes(strokes, inside), gap_s)
            if not follow(episodes, start_s, end_s, read_end.timestamp(), gap_s):
                break
            more, more_inside = read_strokes(connection, provider, data_provider_id, read_end,
                                             read_end + FOLLOW_STEP, region)
            strokes, inside = concatenate([strokes, more]), np.concatenate([inside, more_inside])
            read_end += FOLLOW_STEP
            logger.info("The episode that started at %s is still running: read on to %s",
                        _instant(episodes[-1].start_s), read_end.isoformat())
        last = episodes[-1] if episodes else None
        if (last is not None and start_s <= last.start_s < end_s
                and strokes.t.max() <= last.end_s + gap_s
                and not connection.execute(text(DATA_AFTER_SQL), {
                    "provider_id": data_provider_id, "at": read_end}).scalar()):
            logger.warning("The data end before the episode that started at %s could end: it "
                           "ends at its last flash, %s", _instant(last.start_s),
                           _instant(last.end_s))
        connection.rollback()
    before = [episode for episode in episodes if episode.start_s < start_s]
    if before:
        logger.info("The episode running at --from (since %s, %d zone flash(es) read) belongs "
                    "to the previous period: left out", _instant(before[0].start_s),
                    before[0].flashes)
    return [episode for episode in episodes if start_s <= episode.start_s < end_s]


# --------------------------------------------------------------------------
# The files
# --------------------------------------------------------------------------

def _instant(seconds: float) -> str:
    """Seconds since the epoch as a UTC ISO 8601 instant, to the millisecond."""
    return datetime.datetime.fromtimestamp(seconds, UTC).isoformat(timespec="milliseconds")


def quartiles(episodes: list[Episode]) -> list[float]:
    """The minimum, quartiles and maximum of the episodes' flashes (NumPy's default, type 7);
    empty for no episode."""
    if not episodes:
        return []
    return [float(value) for value in
            np.percentile([episode.flashes for episode in episodes], [0, 25, 50, 75, 100])]


def quarter_counts(episodes: list[Episode], values: list[float]) -> list[int]:
    """How many episodes each quarter holds, from the :func:`quartiles` ``values``.

    The quarters are flashes ≤ Q1, Q1 < flashes ≤ median, median < flashes ≤ Q3 and
    flashes > Q3: an episode on a quartile is in the lower quarter.
    """
    flashes = [episode.flashes for episode in episodes]
    return np.bincount(np.searchsorted(values[1:4], flashes, side="left"), minlength=4).tolist()


def quartiles_path(path: Path) -> Path:
    """``episodes.csv`` → ``episodes_quartiles.csv``, beside it."""
    return path.with_name(f"{path.stem}_quartiles{path.suffix}")


def write_files(path: Path, episodes: list[Episode]) -> None:
    """The episodes file and, beside it, the quartiles file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(EPISODE_COLUMNS)
        writer.writerows([number, _instant(episode.start_s), _instant(episode.end_s),
                          f"{episode.end_s - episode.start_s:.3f}", episode.flashes,
                          episode.strokes]
                         for number, episode in enumerate(episodes, start=1))
    values = quartiles(episodes)
    with quartiles_path(path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(QUARTILE_COLUMNS)
        writer.writerow([len(episodes), *(f"{value:.2f}" for value in values),
                         *quarter_counts(episodes, values)]
                        if values else [0, *[""] * (len(QUARTILE_COLUMNS) - 1)])


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("lightning-episodes")
    try:
        engine = create_engine(common.database_url(common.resolve_database_settings(args)))
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    try:
        common.require_tables(engine, ["lightning", "data_provider", "admin_boundary",
                                       REGIONS[args.provider].table], logger)
        with engine.connect() as connection:
            data_provider_id = provider_id(connection, READERS[args.provider])
            region = read_region(connection, args.provider)
        logger.info("%s strokes (data provider %d) over the zone of %s, episodes starting from "
                    "%s to %s, G = %g h", args.provider, data_provider_id,
                    REGIONS[args.provider].description, args.start.isoformat(),
                    args.end.isoformat(), args.gap)
        episodes = period_episodes(engine, args.provider, data_provider_id, region, args.start,
                                   args.end, datetime.timedelta(hours=args.gap), logger)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1
    finally:
        engine.dispose()
    kept = [episode for episode in episodes if episode.flashes >= args.min_flashes]
    logger.info("%d episode(s) start in the period: %d kept, %d with fewer than %d zone flashes "
                "left out", len(episodes), len(kept), len(episodes) - len(kept), args.min_flashes)
    try:
        write_files(args.csv, kept)
    except OSError as error:
        logger.error("Cannot write %s: %s", error.filename, error)
        return 1
    logger.info("Wrote %s and %s", args.csv, quartiles_path(args.csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
