FMI provider package
====================

Constants shared by the FMI lightning model, the downloader and the import
application: the provider identity (the row ``FMI`` / ``Lightning strikes`` in
``data_provider``, created by the first import), the licence and how to credit the data,
the WFS endpoint and its stored query, the longest interval one request may cover, the
sixteen parameters asked for, the name and header of the downloader's monthly files, the
published CRS (ETRS89, EPSG:4258), the projected one the views and the thunderstorm
reader use (ETRS89 / TM35FIN, EPSG:3067), and the factor that turns the published
kilometres of the ellipse into metres.

The module docstring is also where the dataset itself is written down, all of it found by
querying the service, since FMI documents none of it: the two encodings of the same
records, the half-open 168-hour interval, the sixteen fields and their units, the
archive since 8 January 1998 and what changes across its years, the ellipse ceilings
that are a quality filter, why nothing identifies a stroke, and the licence.

.. automodule:: src.providers.finland_fmi
   :members:
   :show-inheritance:
