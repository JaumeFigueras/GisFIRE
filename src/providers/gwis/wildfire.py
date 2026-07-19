#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GWIS wildfire model.

The *Global Wildfire Database* product of GWIS supplies, for each fire, a start
and an end date, a perimeter in EPSG:4326 and its own identifier. The first
three are exactly what the generic :class:`~src.data_model.wildfire.Wildfire`
already holds, so the only thing this model adds is the identifier GWIS uses for
the fire — the one needed to recognise a record already imported and to trace a
row back to the source.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.wildfire import Wildfire


class GwisWildfire(Wildfire):
    """A wildfire as published by the GWIS Global Wildfire Database.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only ``gwis_id`` is stored here, in
    ``gwis_wildfire``, whose primary key is also a foreign key to the parent
    row. Reading a ``GwisWildfire`` joins the two tables; the generic columns are
    inherited attributes, not copies.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. This is the local GisFIRE
        identifier, shared with the parent row.
    gwis_id : str
        The identifier GWIS gives the fire, unique within the product. Kept as
        text so a change in the provider's identifier format cannot break
        imports.
    """

    __tablename__ = "gwis_wildfire"

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    gwis_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "gwis_wildfire",
    }

    def __repr__(self) -> str:
        return f"GwisWildfire(id={self.id!r}, gwis_id={self.gwis_id!r})"
