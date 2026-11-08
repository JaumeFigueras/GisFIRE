#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightning model.

A ``Lightning`` is one electrical discharge located by a lightning-detection
network operated by a :class:`~src.data_model.data_provider.DataProvider`: where
and when it was detected, its peak current and whether it reached the ground.

This is the *generic* model. Each provider publishes its own extra attributes
(its own identifiers, its location-quality measures, the coordinate in the CRS it
was published in) through a subclass, using joined table inheritance on
:attr:`Lightning.type`, exactly as :class:`~src.data_model.wildfire.Wildfire` and
:class:`~src.data_model.ignition.Ignition` do.

A row is a stroke, not a flash
------------------------------

Detection networks locate *strokes* — the individual return strokes — and group
them into *flashes*, a flash being the strokes sharing one channel within a
second or so. A row here is one stroke. Grouping strokes into flashes is each
network's own algorithm, so the flash a stroke belongs to is provider data and
lives on the subclass.

What is generic and what is not
-------------------------------

Almost every detection network reports, for each stroke, its **peak current**
and whether it was **cloud-to-ground** or intra-cloud, so both are here. Both are
nullable, because a provider that does not report them must not have to invent
them. Everything that describes how well a stroke
was located — sensors, chi², the confidence ellipse — is network specific and
belongs to the subclass.

Dates: an instant, no zone
--------------------------

Unlike :attr:`~src.data_model.wildfire.Wildfire.start_date_time`,
:attr:`date_time` has no ``time_zone`` companion. A detection network
timestamps a stroke with a GPS clock to the microsecond, and publishes it as an
instant in UTC; there is no local wall-clock reading to keep recoverable, so
there is nothing to record about a conversion. The column is still a
``timestamptz``, so it compares and range-scans against every other instant in
the database.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Float
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


class Lightning(Base):
    """One lightning stroke located by a detection network.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. This is the *local* GisFIRE
        identifier; a provider's own identifiers belong to the corresponding
        subclass.
    type : str
        Polymorphic discriminator, ``"lightning"`` for the generic model.
    data_provider_id : int
        Foreign key to :class:`~src.data_model.data_provider.DataProvider`, the
        provider this stroke was obtained from.
    data_provider : DataProvider
        The provider this stroke was obtained from.
    date_time : datetime.datetime
        Timezone-aware instant the stroke was detected. Indexed.
    geometry : geoalchemy2.elements.WKBElement
        Where the stroke was located, as a ``POINT`` in EPSG:4326 (WGS 84). A
        provider publishing in another CRS keeps that coordinate on its subclass
        and stores the reprojection here. Indexed (GiST).
    peak_current : float or None
        Peak current of the stroke in kiloamperes, **signed**: negative for a
        negative discharge, positive for a positive one, so the polarity is the
        sign. ``None`` when the provider does not report it.
    cloud_to_ground : bool or None
        ``True`` for a cloud-to-ground stroke, ``False`` for an intra-cloud (or
        cloud-to-cloud) one, ``None`` when the provider does not say.
    admin_boundary_id : int or None
        Foreign key to the :class:`~src.data_model.geography.admin_boundary.
        AdminBoundary` the stroke fell in, resolved once at import time by
        spatial join rather than per query. ``None`` when the point matches no
        imported boundary — because the boundaries have not been imported, or
        because the stroke fell outside all of them (at sea, most often).
        Indexed.
    admin_boundary : AdminBoundary or None
        The administrative division the stroke fell in.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "lightning"

    __table_args__ = (
        Index("ix_lightning_admin_boundary_id", "admin_boundary_id"),
        Index("ix_lightning_date_time", "date_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    date_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    peak_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_to_ground: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
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
        "polymorphic_identity": "lightning",
    }

    def __repr__(self) -> str:
        return f"Lightning(id={self.id!r}, date_time={self.date_time!r})"
