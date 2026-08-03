REDIAM wildfire import (Andalusia)
===================================

Imports the Andalusian burnt area perimeters — the REDIAM *Perímetros de incendios
forestales* product, 2008 onwards — into
:class:`~src.providers.andalusia_rediam.wildfire.RediamWildfire`, and the published
ignition points into :class:`~src.providers.andalusia_rediam.ignition.RediamIgnition`.

GisFIRE's second regional perimeter source, after :doc:`darpa_import_wildfires`, and the
complement of :doc:`egif_import_wildfires`: EGIF publishes hectares on a report form and
never a polygon; this publishes the polygon.

Usage
-----

Point it at the directory the download was unpacked into, or at one file:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \
       -d /path/to/andalusia/InfGeografica/InfVectorial/Shapes/

   python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \
       -s PERIMETROS_COR_2008_2025.shp

   # only some years, and without reading the yearly layers for ignition points
   python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \
       -d /path/to/Shapes/ --year 2024 --year 2025

   python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \
       -d /path/to/Shapes/ --skip-ignitions

   # everything, rolled back
   python3 -m src.apps.imports.wildfires.andalusia_rediam.import_wildfires \
       -d /path/to/Shapes/ --dry-run

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``,
``--db-password``. Requires the ``ogr2ogr`` binary (GDAL) on ``PATH``.

.. important::

   Import the OCHA boundaries (:doc:`ocha_import_admin_boundaries`) and the time zone
   areas (:doc:`time_zone_import_time_zones`) **first**. Both are resolved at import time
   and cannot be filled in afterwards without re-importing.

What a run looks like
---------------------

.. code-block:: text

   INFO Importing perimeters from PERIMETROS_COR_2008_2025.shp
   INFO PERIMETROS_COR_2008_2025.shp: Replacing 18 year(s) (2008-2025): removed 0 fire(s)
   INFO PERIMETROS_COR_2008_2025.shp: 55 feature(s) are a second copy of a fire already
        in the layer and were dissolved into it
   WARN PERIMETROS_COR_2008_2025.shp: 2 fire(s) are published twice with different burnt
        areas; the largest of each was stored
   INFO PERIMETROS_COR_2008_2025.shp: imported 907 fire(s) from 962 feature(s) over
        2008-2025 in 14s
   INFO Reading 18 yearly layer(s) for ignition points
   INFO PERIMETROS_COR_2021.shp: imported 65 ignition point(s), 28 of them inside their
        own perimeter
   INFO PERIMETROS_COR_2022.shp: imported 58 ignition point(s), 15 of them inside their
        own perimeter
   INFO PERIMETROS_COR_2023.shp: imported 40 ignition point(s), 24 of them inside their
        own perimeter
   INFO PERIMETROS_COR_2024.shp: imported 36 ignition point(s), 20 of them inside their
        own perimeter
   INFO Imported 907 fire(s) and 199 ignition point(s) in 20s

That is the whole published archive: **962 features, 907 fires, 199 ignition points**, in
twenty seconds.

Two kinds of file, and both are read
------------------------------------

The service publishes one shapefile per year **and** one holding the whole series, and
this import reads both — for different things.

``PERIMETROS_COR_2008_2025``
    The combined layer, and the source of every **perimeter**. It is the file the service
    republishes as the archive grows, its attribute names are spelled one way, and reading
    one layer cannot half-import a series.

``PERIMETROS_COR_2021`` … ``PERIMETROS_COR_2024``
    Read for the one thing the combined layer does not carry: ``X_INIC`` and ``Y_INIC``,
    the **ignition point**. The other fourteen yearly layers are staged, found to publish
    no coordinate, and skipped — which is the only way to know, the attribute list being a
    property of the file rather than of its name.

The yearly layers' fires are **not** imported: they are the same fires the combined layer
holds, and importing both would import every year twice. ``-s PERIMETROS_COR_2022.shp``
does import that year's fires, because then it is the only file there is.

.. note::

   The yearly layers are also where the schema wobbles: 2015 upper-cases ``MUNICIPIO`` and
   ``PROVINCIA``, 2020 and 2021 truncate ``SUP_PASTIZ`` to ``SUP_PASTI``, and 2021
   publishes the coordinates as integers where later years use reals. Reading the
   perimeters from the combined layer sidesteps all of it.

What a re-import replaces: the years, not the file
--------------------------------------------------

The name of the combined layer carries the range it covers, so next year's publication is
``PERIMETROS_COR_2008_2026`` rather than a new edition of this file name.

An import that replaced *the layer it is re-importing* — which is what
:doc:`darpa_import_wildfires` does, because there the layer name is a year — would
therefore add a second copy of every fire the first time the range grew, with the same
codes and the same polygons and nothing downstream to notice.

So this import replaces **the years it finds inside the layer it is reading**: the staged
data is asked which years it holds, every stored fire of those years is deleted, and the
layer is loaded, all in one transaction.
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.source_layer` records which
file a fire came from and is not what anything keys on. A test covers exactly this: import,
rename the file to a longer range, import again, and the count must not move.

Deleting a year takes its ignition points with it — they belong to those fires and nothing
else references them.

.. warning::

   Replacing a year discards any
   :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id` already
   bound for it, because the rows themselves go. The import counts the bound rows before
   deleting them and says so at ``WARNING``; re-running the binding application afterwards
   is what puts them back.

962 features are 907 fires
--------------------------

