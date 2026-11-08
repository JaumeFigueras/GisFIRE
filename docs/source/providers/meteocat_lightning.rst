MeteoCat lightning
==================

The stroke model for MeteoCat's lightning-detection network, the XDDE. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/lightning` for the columns it inherits, and :doc:`meteocat_provider`
for the dataset.

Three things about it are worth knowing before using it. The point is stored **twice**:
as published in ETRS89 (``geometry_etrs89``) and reprojected to EPSG:4326 on the parent.
A **flash** is ``(network_version, flash_id)``, never ``flash_id`` alone, and every
stroke carries its flash's ``multiplicity`` and its own ``stroke_index`` — so
``stroke_index = 1`` selects one stroke per flash. And **"not recorded" is NULL**: the
first network generation published ``0`` for the sensor count and the chi-squared, which
are stored as ``NULL``, and a ``CHECK`` refuses a ``0`` sensor count.

.. automodule:: src.providers.catalonia_meteocat.lightning
   :members:
   :show-inheritance:
