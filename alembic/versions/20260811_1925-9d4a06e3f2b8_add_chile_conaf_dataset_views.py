"""add chile conaf dataset views

Revision ID: 9d4a06e3f2b8
Revises: 268b915dce92
Create Date: 2026-08-11 19:25:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '9d4a06e3f2b8'
down_revision: str | None = '268b915dce92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Seven views, following the four rules set out in revision e4b7c1a90f3d: ``id``
# first and an integer, the geometry selected straight from its table so its type
# modifier survives, one geometry per view, and a ``*_local`` companion for every
# datetime.
#
# Seven rather than the usual two or four, because Chile is the first provider whose
# published data is on **two** projected grids. ICNF, DARPA, REDIAM and NBAC each get
# a 4326 view and one grid view; CONAF gets a 4326 view and *two* grid views for each
# of its two spatial tables, because the mainland is EPSG:32719 and Easter Island is
# EPSG:32712 and no single view can carry both — a view has one geometry column, and
# a geometry column has one SRID.
#
# The two grid views of a pair are therefore not alternative renderings of the same
# rows: ``v_conaf_ignition_32719`` shows the 95,625 mainland fires and
# ``v_conaf_ignition_32712`` the 243 Rapa Nui ones, and between them they show every
# row exactly once. The ``_4326`` view of each pair is the one that shows all of
# them, and it is the one a cross-provider layer should use.
#
# Both grid views name their column the same as the 4326 one — ``geometry`` for a
# point, ``perimeter`` for a polygon — so a QGIS style written for one loads on the
# others.
#
# ``v_conaf_wildfire`` is a POINT on a wildfire view, the fifth after
# ``v_egif_wildfire``, ``v_greece_ffa_wildfire``, ``v_nfdb_wildfire`` and
# ``v_inab_wildfire``: the seasonal archive publishes a location, not a shape. It
# INNER JOINs its ignition — the Greek shape rather than the Canadian — because
# ``conaf_wildfire.ignition_id`` is NOT NULL, so the join drops nothing and a LEFT
# JOIN would only suggest to a reader that it might.
#
# It gets no ``_32719``/``_32712`` pair of its own. The report's own grid geometry is
# on its ignition, which already has both views, and a third pair would be six views
# of 95,868 rows differing only in which columns come along for the ride.

# The generic wildfire columns and the lookups behind their foreign keys, shared by
# every wildfire view here. ``w`` is ``wildfire``, ``dp`` ``data_provider``, ``ab``
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

# The cause classification, resolved through the foreign key. Shared by the report
# and perimeter views.
#
# ``cause_normalised`` and ``cause_en`` are here and ``cause_code`` is here beside
# ``cause_scheme``, never without it: the code was reused when CONAF renumbered the
# taxonomy in 2023-2024, and a QGIS user categorising a layer by ``cause_code`` alone
# would merge *incendios de causa desconocida* with *faenas forestales*. Putting the
# scheme in the next column along is the most this layer can do about that.
_CAUSE_COLUMNS = """
    fc.cause AS cause,
    fc.cause_code AS cause_code,
    fc.cause_normalised AS cause_normalised,
    fc.cause_en AS cause_en,
    fc.specific_cause AS specific_cause,
    fc.specific_cause_code AS specific_cause_code,
    fc.scheme AS cause_scheme"""

# The report row's own columns. ``f`` is ``conaf_wildfire``.
_REPORT_COLUMNS = f"""
    f.season AS season,
    f.season_start_year AS season_start_year,
    f.number AS number,
    f.name AS name,
    f.reporter AS reporter,
    f.region AS region,
    f.province AS province,
    f.commune AS commune,
    f.region_code AS region_code,
    f.province_code AS province_code,
    f.commune_code AS commune_code,
    f.start_place AS start_place,
    f.fuel AS fuel,
    f.date_time_precision AS date_time_precision,
    f.area_ha_pine_0_10 AS area_ha_pine_0_10,
    f.area_ha_pine_11_17 AS area_ha_pine_11_17,
    f.area_ha_pine_18_plus AS area_ha_pine_18_plus,
    f.area_ha_eucalyptus AS area_ha_eucalyptus,
    f.area_ha_other_plantation AS area_ha_other_plantation,
    f.area_ha_plantation AS area_ha_plantation,
    f.area_ha_native_forest AS area_ha_native_forest,
    f.area_ha_scrub AS area_ha_scrub,
    f.area_ha_grassland AS area_ha_grassland,
    f.area_ha_vegetation AS area_ha_vegetation,
    f.area_ha_agricultural AS area_ha_agricultural,
    f.area_ha_debris AS area_ha_debris,
    f.area_ha_other AS area_ha_other,
    f.area_ha_total AS area_ha_total,
    f.area_totals_agree AS area_totals_agree,
    f.cause_id AS cause_id,{_CAUSE_COLUMNS},
    f.ignition_id AS ignition_id"""

_REPORT_JOINS = """
JOIN wildfire w ON w.id = f.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN conaf_fire_cause fc ON fc.id = f.cause_id
JOIN conaf_ignition g ON g.id = f.ignition_id
JOIN ignition i ON i.id = g.id"""


conaf_wildfire_view = ReplaceableObject(
    "v_conaf_wildfire",
    f"""