55 codes are published twice — 2 in 2024, 53 in 2025. The mapping groups on
``(CODIGO, FECHA_INC)``, unions the geometries and keeps the count in
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.part_count`.

In 54 of the 55 the two rows are the same fire with the same footprint, differing only in
the case of the names, and the union is the shape either row already had. In the remaining
one, ``IIFF2025210122``, they are two genuinely different mappings — 363.8 ha and 517.4 ha
— and the union is 527.5 ha.

Where a duplicated pair disagrees, the mapping has to choose:

* **the names** are taken with ``min``, which is deterministic and nothing more. The 2025
  pairs really do disagree here (``LUBRIN`` beside ``Lubrín``) and neither spelling is more
  published than the other.
* **the three areas** are taken with ``max``, and a pair that disagrees is counted and
  reported at ``WARNING``. Two do. ``max`` is not a claim that the larger figure is right;
  it is deterministic, it is reported, and refusing to import a fire the service published
  twice would be worse.

The geometry
------------

``ogr2ogr`` loads the polygons in the CRS they were published in, and the mapping keeps
them: the dissolved polygon goes into ``rediam_wildfire.perimeter_etrs89_utm30n`` and its
``ST_Transform`` to EPSG:4326 into ``wildfire.perimeter``. Deriving the second from the
first is what guarantees the two are the same geometry — a test asserts ``ST_Equals`` on
them.

71 of the 962 features have a self-intersecting ring, so each one goes through
``ST_MakeValid`` **before** the union: a bad ring would otherwise fail a whole fire rather
than one feature. ``ST_Force2D`` comes first, which costs nothing and means a 3D layer
cannot surprise the union later.

EPSG:25830, and not the 3042 in the ``.prj``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The published ``.prj`` is an ESRI string with no EPSG code:

.. code-block:: text

   PROJCS["ETRS_1989_ETRS-TM30", ... PARAMETER["Central_Meridian",-3.0] ... ]

GDAL resolves it to **EPSG:3042** — ETRS89 / UTM 30N declared *northing-easting* — while
the coordinates in the files are easting-northing, as GDAL itself reports
(``Data axis to CRS axis mapping: 2,1``).

The load forces EPSG:25830: the same projection with the conventional axis order, which is
what the data follows and what QGIS and PostGIS use for the Spanish peninsular grid.
Storing 3042 would store a declaration the geometry does not obey and invite PROJ to swap
the axes on the next transform.

The fixture in the tests writes the published ``.prj`` verbatim and then asserts that the
stored easting is still 215,000 m and the northing still 4,117,000 m — so this is checked
rather than assumed.

The ignition point is a second pass
-----------------------------------

After the perimeters, each ignition-bearing yearly layer is staged and mapped in a
transaction of its own. A point is stored when its ``(CODIGO, FECHA_INC)`` matches a
perimeter already imported; one that matches nothing is counted and reported, because it
means the two files disagree about which fires exist. On the published data none does.

The published easting and northing are kept as published, and the EPSG:4326 point is built
from them in SQL — the same rule as the perimeter, for the same reason.

.. warning::

   **The point is not checked against the perimeter, and often does not agree with it.**
   88 of the 201 published points fall inside their own fire; the rest are outside by a
   metre to three kilometres, and one 2022 point is 19.5 km away.

   Nothing corrects that. A start point reported by the service and a perimeter mapped
   afterwards are two observations, and where they disagree the disagreement is the
   information — which is why the ignition is a row of its own. The import reports how many
   are inside so the number is visible rather than discovered later.

Under ``--dry-run`` the points can match nothing, because the perimeters they would match
were rolled back a moment earlier. The log says so in those words rather than warning about
a disagreement that is an artefact of the dry run.

The encoding
------------

Every ``.dbf`` carries a ``.cpg`` and the DBF language-driver byte is ``0x00`` throughout,
so GDAL reads the sidecar and gets it right. The import passes **no** ``ENCODING`` open
option and checks the staged municipality and province names for the two signatures of a
mangling afterwards — ``Ã`` for UTF-8 read as Latin-1, U+FFFD for the reverse.

That is the Catalan import's decision and the Catalan import's check, reached here for a
different reason: there the files describe themselves in the language-driver byte, here in
the ``.cpg``. One file is the odd one out — ``PERIMETROS_COR_2025.cpg`` says ``1252`` where
every other says ``UTF-8`` — and it is a yearly layer, so it is only read if it is asked for
by name.

Two staging details
-------------------

Both are small, both took a failed run to find, and both are in shared code with a default
that leaves every other importer alone:

``FID=ogc_fid``
    The combined layer publishes an attribute called ``fid`` — a Real row number — which
    collides with the serial key GDAL creates. Without the rename GDAL reports
    ``ERROR 1: Wrong field type for fid`` on every run and numbers the rows itself anyway.

``PRECISION=NO``
    The 2024 yearly layer declares ``X_INIC`` as ``Real (19.15)``, which the PostgreSQL
    driver renders as ``numeric(19,15)`` — four digits before the point, where the published
    easting ``596812.000001`` has six. Without this the load of that layer fails outright
    with a numeric field overflow. The declared widths are fiction throughout
    (``Real (24.15)`` on an area of 26.9 ha), so nothing is lost by ignoring them.

The EGIF link
-------------

:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id` is left
``NULL`` on every row, with ``match_method``, ``match_confidence`` and ``matched_at``
beside it. This import never writes any of the four, and a test asserts it.

That is not for want of a join key — ``CODIGO`` *is* the EGIF ``report_number``, on all 962
features — but the binding is inference rather than transcription, it belongs in an
application that can record how each link was arrived at, and the rules for this dataset
have not been agreed. See :doc:`darpa_bind_egif_wildfires` for what that application looks
like for Catalonia.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.andalusia_rediam.import_wildfires
   :members:
   :show-inheritance:
