#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Time zone model.

A ``TimeZone`` is the area on the ground over which one IANA time zone applies —
``Europe/Andorra``, ``America/Los_Angeles`` — stored as a PostGIS
``MULTIPOLYGON`` in EPSG:4326.

The table exists for one job: turning a coordinate into a zone *name*, so that a
provider reporting local wall-clock time can be converted to an instant at import
time. That conversion is what makes dates from different agencies comparable —
see :class:`~src.data_model.wildfire.Wildfire` for the storage rule the project
follows.

The zone name is what a query wants, not this table's primary key, so nothing
references ``TimeZone`` by foreign key. Models store the resolved IANA name as
text instead, which means a row here can be replaced when IANA republishes
without rewriting the events that were located against it.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base


class TimeZone(Base):
    """The area over which one IANA time zone applies.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. Purely internal: nothing refers to a
        zone by this id, see the module docstring.
    name : str
        IANA time zone name (``"Europe/Andorra"``), unique. This is the string
        PostgreSQL's ``AT TIME ZONE`` understands, and the one stored on the
        events located against this table.
    geometry : geoalchemy2.elements.WKBElement
        The zone's area as a ``MULTIPOLYGON`` in EPSG:4326 (WGS 84).
        ``MULTIPOLYGON`` because zones are routinely made of several disjoint
        parts — enclaves, islands and, for the ocean zones, whole scattered
        bands of open sea.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.

    Notes
    -----
    Whether the zone is on daylight saving time on a given date is *not* stored
    and must not be: it is a property of the date, not of the area. Resolving it
    is PostgreSQL's job, which is why the name is kept in the form ``AT TIME
    ZONE`` accepts — ``timestamp AT TIME ZONE name`` picks the offset in force on
    that date from the system's IANA database.
    """

    __tablename__ = "time_zone"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"TimeZone(id={self.id!r}, name={self.name!r})"
