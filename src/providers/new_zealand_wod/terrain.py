#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WOD terrain model.

The topography and fuel the WOD's compilers attached to each wildfire record, from
national rasters. One row per :class:`~src.providers.new_zealand_wod.wildfire.
WodWildfire`, on a table of its own because it is the compilers' derivation and not
the agency's observation — see :mod:`src.providers.new_zealand_wod`.

Point records and polygon records are attributed differently
-------------------------------------------------------------

The published columns mean different things depending on whether the record has a
perimeter, and that has to be known before any of them is aggregated:

=====================  ==================================  ==========================================
Column                 Point record                        Polygon record
=====================  ==================================  ==========================================
``elev``, ``slope``    the value at the point              the **average** over the polygon
``min_*``, ``max_*``   ``NULL``                            the minimum and maximum over the polygon
``aspect_car``,        the class at the point              the **most common** class in the polygon
``land_cvr``,
``landform``
``*_2``, ``*_3``       ``NULL``                            the second and third most common
``aspect_deg``         the value at the point              the value at the published point
=====================  ==================================  ==========================================

Sources, as the paper gives them: elevation from the 25 m New Zealand National DEM;
slope from the Land Environments of New Zealand classification; aspect from the
100 m New Zealand Environmental Data Stack; landform from Barringer et al. Land cover
comes from a **different dataset depending on the fire's year** — the Potential
Vegetation of New Zealand before 1980, the Vegetation Cover Map for 1980-1995, and
LCDB v5.0 from 1996, with base imagery 1996/97, 2000/01, 2008/09, 2012/13 and
2018/19 for successive periods — so land-cover classes are not comparable across
those breaks without care.

``fuel_type`` and ``fuel_class`` are mapped from the land cover (Table 2 of the
paper): the fuel class is the NZ Fire Danger Rating System's grass/scrub/forest, plus
non-fuel, and it is what chose which grass, scrub or forest index went into the
``fdc``/``hfi``/``ros`` columns of
:class:`~src.providers.new_zealand_wod.weather.WodWeather`.

There is no terrain at all for the Chatham Islands (outside the rasters) or for the
points in the sea.
"""

from __future__ import annotations

from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.providers.new_zealand_wod.wildfire import WodWildfire


class WodTerrain(Base):
    """The topography and fuel attached to one WOD wildfire record.

    Every column is nullable and ``NULL`` where the WOD published ``-9999``.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.id`; deleting the
        fire deletes this row.
    elev, min_elev, max_elev : float or None
        ``Elev``, ``MinElev``, ``MaxElev``: elevation in metres.
    slope, min_slope, max_slope : float or None
        ``Slope``, ``MinSlope``, ``MaxSlope``: slope in degrees.
    aspect_deg : float or None
        ``AspectDeg``: aspect in degrees, at the published point.
    aspect_car, aspect_car_2, aspect_car_3 : str or None
        ``AspectCar``, ``AspectCar2``, ``AspectCar3``: aspect as one of eight
        cardinal directions, 45° wide and centred on the direction (North is 337.5°
        to 22.5°).
    land_cvr, land_cvr_2, land_cvr_3 : str or None
        ``LandCvr``, ``LandCvr2``, ``LandCvr3``: land cover class, from the dataset
        the fire's year selects.
    fuel_type : str or None
        ``FuelType``: one of the six vegetation categories of the Guide to New
        Zealand Fuels, or ``Non-Fuel``.
    fuel_class : str or None
        ``FuelClass``: ``Grass``, ``Scrub``, ``Forest`` or ``Non Fuel``.
    landform, landform_2, landform_3 : str or None
        ``Landform``, ``Landform2``, ``Landform3``: landform element.
    wildfire : WodWildfire
        The fire.
    """

    __tablename__ = "wod_terrain"

    id: Mapped[int] = mapped_column(ForeignKey(WodWildfire.id, ondelete="CASCADE"),
                                    primary_key=True)

    elev: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_elev: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_elev: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    aspect_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    aspect_car: Mapped[str | None] = mapped_column(String, nullable=True)
    aspect_car_2: Mapped[str | None] = mapped_column(String, nullable=True)
    aspect_car_3: Mapped[str | None] = mapped_column(String, nullable=True)

    land_cvr: Mapped[str | None] = mapped_column(String, nullable=True)
    land_cvr_2: Mapped[str | None] = mapped_column(String, nullable=True)
    land_cvr_3: Mapped[str | None] = mapped_column(String, nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String, nullable=True)
    fuel_class: Mapped[str | None] = mapped_column(String, nullable=True)

    landform: Mapped[str | None] = mapped_column(String, nullable=True)
    landform_2: Mapped[str | None] = mapped_column(String, nullable=True)
    landform_3: Mapped[str | None] = mapped_column(String, nullable=True)

    wildfire: Mapped[WodWildfire] = relationship(back_populates="terrain")

    def __repr__(self) -> str:
        return f"WodTerrain(id={self.id!r}, land_cvr={self.land_cvr!r})"
