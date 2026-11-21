Import US Census Bureau administrative boundaries
=================================================

Imports the US states (and DC) and counties (and their equivalents) from the Census
Bureau's 1:500,000 Cartographic Boundary Files into
:class:`~src.providers.united_states_census.admin_boundary.CensusAdminBoundary` rows, as
administrative levels 1 and 2 below the country. See
:doc:`../providers/census_provider` for the files.

.. contents::
   :local:
   :depth: 2

Download
--------

Two files of an edition, from ``https://www2.census.gov/geo/tiger/GENZ<edition>/shp/``
(for 2025, https://www2.census.gov/geo/tiger/GENZ2025/shp/):

- ``cb_2025_us_state_500k.zip`` (3.1 MB): the states and equivalents;
- ``cb_2025_us_county_500k.zip`` (11 MB): the counties and equivalents.

Keep them zipped: the import reads inside the zips. Not TIGER/Line, whose boundaries run
into the sea, and not the 1:5,000,000 or 1:20,000,000 files, which are coarser.

Usage
-----

Point the application at the directory holding the two files. It is searched
recursively, and the files are found by their names, which carry the edition:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.united_states_census.import_admin_boundaries \
       -d /path/to/census

``--edition`` (default ``2025``) names the files to look for and the provider row to
import into, ``US Census Bureau`` / ``Cartographic Boundary Files 2025, 1:500,000``. Each
edition is a provider of its own, so two editions live side by side.

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line —
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``. To run it on
a server or against a server's database, see :doc:`running_on_a_server`; the commands are
those of :doc:`ign_import_admin_boundaries` with this module.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import the countries first
^^^^^^^^^^^^^^^^^^^^^^^^^^

The states are parented to the United States the OCHA import loads at level 0
(``iso_3 = 'USA'``). Imported the other way round, the states are imported as roots, and
re-running this import once the countries are there links them.

What is imported
----------------

=============================  =========  ======================
Level                          ``level``  Count (2025)
=============================  =========  ======================
State (50 and DC)              1          51
County (and equivalents)       2          3 144
=============================  =========  ======================

3 195 boundaries, in about 2 seconds. A county's parent is the state whose ``GEOID`` is
its first two digits. ``source_id`` is the ``GEOID``, ``name`` and ``name_en`` the
``NAME``, and the LSAD code is kept, since it tells apart two entities of one name in one
state (Baltimore County, ``24005``, LSAD ``06``, and the city of Baltimore, ``24510``,
LSAD ``25``).

The five inhabited territories (FIPS 60 and above) and their 91 county equivalents are
left out: OCHA has each of them as a country of its own.

The source is NAD83 (EPSG:4269), reprojected to EPSG:4326 by ``ogr2ogr``. Every imported
polygon is valid, and Alaska's counties add up to the state (1 520 595 km²).

API reference
-------------

.. automodule:: src.apps.imports.admin_boundaries.united_states_census.import_admin_boundaries
   :members:
