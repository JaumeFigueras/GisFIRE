"""add canada dataset views

Revision ID: a4e8c2b7d951
Revises: cb6f71e0e868
Create Date: 2026-08-04 20:20:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'a4e8c2b7d951'
down_revision: str | None = 'cb6f71e0e868'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Four views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# NBAC gets two, one per CRS, exactly as ICNF, DARPA and REDIAM do: EPSG:4326 for a
# layer that sits beside every other country's, and EPSG:3978 for anything measured
# or drawn on the grid the service publishes on. Both name the column ``perimeter``
# so a style written for one loads on the other.
#
# NFDB gets two of a different shape: an ignition view, and a wildfire view whose
# geometry is a POINT — the third such after ``v_egif_wildfire`` and
# ``v_greece_ffa_wildfire``, and for the same reason. The agencies publish no
# perimeter, so the useful QGIS layer is the report's attributes mapped where it was
# filed.
#
# Unlike the Greek one, ``v_nfdb_wildfire`` LEFT JOINs its ignition rather than
# INNER JOINing it. The Greek inner join hides four fires in five, which is a
# property of that archive; here the coordinate is the point of the dataset and only
# a handful of rows lack one, so dropping them would hide a defect rather than a
# structural absence. A NULL geometry in QGIS is a feature that does not draw, which
# is the correct depiction of a fire report with no usable location.

# The generic wildfire columns and the lookups behind their foreign keys, shared by
# the NBAC views. ``w`` is ``wildfire``, ``dp`` ``data_provider``, ``ab``
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

# The NBAC row's own columns, likewise shared. ``n`` is ``nbac_wildfire``.
#
# ``nfdb_fire_id`` is resolved through the link and is NULL on every row today,
# nothing filling that link in yet — it is here for the same reason the Catalan and
# Andalusian views carry ``egif_report_number``: the layer that will show whether the
# binding worked should not need a migration first.
_NBAC_COLUMNS = """
    n.gid AS gid,
    n.nfireid AS nfireid,
    n.year AS year,
    n.part_count AS part_count,
    n.crosses_admin AS crosses_admin,
    n.admin_name AS admin_name,
    n.admin_div AS admin_div,
    n.fire_cause AS fire_cause,
    n.ba_source AS ba_source,
    n.detection_source AS detection_source,
    n.mapping_method AS mapping_method,
    n.hotspot_start_date AS hotspot_start_date,
    n.hotspot_end_date AS hotspot_end_date,
    n.agency_start_date AS agency_start_date,
    n.agency_end_date AS agency_end_date,
    n.capture_date AS capture_date,
    n.date_source AS date_source,
    n.date_time_precision AS date_time_precision,
    n.area_ha_polygon AS area_ha_polygon,
    n.area_ha_adjusted AS area_ha_adjusted,
    n.area_adjusted AS area_adjusted,
    n.prescribed AS prescribed,
    n.version AS version,
    n.nfdb_wildfire_id AS nfdb_wildfire_id,
    f.nfdb_fire_id AS nfdb_fire_id,
    n.match_method AS match_method,
    n.match_confidence AS match_confidence,
    n.matched_at AS matched_at"""

_NBAC_JOINS = """
JOIN wildfire w ON w.id = n.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN nfdb_wildfire f ON f.id = n.nfdb_wildfire_id"""


nbac_wildfire_4326_view = ReplaceableObject(
    "v_nbac_wildfire_4326",
    f"""
SELECT
    w.id AS id,{_NBAC_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM nbac_wildfire n{_NBAC_JOINS}
""",
)


nbac_wildfire_3978_view = ReplaceableObject(
    "v_nbac_wildfire_3978",
    f"""
SELECT
    w.id AS id,{_NBAC_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    n.perimeter_lambert AS perimeter
FROM nbac_wildfire n{_NBAC_JOINS}
""",
)


# The generic ignition columns, for the ignition view. ``i`` is ``ignition``.
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


nfdb_ignition_view = ReplaceableObject(
    "v_nfdb_ignition",
    f"""
SELECT
    i.id AS id,
    g.nfdb_fire_id AS nfdb_fire_id,
    g.year AS year,
    g.src_agency AS src_agency,{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM nfdb_ignition g{_IGNITION_JOINS}
""",
)


# ``CFS_NOTE1``/``CFS_NOTE2`` are carried through: they are the compiler's own
# annotations on why a row is odd, and a user looking at a suspicious point in QGIS
# is exactly the person who needs them.
nfdb_wildfire_view = ReplaceableObject(
    "v_nfdb_wildfire",
    f"""
SELECT
    w.id AS id,
    f.nfdb_fire_id AS nfdb_fire_id,
    f.agency_fire_id AS agency_fire_id,
    f.fire_name AS fire_name,
    f.src_agency AS src_agency,
    f.nat_park AS nat_park,
    f.year AS year,
    f.size_ha AS size_ha,
    f.fire_cause AS fire_cause,
    f.fire_cause_detail AS fire_cause_detail,
    f.fire_type AS fire_type,
    f.response AS response,
    f.protection_zone AS protection_zone,
    f.prescribed AS prescribed,
    f.report_date AS report_date,
    f.attack_date AS attack_date,
    f.out_date AS out_date,
    f.acquisition_date AS acquisition_date,
    f.more_info AS more_info,
    f.cfs_note1 AS cfs_note1,
    f.cfs_note2 AS cfs_note2,{_WILDFIRE_COLUMNS},
    f.ignition_id AS ignition_id,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM nfdb_wildfire f
JOIN wildfire w ON w.id = f.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN nfdb_ignition g ON g.id = f.ignition_id
LEFT JOIN ignition i ON i.id = g.id
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    nbac_wildfire_4326_view,
    nbac_wildfire_3978_view,
    nfdb_ignition_view,
    nfdb_wildfire_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the four Canadian views. Like the views of revision e4b7c1a90f3d they
    add no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
