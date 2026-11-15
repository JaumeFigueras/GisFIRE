USWFS (Alaska) provider package
===============================

Constants shared by the Alaska lightning model and the import application:

- the provider identity: the row ``USWFS`` / ``ALDN`` in ``data_provider``, created by
  the first import;
- the licence and how to cite the data;
- the publisher's page where the release is downloaded;
- the fifteen columns of the strokes file;
- the published CRS, WGS 84 (EPSG:4326), and the projected one that the views and the
  thunderstorm reader use, NAD83 / Alaska Albers (EPSG:3338);
- the factors that turn amperes into kiloamperes and the published kilometres of the
  ellipse into metres;
- the area the network covers, which crosses the antimeridian;
- the three limits of the flash grouping.

The module docstring is also where the release itself is written down, all of it found by
reading the release of 2026-11-06 row by row, since the metadata gives each column a
sentence and two of those sentences are wrong. It covers:

- what the zip holds;
- the columns and what they turned out to be: the millisecond column is the fraction of
  the second, not a duration, the local time follows three different rules over the
  years, and the ellipse is in whole kilometres;
- the oddities: strokes published twice, semi-major axes of 0 in runs of hours, strokes
  sharing a millisecond;
- why GisFIRE groups the strokes into flashes itself;
- the licence.

.. automodule:: src.providers.alaska_uswfs
   :members:
   :show-inheritance:
