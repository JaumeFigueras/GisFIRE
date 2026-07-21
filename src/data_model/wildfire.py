#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wildfire model.

A ``Wildfire`` is a fire event as reported by a :class:`~src.data_model.
data_provider.DataProvider`: when it started, when it was extinguished and the
area it burnt, stored as a PostGIS ``MULTIPOLYGON`` in EPSG:4326.

This is the *generic* model. Each provider publishes its own extra attributes
(its own identifier included) through a subclass, using joined table inheritance
on :attr:`Wildfire.type`.

Dates: instant plus zone
------------------------

Providers do not agree on how they report time. Some publish an instant in UTC,
some a local wall-clock time, some — GWIS among them — a bare date whose hours
are implied to be local midnight. Storing each as published would make two
agencies' data incomparable, so the project fixes one rule and every import
obeys it:

* :attr:`start_date_time` and :attr:`end_date_time` are ``timestamptz``, which
  in PostgreSQL is *an instant* — internally always UTC, with no zone attached
  to the row. Converting to it is the importer's job, done once, so any two
  events from any two providers can be compared, sorted and range-scanned
  against an index with no per-query conversion.
* :attr:`time_zone` records the IANA zone that instant was derived *from*. It is
  provenance, not a second version of the truth: it is what makes the original
  local reading recoverable, since the ``timestamptz`` alone cannot say what
  wall-clock time the provider actually printed.

So a GWIS fire starting on 2021-07-29 in California is stored as the instant
``2021-07-29T07:00:00Z`` with ``time_zone = "America/Los_Angeles"``, and the
published reading comes back out with
``SELECT start_date_time AT TIME ZONE time_zone``. Note that ``AT TIME ZONE``
resolves daylight saving from the date itself, which is why the zone is kept as
a name rather than as a fixed offset.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary


class Wildfire(Base):
    """A wildfire event reported by a data provider.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. This is the *local* GisFIRE
        identifier; a provider's own identifier belongs to the corresponding
        subclass.
    type : str
        Polymorphic discriminator, ``"wildfire"`` for the generic model.
    data_provider_id : int
        Foreign key to :class:`~src.data_model.data_provider.DataProvider`, the
        provider this wildfire was obtained from.
    data_provider : DataProvider
        The provider this wildfire was obtained from.
    start_date_time : datetime.datetime
        Timezone-aware instant the wildfire started.
    end_date_time : datetime.datetime or None
        Timezone-aware instant the wildfire was extinguished, or ``None`` while
        it is still burning or if the provider does not report it.
    time_zone : str or None
        IANA name of the zone the two instants above were derived from
        (``"America/Los_Angeles"``), or ``None`` when the provider published an
        instant directly and no conversion was involved. See the module
        docstring.
    perimeter : geoalchemy2.elements.WKBElement or None
        Burnt area as a ``MULTIPOLYGON`` in EPSG:4326 (WGS 84), or ``None`` if
        the provider reports no perimeter (yet).
    admin_boundary_id : int or None
        Foreign key to the :class:`~src.data_model.geography.admin_boundary.
        AdminBoundary` the fire burnt in, resolved once at import time by spatial
        join rather than per query. ``None`` when the perimeter matches no
        imported boundary — because the boundaries have not been imported, or
        because the fire lies outside all of them.
    admin_boundary : AdminBoundary or None
        The administrative division the fire burnt in.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "wildfire"

    __table_args__ = (
        Index("ix_wildfire_admin_boundary_id", "admin_boundary_id"),
        Index("ix_wildfire_start_date_time", "start_date_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    start_date_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String, nullable=True)
    perimeter: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    admin_boundary_id: Mapped[int | None] = mapped_column(
        ForeignKey(AdminBoundary.id), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_provider: Mapped[DataProvider] = relationship()
    admin_boundary: Mapped[AdminBoundary | None] = relationship()

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "wildfire",
    }

    def __repr__(self) -> str:
        return f"Wildfire(id={self.id!r}, start_date_time={self.start_date_time!r})"
