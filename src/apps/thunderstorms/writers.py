#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Store what a thunderstorm algorithm found.

A run is written piece by piece (see
:mod:`src.apps.thunderstorms.build_thunderstorms`). Each piece's cells go
through ``COPY`` into temporary tables and then one ``INSERT … SELECT`` per
target table, as the lightning import does: the ORM would take hours over a
period of years.

Generic, for every algorithm (:func:`write_cells`):

* ``thunderstorm``: the label, the flash count and the area come from the
  algorithm; the time span and the number of strokes are computed **in the
  database** from the linked strokes, so they are exactly theirs, with no
  round trip through floating-point seconds; the concave hull is
  ``ST_ConcaveHull`` over the points the algorithm clustered, in the projected
  CRS, reprojected to EPSG:4326, and ``NULL`` when it is not a polygon (fewer
  than three distinct points, or all in a line).
* ``thunderstorm_lightning``: every stroke of the cell.

Specific to Cellsearch (:func:`write_cellsearch_flashes`):
``thunderstorm_cellsearch_flash``, one row per flash with the cell's running
centre after it.

Every statement runs in the caller's transaction; nothing here commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from sqlalchemy import Connection
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy import text

from src.data_model.thunderstorm import ThunderstormExperiment


@dataclass(frozen=True, eq=False)
class Cells:
    """The kept cells of one piece, as the generic tables want them.

    Attributes
    ----------
    label : numpy.ndarray of int64
        One per cell, unique within the run.
    number_of_flashes : numpy.ndarray of int64 or None
        One per cell, for a flash-based algorithm.
    area : list of float or None
        One per cell, in km², ``None`` when undefined.
    link_label, link_lightning_id : numpy.ndarray of int64
        One per linked stroke: its cell and its id.
    hull_label : numpy.ndarray of int64
        One per point the hull is drawn over: its cell.
    hull_x, hull_y : numpy.ndarray of float64
        Those points, in metres of the run's projected CRS.
    """

    label: np.ndarray
    number_of_flashes: np.ndarray | None
    area: list[float | None]
    link_label: np.ndarray
    link_lightning_id: np.ndarray
    hull_label: np.ndarray
    hull_x: np.ndarray
    hull_y: np.ndarray

    def __len__(self) -> int:
        return len(self.label)


@dataclass(frozen=True, eq=False)
class CellsearchFlashes:
    """The flashes of one piece's kept Cellsearch cells, one element per flash.

    Attributes
    ----------
    label : numpy.ndarray of int64
        The flash's cell.
    sequence : numpy.ndarray of int64
        Its position in the cell, from 1.
    lightning_id : numpy.ndarray of int64
        Its representative stroke.
    centre_x, centre_y : numpy.ndarray of float64
        The cell's centre right after it, in metres of the run's projected CRS.
    """

    label: np.ndarray
    sequence: np.ndarray
    lightning_id: np.ndarray
    centre_x: np.ndarray
    centre_y: np.ndarray


# --------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------

#: The columns that make up a run's identity
#: (``uq_thunderstorm_experiment_configuration``).
CONFIGURATION = ("data_provider_id", "algorithm", "parameters", "lightning_filter",
                 "hull_parameters", "date_time_start", "date_time_end", "software_version")


def find_experiment(connection: Connection, configuration: dict[str, Any]) -> tuple[int, str] | None:
    """The ``(id, status)`` of the experiment with this configuration, if one exists.

    ``jsonb`` compares by value, so the key order of a setting does not matter.
    """
    table = ThunderstormExperiment.__table__
    query = select(table.c.id, table.c.status).where(
        *(table.c[name] == configuration[name] for name in CONFIGURATION))
    row = connection.execute(query).first()
    return None if row is None else (row.id, row.status)


def insert_experiment(connection: Connection, configuration: dict[str, Any]) -> int:
    """Insert a ``running`` experiment with this configuration; its id."""
    table = ThunderstormExperiment.__table__
    values = {name: configuration[name] for name in CONFIGURATION}
    return connection.execute(insert(table).values(**values).returning(table.c.id)).scalar_one()


def complete_experiment(connection: Connection, experiment_id: int, summary: dict[str, Any]) -> None:
    """Store the summary and mark the experiment ``complete``."""
    table = ThunderstormExperiment.__table__
    connection.execute(table.update().where(table.c.id == experiment_id).values(
        summary=summary, status="complete", completed_at=text("now()")))


