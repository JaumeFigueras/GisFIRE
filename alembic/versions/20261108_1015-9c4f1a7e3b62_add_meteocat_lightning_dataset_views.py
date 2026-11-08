"""add meteocat lightning dataset views

Revision ID: 9c4f1a7e3b62
Revises: 5b7e2c9d4a13
Create Date: 2026-11-08 10:15:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '9c4f1a7e3b62'
down_revision: str | None = '5b7e2c9d4a13'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Three views of the same strokes, one per CRS, following the rules of revision
# e4b7c1a90f3d: ``id`` first and an integer, one geometry per view, all named
# ``geometry`` so a style written for one loads on the others.
#
# * ``v_meteocat_lightning_4326`` — the parent's EPSG:4326 point, for a layer beside
#   every other dataset.
# * ``v_meteocat_lightning_4258`` — the point as published, in ETRS89.
# * ``v_meteocat_lightning_25831`` — ETRS89 / UTM 31N, the grid Catalonia measures
#   and draws on.
#
# The first two select their geometry straight from its table. The third has no
# column to select — the 25831 point is not stored — so it reprojects the ETRS89
# point and **casts the result back** to ``geometry(Point,25831)``: without the cast
# the type modifier is lost and QGIS can no longer detect type and SRID. A
# reprojection in a view would also defeat the spatial index, and with six million
# strokes every pan in QGIS would be a sequential scan, so revision 5b7e2c9d4a13
# created ``idx_meteocat_lightning_geometry_25831`` on exactly the same expression,
# which the planner matches. Changing the expression here means changing that index.
#
# There is no ``date_time_local``. The ``*_local`` companions recover the reading a
# provider published in local time; the XDDE publishes UTC, so the published reading
# *is* ``date_time``.
#
# The stroke's own columns. ``m`` is ``meteocat_lightning``, ``l`` ``lightning``,
# ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
_COLUMNS = """
    l.id AS id,
    l.date_time AS date_time,
    l.peak_current AS peak_current,
    l.cloud_to_ground AS cloud_to_ground,
    m.network_version AS network_version,
    m.flash_id AS flash_id,
    m.multiplicity AS multiplicity,
    m.stroke_index AS stroke_index,
    m.chi_squared AS chi_squared,
    m.ellipse_major_axis AS ellipse_major_axis,
    m.ellipse_minor_axis AS ellipse_minor_axis,
    m.ellipse_angle AS ellipse_angle,
    m.number_of_sensors AS number_of_sensors,
    m.municipality_code AS municipality_code,
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
JOIN lightning l ON l.id = m.id
LEFT JOIN data_provider dp ON dp.id = l.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = l.admin_boundary_id"""

#: The reprojection the 25831 view selects: the expression
#: ``idx_meteocat_lightning_geometry_25831`` is built on.
_GEOMETRY_25831 = "(st_transform(m.geometry_etrs89, 25831)::geometry(Point,25831))"


def _view(name: str, geometry: str) -> ReplaceableObject:
    return ReplaceableObject(
        name,
        f"""
SELECT{_COLUMNS},
    {geometry} AS geometry
FROM meteocat_lightning m{_JOINS}
""",
    )


meteocat_lightning_4326_view = _view("v_meteocat_lightning_4326", "l.geometry")
meteocat_lightning_4258_view = _view("v_meteocat_lightning_4258", "m.geometry_etrs89")
meteocat_lightning_25831_view = _view("v_meteocat_lightning_25831", _GEOMETRY_25831)

#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    meteocat_lightning_4326_view,
    meteocat_lightning_4258_view,
    meteocat_lightning_25831_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the three MeteoCat lightning views. Like every dataset view they add no
    storage and no constraints.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
