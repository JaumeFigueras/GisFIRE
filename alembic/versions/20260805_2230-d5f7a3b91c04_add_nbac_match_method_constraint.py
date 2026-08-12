"""add nbac match method constraint

Revision ID: d5f7a3b91c04
Revises: a4e8c2b7d951
Create Date: 2026-08-05 22:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5f7a3b91c04'
down_revision: str | None = 'a4e8c2b7d951'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Kept in the revision rather than imported from the model, which is the rule for
#: anything a migration writes into the database: a later edit to ``MATCH_METHODS``
#: must produce a new revision altering this constraint, not change silently what an
#: old database was built with.
MATCH_METHODS = (
    "inside_agency_day",
    "inside_agency_undated",
    "inside_agency_date_mismatch",
    "inside",
    "near_agency_day",
)


def upgrade() -> None:
    """Apply this revision.

    cb6f71e0e868 created ``nbac_wildfire.match_method`` with **no constraint on its
    values**, and said why: the Canadian rules had not been worked out, the two
    datasets share no published identifier, and inventing a vocabulary then would
    have frozen a guess into the schema.

    They have been worked out now — see
    ``src/apps/bindings/wildfires/canada_nbac/bind_nfdb_wildfires.py`` — so this is
    the revision that model's docstring promised, following the Andalusian precedent
    in b1c47d9e3f52.

    **Five values, and none of them an identifier.** The Catalan vocabulary opens with
    three flavours of code match and the Andalusian with two, because in both cases a
    published identifier says the two records are the same fire. NBAC publishes
    nineteen fields in every one of its fifty-three yearly archives and not one of
    them is an agency fire number, so there is no code stage here at all: every value
    below names a geometric or temporal inference, and the vocabulary is shorter for
    exactly that reason.

    The four ``inside_*`` values rest on the NFDB point falling within the burnt
    perimeter. ``near_agency_day`` does not — it is the point being close to one, on
    the same day, from the same agency — and it is a weaker claim by a measurable
    amount rather than by assumption; see ``MATCH_METHOD_CONFIDENCE`` on the model.

    Nothing is backfilled and nothing can violate this on the way in: the binding
    application has not run against any database this revision will be applied to
    before it, and every existing row has a ``NULL`` method.
    """
    op.create_check_constraint(
        'ck_nbac_wildfire_match_method', 'nbac_wildfire',
        "match_method IN (" + ", ".join(f"'{method}'" for method in MATCH_METHODS) + ")",
    )


def downgrade() -> None:
    """Revert this revision.

    The bindings survive: dropping the constraint leaves every ``match_method`` where
    it is and only stops the database checking new ones.
    """
    op.drop_constraint('ck_nbac_wildfire_match_method', 'nbac_wildfire',
                       type_='check')
