#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data provider model.

A ``DataProvider`` is a source of data ingested by GisFIRE (e.g. a weather
service or a lightning-detection network). The set of providers is small and
finite; each provider gets its own tables under ``src/providers/`` for the data
it supplies, and those tables reference this one so data can only be attached to
a known provider.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base


class DataProvider(Base):
    """A source of data ingested by GisFIRE.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key. Referenced by the provider-specific
        data tables.
    name : str
        Short unique identifier, usually an acronym (e.g. ``"MeteoCat"``).
    full_name : str
        Human-readable expansion of ``name``.
    description : str or None
        Free-text description of the provider, if any.
    url : str or None
        Link to the provider's website, if any.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "data_provider"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"DataProvider(id={self.id!r}, name={self.name!r})"
