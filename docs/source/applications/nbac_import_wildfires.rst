NBAC wildfire import (Canada)
=============================

Imports the Canadian *National Burned Area Composite*: 53 zipped shapefiles, one per year
from 1973 to 2025, holding **52,276 published polygons that dissolve to 51,818 fire
events** and 132.7 million hectares of mapped burn. GisFIRE's first source outside Europe
and its largest polygon archive after GWIS and GFA.

See :doc:`../providers` for the dataset and :doc:`../providers/nbac_wildfire` for what each
column means. The zips are read without ever being unpacked, through GDAL's ``/vsizip/``.

Usage
-----

.. code-block:: console

   python3 -m src.apps.imports.wildfires.canada_nbac.import_wildfires -d /path/to/nbac/

   python3 -m src.apps.imports.wildfires.canada_nbac.import_wildfires \
       -s NBAC_2023_20260513.zip NBAC_2024_20260513.zip

   python3 -m src.apps.imports.wildfires.canada_nbac.import_wildfires \
       -d /path/to/nbac/ --year 2023 --dry-run

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` and the
:doc:`time zone areas <time_zone_import_time_zones>` first, so that fires get a country and
a local start time. Canada spans six zones, so unlike Greece the zone really is resolved
per fire.

The whole archive imports in about twelve minutes.

A fire is a GID, not a polygon
------------------------------

The published features are cut at provincial, territorial and national park boundaries, so
a fire that crossed one arrives as several polygons sharing a ``GID``. The import dissolves
them into one row and keeps what the union cannot say by itself: ``part_count``,
``crosses_admin``, the administrations joined with ``"; "``, and the published areas
**summed**.

458 of the 52,276 polygons are such pieces — a little under one percent, but the one
percent includes some of the largest fires in the archive, which is where a boundary is
most likely to be in the way. A 1980 fire published as ``AB`` and ``SK`` becomes one row
reading ``AB; SK`` with ``crosses_admin`` true.

Where the pieces disagree about their cause, their source or their mapping method, the
first is taken and the disagreement is **counted and reported**. The dates are not a
disagreement: NBAC's own documentation says it keeps the earliest agency start and the
latest agency end for a cross-border fire, so the import takes ``min`` and ``max`` for
exactly the same reason.

Which date a fire starts on
---------------------------

Two independent date pairs are published — satellite hotspots and agency-reported — and for
some fires neither:

======================  ===========================  ==========================
``date_source``         From                         ``date_time_precision``
======================  ===========================  ==========================
``agency``              ``AG_SDATE``                 ``day``
``hotspot``             ``HS_SDATE``                 ``day``
``year``                1 January of ``YEAR``        ``year``
======================  ===========================  ==========================

**102 of 1980's 530 fires and 39 of 2023's 2,244 publish no date at all.** They are
imported rather than dropped — a fire with a year is still a fire — and
``date_time_precision`` is what stops anyone reading the 1 January as a date. The run
reports how many were dated each way.

All four published dates are stored as published, so the resolution can be checked and the
other observation stays available.

The end is ``AG_EDATE`` and nothing else. The last hotspot is deliberately not used to fill
it: a satellite losing sight of a fire is not an agency declaring it out, and a column
mixing the two would make every burning duration a mixture of two definitions.

.. warning::

   **The published ``.prj`` names no EPSG code.** It is a bare
   ``Canada_Lambert_Conformal_Conic`` whose parameters are EPSG:3978's exactly. ``ogr2ogr``
   is therefore given ``-t_srs EPSG:3978`` — a null transform if the file is what its
   parameters say, a correcting one if it ever stops being — and
   :func:`~src.apps.imports.wildfires.canada_nbac.import_wildfires.check_extent` then tests
   the staged geometry against Canada's real bounds on that grid.

   A transform that moved the archive is caught at import rather than in a map three months
   later. The test fixtures reproduce the published ``.prj`` verbatim, so this is exercised
   rather than assumed.

.. note::

   ``YEAR`` and ``NFIREID`` are published as ``Real`` and are **converted** to integers on
   the staging table rather than read as they land. The sibling ICNF, DARPA and REDIAM
   imports accept a double where they want an integer, because they only ever read the
   value; this one puts ``YEAR`` into ``make_date``, which has no ``double precision``
   overload and fails outright.

One transaction per year
------------------------

A year is loaded, dissolved, deleted and re-inserted in one transaction, so an interrupted
run leaves the years it finished and the year it was in the middle of exactly as it found
them. **Re-importing replaces the years it reads**, which is what makes a re-run of a
revised publication supersede rather than double. The years are read from the *data*, never
from the file name.

``--dry-run`` does all the work and rolls it back, including the delete, so the numbers
reported are the ones a real run would produce.

If a year being replaced contains fires bound to an NFDB report, the run says so at
``WARNING`` before discarding the links — nothing writes them yet, but it will.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.canada_nbac.import_wildfires
   :members:
   :show-inheritance:
