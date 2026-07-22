"""add ignition

Revision ID: b2d7c4e91f03
Revises: 6a1410b5fe22
Create Date: 2026-07-22 18:10:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
# revision identifiers, used by Alembic.
revision: str = 'b2d7c4e91f03'
down_revision: str | None = '6a1410b5fe22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_geospatial_table('ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('data_provider_id', sa.Integer(), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('date_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('time_zone', sa.String(), nullable=True),
    sa.Column('admin_boundary_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_boundary_id'], ['admin_boundary.id'], ),
    sa.ForeignKeyConstraint(['data_provider_id'], ['data_provider.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ignition_admin_boundary_id', 'ignition', ['admin_boundary_id'], unique=False)
    op.create_index('ix_ignition_date_time', 'ignition', ['date_time'], unique=False)
    op.create_geospatial_index('idx_ignition_geometry', 'ignition', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})


def downgrade() -> None:
    """Revert this revision."""
    op.drop_geospatial_index('idx_ignition_geometry', table_name='ignition', postgresql_using='gist', column_name='geometry')
    op.drop_index('ix_ignition_date_time', table_name='ignition')
    op.drop_index('ix_ignition_admin_boundary_id', table_name='ignition')
    op.drop_geospatial_table('ignition')
