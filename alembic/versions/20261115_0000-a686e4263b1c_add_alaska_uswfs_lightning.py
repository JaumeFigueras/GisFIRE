"""add alaska uswfs lightning

Revision ID: a686e4263b1c
Revises: 5353369ebdc8
Create Date: 2026-11-15 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a686e4263b1c'
down_revision: str | None = '5353369ebdc8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``alaska_uswfs_lightning`` holds the strokes of the Alaska Lightning Detection
    Network, released by the U.S. Wildland Fire Service from 2012. It hangs off
    ``lightning`` by joined table inheritance, as ``meteocat_lightning`` and
    ``fmi_lightning`` do.

    **No geometry column.** The release is in WGS 84, so the published point *is*
    the parent's EPSG:4326 ``geometry``: unlike MeteoCat and FMI there is no second
    point to keep.

    **No unique constraint.** The release has no stroke id (its sequence number is a
    16-bit counter that wraps), so an import replaces a year, found through
    ``ix_lightning_date_time``.

    **The flash is computed.** The network publishes strokes only; the import groups
    them into flashes and stores, as ``flash_id``, the id of each flash's first
    stroke. Two CHECKs hold that: ``flash_id`` never exceeds ``id``, and equals it
    on exactly the stroke whose ``stroke_index`` is 1.

    **Two NULLable columns.** ``sequence_number`` is missing on the first eight
    strokes of 2012, and ``ellipse_semi_major_axis`` is NULL where the release has
    0 (599 strokes, beside a semi-minor of 1 km). The CHECKs hold on every stroke
    of the 2012-2026 release; none bounds a value by the ceiling of its published
    field (255 for ``gdop``), which a later release could widen.

    **A partial expression index on ``lightning``.** The EPSG:3338 point is not
    stored; the ``v_alaska_uswfs_lightning_3338`` view of the next revision and the
    thunderstorm reader compute it from the parent's ``geometry``. So the index on
    that very expression, ``idx_lightning_alaska_uswfs_geometry_3338``, is on
    ``lightning``, restricted to this provider's rows so it does not index every
    other provider's strokes too.
    """
    op.create_table('alaska_uswfs_lightning',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flash_id', sa.Integer(), nullable=False),
    sa.Column('multiplicity', sa.Integer(), nullable=False),
    sa.Column('stroke_index', sa.Integer(), nullable=False),
    sa.Column('network_code', sa.SmallInteger(), nullable=False),
    sa.Column('sequence_number', sa.Integer(), nullable=True),
    sa.Column('gdop', sa.SmallInteger(), nullable=False),
    sa.Column('ellipse_semi_major_axis', sa.Float(), nullable=True),
    sa.Column('ellipse_semi_minor_axis', sa.Float(), nullable=False),
    sa.Column('ellipse_angle', sa.Float(), nullable=False),
    sa.CheckConstraint('flash_id >= 1 AND flash_id <= id', name='ck_alaska_uswfs_lightning_flash_id'),
    sa.CheckConstraint('(stroke_index = 1) = (flash_id = id)', name='ck_alaska_uswfs_lightning_first_stroke'),
    sa.CheckConstraint('multiplicity >= 1', name='ck_alaska_uswfs_lightning_multiplicity'),
    sa.CheckConstraint('stroke_index >= 1 AND stroke_index <= multiplicity', name='ck_alaska_uswfs_lightning_stroke_index'),
    sa.CheckConstraint('network_code >= 0', name='ck_alaska_uswfs_lightning_network_code'),
    sa.CheckConstraint('sequence_number >= 0', name='ck_alaska_uswfs_lightning_sequence_number'),
    sa.CheckConstraint('gdop >= 1', name='ck_alaska_uswfs_lightning_gdop'),
    sa.CheckConstraint('ellipse_semi_minor_axis > 0 AND (ellipse_semi_major_axis IS NULL OR ellipse_semi_major_axis >= ellipse_semi_minor_axis)', name='ck_alaska_uswfs_lightning_ellipse_axes'),
    sa.CheckConstraint('ellipse_angle >= -90 AND ellipse_angle <= 90', name='ck_alaska_uswfs_lightning_ellipse_angle'),
    sa.ForeignKeyConstraint(['id'], ['lightning.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alaska_uswfs_lightning_flash_id', 'alaska_uswfs_lightning', ['flash_id'], unique=False)
    op.create_index('idx_lightning_alaska_uswfs_geometry_3338', 'lightning', [sa.text('(st_transform(geometry, 3338)::geometry(Point,3338))')], unique=False, postgresql_using='gist', postgresql_where=sa.text("type = 'alaska_uswfs_lightning'"))


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index('idx_lightning_alaska_uswfs_geometry_3338', table_name='lightning', postgresql_using='gist', postgresql_where=sa.text("type = 'alaska_uswfs_lightning'"))
    op.drop_index('ix_alaska_uswfs_lightning_flash_id', table_name='alaska_uswfs_lightning')
    op.drop_table('alaska_uswfs_lightning')
