"""add darpa dataset views

Revision ID: a7e4c02f9d16
Revises: d5f2a91c3b48
Create Date: 2026-08-02 11:45:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'a7e4c02f9d16'
down_revision: str | None = 'd5f2a91c3b48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views over the Catalan perimeters, following the four rules set out in
# revision e4b7c1a90f3d: ``id`` first and an integer, the geometry selected
# straight from its table so its type modifier survives, one geometry per view,
# and a ``*_local`` companion for every datetime.
#
# Two rather than one for the ICNF's reason exactly: the perimeter is stored in
# both the CRS it was published in and EPSG:4326, the two live on different
# tables, and a QGIS layer takes a single geometry column. Both expose it as
# ``perimeter``, so a style or an expression written against one loads on the
# other — and on the two ICNF views as well.
#
# The one thing here that no other view has is the EGIF link. It is a column the
# import never fills, so today ``egif_report_number`` is NULL on every row of both
# views; it is selected anyway, because the whole point of the next application is
# to fill it and the layer that shows whether it worked should not need a
# migration first.

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
    because the link is unfilled on every row this import produces — an inner join
    would make both views empty.

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
    s.part_count AS part_count,
    s.egif_wildfire_id AS egif_wildfire_id,
    e.report_number AS egif_report_number,
    e.campaign AS egif_campaign,
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


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    darpa_wildfire_4326_view,
    darpa_wildfire_25831_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the two Catalan views. Like every other view in this schema they add
    no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
