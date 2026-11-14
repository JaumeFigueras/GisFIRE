"""add cellsearch tables

Revision ID: 687521539664
Revises: 7a1c4e9b2d56
Create Date: 2026-11-13 10:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '687521539664'
down_revision: str | None = '7a1c4e9b2d56'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    What the first flash-based algorithm, Cellsearch (Tuomi & Larjavaara 2005),
    needs to store. Most of it is generic; one table is Cellsearch's own.

    * ``thunderstorm_experiment.summary`` — what a run reports about itself
      (Cellsearch: cells and flashes per size class, flashes discarded by the
      location error, cells the window may have cut). An *output*, so it stays
      out of ``uq_thunderstorm_experiment_configuration``. ``'{}'`` by default,
      which also fills the existing rows.
    * ``thunderstorm.number_of_flashes`` — for flash-based algorithms; ``NULL``
      for the others. Between 1 and ``number_of_lightnings``: every flash has at
      least one linked stroke.
    * ``thunderstorm.area`` — in km², the appendix formula of the article
      (``12·√det(Σ)`` over the clustered points). Positive or ``NULL``: the
      formula is undefined for fewer than three points or points in a line, and
      a zero would turn every density into a division by zero.
    * ``thunderstorm_cellsearch_flash`` — one row per flash of a kept cell, with
      a surrogate ``id`` (the integer key QGIS needs for the per-flash view; the
      natural key ``(thunderstorm_id, sequence)`` is unique): its position in
      the cell, its representative stroke and the cell's running
      centre right after it (the article's Fig. 8 trajectory). Two composite
      foreign keys: to ``thunderstorm(id, experiment_id)``, so the copied
      ``experiment_id`` is right and a stroke represents at most one flash per
      experiment; and to ``thunderstorm_lightning(thunderstorm_id,
      lightning_id)``, so the representative stroke is one of the cell's own.
      Both cascade, so an experiment still takes everything with it.

    The existing views select their columns by name, so none of them changes
    here; the next revision adds these columns to them.
    """
    op.add_column('thunderstorm_experiment',
                  sa.Column('summary', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
                            server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_check_constraint('ck_thunderstorm_experiment_summary', 'thunderstorm_experiment',
                               "jsonb_typeof(summary) = 'object'")

    op.add_column('thunderstorm', sa.Column('number_of_flashes', sa.Integer(), nullable=True))
    op.add_column('thunderstorm', sa.Column('area', sa.Float(), nullable=True))
    op.create_check_constraint('ck_thunderstorm_number_of_flashes', 'thunderstorm',
                               'number_of_flashes >= 1 AND number_of_flashes <= number_of_lightnings')
    op.create_check_constraint('ck_thunderstorm_area', 'thunderstorm', 'area > 0')

    op.create_geospatial_table('thunderstorm_cellsearch_flash',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('thunderstorm_id', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('lightning_id', sa.Integer(), nullable=False),
    sa.Column('centre', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.CheckConstraint('sequence >= 1', name='ck_thunderstorm_cellsearch_flash_sequence'),
    sa.ForeignKeyConstraint(['thunderstorm_id', 'experiment_id'], ['thunderstorm.id', 'thunderstorm.experiment_id'], name='fk_thunderstorm_cellsearch_flash_thunderstorm', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['thunderstorm_id', 'lightning_id'], ['thunderstorm_lightning.thunderstorm_id', 'thunderstorm_lightning.lightning_id'], name='fk_thunderstorm_cellsearch_flash_link', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('thunderstorm_id', 'sequence', name='uq_thunderstorm_cellsearch_flash_sequence'),
    sa.UniqueConstraint('experiment_id', 'lightning_id', name='uq_thunderstorm_cellsearch_flash_experiment_lightning')
    )
    op.create_geospatial_index('idx_thunderstorm_cellsearch_flash_centre', 'thunderstorm_cellsearch_flash', ['centre'], unique=False, postgresql_using='gist', postgresql_ops={})


def downgrade() -> None:
    """Revert this revision."""
    op.drop_geospatial_index('idx_thunderstorm_cellsearch_flash_centre', table_name='thunderstorm_cellsearch_flash', postgresql_using='gist', column_name='centre')
    op.drop_geospatial_table('thunderstorm_cellsearch_flash')
    op.drop_constraint('ck_thunderstorm_area', 'thunderstorm', type_='check')
    op.drop_constraint('ck_thunderstorm_number_of_flashes', 'thunderstorm', type_='check')
    op.drop_column('thunderstorm', 'area')
    op.drop_column('thunderstorm', 'number_of_flashes')
    op.drop_constraint('ck_thunderstorm_experiment_summary', 'thunderstorm_experiment', type_='check')
    op.drop_column('thunderstorm_experiment', 'summary')
