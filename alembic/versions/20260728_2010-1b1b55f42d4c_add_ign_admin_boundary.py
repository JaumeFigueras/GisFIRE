"""add ign admin boundary

Revision ID: 1b1b55f42d4c
Revises: 563afdc156a2
Create Date: 2026-07-28 20:10:04.973115+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1b1b55f42d4c'
down_revision: str | None = '563afdc156a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    The Spanish administrative divisions, hanging off ``admin_boundary`` by joined
    table inheritance. No geometry column of its own: the polygon lives on the
    parent row in EPSG:4326 like every other boundary, so there is no spatial index
    to create here.

    ``ine_code`` is indexed because it is the key Spanish statistical sources join
    on, ``nuts3_code`` because grouping by statistical region is a query the tree
    cannot answer, and ``edition`` because it is how one publication of the BDDAE
    is told from the next — the codes repeat between editions and the municipalities
    behind them do not.
    """
    op.create_table('ign_admin_boundary',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edition', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('ine_code', sa.String(), nullable=True),
    sa.Column('nuts1_code', sa.String(), nullable=True),
    sa.Column('nuts2_code', sa.String(), nullable=True),
    sa.Column('nuts3_code', sa.String(), nullable=True),
    sa.CheckConstraint("kind IN ('comunidad_autonoma', 'provincia', 'municipio', 'territorio')", name='ck_ign_admin_boundary_kind'),
    sa.ForeignKeyConstraint(['id'], ['admin_boundary.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ign_admin_boundary_edition', 'ign_admin_boundary', ['edition'], unique=False)
    op.create_index('ix_ign_admin_boundary_ine_code', 'ign_admin_boundary', ['ine_code'], unique=False)
    op.create_index('ix_ign_admin_boundary_kind', 'ign_admin_boundary', ['kind'], unique=False)
    op.create_index('ix_ign_admin_boundary_nuts3_code', 'ign_admin_boundary', ['nuts3_code'], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('ix_ign_admin_boundary_nuts3_code', table_name='ign_admin_boundary')
    op.drop_index('ix_ign_admin_boundary_kind', table_name='ign_admin_boundary')
    op.drop_index('ix_ign_admin_boundary_ine_code', table_name='ign_admin_boundary')
    op.drop_index('ix_ign_admin_boundary_edition', table_name='ign_admin_boundary')
    op.drop_table('ign_admin_boundary')
