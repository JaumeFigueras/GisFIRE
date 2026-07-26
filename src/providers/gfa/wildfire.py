#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GFA wildfire model.

The Global Fire Atlas publishes, for each fire, the three things the generic
:class:`~src.data_model.wildfire.Wildfire` already holds — a start date, an end
date and a perimeter — plus its own identifier, a set of measurements of how the
fire spread, and an ignition point. The measurements are what this model adds.

The ignition point is *not* stored here: it is an
:class:`~src.providers.gfa.ignition.GfaIgnition` of its own, and this model links
to it with :attr:`gfa_ignition_id`. The point describes where the fire began, not
its burnt area, so it belongs on the ignition rather than being duplicated onto
the perimeter — and storing it once, indexed once, is not free at twenty million
fires.

Units are the provider's own and are kept as published rather than converted, so
that a row can be checked against the published file without arithmetic. They
are named for the unit (``size_km2``, ``speed_km_day``) so no reader has to
guess.
"""

from __future__ import annotations

from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.gfa.ignition import GfaIgnition


class GfaWildfire(Wildfire):
    """A wildfire as published by the Global Fire Atlas.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the GFA-specific ones are stored here, in
    ``gfa_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. This is the local GisFIRE
        identifier, shared with the parent row.
    gfa_id : int
        The identifier GFA gives the fire (``fire_ID``). **Unique**, unlike its
        GWIS counterpart — see the note below.
    gfa_ignition_id : int
        Foreign key to the :class:`~src.providers.gfa.ignition.GfaIgnition` this
        fire started from. The country and the local start time on the parent
        :class:`~src.data_model.wildfire.Wildfire` were both resolved from that
        ignition's point, so the two rows always agree on them.
    ignition : GfaIgnition
        The fire's point of origin. Its
        :attr:`~src.data_model.ignition.Ignition.geometry` is the ignition point;
        reach for it instead of a coordinate column on this table.
    size_km2 : float or None
        Fire size, km² (``size``). This is the size of the *whole* fire, so it
        is not the area of :attr:`~src.data_model.wildfire.Wildfire.perimeter`
        computed on the ellipsoid; it is what GFA published.
    perimeter_km : float or None
        Length of the fire perimeter, km (``perimeter``). Named apart from the
        inherited ``perimeter``, which is the geometry.
    duration_days : int or None
        Duration, days (``duration``).
    fire_line_km : float or None
        Average length of the daily fire line, km (``fire_line``).
    spread_km2_day : float or None
        Average daily fire growth, km²/day (``spread``).
    speed_km_day : float or None
        Average speed, km/day (``speed``).
    direction : str or None
        Dominant direction of spread, as published: one of ``north``,
        ``northeast``, ``east``, … or ``none`` where no direction dominated.
    direction_fraction : float or None
        Fraction of the spread in that direction (``direc_frac``), 0 when
        :attr:`direction` is ``none``.
    modis_tile : str or None
        MODIS tile the fire was detected in (``MODIS_tile``), e.g. ``h23v02``.
    landcover : str or None
        Dominant MCD12Q1 land cover class in the UMD classification
        (``landcover``), e.g. ``Savannas``. GFA only classifies 2002-2023; every
        fire in a later file is published as ``Unclassified``.
    landcover_fraction : float or None
        Fraction of the fire in that class (``landc_frac``).
    gfed_region : int or None
        GFED region code (``GFED_regio``), 1-14 as defined by van der Werf et
        al. (2017), or 0 for a fire in none of them.

    Notes
    -----
    ``fire_ID`` encodes the year — ``2xxxxxxx`` for 2002 through ``26xxxxxxx``
    for 2026 — so it does not collide between the yearly files, and within a file
    it repeats only across the parts of one multipart fire. The importer collects
    those parts into a single ``MULTIPOLYGON``, which leaves one row per fire and
    makes the identifier a genuine key. That is what the ``UNIQUE`` below
    records, and what lets the importer skip a file it has already loaded —
    neither of which is possible for
    :class:`~src.providers.gwis.wildfire.GwisWildfire`, whose identifier names
    genuinely different fires when it repeats.

    The constraint covers ``gfa_id`` alone rather than the provider and the id
    together: this table holds GFA rows only, so the provider is implied, and the
    parent's ``data_provider_id`` could not be part of a constraint here anyway.
    """

    __tablename__ = "gfa_wildfire"

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    gfa_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    gfa_ignition_id: Mapped[int] = mapped_column(ForeignKey(GfaIgnition.id), nullable=False)
    size_km2: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fire_line_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_km2_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_km_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    direction_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    modis_tile: Mapped[str | None] = mapped_column(String, nullable=True)
    landcover: Mapped[str | None] = mapped_column(String, nullable=True)
    landcover_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    gfed_region: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ignition: Mapped[GfaIgnition] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "gfa_wildfire",
    }

    def __repr__(self) -> str:
        return f"GfaWildfire(id={self.id!r}, gfa_id={self.gfa_id!r})"
