"""add rediam wildfire

Revision ID: e9e992e02a11
Revises: c07b48e93a51
Create Date: 2026-08-03 14:34:27.905987+00:00
"""
from __future__ import annotations

from typing import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op
from geoalchemy2 import Geometry
# revision identifiers, used by Alembic.
revision: str = 'e9e992e02a11'
down_revision: str | None = 'c07b48e93a51'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision.

    ``rediam_wildfire`` is the second regional perimeter table — the Andalusian burnt
    area cartography, one row per fire, hanging off ``wildfire`` by joined table
    inheritance like every other provider's — and ``rediam_ignition`` is the point
    the service publishes for four of its years, hanging off ``ignition`` the same
    way.

    Four things about them are worth reading before changing either.

    **The unique key is ``(code, fire_date)``, not ``code``.** Here the code really is
    an identifier — ``CODIGO`` is the EGIF ``report_number``, plainly from 2008 and
    behind an ``IIFF`` prefix in 2025, and the 907 fires have 907 distinct report
    numbers — so a unique constraint on the code alone would in fact hold today. The
    pair is used anyway, because it is the key ``darpa_wildfire`` uses and a query
    over both regional datasets should not need two different join shapes.

    **``ignition_id`` is a link to a row, not two coordinate columns.** ``X_INIC`` and
    ``Y_INIC`` are published in the yearly layers of 2021-2024 and nowhere else, and
    the published point is frequently *outside* the published perimeter — 88 of the
    201 are inside. Two observations that disagree belong in two rows; see
    ``src/providers/andalusia_rediam/ignition.py``.

    **``egif_wildfire_id`` is created here and filled by nothing**, exactly as
    ``darpa_wildfire``'s was, so that the application that eventually matches the two
    datasets is an ``UPDATE`` rather than another migration. ``match_method``,
    ``match_confidence`` and ``matched_at`` come with it, because a link with no
    account of how it was made is unusable — and the all-or-nothing check constraint
    holds trivially on the way in, every row having a NULL link.

    What this revision deliberately does **not** create is a check constraint on the
    *values* of ``match_method``. ``darpa_wildfire`` has one, listing eight rules
    worked out against a dataset whose code took six forms over forty years. The
    Andalusian rules have not been worked out at all, and a list invented now would
    be a guess frozen into the schema; adding the constraint later is a one-line
    revision.

    **The published EPSG:25830 geometry is kept alongside the EPSG:4326 one** on the
    parent ``wildfire`` row, as for ICNF and DARPA, so this table gets a spatial index
    of its own. 25830 and not the 3042 GDAL reads off the ``.prj``: same projection,
    but 3042 declares a northing-easting axis order the files do not follow.
    """
    op.create_table('rediam_ignition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('fire_date', sa.Date(), nullable=False),
    sa.Column('utm_x', sa.Float(), nullable=False),
    sa.Column('utm_y', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'fire_date', name='uq_rediam_ignition_code_fire_date')
    )
    op.create_geospatial_table('rediam_wildfire',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_layer', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('fire_date', sa.Date(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('municipality_name', sa.String(), nullable=False),
    sa.Column('province_name', sa.String(), nullable=False),
    sa.Column('part_count', sa.Integer(), nullable=False),
    sa.Column('area_ha_wooded', sa.Float(), nullable=True),
    sa.Column('area_ha_scrub', sa.Float(), nullable=True),
    sa.Column('area_ha_grassland', sa.Float(), nullable=True),
    sa.Column('ignition_id', sa.Integer(), nullable=True),
    sa.Column('egif_wildfire_id', sa.Integer(), nullable=True),
    sa.Column('match_method', sa.String(), nullable=True),
    sa.Column('match_confidence', sa.Float(), nullable=True),
    sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('perimeter_etrs89_utm30n', Geometry(geometry_type='MULTIPOLYGON', srid=25830, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.CheckConstraint('(egif_wildfire_id IS NULL) = (match_method IS NULL)', name='ck_rediam_wildfire_match_method_with_link'),
    sa.ForeignKeyConstraint(['egif_wildfire_id'], ['egif_wildfire.id'], ),
    sa.ForeignKeyConstraint(['id'], ['wildfire.id'], ),
    sa.ForeignKeyConstraint(['ignition_id'], ['ignition.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'fire_date', name='uq_rediam_wildfire_code_fire_date')
    )
    op.create_geospatial_index('idx_rediam_wildfire_perimeter_etrs89_utm30n', 'rediam_wildfire', ['perimeter_etrs89_utm30n'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_rediam_wildfire_egif_wildfire_id', 'rediam_wildfire', ['egif_wildfire_id'], unique=False)
    op.create_index('ix_rediam_wildfire_ignition_id', 'rediam_wildfire', ['ignition_id'], unique=False)
    op.create_index('ix_rediam_wildfire_source_layer', 'rediam_wildfire', ['source_layer'], unique=False)
    op.create_index('ix_rediam_wildfire_year', 'rediam_wildfire', ['year'], unique=False)


def downgrade() -> None:
    """Revert this revision.

    The perimeters go before the points: ``rediam_wildfire.ignition_id`` references
    ``ignition.id``, so dropping ``rediam_ignition`` first would leave a foreign key
    pointing at a parent row whose child table is gone.
    """
    op.drop_index('ix_rediam_wildfire_year', table_name='rediam_wildfire')
    op.drop_index('ix_rediam_wildfire_source_layer', table_name='rediam_wildfire')
    op.drop_index('ix_rediam_wildfire_ignition_id', table_name='rediam_wildfire')
    op.drop_index('ix_rediam_wildfire_egif_wildfire_id', table_name='rediam_wildfire')
    op.drop_geospatial_index('idx_rediam_wildfire_perimeter_etrs89_utm30n', table_name='rediam_wildfire', postgresql_using='gist', column_name='perimeter_etrs89_utm30n')
    op.drop_geospatial_table('rediam_wildfire')
    op.drop_table('rediam_ignition')
