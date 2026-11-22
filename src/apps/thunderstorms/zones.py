#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The zone of the thunderstorm rules: a network's nominal region plus 50 km.

See :doc:`/algorithms/thunderstorm_rules`. Each network has a fixed nominal region
(:data:`REGIONS`): FMI OCHA's Finland, MeteoCat IGN's Catalonia, USWFS the Census
Bureau's Alaska. Finland is OCHA's ``FIN`` alone: the Åland Islands, which OCHA
publishes as an entity of their own (``ALA``), are not part of the region, and
count only where they lie within 50 km of it (decided on 2026-11-22). The **zone**
is everything within :data:`ZONE_BUFFER_M` (50 km) of the region, measured in a
projected CRS (the network's own, the reader's ``default_srid``, unless told
otherwise). A stroke is in the zone when its distance to the region is at most
50 km, tested with shapely on the region's polygon: exact, with no buffer polygon
to approximate it (a 50 km buffer of OCHA's Finland, 3.75 M vertices, takes
PostGIS more than 10 minutes).

A **zone flash** has at least one stroke in the zone, even when the stroke that
represents it lies outside.

Used by the thunderstorm builder (which keeps only the storms with a zone flash),
the sweep's statistics and the episodes study.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from sqlalchemy import Connection
from sqlalchemy import text

from gisfire_algorithms.thunderstorm import Flashes
from src.apps.thunderstorms.readers import READERS
from src.providers import alaska_uswfs
from src.providers import catalonia_meteocat
from src.providers import finland_fmi

#: How far beyond the region the zone reaches, in metres.
ZONE_BUFFER_M = 50_000.0


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

#: The region's polygon in a projected CRS.
REGION_SQL = """
SELECT b.id, ST_AsBinary(ST_Transform(b.geometry, :srid)) AS wkb
FROM admin_boundary AS b
JOIN {table} AS p ON p.id = b.id
WHERE {column} = :value
ORDER BY b.id
"""


def read_region(connection: Connection, provider: str, srid: int | None = None) -> shapely.Geometry:
    """The provider's nominal region, prepared for the zone test.

    Parameters
    ----------
    srid : int, optional
        The projected CRS to read it in; the network's own (the reader's
        ``default_srid``) by default.

    Raises
    ------
    RuntimeError
        If the boundary is not in the database, or more than one row matches (two
        editions of its source, say).
    """
    region = REGIONS[provider]
    rows = connection.execute(text(REGION_SQL.format(table=region.table, column=region.column)),
                              {"srid": srid or READERS[provider].default_srid,
                               "value": region.value}).all()
    if not rows:
        raise RuntimeError(f"No boundary for {region.description} in the database: import it first")
    if len(rows) > 1:
        raise RuntimeError(f"{len(rows)} boundaries match {region.description} (admin_boundary "
                           f"ids {', '.join(str(row.id) for row in rows)}): keep one")
    geometry = shapely.from_wkb(bytes(rows[0].wkb))
    shapely.prepare(geometry)
    return geometry


def in_zone(region: shapely.Geometry, x, y) -> np.ndarray:
    """For each point, whether it is at most :data:`ZONE_BUFFER_M` from the region.

    ``x`` and ``y`` are in the region's CRS.
    """
    x = np.asarray(x, dtype=np.float64)
    if not len(x):
        return np.empty(0, dtype=bool)
    return shapely.dwithin(region, shapely.points(x, np.asarray(y, dtype=np.float64)),
                           ZONE_BUFFER_M)


def zone_stroke_counts(flashes: Flashes, inside: np.ndarray) -> np.ndarray:
    """For each flash, how many of its strokes are in the zone; a zone flash has one or more.

    ``inside`` is :func:`in_zone` of the strokes ``flashes`` were built from, in their
    order (``flashes.stroke_flash_index`` maps them).
    """
    return np.bincount(flashes.stroke_flash_index, weights=np.asarray(inside, dtype=np.float64),
                       minlength=len(flashes)).astype(np.int64)
