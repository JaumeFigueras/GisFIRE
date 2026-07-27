"""add icnf wildfire and fire cause

Revision ID: 3c9d61f0a742
Revises: 6a1410b5fe22
Create Date: 2026-07-27 10:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
# revision identifiers, used by Alembic.
revision: str = '3c9d61f0a742'
down_revision: str | None = '6a1410b5fe22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``icnf_fire_cause`` before ``icnf_wildfire``: the fire's ``cause_id``
    references it, so the lookup table has to exist first. It is created empty —
    the classification is not seeded here, the import inserts whatever codes the
    layers it reads actually use.

    Its unique key is the whole ``(code, type, description)`` triple rather than
    the code: the ICNF has reused four codes for different causes, so there are 97
    codes but 101 classifications.

    ``icnf_wildfire`` keeps the published EPSG:3763 geometry alongside the
    EPSG:4326 one on the parent ``wildfire`` row, so this table gets a spatial
    index of its own.
    """
    op.create_table('icnf_fire_cause',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('type_en', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('description_en', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'type', 'description', name='uq_icnf_fire_cause_code_type_description')
    )
    op.create_index('ix_icnf_fire_cause_code', 'icnf_fire_cause', ['code'], unique=False)
    op.create_geospatial_table('icnf_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('sgif_code', sa.String(), nullable=True),
    sa.Column('anepc_code', sa.String(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('date_time_precision', sa.String(), nullable=False),
    sa.Column('first_response_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), nullable=True),
    sa.Column('dicofre_code', sa.String(), nullable=True),
    sa.Column('nuts3_name', sa.String(), nullable=True),
    sa.Column('district_name', sa.String(), nullable=True),
    sa.Column('municipality_name', sa.String(), nullable=True),
    sa.Column('parish_name', sa.String(), nullable=True),
    sa.Column('place_name', sa.String(), nullable=True),
    sa.Column('cause_id', sa.Integer(), nullable=True),
    sa.Column('area_ha_gis', sa.Float(), nullable=False),
    sa.Column('area_ha_sgif', sa.Float(), nullable=True),
    sa.Column('area_ha_forest_stand', sa.Float(), nullable=True),
    sa.Column('area_ha_shrubland', sa.Float(), nullable=True),
    sa.Column('area_ha_agricultural', sa.Float(), nullable=True),
    sa.Column('edition_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('perimeter_etrs89_tm06', Geometry(geometry_type='MULTIPOLYGON', srid=3763, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=True), nullable=True),
    sa.CheckConstraint("date_time_precision IN ('year', 'day', 'minute')", name='ck_icnf_wildfire_date_time_precision'),
    sa.ForeignKeyConstraint(['cause_id'], ['icnf_fire_cause.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sgif_code')
    )
    op.create_index('ix_icnf_wildfire_cause_id', 'icnf_wildfire', ['cause_id'], unique=False)
    op.create_index('ix_icnf_wildfire_source_layer', 'icnf_wildfire', ['source_layer'], unique=False)
    op.create_index('ix_icnf_wildfire_year', 'icnf_wildfire', ['year'], unique=False)
    op.create_geospatial_index('idx_icnf_wildfire_perimeter_etrs89_tm06', 'icnf_wildfire', ['perimeter_etrs89_tm06'], unique=False, postgresql_using='gist', postgresql_ops={})


def downgrade() -> None:
    """Revert this revision."""
    op.drop_geospatial_index('idx_icnf_wildfire_perimeter_etrs89_tm06', table_name='icnf_wildfire', postgresql_using='gist', column_name='perimeter_etrs89_tm06')
    op.drop_index('ix_icnf_wildfire_year', table_name='icnf_wildfire')
    op.drop_index('ix_icnf_wildfire_source_layer', table_name='icnf_wildfire')
    op.drop_index('ix_icnf_wildfire_cause_id', table_name='icnf_wildfire')
    op.drop_geospatial_table('icnf_wildfire')
    op.drop_index('ix_icnf_fire_cause_code', table_name='icnf_fire_cause')
    op.drop_table('icnf_fire_cause')
