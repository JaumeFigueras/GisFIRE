#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFA ignition model.

The Global Fire Atlas publishes an ignition point for every fire — the ``lat`` /
``lon`` where the burn began — which is exactly what the generic
:class:`~src.data_model.ignition.Ignition` holds: a point, the instant it
started, and the country and zone that follow from the point. The only thing
this model adds is the identifier GFA uses for the fire, shared with
:class:`~src.providers.gfa.wildfire.GfaWildfire` so the two observations of one
fire can be matched.

There is no separate ignitions import. The Atlas ships the ignition points as
their own set of shapefiles, but they carry the same ``lat`` / ``lon`` the
perimeter files already do, so the ignition is built from the perimeter import
rather than read again — see
:mod:`src.apps.imports.wildfires.gfa.import_wildfires`.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition


class GfaIgnition(Ignition):
    """A fire's point of origin as published by the Global Fire Atlas.

    Uses joined table inheritance: the columns shared by every ignition live in
    the ``ignition`` table and only ``gfa_id`` is stored here, in
    ``gfa_ignition``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE
        identifier, shared with the parent row.
    gfa_id : int
        The identifier GFA gives the fire (``fire_ID``). Unique, and the same
        value carried by the matching
        :attr:`~src.providers.gfa.wildfire.GfaWildfire.gfa_id`. This is what ties
        an ignition to its perimeter: they are two observations of the fire the
        Atlas numbers ``gfa_id``.
    """

    __tablename__ = "gfa_ignition"

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    gfa_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "gfa_ignition",
    }

    def __repr__(self) -> str:
        return f"GfaIgnition(id={self.id!r}, gfa_id={self.gfa_id!r})"
