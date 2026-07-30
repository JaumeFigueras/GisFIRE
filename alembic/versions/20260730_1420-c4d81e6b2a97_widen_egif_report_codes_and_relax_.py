"""widen egif report codes and relax egif coordinate constraints

Revision ID: c4d81e6b2a97
Revises: 9a3d61c07e84
Create Date: 2026-07-30 14:20:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = 'c4d81e6b2a97'
down_revision: str | None = '9a3d61c07e84'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# Both EGIF views are replaced, for two reasons.
#
# ``datum_code`` is new on ``egif_ignition`` and both views expose every column of
# that table, so both gain it.
#
# ``v_egif_wildfire`` additionally has to stop inner-joining the ignition. It was
# written when ``egif_wildfire.ignition_id`` was ``NOT NULL``; now that a fire may
# have no published coordinate, an inner join would silently drop 9% of the
# 2004-2023 archive from the layer — the worst kind of wrong, because the view
# would still look healthy. The join becomes a LEFT JOIN and those fires arrive
# with a NULL geometry, which QGIS shows as a feature with no location rather than
# as no feature.
#
# The geometry is still selected straight from ``ignition`` with nothing wrapped
# round it, so its type modifier survives the LEFT JOIN and the view stays
# registered in ``geometry_columns`` as POINT/4326. That is checked by
# ``test_the_dataset_views_register_their_geometry``.

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

_EGIF_IGNITION_COLUMNS = """
    n.utm_zone AS utm_zone,
    n.utm_x AS utm_x,
    n.utm_y AS utm_y,
    n.datum AS datum,
    n.datum_code AS datum_code,
    n.start_point_count AS start_point_count,
    n.mtn_sheet AS mtn_sheet,
    n.mtn_grid AS mtn_grid,
    n.place_name AS place_name"""

_IGNITION_JOINS = """
JOIN ignition i ON i.id = n.id
LEFT JOIN data_provider dpi ON dpi.id = i.data_provider_id
LEFT JOIN admin_boundary abi ON abi.id = i.admin_boundary_id"""


egif_ignition_view = ReplaceableObject(
    "v_egif_ignition",
    f"""
SELECT
    i.id AS id,
    n.report_number AS report_number,{_IGNITION_COLUMNS},{_EGIF_IGNITION_COLUMNS},
    i.created_at AS created_at,
    i.updated_at AS updated_at,
    i.geometry AS geometry
FROM egif_ignition n{_IGNITION_JOINS}
""",
)


egif_wildfire_view = ReplaceableObject(
    "v_egif_wildfire",
    """
SELECT
    w.id AS id,
    s.report_number AS report_number,
    s.egif_id AS egif_id,
    s.campaign AS campaign,
    s.status AS status,
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
    s.ccaa_name AS ccaa_name,
    s.province_name AS province_name,
    s.province_ine_code AS province_ine_code,
    s.municipality_name AS municipality_name,
    s.municipality_ine_code AS municipality_ine_code,
    s.comarca_name AS comarca_name,
    s.minor_entity_name AS minor_entity_name,
    s.affected_municipality_count AS affected_municipality_count,
    s.cause_id AS cause_id,
    c.code AS cause_code,
    c.label AS cause_label,
    c.label_en AS cause_label_en,
    s.motivation_id AS motivation_id,
    m.code AS motivation_code,
    m.label AS motivation_label,
    m.label_en AS motivation_label_en,
    s.area_ha_wooded AS area_ha_wooded,
    s.area_ha_non_wooded AS area_ha_non_wooded,
    s.area_ha_forest_total AS area_ha_forest_total,
    s.area_ha_agricultural AS area_ha_agricultural,
    s.area_ha_other_non_forest AS area_ha_other_non_forest,
    s.wui_affected AS wui_affected,
    s.wui_compact AS wui_compact,
    s.wui_scattered AS wui_scattered,
    s.wui_isolated AS wui_isolated,
    s.protected_space_affected AS protected_space_affected,
    s.agricultural_land_affected AS agricultural_land_affected,
    s.zar_affected AS zar_affected,
    s.pss_report_number AS pss_report_number,
    s.ignition_id AS ignition_id,
    n.utm_zone AS utm_zone,
    n.utm_x AS utm_x,
    n.utm_y AS utm_y,
    n.datum AS datum,
    n.datum_code AS datum_code,
    n.start_point_count AS start_point_count,
    n.mtn_sheet AS mtn_sheet,
    n.mtn_grid AS mtn_grid,
    n.place_name AS place_name,
    (r.id IS NOT NULL) AS has_full_report,
    r.days_since_storm AS days_since_storm,
    r.fuel_model_codes AS fuel_model_codes,
    r.fire_type_codes AS fire_type_codes,
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    i.geometry AS geometry
FROM egif_wildfire s
JOIN wildfire w ON w.id = s.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id
LEFT JOIN egif_fire_cause c ON c.id = s.cause_id
LEFT JOIN egif_fire_motivation m ON m.id = s.motivation_id
LEFT JOIN egif_ignition n ON n.id = s.ignition_id
LEFT JOIN ignition i ON i.id = n.id
LEFT JOIN egif_wildfire_report r ON r.id = s.id
""",
)


#: Every view this revision redefines, paired with the revision that last defined
#: it. ``downgrade()`` walks it backwards, putting the older definition back.
VIEWS = [
    (egif_ignition_view, "9a3d61c07e84.egif_ignition_view"),
    (egif_wildfire_view, "9a3d61c07e84.egif_wildfire_view"),
]


def upgrade() -> None:
    """Apply this revision.

    Four columns added, three constraints relaxed, two views replaced. All of it
    comes from checking the model — written against one 98-fire province-year
    sample and the 2022-2023 Excel export — against the seven XML exports that
    cover 2004-2023, 248,257 fires.

    The four new columns
    --------------------

    ``egif_wildfire_report`` gains ``fuel_model_codes``, ``fire_type_codes``,
    ``start_area_type_codes`` and ``started_next_to_codes``, the four multi-valued
    code lists of the report that carry a code and nothing else.

    They are ``text[]`` rather than four child tables because each really is a
    *set*: across the 29,926 fires of the 2020-2023 export no fire ever repeats a
    code within any of the four, so an array loses nothing and saves four joins.
    The first two are the ones worth having — the fuel model is the only record of
    what was burning, and ``fire_type_codes`` containing ``'3'`` (*de subsuelo*) is
    the smouldering ground fire that makes a holdover interval physically
    plausible. Both are populated on every lightning fire in the archive.

    ``egif_ignition`` gains ``datum_code``, the raw ``iddatum``. Three values occur
    and only two can be resolved, so the unmappable ``3`` — three records in the
    whole archive — keeps its code beside a NULL ``datum`` instead of being rounded
    to ETRS89.

    The three relaxations
    ---------------------

    ``egif_wildfire.ignition_id`` becomes nullable. **22,855 fires of the 248,257
    in the archive publish no coordinate at all** — 8,872 in 2004-2005, none from
    2017 on. They are real *partes* of real fires that nobody located, and the
    previous NOT NULL would have made the historical series unimportable.

    ``egif_ignition.datum`` becomes nullable. ``iddatum`` does not exist in the XML
    before the 2014-2016 campaigns: 2004-2013 publish coordinates with no datum
    whatsoever. The CHECK stays — a NULL satisfies ``datum IN (...)`` in SQL — so
    an unknown *label* is still refused while an absent one is allowed.

    ``ck_egif_ignition_utm_zone`` is dropped outright. It was there to turn a
    transcription error into a failed insert, on the reading that ``huso 3`` on
    fire ``2022470051`` was a typo for 30. It is not a transcription error: seven
    fires across 2004-2023 carry a zone outside 28-31 (``3``, ``27``, ``32``,
    ``33``, ``39``, ``50``, ``63``, ``71``), and the service's own ``latitud`` and
    ``longitud`` are computed *from* the bad zone — fire ``2011331154`` is
    published at longitude -117.24, in the Pacific. So the published geographic
    coordinate is derived rather than independent, it cannot be used to check the
    projected one, and the constraint's only effect would be to reject genuine
    published records. The zone is kept as published and the importer derives the
    zone it reprojects from, which the province settles in all seven cases.
    """
    op.add_column('egif_ignition', sa.Column('datum_code', sa.String(), nullable=True))
    op.alter_column('egif_ignition', 'datum', existing_type=sa.VARCHAR(), nullable=True)
    op.drop_constraint('ck_egif_ignition_utm_zone', 'egif_ignition', type_='check')
    op.alter_column('egif_wildfire', 'ignition_id', existing_type=sa.INTEGER(),
                    nullable=True)
    op.add_column('egif_wildfire_report',
                  sa.Column('fuel_model_codes', postgresql.ARRAY(sa.String()),
                            nullable=True))
    op.add_column('egif_wildfire_report',
                  sa.Column('fire_type_codes', postgresql.ARRAY(sa.String()),
                            nullable=True))
    op.add_column('egif_wildfire_report',
                  sa.Column('start_area_type_codes', postgresql.ARRAY(sa.String()),
                            nullable=True))
    op.add_column('egif_wildfire_report',
                  sa.Column('started_next_to_codes', postgresql.ARRAY(sa.String()),
                            nullable=True))
    # After the columns exist: both new definitions select ``datum_code``.
    for view, previous in VIEWS:
        op.replace_view(view, replaces=previous)


def downgrade() -> None:
    """Revert this revision.

    The views go back first, because the definitions of revision 9a3d61c07e84 do
    not select the columns this one is about to drop. Restoring ``NOT NULL`` on
    ``ignition_id`` and ``datum`` will fail if any row has since been imported
    without one, which is correct: there is no way back that keeps the data.
    """
    for view, previous in reversed(VIEWS):
        op.replace_view(view, replace_with=previous)
    op.drop_column('egif_wildfire_report', 'started_next_to_codes')
    op.drop_column('egif_wildfire_report', 'start_area_type_codes')
    op.drop_column('egif_wildfire_report', 'fire_type_codes')
    op.drop_column('egif_wildfire_report', 'fuel_model_codes')
    op.alter_column('egif_wildfire', 'ignition_id', existing_type=sa.INTEGER(),
                    nullable=False)
    op.create_check_constraint('ck_egif_ignition_utm_zone', 'egif_ignition',
                               'utm_zone IN (28, 29, 30, 31)')
    op.alter_column('egif_ignition', 'datum', existing_type=sa.VARCHAR(),
                    nullable=False)
    op.drop_column('egif_ignition', 'datum_code')
