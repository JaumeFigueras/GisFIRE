"""add thunderstorm tables

Revision ID: 3e8b5d1c7f20
Revises: 9c4f1a7e3b62
Create Date: 2026-11-08 11:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3e8b5d1c7f20'
down_revision: str | None = '9c4f1a7e3b62'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    The five thunderstorm tables of ``src/data_model/thunderstorm.py``: a
    thunderstorm is inferred, by clustering one provider's strokes, so it hangs
    off the run that produced it.

    * ``thunderstorm_experiment`` — one clustering run: provider, period, stroke
      filter, algorithm, parameters, hull settings, software version, status.
    * ``thunderstorm`` — one group the run found, with its concave hull.
    * ``thunderstorm_lightning`` — which strokes make it up.
    * ``thunderstorm_tracking`` — one evolution run on an experiment's
      thunderstorms: window length and step, anchor, minimum strokes, centre.
    * ``thunderstorm_evolution`` — one window of one thunderstorm in one
      tracking, with its gravity centre and concave hull.

    **No configuration twice.** Each run is unique on its whole configuration,
    ``software_version`` included; ``jsonb`` and ``interval`` compare by value, so
    neither key order nor ``600 s`` against ``10 min`` makes two runs different.

    **Nothing across experiments.** Links and windows copy ``experiment_id`` and
    reference ``(id, experiment_id)`` — hence the ``UNIQUE (id, experiment_id)``
    on ``thunderstorm`` and ``thunderstorm_tracking`` — so a stroke can be in one
    thunderstorm per experiment, and a window cannot pair a thunderstorm with a
    tracking of another experiment.

    **Deletes.** An experiment takes everything it produced with it, a tracking
    its windows. A stroke in a thunderstorm cannot be deleted (``RESTRICT``): a
    re-import of a provider's year has to drop the experiments covering it first,
    which ``ix_thunderstorm_experiment_period`` finds.
    """
    op.create_table('thunderstorm_experiment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('data_provider_id', sa.Integer(), nullable=False),
    sa.Column('algorithm', sa.String(), nullable=False),
    sa.Column('parameters', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.Column('lightning_filter', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.Column('hull_parameters', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.Column('date_time_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_time_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('software_version', sa.String(), nullable=False),
    sa.Column('status', sa.String(), server_default=sa.text("'running'"), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('date_time_end > date_time_start', name='ck_thunderstorm_experiment_period'),
    sa.CheckConstraint("algorithm <> ''", name='ck_thunderstorm_experiment_algorithm'),
    sa.CheckConstraint("software_version <> ''", name='ck_thunderstorm_experiment_software_version'),
    sa.CheckConstraint("status IN ('running', 'complete', 'failed')", name='ck_thunderstorm_experiment_status'),
    sa.CheckConstraint("(status = 'complete') = (completed_at IS NOT NULL)", name='ck_thunderstorm_experiment_completed_at'),
    sa.CheckConstraint("jsonb_typeof(parameters) = 'object'", name='ck_thunderstorm_experiment_parameters'),
    sa.CheckConstraint("jsonb_typeof(lightning_filter) = 'object'", name='ck_thunderstorm_experiment_lightning_filter'),
    sa.CheckConstraint("jsonb_typeof(hull_parameters) = 'object'", name='ck_thunderstorm_experiment_hull_parameters'),
    sa.ForeignKeyConstraint(['data_provider_id'], ['data_provider.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('data_provider_id', 'algorithm', 'parameters', 'lightning_filter', 'hull_parameters', 'date_time_start', 'date_time_end', 'software_version', name='uq_thunderstorm_experiment_configuration')
    )
    op.create_index('ix_thunderstorm_experiment_period', 'thunderstorm_experiment', ['data_provider_id', 'date_time_start', 'date_time_end'], unique=False)

    op.create_geospatial_table('thunderstorm',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.Integer(), nullable=False),
    sa.Column('date_time_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_time_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('number_of_lightnings', sa.Integer(), nullable=False),
    sa.Column('concave_hull', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('date_time_end >= date_time_start', name='ck_thunderstorm_period'),
    sa.CheckConstraint('number_of_lightnings >= 1', name='ck_thunderstorm_number_of_lightnings'),
    sa.ForeignKeyConstraint(['experiment_id'], ['thunderstorm_experiment.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('experiment_id', 'label', name='uq_thunderstorm_experiment_label'),
    sa.UniqueConstraint('id', 'experiment_id', name='uq_thunderstorm_id_experiment')
    )
    op.create_geospatial_index('idx_thunderstorm_concave_hull', 'thunderstorm', ['concave_hull'], unique=False, postgresql_using='gist', postgresql_ops={})

    op.create_table('thunderstorm_lightning',
    sa.Column('thunderstorm_id', sa.Integer(), nullable=False),
    sa.Column('lightning_id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['lightning_id'], ['lightning.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['thunderstorm_id', 'experiment_id'], ['thunderstorm.id', 'thunderstorm.experiment_id'], name='fk_thunderstorm_lightning_thunderstorm', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('thunderstorm_id', 'lightning_id'),
    sa.UniqueConstraint('experiment_id', 'lightning_id', name='uq_thunderstorm_lightning_experiment_lightning')
    )
    op.create_index('ix_thunderstorm_lightning_lightning_id', 'thunderstorm_lightning', ['lightning_id'], unique=False)

    op.create_table('thunderstorm_tracking',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('window_length', sa.Interval(), nullable=False),
    sa.Column('window_step', sa.Interval(), nullable=False),
    sa.Column('window_anchor', sa.String(), server_default=sa.text("'clock'"), nullable=False),
    sa.Column('min_lightnings', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('centre_method', sa.String(), server_default=sa.text("'mean'"), nullable=False),
    sa.Column('hull_parameters', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False),
    sa.Column('software_version', sa.String(), nullable=False),
    sa.Column('status', sa.String(), server_default=sa.text("'running'"), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("window_step > INTERVAL '0' AND window_step <= window_length", name='ck_thunderstorm_tracking_window'),
    sa.CheckConstraint('min_lightnings >= 1', name='ck_thunderstorm_tracking_min_lightnings'),
    sa.CheckConstraint("window_anchor IN ('clock', 'storm_start')", name='ck_thunderstorm_tracking_window_anchor'),
    sa.CheckConstraint("centre_method IN ('mean')", name='ck_thunderstorm_tracking_centre_method'),
    sa.CheckConstraint("software_version <> ''", name='ck_thunderstorm_tracking_software_version'),
    sa.CheckConstraint("status IN ('running', 'complete', 'failed')", name='ck_thunderstorm_tracking_status'),
    sa.CheckConstraint("(status = 'complete') = (completed_at IS NOT NULL)", name='ck_thunderstorm_tracking_completed_at'),
    sa.CheckConstraint("jsonb_typeof(hull_parameters) = 'object'", name='ck_thunderstorm_tracking_hull_parameters'),
    sa.ForeignKeyConstraint(['experiment_id'], ['thunderstorm_experiment.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('experiment_id', 'window_length', 'window_step', 'window_anchor', 'min_lightnings', 'centre_method', 'hull_parameters', 'software_version', name='uq_thunderstorm_tracking_configuration'),
    sa.UniqueConstraint('id', 'experiment_id', name='uq_thunderstorm_tracking_id_experiment')
    )

    op.create_geospatial_table('thunderstorm_evolution',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tracking_id', sa.Integer(), nullable=False),
    sa.Column('thunderstorm_id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('number_of_lightnings', sa.Integer(), nullable=False),
    sa.Column('centre', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('concave_hull', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('sequence >= 1', name='ck_thunderstorm_evolution_sequence'),
    sa.CheckConstraint('window_end > window_start', name='ck_thunderstorm_evolution_window'),
    sa.CheckConstraint('number_of_lightnings >= 1', name='ck_thunderstorm_evolution_number_of_lightnings'),
    sa.ForeignKeyConstraint(['tracking_id', 'experiment_id'], ['thunderstorm_tracking.id', 'thunderstorm_tracking.experiment_id'], name='fk_thunderstorm_evolution_tracking', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['thunderstorm_id', 'experiment_id'], ['thunderstorm.id', 'thunderstorm.experiment_id'], name='fk_thunderstorm_evolution_thunderstorm', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tracking_id', 'thunderstorm_id', 'sequence', name='uq_thunderstorm_evolution_sequence')
    )
    op.create_index('ix_thunderstorm_evolution_thunderstorm_id', 'thunderstorm_evolution', ['thunderstorm_id'], unique=False)
    op.create_geospatial_index('idx_thunderstorm_evolution_centre', 'thunderstorm_evolution', ['centre'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_geospatial_index('idx_thunderstorm_evolution_concave_hull', 'thunderstorm_evolution', ['concave_hull'], unique=False, postgresql_using='gist', postgresql_ops={})


def downgrade() -> None:
    """Revert this revision."""
    op.drop_geospatial_index('idx_thunderstorm_evolution_concave_hull', table_name='thunderstorm_evolution', postgresql_using='gist', column_name='concave_hull')
    op.drop_geospatial_index('idx_thunderstorm_evolution_centre', table_name='thunderstorm_evolution', postgresql_using='gist', column_name='centre')
    op.drop_index('ix_thunderstorm_evolution_thunderstorm_id', table_name='thunderstorm_evolution')
    op.drop_geospatial_table('thunderstorm_evolution')
    op.drop_table('thunderstorm_tracking')
    op.drop_index('ix_thunderstorm_lightning_lightning_id', table_name='thunderstorm_lightning')
    op.drop_table('thunderstorm_lightning')
    op.drop_geospatial_index('idx_thunderstorm_concave_hull', table_name='thunderstorm', postgresql_using='gist', column_name='concave_hull')
    op.drop_geospatial_table('thunderstorm')
    op.drop_index('ix_thunderstorm_experiment_period', table_name='thunderstorm_experiment')
    op.drop_table('thunderstorm_experiment')
