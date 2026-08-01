#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAOP administrative boundary model.

One *distrito*, *município* or *freguesia* of the Carta Administrativa Oficial de
Portugal. See :mod:`src.providers.caop` for what the dataset is, why GisFIRE
imports it and how its two hierarchies are reconciled.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers.caop import KINDS

_KINDS_SQL = ", ".join(f"'{kind}'" for kind in KINDS)


class CaopAdminBoundary(AdminBoundary):
    """An administrative division of Portugal as published in the CAOP.

    Uses joined table inheritance: the columns every boundary has — the code, the
    name, the level, the parent and the polygon — live on ``admin_boundary``, and
    only what the CAOP adds is stored here.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.geography.admin_boundary.AdminBoundary.id`.
    edition : str
        Year of the CAOP edition this boundary was published in, ``"2025"``. It
        also appears in the provider's ``product``, which is what actually keeps
        editions apart (see :mod:`src.providers.caop`); it is repeated here so
        that filtering or grouping by edition needs no join.
    kind : str
        Which division this is: :data:`~src.providers.caop.KIND_DISTRITO`,
        :data:`~src.providers.caop.KIND_MUNICIPIO` or
        :data:`~src.providers.caop.KIND_FREGUESIA`. Redundant with the inherited
        ``level``, and kept anyway: ``level`` is a normalised depth shared with
        every other provider, while this names the division in the terms Portugal
        uses, which is what a query about parishes is actually asking for.
    name_simplified : str or None
        The parish's *designação simplificada* — the short form of a name that is
        often a compound of the settlements it merged in 2013, so
        ``"União das Freguesias de Angeja e Frossos"`` is simplified to
        ``"Angeja e Frossos"``. Published for *freguesias* only, and differs from
        the full name for 635 of the 3 259; ``None`` at the other two levels.

        Useful when matching against the ICNF's
        :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.parish_name`, which does
        not consistently use either form.
    nuts1_code : str or None
        INE code of the NUTS 1 region — ``"1"`` mainland, ``"2"`` Azores, ``"3"``
        Madeira. Published on the *distritos* layer only, so ``None`` below that
        level; the region itself is still named by :attr:`nuts1_name` everywhere.
    nuts1_name : str or None
        NUTS 1 region: *Continente*, *Região Autónoma dos Açores* or *Região
        Autónoma da Madeira*.
    nuts2_name : str or None
        NUTS 2 region. ``None`` on *distritos*, which the CAOP does not assign one
        to — and could not, since the two hierarchies cross (see
        :mod:`src.providers.caop`).
    nuts3_code : str or None
        INE code of the NUTS 3 region, three characters, ``"191"`` or ``"11A"``.
        This is the national code without the ``PT`` prefix Eurostat uses, so
        ``"111"`` here is Eurostat's ``PT111``. ``None`` on *distritos*.
    nuts3_name : str or None
        NUTS 3 region, e.g. *Região de Aveiro*. ``None`` on *distritos*. This is
        what :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.nuts3_name` can be
        matched against.
    area_ha : float
        Area in hectares, as the DGT computed it on the national grid. Kept as
        published rather than recomputed from :attr:`geometry`: the stored polygon
        is a reprojection to EPSG:4326, and measuring it would give a number that
        is close to but not the provider's.
    perimeter_km : int
        Perimeter in kilometres, as published. Rounded to the kilometre at the
        source, which is why it is an integer.

    Notes
    -----
    The source denormalises each row's ancestry onto it: a *freguesia* record
    repeats its *município* and *distrito* names, and a *distrito* record counts
    the *municípios* and *freguesias* below it. None of that is stored. The tree
    already holds it, the two agree exactly — checked over all 3 596 boundaries,
    with no disagreement — and a copy that can drift is worse than a join.

    What *is* kept from the denormalised columns is the NUTS chain, because that
    is the one thing the tree cannot express.
    """

    __tablename__ = "caop_admin_boundary"

    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS_SQL})", name="ck_caop_admin_boundary_kind"),
        Index("ix_caop_admin_boundary_kind", "kind"),
        Index("ix_caop_admin_boundary_edition", "edition"),
        Index("ix_caop_admin_boundary_nuts3_code", "nuts3_code"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(AdminBoundary.id), primary_key=True)
    edition: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    name_simplified: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts1_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts1_name: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts2_name: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts3_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts3_name: Mapped[str | None] = mapped_column(String, nullable=True)
    area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    perimeter_km: Mapped[int] = mapped_column(Integer, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "caop_admin_boundary",
    }

    def __repr__(self) -> str:
        return f"CaopAdminBoundary(kind={self.kind!r}, source_id={self.source_id!r}, name={self.name!r})"
