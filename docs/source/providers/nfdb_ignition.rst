NFDB ignition
=============

Where a Canadian fire was reported, as the agency filed it — a point on the NAD83 / Canada
Atlas Lambert grid. See :doc:`../data_model/ignition` for the columns it inherits and why
an ignition is a model of its own, and :doc:`nfdb_wildfire` for the report it belongs to.

Two things about it are worth knowing before using it. It stores the published point
**twice**, in EPSG:3978 as published and in EPSG:4326 on the generic model — which is
where this provider parts company with :doc:`greece_ffa_ignition`, whose source publishes
degrees and whose geometry therefore *is* the published pair. Here the source publishes
metres, so the EPSG:4326 point is a reprojection and the grid coordinates are the
originals. And the shapefile's own ``LATITUDE``/``LONGITUDE`` attribute columns are
deliberately **not** kept: they are the service's own reprojection of the same point, and
where they disagree with the geometry it is because they are wrong.

.. warning::

   This is where the fire was **reported**, not necessarily where it started. The published
   summary says *"Locations are approximate"*, and thirteen agencies contribute at thirteen
   standards over ninety-five years.

.. automodule:: src.providers.canada_nfdb.ignition
   :members:
   :show-inheritance:
