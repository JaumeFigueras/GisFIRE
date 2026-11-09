"""add thunderstorm views

Revision ID: 7a1c4e9b2d56
Revises: 3e8b5d1c7f20
Create Date: 2026-11-08 11:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '7a1c4e9b2d56'
down_revision: str | None = '3e8b5d1c7f20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Seven layers, each in EPSG:4326 and in ETRS89 / UTM 31N (``_25831``), the grid
# of the only lightning provider so far. The rules of revision e4b7c1a90f3d hold:
# ``id`` first and an integer, one geometry per view, named ``geometry``.
#
# * ``v_thunderstorm`` — each thunderstorm with its concave hull.
# * ``v_thunderstorm_convex_hull`` — the same rows with the convex hull.
# * ``v_thunderstorm_evolution`` — each window's gravity centre, with the
#   direction vector that brought the thunderstorm there.
# * ``v_thunderstorm_evolution_hull`` — each window's concave hull.
# * ``v_thunderstorm_evolution_convex_hull`` — each window's convex hull.
# * ``v_thunderstorm_vector`` — each direction vector as a segment from the
#   previous centre to this one, for drawing with an arrow.
# * ``v_thunderstorm_path`` — each thunderstorm's path in a tracking, the line
#   through its centres, with the summary of its motion.
#
# **Complete runs only.** A run being built, or one that failed, is half a
# result: every view requires ``status = 'complete'`` on the experiment, and the
# window views on the tracking as well.
#
# **Nothing here is stored.** The convex hull, the vectors and the path are
# computed from the stored centres and concave hulls, so they cannot go stale:
#
# * The *convex hull* is ``ST_ConvexHull`` of the concave hull. A concave hull
#   contains every stroke and its vertices are strokes, so this is the convex
#   hull of the strokes.
# * A window stands for its **midpoint**, ``date_time``: a moving average
#   stamped at the window's end would lag the thunderstorm by half a window.
# * The *direction vector* of a window is the move from the previous window's
#   centre (``LAG`` over ``sequence``) to its own: ``displacement_m`` and
#   ``bearing_deg`` (0 = north, clockwise) on the WGS 84 spheroid, ``elapsed_s``
#   between the two midpoints, ``speed_m_s``, and the east and north components
#   ``u_m_s`` / ``v_m_s``. Average the components, never the bearings: the mean
#   of 350° and 10° is north, not south. The first window has none.
# * The *path* needs two windows: a thunderstorm tracked in one window has no
#   path row. Its ``id`` is the ``id`` of its first window, unique per tracking
#   and thunderstorm. ``bearing_deg`` is the direction of the mean velocity.
#
# The 4326 views select stored geometries straight from their tables where
# there is one. Everything else — every reprojection, hull, segment and line —
# is cast back to ``geometry(<type>,<srid>)`` so that the view keeps a typed
# geometry and QGIS detects it on its own. The 25831 geometries are computed per
# row and have no expression index: a run is some 60,000 thunderstorms and
# 600,000 windows, not six million strokes.

#: The thunderstorm's columns. ``t`` is ``thunderstorm``, ``e``
#: ``thunderstorm_experiment``, ``dp`` ``data_provider``. Strokes per minute
#: count at least one minute, so a burst of strokes in a few seconds is not
#: thousands per minute.
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
    t.created_at AS created_at,
    t.updated_at AS updated_at"""

_THUNDERSTORM_FROM = """
FROM thunderstorm t
JOIN thunderstorm_experiment e ON e.id = t.experiment_id
LEFT JOIN data_provider dp ON dp.id = e.data_provider_id
WHERE e.status = 'complete'"""

#: The windows of complete runs, each with its direction vector, in three steps:
#: ``motion`` finds the previous centre and midpoint, ``step`` measures the move
#: on the spheroid, ``vector`` turns it into a velocity.
_VECTORS = """
WITH motion AS (
    SELECT
        ev.id, ev.tracking_id, ev.thunderstorm_id, ev.experiment_id, ev.sequence,
        ev.window_start, ev.window_end,
        ev.window_start + (ev.window_end - ev.window_start) / 2 AS date_time,
        ev.number_of_lightnings, ev.centre, ev.concave_hull, ev.created_at, ev.updated_at,
        LAG(ev.centre) OVER w AS previous_centre,
        LAG(ev.window_start + (ev.window_end - ev.window_start) / 2) OVER w AS previous_date_time
    FROM thunderstorm_evolution ev
    JOIN thunderstorm_tracking tr ON tr.id = ev.tracking_id
    JOIN thunderstorm_experiment e ON e.id = ev.experiment_id
    WHERE tr.status = 'complete' AND e.status = 'complete'
    WINDOW w AS (PARTITION BY ev.tracking_id, ev.thunderstorm_id ORDER BY ev.sequence)
), step AS (
    SELECT
        motion.*,
        ST_Distance(previous_centre::geography, centre::geography) AS displacement_m,
        degrees(ST_Azimuth(previous_centre::geography, centre::geography)) AS bearing_deg,
        EXTRACT(EPOCH FROM date_time - previous_date_time)::double precision AS elapsed_s
    FROM motion
), vector AS (
    SELECT
        step.*,
        displacement_m / NULLIF(elapsed_s, 0) AS speed_m_s,
        -- A centre that did not move has no bearing but a velocity of zero.
        displacement_m / NULLIF(elapsed_s, 0) * COALESCE(sin(radians(bearing_deg)), 0) AS u_m_s,
        displacement_m / NULLIF(elapsed_s, 0) * COALESCE(cos(radians(bearing_deg)), 0) AS v_m_s
    FROM step
)"""

#: A window's columns. ``mv`` is the ``vector`` step above, ``t`` the
#: thunderstorm, ``tr`` the tracking.
_WINDOW_COLUMNS = """
    mv.id AS id,
    mv.tracking_id AS tracking_id,
    mv.thunderstorm_id AS thunderstorm_id,
    mv.experiment_id AS experiment_id,
    t.label AS label,
    tr.window_length AS window_length,
    tr.window_step AS window_step,
    mv.sequence AS sequence,
    mv.window_start AS window_start,
    mv.window_end AS window_end,
    mv.date_time AS date_time,
    mv.number_of_lightnings AS number_of_lightnings,
    mv.created_at AS created_at,
    mv.updated_at AS updated_at"""

_MOTION_COLUMNS = """
    mv.displacement_m AS displacement_m,
    mv.elapsed_s AS elapsed_s,
    mv.speed_m_s AS speed_m_s,
    mv.bearing_deg AS bearing_deg,
    mv.u_m_s AS u_m_s,
    mv.v_m_s AS v_m_s"""

_WINDOW_FROM = """
FROM vector mv
JOIN thunderstorm t ON t.id = mv.thunderstorm_id
JOIN thunderstorm_tracking tr ON tr.id = mv.tracking_id"""


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


def _evolution(srid: int) -> ReplaceableObject:
    geometry = "mv.centre" if srid == 4326 else _cast(_in("mv.centre", srid), "Point", srid)
    return ReplaceableObject(_name("v_thunderstorm_evolution", srid), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},{_MOTION_COLUMNS},
    {geometry} AS geometry{_WINDOW_FROM}
""")


def _evolution_hull(srid: int) -> ReplaceableObject:
    geometry = "mv.concave_hull" if srid == 4326 else _cast(_in("mv.concave_hull", srid), "Polygon", srid)
    return ReplaceableObject(_name("v_thunderstorm_evolution_hull", srid), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},
    {geometry} AS geometry{_WINDOW_FROM}
""")


def _evolution_convex_hull(srid: int) -> ReplaceableObject:
    geometry = _cast(f"ST_ConvexHull({_in('mv.concave_hull', srid)})", "Polygon", srid)
    return ReplaceableObject(_name("v_thunderstorm_evolution_convex_hull", srid), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},
    {geometry} AS geometry{_WINDOW_FROM}
""")


def _vector(srid: int) -> ReplaceableObject:
    segment = f"ST_MakeLine({_in('mv.previous_centre', srid)}, {_in('mv.centre', srid)})"
    return ReplaceableObject(_name("v_thunderstorm_vector", srid), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},{_MOTION_COLUMNS},
    {_cast(segment, "LineString", srid)} AS geometry{_WINDOW_FROM}
WHERE mv.previous_centre IS NOT NULL
""")


def _path(srid: int) -> ReplaceableObject:
    line = f"ST_MakeLine({_in('mv.centre', srid)} ORDER BY mv.sequence)"
    return ReplaceableObject(_name("v_thunderstorm_path", srid), f"""{_VECTORS},
path AS (
    SELECT
        min(mv.id) AS id,
        mv.tracking_id,
        mv.thunderstorm_id,
        mv.experiment_id,
        count(*)::integer AS number_of_windows,
        min(mv.date_time) AS date_time_start,
        max(mv.date_time) AS date_time_end,
        EXTRACT(EPOCH FROM max(mv.date_time) - min(mv.date_time))::double precision AS duration_s,
        sum(mv.displacement_m) AS distance_m,
        ST_Distance((array_agg(mv.centre ORDER BY mv.sequence))[1]::geography,
                    (array_agg(mv.centre ORDER BY mv.sequence DESC))[1]::geography)
            AS net_displacement_m,
        avg(mv.u_m_s) AS mean_u_m_s,
        avg(mv.v_m_s) AS mean_v_m_s,
        {_cast(line, "LineString", srid)} AS geometry
    FROM vector mv
    GROUP BY mv.tracking_id, mv.thunderstorm_id, mv.experiment_id
    HAVING count(*) >= 2
)
SELECT
    p.id AS id,
    p.tracking_id AS tracking_id,
    p.thunderstorm_id AS thunderstorm_id,
    p.experiment_id AS experiment_id,
    t.label AS label,
    tr.window_length AS window_length,
    tr.window_step AS window_step,
    p.number_of_windows AS number_of_windows,
    p.date_time_start AS date_time_start,
    p.date_time_end AS date_time_end,
    p.duration_s AS duration_s,
    p.distance_m AS distance_m,
    p.net_displacement_m AS net_displacement_m,
    p.distance_m / NULLIF(p.duration_s, 0) AS mean_speed_m_s,
    p.mean_u_m_s AS mean_u_m_s,
    p.mean_v_m_s AS mean_v_m_s,
    CASE WHEN p.mean_u_m_s = 0 AND p.mean_v_m_s = 0 THEN NULL
         ELSE (degrees(atan2(p.mean_u_m_s, p.mean_v_m_s)) + 360)::numeric % 360
    END::double precision AS bearing_deg,
    p.geometry AS geometry
FROM path p
JOIN thunderstorm t ON t.id = p.thunderstorm_id
JOIN thunderstorm_tracking tr ON tr.id = p.tracking_id
""")


_LAYERS = (_thunderstorm, _thunderstorm_convex_hull, _evolution, _evolution_hull,
           _evolution_convex_hull, _vector, _path)

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [layer(srid) for layer in _LAYERS for srid in (4326, 25831)]


def upgrade() -> None:
    """Apply this revision.

    Creates the fourteen thunderstorm views. They add no storage and no
    constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
