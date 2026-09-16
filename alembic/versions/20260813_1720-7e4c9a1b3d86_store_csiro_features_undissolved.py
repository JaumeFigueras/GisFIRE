"""store csiro features undissolved

Revision ID: 7e4c9a1b3d86
Revises: 5d8a2f4c6b19
Create Date: 2026-08-13 17:20:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

from src.data_model.replaceable import ReplaceableObject

# revision identifiers, used by Alembic.
revision: str = '7e4c9a1b3d86'
down_revision: str | None = '5d8a2f4c6b19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- View definitions -------------------------------------------------------
#
# The two Australian views of revision 5d8a2f4c6b19, minus the two columns this
# revision drops. Its own copies, as the replaceable-object recipe requires: a
# migration has to stay a faithful snapshot of the schema as it was.

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

_CSIRO_COLUMNS = """
    c.source_layer AS source_layer,
    c.object_id AS object_id,
    c.year AS year,
    c.fire_id AS fire_id,
    c.fire_id_is_sentinel AS fire_id_is_sentinel,
    c.fire_name AS fire_name,
    c.state_published AS state_published,
    c.state_code AS state_code,
    c.agency AS agency,
    c.fire_type_published AS fire_type_published,
    c.fire_type AS fire_type,
    c.cause_published AS cause_published,
    c.cause AS cause,
    c.capture_method_published AS capture_method_published,
    c.capture_method AS capture_method,
    c.ignition_date AS ignition_date,
    c.extinguish_date AS extinguish_date,
    c.capture_date AS capture_date,
    c.date_source AS date_source,
    c.date_time_precision AS date_time_precision,
    c.dates_plausible AS dates_plausible,
    c.area_ha AS area_ha,
    c.perim_km AS perim_km"""

_CSIRO_JOINS = """
JOIN wildfire w ON w.id = c.id
LEFT JOIN data_provider dp ON dp.id = w.data_provider_id
LEFT JOIN admin_boundary ab ON ab.id = w.admin_boundary_id"""


csiro_wildfire_view = ReplaceableObject(
    "v_csiro_wildfire",
    f"""
SELECT
    c.id AS id,{_CSIRO_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM csiro_wildfire c{_CSIRO_JOINS}
""",
)

csiro_bushfire_view = ReplaceableObject(
    "v_csiro_bushfire",
    f"""
SELECT
    c.id AS id,{_CSIRO_COLUMNS},{_WILDFIRE_COLUMNS},
    w.created_at AS created_at,
    w.updated_at AS updated_at,
    w.perimeter AS perimeter
FROM csiro_wildfire c{_CSIRO_JOINS}
WHERE c.fire_type = 'bushfire'
""",
)

#: The views, and the revision each replaces.
VIEWS = (
    (csiro_wildfire_view, "5d8a2f4c6b19.csiro_wildfire_view"),
    (csiro_bushfire_view, "5d8a2f4c6b19.csiro_bushfire_view"),
)


def upgrade() -> None:
    """Apply this revision.

    **The Australian archive is stored one row per published polygon, and the
    dissolve is gone.** Revision ac2b51efcb0f built this table around the opposite
    decision — one row per ``(source_layer, state_code, fire_id, ignition_date)``,
    stated as a partial unique index, with ``part_count`` and ``attributes_agree``
    recording what each merge had joined and what it had thrown away. That decision
    was wrong, and it was wrong in a way the identifiers hide.

    Grouping the national class on those four columns gives 4,078 merged groups.
    **956 of them (23.4%) span more than 10 km**, 645 more than 25 km and 270 more
    than 100 km; the widest joins two Western Australian features **2,403 km apart**
    that both publish ``fire_id`` ``23`` on 2010-11-24. The next widest are the same
    shape — ``21``, ``001``, ``1``, ``4`` — small numbers that Western Australian
    districts reuse, placeholders exactly as ``'999'`` is but without saying so.

    A fire has several fronts; it does not have one on either side of a state. Since
    nothing published tells a reused number from a real one, the table now stores the
    only unit that is certainly true — the published feature — and leaves the
    reassembling of fires to an application that can bring a rule to it. Merging is
    the one thing an import cannot undo, so it is not done here.

    What that costs and what it removes:

    * ``uq_csiro_wildfire_dissolve_key`` is **dropped**. It asserted that those four
      columns identify a fire. They do not, and with the dissolve gone the table
      really does hold several rows per value.
    * ``part_count`` and ``attributes_agree`` are **dropped**. Both existed only to
      describe a merge: one counted the features joined, the other said whether the
      values kept were a choice between disagreeing parts. Without the merge the
      first is 1 on every row and the second true on every row, and a column that
      cannot vary is a column that will be misread.
    * Both views are replaced without those two columns. ``ST_NumGeometries(w.
      perimeter)`` answers the geometric question ``part_count`` was sometimes
      mistaken for — how many polygons this feature's own MultiPolygon has.

    **This revision does not fix data, only the schema.** A database that imported
    with the dissolve keeps its merged rows: dropping two columns cannot take a
    unioned geometry apart again. Those rows are 285,232 merges of 347,834 published
    features, and the only way back is to **re-import**, which the year loop does
    year by year in place — see
    :mod:`src.apps.imports.wildfires.australia_csiro.import_wildfires`.
    """
    for view, previous in VIEWS:
        op.replace_view(view, replaces=previous)

    op.drop_index('uq_csiro_wildfire_dissolve_key', table_name='csiro_wildfire',
                  postgresql_where=sa.text('NOT fire_id_is_sentinel'))
    op.drop_constraint('ck_csiro_wildfire_part_count', 'csiro_wildfire',
                       type_='check')
    op.drop_column('csiro_wildfire', 'attributes_agree')
    op.drop_column('csiro_wildfire', 'part_count')


def downgrade() -> None:
    """Revert this revision.

    .. warning::

       The two columns come back filled with what they would say for undissolved
       rows — ``part_count`` 1 and ``attributes_agree`` true — because that is what
       is true of the data this revision leaves behind. They are **not** recovered
       merges.

       ``uq_csiro_wildfire_dissolve_key`` comes back too, and on a table imported
       without the dissolve **it will fail to build**: several rows really do share
       ``(source_layer, state_code, fire_id, ignition_date)``. That failure is
       correct and is the point of this revision. Empty the table before downgrading
       if the index is what you are after.
    """
    op.add_column('csiro_wildfire',
                  sa.Column('part_count', sa.Integer(), nullable=False,
                            server_default='1'))
    op.add_column('csiro_wildfire',
                  sa.Column('attributes_agree', sa.Boolean(), nullable=False,
                            server_default=sa.true()))
    op.alter_column('csiro_wildfire', 'part_count', server_default=None)
    op.alter_column('csiro_wildfire', 'attributes_agree', server_default=None)
    op.create_check_constraint('ck_csiro_wildfire_part_count', 'csiro_wildfire',
                               'part_count >= 1')
    op.create_index('uq_csiro_wildfire_dissolve_key', 'csiro_wildfire',
                    ['source_layer', 'state_code', 'fire_id', 'ignition_date'],
                    unique=True, postgresql_where=sa.text('NOT fire_id_is_sentinel'))

    for view, previous in reversed(VIEWS):
        op.replace_view(view, replace_with=previous)
