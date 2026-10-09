"""add south korea kfs wildfire

Revision ID: 8cbaa9e5a65e
Revises: 2f5e28048454
Create Date: 2026-10-10 10:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8cbaa9e5a65e'
down_revision: str | None = '2f5e28048454'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``kfs_wildfire`` is the Korea Forest Service's wildfire statistic — 2,020
    fires over 2022 to September 2025 in its first release, one row per fire —
    hanging off ``wildfire`` by joined table inheritance like every other
    provider's.

    **No geometry and no ignition.** The statistic publishes place names and no
    coordinate, so this is, with nothing else in the schema, a wildfire table with
    neither its own geometry nor a link to an ``ignition``. The parent's
    ``perimeter`` and ``admin_boundary_id`` stay ``NULL``.

    **No unique constraint.** Nothing in a row identifies the fire, so an import
    replaces a ``year``, which is ``NOT NULL`` and indexed.

    **The two cause classifications are constrained, the published code is not.**
    ``cause_class`` and ``fire_cause`` are GisFIRE's own vocabularies and are
    checked; ``cause_category_code`` is four letters seen in one release, and a
    ``CHECK`` built from them would reject the first one the service adds.
    """
    op.create_table('kfs_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('source_file', sa.String(), nullable=False),
    sa.Column('source_row', sa.Integer(), nullable=False),
    sa.Column('office_name', sa.String(), nullable=False),
    sa.Column('office_name_rr', sa.String(), nullable=False),
    sa.Column('province_name', sa.String(), nullable=False),
    sa.Column('province_name_rr', sa.String(), nullable=False),
    sa.Column('municipality_name', sa.String(), nullable=True),
    sa.Column('municipality_name_rr', sa.String(), nullable=True),
    sa.Column('township_name', sa.String(), nullable=True),
    sa.Column('township_name_rr', sa.String(), nullable=True),
    sa.Column('village_name', sa.String(), nullable=True),
    sa.Column('village_name_rr', sa.String(), nullable=True),
    sa.Column('cause_category_code', sa.String(), nullable=True),
    sa.Column('cause_detail', sa.String(), nullable=False),
    sa.Column('cause_text', sa.String(), nullable=False),
    sa.Column('cause_text_en', sa.String(), nullable=False),
    sa.Column('cause_class', sa.String(), nullable=False),
    sa.Column('fire_cause', sa.String(), nullable=False),
    sa.Column('cause_suspected', sa.Boolean(), nullable=False),
    sa.Column('area_ha', sa.Float(), nullable=False),
    sa.Column('end_date_problem', sa.String(), nullable=True),
    sa.CheckConstraint("cause_class IN ('visitor', 'unknown', 'waste_burning', 'cigarette', 'embers_ash', 'agricultural_burning', 'structure_fire', 'work_machinery', 'power_electrical', 'grave_visitor', 'arson', 'beekeeping', 'military_aircraft', 'vehicle', 'other', 'lightning', 'children', 'rekindle')", name='ck_kfs_wildfire_cause_class'),
    sa.CheckConstraint("end_date_problem IS NULL OR end_date_problem IN ('extinguish_before_start', 'extinguish_year_invalid')", name='ck_kfs_wildfire_end_date_problem'),
    sa.CheckConstraint("fire_cause IN ('lightning', 'natural', 'human', 'unknown')", name='ck_kfs_wildfire_fire_cause'),
    sa.CheckConstraint('area_ha >= 0', name='ck_kfs_wildfire_area_ha'),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_kfs_wildfire_cause_class', 'kfs_wildfire', ['cause_class'], unique=False)
    op.create_index('ix_kfs_wildfire_fire_cause', 'kfs_wildfire', ['fire_cause'], unique=False)
    op.create_index('ix_kfs_wildfire_province_name', 'kfs_wildfire', ['province_name'], unique=False)
    op.create_index('ix_kfs_wildfire_year', 'kfs_wildfire', ['year'], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('ix_kfs_wildfire_year', table_name='kfs_wildfire')
    op.drop_index('ix_kfs_wildfire_province_name', table_name='kfs_wildfire')
    op.drop_index('ix_kfs_wildfire_fire_cause', table_name='kfs_wildfire')
    op.drop_index('ix_kfs_wildfire_cause_class', table_name='kfs_wildfire')
    op.drop_table('kfs_wildfire')
