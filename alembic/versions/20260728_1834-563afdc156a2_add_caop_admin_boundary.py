"""add caop admin boundary

Revision ID: 563afdc156a2
Revises: e4b7c1a90f3d
Create Date: 2026-07-28 18:34:03.397580+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '563afdc156a2'
down_revision: str | None = 'e4b7c1a90f3d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    The Portuguese administrative divisions, hanging off ``admin_boundary`` by
    joined table inheritance. No geometry column of its own: the polygon lives on
    the parent row in EPSG:4326 like every other boundary, so there is no spatial
    index to create here.

    ``edition`` is indexed because it is how one publication of the CAOP is told
    from the next — the codes repeat between editions and the parishes behind them
    do not — and ``nuts3_code`` because grouping fires by statistical region is a
    query the tree cannot answer.
    """
    op.create_table('caop_admin_boundary',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edition', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('name_simplified', sa.String(), nullable=True),
    sa.Column('nuts1_code', sa.String(), nullable=True),
    sa.Column('nuts1_name', sa.String(), nullable=True),
    sa.Column('nuts2_name', sa.String(), nullable=True),
    sa.Column('nuts3_code', sa.String(), nullable=True),
    sa.Column('nuts3_name', sa.String(), nullable=True),
    sa.Column('area_ha', sa.Float(), nullable=False),
    sa.Column('perimeter_km', sa.Integer(), nullable=False),
    sa.CheckConstraint("kind IN ('distrito', 'municipio', 'freguesia')", name='ck_caop_admin_boundary_kind'),
    sa.ForeignKeyConstraint(['id'], ['admin_boundary.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_caop_admin_boundary_edition', 'caop_admin_boundary', ['edition'], unique=False)
    op.create_index('ix_caop_admin_boundary_kind', 'caop_admin_boundary', ['kind'], unique=False)
    op.create_index('ix_caop_admin_boundary_nuts3_code', 'caop_admin_boundary', ['nuts3_code'], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('ix_caop_admin_boundary_nuts3_code', table_name='caop_admin_boundary')
    op.drop_index('ix_caop_admin_boundary_kind', table_name='caop_admin_boundary')
    op.drop_index('ix_caop_admin_boundary_edition', table_name='caop_admin_boundary')
    op.drop_table('caop_admin_boundary')
