Geospatial Libraries
====================

.. contents::
   :local:
   :depth: 2

Overview
--------

PostGIS is a thin SQL layer over three native libraries, and a GisFIRE server needs
them (plus a few more) installed at the right versions:

.. list-table::
   :header-rows: 1
   :widths: 14 30 56

   * - Library
     - Does
     - Used by
   * - **GEOS**
     - Planar geometry: intersections, buffers, validity, predicates.
     - PostGIS (``ST_Intersects``, ``ST_Buffer``, ...), Shapely.
   * - **PROJ**
     - Coordinate reference systems and datum transformations.
     - PostGIS (``ST_Transform``), pyproj, GDAL, QGIS.
   * - **GDAL/OGR**
     - Reading and writing raster and vector formats (Shapefile, File
       Geodatabase, GeoPackage, GeoJSON, GeoTIFF).
     - The import applications (via GeoPandas/pyogrio), ``ogr2ogr``, QGIS,
       PostGIS raster.
   * - **SpatiaLite**
     - The same spatial types inside SQLite.
     - QGIS, GeoPackage handling, offline datasets.
   * - libxml2, json-c, protobuf-c
     - GML/KML parsing, GeoJSON output, Mapbox Vector Tiles.
     - PostGIS (``ST_GeomFromGML``, ``ST_AsGeoJSON``, ``ST_AsMVT``).

``SELECT postgis_full_version();`` prints exactly which build of each the running
server is linked against — that output, not the installed package list, is the
authority for what the database can do.

Installing the stack
--------------------

Everything at once, on Debian/Ubuntu:

.. code-block:: bash

   sudo apt update
   sudo apt install \
       libgeos-dev libproj-dev proj-bin proj-data \
       libgdal-dev gdal-bin gdal-data gdal-plugins python3-gdal \
       libspatialite-dev spatialite-bin libsqlite3-mod-spatialite \
       libxml2-dev libjson-c-dev libprotobuf-c-dev protobuf-c-compiler \
       libpq-dev postgis postgis-doc

Package by package
^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Package
     - Why it is on a GisFIRE server
   * - ``libgeos-dev``
     - GEOS headers. The runtime (``libgeos-c1``) arrives as a PostGIS dependency;
       the ``-dev`` package adds ``geos-config`` and is required to build anything
       against GEOS from source.
   * - ``libproj-dev``, ``proj-bin``
     - PROJ headers plus the command-line tools ``projinfo``, ``cs2cs`` and
       ``proj`` — the quickest way to check what a transformation between two CRS
       will actually do.
   * - ``proj-data``
     - **The datum-shift grids.** Without them PROJ silently falls back to a
       ball-park transformation: converting ED50 to ETRS89 is then off by metres.
       Any server handling the Spanish, Portuguese or Greek historical datasets
       should have it installed.
   * - ``libgdal-dev``, ``gdal-bin``
     - GDAL/OGR headers and the tools ``ogrinfo``, ``ogr2ogr``, ``gdalinfo``,
       ``gdal_translate``. Indispensable for inspecting a provider's delivery
       before writing an importer for it.
   * - ``gdal-data``, ``gdal-plugins``
     - GDAL's own EPSG/format support files and the optional format drivers.
   * - ``python3-gdal``
     - The Python binding built against the system GDAL, for scripts run outside
       the project virtual environment (see :ref:`geo-python` below).
   * - ``libspatialite-dev``, ``spatialite-bin``
     - SpatiaLite and its ``spatialite`` shell: spatial SQL over SQLite, which is
       what a GeoPackage is underneath.
   * - ``libsqlite3-mod-spatialite``
     - The loadable SpatiaLite module. QGIS and GDAL need it to write GeoPackage
       and SpatiaLite layers.
   * - ``libxml2-dev``, ``libjson-c-dev``
     - XML and JSON support inside PostGIS: ``ST_GeomFromGML``,
       ``ST_GeomFromKML``, ``ST_AsGeoJSON``.
   * - ``libprotobuf-c-dev``, ``protobuf-c-compiler``
     - Vector-tile support (``ST_AsMVT``), for serving layers to web clients.
   * - ``libpq-dev``
     - PostgreSQL client headers, needed when a Python or C package has to be
       compiled against libpq instead of using a binary wheel.
   * - ``postgis``, ``postgis-doc``
     - ``shp2pgsql``, ``pgsql2shp``, ``raster2pgsql`` and the local reference
       documentation.

The extension packages themselves (``postgresql-17-postgis-3`` and
``-postgis-3-scripts``) are installed with the database — see
:doc:`postgresql_database`.

Optional extras
^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo apt install postgresql-17-pgrouting    # network routing on PostGIS geometries
   sudo apt install osm2pgsql                  # bulk OpenStreetMap loading
   sudo apt install pgadmin4                   # graphical database client
   sudo apt install saga grass-core            # raster/terrain analysis toolboxes

Verifying
---------

.. code-block:: bash

   geos-config --version
   proj                                  # prints the PROJ version banner
   gdalinfo --version
   gdal-config --version
   ogrinfo --formats | grep -iE 'gpkg|openfilegdb|esri shapefile'
   spatialite --version

   # is a transformation grid-based (accurate) or a bare datum shift?
   projinfo -s EPSG:4230 -t EPSG:25831 --spatial-test intersects

   # and what the database itself is linked against
   psql -h localhost -p 5433 -U gisfire_user -d gisfire_db -c "SELECT postgis_full_version();"

If ``projinfo`` reports a transformation using a ``.tif``/``.gsb`` grid file, the grids
are installed and being found; if it only offers "Ballpark geographic offset
transformation", ``proj-data`` is missing.

.. _geo-python:

The Python side
---------------

The project virtual environment installs ``pyproj``, ``shapely`` and ``geopandas``
from PyPI, and **their binary wheels bundle their own copies of PROJ, GEOS and GDAL**.
Two consequences worth remembering:

- The project venv does *not* need the system libraries to work. The packages above
  are for the **server and the database**: PostGIS links against them, and the
  command-line tools are what you reach for when diagnosing data.
- The PROJ inside ``pyproj`` has its own grid directory, so a coordinate conversion
  in Python and the same conversion in SQL (``ST_Transform``) can disagree slightly
  if one has the grids and the other does not. ``pyproj`` can download them on demand
  (``pyproj sync``), which is the way to align the two.

The GDAL Python binding is the exception to "just pip install it": it must match the
system ``libgdal`` **exactly**. Either use the distribution's ``python3-gdal``, or
build the matching version against ``libgdal-dev``:

.. code-block:: bash

   pip install "GDAL==$(gdal-config --version)"

GisFIRE avoids that dependency in the importers by going through GeoPandas/pyogrio,
whose wheels ship a self-contained GDAL — including the ``OpenFileGDB`` driver used to
read the Esri File Geodatabases some providers deliver.

QGIS
----

QGIS brings its own build of the whole stack and is installed from its own repository;
it is not configured from this page. See :doc:`development_environment` for the QGIS
virtual environment and the dedicated user profile.
