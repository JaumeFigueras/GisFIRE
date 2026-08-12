"""add greece ffa wildfire

Revision ID: 46ccdd5b462b
Revises: b1c47d9e3f52
Create Date: 2026-08-04 11:56:21.811370+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '46ccdd5b462b'
down_revision: str | None = 'b1c47d9e3f52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``greece_ffa_wildfire`` is the Greek Fire Service's national fire statistic —
    260,194 records over 2000-2025, one row per intervention — and
    ``greece_ffa_ignition`` is the point the service's dispatch system recorded,
    which exists for six of those twenty-six years. Both hang off their generic
    parent by joined table inheritance like every other provider's.

    Four things about them are worth reading before changing either.

    **Neither table has a unique constraint, and that is deliberate.** Nothing in
    this dataset identifies a fire. ``Α/Α ΕΓΓΡΑΦΗΣ`` and ``Α/Α ENGAGE`` begin in
    2020 — 201,948 of the 260,194 rows therefore have no identifier of any kind —
    and where the record number does exist it is not unique either: 512 of its
    57,734 values are used by more than one row. A ``UNIQUE`` on either column
    would reject records the service really published, so both are indexed and
    neither is constrained, exactly as ``gwis_wildfire.gwis_id`` is. What an import
    replaces is a **year**, which is why ``year`` is ``NOT NULL`` and indexed on
    both tables.

    **Both identifiers are ``bigint``, and one of them has to be.** ``Α/Α ENGAGE``
    runs from 92,687 to **911,023,000,013**: two rows of the 2023 sheet are past
    what a 32-bit integer holds, against a median around a million, and they look
    like a date and a sequence run together by whatever wrote them. They are what
    the service published. ``Α/Α ΕΓΓΡΑΦΗΣ`` tops out at 2,047,844 today and is
    widened with it, being the same kind of number written by the same service —
    four bytes a row against having to widen it later.

    **No geometry is created here at all**, which makes this the only wildfire
    table in the schema with no spatial index. The Fire Service publishes no
    perimeter in any year — it is an administrative statistic, like EGIF — and the
    point it does publish from 2020 lives on ``greece_ffa_ignition``, whose
    geometry is the generic ``ignition.geometry`` on the parent row. There is
    nothing to index here that is not already indexed there.

    **``ignition_id`` is a link to a row, not two coordinate columns**, on the
    argument set out in ``src/data_model/ignition.py`` — and here it is NULL on
    205,703 of the 260,194 rows, four in five. The published pair is WGS 84
    longitude and latitude, the same CRS the generic geometry is in, so
    ``greece_ffa_ignition`` stores **no coordinate columns of its own**: unlike the
    Spanish and Andalusian points, these numbers are not in another CRS and keeping
    them would be storing the same two doubles twice.

    **``incident_category`` gets no check constraint.** ``Κατηγορία Συμβάντος``
    is published by the 2025 file and by no earlier one, in four values — three
    size classes and ``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ``, a call-out that found no fire. That is
    one year of one file observed once, and a constraint built from it would
    reject the first class the service adds; the vocabulary lives in
    ``src/providers/greece_ffa`` instead. The column is indexed because excluding
    the 1,255 false alarms is a filter every count over 2025 has to apply.
    """
    op.create_table('greece_ffa_ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('record_number', sa.BigInteger(), nullable=True),
    sa.Column('engage_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_greece_ffa_ignition_record_number', 'greece_ffa_ignition', ['record_number'], unique=False)
    op.create_index('ix_greece_ffa_ignition_year', 'greece_ffa_ignition', ['year'], unique=False)
    op.create_table('greece_ffa_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('source_sheet', sa.String(), nullable=False),
    sa.Column('record_number', sa.BigInteger(), nullable=True),
    sa.Column('engage_id', sa.BigInteger(), nullable=True),
    sa.Column('incident_category', sa.String(), nullable=True),
    sa.Column('station_name', sa.String(), nullable=True),
    sa.Column('prefecture_name', sa.String(), nullable=True),
    sa.Column('forest_district_name', sa.String(), nullable=True),
    sa.Column('municipality_name', sa.String(), nullable=True),
    sa.Column('locality_name', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('area_ha_forest', sa.Float(), nullable=True),
    sa.Column('area_ha_forest_land', sa.Float(), nullable=True),
    sa.Column('area_ha_grove', sa.Float(), nullable=True),
    sa.Column('area_ha_grassland', sa.Float(), nullable=True),
    sa.Column('area_ha_reeds_marsh', sa.Float(), nullable=True),
    sa.Column('area_ha_agricultural', sa.Float(), nullable=True),
    sa.Column('area_ha_crop_residue', sa.Float(), nullable=True),
    sa.Column('area_ha_landfill', sa.Float(), nullable=True),
    sa.Column('personnel_fire_service', sa.Integer(), nullable=True),
    sa.Column('personnel_infantry_units', sa.Integer(), nullable=True),
    sa.Column('personnel_volunteers', sa.Integer(), nullable=True),
    sa.Column('personnel_army', sa.Integer(), nullable=True),
    sa.Column('personnel_other', sa.Integer(), nullable=True),
    sa.Column('vehicles_fire_service', sa.Integer(), nullable=True),
    sa.Column('vehicles_public_service', sa.Integer(), nullable=True),
    sa.Column('vehicles_water_tankers', sa.Integer(), nullable=True),
    sa.Column('vehicles_machinery', sa.Integer(), nullable=True),
    sa.Column('aircraft_helicopters', sa.Integer(), nullable=True),
    sa.Column('aircraft_cl415', sa.Integer(), nullable=True),
    sa.Column('aircraft_cl215', sa.Integer(), nullable=True),
    sa.Column('aircraft_pzl', sa.Integer(), nullable=True),
    sa.Column('aircraft_gru', sa.Integer(), nullable=True),
    sa.Column('aircraft_leased_helicopters', sa.Integer(), nullable=True),
    sa.Column('aircraft_leased_planes', sa.Integer(), nullable=True),
    sa.Column('aircraft_other_agencies', sa.Integer(), nullable=True),
    sa.Column('ignition_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.ForeignKeyConstraint(['ignition_id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_greece_ffa_wildfire_ignition_id', 'greece_ffa_wildfire', ['ignition_id'], unique=False)
    op.create_index('ix_greece_ffa_wildfire_incident_category', 'greece_ffa_wildfire', ['incident_category'], unique=False)
    op.create_index('ix_greece_ffa_wildfire_prefecture_name', 'greece_ffa_wildfire', ['prefecture_name'], unique=False)
    op.create_index('ix_greece_ffa_wildfire_record_number', 'greece_ffa_wildfire', ['record_number'], unique=False)
    op.create_index('ix_greece_ffa_wildfire_year', 'greece_ffa_wildfire', ['year'], unique=False)


def downgrade() -> None:
    """Revert this revision.

    The fires go before the points: ``greece_ffa_wildfire.ignition_id`` references
    ``ignition.id``, so dropping ``greece_ffa_ignition`` first would leave a
    foreign key pointing at a parent row whose child table is gone.
    """
    op.drop_index('ix_greece_ffa_wildfire_year', table_name='greece_ffa_wildfire')
    op.drop_index('ix_greece_ffa_wildfire_record_number', table_name='greece_ffa_wildfire')
    op.drop_index('ix_greece_ffa_wildfire_prefecture_name', table_name='greece_ffa_wildfire')
    op.drop_index('ix_greece_ffa_wildfire_incident_category', table_name='greece_ffa_wildfire')
    op.drop_index('ix_greece_ffa_wildfire_ignition_id', table_name='greece_ffa_wildfire')
    op.drop_table('greece_ffa_wildfire')
    op.drop_index('ix_greece_ffa_ignition_year', table_name='greece_ffa_ignition')
    op.drop_index('ix_greece_ffa_ignition_record_number', table_name='greece_ffa_ignition')
    op.drop_table('greece_ffa_ignition')
