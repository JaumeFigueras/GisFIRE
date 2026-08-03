"""show darpa match provenance in views

Revision ID: c07b48e93a51
Revises: b93f7c15ea20
Create Date: 2026-08-02 18:25:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'c07b48e93a51'
down_revision: str | None = 'b93f7c15ea20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# The two Catalan views again, with the three columns b93f7c15ea20 added:
# ``match_method``, ``match_confidence`` and ``matched_at``.
#
# They belong in the layer rather than a join away because the thing a person does
# with this dataset in QGIS is *look at the bindings* — style the perimeters by
# confidence, and see at a glance where the exact identifier matches stop and the
# name matches begin. A layer that showed only ``egif_report_number`` would make
# a 1989 name guess and a 2013 identifier match look identical on the map.
#
# A full copy of the SELECT, as the recipe requires: each revision is a snapshot,
# so this one does not import a7e4c02f9d16's definition, it restates it.

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


def _darpa_wildfire_view(name: str, geometry: str) -> ReplaceableObject:
    """Build one of the two DARPA views.

    The two differ only in which perimeter they expose, so the column list is
    written once here rather than copied. ``e`` is ``egif_wildfire``, joined LEFT
    because most rows have no binding — an inner join would turn these into a layer
    of the matched fires only, which is the opposite of what they are for.
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
    s.part_count AS part_count,
    s.egif_wildfire_id AS egif_wildfire_id,
    e.report_number AS egif_report_number,
    e.campaign AS egif_campaign,
    s.match_method AS match_method,
    s.match_confidence AS match_confidence,
    s.matched_at AS matched_at,
    {geometry} AS perimeter
FROM darpa_wildfire s{_WILDFIRE_JOINS}
LEFT JOIN egif_wildfire e ON e.id = s.egif_wildfire_id
""",
    )


#: Catalonia, EPSG:4326 — the perimeter reprojected at import time, on ``wildfire``.
darpa_wildfire_4326_view = _darpa_wildfire_view("v_darpa_wildfire_4326", "w.perimeter")

#: Catalonia, EPSG:25831 (ETRS89 / UTM 31N) — the perimeter on the grid the
#: department published it on.
darpa_wildfire_25831_view = _darpa_wildfire_view(
    "v_darpa_wildfire_25831", "s.perimeter_etrs89_utm31n")


#: The views this revision replaces, each with the identifier of the definition it
#: supersedes. ``downgrade()`` walks it backwards.
REPLACEMENTS = [
    (darpa_wildfire_4326_view, "a7e4c02f9d16.darpa_wildfire_4326_view"),
    (darpa_wildfire_25831_view, "a7e4c02f9d16.darpa_wildfire_25831_view"),
]


def upgrade() -> None:
    """Apply this revision."""
    for view, previous in REPLACEMENTS:
        op.replace_view(view, replaces=previous)


def downgrade() -> None:
    """Revert this revision."""
    for view, previous in reversed(REPLACEMENTS):
        op.replace_view(view, replace_with=previous)
