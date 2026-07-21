#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GWIS wildfire model.

The *Global Wildfire Database* product of GWIS supplies, for each fire, a start
and an end date, a perimeter in EPSG:4326 and its own identifier. The first
three are exactly what the generic :class:`~src.data_model.wildfire.Wildfire`
already holds, so the only thing this model adds is the identifier GWIS uses for
the fire, which is what traces a row back to the published dataset.

It does *not* identify the fire uniquely, despite being the dataset's only
identifier — see :class:`GwisWildfire`.
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
        The identifier GWIS gives the fire. Kept as text so a change in the
        provider's identifier format cannot break imports.

        **Not unique**, despite the name, and not usable as a key — see the note
        below. Indexed, because looking a fire up by it is still the normal way
        to trace a row back to the published dataset.

    Notes
    -----
    ``Id`` repeats in the published files, and where it repeats it names
    genuinely different fires rather than duplicate records: in the 2021 file,
    ``24935861`` is both a fire in Papua New Guinea on 8 January and one in
    California on 23 February. Across the whole of GlobFire v3 — 23,299,416
    fires in the 2000-2021 files — there are 359 such collisions, some of them
    spanning two years' files.

    ``(Id, IDate)``, on the other hand, *is* unique over all 23,299,416, so it
    could serve as a natural key. It is deliberately not made one here: doing so
    would mean storing the published ``IDate`` again on this table, since a
    constraint cannot span the two tables of the inheritance and the parent's
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is a converted
    instant rather than the date as published.

    The consequence is that GisFIRE has no key with which to recognise a GWIS
    fire it has already seen, so **re-running an import inserts the file again**
    rather than skipping it. The importer warns before doing so. The alternative
    — treating a repeated ``Id`` as a fire already imported — was rejected
    because it would throw away the second fire of each of those 359 pairs,
    which is real data.
    """

    __tablename__ = "gwis_wildfire"

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    gwis_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "gwis_wildfire",
    }

    def __repr__(self) -> str:
        return f"GwisWildfire(id={self.id!r}, gwis_id={self.gwis_id!r})"
