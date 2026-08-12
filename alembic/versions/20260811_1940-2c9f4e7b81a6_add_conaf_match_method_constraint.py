"""add conaf match method constraint

Revision ID: 2c9f4e7b81a6
Revises: 9d4a06e3f2b8
Create Date: 2026-08-11 19:40:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2c9f4e7b81a6'
down_revision: str | None = '9d4a06e3f2b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: The methods
#: :mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires` can
#: bind a perimeter to a report by, strongest first.
#:
#: Kept in the revision rather than imported from
#: :data:`src.providers.chile_conaf_magnitud.MATCH_METHODS`, on the rule the whole
#: ``alembic/versions`` directory follows: a migration states the schema as it was
#: at this revision, so a later edit to that tuple must produce a *new* revision
#: altering this constraint rather than silently changing what this one did.
MATCH_METHODS = (
    "number_region_name_season",
    "number_region_inside_season",
    "number_region_season",
    "number_name_season",
    "name_season_inside",
    "name_season",
    "inside_single",
    "near_single",
)


def upgrade() -> None:
    """Apply this revision.

    Constrains ``conaf_magnitud_wildfire.match_method`` to the six rules the binder
    can bind by, now that the binder exists and they are known.

    Revision ``268b915dce92`` created the column without this and with only
    ``ck_conaf_magnitud_wildfire_match_method_with_link``, which says a link and its
    explanation arrive together. That one needed no vocabulary; this one is the
    vocabulary, and writing it before the application that produces it would have
    been a guess — the same reason ``d5f7a3b91c04`` came after NBAC's binder rather
    than with NBAC's tables.

    The six are a ladder, and the order in :data:`MATCH_METHODS` is the order the
    binder prefers them in. The ``CHECK`` does not know that: it accepts any of the
    six on any row, because which rule fired is a fact about one perimeter and not
    something the schema can rank.
    """
    op.create_check_constraint(
        "ck_conaf_magnitud_wildfire_match_method",
        "conaf_magnitud_wildfire",
        "match_method IS NULL OR match_method IN ("
        + ", ".join(f"'{method}'" for method in MATCH_METHODS) + ")",
    )


def downgrade() -> None:
    """Revert this revision.

    Drops the vocabulary constraint. ``match_method`` keeps its
    ``..._match_method_with_link`` ``CHECK``, so a downgraded schema still refuses an
    unexplained link — it just stops caring what the explanation says.
    """
    op.drop_constraint(
        "ck_conaf_magnitud_wildfire_match_method",
        "conaf_magnitud_wildfire",
        type_="check",
    )
