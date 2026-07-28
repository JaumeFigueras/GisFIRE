#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IGN administrative boundary model.

One *comunidad autónoma*, *provincia* or *municipio* of the Base de Datos de
Divisiones Administrativas de España. See :mod:`src.providers.ign` for what the
dataset is, how its codes nest and what is left out of it.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers.ign import KINDS

_KINDS_SQL = ", ".join(f"'{kind}'" for kind in KINDS)


class IgnAdminBoundary(AdminBoundary):
    """An administrative division of Spain as published by the IGN.

    Uses joined table inheritance: the columns every boundary has — the code, the
    name, the level, the parent and the polygon — live on ``admin_boundary``, and
    only what the BDDAE adds is stored here.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.geography.admin_boundary.AdminBoundary.id`.
    edition : str
        Label of the BDDAE publication this boundary came from, ``"2026"``. It
        also appears in the provider's ``product``, which is what actually keeps
        editions apart (see :mod:`src.providers.ign`); it is repeated here so that
        filtering or grouping by edition needs no join.

        Nothing in the published files states it, so it is whatever the import was
        told — unlike the CAOP, where the file names carry the year and can be
        checked against it.
    kind : str
        Which division this is: :data:`~src.providers.ign.KIND_COMUNIDAD_AUTONOMA`,
        :data:`~src.providers.ign.KIND_PROVINCIA`,
        :data:`~src.providers.ign.KIND_MUNICIPIO` or, only when the import was
        asked for them, :data:`~src.providers.ign.KIND_TERRITORIO`. Redundant with
        the inherited ``level`` for the first three, and kept anyway: ``level`` is
        a normalised depth shared with every other provider, while this names the
        division in the terms Spain uses. For the fourth it is not redundant at
        all — a *territorio* is stored at the same level as a *municipio* and is
        not one.
    ine_code : str or None
        The INE five-digit municipal code, ``"26145"``. It is the last five digits
        of the inherited ``source_id``, but it belongs to a different numbering
        system that happens to be embedded there, and it is what Spanish
        statistical sources — the INE's own tables, the EGIF wildfire statistics —
        join on. ``None`` above the municipal level, where those digits are
        padding.

        Text, not a number: codes such as ``"01001"`` would lose their leading
        zero.
    nuts1_code : str or None
        NUTS 1 group, ``"ES2"``. ``None`` for the excluded territories, which the
        IGN gives ``"0"``.
    nuts2_code : str or None
        NUTS 2 region, ``"ES23"``. Maps one-to-one onto the *comunidad autónoma*.
    nuts3_code : str or None
        NUTS 3 region, ``"ES230"``. Published on *municipios* only — the IGN leaves
        it empty at both levels above, so it is ``None`` there rather than derived.

        It nests inside the *provincia* rather than cutting across it, unlike its
        Portuguese counterpart: it equals the province except in the three island
        provinces, which it splits one region per island. See
        :mod:`src.providers.ign`.

    Notes
    -----
    Two published columns are deliberately not stored. ``INSPIREID`` is exactly
    :data:`~src.providers.ign.INSPIRE_ID_PREFIX` followed by the ``NATCODE`` in
    every one of the 8 293 rows, so it carries nothing ``source_id`` does not.
    ``NATLEV`` is the INSPIRE codelist URL for the level, one constant per layer,
    which :attr:`kind` already says in a form that can be queried.

    ``COUNTRY`` is ``"ES"`` throughout and is likewise dropped: the provider says
    which country this is.
    """

    __tablename__ = "ign_admin_boundary"

    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS_SQL})", name="ck_ign_admin_boundary_kind"),
        Index("ix_ign_admin_boundary_kind", "kind"),
        Index("ix_ign_admin_boundary_edition", "edition"),
        Index("ix_ign_admin_boundary_ine_code", "ine_code"),
        Index("ix_ign_admin_boundary_nuts3_code", "nuts3_code"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(AdminBoundary.id), primary_key=True)
    edition: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    ine_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts1_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts2_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts3_code: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "ign_admin_boundary",
    }

    def __repr__(self) -> str:
        return f"IgnAdminBoundary(kind={self.kind!r}, source_id={self.source_id!r}, name={self.name!r})"
