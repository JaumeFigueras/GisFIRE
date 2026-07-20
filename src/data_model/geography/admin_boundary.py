#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Administrative boundary model.

An ``AdminBoundary`` is an administrative division — a country, a region, a
province, a municipality — stored as a PostGIS ``MULTIPOLYGON`` in EPSG:4326.
Boundaries nest: Spain contains Catalonia, which contains Girona, which contains
Osor. The nesting is an adjacency list (:attr:`AdminBoundary.parent_id` pointing
back at this same table), so a branch can be as deep as its source describes
without the model having to fix a number of levels in advance.

This is the *generic* model. Each source publishes its own identifiers and
metadata through a subclass, using joined table inheritance on
:attr:`AdminBoundary.type`.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.data_model.data_provider import DataProvider


class AdminBoundary(Base):
    """An administrative division, as published by a data provider.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. This is the *local* GisFIRE
        identifier; a source's own identifier belongs to the corresponding
        subclass.
    type : str
        Polymorphic discriminator, ``"admin_boundary"`` for the generic model.
    data_provider_id : int
        Foreign key to :class:`~src.data_model.data_provider.DataProvider`, the
        provider this boundary was obtained from.
    data_provider : DataProvider
        The provider this boundary was obtained from.
    source_id : str
        The identifier the provider gives this boundary (OCHA's ``adm0_id``, an
        OSM relation id, ...), unique within the provider. Kept as text so a
        change in the provider's identifier format cannot break imports, and used
        to recognise a boundary already imported.
    level : int
        Depth in the administrative hierarchy, ``0`` for a country and one more
        for each subdivision below it (Spain 0, Catalonia 1, Girona 2, Osor 3).

        This is a *normalised* depth, deliberately not the level number the
        source uses. OSM's ``admin_level`` tag, for one, is neither contiguous
        nor comparable across countries — Spain tags its autonomous communities
        4 and its provinces 6, France tags its departments 6 and its
        arrondissements 7 — so it cannot be queried across countries. Sources
        that have a level number of their own keep it on their subclass.
    name : str
        Name of the division in its own language, as the provider spells it
        (``"Catalunya"``, not ``"Cataluña"``).
    name_en : str or None
        English name, if the provider supplies one.
    parent_id : int or None
        Foreign key to the boundary one level up, or ``None`` for a boundary with
        no parent in the database — a country, or any boundary whose ancestors
        have not been imported.
    parent : AdminBoundary or None
        The boundary one level up.
    children : list of AdminBoundary
        The boundaries one level down.
    geometry : geoalchemy2.elements.WKBElement
        The division's area as a ``MULTIPOLYGON`` in EPSG:4326 (WGS 84).
        ``MULTIPOLYGON`` rather than ``POLYGON`` because administrative divisions
        routinely have several parts: islands, enclaves and exclaves.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    Resolving which boundary contains a wildfire is a spatial join, not a foreign
    key, and country polygons are large enough that repeating it per query is
    wasteful. Do it once, at import time, and store the resulting boundary id on
    the event.
    """

    __tablename__ = "admin_boundary"

    __table_args__ = (
        UniqueConstraint("data_provider_id", "source_id", name="uq_admin_boundary_provider_source"),
        Index("ix_admin_boundary_parent_id", "parent_id"),
        Index("ix_admin_boundary_level", "level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("admin_boundary.id"), nullable=True)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_provider: Mapped[DataProvider] = relationship()
    parent: Mapped[AdminBoundary | None] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list[AdminBoundary]] = relationship(back_populates="parent")

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "admin_boundary",
    }

    def __repr__(self) -> str:
        return f"AdminBoundary(id={self.id!r}, level={self.level!r}, name={self.name!r})"
