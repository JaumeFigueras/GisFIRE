"""add egif wildfire ignition and catalogues

Revision ID: 7f2c85d43b19
Revises: 1b1b55f42d4c
Create Date: 2026-07-29 17:10:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f2c85d43b19'
down_revision: str | None = '1b1b55f42d4c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    Five tables, created in dependency order.

    The two catalogues come first, because ``egif_wildfire`` references both.
    They are separate tables rather than one keyed by a code space, because the
    code spaces overlap and disagree: ``400`` is *Intencionado* as a cause and
    *Motivación desconocida* as a motivation. Each is unique on ``(code, label)``
    rather than on the code, so an edition of the *Instrucciones* that renames a
    code can be stored beside the old meaning instead of overwriting it. Both are
    created empty — the import inserts whatever the Excel export it reads
    contains.

    ``egif_ignition`` comes before ``egif_wildfire``, which carries the foreign
    key to it. It holds no geometry of its own: the point lives on the parent
    ``ignition`` row in EPSG:4326, and the coordinate as published is kept as the
    four scalars ``utm_zone`` / ``utm_x`` / ``utm_y`` / ``datum``. The two CHECKs
    on those pin the zone and the datum to the values the exports actually use,
    which is what turns a transcription error — one 2022 fire is published with
    ``Huso 3`` — into a failed insert rather than a point in the sea.

    ``egif_wildfire_report`` is last: a one-to-one child of ``egif_wildfire``
    holding the blocks only the XML export publishes. Its primary key is also its
    foreign key, so a fire has at most one, and whether it has one at all is how
    the schema records which export a fire was read from.
    """
    op.create_table('egif_fire_cause',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('label_en', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'label', name='uq_egif_fire_cause_code_label')
    )
    op.create_index('ix_egif_fire_cause_code', 'egif_fire_cause', ['code'], unique=False)
    op.create_table('egif_fire_motivation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('label_en', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'label', name='uq_egif_fire_motivation_code_label')
    )
    op.create_index('ix_egif_fire_motivation_code', 'egif_fire_motivation', ['code'], unique=False)
    op.create_table('egif_ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_number', sa.String(), nullable=False),
    sa.Column('utm_zone', sa.Integer(), nullable=False),
    sa.Column('utm_x', sa.Float(), nullable=False),
    sa.Column('utm_y', sa.Float(), nullable=False),
    sa.Column('datum', sa.String(), nullable=False),
    sa.Column('start_point_count', sa.Integer(), nullable=True),
    sa.Column('mtn_sheet', sa.String(), nullable=True),
    sa.Column('mtn_grid', sa.String(), nullable=True),
    sa.Column('place_name', sa.String(), nullable=True),
    sa.CheckConstraint("datum IN ('ETRS89', 'REGCAN95')", name='ck_egif_ignition_datum'),
    sa.CheckConstraint('utm_zone IN (28, 29, 30, 31)', name='ck_egif_ignition_utm_zone'),
    sa.ForeignKeyConstraint(['id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('report_number')
    )
    op.create_table('egif_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_number', sa.String(), nullable=False),
    sa.Column('egif_id', sa.Integer(), nullable=True),
    sa.Column('campaign', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('ignition_id', sa.Integer(), nullable=False),
    sa.Column('ccaa_name', sa.String(), nullable=True),
    sa.Column('province_name', sa.String(), nullable=True),
    sa.Column('province_ine_code', sa.String(), nullable=False),
    sa.Column('municipality_name', sa.String(), nullable=True),
    sa.Column('municipality_ine_code', sa.String(), nullable=True),
    sa.Column('comarca_name', sa.String(), nullable=True),
    sa.Column('minor_entity_name', sa.String(), nullable=True),
    sa.Column('affected_municipality_count', sa.Integer(), nullable=True),
    sa.Column('cause_id', sa.Integer(), nullable=True),
    sa.Column('motivation_id', sa.Integer(), nullable=True),
    sa.Column('area_ha_wooded', sa.Float(), nullable=True),
    sa.Column('area_ha_non_wooded', sa.Float(), nullable=True),
    sa.Column('area_ha_forest_total', sa.Float(), nullable=True),
    sa.Column('area_ha_agricultural', sa.Float(), nullable=True),
    sa.Column('area_ha_other_non_forest', sa.Float(), nullable=True),
    sa.Column('wui_affected', sa.Boolean(), nullable=True),
    sa.Column('wui_compact', sa.Boolean(), nullable=True),
    sa.Column('wui_scattered', sa.Boolean(), nullable=True),
    sa.Column('wui_isolated', sa.Boolean(), nullable=True),
    sa.Column('protected_space_affected', sa.Boolean(), nullable=True),
    sa.Column('agricultural_land_affected', sa.Boolean(), nullable=True),
    sa.Column('zar_affected', sa.Boolean(), nullable=True),
    sa.Column('pss_report_number', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['cause_id'], ['egif_fire_cause.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.ForeignKeyConstraint(['ignition_id'], ['egif_ignition.id'], ),
    sa.ForeignKeyConstraint(['motivation_id'], ['egif_fire_motivation.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('egif_id'),
    sa.UniqueConstraint('report_number')
    )
    op.create_index('ix_egif_wildfire_campaign', 'egif_wildfire', ['campaign'], unique=False)
    op.create_index('ix_egif_wildfire_cause_id', 'egif_wildfire', ['cause_id'], unique=False)
    op.create_index('ix_egif_wildfire_motivation_id', 'egif_wildfire', ['motivation_id'], unique=False)
    op.create_table('egif_wildfire_report',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('control_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_ground_response_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_aerial_response_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_helitransported_response_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_coordination_response_date_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_notification_from_112', sa.Boolean(), nullable=True),
    sa.Column('detected_by_code', sa.String(), nullable=True),
    sa.Column('started_next_to_other', sa.String(), nullable=True),
    sa.Column('responsibility_grade_code', sa.String(), nullable=True),
    sa.Column('days_since_storm', sa.Integer(), nullable=True),
    sa.Column('cause_investigated_code', sa.String(), nullable=True),
    sa.Column('cause_certainty_code', sa.String(), nullable=True),
    sa.Column('offender_identified_code', sa.String(), nullable=True),
    sa.Column('activity_authorisation_code', sa.String(), nullable=True),
    sa.Column('day_class_code', sa.String(), nullable=True),
    sa.Column('weather_station_code', sa.String(), nullable=True),
    sa.Column('weather_observation_time', sa.Time(), nullable=True),
    sa.Column('days_since_rain', sa.Integer(), nullable=True),
    sa.Column('max_temperature_celsius', sa.Float(), nullable=True),
    sa.Column('relative_humidity_percent', sa.Float(), nullable=True),
    sa.Column('wind_speed_km_h', sa.Float(), nullable=True),
    sa.Column('wind_direction_degrees', sa.Integer(), nullable=True),
    sa.Column('max_severity_level', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['egif_wildfire.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table('egif_wildfire_report')
    op.drop_index('ix_egif_wildfire_motivation_id', table_name='egif_wildfire')
    op.drop_index('ix_egif_wildfire_cause_id', table_name='egif_wildfire')
    op.drop_index('ix_egif_wildfire_campaign', table_name='egif_wildfire')
    op.drop_table('egif_wildfire')
    op.drop_table('egif_ignition')
    op.drop_index('ix_egif_fire_motivation_code', table_name='egif_fire_motivation')
    op.drop_table('egif_fire_motivation')
    op.drop_index('ix_egif_fire_cause_code', table_name='egif_fire_cause')
    op.drop_table('egif_fire_cause')
