#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US Census Bureau administrative boundary model.

One state or county of the Census Bureau's Cartographic Boundary Files. See
:mod:`src.providers.united_states_census` for what the files are, how their codes
nest and what is left out of them.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers.united_states_census import KINDS

_KINDS_SQL = ", ".join(f"'{kind}'" for kind in KINDS)


class CensusAdminBoundary(AdminBoundary):
    """A state or county of the United States, as published by the Census Bureau.

    Uses joined table inheritance: the columns every boundary has — the code, the
    name, the level, the parent and the polygon — live on ``admin_boundary``, and
    only what the Census adds is stored here. The inherited ``source_id`` is the
    ``GEOID`` (the FIPS code), ``name`` and ``name_en`` are both its ``NAME``.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.geography.admin_boundary.AdminBoundary.id`.
    edition : str
        Year of the Cartographic Boundary Files this boundary came from,
        ``"2025"``. It also appears in the provider's ``product``, which is what
        keeps editions apart; it is repeated here so that filtering or grouping by
        edition needs no join.
    kind : str
        :data:`~src.providers.united_states_census.KIND_STATE` or
        :data:`~src.providers.united_states_census.KIND_COUNTY`. Redundant with the
        inherited ``level``, and kept anyway, as for the IGN and the CAOP:
        ``level`` is a depth shared with every other provider, this names the
        division in the source's terms.
    lsad : str
        The published ``LSAD`` code, what kind of entity this is: ``00`` for every
        state, ``06`` County, ``04`` Borough, ``15`` Parish, ``25`` independent
        city, ... (the full list is in :mod:`src.providers.united_states_census`).
        It tells apart Baltimore County and the city of Baltimore, which share a
        name.

    Notes
    -----
    The ``GEOID`` is not stored again: it is ``source_id``. Neither are
    ``GEOIDFQ`` (the ``GEOID`` behind a fixed prefix), ``STATEFP`` and
    ``COUNTYFP`` (its two halves), ``STUSPS`` and ``STATE_NAME`` (the parent's),
    ``NAMELSAD`` (the name followed by the words of :attr:`lsad`), the GNIS codes
    (``STATENS``, ``COUNTYNS``) or the land and water areas (``ALAND``,
    ``AWATER``), which the polygon supersedes.
    """

    __tablename__ = "census_admin_boundary"

    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS_SQL})", name="ck_census_admin_boundary_kind"),
        Index("ix_census_admin_boundary_kind", "kind"),
        Index("ix_census_admin_boundary_edition", "edition"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(AdminBoundary.id), primary_key=True)
    edition: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    lsad: Mapped[str] = mapped_column(String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "census_admin_boundary",
    }

    def __repr__(self) -> str:
        return (f"CensusAdminBoundary(kind={self.kind!r}, source_id={self.source_id!r}, "
                f"name={self.name!r})")