def fail_experiment(connection: Connection, experiment_id: int) -> None:
    """Delete whatever the experiment produced and mark it ``failed``."""
    connection.execute(text("DELETE FROM thunderstorm WHERE experiment_id = :id"),
                       {"id": experiment_id})
    table = ThunderstormExperiment.__table__
    connection.execute(table.update().where(table.c.id == experiment_id).values(status="failed"))


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def _stage(connection: Connection, table: str, columns: str, rows) -> None:
    """(Re)create a temporary table and ``COPY`` the rows into it.

    Dropped first rather than relying on ``ON COMMIT DROP``: a dry run writes
    every piece in one transaction.
    """
    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
    connection.execute(text(f"CREATE TEMPORARY TABLE {table} ({columns}) ON COMMIT DROP"))
    names = ", ".join(column.split()[0] for column in columns.split(","))
    raw = connection.connection.driver_connection
    with raw.cursor() as cursor, cursor.copy(f"COPY {table} ({names}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
    connection.execute(text(f"ANALYZE {table}"))


def _ints(array: np.ndarray) -> list[int]:
    return np.asarray(array, dtype=np.int64).tolist()


def _floats(array: np.ndarray) -> list[float]:
    return np.asarray(array, dtype=np.float64).tolist()


# --------------------------------------------------------------------------
# Generic tables
# --------------------------------------------------------------------------

INSERT_THUNDERSTORMS_SQL = """
INSERT INTO thunderstorm (experiment_id, label, date_time_start, date_time_end,
                          number_of_lightnings, number_of_flashes, area, concave_hull)
SELECT :experiment_id, cell.label, span.date_time_start, span.date_time_end,
       span.number_of_lightnings, cell.number_of_flashes, cell.area,
       CASE WHEN GeometryType(hull.hull) = 'POLYGON'
            THEN ST_Transform(hull.hull, 4326) END
FROM staging_cell AS cell
JOIN (SELECT link.label, min(stroke.date_time) AS date_time_start,
             max(stroke.date_time) AS date_time_end, count(*) AS number_of_lightnings
      FROM staging_link AS link
      JOIN lightning AS stroke ON stroke.id = link.lightning_id
      GROUP BY link.label) AS span ON span.label = cell.label
LEFT JOIN (SELECT point.label,
                  ST_ConcaveHull(ST_Collect(ST_SetSRID(ST_MakePoint(point.x, point.y), :srid)),
                                 :ratio, :allow_holes) AS hull
           FROM staging_hull_point AS point
           GROUP BY point.label) AS hull ON hull.label = cell.label
ORDER BY cell.label
"""

INSERT_LINKS_SQL = """
INSERT INTO thunderstorm_lightning (thunderstorm_id, lightning_id, experiment_id)
SELECT storm.id, link.lightning_id, :experiment_id
FROM staging_link AS link
JOIN thunderstorm AS storm ON storm.experiment_id = :experiment_id AND storm.label = link.label
"""


def write_cells(connection: Connection, experiment_id: int, cells: Cells,
                hull_parameters: dict[str, Any]) -> None:
    """Insert one piece's cells and their links, with their hulls.

    Parameters
    ----------
    hull_parameters : dict
        ``ratio``, ``allow_holes`` and ``srid`` (the CRS of ``cells.hull_x/y``).
    """
    if not len(cells):
        return
    flashes = ([None] * len(cells) if cells.number_of_flashes is None
               else _ints(cells.number_of_flashes))
    _stage(connection, "staging_cell", "label bigint, number_of_flashes integer, area double precision",
           zip(_ints(cells.label), flashes, cells.area))
    _stage(connection, "staging_link", "label bigint, lightning_id integer",
           zip(_ints(cells.link_label), _ints(cells.link_lightning_id)))
    _stage(connection, "staging_hull_point", "label bigint, x double precision, y double precision",
           zip(_ints(cells.hull_label), _floats(cells.hull_x), _floats(cells.hull_y)))
    connection.execute(text(INSERT_THUNDERSTORMS_SQL), {
        "experiment_id": experiment_id, "srid": int(hull_parameters["srid"]),
        "ratio": float(hull_parameters["ratio"]),
        "allow_holes": bool(hull_parameters["allow_holes"])})
    connection.execute(text(INSERT_LINKS_SQL), {"experiment_id": experiment_id})


# --------------------------------------------------------------------------
# Cellsearch
# --------------------------------------------------------------------------

INSERT_CELLSEARCH_FLASHES_SQL = """
INSERT INTO thunderstorm_cellsearch_flash (thunderstorm_id, sequence, experiment_id,
                                           lightning_id, centre)
SELECT storm.id, flash.sequence, :experiment_id, flash.lightning_id,
       ST_Transform(ST_SetSRID(ST_MakePoint(flash.x, flash.y), :srid), 4326)
FROM staging_cellsearch_flash AS flash
JOIN thunderstorm AS storm ON storm.experiment_id = :experiment_id AND storm.label = flash.label
ORDER BY storm.id, flash.sequence
"""


def write_cellsearch_flashes(connection: Connection, experiment_id: int,
                             flashes: CellsearchFlashes, srid: int) -> None:
    """Insert one piece's Cellsearch flashes, after their cells and links."""
    if not len(flashes.label):
        return
    _stage(connection, "staging_cellsearch_flash",
           "label bigint, sequence integer, lightning_id integer, "
           "x double precision, y double precision",
           zip(_ints(flashes.label), _ints(flashes.sequence), _ints(flashes.lightning_id),
               _floats(flashes.centre_x), _floats(flashes.centre_y)))
    connection.execute(text(INSERT_CELLSEARCH_FLASHES_SQL),
                       {"experiment_id": experiment_id, "srid": int(srid)})
