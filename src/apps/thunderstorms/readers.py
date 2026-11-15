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
given to ``--provider``, with the provider's own ``lightning_filter``.

Ground strokes only
-------------------

By default every reader reads **cloud-to-ground strokes only**
(``lightning.cloud_to_ground``), as Tuomi & Larjavaara's Cellsearch does: its
data were ground flashes, and its parameters were set on them. Cloud strokes
are read too only when asked (``cloud_to_ground_only=False``). The filter
drops whole flashes: FMI publishes a cloud stroke as a flash of its own, the
Alaska import groups ground and cloud strokes apart, and MeteoCat's strokes are
all ground strokes. The exception is three FMI flashes of 26.4 million in
2010-2025 (2015-08-11, 2016-06-28, 2016-07-03), each a cloud stroke followed by
ground strokes under one flash id; their ground strokes stay a flash.

The value stored in ``thunderstorm_experiment.lightning_filter``, which must
describe the filter completely, is :meth:`StrokeReader.filter_for`'s: the
provider's own filter plus ``{"cloud_to_ground": true}`` when only ground
strokes are read. A run that reads cloud strokes too stores the provider's
filter alone, as every run did before the ground filter existed.

MeteoCat
--------

* **Flash key**: ``network_version · 10¹⁰ + flash_id``. The two networks number
  their flashes independently (see :mod:`src.providers.catalonia_meteocat`),
  and a flash id is never reused across days within a network.
* **Location error**: ``ellipse_major_axis`` as published, in metres.
* **Coordinates**: the published ETRS89 point projected to the requested CRS.
  For EPSG:25831 the expression is exactly the indexed one
  (:data:`~src.providers.catalonia_meteocat.lightning.GEOMETRY_25831`).
* **Filter** ``{"network": "newest"}`` (plus the ground filter, which drops
  nothing: MeteoCat's strokes are all ground strokes): the networks overlap in
  time (version 1 runs until 2009-09-29 23:59 UTC, version 2 starts on
  2009-09-01 00:06 UTC), and the same discharge located twice would make two
  flashes. A stroke of a network is dropped at or after the **first stroke of
  any newer network**. That instant is read from the database, not hard-coded,
  and does not depend on the run window: September 2009 is version 2 only,
  whichever period is asked for.
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
* **Filter** ``{}``, plus the ground filter: one network, nothing to choose
  between.
* **Default CRS**: EPSG:3067, ETRS89 / TM35FIN.
* **Times** are whole seconds, so many strokes share one: the ``id`` that breaks
  the tie follows the import's content order
  (:mod:`src.apps.imports.lightnings.finland_fmi.readers`), so a month imported
  again reads in the same order.

USWFS (Alaska)
--------------

* **Flash key**: ``flash_id``, the identifier of the flash's first stroke. The
  release has no flashes: the import groups the strokes with the NLDN rule (see
  :mod:`src.providers.alaska_uswfs`), so the key is unique across years.
* **Location error**: ``ellipse_semi_major_axis``, in metres (the import
  converts the release's kilometres). It is a *semi*-axis, named as such:
  whether MeteoCat's and FMI's ``ellipse_major_axis`` are full or semi axes is
  not known, so the same E_max may not mean the same on all three.
* **Unknown error**: 599 strokes are published with a semi-major axis of 0,
  stored as NULL. They are read as :data:`UNKNOWN_ERROR_M`, the largest finite
  float, which is larger than any E_max that can be asked (``Strokes`` refuses
  infinities). Such a stroke therefore represents its flash only when no stroke
  of the flash has a known error, and E_max then discards that flash. The error
  has no other use in a run.
* **Coordinates**: the published WGS 84 point (``lightning.geometry``) projected
  to the requested CRS. For EPSG:3338 the expression is exactly the indexed one
  (:data:`~src.providers.alaska_uswfs.lightning.GEOMETRY_3338`).
* **Filter** ``{}``, plus the ground filter: one network (``network_code`` is 0
  throughout the release).
* **Default CRS**: EPSG:3338, NAD83 / Alaska Albers, which also holds the
  strokes west of the antimeridian (the Aleutians, the Bering Sea).
* **Times** have milliseconds; strokes of one millisecond come in ``id`` order,
  which follows the import's content order, as FMI's.

Each reader also names its provider's **default CRS** (``default_srid``): the
builder uses it when ``--srid`` is not given, so that a run over FMI's strokes
does not fall back to MeteoCat's UTM 31N.
"""

from __future__ import annotations

import datetime
import sys

from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from sqlalchemy import Connection
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import Strokes
from src.providers import alaska_uswfs
from src.providers import catalonia_meteocat
from src.providers import finland_fmi
from src.providers.alaska_uswfs.lightning import GEOMETRY_3338
from src.providers.catalonia_meteocat.lightning import GEOMETRY_25831
from src.providers.finland_fmi.lightning import GEOMETRY_3067

#: How many rows the server-side cursor hands over at a time.
FETCH_SIZE = 50_000

#: The factor that folds MeteoCat's ``(network_version, flash_id)`` into one key.
#: Flash ids are 32-bit integers, below it.
METEOCAT_FLASH_KEY_FACTOR = 10_000_000_000

#: The error read for a stroke whose error is not known (USWFS's semi-major axis
#: published as 0), in metres: the largest finite float, so that no E_max keeps
#: it. ``Strokes`` refuses infinities.
UNKNOWN_ERROR_M = sys.float_info.max

#: What a ground-only read adds to the provider's own filter, in the stored
#: ``lightning_filter``.
CLOUD_TO_GROUND_FILTER: dict[str, Any] = {"cloud_to_ground": True}

#: The condition a ground-only read adds to its query.
CLOUD_TO_GROUND_SQL = "\n  AND l.cloud_to_ground"

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
  AND l.date_time >= :start AND l.date_time < :end{network}{ground}
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
  AND l.date_time >= :start AND l.date_time < :end{ground}
ORDER BY l.date_time, l.id
"""

ALASKA_USWFS_STROKES_SQL = """
SELECT l.id,
       CAST(a.flash_id AS bigint) AS flash_key,
       CAST(EXTRACT(EPOCH FROM l.date_time) AS double precision) AS t,
       ST_X(p.point) AS x,
       ST_Y(p.point) AS y,
       COALESCE(a.ellipse_semi_major_axis, :unknown_error) AS error
FROM lightning AS l
JOIN alaska_uswfs_lightning AS a ON a.id = l.id
CROSS JOIN LATERAL (SELECT {point} AS point) AS p
WHERE l.data_provider_id = :provider_id
  AND l.date_time >= :start AND l.date_time < :end{ground}
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
        The provider's own filter; the experiment stores
        :meth:`filter_for`'s, which adds the ground filter.
    default_srid : int
        The provider's projected CRS, used when a run does not name one.
    read : callable
        ``read(connection, provider_id, start, end, srid, fetch_size,
        cloud_to_ground_only=True)``, an iterator over
        :class:`~gisfire_algorithms.thunderstorm.Strokes` batches in time order.
    """

    provider_name: str
    provider_product: str
    lightning_filter: dict[str, Any]
    default_srid: int
    read: Callable[..., Iterator[Strokes]]

    def filter_for(self, cloud_to_ground_only: bool) -> dict[str, Any]:
        """The ``lightning_filter`` of a read: the provider's, plus the ground filter."""
        return {**self.lightning_filter, **(CLOUD_TO_GROUND_FILTER if cloud_to_ground_only else {})}


def ground_sql(cloud_to_ground_only: bool) -> str:
    """The condition a query adds for ``cloud_to_ground_only``: none, or ground strokes."""
    return CLOUD_TO_GROUND_SQL if cloud_to_ground_only else ""


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


def meteocat_strokes_sql(srid: int, cutoffs: dict[int, datetime.datetime],
                         cloud_to_ground_only: bool = True) -> tuple[str, dict[str, Any]]:
    """The query and the parameters it binds besides the provider and the period."""
    if srid == catalonia_meteocat.PROJECTED_SRID:
        point = GEOMETRY_25831.format(column="m.geometry_etrs89")
    else:
        point = f"ST_Transform(m.geometry_etrs89, {int(srid)})"
    network = "".join(
        f"\n  AND NOT (m.network_version = {int(version)} AND l.date_time >= :cutoff_{int(version)})"
        for version in sorted(cutoffs))
    sql = METEOCAT_STROKES_SQL.format(factor=METEOCAT_FLASH_KEY_FACTOR, point=point, network=network,
                                      ground=ground_sql(cloud_to_ground_only))
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
                          end: datetime.datetime, srid: int, fetch_size: int | None = None, *,
                          cloud_to_ground_only: bool = True) -> Iterator[Strokes]:
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
    cloud_to_ground_only : bool, optional
        Read ground strokes only (the default), or cloud strokes too.

    Yields
    ------
    Strokes
        Consecutive batches in ``(date_time, id)`` order; none for an empty
        period.
    """
    fetch_size = fetch_size or FETCH_SIZE
    sql, extra = meteocat_strokes_sql(srid, meteocat_network_cutoffs(connection, provider_id),
                                      cloud_to_ground_only)
    yield from _stream(connection, sql,
                       {"provider_id": provider_id, "start": start, "end": end, **extra},
                       fetch_size)


def fmi_strokes_sql(srid: int, cloud_to_ground_only: bool = True) -> str:
    """The query for FMI's strokes in ``srid``."""
    if srid == finland_fmi.PROJECTED_SRID:
        point = GEOMETRY_3067.format(column="f.geometry_etrs89")
    else:
        point = f"ST_Transform(f.geometry_etrs89, {int(srid)})"
    return FMI_STROKES_SQL.format(point=point, ground=ground_sql(cloud_to_ground_only))


def read_fmi_strokes(connection: Connection, provider_id: int, start: datetime.datetime,
                     end: datetime.datetime, srid: int, fetch_size: int | None = None, *,
                     cloud_to_ground_only: bool = True) -> Iterator[Strokes]:
    """FMI's strokes of ``[start, end)``, in batches.

    Parameters and batches as :func:`read_meteocat_strokes`, without a network
    filter: FMI has one network.
    """
    yield from _stream(connection, fmi_strokes_sql(srid, cloud_to_ground_only),
                       {"provider_id": provider_id, "start": start, "end": end},
                       fetch_size or FETCH_SIZE)


def alaska_uswfs_strokes_sql(srid: int, cloud_to_ground_only: bool = True) -> str:
    """The query for USWFS's Alaska strokes in ``srid``."""
    if srid == alaska_uswfs.PROJECTED_SRID:
        point = GEOMETRY_3338.format(column="l.geometry")
    else:
        point = f"ST_Transform(l.geometry, {int(srid)})"
    return ALASKA_USWFS_STROKES_SQL.format(point=point, ground=ground_sql(cloud_to_ground_only))


def read_alaska_uswfs_strokes(connection: Connection, provider_id: int,
                              start: datetime.datetime, end: datetime.datetime, srid: int,
                              fetch_size: int | None = None, *,
                              cloud_to_ground_only: bool = True) -> Iterator[Strokes]:
    """USWFS's Alaska strokes of ``[start, end)``, in batches.

    Parameters and batches as :func:`read_meteocat_strokes`, without a network
    filter. A stroke whose error is not known gets :data:`UNKNOWN_ERROR_M`.
    """
    yield from _stream(connection, alaska_uswfs_strokes_sql(srid, cloud_to_ground_only),
                       {"provider_id": provider_id, "start": start, "end": end,
                        "unknown_error": UNKNOWN_ERROR_M},
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
    alaska_uswfs.PROVIDER_NAME: StrokeReader(
        provider_name=alaska_uswfs.PROVIDER_NAME,
        provider_product=alaska_uswfs.PROVIDER_PRODUCT,
        lightning_filter={},
        default_srid=alaska_uswfs.PROJECTED_SRID,
        read=read_alaska_uswfs_strokes,
    ),
}
