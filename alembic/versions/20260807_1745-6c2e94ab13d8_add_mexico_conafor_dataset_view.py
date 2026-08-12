"""add mexico conafor dataset view

Revision ID: 6c2e94ab13d8
Revises: 3f8a5c21d7b4
Create Date: 2026-08-07 17:45:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '6c2e94ab13d8'
down_revision: str | None = '3f8a5c21d7b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# One view, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# **One and not two**, which makes CONAFOR the only perimeter provider in the
# schema with a single wildfire view. ICNF, DARPA, REDIAM and NBAC each get a pair
# — one per CRS — because each publishes on a national grid that GisFIRE keeps
# alongside the EPSG:4326 reprojection. CONAFOR publishes in EPSG:4326 in all
# thirteen archives. There is no second CRS to expose, so there is no
# ``v_conafor_wildfire_<epsg>`` naming to adopt either: the view is
# ``v_conafor_wildfire``, like ``v_gwis_wildfire`` and ``v_gfa_wildfire``.
#
# The cause is joined and flattened rather than left as a foreign key. It is four
# columns, and the alternative is a QGIS user styling a layer by fire cause through
# a relation, which QGIS's symbology cannot do. ``cause_normalised`` is the one to
# categorise on — see revision 3f8a5c21d7b4 for why the published ``cause`` is not.

# The generic wildfire columns and the lookups behind their foreign keys. ``w`` is
# ``wildfire``, ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_WILDFIRE_COLUMNS = """
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
    ab.level AS admin_boundary_level"""


conafor_wildfire_view = ReplaceableObject(
    "v_conafor_wildfire",
    f"""
SELECT
    w.id AS id,
    c.fire_code AS fire_code,
    c.year AS year,
    c.source_layer AS source_layer,
    c.state_code AS state_code,
    c.state_name AS state_name,
    c.municipality_code AS municipality_code,
    c.municipality_name AS municipality_name,
    c.property_name AS property_name,
    c.date_time_precision AS date_time_precision,
    c.cause_id AS cause_id,
    fc.cause AS cause,
    fc.cause_normalised AS cause_normalised,
    fc.cause_en AS cause_en,
    fc.specific_cause AS specific_cause,
    fc.specific_cause_en AS specific_cause_en,
    c.fire_type AS fire_type,
    c.impact_level AS impact_level,
    c.vegetation_type AS vegetation_type,
    c.vegetation_type_code AS vegetation_type_code,
    c.protected_area_name AS protected_area_name,
    c.area_ha_protected AS area_ha_protected,
    c.area_ha AS area_ha,
    c.area_ha_tree AS area_ha_tree,
    c.area_ha_regeneration AS area_ha_regeneration,
    c.area_ha_shrub AS area_ha_shrub,
    c.area_ha_herbaceous AS area_ha_herbaceous,
    c.area_ha_litter AS area_ha_litter,
    c.area_ha_organic_soil AS area_ha_organic_soil,
    c.perimeter_source AS perimeter_source,{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM conafor_wildfire c
JOIN wildfire w ON w.id = c.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN conafor_fire_cause fc ON fc.id = c.cause_id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards.
VIEWS = [
    conafor_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the Mexican view. Like the views of revision e4b7c1a90f3d it adds no
    storage and no constraints, so dropping and recreating it costs nothing but the
    ``CREATE`` statement.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
