"""add darpa wildfire

Revision ID: d5f2a91c3b48
Revises: c4d81e6b2a97
Create Date: 2026-08-02 11:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
# revision identifiers, used by Alembic.
revision: str = 'd5f2a91c3b48'
down_revision: str | None = 'c4d81e6b2a97'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``darpa_wildfire`` is the first regional perimeter table: the Catalan burnt
    area cartography, one row per fire, hanging off ``wildfire`` by joined table
    inheritance like every other provider's.

    Three things about it are worth reading before changing it.

    **The unique key is ``(code, fire_date)``, not ``code``.** ``CODI_FINAL`` is not
    an identifier: ``303/22N`` names a fire in Lleida on 19 June 2022 and another in
    Figueres on 7 July. A unique constraint on the code alone would have forced two
    fires into one row at import time and there would have been nothing left to
    notice it by. The pair is unique across the whole 1986-2024 archive — 860 of
    them for 859 codes — and its index is what serves lookups by code as well.

    **``egif_wildfire_id`` is created here and filled by nothing.** It is the link
    to the Spanish *parte* for the same fire, and the import leaves it ``NULL`` on
    every row. Creating it now means the application that eventually matches the
    two datasets is an ``UPDATE`` rather than another migration; what that
    application will join on is deliberately not decided by this table. See
    ``src/providers/catalonia_darpa/__init__.py``.

    It is a plain nullable FK rather than an association table because the ten-digit
    Catalan codes are shaped exactly like an EGIF ``report_number``, which points at
    one *parte* per perimeter. If the matching exercise finds otherwise, replacing
    it with a link table is a later revision and a smaller change than having
    guessed the other way round.

    **The published EPSG:25831 geometry is kept alongside the EPSG:4326 one** on the
    parent ``wildfire`` row, exactly as for ICNF, so this table gets a spatial index
    of its own.
    """
    op.create_geospatial_table('darpa_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('fire_date', sa.Date(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('municipality_name', sa.String(), nullable=False),
    sa.Column('part_count', sa.Integer(), nullable=False),
    sa.Column('egif_wildfire_id', sa.Integer(), nullable=True),
    sa.Column('perimeter_etrs89_utm31n', Geometry(geometry_type='MULTIPOLYGON', srid=25831, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=True), nullable=True),
    sa.ForeignKeyConstraint(['egif_wildfire_id'], ['egif_wildfire.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'fire_date', name='uq_darpa_wildfire_code_fire_date')
    )
    op.create_index('ix_darpa_wildfire_egif_wildfire_id', 'darpa_wildfire', ['egif_wildfire_id'], unique=False)
    op.create_index('ix_darpa_wildfire_source_layer', 'darpa_wildfire', ['source_layer'], unique=False)
    op.create_index('ix_darpa_wildfire_year', 'darpa_wildfire', ['year'], unique=False)
    op.create_geospatial_index('idx_darpa_wildfire_perimeter_etrs89_utm31n', 'darpa_wildfire', ['perimeter_etrs89_utm31n'], unique=False, postgresql_using='gist', postgresql_ops={})


def downgrade() -> None:
    """Revert this revision."""
    op.drop_geospatial_index('idx_darpa_wildfire_perimeter_etrs89_utm31n', table_name='darpa_wildfire', postgresql_using='gist', column_name='perimeter_etrs89_utm31n')
    op.drop_index('ix_darpa_wildfire_year', table_name='darpa_wildfire')
    op.drop_index('ix_darpa_wildfire_source_layer', table_name='darpa_wildfire')
    op.drop_index('ix_darpa_wildfire_egif_wildfire_id', table_name='darpa_wildfire')
    op.drop_geospatial_table('darpa_wildfire')
