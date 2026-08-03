"""add darpa egif match provenance

Revision ID: b93f7c15ea20
Revises: a7e4c02f9d16
Create Date: 2026-08-02 18:10:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b93f7c15ea20'
down_revision: str | None = 'a7e4c02f9d16'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Kept in the revision rather than imported from the model, which is the rule for
#: anything a migration writes into the database: a later edit to
#: ``MATCH_METHODS`` must produce a new revision altering this constraint, not
#: change silently what an old database was built with.
MATCH_METHODS = (
    "code",
    "code_reformatted",
    "code_date_mismatch",
    "geometry",
    "date_province_name",
    "date_name",
    "date_province",
    "date",
)


def upgrade() -> None:
    """Apply this revision.

    ``darpa_wildfire.egif_wildfire_id`` has existed since d5f2a91c3b48 and nothing
    has ever written it. This adds the three columns that make it *readable* once
    something does.

    The link on its own is not enough, and that is the whole point of this
    revision. About 70% of the bindings come from an identifier — the Catalan
    ``CODI_FINAL`` **is** the EGIF ``report_number``, literally from 1997 on and
    rearranged before that — while the rest come from a date, a province and a
    municipality name, which is a good rule and not a certainty. Those are
    different kinds of claim, and an analysis that could not tell them apart would
    be asserting a precision a third of its rows do not have.

    ``code_reformatted`` is in the list because four of the six published Catalan
    code formats are the EGIF report number rearranged rather than absent — see
    ``src/providers/catalonia_darpa/__init__.py``. It is a separate value from
    ``code`` because it rests on a reading of a format rather than on string
    equality.

    ``match_method`` says which rule fired, ``match_confidence`` orders them for the
    ``WHERE`` clause people actually write, and ``matched_at`` dates the binding —
    ``updated_at`` cannot, because it moves for any edit, and what matters here is
    whether the binding predates the last EGIF import.

    Two check constraints:

    * ``match_method`` is one of the eight known rules, so a typo in a future
      binding application is refused rather than stored.
    * the method and the link are all-or-nothing. A link with no method would be
      unattributable; a method with no link would be a claim about nothing.

    No index on ``match_method``: seven values over 860 rows is not a selectivity a
    query planner would ever use one for. ``egif_wildfire_id`` already has its own,
    from d5f2a91c3b48.

    Nothing is backfilled. Every existing row has a ``NULL`` link, so the
    all-or-nothing constraint holds on the way in with no data migration at all.
    """
    op.add_column('darpa_wildfire', sa.Column('match_method', sa.String(), nullable=True))
    op.add_column('darpa_wildfire', sa.Column('match_confidence', sa.Float(), nullable=True))
    op.add_column('darpa_wildfire',
                  sa.Column('matched_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        'ck_darpa_wildfire_match_method', 'darpa_wildfire',
        "match_method IN (" + ", ".join(f"'{method}'" for method in MATCH_METHODS) + ")",
    )
    op.create_check_constraint(
        'ck_darpa_wildfire_match_method_with_link', 'darpa_wildfire',
        "(egif_wildfire_id IS NULL) = (match_method IS NULL)",
    )


def downgrade() -> None:
    """Revert this revision.

    The constraints go first: dropping a column a check constraint names would fail
    otherwise. Any binding recorded is lost with the columns, which is what
    reverting the revision that introduced them means — the links themselves survive
    in ``egif_wildfire_id``, unattributable.
    """
    op.drop_constraint('ck_darpa_wildfire_match_method_with_link', 'darpa_wildfire',
                       type_='check')
    op.drop_constraint('ck_darpa_wildfire_match_method', 'darpa_wildfire', type_='check')
    op.drop_column('darpa_wildfire', 'matched_at')
    op.drop_column('darpa_wildfire', 'match_confidence')
    op.drop_column('darpa_wildfire', 'match_method')
