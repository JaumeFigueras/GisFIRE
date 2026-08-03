"""add rediam match method constraint

Revision ID: b1c47d9e3f52
Revises: f3a1d8c26b74
Create Date: 2026-08-03 17:20:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c47d9e3f52'
down_revision: str | None = 'f3a1d8c26b74'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Kept in the revision rather than imported from the model, which is the rule for
#: anything a migration writes into the database: a later edit to ``MATCH_METHODS``
#: must produce a new revision altering this constraint, not change silently what an
#: old database was built with.
MATCH_METHODS = (
    "code",
    "code_reformatted",
    "code_date_mismatch",
    "geometry",
    "date_province_name",
    "date_province",
)


def upgrade() -> None:
    """Apply this revision.

    e9e992e02a11 created ``rediam_wildfire.match_method`` with **no constraint on its
    values**, and said why: the Catalan vocabulary was worked out against a dataset
    whose code took six forms over forty years, the Andalusian rules had not been
    worked out at all, and a list invented then would have been a guess frozen into
    the schema.

    They have been worked out now — see
    ``src/apps/bindings/wildfires/andalusia_rediam/bind_egif_wildfires.py`` — so this
    is the one-line revision that was promised.

    **Six values, not the Catalan eight.** ``date`` and ``date_name`` are the branches
    the Catalan cascade takes when a code carries no province, and every Andalusian
    code carries one: all 962 published features decode to one of the eight Andalusian
    INE provinces. A fire whose code did not decode is left unbound rather than bound
    on a date alone, which in a province with 40,757 *partes* would be a coin toss —
    so those two values can never be written and are not allowed.

    Nothing is backfilled and nothing can violate this on the way in: the binding
    application has not run against any database this revision will be applied to
    before it, and every existing row has a ``NULL`` method.
    """
    op.create_check_constraint(
        'ck_rediam_wildfire_match_method', 'rediam_wildfire',
        "match_method IN (" + ", ".join(f"'{method}'" for method in MATCH_METHODS) + ")",
    )


def downgrade() -> None:
    """Revert this revision.

    The bindings survive: dropping the constraint leaves every ``match_method`` where
    it is and only stops the database checking new ones.
    """
    op.drop_constraint('ck_rediam_wildfire_match_method', 'rediam_wildfire',
                       type_='check')
