"""add thunderstorm 3338 views

Revision ID: 92cfa94c65e5
Revises: fdc1d32daef2
Create Date: 2026-11-15 00:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '92cfa94c65e5'
down_revision: str | None = 'fdc1d32daef2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# The nine thunderstorm layers in NAD83 / Alaska Albers (EPSG:3338), the CRS of
# the Alaska Lightning Detection Network's strokes (USWFS), the third lightning
# provider, beside their EPSG:4326, ETRS89 / UTM 31N (``_25831``) and ETRS89 /
# TM35FIN (``_3067``) versions:
#
# * from revision 7a1c4e9b2d56, unchanged since: ``v_thunderstorm_evolution``,
#   ``v_thunderstorm_evolution_hull``, ``v_thunderstorm_evolution_convex_hull``,
#   ``v_thunderstorm_vector`` and ``v_thunderstorm_path``;
# * as revision e7147a41b62b left them: ``v_thunderstorm``,
#   ``v_thunderstorm_convex_hull``, ``v_thunderstorm_cellsearch_centre`` and
#   ``v_thunderstorm_cellsearch_path``.
#
# Each is the same SQL as its ``_3067`` twin of revision 5353369ebdc8 with 3338
# for 3067, copied here rather than imported from that revision, so that this one
# keeps its own copy whatever later revisions do (``test/test_migrations.py``
# checks the two copies differ only by the SRID). The rules hold: ``id`` first and
# an integer, one geometry per view named ``geometry``, complete runs only, every
# reprojection cast back to ``geometry(<type>,3338)`` so QGIS detects type and
# SRID. The geometries are computed per row, with no expression index: a run is
# thousands of thunderstorms, not millions of strokes.
#
# A view per CRS, not per provider: every thunderstorm view shows every run,
# whichever provider's strokes it was built from.
#
# The antimeridian: a hull is built in the run's CRS and stored in EPSG:4326 vertex
# by vertex, so a storm across 180° (the Aleutians, the Bering Sea) has vertices
# at both +179° and -179°. Reprojected here vertex by vertex, it comes back whole;
# the 4326 layers draw the same polygon the long way round the globe.

SRID = 3338

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

_FLASHES_FROM = """
FROM thunderstorm_cellsearch_flash c
JOIN thunderstorm t ON t.id = c.thunderstorm_id
JOIN thunderstorm_experiment e ON e.id = c.experiment_id
JOIN lightning l ON l.id = c.lightning_id
WHERE e.status = 'complete'"""


def _cast(expression: str, kind: str) -> str:
    return f"({expression})::geometry({kind},{SRID})"


def _in(column: str) -> str:
    """A stored 4326 geometry, reprojected to 3338."""
    return f"ST_Transform({column}, {SRID})"


def _name(base: str) -> str:
    return f"{base}_{SRID}"


thunderstorm_view = ReplaceableObject(_name("v_thunderstorm"), f"""
SELECT{_THUNDERSTORM_COLUMNS},
    {_cast(_in("t.concave_hull"), "Polygon")} AS geometry{_THUNDERSTORM_FROM}
""")

thunderstorm_convex_hull_view = ReplaceableObject(_name("v_thunderstorm_convex_hull"), f"""
SELECT{_THUNDERSTORM_COLUMNS},
    {_cast(f"ST_ConvexHull({_in('t.concave_hull')})", "Polygon")} AS geometry{_THUNDERSTORM_FROM}
""")

evolution_view = ReplaceableObject(_name("v_thunderstorm_evolution"), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},{_MOTION_COLUMNS},
    {_cast(_in("mv.centre"), "Point")} AS geometry{_WINDOW_FROM}
""")

evolution_hull_view = ReplaceableObject(_name("v_thunderstorm_evolution_hull"), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},
    {_cast(_in("mv.concave_hull"), "Polygon")} AS geometry{_WINDOW_FROM}
""")

evolution_convex_hull_view = ReplaceableObject(_name("v_thunderstorm_evolution_convex_hull"), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},
    {_cast(f"ST_ConvexHull({_in('mv.concave_hull')})", "Polygon")} AS geometry{_WINDOW_FROM}
""")

vector_view = ReplaceableObject(_name("v_thunderstorm_vector"), f"""{_VECTORS}
SELECT{_WINDOW_COLUMNS},{_MOTION_COLUMNS},
    {_cast(f"ST_MakeLine({_in('mv.previous_centre')}, {_in('mv.centre')})", "LineString")} AS geometry{_WINDOW_FROM}
WHERE mv.previous_centre IS NOT NULL
""")

path_view = ReplaceableObject(_name("v_thunderstorm_path"), f"""{_VECTORS},
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
        {_cast(f"ST_MakeLine({_in('mv.centre')} ORDER BY mv.sequence)", "LineString")} AS geometry
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

cellsearch_centre_view = ReplaceableObject(_name("v_thunderstorm_cellsearch_centre"), f"""
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
    {_cast(_in("c.centre"), "Point")} AS geometry{_FLASHES_FROM}
""")

_LIFETIME_MIN = "EXTRACT(EPOCH FROM p.date_time_end - p.date_time_start)::double precision / 60"

cellsearch_path_view = ReplaceableObject(_name("v_thunderstorm_cellsearch_path"), f"""
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
        {_cast(f"ST_MakeLine({_in('c.centre')} ORDER BY c.sequence)", "LineString")} AS geometry{_FLASHES_FROM}
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
    {_LIFETIME_MIN} AS lifetime_min,
    p.number_of_flashes / NULLIF({_LIFETIME_MIN}, 0) AS flash_rate_per_min,
    t.area AS area_km2,
    100 * p.number_of_flashes / t.area AS density_per_100km2,
    ST_Length(p.line_4326::geography) AS path_length_m,
    ST_Distance(p.first_centre::geography, p.last_centre::geography) AS net_displacement_m,
    p.geometry AS geometry
FROM path p
JOIN thunderstorm t ON t.id = p.thunderstorm_id
JOIN thunderstorm_experiment e ON e.id = p.experiment_id
""")

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    thunderstorm_view,
    thunderstorm_convex_hull_view,
    evolution_view,
    evolution_hull_view,
    evolution_convex_hull_view,
    vector_view,
    path_view,
    cellsearch_centre_view,
    cellsearch_path_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the nine thunderstorm views in EPSG:3338. No storage and no
    constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
