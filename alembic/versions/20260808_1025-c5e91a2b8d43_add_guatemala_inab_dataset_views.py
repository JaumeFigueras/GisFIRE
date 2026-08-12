"""add guatemala inab dataset views

Revision ID: c5e91a2b8d43
Revises: 8b3d47f0c621
Create Date: 2026-08-08 10:25:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'c5e91a2b8d43'
down_revision: str | None = '8b3d47f0c621'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Two views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# ``v_inab_wildfire`` exposes a POINT, the fourth wildfire view to do so after
# ``v_egif_wildfire``, ``v_greece_ffa_wildfire`` and ``v_nfdb_wildfire``, and for
# the same reason: INAB publishes no perimeter, so the useful QGIS layer is the
# report's attributes mapped where it was reported.
#
# It LEFT JOINs its ignition, as the NFDB one does and unlike the Greek one. The
# Greek inner join hides four fires in five, which is a property of that archive;
# here every published record has a point, so the join hides nothing today and a
# future record without one should be a feature that does not draw rather than a
# row that vanishes.
#
# Note what is *not* here: no burnt area, in either view. INAB publishes none —
# see revision 8b3d47f0c621 — so a QGIS user styling this layer by fire size has
# nothing to style by, and that is the dataset rather than the view.

# The generic wildfire columns and the lookups behind their foreign keys. ``w`` is
# ``wildfire``, ``dp`` ``data_provider``, ``ab`` ``admin_boundary``.
#
# ``end_date_time`` is carried through and is NULL on every row: the times a fire
# was controlled and extinguished are in the ``informes`` layer, which is not
# modelled. The column is here so the view has the shape of every other wildfire
# view, and so that adding that layer later needs no migration to this.
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

# The generic ignition columns. ``i`` is ``ignition``, ``dpi``/``abi`` its lookups.
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

_IGNITION_JOINS = """
JOIN ignition i ON i.id = g.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id"""


inab_ignition_view = ReplaceableObject(
    "v_inab_ignition",
    f"""
SELECT
    i.id AS id,
    g.global_id AS global_id,
    g.reported_x AS reported_x,
    g.reported_y AS reported_y,
    g.reported_crs AS reported_crs,
    g.utm_zone AS utm_zone,
    g.altitude_m AS altitude_m,{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM inab_ignition g{_IGNITION_JOINS}
""",
)


# ``report_status`` is first among the INAB columns on purpose. It is the column a
# QGIS user has to filter on before the layer means anything — 140 of these
# records say there was no fire — and a column near the left of the attribute
# table is one that gets noticed.
inab_wildfire_view = ReplaceableObject(
    "v_inab_wildfire",
    f"""
SELECT
    w.id AS id,
    n.global_id AS global_id,
    n.report_status AS report_status,
    n.object_id AS object_id,
    n.source_id AS source_id,
    n.report_channel AS report_channel,
    n.institution AS institution,
    n.institution_other AS institution_other,
    n.fire_location AS fire_location,
    n.department_name AS department_name,
    n.municipality_name AS municipality_name,
    n.municipality_code AS municipality_code,
    lpad(n.municipality_code::text, 4, '0') AS municipality_code_ine,
    n.locality_name AS locality_name,
    n.estate_name AS estate_name,
    n.inab_region AS inab_region,
    n.inab_subregion AS inab_subregion,
    n.protected_area_name AS protected_area_name,
    n.protected_area_name_secondary AS protected_area_name_secondary,
    n.published_at AS published_at,
    n.edited_at AS edited_at,{_WILDFIRE_COLUMNS},
    n.ignition_id AS ignition_id,
    g.altitude_m AS altitude_m,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM inab_wildfire n
JOIN wildfire w ON w.id = n.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN inab_ignition g ON g.id = n.ignition_id
LEFT JOIN ignition i ON i.id = g.id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    inab_ignition_view,
    inab_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the two Guatemalan views. Like the views of revision e4b7c1a90f3d they
    add no storage and no constraints, so dropping and recreating them costs
    nothing but the ``CREATE`` statements.

    ``v_inab_wildfire`` carries one derived column the table does not have:
    ``municipality_code_ine``, the code zero-padded to the four characters INE
    publishes. The integer column is what the slug carries; this is what a join to
    a Guatemalan boundary layer needs, because those publish the code as text and
    ``114`` will not match ``'0114'``. Derived in the view rather than stored,
    being a rendering of a column that is already there.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
