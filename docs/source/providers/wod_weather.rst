WOD weather
===========

The weather, fire danger and climate the WOD's compilers attached to each record, from the
nearest suitable station of the Fire Weather System. One row per :doc:`wod_wildfire`,
deleted with it, and a table of its own for the reason :doc:`wod_terrain` is.

Column dictionary
-----------------

Names are the published ones in snake case. The suffix says *when*:

========  ==============================================================================
(none)    at the hour the fire was reported — the paper's proxy for ignition
``noon``  at noon of the day of the fire
``8b``    over the 8 hours **before** the report (``max``/``min``/``avg``, or the average)
``8a``    over the 8 hours **after** the report
========  ==============================================================================

=============================================  ==============================================
Columns                                        Unit
=============================================  ==============================================
``temp*``, ``soil_temp``                       °C
``rh*``, ``soil_moist``                        %
``ws*``                                        m/s — 10 m height-adjusted from September 2011
``wd``                                         degrees, the direction the wind blows from
``precip*``                                    mm
``no_rain_1``-``no_rain_3``                    days back to the 1st/2nd/3rd day above 0.5 mm
``ffmc*``, ``isi*``, ``fwi*``                  unitless indices of the FWI system
``dmc_noon``, ``dc_noon``, ``bui_noon``,       unitless, daily (noon only)
``dsr_noon``
``fdc*``                                       fire danger class, 1 to 5
``hfi*``                                       kW/m, head fire intensity
``ros*``                                       m/h, rate of spread
``soi``                                        Southern Oscillation Index of the month
``enso``                                       ``El Nino``, ``La Nina`` or ``Neutral``
``wx_name``, ``wx_id``                         the station used
``wx_dist``                                    km from the fire to the station (at most 50)
``clim_zn_name``                               the FENZ climate zone; ``NULL`` = a fallback
                                               station outside the fire's zone was used
=============================================  ==============================================

``fdc``, ``hfi`` and ``ros`` are read from the grass, scrub or forest model chosen by
:attr:`~src.providers.new_zealand_wod.terrain.WodTerrain.fuel_class`.

.. warning::

   **Nothing before 1995 has weather**, and soil moisture and temperature exist only at
   some stations from 2018. **DOC records have no report time**, and the compilers assumed
   12:00 for them — so for a DOC fire the unsuffixed and ``8b``/``8a`` values are centred
   on noon. Its ``report_time`` is ``NULL``, which is how to tell.

.. automodule:: src.providers.new_zealand_wod.weather
   :members:
   :show-inheritance:
