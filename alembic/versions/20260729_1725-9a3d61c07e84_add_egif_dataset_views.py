"""add egif dataset views

Revision ID: 9a3d61c07e84
Revises: 7f2c85d43b19
Create Date: 2026-07-29 17:25:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '9a3d61c07e84'
down_revision: str | None = '7f2c85d43b19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# The one thing that is new here is which geometry ``v_egif_wildfire`` exposes.
# Every other wildfire view shows a perimeter; EGIF publishes none and never will,
# so a perimeter column would be a layer of 13,656 NULLs. What an EGIF fire does
# have is the point it started at, on its ignition, and the useful QGIS layer is
# the fire's attributes mapped there. The view therefore joins the ignition and
# exposes ``i.geometry`` — a POINT, on a view whose name says wildfire, which is
# deliberate and is the whole reason this comment exists.
#
# ``v_egif_ignition`` is the same point without the report around it, matching
# ``v_gfa_ignition`` column for column so a style written for one loads on the
# other.

# The generic ignition columns and the lookups behind their foreign keys, shared
# by both views. ``i`` is ``ignition``, ``dpi`` ``data_provider``, ``abi``
# ``admin_boundary``.
_IGNITION_COLUMNS = """
    i.date_time AS date_time,
    i.date_time AT TIME ZONE i.time_zone AS date_time_local,
    i.time_zone AS time_zone,
    i.data_provider_id AS data_provider_id,
    dpi.name AS data_provider_name,
    dpi.product AS data_provider_product,
    i.admin_boundary_id AS admin_boundary_id,
    abi.name AS admin_boundary_name,
    abi.name_en AS admin_boundary_name_en,
    abi.level AS admin_boundary_level"""

# The EGIF ignition's own columns, likewise shared. ``n`` is ``egif_ignition``.
_EGIF_IGNITION_COLUMNS = """
    n.utm_zone AS utm_zone,
    n.utm_x AS utm_x,
    n.utm_y AS utm_y,
    n.datum AS datum,
    n.start_point_count AS start_point_count,
    n.mtn_sheet AS mtn_sheet,
    n.mtn_grid AS mtn_grid,
    n.place_name AS place_name"""

_IGNITION_JOINS = """
JOIN ignition i ON i.id = n.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id"""


egif_ignition_view = ReplaceableObject(
    "v_egif_ignition",
    f"""
SELECT
    i.id AS id,
    n.report_number AS report_number,{_IGNITION_COLUMNS},{_EGIF_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM egif_ignition n{_IGNITION_JOINS}
""",
)


# The report is LEFT JOINed and contributes exactly two columns. ``has_full_report``
# is the provenance rule made visible — a fire read only from an Excel export has
# no report row — and ``days_since_storm`` is the field that justifies loading the
# XML at all. The rest of ``egif_wildfire_report`` is a join away and does not
# belong in a QGIS attribute table.
egif_wildfire_view = ReplaceableObject(
    "v_egif_wildfire",
    """
SELECT
    w.id AS id,
    s.report_number AS report_number,
    s.egif_id AS egif_id,
    s.campaign AS campaign,
    s.status AS status,
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
    s.ccaa_name AS ccaa_name,
    s.province_name AS province_name,
    s.province_ine_code AS province_ine_code,
    s.municipality_name AS municipality_name,
    s.municipality_ine_code AS municipality_ine_code,
    s.comarca_name AS comarca_name,
    s.minor_entity_name AS minor_entity_name,
    s.affected_municipality_count AS affected_municipality_count,
    s.cause_id AS cause_id,
    c.code AS cause_code,
    c.label AS cause_label,
    c.label_en AS cause_label_en,
    s.motivation_id AS motivation_id,
    m.code AS motivation_code,
    m.label AS motivation_label,
    m.label_en AS motivation_label_en,
    s.area_ha_wooded AS area_ha_wooded,
    s.area_ha_non_wooded AS area_ha_non_wooded,
    s.area_ha_forest_total AS area_ha_forest_total,
    s.area_ha_agricultural AS area_ha_agricultural,
    s.area_ha_other_non_forest AS area_ha_other_non_forest,
    s.wui_affected AS wui_affected,
    s.wui_compact AS wui_compact,
    s.wui_scattered AS wui_scattered,
    s.wui_isolated AS wui_isolated,
    s.protected_space_affected AS protected_space_affected,
    s.agricultural_land_affected AS agricultural_land_affected,
    s.zar_affected AS zar_affected,
    s.pss_report_number AS pss_report_number,
    s.ignition_id AS ignition_id,
    n.utm_zone AS utm_zone,
    n.utm_x AS utm_x,
    n.utm_y AS utm_y,
    n.datum AS datum,
    n.start_point_count AS start_point_count,
    n.mtn_sheet AS mtn_sheet,
    n.mtn_grid AS mtn_grid,
    n.place_name AS place_name,
    (r.id IS NOT NULL) AS has_full_report,
    r.days_since_storm AS days_since_storm,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM egif_wildfire s
JOIN wildfire w ON w.id = s.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN egif_fire_cause c ON c.id = s.cause_id
LEFT JOIN egif_fire_motivation m ON m.id = s.motivation_id
JOIN egif_ignition n ON n.id = s.ignition_id
JOIN ignition i ON i.id = n.id
LEFT JOIN egif_wildfire_report r ON r.id = s.id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    egif_ignition_view,
    egif_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the two EGIF views. Like the views of revision e4b7c1a90f3d they add
    no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
