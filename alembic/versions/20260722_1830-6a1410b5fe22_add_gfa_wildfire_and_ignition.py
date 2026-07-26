"""add gfa wildfire and ignition

Revision ID: 6a1410b5fe22
Revises: b2d7c4e91f03
Create Date: 2026-07-22 18:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
# revision identifiers, used by Alembic.
revision: str = '6a1410b5fe22'
down_revision: str | None = 'b2d7c4e91f03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``gfa_ignition`` before ``gfa_wildfire``: the wildfire's ``gfa_ignition_id``
    references it, so the ignition table has to exist first. The ignition point
    lives on ``gfa_ignition`` (through the generic ``ignition`` table), not on
    ``gfa_wildfire`` — the perimeter and the point are two observations of one
    fire, matched by ``gfa_id``.
    """
    op.create_table('gfa_ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gfa_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gfa_id')
    )
    op.create_table('gfa_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gfa_id', sa.Integer(), nullable=False),
    sa.Column('gfa_ignition_id', sa.Integer(), nullable=False),
    sa.Column('size_km2', sa.Float(), nullable=True),
    sa.Column('perimeter_km', sa.Float(), nullable=True),
    sa.Column('duration_days', sa.Integer(), nullable=True),
    sa.Column('fire_line_km', sa.Float(), nullable=True),
    sa.Column('spread_km2_day', sa.Float(), nullable=True),
    sa.Column('speed_km_day', sa.Float(), nullable=True),
    sa.Column('direction', sa.String(), nullable=True),
    sa.Column('direction_fraction', sa.Float(), nullable=True),
    sa.Column('modis_tile', sa.String(), nullable=True),
    sa.Column('landcover', sa.String(), nullable=True),
    sa.Column('landcover_fraction', sa.Float(), nullable=True),
    sa.Column('gfed_region', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['gfa_ignition_id'], ['gfa_ignition.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gfa_id')
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table('gfa_wildfire')
    op.drop_table('gfa_ignition')
