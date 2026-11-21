"""add census admin boundary

Revision ID: cdeda14cfb8b
Revises: 92cfa94c65e5
Create Date: 2026-11-22 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cdeda14cfb8b'
down_revision: str | None = '92cfa94c65e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    The US states and counties of the Census Bureau's Cartographic Boundary Files,
    hanging off ``admin_boundary`` by joined table inheritance, as the IGN and CAOP
    divisions do. No geometry column of its own: the polygon lives on the parent
    row in EPSG:4326, so there is no spatial index to create here.
    """
    op.create_table('census_admin_boundary',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edition', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('lsad', sa.String(), nullable=False),
    sa.CheckConstraint("kind IN ('state', 'county')", name='ck_census_admin_boundary_kind'),
    sa.ForeignKeyConstraint(['id'], ['admin_boundary.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_census_admin_boundary_edition', 'census_admin_boundary', ['edition'],
                    unique=False)
    op.create_index('ix_census_admin_boundary_kind', 'census_admin_boundary', ['kind'],
                    unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('ix_census_admin_boundary_kind', table_name='census_admin_boundary')
    op.drop_index('ix_census_admin_boundary_edition', table_name='census_admin_boundary')
    op.drop_table('census_admin_boundary')