SELECT
    w.id AS id,{_REPORT_COLUMNS},{_WILDFIRE_COLUMNS},
    g.utm_easting AS utm_easting,
    g.utm_northing AS utm_northing,
    g.utm_zone AS utm_zone,
    g.utm_band AS utm_band,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM conaf_wildfire f{_REPORT_JOINS}
""",
)


# The generic ignition columns, for the three ignition views. ``i`` is ``ignition``.
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

# The ignition row's own columns, plus the report's name and precision resolved back
# through ``conaf_wildfire.ignition_id``.
#
# The join is the reverse of the usual direction — the fire points at the point, so
# finding the fire from the point means joining on ``ignition_id`` — and it is a LEFT
# JOIN because an ignition is written before its report inside the same statement,
# and because nothing in the schema promises every point has one.
_CONAF_IGNITION_COLUMNS = """
    g.season_start_year AS season_start_year,
    g.number AS number,
    g.region_code AS region_code,
    g.utm_easting AS utm_easting,
    g.utm_northing AS utm_northing,
    g.utm_zone AS utm_zone,
    g.utm_band AS utm_band,
    f.id AS conaf_wildfire_id,
    f.season AS season,
    f.name AS name,
    f.reporter AS reporter,
    f.area_ha_total AS area_ha_total,
    f.date_time_precision AS date_time_precision"""

_CONAF_IGNITION_JOINS = """
JOIN ignition i ON i.id = g.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id
LEFT JOIN conaf_wildfire f ON f.ignition_id = g.id"""


conaf_ignition_4326_view = ReplaceableObject(
    "v_conaf_ignition_4326",
    f"""
SELECT
    i.id AS id,{_CONAF_IGNITION_COLUMNS},{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM conaf_ignition g{_CONAF_IGNITION_JOINS}
""",
)


# Mainland only: ``geometry_utm19s`` is NULL on the Rapa Nui rows, and a NULL
# geometry in QGIS is a feature that does not draw. The ``WHERE`` makes the view a
# clean 95,625-row layer instead of one with 243 invisible rows in it, and it is
# safe to add here in a way it would not be on the 4326 view — this view exists
# *because* of the grid, so rows that are not on the grid do not belong in it.
conaf_ignition_32719_view = ReplaceableObject(
    "v_conaf_ignition_32719",
    f"""
SELECT
    i.id AS id,{_CONAF_IGNITION_COLUMNS},{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    g.geometry_utm19s AS geometry
FROM conaf_ignition g{_CONAF_IGNITION_JOINS}
WHERE g.geometry_utm19s IS NOT NULL
""",
)


conaf_ignition_32712_view = ReplaceableObject(
    "v_conaf_ignition_32712",
    f"""
SELECT
    i.id AS id,{_CONAF_IGNITION_COLUMNS},{_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    g.geometry_utm12s AS geometry
FROM conaf_ignition g{_CONAF_IGNITION_JOINS}
WHERE g.geometry_utm12s IS NOT NULL
""",
)


# The perimeter row's own columns. ``m`` is ``conaf_magnitud_wildfire``.
#
# ``report_number`` and ``report_name`` are resolved through ``conaf_wildfire_id``
# and are NULL on every row until the binder has run — here for the same reason the
# Catalan, Andalusian and NBAC views carry theirs: the layer that will show whether
# the binding worked should not need a migration first.
#
# ``report_area_ha_total`` is beside ``area_ha_mapped`` on purpose. The two are
# different measurements of the same fire — one traced from a polygon, one filed by
# an office — and putting them in adjacent columns is the cheapest way to let someone
# looking at the map see how far apart they are.
_MAGNITUD_COLUMNS = f"""
    m.season AS season,
    m.season_start_year AS season_start_year,
    m.number AS number,
    m.name AS name,
    m.region AS region,
    m.province AS province,
    m.commune AS commune,
    m.region_code AS region_code,
    m.province_code AS province_code,
    m.commune_code AS commune_code,
    m.cause_published AS cause_published,
    m.cause_id AS cause_id,{_CAUSE_COLUMNS},
    m.area_ha_mapped AS area_ha_mapped,
    m.area_ha_published AS area_ha_published,
    m.part_count AS part_count,
    m.date_time_precision AS date_time_precision,
    m.conaf_wildfire_id AS conaf_wildfire_id,
    r.number AS report_number,
    r.name AS report_name,
    r.area_ha_total AS report_area_ha_total,
    m.match_method AS match_method,
    m.match_confidence AS match_confidence,
    m.matched_at AS matched_at"""

_MAGNITUD_JOINS = """
JOIN wildfire w ON w.id = m.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN conaf_fire_cause fc ON fc.id = m.cause_id
LEFT JOIN conaf_wildfire r ON r.id = m.conaf_wildfire_id"""


conaf_magnitud_wildfire_4326_view = ReplaceableObject(
    "v_conaf_magnitud_wildfire_4326",
    f"""
SELECT
    w.id AS id,{_MAGNITUD_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM conaf_magnitud_wildfire m{_MAGNITUD_JOINS}
""",
)


conaf_magnitud_wildfire_32719_view = ReplaceableObject(
    "v_conaf_magnitud_wildfire_32719",
    f"""
SELECT
    w.id AS id,{_MAGNITUD_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    m.perimeter_utm19s AS perimeter
FROM conaf_magnitud_wildfire m{_MAGNITUD_JOINS}
WHERE m.perimeter_utm19s IS NOT NULL
""",
)


conaf_magnitud_wildfire_32712_view = ReplaceableObject(
    "v_conaf_magnitud_wildfire_32712",
    f"""
SELECT
    w.id AS id,{_MAGNITUD_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    m.perimeter_utm12s AS perimeter
FROM conaf_magnitud_wildfire m{_MAGNITUD_JOINS}
WHERE m.perimeter_utm12s IS NOT NULL
""",
)


#: Every view this revision creates, in creation order; ``downgrade()`` walks it
#: backwards. There is no dependency between them.
VIEWS = [
    conaf_wildfire_view,
    conaf_ignition_4326_view,
    conaf_ignition_32719_view,
    conaf_ignition_32712_view,
    conaf_magnitud_wildfire_4326_view,
    conaf_magnitud_wildfire_32719_view,
    conaf_magnitud_wildfire_32712_view,
]


def upgrade() -> None:
    """Apply this revision.

    Creates the seven Chilean views. Like the views of revision e4b7c1a90f3d they
    add no storage and no constraints, so dropping and recreating them costs nothing
    but the ``CREATE`` statements.

    They do, however, block ``ALTER COLUMN ... TYPE`` on every column they select —
    which here is most of ``conaf_wildfire``, ``conaf_ignition``,
    ``conaf_magnitud_wildfire`` and ``conaf_fire_cause``. A later revision changing
    one of those types has to drop the views first and recreate them at the end. See
    ``src/data_model/replaceable.py``.
    """
    for view in VIEWS:
        op.create_view(view)


def downgrade() -> None:
    """Revert this revision."""
    for view in reversed(VIEWS):
        op.drop_view(view)
