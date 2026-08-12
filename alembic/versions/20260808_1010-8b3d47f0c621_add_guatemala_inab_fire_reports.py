"""add guatemala inab fire reports

Revision ID: 8b3d47f0c621
Revises: 6c2e94ab13d8
Create Date: 2026-08-08 10:10:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8b3d47f0c621'
down_revision: str | None = '6c2e94ab13d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``inab_wildfire`` is Guatemala's *Monitoreo de Incendios Forestales* — 4,615
    fire reports over 2023-2026, one row per call to INAB — and ``inab_ignition``
    is the point each was reported at. Both hang off their generic parent by
    joined table inheritance like every other provider's.

    Five things about this pair are worth reading before changing either.

    **There is no area column, and that is not an omission.** This is the first
    provider in the schema publishing **neither a perimeter nor a burnt area**:
    ``egif_wildfire`` and ``greece_ffa_wildfire`` have no perimeter but do carry
    hectares, five figures and eight respectively. INAB publishes thirty-three
    attributes and not one is a size. ``wildfire.perimeter`` is NULL on every row
    and there is nothing here for a statistics application to measure.

    **``global_id`` is the key, and ``object_id`` is not.** The published
    ``GlobalID`` is a braced UUID, unique across all 4,615 rows, and it survives a
    republication. ``OBJECTID`` does not: the layer is a hosted view, its values
    run 13 to 4,798 with gaps, and they are reassigned when INAB republishes. It
    is stored and indexed so a row can be matched back to a downloaded file, and
    it is deliberately **not** unique.

    ``global_id`` sits on *both* tables rather than only on the fire, so a point
    can be matched to a published record without a join — which is what
    re-importing a revised publication needs.

    **The key identifies a report, not a fire.** 57 pairs of published records
    share an exact coordinate and an exact minute: the same fire called in by two
    institutions, sometimes reaching two different outcomes. The unique constraint
    is therefore correct and a ``count(*)`` on this table is a count of reports.
    Deduplicating is an analysis — the two rows disagree about ``estado_aviso``,
    and choosing between them is a judgement no import should make silently.

    **``report_status`` is indexed because every honest query filters on it.**
    140 of the 4,615 records are ``falso`` — the report was false, there was no
    fire — and 90 more are ``no_verificado``. A count that does not exclude the
    first is 3% too high. It gets no ``CHECK``: five values from one publication
    observed once, and a constraint built from them would reject the first outcome
    INAB adds, exactly as for ``greece_ffa_wildfire.incident_category``.

    **No column holds personal data.** The published layer carries the name and
    telephone number of whoever reported each fire — 1,969 distinct pairs, mostly
    private individuals — plus the INAB accounts that created and edited each
    record. None of the four columns is imported, and none exists here to import
    them into. ``institution`` keeps which *organisation* reported the fire, which
    is the part with analytical meaning. See
    ``src/providers/guatemala_inab.PERSONAL_FIELDS``.

    ``municipality_code`` is indexed and is the **national** INE code, unlike
    ``conafor_wildfire.municipality_code``, which is only a number within its
    state. It is NULL on 22 rows whose published slug carries a truncated code
    naming the wrong department, and on the 4 that carry no attributes at all.
    """
    op.create_table('inab_ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('global_id', sa.String(), nullable=False),
    sa.Column('reported_x', sa.Float(), nullable=True),
    sa.Column('reported_y', sa.Float(), nullable=True),
    sa.Column('reported_crs', sa.String(), nullable=True),
    sa.Column('utm_zone', sa.Integer(), nullable=True),
    sa.Column('altitude_m', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('global_id')
    )
    op.create_index('ix_inab_ignition_reported_crs', 'inab_ignition', ['reported_crs'], unique=False)
    op.create_table('inab_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('global_id', sa.String(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=True),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.Column('report_status', sa.String(), nullable=True),
    sa.Column('report_channel', sa.String(), nullable=True),
    sa.Column('institution', sa.String(), nullable=True),
    sa.Column('institution_other', sa.String(), nullable=True),
    sa.Column('fire_location', sa.String(), nullable=True),
    sa.Column('department_name', sa.String(), nullable=True),
    sa.Column('municipality_name', sa.String(), nullable=True),
    sa.Column('municipality_code', sa.Integer(), nullable=True),
    sa.Column('locality_name', sa.String(), nullable=True),
    sa.Column('estate_name', sa.String(), nullable=True),
    sa.Column('inab_region', sa.String(), nullable=True),
    sa.Column('inab_subregion', sa.String(), nullable=True),
    sa.Column('protected_area_name', sa.String(), nullable=True),
    sa.Column('protected_area_name_secondary', sa.String(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ignition_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.ForeignKeyConstraint(['ignition_id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('global_id')
    )
    op.create_index('ix_inab_wildfire_department_name', 'inab_wildfire', ['department_name'], unique=False)
    op.create_index('ix_inab_wildfire_ignition_id', 'inab_wildfire', ['ignition_id'], unique=False)
    op.create_index('ix_inab_wildfire_municipality_code', 'inab_wildfire', ['municipality_code'], unique=False)
    op.create_index('ix_inab_wildfire_object_id', 'inab_wildfire', ['object_id'], unique=False)
    op.create_index('ix_inab_wildfire_report_status', 'inab_wildfire', ['report_status'], unique=False)


def downgrade() -> None:
    """Revert this revision.

    The fires go before the points: ``inab_wildfire.ignition_id`` references
    ``ignition.id``, so dropping ``inab_ignition`` first would leave a foreign key
    pointing at a parent row whose child table is gone.
    """
    op.drop_index('ix_inab_wildfire_report_status', table_name='inab_wildfire')
    op.drop_index('ix_inab_wildfire_object_id', table_name='inab_wildfire')
    op.drop_index('ix_inab_wildfire_municipality_code', table_name='inab_wildfire')
    op.drop_index('ix_inab_wildfire_ignition_id', table_name='inab_wildfire')
    op.drop_index('ix_inab_wildfire_department_name', table_name='inab_wildfire')
    op.drop_table('inab_wildfire')
    op.drop_index('ix_inab_ignition_reported_crs', table_name='inab_ignition')
    op.drop_table('inab_ignition')
