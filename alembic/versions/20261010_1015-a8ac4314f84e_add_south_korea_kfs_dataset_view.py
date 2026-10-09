"""add south korea kfs dataset view

Revision ID: a8ac4314f84e
Revises: 8cbaa9e5a65e
Create Date: 2026-10-10 10:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'a8ac4314f84e'
down_revision: str | None = '8cbaa9e5a65e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# One view, following the rules of revision e4b7c1a90f3d — ``id`` first and an
# integer, a ``*_local`` companion for every datetime — except the one about the
# geometry: **this is the first dataset view with no geometry at all.** The
# Korea Forest Service publishes place names and no coordinate, so there is no
# perimeter and no ignition to select, and QGIS loads the view as a table.
#
# The romanized names and the English cause text sit next to the published ones,
# so the table can be read without reading Hangul. The admin boundary is joined
# like every other view's although it is NULL on every row today: it is where a
# fire will show once the names are matched against Korean boundaries.
kfs_wildfire_view = ReplaceableObject(
    "v_kfs_wildfire",
    """
SELECT
    w.id AS id,
    k.year AS year,
    k.source_file AS source_file,
    k.source_row AS source_row,
    w.start_date_time AS start_date_time,
    w.end_date_time AS end_date_time,
    w.start_date_time AT TIME ZONE w.time_zone AS start_date_time_local,
    w.end_date_time AT TIME ZONE w.time_zone AS end_date_time_local,
    w.time_zone AS time_zone,
    k.end_date_problem AS end_date_problem,
    w.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    w.admin_boundary_id AS admin_boundary_id,
    ab.name AS admin_boundary_name,
    ab.name_en AS admin_boundary_name_en,
    ab.level AS admin_boundary_level,
    k.office_name AS office_name,
    k.office_name_rr AS office_name_rr,
    k.province_name AS province_name,
    k.province_name_rr AS province_name_rr,
    k.municipality_name AS municipality_name,
    k.municipality_name_rr AS municipality_name_rr,
    k.township_name AS township_name,
    k.township_name_rr AS township_name_rr,
    k.village_name AS village_name,
    k.village_name_rr AS village_name_rr,
    k.cause_category_code AS cause_category_code,
    k.cause_detail AS cause_detail,
    k.cause_text AS cause_text,
    k.cause_text_en AS cause_text_en,
    k.cause_class AS cause_class,
    k.fire_cause AS fire_cause,
    k.cause_suspected AS cause_suspected,
    k.area_ha AS area_ha,
    w.created_at AS created_at,
    w.updated_at AS updated_at
FROM kfs_wildfire k
JOIN wildfire w ON w.id = k.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
""",
)

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards.
VIEWS = [
    kfs_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision."""
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
