REDIAM provider package
=======================

Constants shared by the REDIAM models and the import application: the provider identity,
the published CRS and the one the ``.prj`` resolves to, the Andalusian INE province
codes, the layer-name patterns that tell the combined layer from a yearly one, and
:func:`~src.providers.andalusia_rediam.egif_report_number`, which turns a published
``CODIGO`` into the EGIF report number it is.

The module docstring is also where the dataset itself is written down — the combined
layer and the eighteen yearly ones, the three published burnt areas, the ignition point
that exists for four years, the 55 duplicated records, and why the geometry is stored as
EPSG:25830 rather than as the EPSG:3042 GDAL reads off the ``.prj``.

.. automodule:: src.providers.andalusia_rediam
   :members:
   :show-inheritance:
