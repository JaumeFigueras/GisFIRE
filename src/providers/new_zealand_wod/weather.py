#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WOD weather model.

The weather, fire danger and climate the WOD's compilers attached to each wildfire
record. One row per :class:`~src.providers.new_zealand_wod.wildfire.WodWildfire`, on
a table of its own because it is the compilers' derivation and not the agency's
observation — see :mod:`src.providers.new_zealand_wod`.

Where it comes from
-------------------

Weather stations of the Fire Weather System (FWSYS) API, from 1995 — **nothing
earlier has any weather**. For each fire the compilers took the station of the FENZ
climate zone the point is in, provided it had noon temperature and FWI that day;
otherwise the nearest station that did, trying up to ten, no further than 50 km.
:attr:`WodWeather.clim_zn_name` is ``NULL`` exactly when that fallback was used, and
:attr:`WodWeather.wx_dist` then says how far the weather was measured from the fire.

The suffixes
------------

========  ==================================================================
(none)    at the hour the fire was **reported** — ``Time``, the paper's proxy
          for ignition
``noon``  at noon of the day of the fire
``8b``    over the 8 hours **before** the report time
``8a``    over the 8 hours **after** the report time
========  ==================================================================

Temperature, humidity and wind speed have the maximum, minimum and average over each
8-hour window; the FWI-system values (FFMC, ISI, FWI) and the fuel-specific ones
(FDC, HFI, ROS) have only the average. DMC, DC, BUI and DSR are daily and exist at
noon only.

