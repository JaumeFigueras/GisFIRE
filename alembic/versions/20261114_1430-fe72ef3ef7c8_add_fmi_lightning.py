"""add fmi lightning

Revision ID: fe72ef3ef7c8
Revises: e7147a41b62b
Create Date: 2026-11-14 14:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = 'fe72ef3ef7c8'
down_revision: str | None = 'e7147a41b62b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``fmi_lightning`` holds the strokes published by the Finnish Meteorological
    Institute's open-data WFS, from 1998, over Northern Europe. It hangs off
    ``lightning`` by joined table inheritance, as ``meteocat_lightning`` does.

    **No unique constraint.** FMI publishes no stroke id and no combination of
    fields is unique, so an import replaces a month, found through
    ``ix_lightning_date_time``.

    **The flash is ``flash_id`` alone**, one sequence since 1998, so
    ``ix_fmi_lightning_flash_id`` is on that column only — unlike MeteoCat's,
    which needs the network version beside it.

    **Every column is NOT NULL.** No sample from 1998 to 2025 has a missing value
    in any of them; the one "not recorded" value FMI publishes, a peak current of
    0, lives on ``lightning.peak_current``, which is nullable. The CHECKs hold on
    every one of 1.08 million sampled strokes. The three indicators have none:
    they are undocumented, and ``angle_indicator`` and ``timing_indicator`` are 0
    on some strokes of 1998-2004 and 1 on every later one.

    **An expression index on the TM35FIN point.** The EPSG:3067 point is not
    stored; the ``v_fmi_lightning_3067`` view of the next revision and the
    thunderstorm reader compute it, and ``idx_fmi_lightning_geometry_3067``
    indexes the very same expression, as ``idx_meteocat_lightning_geometry_25831``
    does for MeteoCat.
    """
    op.create_geospatial_table('fmi_lightning',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flash_id', sa.Integer(), nullable=False),
    sa.Column('multiplicity', sa.Integer(), nullable=False),
    sa.Column('stroke_index', sa.Integer(), nullable=False),
    sa.Column('published_multiplicity', sa.Integer(), nullable=False),
    sa.Column('number_of_sensors', sa.Integer(), nullable=False),
    sa.Column('degrees_of_freedom', sa.Integer(), nullable=False),
    sa.Column('chi_squared', sa.Float(), nullable=False),
    sa.Column('ellipse_major_axis', sa.Float(), nullable=False),
    sa.Column('ellipse_minor_axis', sa.Float(), nullable=False),
    sa.Column('ellipse_angle', sa.Float(), nullable=False),
    sa.Column('rise_time', sa.Float(), nullable=False),
    sa.Column('peak_to_zero_time', sa.Float(), nullable=False),
    sa.Column('stroke_status', sa.SmallInteger(), nullable=False),
    sa.Column('angle_indicator', sa.SmallInteger(), nullable=False),
    sa.Column('signal_indicator', sa.SmallInteger(), nullable=False),
    sa.Column('timing_indicator', sa.SmallInteger(), nullable=False),
    sa.Column('geometry_etrs89', Geometry(geometry_type='POINT', srid=4258, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.CheckConstraint('flash_id >= 0', name='ck_fmi_lightning_flash_id'),
    sa.CheckConstraint('multiplicity >= 1', name='ck_fmi_lightning_multiplicity'),
    sa.CheckConstraint('stroke_index >= 1 AND stroke_index <= multiplicity', name='ck_fmi_lightning_stroke_index'),
    sa.CheckConstraint('published_multiplicity >= 0', name='ck_fmi_lightning_published_multiplicity'),
    sa.CheckConstraint('number_of_sensors >= 1', name='ck_fmi_lightning_number_of_sensors'),
    sa.CheckConstraint('degrees_of_freedom >= 0', name='ck_fmi_lightning_degrees_of_freedom'),
    sa.CheckConstraint('chi_squared >= 0', name='ck_fmi_lightning_chi_squared'),
    sa.CheckConstraint('ellipse_minor_axis >= 0 AND ellipse_minor_axis <= ellipse_major_axis', name='ck_fmi_lightning_ellipse_axes'),
    sa.CheckConstraint('ellipse_angle >= 0 AND ellipse_angle <= 180', name='ck_fmi_lightning_ellipse_angle'),
    sa.CheckConstraint('rise_time >= 0', name='ck_fmi_lightning_rise_time'),
    sa.CheckConstraint('peak_to_zero_time >= 0', name='ck_fmi_lightning_peak_to_zero_time'),
    sa.ForeignKeyConstraint(['id'], ['lightning.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_geospatial_index('idx_fmi_lightning_geometry_etrs89', 'fmi_lightning', ['geometry_etrs89'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_fmi_lightning_flash_id', 'fmi_lightning', ['flash_id'], unique=False)
    op.create_index('idx_fmi_lightning_geometry_3067', 'fmi_lightning', [sa.text('(st_transform(geometry_etrs89, 3067)::geometry(Point,3067))')], unique=False, postgresql_using='gist')


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('idx_fmi_lightning_geometry_3067', table_name='fmi_lightning', postgresql_using='gist')
    op.drop_index('ix_fmi_lightning_flash_id', table_name='fmi_lightning')
    op.drop_geospatial_index('idx_fmi_lightning_geometry_etrs89', table_name='fmi_lightning', postgresql_using='gist', column_name='geometry_etrs89')
    op.drop_geospatial_table('fmi_lightning')
