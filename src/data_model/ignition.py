#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ignition model.

An ``Ignition`` is where and when a fire started, as reported by a
:class:`~src.data_model.data_provider.DataProvider`: a point in EPSG:4326 and the
instant it ignited.

This is the *generic* model. Each provider publishes its own extra attributes
(its own identifier included) through a subclass, using joined table inheritance
on :attr:`Ignition.type`, exactly as :class:`~src.data_model.wildfire.Wildfire`
does.

Why it is a model of its own
----------------------------

A perimeter and an ignition are different observations and not every provider
publishes both. Some publish only detections — a point and a time, with no burnt
area ever attached — and a provider that publishes both may publish them at
different times or with different coverage. Modelling the ignition as an
attribute of a wildfire would leave nowhere to put the first kind and would make
"every ignition in this region last year" a query over a table of perimeters.

An ignition therefore stands alone. Where a provider does publish both, and the
two can be matched, the link belongs on the provider's subclasses, which are the
only place that knows what identifies a fire in that dataset.

Dates: instant plus zone
------------------------

:attr:`date_time` follows the same rule as
:attr:`~src.data_model.wildfire.Wildfire.start_date_time`, for the same reasons —
it is a ``timestamptz``, which in PostgreSQL is *an instant*, and
:attr:`time_zone` records the IANA zone it was derived from so that the reading
the provider actually published stays recoverable. See
:mod:`src.data_model.wildfire` for the full argument.
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


class Ignition(Base):
    """The point and instant at which a fire started, as reported by a provider.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. This is the *local* GisFIRE
        identifier; a provider's own identifier belongs to the corresponding
        subclass.
    type : str
        Polymorphic discriminator, ``"ignition"`` for the generic model.
    data_provider_id : int
        Foreign key to :class:`~src.data_model.data_provider.DataProvider`, the
        provider this ignition was obtained from.
    data_provider : DataProvider
        The provider this ignition was obtained from.
    geometry : geoalchemy2.elements.WKBElement
        Where the fire started, as a ``POINT`` in EPSG:4326 (WGS 84).
    date_time : datetime.datetime
        Timezone-aware instant the fire ignited. A provider publishing a bare
        date means local midnight, and the importer resolves it, exactly as it
        does for a wildfire's start.
    time_zone : str or None
        IANA name of the zone :attr:`date_time` was derived from
        (``"America/Los_Angeles"``), or ``None`` when the provider published an
        instant directly and no conversion was involved.
    admin_boundary_id : int or None
        Foreign key to the :class:`~src.data_model.geography.admin_boundary.
        AdminBoundary` the fire started in, resolved once at import time by
        spatial join rather than per query. ``None`` when the point matches no
        imported boundary — because the boundaries have not been imported, or
        because the point lies outside all of them.
    admin_boundary : AdminBoundary or None
        The administrative division the fire started in.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    A point is unambiguous about its country in a way a perimeter is not: it is
    in exactly one boundary or in none, so :attr:`admin_boundary_id` needs no
    tie-break rule of the kind the GWIS wildfire import has to apply.
    """

    __tablename__ = "ignition"

    __table_args__ = (
        Index("ix_ignition_admin_boundary_id", "admin_boundary_id"),
        Index("ix_ignition_date_time", "date_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    date_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_zone: Mapped[str | None] = mapped_column(String, nullable=True)
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
        "polymorphic_identity": "ignition",
    }

    def __repr__(self) -> str:
        return f"Ignition(id={self.id!r}, date_time={self.date_time!r})"
