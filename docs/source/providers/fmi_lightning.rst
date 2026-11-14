FMI lightning
=============

The stroke model for the Finnish Meteorological Institute's lightning data. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/lightning` for the columns it inherits, and :doc:`fmi_provider` for
the dataset.

Four things about it are worth knowing before using it. The point is stored **twice**:
as published in ETRS89 (``geometry_etrs89``) and reprojected to EPSG:4326 on the parent;
the EPSG:3067 point is never stored, only indexed. A **flash** is ``flash_id`` alone —
one sequence for the whole archive — and every stroke carries its flash's
``multiplicity`` and its own ``stroke_index``, so ``stroke_index = 1`` selects one stroke
per flash; FMI's own count is kept as ``published_multiplicity``. The ellipse axes are in
**metres**, converted from the kilometres FMI publishes, so that they mean the same as
MeteoCat's. And the undocumented fields — the three indicators, the stroke status — are
**stored as published**, with no constraint on their values.

.. automodule:: src.providers.finland_fmi.lightning
   :members:
   :show-inheritance:
