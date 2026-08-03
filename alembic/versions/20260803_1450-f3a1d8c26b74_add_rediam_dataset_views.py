"""add rediam dataset views

Revision ID: f3a1d8c26b74
Revises: e9e992e02a11
Create Date: 2026-08-03 14:50:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'f3a1d8c26b74'
down_revision: str | None = 'e9e992e02a11'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Three views over the Andalusian perimeters, following the four rules set out in
# revision e4b7c1a90f3d: ``id`` first and an integer, the geometry selected straight
# from its table so its type modifier survives, one geometry per view, and a
# ``*_local`` companion for every datetime.
#
# Two of the three are the same fires with a different geometry, for the ICNF and
# DARPA reason exactly: the perimeter is stored both in the CRS it was published in
# and in EPSG:4326, the two live on different tables, and a QGIS layer takes a single
# geometry column. Both expose it as ``perimeter``, so a style or an expression
# written against one loads on the other — and on the DARPA and ICNF views as well.
#
# The third is the ignition point. It is a third *view* rather than a fourth column
# on the first two for the same reason it is a third *table*: the published point is
# frequently outside the published perimeter, so they are two observations and one
# QGIS layer cannot show both geometries anyway.
#
# Like the Catalan views, these select the EGIF link that nothing fills in yet. The
# whole point of the next application is to fill it, and the layer that shows whether
# it worked should not need a migration first.

# Columns shared by every wildfire, plus the lookups behind its foreign keys.
# ``w`` is ``wildfire``, ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_WILDFIRE_COLUMNS = """
    w.id AS id,
    w.start_date_time AS start_date_time,
    w.end_date_time AS end_date_time,
    w.start_date_time AT TIME ZONE w.time_zone AS start_date_time_local,
    w.end_date_time AT TIME ZONE w.time_zone AS end_date_time_local,
    w.time_zone AS time_zone,
    w.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    w.admin_boundary_id AS admin_boundary_id,
    ab.name AS admin_boundary_name,
    ab.name_en AS admin_boundary_name_en,
    ab.level AS admin_boundary_level,
    w.created_at AS created_at,
    w.updated_at AS updated_at"""

# The joins that go with the columns above. LEFT for both lookups: an outer join
# cannot drop a wildfire even if a boundary was never resolved for it.
_WILDFIRE_JOINS = """
JOIN wildfire w ON w.id = s.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id"""


def _rediam_wildfire_view(name: str, geometry: str) -> ReplaceableObject:
    """Build one of the two REDIAM perimeter views.

    The two differ only in which perimeter they expose, so the column list is written
    once here rather than copied.

    ``e`` is ``egif_wildfire``, joined LEFT because the link is unfilled on every row
    this import produces — an inner join would make both views empty. ``ig`` and
    ``ri`` are the ignition and its Andalusian half, joined LEFT because four fires
    out of five have no published point: an inner join would silently reduce the
    layer to 2021-2024.

    ``ignition_x`` and ``ignition_y`` are the published UTM coordinates rather than a
    second geometry, which the view could not expose anyway. They are what makes the
    point visible in the attribute table of a perimeter layer; the point *as a point*
    is ``v_rediam_ignition``.

    Parameters
    ----------
    name : str
        Name of the view.
    geometry : str
        The qualified geometry column to expose as ``perimeter``.

    Returns
    -------
    ReplaceableObject
        The view definition.
    """
    return ReplaceableObject(
        name,
        f"""
SELECT{_WILDFIRE_COLUMNS},
    s.source_layer AS source_layer,
    s.code AS code,
    s.fire_date AS fire_date,
    s.year AS year,
    s.municipality_name AS municipality_name,
    s.province_name AS province_name,
    s.part_count AS part_count,
    s.area_ha_wooded AS area_ha_wooded,
    s.area_ha_scrub AS area_ha_scrub,
    s.area_ha_grassland AS area_ha_grassland,
    s.area_ha_wooded + s.area_ha_scrub + s.area_ha_grassland AS area_ha_published_total,
    s.ignition_id AS ignition_id,
    ri.utm_x AS ignition_x,
    ri.utm_y AS ignition_y,
    ig.date_time AS ignition_date_time,
    s.egif_wildfire_id AS egif_wildfire_id,
    e.report_number AS egif_report_number,
    e.campaign AS egif_campaign,
    s.match_method AS match_method,
    s.match_confidence AS match_confidence,
    s.matched_at AS matched_at,
    {geometry} AS perimeter
FROM rediam_wildfire s{_WILDFIRE_JOINS}
LEFT JOIN egif_wildfire e ON e.id = s.egif_wildfire_id
LEFT JOIN ignition ig ON ig.id = s.ignition_id
LEFT JOIN rediam_ignition ri ON ri.id = s.ignition_id
""",
    )


#: Andalusia, EPSG:4326 — the perimeter reprojected at import time, on ``wildfire``.
rediam_wildfire_4326_view = _rediam_wildfire_view("v_rediam_wildfire_4326", "w.perimeter")

#: Andalusia, EPSG:25830 (ETRS89 / UTM 30N) — the perimeter on the grid the service
#: published it on. Not 3042, which is what the ``.prj`` resolves to: same projection,
#: opposite axis order, and the files follow the one stored here.
rediam_wildfire_25830_view = _rediam_wildfire_view(
    "v_rediam_wildfire_25830", "s.perimeter_etrs89_utm30n")

#: The published ignition points, 2021-2024. ``i`` is ``ignition``, ``s`` its
#: Andalusian half; the perimeter is joined LEFT so the layer can be labelled with
#: the fire it belongs to without depending on one having been imported.
rediam_ignition_view = ReplaceableObject(
    "v_rediam_ignition",
    """
SELECT
    i.id AS id,
    s.source_layer AS source_layer,
    s.code AS code,
    s.fire_date AS fire_date,
    s.utm_x AS utm_x,
    s.utm_y AS utm_y,
    i.date_time AS date_time,
    i.date_time AT TIME ZONE i.time_zone AS date_time_local,
    i.time_zone AS time_zone,
    i.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    i.admin_boundary_id AS admin_boundary_id,
    ab.name AS admin_boundary_name,
    ab.name_en AS admin_boundary_name_en,
    ab.level AS admin_boundary_level,
    w.id AS wildfire_id,
    w.municipality_name AS municipality_name,
    w.province_name AS province_name,
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM rediam_ignition s
JOIN ignition i ON i.id = s.id
LEFT JOIN data_provider dp ON dp.id = i.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = i.admin_boundary_id
LEFT JOIN rediam_wildfire w ON w.ignition_id = s.id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    rediam_wildfire_4326_view,
    rediam_wildfire_25830_view,
    rediam_ignition_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the three Andalusian views. Like every other view in this schema they add
    no storage and no constraints, so dropping and recreating them costs nothing but
    the ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
