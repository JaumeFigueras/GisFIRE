"""add lightning and meteocat lightning

Revision ID: 5b7e2c9d4a13
Revises: a8ac4314f84e
Create Date: 2026-11-08 10:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = '5b7e2c9d4a13'
down_revision: str | None = 'a8ac4314f84e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``lightning`` is the generic stroke — instant, point in EPSG:4326, signed peak
    current, cloud-to-ground flag, administrative boundary — and the first table of
    the schema that is not about fires. It follows ``ignition`` closely, without the
    ``time_zone`` column: a detection network publishes an instant, so there is no
    conversion to record.

    ``meteocat_lightning`` is MeteoCat's XDDE network, hanging off it by joined
    table inheritance like every provider's table: about 6.2 million strokes over
    2006-2020 in the CSV delivery.

    **No unique constraint.** Nothing in a row identifies a stroke — not even
    ``(secidx, data)`` — so an import replaces a UTC year, found through
    ``ix_lightning_date_time``.

    **The flash is indexed as a pair.** The two network generations number their
    flashes independently, so ``flash_id`` means something only with
    ``network_version``, and ``ix_meteocat_lightning_flash`` is on both.

    **The CHECKs encode "not recorded is NULL".** ``number_of_sensors >= 1``
    refuses the ``0`` the first network generation published for "not recorded".
    ``stroke_index <= multiplicity`` and ``minor <= major`` hold on every row of the
    delivery.

    **An expression index on the UTM 31N point.** The 25831 point is not stored; the
    ``v_meteocat_lightning_25831`` view of the next revision computes it, and
    ``idx_meteocat_lightning_geometry_25831`` indexes the very same expression so a
    QGIS bounding-box query on that view is not a scan of six million points.
    """
    op.create_geospatial_table('lightning',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('data_provider_id', sa.Integer(), nullable=False),
    sa.Column('date_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('peak_current', sa.Float(), nullable=True),
    sa.Column('cloud_to_ground', sa.Boolean(), nullable=True),
    sa.Column('admin_boundary_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_boundary_id'], ['admin_boundary.id'], ),
    sa.ForeignKeyConstraint(['data_provider_id'], ['data_provider.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_lightning_admin_boundary_id', 'lightning', ['admin_boundary_id'], unique=False)
    op.create_index('ix_lightning_date_time', 'lightning', ['date_time'], unique=False)
    op.create_geospatial_index('idx_lightning_geometry', 'lightning', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})

    op.create_geospatial_table('meteocat_lightning',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('network_version', sa.Integer(), nullable=False),
    sa.Column('flash_id', sa.Integer(), nullable=False),
    sa.Column('multiplicity', sa.Integer(), nullable=False),
    sa.Column('stroke_index', sa.Integer(), nullable=False),
    sa.Column('chi_squared', sa.Float(), nullable=True),
    sa.Column('ellipse_major_axis', sa.Float(), nullable=False),
    sa.Column('ellipse_minor_axis', sa.Float(), nullable=False),
    sa.Column('ellipse_angle', sa.Float(), nullable=True),
    sa.Column('number_of_sensors', sa.Integer(), nullable=True),
    sa.Column('municipality_code', sa.String(), nullable=True),
    sa.Column('geometry_etrs89', Geometry(geometry_type='POINT', srid=4258, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.CheckConstraint('network_version >= 1', name='ck_meteocat_lightning_network_version'),
    sa.CheckConstraint('multiplicity >= 1', name='ck_meteocat_lightning_multiplicity'),
    sa.CheckConstraint('stroke_index >= 1 AND stroke_index <= multiplicity', name='ck_meteocat_lightning_stroke_index'),
    sa.CheckConstraint('chi_squared >= 0', name='ck_meteocat_lightning_chi_squared'),
    sa.CheckConstraint('ellipse_minor_axis >= 0 AND ellipse_minor_axis <= ellipse_major_axis', name='ck_meteocat_lightning_ellipse_axes'),
    sa.CheckConstraint('number_of_sensors >= 1', name='ck_meteocat_lightning_number_of_sensors'),
    sa.CheckConstraint("municipality_code ~ '^[0-9]{6}$'", name='ck_meteocat_lightning_municipality_code'),
    sa.ForeignKeyConstraint(['id'], ['lightning.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_geospatial_index('idx_meteocat_lightning_geometry_etrs89', 'meteocat_lightning', ['geometry_etrs89'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_meteocat_lightning_flash', 'meteocat_lightning', ['network_version', 'flash_id'], unique=False)
    op.create_index('idx_meteocat_lightning_geometry_25831', 'meteocat_lightning', [sa.text('(st_transform(geometry_etrs89, 25831)::geometry(Point,25831))')], unique=False, postgresql_using='gist')


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('idx_meteocat_lightning_geometry_25831', table_name='meteocat_lightning', postgresql_using='gist')
    op.drop_index('ix_meteocat_lightning_flash', table_name='meteocat_lightning')
    op.drop_geospatial_index('idx_meteocat_lightning_geometry_etrs89', table_name='meteocat_lightning', postgresql_using='gist', column_name='geometry_etrs89')
    op.drop_geospatial_table('meteocat_lightning')
    op.drop_geospatial_index('idx_lightning_geometry', table_name='lightning', postgresql_using='gist', column_name='geometry')
    op.drop_index('ix_lightning_date_time', table_name='lightning')
    op.drop_index('ix_lightning_admin_boundary_id', table_name='lightning')
    op.drop_geospatial_table('lightning')
