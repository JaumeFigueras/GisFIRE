DARPA provider package
======================

Constants shared by the DARPA model and the import application: the provider identity,
the published CRS, the burnt ``GRID_CODE`` class, the layer names that must not be
imported, and :func:`~src.providers.catalonia_darpa.layer_year`, which turns a published
layer name into the year it covers.

The module docstring is also where the dataset itself is written down — the two character
sets, the three shattered years, the six formats of ``CODI_FINAL``, and why the natural key
is the code *and* the date.

.. automodule:: src.providers.catalonia_darpa
   :members:
   :show-inheritance:
