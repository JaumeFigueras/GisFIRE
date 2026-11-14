"""add cellsearch views

Revision ID: e7147a41b62b
Revises: 687521539664
Create Date: 2026-11-13 10:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'e7147a41b62b'
down_revision: str | None = '687521539664'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The revision whose definitions of ``v_thunderstorm`` and
#: ``v_thunderstorm_convex_hull`` (and their ``_25831`` twins) this one replaces.
PREVIOUS = '7a1c4e9b2d56'


# --- View definitions -------------------------------------------------------
#
# The rules of revision e4b7c1a90f3d and 7a1c4e9b2d56 hold: ``id`` first and an
# integer, one geometry per view named ``geometry``, each layer in EPSG:4326 and
# in ETRS89 / UTM 31N (``_25831``), complete runs only.
#
# * ``v_thunderstorm`` and ``v_thunderstorm_convex_hull`` (replaced) — the same
#   rows and columns as in 7a1c4e9b2d56 plus three, after
#   ``lightnings_per_minute``: ``number_of_flashes``, ``area_km2`` and
#   ``density_per_100km2`` (= 100 · flashes / area, as the article reports it).
#   All three are NULL for an algorithm without flashes or an undefined area.
#   ``duration_s`` stays the span of the linked *strokes*; the article's flash
#   lifetime is in the Cellsearch path view.
# * ``v_thunderstorm_cellsearch_centre`` (new) — one point per flash of a kept
#   cell: the cell's running centre right after it (the article's Fig. 8), with
#   the time of the flash's representative stroke.
# * ``v_thunderstorm_cellsearch_path`` (new) — one line per cell through those
#   centres in sequence, with the article's per-cell statistics computed from
#   the **flashes**: ``lifetime_min`` (last − first flash), ``flash_rate_per_min``
#   (NULL for a lifetime of 0), ``area_km2`` and ``density_per_100km2``; and the
#   path's geodesic length and the distance from its first to its last centre.
#   Its ``id`` is the cell's (one path per cell). Every kept cell has at least
#   N_min ≥ 3 flashes, so every kept cell has a path; ``HAVING count(*) >= 2``
#   only guards against a one-point line.
#
# The 4326 point view selects the stored centre straight from its table, so it
# keeps its type modifier; every reprojection and line is cast back to
# ``geometry(<type>,<srid>)``.

#: The thunderstorm's columns, as in 7a1c4e9b2d56 plus the three new ones.
_THUNDERSTORM_COLUMNS = """
    t.id AS id,
    t.experiment_id AS experiment_id,
    e.algorithm AS algorithm,
    e.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    t.label AS label,
    t.date_time_start AS date_time_start,
    t.date_time_end AS date_time_end,
    EXTRACT(EPOCH FROM t.date_time_end - t.date_time_start)::double precision AS duration_s,
    t.number_of_lightnings AS number_of_lightnings,
    t.number_of_lightnings / GREATEST(
        EXTRACT(EPOCH FROM t.date_time_end - t.date_time_start)::double precision / 60, 1)
        AS lightnings_per_minute,
    t.number_of_flashes AS number_of_flashes,
    t.area AS area_km2,
    100 * t.number_of_flashes / t.area AS density_per_100km2,
    t.created_at AS created_at,
    t.updated_at AS updated_at"""

_THUNDERSTORM_FROM = """
FROM thunderstorm t
JOIN thunderstorm_experiment e ON e.id = t.experiment_id
LEFT JOIN data_provider dp ON dp.id = e.data_provider_id
WHERE e.status = 'complete'"""

#: The flashes of the kept cells of complete runs: ``c`` the flash, ``t`` its
#: cell, ``e`` the experiment, ``l`` the representative stroke.
_FLASHES_FROM = """
FROM thunderstorm_cellsearch_flash c
JOIN thunderstorm t ON t.id = c.thunderstorm_id
JOIN thunderstorm_experiment e ON e.id = c.experiment_id
JOIN lightning l ON l.id = c.lightning_id
WHERE e.status = 'complete'"""


def _cast(expression: str, kind: str, srid: int) -> str:
    return f"({expression})::geometry({kind},{srid})"


def _in(column: str, srid: int) -> str:
    """A stored 4326 geometry, reprojected when the view is not in 4326."""
    return column if srid == 4326 else f"ST_Transform({column}, {srid})"


def _name(base: str, srid: int) -> str:
    return base if srid == 4326 else f"{base}_{srid}"


def _thunderstorm(srid: int) -> ReplaceableObject:
    geometry = "t.concave_hull" if srid == 4326 else _cast(_in("t.concave_hull", srid), "Polygon", srid)
    return ReplaceableObject(_name("v_thunderstorm", srid), f"""
SELECT{_THUNDERSTORM_COLUMNS},
    {geometry} AS geometry{_THUNDERSTORM_FROM}
""")


def _thunderstorm_convex_hull(srid: int) -> ReplaceableObject:
    geometry = _cast(f"ST_ConvexHull({_in('t.concave_hull', srid)})", "Polygon", srid)
    return ReplaceableObject(_name("v_thunderstorm_convex_hull", srid), f"""
SELECT{_THUNDERSTORM_COLUMNS},
    {geometry} AS geometry{_THUNDERSTORM_FROM}
""")


def _cellsearch_centre(srid: int) -> ReplaceableObject:
    geometry = "c.centre" if srid == 4326 else _cast(_in("c.centre", srid), "Point", srid)
    return ReplaceableObject(_name("v_thunderstorm_cellsearch_centre", srid), f"""
SELECT
    c.id AS id,
    c.thunderstorm_id AS thunderstorm_id,
    c.experiment_id AS experiment_id,
    e.algorithm AS algorithm,
    t.label AS label,
    t.number_of_flashes AS cell_number_of_flashes,
    c.sequence AS sequence,
    c.lightning_id AS lightning_id,
    l.date_time AS date_time,
    {geometry} AS geometry{_FLASHES_FROM}
""")


def _cellsearch_path(srid: int) -> ReplaceableObject:
    line = _cast(f"ST_MakeLine({_in('c.centre', srid)} ORDER BY c.sequence)", "LineString", srid)
    lifetime_min = "EXTRACT(EPOCH FROM p.date_time_end - p.date_time_start)::double precision / 60"
    return ReplaceableObject(_name("v_thunderstorm_cellsearch_path", srid), f"""
WITH path AS (
    SELECT
        c.thunderstorm_id,
        c.experiment_id,
        count(*)::integer AS number_of_flashes,
        min(l.date_time) AS date_time_start,
        max(l.date_time) AS date_time_end,
        ST_MakeLine(c.centre ORDER BY c.sequence) AS line_4326,
        (array_agg(c.centre ORDER BY c.sequence))[1] AS first_centre,
        (array_agg(c.centre ORDER BY c.sequence DESC))[1] AS last_centre,
        {line} AS geometry{_FLASHES_FROM}
    GROUP BY c.thunderstorm_id, c.experiment_id
    HAVING count(*) >= 2
)
SELECT
    t.id AS id,
    p.experiment_id AS experiment_id,
    e.algorithm AS algorithm,
    t.label AS label,
    p.number_of_flashes AS number_of_flashes,
    p.date_time_start AS date_time_start,
    p.date_time_end AS date_time_end,
    {lifetime_min} AS lifetime_min,
    p.number_of_flashes / NULLIF({lifetime_min}, 0) AS flash_rate_per_min,
    t.area AS area_km2,
    100 * p.number_of_flashes / t.area AS density_per_100km2,
    ST_Length(p.line_4326::geography) AS path_length_m,
    ST_Distance(p.first_centre::geography, p.last_centre::geography) AS net_displacement_m,
    p.geometry AS geometry
FROM path p
JOIN thunderstorm t ON t.id = p.thunderstorm_id
JOIN thunderstorm_experiment e ON e.id = p.experiment_id
""")


#: The views this revision replaces, in order; their previous definitions are
#: read from revision :data:`PREVIOUS`.
REPLACED = [layer(srid) for layer in (_thunderstorm, _thunderstorm_convex_hull)
            for srid in (4326, 25831)]

#: The views this revision creates, in order; ``downgrade()`` walks it backwards.
CREATED = [layer(srid) for layer in (_cellsearch_centre, _cellsearch_path)
           for srid in (4326, 25831)]


def _previous(name: str) -> ReplaceableObject:
    """The definition of ``name`` in revision :data:`PREVIOUS`.

    That revision keeps its views in a list rather than one variable each, so
    ``op.replace_view(..., replaces="<revision>.<variable>")`` cannot name them;
    this looks the old definition up by name instead. Either way the old SQL is
    the old revision's own copy.
    """
    module = op.get_context().script.get_revision(PREVIOUS).module
    return next(view for view in module.VIEWS if view.name == name)


def upgrade() -> None:
    """Apply this revision.

    Replaces the four thunderstorm hull views to show the flash count, the area
    and the density, and creates the four Cellsearch views. No storage and no
    constraints.
    """
    for view in REPLACED:
        op.drop_view(_previous(view.name))
        op.create_view(view)
    for view in CREATED:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(CREATED):
        op.drop_view(view)
    for view in reversed(REPLACED):
        op.drop_view(view)
        op.create_view(_previous(view.name))
