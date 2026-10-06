WOD terrain
===========

The topography and fuel the WOD's compilers attached to each record from national rasters:
elevation, slope, aspect, land cover, fuel type and class, landform. One row per
:doc:`wod_wildfire`, deleted with it.

It is a table of its own because it is a **derivation, not an observation**: the agencies
recorded the fire, the compilers looked up what was at its location. Every published column
is kept — ``NULL`` where the WOD wrote ``-9999``.

.. important::

   **A point record and a polygon record are attributed differently.** For a point,
   ``elev`` and ``slope`` are the values at the point and the ``min_*``/``max_*``/``*_2``/
   ``*_3`` columns are empty. For a polygon, ``elev`` and ``slope`` are **averages over
   the polygon**, ``min_*``/``max_*`` are real, and the categorical columns hold the most
   common class followed by the second and third. Aggregating ``elev`` across both kinds
   mixes two quantities.

   **The land cover comes from a different dataset depending on the fire's year** — the
   Potential Vegetation of New Zealand before 1980, the Vegetation Cover Map for
   1980-1995, LCDB v5.0 from 1996 with base imagery of 1996/97, 2000/01, 2008/09, 2012/13
   and 2018/19 for successive periods — so land-cover classes are not comparable across
   those breaks without care.

There is no terrain for the Chatham Islands, which the rasters do not cover, or for the
points in the sea.

.. automodule:: src.providers.new_zealand_wod.terrain
   :members:
   :show-inheritance:
