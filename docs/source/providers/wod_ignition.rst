WOD ignition
============

Where a New Zealand wildfire was recorded — the published ``X``/``Y`` on the NZTM2000 grid.
See :doc:`../data_model/ignition` for the columns it inherits and :doc:`wod_wildfire` for
the record it belongs to.

**Every record has one, and none is moved.** The 92 points in the sea are stored as
published, the 15 on the placeholder coordinate among them, and so is the point of every
polygon record — which is the location of the original record and neither the polygon's
centroid nor its origin. The point is stored twice, in EPSG:2193 as published and in
EPSG:4326 on the generic model; the published ``Lat``/``Lon`` are not kept, being that
reprojection to a billionth of a degree.

.. warning::

   This is where the fire was **reported**, not necessarily where it started. FENZ records
   were historically tied to a road, often a roadside address; the paper warns that this can
   exaggerate the role of roads.

.. automodule:: src.providers.new_zealand_wod.ignition
   :members:
   :show-inheritance:
