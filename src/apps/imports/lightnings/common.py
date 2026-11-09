#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What every lightning import shares: the thunderstorms built on the strokes.

A :class:`~src.data_model.thunderstorm.ThunderstormExperiment` is computed from
one provider's strokes over a period. An import that replaces a year of strokes
(deleting them and inserting them again with new identifiers) would change an
experiment's input under it, and the strokes in its thunderstorms cannot be
deleted at all: ``thunderstorm_lightning.lightning_id`` is ``ON DELETE
RESTRICT``.

So before replacing a year an import asks :func:`covering_experiments` which
experiments depend on it, and either refuses the year (:class:`YearInUse`) or,
when told to, deletes those experiments with :func:`drop_experiments` in the
same transaction. An experiment is deleted **whole** — its thunderstorms, their
strokes' links, its trackings and their windows go by cascade — never just the
year: a run is one consistent result, and cutting a year out of it would leave
thunderstorms that crossed New Year half built.

These helpers are provider-agnostic, for the next lightning import to reuse.
"""

from __future__ import annotations

import datetime
import logging

from dataclasses import dataclass

from sqlalchemy import Connection
from sqlalchemy import text

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


class YearInUse(RuntimeError):
    """A year cannot be replaced: thunderstorm experiments depend on its strokes."""

    def __init__(self, year: int, experiment_ids: list[int], reason: str | None = None) -> None:
        self.year = year
        self.experiment_ids = experiment_ids
        ids = ", ".join(str(identifier) for identifier in experiment_ids) or "unknown"
        super().__init__(
            reason or f"{year} not replaced: thunderstorm experiment(s) {ids} depend on its "
                      f"strokes; delete them first, or run again with {DROP_FLAG}")


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
