#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wildfire model.

A ``Wildfire`` is a fire event as reported by a :class:`~src.data_model.
data_provider.DataProvider`: when it started, when it was extinguished and the
area it burnt, stored as a PostGIS ``MULTIPOLYGON`` in EPSG:4326.

This is the *generic* model. Each provider publishes its own extra attributes
(its own identifier included) through a subclass, using single-table
polymorphic inheritance on :attr:`Wildfire.type`.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.data_model.data_provider import DataProvider


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
    perimeter : geoalchemy2.elements.WKBElement or None
        Burnt area as a ``MULTIPOLYGON`` in EPSG:4326 (WGS 84), or ``None`` if
        the provider reports no perimeter (yet).
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "wildfire"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    start_date_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    perimeter: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_provider: Mapped[DataProvider] = relationship()

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "wildfire",
    }

    def __repr__(self) -> str:
        return f"Wildfire(id={self.id!r}, start_date_time={self.start_date_time!r})"
