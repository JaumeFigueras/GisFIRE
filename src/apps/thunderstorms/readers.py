#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read one provider's strokes from the database, as the algorithms want them.

A reader turns the strokes of ``[start, end)`` into
:class:`~gisfire_algorithms.thunderstorm.Strokes`: identifiers, a flash key,
times in seconds since the epoch, coordinates in metres of a projected CRS and
location errors in metres. It streams them with a server-side cursor, in time
order (``date_time, id``), one batch at a time, so a period of years never sits
in memory twice.

Each provider has its own reader, registered in :data:`READERS` under the name
given to ``--provider``, with the ``lightning_filter`` it applies: the value
stored in ``thunderstorm_experiment.lightning_filter``, which must describe the
filter completely.

MeteoCat
--------

* **Flash key**: ``network_version · 10¹⁰ + flash_id``. The two networks number
  their flashes independently (see :mod:`src.providers.catalonia_meteocat`),
  and a flash id is never reused across days within a network.
* **Location error**: ``ellipse_major_axis`` as published, in metres.
* **Coordinates**: the published ETRS89 point projected to the requested CRS.
  For EPSG:25831 the expression is exactly the indexed one
  (:data:`~src.providers.catalonia_meteocat.lightning.GEOMETRY_25831`).
* **Filter** ``{"network": "newest"}``: the networks overlap in time (version 1
  runs until 2009-09-29 23:59 UTC, version 2 starts on 2009-09-01 00:06 UTC),
  and the same discharge located twice would make two flashes. A stroke of a
  network is dropped at or after the **first stroke of any newer network**. That
  instant is read from the database, not hard-coded, and does not depend on the
  run window: September 2009 is version 2 only, whichever period is asked for.
* **Default CRS**: EPSG:25831, ETRS89 / UTM 31N.

FMI
---

* **Flash key**: ``flash_id``, one sequence since 1998 for the whole network
  (see :mod:`src.providers.finland_fmi`).
* **Location error**: ``ellipse_major_axis``, in metres (the import converts
  FMI's kilometres).
* **Coordinates**: the published ETRS89 point projected to the requested CRS.
  For EPSG:3067 the expression is exactly the indexed one
  (:data:`~src.providers.finland_fmi.lightning.GEOMETRY_3067`).
* **Filter** ``{}``: one network, nothing to choose between.
* **Default CRS**: EPSG:3067, ETRS89 / TM35FIN.
* **Times** are whole seconds, so many strokes share one: the ``id`` that breaks
  the tie follows the import's content order
  (:mod:`src.apps.imports.lightnings.finland_fmi.readers`), so a month imported
  again reads in the same order.

Each reader also names its provider's **default CRS** (``default_srid``): the
builder uses it when ``--srid`` is not given, so that a run over FMI's strokes
does not fall back to MeteoCat's UTM 31N.
"""

from __future__ import annotations

import datetime

from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from sqlalchemy import Connection
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import Strokes
from src.providers import catalonia_meteocat
from src.providers import finland_fmi
from src.providers.catalonia_meteocat.lightning import GEOMETRY_25831
from src.providers.finland_fmi.lightning import GEOMETRY_3067

#: How many rows the server-side cursor hands over at a time.
FETCH_SIZE = 50_000

#: The factor that folds MeteoCat's ``(network_version, flash_id)`` into one key.
#: Flash ids are 32-bit integers, below it.
METEOCAT_FLASH_KEY_FACTOR = 10_000_000_000

#: The first stroke of each MeteoCat network.
METEOCAT_NETWORK_STARTS_SQL = """
SELECT m.network_version, min(l.date_time)
FROM meteocat_lightning AS m
JOIN lightning AS l ON l.id = m.id
WHERE l.data_provider_id = :provider_id
GROUP BY m.network_version
ORDER BY m.network_version
"""

METEOCAT_STROKES_SQL = """
SELECT l.id,
       CAST(m.network_version AS bigint) * {factor} + m.flash_id AS flash_key,
       CAST(EXTRACT(EPOCH FROM l.date_time) AS double precision) AS t,
       ST_X(p.point) AS x,
       ST_Y(p.point) AS y,
       m.ellipse_major_axis AS error
FROM lightning AS l
JOIN meteocat_lightning AS m ON m.id = l.id
CROSS JOIN LATERAL (SELECT {point} AS point) AS p
WHERE l.data_provider_id = :provider_id
  AND l.date_time >= :start AND l.date_time < :end{network}
ORDER BY l.date_time, l.id
"""

FMI_STROKES_SQL = """
SELECT l.id,
       CAST(f.flash_id AS bigint) AS flash_key,
       CAST(EXTRACT(EPOCH FROM l.date_time) AS double precision) AS t,
       ST_X(p.point) AS x,
       ST_Y(p.point) AS y,
       f.ellipse_major_axis AS error
FROM lightning AS l
JOIN fmi_lightning AS f ON f.id = l.id
CROSS JOIN LATERAL (SELECT {point} AS point) AS p
WHERE l.data_provider_id = :provider_id
  AND l.date_time >= :start AND l.date_time < :end
ORDER BY l.date_time, l.id
"""


@dataclass(frozen=True)
class StrokeReader:
    """How to read one provider's strokes.

    Attributes
    ----------
    provider_name, provider_product : str
        The provider's ``data_provider`` row.
    lightning_filter : dict
        The filter the reader applies, stored as the experiment's
        ``lightning_filter``.
    default_srid : int
        The provider's projected CRS, used when a run does not name one.
    read : callable
        ``read(connection, provider_id, start, end, srid, fetch_size)``, an
        iterator over :class:`~gisfire_algorithms.thunderstorm.Strokes` batches
        in time order.
    """

    provider_name: str
    provider_product: str
    lightning_filter: dict[str, Any]
    default_srid: int
    read: Callable[..., Iterator[Strokes]]


def meteocat_network_cutoffs(connection: Connection, provider_id: int) -> dict[int, datetime.datetime]:
    """For each MeteoCat network with a newer one, the instant its strokes stop counting.

    That instant is the first stroke of any newer network. The newest network
    has no cutoff.
    """
    starts = list(connection.execute(text(METEOCAT_NETWORK_STARTS_SQL),
                                     {"provider_id": provider_id}))
    cutoffs = {}
    for index, (version, _) in enumerate(starts):
        newer = [start for _, start in starts[index + 1:]]
        if newer:
            cutoffs[version] = min(newer)
    return cutoffs


def meteocat_strokes_sql(srid: int, cutoffs: dict[int, datetime.datetime]) -> tuple[str, dict[str, Any]]:
    """The query and the parameters it binds besides the provider and the period."""
    if srid == catalonia_meteocat.PROJECTED_SRID:
        point = GEOMETRY_25831.format(column="m.geometry_etrs89")
    else:
        point = f"ST_Transform(m.geometry_etrs89, {int(srid)})"
    network = "".join(
        f"\n  AND NOT (m.network_version = {int(version)} AND l.date_time >= :cutoff_{int(version)})"
        for version in sorted(cutoffs))
    sql = METEOCAT_STROKES_SQL.format(factor=METEOCAT_FLASH_KEY_FACTOR, point=point, network=network)
    return sql, {f"cutoff_{int(version)}": cutoff for version, cutoff in cutoffs.items()}


def strokes_from_rows(rows: list[Any]) -> Strokes:
    """``(id, flash_key, t, x, y, error)`` rows as :class:`Strokes`."""
    if not rows:
        empty = np.empty(0)
        return Strokes(ids=np.empty(0, dtype=np.int64), flash_keys=np.empty(0, dtype=np.int64),
                       t=empty, x=empty, y=empty, error=empty)
    ids, keys, t, x, y, error = zip(*rows)
    return Strokes(ids=np.array(ids, dtype=np.int64), flash_keys=np.array(keys, dtype=np.int64),
                   t=np.array(t, dtype=np.float64), x=np.array(x, dtype=np.float64),
                   y=np.array(y, dtype=np.float64), error=np.array(error, dtype=np.float64))


def _stream(connection: Connection, sql: str, parameters: dict[str, Any],
            fetch_size: int) -> Iterator[Strokes]:
    """Run ``sql`` through a server-side cursor and yield its rows as batches."""
    # Streaming is asked for on this statement only: Connection.execution_options()
    # would change the connection in place, and every later query on it would
    # then run through a server-side cursor, where PostgreSQL plans no parallel
    # workers (the network starts take three times as long).
    result = connection.execute(text(sql), parameters,
                                execution_options={"stream_results": True,
                                                   "yield_per": fetch_size})
    for rows in result.partitions(fetch_size):
        yield strokes_from_rows(rows)


def read_meteocat_strokes(connection: Connection, provider_id: int, start: datetime.datetime,
                          end: datetime.datetime, srid: int,
                          fetch_size: int | None = None) -> Iterator[Strokes]:
    """MeteoCat's strokes of ``[start, end)``, newest network only, in batches.

    Parameters
    ----------
    connection : Connection
        An open connection; the cursor lives in its current transaction.
    provider_id : int
        MeteoCat's ``data_provider.id``.
    start, end : datetime.datetime
        The period, half-open, timezone-aware.
    srid : int
        The projected CRS of the coordinates.
    fetch_size : int, optional
        Strokes per batch; :data:`FETCH_SIZE` by default.

    Yields
    ------
    Strokes
        Consecutive batches in ``(date_time, id)`` order; none for an empty
        period.
    """
    fetch_size = fetch_size or FETCH_SIZE
    sql, extra = meteocat_strokes_sql(srid, meteocat_network_cutoffs(connection, provider_id))
    yield from _stream(connection, sql,
                       {"provider_id": provider_id, "start": start, "end": end, **extra},
                       fetch_size)


def fmi_strokes_sql(srid: int) -> str:
    """The query for FMI's strokes in ``srid``."""
    if srid == finland_fmi.PROJECTED_SRID:
        point = GEOMETRY_3067.format(column="f.geometry_etrs89")
    else:
        point = f"ST_Transform(f.geometry_etrs89, {int(srid)})"
    return FMI_STROKES_SQL.format(point=point)


def read_fmi_strokes(connection: Connection, provider_id: int, start: datetime.datetime,
                     end: datetime.datetime, srid: int,
                     fetch_size: int | None = None) -> Iterator[Strokes]:
    """FMI's strokes of ``[start, end)``, in batches.

    Parameters and batches as :func:`read_meteocat_strokes`, without a network
    filter: FMI has one network.
    """
    yield from _stream(connection, fmi_strokes_sql(srid),
                       {"provider_id": provider_id, "start": start, "end": end},
                       fetch_size or FETCH_SIZE)


#: The readers, by the name given to ``--provider``.
READERS: dict[str, StrokeReader] = {
    catalonia_meteocat.PROVIDER_NAME: StrokeReader(
        provider_name=catalonia_meteocat.PROVIDER_NAME,
        provider_product=catalonia_meteocat.PROVIDER_PRODUCT,
        lightning_filter={"network": "newest"},
        default_srid=catalonia_meteocat.PROJECTED_SRID,
        read=read_meteocat_strokes,
    ),
    finland_fmi.PROVIDER_NAME: StrokeReader(
        provider_name=finland_fmi.PROVIDER_NAME,
        provider_product=finland_fmi.PROVIDER_PRODUCT,
        lightning_filter={},
        default_srid=finland_fmi.PROJECTED_SRID,
        read=read_fmi_strokes,
    ),
}