.. warning::

   **DOC records have no report time**, and for them the compilers assumed 12:00
   local. So for a DOC fire the unsuffixed and ``8b``/``8a`` values are centred on
   noon, not on a report. Their
   :attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.report_time` is
   ``None``, which is how to tell.

``fdc``, ``hfi`` and ``ros`` depend on fuel and were read from the grass, scrub or
forest model selected by
:attr:`~src.providers.new_zealand_wod.terrain.WodTerrain.fuel_class`; a non-fuel
point has none.

Wind speed is the 10 m height-adjusted wind from **September 2011** and the station's
own before that, so a wind series across 2011 compares two measurements.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import SmallInteger
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.providers.new_zealand_wod import ENSO_PHASES
from src.providers.new_zealand_wod import FIRE_DANGER_CLASS_RANGE
from src.providers.new_zealand_wod.wildfire import WodWildfire

#: The four fire danger class columns, each constrained to
#: :data:`~src.providers.new_zealand_wod.FIRE_DANGER_CLASS_RANGE`.
FIRE_DANGER_CLASS_COLUMNS = ("fdc", "fdc_noon", "fdc_8b", "fdc_8a")


def _fire_danger_class_check(column: str) -> CheckConstraint:
    low, high = FIRE_DANGER_CLASS_RANGE
    return CheckConstraint(f"{column} IS NULL OR {column} BETWEEN {low} AND {high}",
                           name=f"ck_wod_weather_{column}")


def _float() -> Mapped[float | None]:
    return mapped_column(Float, nullable=True)


class WodWeather(Base):
    """The weather, fire danger and climate attached to one WOD wildfire record.

    Every measurement is nullable and ``NULL`` where the WOD published ``-9999``.
    Column names are the published ones in snake case, suffixes as in the module
    docstring.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.id`; deleting the
        fire deletes this row.
    clim_zn_name : str or None
        ``ClimZnName``: the FENZ climate zone whose station was used, or ``None``
        when the station was a fallback from outside it.
    wx_name, wx_id : str or None
        ``WxName``, ``WxID``: the weather station used. ``None`` when no suitable
        station was found.
    wx_dist : float or None
        ``WxDist``: distance from the fire to that station, in **kilometres** (at
        most 50).
    temp, temp_noon, temp_max_8b, temp_min_8b, temp_avg_8b, temp_max_8a, temp_min_8a, temp_avg_8a : float or None
        Air temperature, °C.
    rh, rh_noon, rh_max_8b, rh_min_8b, rh_avg_8b, rh_max_8a, rh_min_8a, rh_avg_8a : float or None
        Relative humidity, %.
    ws, ws_noon, ws_max_8b, ws_min_8b, ws_avg_8b, ws_max_8a, ws_min_8a, ws_avg_8a : float or None
        Wind speed, **m/s**; 10 m height-adjusted from September 2011.
    wd : float or None
        Wind direction, degrees (from), at the report hour.
    soil_moist : float or None
        Soil moisture, %, at the report hour. Measured at some stations from 2018.
    soil_temp : float or None
        Soil temperature, °C, at the report hour. As :attr:`soil_moist`.
    ffmc, ffmc_noon, ffmc_8b, ffmc_8a : float or None
        Fine Fuel Moisture Code, unitless.
    isi, isi_noon, isi_8b, isi_8a : float or None
        Initial Spread Index, unitless.
    fwi, fwi_noon, fwi_8b, fwi_8a : float or None
        Fire Weather Index, unitless.
    fdc, fdc_noon, fdc_8b, fdc_8a : int or None
        Fire Danger Class, 1 to 5, for the fuel class of the point. Published as
        text, and whole numbers throughout — the 8-hour averages included.
    hfi, hfi_noon, hfi_8b, hfi_8a : float or None
        Head Fire Intensity, kW/m, for the fuel class of the point.
    ros, ros_noon, ros_8b, ros_8a : float or None
        Rate of Spread, m/h, for the fuel class of the point.
    dmc_noon, dc_noon, bui_noon, dsr_noon : float or None
        Duff Moisture Code, Drought Code, Build-Up Index and Daily Severity Rating at
        noon, unitless.
    precip_noon : float or None
        Precipitation over the 24 hours to noon of the day of the fire, mm.
    precip_24hr, precip_48hr, precip_72hr : float or None
        Precipitation over the 24, 48 and 72 hours before the report time, mm.
    no_rain_1, no_rain_2, no_rain_3 : float or None
        ``NoRain1``-``NoRain3``: days back from the fire to the first, second and
        third day with more than 0.5 mm of rain.
    soi : float or None
        Southern Oscillation Index of the month, from the Australian Bureau of
        Meteorology.
    enso : str or None
        ENSO phase, one of :data:`~src.providers.new_zealand_wod.ENSO_PHASES`: a
        five-month rolling SOI above 7 is La Niña, below −7 El Niño.
    wildfire : WodWildfire
        The fire.
    """

    __tablename__ = "wod_weather"

    __table_args__ = (
        *(_fire_danger_class_check(column) for column in FIRE_DANGER_CLASS_COLUMNS),
        CheckConstraint("enso IS NULL OR enso IN ("
                        + ", ".join(f"'{phase}'" for phase in ENSO_PHASES) + ")",
                        name="ck_wod_weather_enso"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(WodWildfire.id, ondelete="CASCADE"),
                                    primary_key=True)

    clim_zn_name: Mapped[str | None] = mapped_column(String, nullable=True)
    wx_name: Mapped[str | None] = mapped_column(String, nullable=True)
    wx_id: Mapped[str | None] = mapped_column(String, nullable=True)
    wx_dist: Mapped[float | None] = _float()

    temp: Mapped[float | None] = _float()
    temp_noon: Mapped[float | None] = _float()
    temp_max_8b: Mapped[float | None] = _float()
    temp_min_8b: Mapped[float | None] = _float()
    temp_avg_8b: Mapped[float | None] = _float()
    temp_max_8a: Mapped[float | None] = _float()
    temp_min_8a: Mapped[float | None] = _float()
    temp_avg_8a: Mapped[float | None] = _float()

    rh: Mapped[float | None] = _float()
    rh_noon: Mapped[float | None] = _float()
    rh_max_8b: Mapped[float | None] = _float()
    rh_min_8b: Mapped[float | None] = _float()
    rh_avg_8b: Mapped[float | None] = _float()
    rh_max_8a: Mapped[float | None] = _float()
    rh_min_8a: Mapped[float | None] = _float()
    rh_avg_8a: Mapped[float | None] = _float()

    ws: Mapped[float | None] = _float()
    ws_noon: Mapped[float | None] = _float()
    ws_max_8b: Mapped[float | None] = _float()
    ws_min_8b: Mapped[float | None] = _float()
    ws_avg_8b: Mapped[float | None] = _float()
    ws_max_8a: Mapped[float | None] = _float()
    ws_min_8a: Mapped[float | None] = _float()
    ws_avg_8a: Mapped[float | None] = _float()
    wd: Mapped[float | None] = _float()

    soil_moist: Mapped[float | None] = _float()
    soil_temp: Mapped[float | None] = _float()

    ffmc: Mapped[float | None] = _float()
    ffmc_noon: Mapped[float | None] = _float()
    ffmc_8b: Mapped[float | None] = _float()
    ffmc_8a: Mapped[float | None] = _float()
    isi: Mapped[float | None] = _float()
    isi_noon: Mapped[float | None] = _float()
    isi_8b: Mapped[float | None] = _float()
    isi_8a: Mapped[float | None] = _float()
    fwi: Mapped[float | None] = _float()
    fwi_noon: Mapped[float | None] = _float()
    fwi_8b: Mapped[float | None] = _float()
    fwi_8a: Mapped[float | None] = _float()

    fdc: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fdc_noon: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fdc_8b: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fdc_8a: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    hfi: Mapped[float | None] = _float()
    hfi_noon: Mapped[float | None] = _float()
    hfi_8b: Mapped[float | None] = _float()
    hfi_8a: Mapped[float | None] = _float()
    ros: Mapped[float | None] = _float()
    ros_noon: Mapped[float | None] = _float()
    ros_8b: Mapped[float | None] = _float()
    ros_8a: Mapped[float | None] = _float()

    dmc_noon: Mapped[float | None] = _float()
    dc_noon: Mapped[float | None] = _float()
    bui_noon: Mapped[float | None] = _float()
    dsr_noon: Mapped[float | None] = _float()

    precip_noon: Mapped[float | None] = _float()
    precip_24hr: Mapped[float | None] = _float()
    precip_48hr: Mapped[float | None] = _float()
    precip_72hr: Mapped[float | None] = _float()
    no_rain_1: Mapped[float | None] = _float()
    no_rain_2: Mapped[float | None] = _float()
    no_rain_3: Mapped[float | None] = _float()

    soi: Mapped[float | None] = _float()
    enso: Mapped[str | None] = mapped_column(String, nullable=True)

    wildfire: Mapped[WodWildfire] = relationship(back_populates="weather")

    def __repr__(self) -> str:
        return f"WodWeather(id={self.id!r}, wx_name={self.wx_name!r})"
