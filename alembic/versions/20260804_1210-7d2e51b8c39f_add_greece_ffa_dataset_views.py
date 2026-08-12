"""add greece ffa dataset views

Revision ID: 7d2e51b8c39f
Revises: 46ccdd5b462b
Create Date: 2026-08-04 12:10:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '7d2e51b8c39f'
down_revision: str | None = '46ccdd5b462b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# ``v_greece_ffa_wildfire`` exposes a POINT, the second wildfire view to do so
# after ``v_egif_wildfire`` and for the same reason: the Fire Service publishes no
# perimeter and never will, so the useful QGIS layer is the fire's attributes
# mapped at the point it was reported. See revision 9a3d61c07e84.
#
# It is an INNER join to the ignition, as the EGIF one is, and here that decision
# hides far more rows: **only 54,491 of the 260,194 fires have a point**, because
# no year before 2020 publishes a coordinate. The view is therefore the *mappable*
# fifth of the dataset, and a count taken from it is not a count of Greek fires.
# Anything counting fires reads ``greece_ffa_wildfire``; this is a layer.
#
# A LEFT JOIN was the alternative and is worse for the one job a view has here: it
# would hand QGIS 205,703 features with no geometry, which render as nothing,
# select as nothing, and make the layer's feature count a lie in the other
# direction.

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

_IGNITION_JOINS = """
JOIN ignition i ON i.id = n.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id"""


greece_ffa_ignition_view = ReplaceableObject(
    "v_greece_ffa_ignition",
    f"""
SELECT
    i.id AS id,
    n.year AS year,
    n.record_number AS record_number,
    n.engage_id AS engage_id,{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM greece_ffa_ignition n{_IGNITION_JOINS}
""",
)


# The deployment block is carried through in full. It is thirteen columns of
# attribute table, which is a lot — and it is also the only thing in GisFIRE that
# measures a response rather than an event, so styling a layer by "how many
# aircraft flew to this fire" is a thing a user of this dataset will want to do
# and cannot do through a join in QGIS's symbology.
greece_ffa_wildfire_view = ReplaceableObject(
    "v_greece_ffa_wildfire",
    """
SELECT
    w.id AS id,
    g.year AS year,
    g.source_sheet AS source_sheet,
    g.record_number AS record_number,
    g.engage_id AS engage_id,
    g.incident_category AS incident_category,
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
    g.station_name AS station_name,
    g.prefecture_name AS prefecture_name,
    g.forest_district_name AS forest_district_name,
    g.municipality_name AS municipality_name,
    g.locality_name AS locality_name,
    g.address AS address,
    g.area_ha_forest AS area_ha_forest,
    g.area_ha_forest_land AS area_ha_forest_land,
    g.area_ha_grove AS area_ha_grove,
    g.area_ha_grassland AS area_ha_grassland,
    g.area_ha_reeds_marsh AS area_ha_reeds_marsh,
    g.area_ha_agricultural AS area_ha_agricultural,
    g.area_ha_crop_residue AS area_ha_crop_residue,
    g.area_ha_landfill AS area_ha_landfill,
    g.personnel_fire_service AS personnel_fire_service,
    g.personnel_infantry_units AS personnel_infantry_units,
    g.personnel_volunteers AS personnel_volunteers,
    g.personnel_army AS personnel_army,
    g.personnel_other AS personnel_other,
    g.vehicles_fire_service AS vehicles_fire_service,
    g.vehicles_public_service AS vehicles_public_service,
    g.vehicles_water_tankers AS vehicles_water_tankers,
    g.vehicles_machinery AS vehicles_machinery,
    g.aircraft_helicopters AS aircraft_helicopters,
    g.aircraft_cl415 AS aircraft_cl415,
    g.aircraft_cl215 AS aircraft_cl215,
    g.aircraft_pzl AS aircraft_pzl,
    g.aircraft_gru AS aircraft_gru,
    g.aircraft_leased_helicopters AS aircraft_leased_helicopters,
    g.aircraft_leased_planes AS aircraft_leased_planes,
    g.aircraft_other_agencies AS aircraft_other_agencies,
    g.ignition_id AS ignition_id,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM greece_ffa_wildfire g
JOIN wildfire w ON w.id = g.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
JOIN greece_ffa_ignition n ON n.id = g.ignition_id
JOIN ignition i ON i.id = n.id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    greece_ffa_ignition_view,
    greece_ffa_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the two Greek views. Like the views of revision e4b7c1a90f3d they add
    no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
