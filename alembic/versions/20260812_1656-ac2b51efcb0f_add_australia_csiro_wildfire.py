"""add australia csiro wildfire

Revision ID: ac2b51efcb0f
Revises: 2c9f4e7b81a6
Create Date: 2026-08-12 16:56:51.401552+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ac2b51efcb0f'
down_revision: str | None = '2c9f4e7b81a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``csiro_wildfire`` is the Australian historical bushfire cartography — 347,834
    published polygons over 1898-2025, dissolving to 285,232 rows — hanging off its
    generic parent by joined table inheritance like every other provider's. Five
    things about it are worth reading before changing it.

    **Half of what this table holds is not a wildfire.** 166,048 of the published
    features are prescribed burns and 93,960 more are published as ``Unknown``,
    against 85,336 bushfires. All of them are stored, because dropping rows at
    import is irreversible and no rule would honestly assign the unknowns, so
    ``fire_type`` is ``NOT NULL``, constrained to three values and indexed — it is
    the filter every cross-provider count over ``wildfire`` has to apply, and
    ``v_csiro_bushfire`` in the next revision is that filter already applied.

    **There is no natural key, so there are two.** ``(source_layer, object_id)`` is
    ``UNIQUE`` and is the row's identity: the published ``OBJECTID`` of its largest
    part, which no other row can claim because every published feature belongs to
    exactly one stored row. ``fire_id`` is *not* unique and is not a key — 145,694
    Western Australian features publish the sentinel ``'999'``, every Queensland
    feature publishes nothing at all, and 10.5% of the national class is null — so
    it is indexed and left open, as ``gwis_wildfire.gwis_id`` is.

    **The dissolve is stated as a partial unique index.**
    ``uq_csiro_wildfire_dissolve_key`` says that
    ``(source_layer, state_code, fire_id, ignition_date)`` identifies one fire, over
    the rows where ``NOT fire_id_is_sentinel``. All four columns are needed:
    Victoria's fire 541342 is 3,496 features over three ignition dates, fourteen
    national ``(fire_id, ignition_date)`` pairs are shared by New South Wales and
    the ACT, and the two feature classes number their fires independently. The
    partial clause is what keeps the 186,632 sentinel rows out of a constraint they
    would all collide on at once, and
    ``ck_csiro_wildfire_null_fire_id_is_sentinel`` is what stops a NULL ``fire_id``
    slipping into the indexed half.

    **``year`` is not a published attribute.** The geodatabase has no year column;
    this is the year of the resolved start, and it is ``NOT NULL`` and indexed
    because it is the unit the import replaces — the archive is one 860 MB file read
    a year at a time, one transaction each, so a year is what gets deleted and
    rewritten. Nothing else in the table could stand in for it: ``ignition_date`` is
    NULL on the 331 features that publish none, and ``start_date_time`` is a
    timestamptz whose year depends on the zone it is read in.

    **No geometry column is created here**, which makes this the second wildfire
    table in the schema with no spatial index of its own, after
    ``greece_ffa_wildfire`` — but for the opposite reason. Greece publishes no
    polygon; Australia publishes 155.8 million vertices of them, in EPSG:4283, which
    is geographic degrees 1.8 m from the EPSG:4326 that ``wildfire.perimeter``
    already holds and indexes. The Portuguese, Canadian, Catalan and Andalusian
    tables keep a second geometry because theirs is a projected national grid worth
    computing on; a second copy in degrees would cost gigabytes and answer nothing.

    **``date_time_precision`` is constrained to a single value.** Every timestamp in
    both feature classes is at 00:00:00, so ``day`` is the only precision this
    archive has. The column exists anyway so that a query joining it to the
    Portuguese, Canadian or Chilean archives is one query over one column name, and
    the constraint is what will fail loudly if an import ever invents another value
    rather than storing a lie quietly.
    """
    op.create_table('csiro_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('fire_id', sa.String(), nullable=True),
    sa.Column('fire_id_is_sentinel', sa.Boolean(), nullable=False),
    sa.Column('fire_name', sa.String(), nullable=True),
    sa.Column('state_published', sa.String(), nullable=False),
    sa.Column('state_code', sa.String(), nullable=False),
    sa.Column('agency', sa.String(), nullable=True),
    sa.Column('fire_type_published', sa.String(), nullable=True),
    sa.Column('fire_type', sa.String(), nullable=False),
    sa.Column('cause_published', sa.String(), nullable=True),
    sa.Column('cause', sa.String(), nullable=True),
    sa.Column('capture_method_published', sa.String(), nullable=True),
    sa.Column('capture_method', sa.String(), nullable=True),
    sa.Column('ignition_date', sa.Date(), nullable=True),
    sa.Column('extinguish_date', sa.Date(), nullable=True),
    sa.Column('capture_date', sa.Date(), nullable=True),
    sa.Column('date_source', sa.String(), nullable=False),
    sa.Column('date_time_precision', sa.String(), nullable=False),
    sa.Column('dates_plausible', sa.Boolean(), nullable=False),
    sa.Column('area_ha', sa.Float(), nullable=True),
    sa.Column('perim_km', sa.Float(), nullable=True),
    sa.Column('part_count', sa.Integer(), nullable=False),
    sa.Column('attributes_agree', sa.Boolean(), nullable=False),
    sa.CheckConstraint("cause IS NULL OR cause IN ('natural', 'accidental', 'incendiary', 'undetermined')", name='ck_csiro_wildfire_cause'),
    sa.CheckConstraint("date_source IN ('ignition', 'extinguish', 'capture')", name='ck_csiro_wildfire_date_source'),
    sa.CheckConstraint("date_time_precision IN ('day')", name='ck_csiro_wildfire_date_time_precision'),
    sa.CheckConstraint("fire_type IN ('bushfire', 'prescribed_burn', 'unknown')", name='ck_csiro_wildfire_fire_type'),
    sa.CheckConstraint("source_layer IN ('national', 'nt')", name='ck_csiro_wildfire_source_layer'),
    sa.CheckConstraint("state_code IN ('WA', 'VIC', 'NSW', 'QLD', 'TAS', 'SA', 'ACT', 'NT')", name='ck_csiro_wildfire_state_code'),
    sa.CheckConstraint('fire_id IS NOT NULL OR fire_id_is_sentinel', name='ck_csiro_wildfire_null_fire_id_is_sentinel'),
    sa.CheckConstraint('part_count >= 1', name='ck_csiro_wildfire_part_count'),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_layer', 'object_id', name='uq_csiro_wildfire_source_layer_object_id')
    )
    op.create_index('ix_csiro_wildfire_year', 'csiro_wildfire', ['year'], unique=False)
    op.create_index('ix_csiro_wildfire_fire_id', 'csiro_wildfire', ['fire_id'], unique=False)
    op.create_index('ix_csiro_wildfire_fire_type', 'csiro_wildfire', ['fire_type'], unique=False)
    op.create_index('ix_csiro_wildfire_ignition_date', 'csiro_wildfire', ['ignition_date'], unique=False)
    op.create_index('ix_csiro_wildfire_source_layer', 'csiro_wildfire', ['source_layer'], unique=False)
    op.create_index('ix_csiro_wildfire_state_code', 'csiro_wildfire', ['state_code'], unique=False)
    op.create_index('uq_csiro_wildfire_dissolve_key', 'csiro_wildfire', ['source_layer', 'state_code', 'fire_id', 'ignition_date'], unique=True, postgresql_where=sa.text('NOT fire_id_is_sentinel'))


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('uq_csiro_wildfire_dissolve_key', table_name='csiro_wildfire', postgresql_where=sa.text('NOT fire_id_is_sentinel'))
    op.drop_index('ix_csiro_wildfire_state_code', table_name='csiro_wildfire')
    op.drop_index('ix_csiro_wildfire_source_layer', table_name='csiro_wildfire')
    op.drop_index('ix_csiro_wildfire_ignition_date', table_name='csiro_wildfire')
    op.drop_index('ix_csiro_wildfire_fire_type', table_name='csiro_wildfire')
    op.drop_index('ix_csiro_wildfire_fire_id', table_name='csiro_wildfire')
    op.drop_index('ix_csiro_wildfire_year', table_name='csiro_wildfire')
    op.drop_table('csiro_wildfire')
