MeteoCat provider package
=========================

Constants and functions shared by the MeteoCat lightning model and the import
application: the provider identity (the row ``MeteoCat`` / ``XDDE`` in
``data_provider``, created by the first import and shared with the future API import),
the published CRS (ETRS89, EPSG:4258) and the projected one the views expose (ETRS89 /
UTM 31N, EPSG:25831), the extract header, and the generations of the network.

One function lives here because both the reader and anything else interpreting the
delivery need it: :func:`~src.providers.catalonia_meteocat.network_version`, which tells
the two generations of the network apart by the published sensor count.

The module docstring is also where the dataset itself is written down — the eleven
columns, what ``secidx`` is, why nothing identifies a stroke, the two network generations
and the September 2009 overlap.

.. automodule:: src.providers.catalonia_meteocat
   :members:
   :show-inheritance:
