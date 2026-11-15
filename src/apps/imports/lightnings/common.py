#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What every lightning import shares: the thunderstorms built on the strokes.

A :class:`~src.data_model.thunderstorm.ThunderstormExperiment` is computed from
one provider's strokes over a period. An import that replaces a period of strokes
(deleting them and inserting them again with new identifiers) would change an
experiment's input under it, and the strokes in its thunderstorms cannot be
deleted at all: ``thunderstorm_lightning.lightning_id`` is ``ON DELETE
RESTRICT``.

So before replacing a period — a year for MeteoCat and the Alaska network, a
month for FMI — an import asks :func:`covering_experiments` which experiments
depend on it, and either refuses the period (:class:`PeriodInUse`;
:class:`YearInUse` for a year) or, when told to, deletes those experiments with
:func:`drop_experiments` in the same transaction. An experiment is deleted
**whole** — its thunderstorms, their strokes' links, its trackings and their
windows go by cascade — never just the period: a run is one consistent result,
and cutting a year out of it would leave thunderstorms that crossed New Year
half built.

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

A box may cross the antimeridian: the Alaska network's strokes run from 168.8 E
to 97.0 W. Taking the least and greatest longitude would then give a box round
the whole globe — cutting the United States, Canada and Russia whole again — so
a box is kept in its **area's own longitude frame**: the area is written past
180 when it crosses it (``alaska_uswfs.NETWORK_AREA`` ends at 263.1, which is
96.9 W), each stroke's longitude is moved by 360° to the side of the area's
centre, and the box is clipped with two envelopes, one each side of 180°, when it
crosses. MeteoCat's and FMI's areas are far from 180°, so for them nothing
changes.
"""

from __future__ import annotations

import datetime
import logging
import math

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

    ``period`` is how the import names its unit — a year for MeteoCat and the
    Alaska network, a month (``YYYY-MM``) for FMI.
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

#: The pieces: the OCHA level-0 boundaries whose box touches an envelope of the
#: clipping box, clipped to it and cut; ``{envelopes}`` is one ``ST_MakeEnvelope``
#: per envelope (:func:`envelopes`: two when the box crosses the antimeridian). A
#: temporary table of the session, not of the transaction, so a run's periods share
#: it. With no boundary provider ``:boundary_provider_id`` is NULL and the table is
#: empty.
CREATE_PIECES_SQL = """
CREATE TEMPORARY TABLE {table} AS
SELECT clipped.admin_boundary_id,
       ST_Subdivide(clipped.geometry, {vertices}) AS geometry
FROM (SELECT boundary.id AS admin_boundary_id,
             ST_ClipByBox2D(boundary.geometry, envelope.geometry) AS geometry
      FROM admin_boundary AS boundary
      JOIN (VALUES {envelopes}) AS envelope (geometry)
        ON boundary.geometry && envelope.geometry
      WHERE boundary.level = 0
        AND boundary.data_provider_id = :boundary_provider_id) AS clipped
WHERE NOT ST_IsEmpty(clipped.geometry)
"""

#: One envelope of :data:`CREATE_PIECES_SQL`, its binds numbered.
ENVELOPE_SQL = "(ST_MakeEnvelope(:west_{n}, :south_{n}, :east_{n}, :north_{n}, 4326))"

#: The box the pieces were cut for, beside them, in the same transaction, in its
#: own longitude frame. Its columns are not ``xmin``/``xmax``: those are PostgreSQL
#: system column names.
CREATE_PIECES_BOX_SQL = """
CREATE TEMPORARY TABLE {table}_box AS
SELECT CAST(:xmin AS double precision) AS west, CAST(:ymin AS double precision) AS south,
       CAST(:xmax AS double precision) AS east, CAST(:ymax AS double precision) AS north
"""


def _turns(longitude: float, centre: float) -> float:
    """The multiple of 360° that brings ``longitude`` within half a turn of ``centre``."""
    return 360.0 * math.floor((centre - longitude) / 360.0 + 0.5)


def clipping_box(area: tuple[float, float, float, float], records: Iterable,
                 margin: float) -> dict[str, float]:
    """The box strokes can fall in: ``area`` joined with the records' extent, plus ``margin``.

    ``area`` is ``(west, south, east, north)``, with ``east`` past 180 when the area
    crosses the antimeridian; the records need ``longitude`` and ``latitude``. The
    box is in the area's longitude frame: a record's longitude is moved by 360° to
    the side of the area's centre, so a stroke at 170 W joins an area of 168..263
    as 190. A box a turn wide or wider is the whole globe, -180..180.
    """
    west, south, east, north = area
    centre = (west + east) / 2.0
    for record in records:
        longitude = record.longitude + _turns(record.longitude, centre)
        west, east = min(west, longitude), max(east, longitude)
        south, north = min(south, record.latitude), max(north, record.latitude)
    west, east = west - margin, east + margin
    if east - west >= 360.0:
        west, east = -180.0, 180.0
    return {"xmin": west, "ymin": max(south - margin, -90.0),
            "xmax": east, "ymax": min(north + margin, 90.0)}


def envelopes(box: dict[str, float]) -> list[tuple[float, float, float, float]]:
    """``box`` as ``(west, south, east, north)`` envelopes within -180..180.

    One, or two when the box crosses the antimeridian: from its west edge to 180,
    and from -180 to its east edge.
    """
    west, east, south, north = box["xmin"], box["xmax"], box["ymin"], box["ymax"]
    if east - west >= 360.0:
        return [(-180.0, south, 180.0, north)]
    shift = 360.0 * math.floor((west + 180.0) / 360.0)
    west, east = west - shift, east - shift
    if east <= 180.0:
        return [(west, south, east, north)]
    return [(west, south, 180.0, north), (-180.0, south, east - 360.0, north)]


def _aligned(box: dict[str, float], reference: dict[str, float]) -> dict[str, float]:
    """``box`` moved by whole turns so its centre is within half a turn of ``reference``'s."""
    shift = _turns((box["xmin"] + box["xmax"]) / 2.0, (reference["xmin"] + reference["xmax"]) / 2.0)
    return {**box, "xmin": box["xmin"] + shift, "xmax": box["xmax"] + shift}


def box_holds(outer: dict[str, float], inner: dict[str, float]) -> bool:
    """Whether ``outer`` holds ``inner``, whichever longitude frame each is in."""
    if not (outer["ymin"] <= inner["ymin"] and inner["ymax"] <= outer["ymax"]):
        return False
    if outer["xmax"] - outer["xmin"] >= 360.0:
        return True
    inner = _aligned(inner, outer)
    return outer["xmin"] <= inner["xmin"] and inner["xmax"] <= outer["xmax"]


def box_union(first: dict[str, float], second: dict[str, float]) -> dict[str, float]:
    """The smallest box holding both, in ``first``'s longitude frame."""
    second = _aligned(second, first)
    west, east = min(first["xmin"], second["xmin"]), max(first["xmax"], second["xmax"])
    if east - west >= 360.0:
        west, east = -180.0, 180.0
    return {"xmin": west, "ymin": min(first["ymin"], second["ymin"]),
            "xmax": east, "ymax": max(first["ymax"], second["ymax"])}


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
    both boxes together. A box crossing the antimeridian is clipped with two
    envelopes (:func:`envelopes`).
    """
    if pieces_exist(connection, table):
        row = connection.execute(text(f"SELECT west, south, east, north FROM {table}_box")).one()
        built = {"xmin": row.west, "ymin": row.south, "xmax": row.east, "ymax": row.north}
        if box_holds(built, box):
            return False
        box = box_union(built, box)
        drop_boundary_pieces(connection, table)
    logger = log.logger if isinstance(log, logging.LoggerAdapter) else log
    parts = envelopes(box)
    binds: dict[str, float | int | None] = {"boundary_provider_id": boundary_provider_id}
    for n, (west, south, east, north) in enumerate(parts):
        binds.update({f"west_{n}": west, f"south_{n}": south, f"east_{n}": east, f"north_{n}": north})
    sql = CREATE_PIECES_SQL.format(
        table=table, vertices=SUBDIVIDE_VERTICES,
        envelopes=", ".join(ENVELOPE_SQL.format(n=n) for n in range(len(parts))))
    with Spinner("Cutting the boundaries the strokes can fall in (once per run)", logger):
        connection.execute(text(sql), binds)
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

