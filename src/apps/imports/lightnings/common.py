#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What every lightning import shares: the thunderstorms built on the strokes.

A :class:`~src.data_model.thunderstorm.ThunderstormExperiment` is computed from
one provider's strokes over a period. An import that replaces a period of strokes
(deleting them and inserting them again with new identifiers) would change an
experiment's input under it, and the strokes in its thunderstorms cannot be
deleted at all: ``thunderstorm_lightning.lightning_id`` is ``ON DELETE
RESTRICT``.

So before replacing a period — a year for MeteoCat, a month for FMI — an import
asks :func:`covering_experiments` which experiments depend on it, and either
refuses the period (:class:`PeriodInUse`; :class:`YearInUse` for a year) or,
when told to, deletes those experiments with :func:`drop_experiments` in the
same transaction. An experiment is deleted **whole** — its thunderstorms, their
strokes' links, its trackings and their windows go by cascade — never just the
period: a run is one consistent result, and cutting a year out of it would leave
thunderstorms that crossed New Year half built.

These helpers are provider-agnostic, for the next lightning import to reuse.

The country of a stroke
-----------------------

A lightning import resolves each stroke's country against the OCHA level-0
boundaries, cut into pieces of at most :data:`SUBDIVIDE_VERTICES` vertices so
that millions of points can be tested quickly. :func:`ensure_boundary_pieces`
cuts them **once per run**, into a temporary table of the run's single
connection, and **clips** them first to the box the strokes can fall in — the
provider's area joined with the strokes being imported, plus a margin. Cutting
whole countries for every period was what made the imports slow: a
bounding-box test also selects countries whose overseas territories stretch
their boxes over Europe (the United States, France, the United Kingdom, the
Netherlands), and Norway, Sweden, Finland and Russia are millions of vertices
each. A period whose strokes reach outside the box already cut gets the pieces
cut again over the larger box, so no stroke can lose its country to the
clipping. The margin keeps the clipping's edge, where ``ST_ClipByBox2D`` may
leave invalid rings, away from every stroke.
"""

from __future__ import annotations

import datetime
import logging

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Connection
from sqlalchemy import text

from src.apps.imports.common import Spinner

#: The experiments that depend on a provider's strokes in ``[start, end)``: those
#: of the provider whose period overlaps it — whether or not any of those
#: strokes ended up in a thunderstorm, since the experiment read them all — and
#: any experiment holding one of those strokes in a thunderstorm, whatever its
#: period, which is what ``RESTRICT`` would otherwise trip on.
COVERING_EXPERIMENTS_SQL = """
SELECT experiment.id, experiment.algorithm, experiment.status,
       experiment.date_time_start, experiment.date_time_end,
       (SELECT count(*) FROM thunderstorm AS storm
        WHERE storm.experiment_id = experiment.id) AS thunderstorms,
       (SELECT count(*) FROM thunderstorm_tracking AS tracking
        WHERE tracking.experiment_id = experiment.id) AS trackings
FROM thunderstorm_experiment AS experiment
WHERE (experiment.data_provider_id = :provider_id
       AND experiment.date_time_start < :end AND experiment.date_time_end > :start)
   OR experiment.id IN (
       SELECT link.experiment_id
       FROM thunderstorm_lightning AS link
       JOIN lightning AS stroke ON stroke.id = link.lightning_id
       WHERE stroke.data_provider_id = :provider_id
         AND stroke.date_time >= :start AND stroke.date_time < :end)
ORDER BY experiment.id
"""

#: Deletes experiments; the foreign keys cascade to everything they produced.
DROP_EXPERIMENTS_SQL = "DELETE FROM thunderstorm_experiment WHERE id = ANY(:ids)"

#: The experiments holding a provider's strokes of ``[start, end)`` in a
#: thunderstorm, for the message when ``RESTRICT`` refused a delete.
HOLDING_EXPERIMENTS_SQL = """
SELECT DISTINCT link.experiment_id
FROM thunderstorm_lightning AS link
JOIN lightning AS stroke ON stroke.id = link.lightning_id
WHERE stroke.data_provider_id = :provider_id
  AND stroke.date_time >= :start AND stroke.date_time < :end
ORDER BY link.experiment_id
"""

#: The flag that lets an import drop the experiments in its way.
DROP_FLAG = "--drop-thunderstorms"


@dataclass(frozen=True)
class CoveringExperiment:
    """An experiment that depends on the strokes about to be replaced."""

    id: int
    algorithm: str
    status: str
    date_time_start: datetime.datetime
    date_time_end: datetime.datetime
    thunderstorms: int
    trackings: int

    def describe(self) -> str:
        return (f"{self.id} ({self.algorithm}, {self.status}, "
                f"{self.date_time_start:%Y-%m-%d} to {self.date_time_end:%Y-%m-%d}): "
                f"{self.thunderstorms} thunderstorm(s), {self.trackings} tracking(s)")


class PeriodInUse(RuntimeError):
    """A period cannot be replaced: thunderstorm experiments depend on its strokes.

    ``period`` is how the import names its unit — a year for MeteoCat, a month
    (``YYYY-MM``) for FMI.
    """

    def __init__(self, period: str, experiment_ids: list[int], reason: str | None = None) -> None:
        self.period = period
        self.experiment_ids = experiment_ids
        ids = ", ".join(str(identifier) for identifier in experiment_ids) or "unknown"
        super().__init__(
            reason or f"{period} not replaced: thunderstorm experiment(s) {ids} depend on its "
                      f"strokes; delete them first, or run again with {DROP_FLAG}")


class YearInUse(PeriodInUse):
    """A year cannot be replaced: thunderstorm experiments depend on its strokes."""

    def __init__(self, year: int, experiment_ids: list[int], reason: str | None = None) -> None:
        self.year = year
        super().__init__(str(year), experiment_ids, reason)


def covering_experiments(connection: Connection, provider_id: int, start: str,
                         end: str) -> list[CoveringExperiment]:
    """The experiments that depend on the provider's strokes in ``[start, end)``."""
    rows = connection.execute(text(COVERING_EXPERIMENTS_SQL),
                              {"provider_id": provider_id, "start": start, "end": end})
    return [CoveringExperiment(*row) for row in rows]


def drop_experiments(connection: Connection, experiments: list[CoveringExperiment],
                     log: logging.Logger | logging.LoggerAdapter) -> int:
    """Delete the experiments whole, in the open transaction; the number deleted."""
    for experiment in experiments:
        log.warning("Dropping thunderstorm experiment %s", experiment.describe())
    if not experiments:
        return 0
    return connection.execute(text(DROP_EXPERIMENTS_SQL),
                              {"ids": [experiment.id for experiment in experiments]}).rowcount


def holding_experiments(connection: Connection, provider_id: int, start: str,
                        end: str) -> list[int]:
    """The experiments with the provider's strokes of ``[start, end)`` in a thunderstorm."""
    return list(connection.execute(text(HOLDING_EXPERIMENTS_SQL),
                                   {"provider_id": provider_id, "start": start,
                                    "end": end}).scalars())


# --------------------------------------------------------------------------
# Boundary pieces for the country of each stroke
# --------------------------------------------------------------------------

#: How finely the boundaries are cut before the lookup (the PostGIS recipe).
SUBDIVIDE_VERTICES = 256

#: The pieces: the OCHA level-0 boundaries whose box touches the clipping box,
#: clipped to it and cut. A temporary table of the session, not of the
#: transaction, so a run's periods share it. With no boundary provider
#: ``:boundary_provider_id`` is NULL and the table is empty.
CREATE_PIECES_SQL = """
CREATE TEMPORARY TABLE {table} AS
SELECT clipped.admin_boundary_id,
       ST_Subdivide(clipped.geometry, {vertices}) AS geometry
FROM (SELECT boundary.id AS admin_boundary_id,
             ST_ClipByBox2D(boundary.geometry,
                            ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)) AS geometry
      FROM admin_boundary AS boundary
      WHERE boundary.level = 0
        AND boundary.data_provider_id = :boundary_provider_id
        AND boundary.geometry && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)) AS clipped
WHERE NOT ST_IsEmpty(clipped.geometry)
"""

#: The box the pieces were cut for, beside them, in the same transaction. Its
#: columns are not ``xmin``/``xmax``: those are PostgreSQL system column names.
CREATE_PIECES_BOX_SQL = """
CREATE TEMPORARY TABLE {table}_box AS
SELECT CAST(:xmin AS double precision) AS west, CAST(:ymin AS double precision) AS south,
       CAST(:xmax AS double precision) AS east, CAST(:ymax AS double precision) AS north
"""


def clipping_box(area: tuple[float, float, float, float], records: Iterable,
                 margin: float) -> dict[str, float]:
    """The box strokes can fall in: ``area`` joined with the records' extent, plus ``margin``.

    ``area`` is ``(west, south, east, north)``; the records need ``longitude`` and
    ``latitude``. The result is what :data:`CREATE_PIECES_SQL` binds.
    """
    west, south, east, north = area
    for record in records:
        west, east = min(west, record.longitude), max(east, record.longitude)
        south, north = min(south, record.latitude), max(north, record.latitude)
    return {"xmin": max(west - margin, -180.0), "ymin": max(south - margin, -90.0),
            "xmax": min(east + margin, 180.0), "ymax": min(north + margin, 90.0)}


def pieces_exist(connection: Connection, table: str) -> bool:
    """Whether this session has the pieces ``table``."""
    return bool(connection.execute(text(
        f"SELECT to_regclass('pg_temp.{table}') IS NOT NULL")).scalar())


def ensure_boundary_pieces(connection: Connection, table: str,
                           boundary_provider_id: int | None, box: dict[str, float],
                           log: logging.Logger | logging.LoggerAdapter) -> bool:
    """Cut the pieces ``table`` for ``box`` unless the session has them for a box
    holding it; whether they were cut.

    Run inside a period's transaction: if it is rolled back, the pieces go with
    it and the next period cuts them again; once committed, they stay for the
    session. Pieces cut for a box that does not hold ``box`` are cut again, over
    both boxes together.
    """
    if pieces_exist(connection, table):
        built = connection.execute(text(f"SELECT west, south, east, north FROM {table}_box")).one()
        if (built.west <= box["xmin"] and built.south <= box["ymin"]
                and built.east >= box["xmax"] and built.north >= box["ymax"]):
            return False
        box = {"xmin": min(built.west, box["xmin"]), "ymin": min(built.south, box["ymin"]),
               "xmax": max(built.east, box["xmax"]), "ymax": max(built.north, box["ymax"])}
        drop_boundary_pieces(connection, table)
    logger = log.logger if isinstance(log, logging.LoggerAdapter) else log
    with Spinner("Cutting the boundaries the strokes can fall in (once per run)", logger):
        connection.execute(text(CREATE_PIECES_SQL.format(table=table, vertices=SUBDIVIDE_VERTICES)),
                           {"boundary_provider_id": boundary_provider_id, **box})
        connection.execute(text(f"CREATE INDEX ON {table} USING gist (geometry)"))
        connection.execute(text(f"ANALYZE {table}"))
        connection.execute(text(CREATE_PIECES_BOX_SQL.format(table=table)), box)
    return True


def drop_boundary_pieces(connection: Connection, table: str) -> None:
    """Drop the pieces ``table`` and its box, if the session has them.

    A run calls it at its end: a pooled connection keeps its session, temporary
    tables included, for whoever takes it next.
    """
    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
    connection.execute(text(f"DROP TABLE IF EXISTS {table}_box"))

