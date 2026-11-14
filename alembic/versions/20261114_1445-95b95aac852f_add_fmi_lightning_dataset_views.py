"""add fmi lightning dataset views

Revision ID: 95b95aac852f
Revises: fe72ef3ef7c8
Create Date: 2026-11-14 14:45:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '95b95aac852f'
down_revision: str | None = 'fe72ef3ef7c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Three views of the same strokes, one per CRS, exactly as MeteoCat's of revision
# 9c4f1a7e3b62: ``id`` first and an integer, one geometry per view, all named
# ``geometry`` so a style written for one loads on the others.
#
# * ``v_fmi_lightning_4326`` — the parent's EPSG:4326 point, for a layer beside
#   every other dataset.
# * ``v_fmi_lightning_4258`` — the point as published, in ETRS89.
# * ``v_fmi_lightning_3067`` — ETRS89 / TM35FIN(E,N), Finland's national grid.
#
# The first two select their geometry straight from its table. The third has no
# column to select — the 3067 point is not stored — so it reprojects the ETRS89
# point and **casts the result back** to ``geometry(Point,3067)``, which keeps the
# type modifier QGIS reads type and SRID from. Revision fe72ef3ef7c8 created
# ``idx_fmi_lightning_geometry_3067`` on exactly the same expression, which the
# planner matches; changing the expression here means changing that index.
#
# There is no ``date_time_local``: FMI publishes UTC, so the published reading *is*
# ``date_time``.
#
# The stroke's own columns. ``f`` is ``fmi_lightning``, ``l`` ``lightning``,
# ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_COLUMNS = """
    l.id AS id,
    l.date_time AS date_time,
    l.peak_current AS peak_current,
    l.cloud_to_ground AS cloud_to_ground,
    f.flash_id AS flash_id,
    f.multiplicity AS multiplicity,
    f.stroke_index AS stroke_index,
    f.published_multiplicity AS published_multiplicity,
    f.number_of_sensors AS number_of_sensors,
    f.degrees_of_freedom AS degrees_of_freedom,
    f.chi_squared AS chi_squared,
    f.ellipse_major_axis AS ellipse_major_axis,
    f.ellipse_minor_axis AS ellipse_minor_axis,
    f.ellipse_angle AS ellipse_angle,
    f.rise_time AS rise_time,
    f.peak_to_zero_time AS peak_to_zero_time,
    f.stroke_status AS stroke_status,
    f.angle_indicator AS angle_indicator,
    f.signal_indicator AS signal_indicator,
    f.timing_indicator AS timing_indicator,
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
JOIN lightning l ON l.id = f.id
LEFT JOIN data_provider dp ON dp.id = l.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = l.admin_boundary_id"""

#: The reprojection the 3067 view selects: the expression
#: ``idx_fmi_lightning_geometry_3067`` is built on.
_GEOMETRY_3067 = "(st_transform(f.geometry_etrs89, 3067)::geometry(Point,3067))"


def _view(name: str, geometry: str) -> ReplaceableObject:
    return ReplaceableObject(
        name,
        f"""
SELECT{_COLUMNS},
    {geometry} AS geometry
FROM fmi_lightning f{_JOINS}
""",
    )


fmi_lightning_4326_view = _view("v_fmi_lightning_4326", "l.geometry")
fmi_lightning_4258_view = _view("v_fmi_lightning_4258", "f.geometry_etrs89")
fmi_lightning_3067_view = _view("v_fmi_lightning_3067", _GEOMETRY_3067)

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    fmi_lightning_4326_view,
    fmi_lightning_4258_view,
    fmi_lightning_3067_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the three FMI lightning views. Like every dataset view they add no
    storage and no constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
