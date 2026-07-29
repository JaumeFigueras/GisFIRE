EGIF ignition
=============

The point an EGIF fire started at. See :doc:`../data_model/ignition` for the columns it
inherits — the EPSG:4326 geometry above all — and :doc:`egif_wildfire` for the report
that hangs off it.

This is the model that explains why EGIF is worth importing despite publishing no
perimeter: it is the only Iberian dataset here with an ignition coordinate.

.. automodule:: src.providers.egif.ignition
   :members:
   :show-inheritance:
