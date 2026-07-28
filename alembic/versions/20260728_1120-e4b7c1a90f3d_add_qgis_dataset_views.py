"""add qgis dataset views

Revision ID: e4b7c1a90f3d
Revises: 3c9d61f0a742
Create Date: 2026-07-28 11:20:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'e4b7c1a90f3d'
down_revision: str | None = '3c9d61f0a742'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# One view per dataset, flattening the joined table inheritance into the single
# relation QGIS wants: the generic columns from ``wildfire`` / ``ignition``, the
# provider's own columns from its subclass table, and the names behind the
# foreign keys so the attribute table reads as text instead of integers.
#
# Four rules the SELECTs follow, all of them for QGIS's benefit:
#
# * ``id`` comes first and is the parent's integer primary key. QGIS cannot infer
#   a key for a view and needs a unique integer column to identify features.
# * The geometry column is selected straight from its table, never wrapped in a
#   function. That preserves the type modifier — ``geometry(MultiPolygon,4326)``
#   — so the view registers itself in PostGIS's ``geometry_columns`` and QGIS
#   picks up geometry type and SRID on its own. ``ST_Transform(...)`` and friends
#   return an untyped ``geometry`` and would have to be cast back explicitly.
# * One geometry per view, which is why ICNF gets two: the published EPSG:3763
#   perimeter and the EPSG:4326 one live on different tables and a QGIS layer
#   takes a single geometry column. Both are named ``perimeter``, so a style or
#   an expression written against one works on the other.
# * Every datetime comes with a ``*_local`` companion, the reading as the
#   provider published it, recovered with ``AT TIME ZONE`` (NULL where the
#   provider gave an instant and no zone was recorded). See the module docstring
#   of ``src/data_model/wildfire.py``.
#
# These definitions are a snapshot: a later revision that changes a view carries
# its own copy and uses ``op.replace_view(..., replaces="e4b7c1a90f3d.<name>")``.
# See ``src/data_model/replaceable.py``.

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


gwis_wildfire_view = ReplaceableObject(
    "v_gwis_wildfire",
    f"""
SELECT{_WILDFIRE_COLUMNS},
    s.gwis_id AS gwis_id,
    w.perimeter AS perimeter
FROM gwis_wildfire s{_WILDFIRE_JOINS}
""",
)


gfa_wildfire_view = ReplaceableObject(
    "v_gfa_wildfire",
    f"""
SELECT{_WILDFIRE_COLUMNS},
    s.gfa_id AS gfa_id,
    s.gfa_ignition_id AS gfa_ignition_id,
    s.size_km2 AS size_km2,
    s.perimeter_km AS perimeter_km,
    s.duration_days AS duration_days,
    s.fire_line_km AS fire_line_km,
    s.spread_km2_day AS spread_km2_day,
    s.speed_km_day AS speed_km_day,
    s.direction AS direction,
    s.direction_fraction AS direction_fraction,
    s.modis_tile AS modis_tile,
    s.landcover AS landcover,
    s.landcover_fraction AS landcover_fraction,
    s.gfed_region AS gfed_region,
    w.perimeter AS perimeter
FROM gfa_wildfire s{_WILDFIRE_JOINS}
""",
)


gfa_ignition_view = ReplaceableObject(
    "v_gfa_ignition",
    """
SELECT
    i.id AS id,
    s.gfa_id AS gfa_id,
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
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM gfa_ignition s
JOIN ignition i ON i.id = s.id
LEFT JOIN data_provider dp ON dp.id = i.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = i.admin_boundary_id
""",
)


def _icnf_wildfire_view(name: str, geometry: str) -> ReplaceableObject:
    """Build one of the two ICNF views.

    The two differ only in which perimeter they expose, so the column list is
    written once here rather than copied. ``c`` is ``icnf_fire_cause``, joined
    LEFT because the ICNF leaves the cause unknown on many fires.

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
    s.sgif_code AS sgif_code,
    s.anepc_code AS anepc_code,
    s.year AS year,
    s.date_time_precision AS date_time_precision,
    s.first_response_date_time AS first_response_date_time,
    s.first_response_date_time AT TIME ZONE w.time_zone AS first_response_date_time_local,
    s.duration_minutes AS duration_minutes,
    s.dicofre_code AS dicofre_code,
    s.nuts3_name AS nuts3_name,
    s.district_name AS district_name,
    s.municipality_name AS municipality_name,
    s.parish_name AS parish_name,
    s.place_name AS place_name,
    s.cause_id AS cause_id,
    c.code AS cause_code,
    c.type AS cause_type,
    c.type_en AS cause_type_en,
    c.description AS cause_description,
    c.description_en AS cause_description_en,
    s.area_ha_gis AS area_ha_gis,
    s.area_ha_sgif AS area_ha_sgif,
    s.area_ha_forest_stand AS area_ha_forest_stand,
    s.area_ha_shrubland AS area_ha_shrubland,
    s.area_ha_agricultural AS area_ha_agricultural,
    s.edition_date_time AS edition_date_time,
    {geometry} AS perimeter
FROM icnf_wildfire s{_WILDFIRE_JOINS}
LEFT JOIN icnf_fire_cause c ON c.id = s.cause_id
""",
    )


#: Portugal, EPSG:4326 — the perimeter reprojected at import time, on ``wildfire``.
icnf_wildfire_4326_view = _icnf_wildfire_view("v_icnf_wildfire_4326", "w.perimeter")

#: Portugal, EPSG:3763 (ETRS89 / PT-TM06) — the perimeter as the ICNF published it.
icnf_wildfire_3763_view = _icnf_wildfire_view("v_icnf_wildfire_3763", "s.perimeter_etrs89_tm06")


#: Every view this revision creates, in dependency order (there is none between
#: them, so this is just the creation order; ``downgrade()`` walks it backwards).
VIEWS = [
    gwis_wildfire_view,
    gfa_wildfire_view,
    gfa_ignition_view,
    icnf_wildfire_4326_view,
    icnf_wildfire_3763_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates one read-only view per dataset. They add no storage and no
    constraints — dropping them all and starting again costs nothing but the
    ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
