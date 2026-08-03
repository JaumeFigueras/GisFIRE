DARPA wildfire import (Catalonia)
==================================

Imports the Catalan burnt area perimeters published by the *Departament d'Agricultura,
Ramaderia, Pesca i Alimentació* into
:class:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire` rows: the generic columns
in ``wildfire``, the Catalan ones in ``darpa_wildfire``.

Thirty-nine published layers, 4,712 features, **860 fires**, 1986 to 2024.

Usage
-----

.. code-block:: bash

   # a directory of published shapefiles, one per year
   python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires \
       -d /path/to/catalunya/

   # one file, zipped or not
   python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires \
       -s incendis2024.zip

   # only the years asked for
   python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires \
       -d /path/to/catalunya/ --year 2023 --year 2024

   # everything, written nowhere
   python3 -m src.apps.imports.wildfires.catalonia_darpa.import_wildfires \
       -d /path/to/catalunya/ --dry-run

Each layer is imported in its own transaction, so a year is either wholly in or wholly out
and a failure on the fifteenth does not throw away the fourteen before it.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``,
``--db-password``.

Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``. It is a system dependency, not a
Python package.

.. note::

   Import :doc:`ocha_import_admin_boundaries` and :doc:`time_zone_import_time_zones`
   first, so that fires get a country and a local start time. Both are optional — the
   perimeters and the dates are worth having on their own — and the import says so at
   ``WARNING`` when either is missing.

What the import does to the published features
-----------------------------------------------

Four filters and one grouping, in that order. The log reports what each one dropped, not
only what survived.

**Everything that is not burnt is dropped.** ``GRID_CODE`` is the class of the raster the
polygons were vectorised from: ``2`` is burnt, ``0`` is background. The 179 background
features are not fires, and they are also where every defect in the dataset lives — the
152 with no code and no date, and the twenty whose ``DATA_INCEN`` is the float
``2,152543589*``. One predicate does the whole of the data cleaning, which is why
``start_date_time`` can be ``NOT NULL`` here with no invented placeholder.

**The text attributes are trimmed**, of the padding a DBF character field always has and
of the ``\r\n`` that six published values end in. Untrimmed, ``31/07/2021\r\n`` is not a
date and four 2021 fires and one 1994 fire vanish with nothing in the log to say so.

**The date is parsed and then checked twice.** ``DATA_INCEN`` is ``dd/mm/yy`` to 2018 and
``dd/mm/yyyy`` from 2019; a two-digit year takes whichever century lands nearer the
layer's own year, which is exact where a fixed pivot would misread a New Year's Eve fire.
``to_date`` is lenient and never says it failed, so the day and month have to survive
being read back — ``31/02`` is rejected rather than becoming the 3rd of March — and the
year has to be the layer's.

**The fragments are dissolved.** Every feature sharing a ``(CODI_FINAL, DATA_INCEN)`` pair
becomes one ``MULTIPOLYGON``, repaired fragment by fragment before the union so that one
self-intersecting ring cannot fail a whole fire. The count is kept in ``part_count``.

.. code-block:: text

   [24/39] incendis1994.shp
   incendis1994.shp: imported 109 fire(s) from 3642 burnt feature(s) in 6s
                     (33.4 polygons per fire)

Why the key is the code *and* the date
---------------------------------------

``CODI_FINAL`` is not an identifier. ``303/22N`` names a fire in Lleida on 19 June 2022
and another in Figueres on 7 July, 190 km apart.

Grouping on the code alone would have unioned the two into a single polygon spanning half
of Catalonia, and a ``UNIQUE`` constraint on the code would have made the import fail on a
perfectly ordinary pair of fires. The pair is unique across the whole archive: 860 of them
for 859 codes, and no code is used in two different years.

Three years are shattered
-------------------------

Most years publish one feature per fire. These do not:

======  ========  =====  ===============
Layer   Features  Fires  Largest fire
======  ========  =====  ===============
1991         306     36  67 polygons
1993          67     21  15 polygons
1994       3,642    109  1,309 polygons
======  ========  =====  ===============

Two character sets, and no ``ENCODING`` option
------------------------------------------------

The ``.dbf`` files are **not all in the same character set** and none carries a ``.cpg``:
1986-1988 and 1991-2012 are ISO-8859-1, while 1989, 1990 and 2013-2024 are UTF-8.

They are not ambiguous, though. Each declares itself in the DBF language-driver byte, and
the correlation over all forty files is exact:

========  =============  ==========================================
LDID      Encoding       Files
========  =============  ==========================================
``0x57``  ISO-8859-1     23, plus 2 that are pure ASCII anyway
``0x00``  UTF-8          15
========  =============  ==========================================

So the import passes **no** ``ENCODING`` open option, and that is a decision rather than an
omission — forcing one overrides the byte.

.. warning::

   :doc:`icnf_import_wildfires` *does* force an encoding, because the ICNF archives carry
   a ``.cst`` file GDAL cannot read. Copying that here breaks half the archive whichever
   way it is forced: ``ENCODING=ISO-8859-1`` turns ``Alfarràs`` into ``AlfarrÃ s`` in the
   newer layers, and ``ENCODING=UTF-8`` turns ``Vallès`` into a name with a replacement
   character in it in the older ones.

The import checks anyway: after staging it looks for both signatures of a mangling in the
municipality names and warns. The rule is one byte deep in a file format from 1986, which
is worth asserting rather than trusting.

The geometry is stored twice
----------------------------

``ogr2ogr`` loads the polygons in EPSG:25831, the grid the department publishes on, and
the mapping keeps them: the dissolved polygon goes into
``darpa_wildfire.perimeter_etrs89_utm31n`` and its ``ST_Transform`` to EPSG:4326 into
``wildfire.perimeter``. Deriving the second from the first is what guarantees the two are
the same geometry.

Both are exposed to QGIS, one view each, and both call the column ``perimeter`` so a style
written against one loads on the other — and on the two ICNF views as well:
``v_darpa_wildfire_4326`` and ``v_darpa_wildfire_25831``. See
:doc:`../setup/database_migrations`.

Three layers publish 3D polygons (2017, 2022 and the duplicate), so everything is
flattened with ``ST_Force2D`` before anything else touches it.

Which files are imported, and which are not
--------------------------------------------

Files are found by name — ``incendis<year>``, two digits or four — and imported oldest
year first.

``incendis10``
    2010, named with two digits where every other loose file uses four. It is the layer
    name inside the department's own ``incendis10.zip``, so it is not a local renaming
    that could be tidied up, and it sorts as 2010 rather than as 10. Every zip is named
    with two digits.

``incendis.shp``
    **Skipped.** It is byte-identical to ``incendis2022.shp`` — same MD5 on the ``.shp``
    and the ``.dbf`` — because it is what unpacking ``incendis22.zip`` produces.
    Importing both would import 2022 twice, with the same codes and the same polygons,
    and nothing downstream would flag it. The **zip** is not skipped: it is a perfectly
    good source of 2022, and only the loose copy beside the four-digit file is redundant.

Anything else
    A file whose name carries no year is skipped and reported at ``WARNING``. Guessing a
    year for it would be worse: a layer imported under the wrong year is a silent error.

.. important::

   The year and the stored ``source_layer`` come from the **file name**, never from the
   GDAL layer inside it, and ``source_layer`` is canonicalised to ``incendis`` plus four
   digits.

   ``incendis22.zip`` is why. Alone among the thirty-nine archives it holds a shapefile
   called plainly ``incendis``, which carries no year at all — so reading the year off the
   layer stops the run dead at 2022, after every earlier year has already committed. And
   without the canonical name, ``incendis22.zip`` and ``incendis2022.shp`` would store two
   different ``source_layer`` values for the same fires, so importing one after the other
   would double the year instead of replacing it.

Re-importing a year
-------------------

A layer already in the database is **replaced**: its fires are deleted and the file is
loaded again, in one transaction. The department does republish — the 2024 archive was
rewritten in September 2025 — and skipping what is already there would mean a corrected
perimeter is silently ignored, which is the failure that is hard to notice.

.. warning::

   Replacing a layer discards any ``egif_wildfire_id`` already bound for that year,
   because the rows themselves go. The import counts the bound rows before deleting them
   and says so:

   .. code-block:: text

      WARNING incendis2022.shp: 18 of the removed fire(s) were bound to an EGIF parte;
              the link went with them. Re-run the binding application for incendis2022.

``--dry-run`` does all of the work, including the replacement, and rolls the transaction
back — so its numbers are the ones a real run would produce.

The EGIF link is not filled in
-------------------------------

``egif_wildfire_id`` exists on every row and this import **never writes it**. Matching the
Catalan perimeters to the Spanish *partes* is a separate application against a rule that
has not been agreed yet; see the note in :doc:`../providers`.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.catalonia_darpa.import_wildfires
   :members:
   :show-inheritance:
