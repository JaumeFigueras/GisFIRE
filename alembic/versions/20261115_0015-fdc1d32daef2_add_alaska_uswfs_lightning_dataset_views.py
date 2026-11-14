"""add alaska uswfs lightning dataset views

Revision ID: fdc1d32daef2
Revises: a686e4263b1c
Create Date: 2026-11-15 00:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'fdc1d32daef2'
down_revision: str | None = 'a686e4263b1c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views of the same strokes, one per CRS, built like MeteoCat's of revision
# 9c4f1a7e3b62 and FMI's of 95b95aac852f: ``id`` first and an integer, one geometry
# per view, named ``geometry`` so a style written for one loads on the other.
#
# * ``v_alaska_uswfs_lightning_4326`` — the parent's EPSG:4326 point, which is the
#   point as published (WGS 84): there is no third, "as published" view.
# * ``v_alaska_uswfs_lightning_3338`` — NAD83 / Alaska Albers.
#
# The 3338 view has no column to select — the point is not stored in that CRS — so
# it reprojects the parent's point and **casts the result back** to
# ``geometry(Point,3338)``, keeping the type modifier QGIS reads type and SRID from.
# Revision a686e4263b1c created ``idx_lightning_alaska_uswfs_geometry_3338`` on
# exactly the same expression, on ``lightning`` and **partial** (``type =
# 'alaska_uswfs_lightning'``). The planner uses a partial index only when the query
# implies its predicate, and the join to ``alaska_uswfs_lightning`` does not tell it
# that, so both views also filter on ``l.type``. Changing the expression or the
# filter here means changing that index.
#
# There is no ``date_time_local``: the release's local time is unusable (three
# offsets over the years), and the published UTC reading *is* ``date_time``.
#
# The stroke's own columns. ``a`` is ``alaska_uswfs_lightning``, ``l`` ``lightning``,
# ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_COLUMNS = """
    l.id AS id,
    l.date_time AS date_time,
    l.peak_current AS peak_current,
    l.cloud_to_ground AS cloud_to_ground,
    a.flash_id AS flash_id,
    a.multiplicity AS multiplicity,
    a.stroke_index AS stroke_index,
    a.network_code AS network_code,
    a.sequence_number AS sequence_number,
    a.gdop AS gdop,
    a.ellipse_semi_major_axis AS ellipse_semi_major_axis,
    a.ellipse_semi_minor_axis AS ellipse_semi_minor_axis,
    a.ellipse_angle AS ellipse_angle,
    l.data_provider_id AS data_provider_id,
    dp.name AS data_provider_name,
    dp.product AS data_provider_product,
    l.admin_boundary_id AS admin_boundary_id,
    ab.name AS admin_boundary_name,
    ab.name_en AS admin_boundary_name_en,
    ab.level AS admin_boundary_level,
    l.created_at AS created_at,
    l.updated_at AS updated_at"""

_JOINS = """
JOIN lightning l ON l.id = a.id
LEFT JOIN data_provider dp ON dp.id = l.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = l.admin_boundary_id
WHERE l.type = 'alaska_uswfs_lightning'"""

#: The reprojection the 3338 view selects: the expression
#: ``idx_lightning_alaska_uswfs_geometry_3338`` is built on.
_GEOMETRY_3338 = "(st_transform(l.geometry, 3338)::geometry(Point,3338))"


def _view(name: str, geometry: str) -> ReplaceableObject:
    return ReplaceableObject(
        name,
        f"""
SELECT{_COLUMNS},
    {geometry} AS geometry
FROM alaska_uswfs_lightning a{_JOINS}
""",
    )


alaska_uswfs_lightning_4326_view = _view("v_alaska_uswfs_lightning_4326", "l.geometry")
alaska_uswfs_lightning_3338_view = _view("v_alaska_uswfs_lightning_3338", _GEOMETRY_3338)

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    alaska_uswfs_lightning_4326_view,
    alaska_uswfs_lightning_3338_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the two Alaska lightning views. Like every dataset view they add no
    storage and no constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
