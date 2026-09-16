"""add australia csiro dataset views

Revision ID: 5d8a2f4c6b19
Revises: ac2b51efcb0f
Create Date: 2026-08-12 17:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '5d8a2f4c6b19'
down_revision: str | None = 'ac2b51efcb0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# There is one geometry to expose and not two, unlike the Portuguese, Canadian,
# Catalan and Andalusian pairs: this provider stores no second geometry, its
# published EPSG:4283 being geographic degrees 1.8 m from EPSG:4326. See revision
# ac2b51efcb0f.
#
# What is unusual here is the *second* view, which is the same view with a WHERE.
# ``v_csiro_wildfire`` is 285,232 rows of which 48% are prescribed burns and 27%
# are published as ``Unknown``; ``v_csiro_bushfire`` is the 85,336 the agencies
# called bushfires. Both are needed and neither is the other's replacement: a QGIS
# layer of Australian *fire* is the first, a layer of Australian *wildfire* is the
# second, and the difference between them is 84.8 million hectares of deliberate
# burning. Leaving only the first would make every map drawn from it wrong in a way
# no legend would show.
#
# It is a filtered view and not a materialised one: it adds no storage over a table
# already carrying 155.8 million vertices, and ``ix_csiro_wildfire_fire_type`` is
# what makes the filter cheap.

# The generic wildfire columns and the lookups behind their foreign keys, shared by
# both views. ``w`` is ``wildfire``, ``dp`` ``data_provider``, ``ab``
# ``admin_boundary``.
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

# The Australian row's own columns, likewise shared. ``c`` is ``csiro_wildfire``.
#
# Both halves of every normalised pair are exposed. The published spelling is what a
# reader recognises from the geodatabase and the normalised one is what a filter
# uses, and a QGIS user with only the second cannot tell ``NULL`` cause *not
# published* from ``NULL`` cause *published as OTHER*.
_CSIRO_COLUMNS = """
    c.source_layer AS source_layer,
    c.object_id AS object_id,
    c.year AS year,
    c.fire_id AS fire_id,
    c.fire_id_is_sentinel AS fire_id_is_sentinel,
    c.fire_name AS fire_name,
    c.state_published AS state_published,
    c.state_code AS state_code,
    c.agency AS agency,
    c.fire_type_published AS fire_type_published,
    c.fire_type AS fire_type,
    c.cause_published AS cause_published,
    c.cause AS cause,
    c.capture_method_published AS capture_method_published,
    c.capture_method AS capture_method,
    c.ignition_date AS ignition_date,
    c.extinguish_date AS extinguish_date,
    c.capture_date AS capture_date,
    c.date_source AS date_source,
    c.date_time_precision AS date_time_precision,
    c.dates_plausible AS dates_plausible,
    c.area_ha AS area_ha,
    c.perim_km AS perim_km,
    c.part_count AS part_count,
    c.attributes_agree AS attributes_agree"""

_CSIRO_JOINS = """
JOIN wildfire w ON w.id = c.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id"""


csiro_wildfire_view = ReplaceableObject(
    "v_csiro_wildfire",
    f"""
SELECT
    c.id AS id,{_CSIRO_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM csiro_wildfire c{_CSIRO_JOINS}
""",
)

csiro_bushfire_view = ReplaceableObject(
    "v_csiro_bushfire",
    f"""
SELECT
    c.id AS id,{_CSIRO_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM csiro_wildfire c{_CSIRO_JOINS}
WHERE c.fire_type = 'bushfire'
""",
)

#: In creation order; dropped in reverse.
VIEWS = (csiro_wildfire_view, csiro_bushfire_view)


def upgrade() -> None:
    """Apply this revision.

    Creates the two Australian views. Like the views of revision e4b7c1a90f3d they
    add no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements — which is what makes them the right place for the
    prescribed-burn filter, a decision that may well be revisited.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
