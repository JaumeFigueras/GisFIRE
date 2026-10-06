"""add new zealand wod dataset views

Revision ID: 2f5e28048454
Revises: dd3d58146f8b
Create Date: 2026-10-06 21:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '2f5e28048454'
down_revision: str | None = 'dd3d58146f8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Four views, following the rules of revision e4b7c1a90f3d: ``id`` first and an
# integer, the geometry selected straight from its table so its type modifier
# survives, one geometry per view, and a ``*_local`` companion for every datetime.
#
# Two per spatial table, one per CRS, as ICNF, DARPA, REDIAM and NBAC have: EPSG:4326
# for a layer beside every other country's, EPSG:2193 (NZTM2000) for anything
# measured or drawn on the grid the WOD publishes on. A pair names its geometry
# column the same, so a style written for one loads on the other.
#
# The wildfire views carry the record and its perimeter. **Every fire is a row**,
# the 125,931 point records with a NULL perimeter: a NULL geometry is a feature that
# does not draw, which is the right depiction of a fire reported without a shape, and
# the layer's feature count stays the dataset's. Filter on ``has_perimeter`` for the
# 2,089 that draw.
#
# The ignition views carry everything: the point, the record, and **all the terrain
# and weather** the compilers attached. Those were attributed at the point (or over
# the polygon, for polygon records — see ``wod_terrain``), so the point layer is the
# one a user analysing fire environment loads, and having it whole in one layer is
# the reason the views exist. ``id`` is the ignition's; ``wildfire_id`` leads back.
#
# Because these views select every terrain and weather column, they block ``ALTER
# COLUMN ... TYPE`` on all of them: a type change there means replacing the views in
# the same revision.

# The record's own columns, shared by all four views. ``f`` is ``wod_wildfire``.
_RECORD_COLUMNS = """
    f.wod_id AS wod_id,
    f.source AS source,
    f.org_id AS org_id,
    f.dropped_fenz_org_id AS dropped_fenz_org_id,
    f.year AS year,
    f.report_date AS report_date,
    f.report_time AS report_time,
    f.season AS season,
    f.financial_year AS financial_year,
    f.area_ha AS area_ha,
    f.area_category AS area_category,
    f.ignition_source AS ignition_source,
    f.fire_cause AS fire_cause,
    f.original_vegetation AS original_vegetation,
    f.fenz_district AS fenz_district,
    f.perimeter_nztm IS NOT NULL AS has_perimeter"""

# The generic wildfire columns and the lookups behind their foreign keys. ``w`` is
# ``wildfire``, ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_WILDFIRE_COLUMNS = """
    w.start_date_time AS start_date_time,
    w.start_date_time AT TIME ZONE w.time_zone AS start_date_time_local,
    w.time_zone AS time_zone,
    w.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    w.admin_boundary_id AS admin_boundary_id,
    ab.name AS admin_boundary_name,
    ab.name_en AS admin_boundary_name_en,
    ab.level AS admin_boundary_level"""

_WILDFIRE_JOINS = """
JOIN wildfire w ON w.id = f.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id"""

# The generic ignition columns. ``i`` is ``ignition``.
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

# From the point to everything else. LEFT joins throughout: every point has its fire
# and every fire its terrain and weather, but a view that silently dropped a point
# if one ever did not would hide exactly the defect it should show.
_IGNITION_JOINS = """
JOIN ignition i ON i.id = g.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id
LEFT JOIN wod_wildfire f ON f.ignition_id = g.id
LEFT JOIN wod_terrain t ON t.id = f.id
LEFT JOIN wod_weather m ON m.id = f.id"""

# The terrain columns. ``t`` is ``wod_terrain``.
_TERRAIN_COLUMNS = """
    t.elev AS elev,
    t.min_elev AS min_elev,
    t.max_elev AS max_elev,
    t.slope AS slope,
    t.min_slope AS min_slope,
    t.max_slope AS max_slope,
    t.aspect_deg AS aspect_deg,
    t.aspect_car AS aspect_car,
    t.aspect_car_2 AS aspect_car_2,
    t.aspect_car_3 AS aspect_car_3,
    t.land_cvr AS land_cvr,
    t.land_cvr_2 AS land_cvr_2,
    t.land_cvr_3 AS land_cvr_3,
    t.fuel_type AS fuel_type,
    t.fuel_class AS fuel_class,
    t.landform AS landform,
    t.landform_2 AS landform_2,
    t.landform_3 AS landform_3"""

# The weather columns. ``m`` is ``wod_weather``.
_WEATHER_COLUMNS = """
    m.clim_zn_name AS clim_zn_name,
    m.wx_name AS wx_name,
    m.wx_id AS wx_id,
    m.wx_dist AS wx_dist,
    m.temp AS temp,
    m.temp_noon AS temp_noon,
    m.temp_max_8b AS temp_max_8b,
    m.temp_min_8b AS temp_min_8b,
    m.temp_avg_8b AS temp_avg_8b,
    m.temp_max_8a AS temp_max_8a,
    m.temp_min_8a AS temp_min_8a,
    m.temp_avg_8a AS temp_avg_8a,
    m.rh AS rh,
    m.rh_noon AS rh_noon,
    m.rh_max_8b AS rh_max_8b,
    m.rh_min_8b AS rh_min_8b,
    m.rh_avg_8b AS rh_avg_8b,
    m.rh_max_8a AS rh_max_8a,
    m.rh_min_8a AS rh_min_8a,
    m.rh_avg_8a AS rh_avg_8a,
    m.ws AS ws,
    m.ws_noon AS ws_noon,
    m.ws_max_8b AS ws_max_8b,
    m.ws_min_8b AS ws_min_8b,
    m.ws_avg_8b AS ws_avg_8b,
    m.ws_max_8a AS ws_max_8a,
    m.ws_min_8a AS ws_min_8a,
    m.ws_avg_8a AS ws_avg_8a,
    m.wd AS wd,
    m.soil_moist AS soil_moist,
    m.soil_temp AS soil_temp,
    m.ffmc AS ffmc,
    m.ffmc_noon AS ffmc_noon,
    m.ffmc_8b AS ffmc_8b,
    m.ffmc_8a AS ffmc_8a,
    m.isi AS isi,
    m.isi_noon AS isi_noon,
    m.isi_8b AS isi_8b,
    m.isi_8a AS isi_8a,
    m.fwi AS fwi,
    m.fwi_noon AS fwi_noon,
    m.fwi_8b AS fwi_8b,
    m.fwi_8a AS fwi_8a,
    m.fdc AS fdc,
    m.fdc_noon AS fdc_noon,
    m.fdc_8b AS fdc_8b,
    m.fdc_8a AS fdc_8a,
    m.hfi AS hfi,
    m.hfi_noon AS hfi_noon,
    m.hfi_8b AS hfi_8b,
    m.hfi_8a AS hfi_8a,
    m.ros AS ros,
    m.ros_noon AS ros_noon,
    m.ros_8b AS ros_8b,
    m.ros_8a AS ros_8a,
    m.dmc_noon AS dmc_noon,
    m.dc_noon AS dc_noon,
    m.bui_noon AS bui_noon,
    m.dsr_noon AS dsr_noon,
    m.precip_noon AS precip_noon,
    m.precip_24hr AS precip_24hr,
    m.precip_48hr AS precip_48hr,
    m.precip_72hr AS precip_72hr,
    m.no_rain_1 AS no_rain_1,
    m.no_rain_2 AS no_rain_2,
    m.no_rain_3 AS no_rain_3,
    m.soi AS soi,
    m.enso AS enso"""


def _wildfire_view(name: str, perimeter: str) -> ReplaceableObject:
    return ReplaceableObject(
        name,
        f"""
SELECT
    w.id AS id,{_RECORD_COLUMNS},{_WILDFIRE_COLUMNS},
    f.ignition_id AS ignition_id,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    {perimeter} AS perimeter
FROM wod_wildfire f{_WILDFIRE_JOINS}
""",
    )


def _ignition_view(name: str, geometry: str) -> ReplaceableObject:
    return ReplaceableObject(
        name,
        f"""
SELECT
    i.id AS id,
    f.id AS wildfire_id,{_RECORD_COLUMNS},{_IGNITION_COLUMNS},{_TERRAIN_COLUMNS},{_WEATHER_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    {geometry} AS geometry
FROM wod_ignition g{_IGNITION_JOINS}
""",
    )


wod_wildfire_view = _wildfire_view("v_wod_wildfire", "w.perimeter")
wod_wildfire_2193_view = _wildfire_view("v_wod_wildfire_2193", "f.perimeter_nztm")
wod_ignition_view = _ignition_view("v_wod_ignition", "i.geometry")
wod_ignition_2193_view = _ignition_view("v_wod_ignition_2193", "g.geometry_nztm")

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    wod_wildfire_view,
    wod_wildfire_2193_view,
    wod_ignition_view,
    wod_ignition_2193_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the four New Zealand views. Like every dataset view they add no storage
    and no constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
