"""add mexico conafor wildfire

Revision ID: 3f8a5c21d7b4
Revises: d5f7a3b91c04
Create Date: 2026-08-07 17:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3f8a5c21d7b4'
down_revision: str | None = 'd5f7a3b91c04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``conafor_wildfire`` is CONAFOR's national burnt-area cartography for Mexico —
    45,914 polygons over 2010-2023 in fourteen yearly shapefiles — and
    ``conafor_fire_cause`` is the catalogue of the 179 cause classifications they
    use between them. The fire hangs off its generic parent by joined table
    inheritance like every other provider's.

    Five things about this pair are worth reading before changing either.

    **``fire_code`` is UNIQUE, and this is the first perimeter provider where that
    is true.** ICNF cannot have one (48,861 of its features publish no identifier),
    Greece cannot (nothing identifies a fire), GWIS cannot (its id repeats). Here
    the published ``CLAVEINC`` is ``YY-EE-NNNN`` in all 45,914 rows and takes 45,909
    distinct values; the five repeats are all in 2021 and all *exact* duplicate
    features — identical attributes, byte-identical geometry — so an import that
    drops the second copy loses nothing and the constraint holds. It is also what
    makes an ``ON CONFLICT (fire_code)`` upsert correct for this dataset.

    **No geometry is created here, and that is not because there is none.** The
    perimeter is the generic ``wildfire.perimeter`` on the parent row, already
    indexed there. Unlike ``icnf_wildfire``, ``nbac_wildfire``, ``darpa_wildfire``
    and ``rediam_wildfire``, this table carries **no second geometry column**:
    CONAFOR publishes in EPSG:4326 in all fourteen archives, so there is no
    national grid to keep beside it. Adding one would mean storing a projection the
    provider never used.

    **``conafor_fire_cause`` gets two partial unique indexes rather than one
    ``UNIQUE`` constraint.** The natural key is the ``(cause, specific_cause)``
    pair, and ``CAUSAESP`` is not published by 2011 or by any year from 2020 — so
    ``specific_cause`` is NULL on the classifications covering 27,624 of the 45,914
    fires, three in five. Under SQL's rules two NULLs are not equal, so a plain
    ``UNIQUE (cause, specific_cause)`` would admit ``('Fogatas', NULL)`` twice and
    the catalogue would grow a duplicate row every time a layer without the column
    was imported. ``uq_conafor_fire_cause_pair`` covers the rows that have both
    halves, ``uq_conafor_fire_cause_cause_only`` the rows that have only a cause,
    and between them every row is covered exactly once.

    PostgreSQL 15 would write this as ``UNIQUE NULLS NOT DISTINCT``. Two partial
    indexes say the same thing without a dialect-specific construct and without
    tying the schema to a server version.

    **``cause_normalised`` is indexed and deliberately not unique.** CONAFOR
    publishes no cause code at all — the cause is free text, typed 64 ways over
    fourteen years for about twenty real causes, ``'Fogatas'`` beside ``'fogatas'``
    beside ``'Fogata'`` beside ``'Fogatas\\n'``. Case- and accent-folding gets 64 to
    43 and no further. Many published strings therefore share one canonical form,
    which is the entire point of the column: it is the grouping key that makes a
    fourteen-year cause series a ``GROUP BY``, not an identity.

    **``fire_type``, ``impact_level``, ``vegetation_type`` and ``perimeter_source``
    get no check constraints**, on the argument ``greece_ffa_wildfire.incident_
    category`` sets out. Every one of them is a published vocabulary observed once,
    and half of them are misspelt in the observation: ``TIPIMPAC`` has fourteen
    spellings of three values and ``TIPVEG`` a hundred and fifty-six. A
    constraint built from that would reject both the next term CONAFOR adds and
    the next way it mistypes an old one. The vocabularies live in
    ``src/providers/mexico_conafor`` instead.

    **``area_ha`` is nullable, for one row in 45,914.** It is the burnt area, it
    is published by every layer of every year, and it is empty on ``21-24-0078`` —
    a San Luis Potosí fire of December 2021 that publishes everything else,
    polygon included. A ``NOT NULL`` here would delete a real fire rather than
    record what CONAFOR published, and the area is recoverable from either the
    strata or the geometry. The same argument as ``wildfire.perimeter`` being
    nullable for the nine 2012 features that carry attributes and an empty shape.

    ``state_code`` is indexed and ``state_name`` is not: the name is spelled 34
    ways for 32 states — *Distrito Federal* and *Ciudad de México* being one state
    either side of 2016 — so it is the code that a query should group and filter
    on, and indexing the name would invite the wrong one.
    """
    op.create_table('conafor_fire_cause',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cause', sa.String(), nullable=False),
    sa.Column('cause_normalised', sa.String(), nullable=True),
    sa.Column('cause_en', sa.String(), nullable=True),
    sa.Column('specific_cause', sa.String(), nullable=True),
    sa.Column('specific_cause_en', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conafor_fire_cause_cause_normalised', 'conafor_fire_cause', ['cause_normalised'], unique=False)
    op.create_index('uq_conafor_fire_cause_cause_only', 'conafor_fire_cause', ['cause'], unique=True,
                    postgresql_where=sa.text('specific_cause IS NULL'))
    op.create_index('uq_conafor_fire_cause_pair', 'conafor_fire_cause', ['cause', 'specific_cause'], unique=True,
                    postgresql_where=sa.text('specific_cause IS NOT NULL'))
    op.create_table('conafor_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fire_code', sa.String(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('state_code', sa.Integer(), nullable=False),
    sa.Column('state_name', sa.String(), nullable=False),
    sa.Column('municipality_code', sa.Integer(), nullable=True),
    sa.Column('municipality_name', sa.String(), nullable=False),
    sa.Column('property_name', sa.String(), nullable=True),
    sa.Column('date_time_precision', sa.String(), nullable=False),
    sa.Column('cause_id', sa.Integer(), nullable=True),
    sa.Column('fire_type', sa.String(), nullable=True),
    sa.Column('impact_level', sa.String(), nullable=True),
    sa.Column('vegetation_type', sa.String(), nullable=True),
    sa.Column('vegetation_type_code', sa.String(), nullable=True),
    sa.Column('protected_area_name', sa.String(), nullable=True),
    sa.Column('area_ha_protected', sa.Float(), nullable=True),
    sa.Column('area_ha', sa.Float(), nullable=True),
    sa.Column('area_ha_tree', sa.Float(), nullable=True),
    sa.Column('area_ha_regeneration', sa.Float(), nullable=True),
    sa.Column('area_ha_shrub', sa.Float(), nullable=True),
    sa.Column('area_ha_herbaceous', sa.Float(), nullable=True),
    sa.Column('area_ha_litter', sa.Float(), nullable=True),
    sa.Column('area_ha_organic_soil', sa.Float(), nullable=True),
    sa.Column('perimeter_source', sa.String(), nullable=True),
    sa.CheckConstraint("date_time_precision IN ('year', 'day')",
                       name='ck_conafor_wildfire_date_time_precision'),
    sa.ForeignKeyConstraint(['cause_id'], ['conafor_fire_cause.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fire_code')
    )
    op.create_index('ix_conafor_wildfire_cause_id', 'conafor_wildfire', ['cause_id'], unique=False)
    op.create_index('ix_conafor_wildfire_source_layer', 'conafor_wildfire', ['source_layer'], unique=False)
    op.create_index('ix_conafor_wildfire_state_code', 'conafor_wildfire', ['state_code'], unique=False)
    op.create_index('ix_conafor_wildfire_year', 'conafor_wildfire', ['year'], unique=False)


def downgrade() -> None:
    """Revert this revision.

    The fires go before the causes: ``conafor_wildfire.cause_id`` references
    ``conafor_fire_cause.id``, so dropping the catalogue first would fail on the
    foreign key.
    """
    op.drop_index('ix_conafor_wildfire_year', table_name='conafor_wildfire')
    op.drop_index('ix_conafor_wildfire_state_code', table_name='conafor_wildfire')
    op.drop_index('ix_conafor_wildfire_source_layer', table_name='conafor_wildfire')
    op.drop_index('ix_conafor_wildfire_cause_id', table_name='conafor_wildfire')
    op.drop_table('conafor_wildfire')
    op.drop_index('uq_conafor_fire_cause_pair', table_name='conafor_fire_cause')
    op.drop_index('uq_conafor_fire_cause_cause_only', table_name='conafor_fire_cause')
    op.drop_index('ix_conafor_fire_cause_cause_normalised', table_name='conafor_fire_cause')
    op.drop_table('conafor_fire_cause')
