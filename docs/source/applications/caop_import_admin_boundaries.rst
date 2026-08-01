Import CAOP administrative boundaries
=====================================

Imports the Portuguese administrative divisions — *distritos*, *municípios* and
*freguesias* — from the published CAOP GeoPackages into
:class:`~src.providers.caop.admin_boundary.CaopAdminBoundary` rows, as administrative
levels 1, 2 and 3 below the country. See :doc:`../providers/caop_provider` for the
dataset and why GisFIRE wants it.

.. contents::
   :local:
   :depth: 2

Usage
-----

The DGT publishes four files, one per territory. Point the application at the directory
they were unpacked into:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.caop.import_admin_boundaries -d /path/to/caop

or import one territory on its own:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.caop.import_admin_boundaries \
       -g Continente_CAOP2025.gpkg

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line —
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import the countries first
^^^^^^^^^^^^^^^^^^^^^^^^^^

The CAOP publishes no Portugal polygon — only the three NUTS 1 regions — so the
*distritos* are parented to the country boundary the OCHA import loads at level 0:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ocha.import_admin_boundaries -g adm0_polygons.gpkg
   python3 -m src.apps.imports.admin_boundaries.caop.import_admin_boundaries -d /path/to/caop

Running them the other way round is not a mistake to undo by hand: the *distritos* are
imported as roots, and **re-running the CAOP import once the countries are there links
them**. That is a deliberate step in the application rather than a side effect —
``ON CONFLICT DO NOTHING`` skips rows that already exist, so nothing else would ever
fill the parent in.

What is imported
----------------

=====================  ==========  ======  =========  ==================
Level                  Code field  Length  ``level``  Count in CAOP 2025
=====================  ==========  ======  =========  ==================
*Distrito* / *Ilha*    ``dt``      2       1          29
*Município*            ``dtmn``    4       2          308
*Freguesia*            ``dtmnfr``  6       3          3 259
=====================  ==========  ======  =========  ==================

The code becomes ``source_id``, which is what a fire's
:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.dicofre_code` joins to.

How it works
------------

Four files, four CRSs
^^^^^^^^^^^^^^^^^^^^^

Each published file is in **its own** projected CRS: the mainland in EPSG:3763
(ETRS89 / Portugal TM06), the island groups in EPSG:5014, 5015 and 5016 (PTRA08 / UTM
zones 25N, 26N and 28N). All are ETRS89/PTRA08-based, so reprojecting to EPSG:4326 is a
sub-metre operation — but it cannot be done with one CRS for the country.

``ogr2ogr`` reprojects each file as it stages it, so nothing downstream has to know
which file a boundary came from. The layer names differ per file too (``cont_``,
``ram_``, ``raa_cen_ori_``, ``raa_oci_``), so the layers are discovered from the
GeoPackage's own ``gpkg_contents`` rather than named on the command line.

Three passes, largest division first
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each level is staged from every file into one table, then mapped in turn — *distritos*,
then *municípios*, then *freguesias*. The order is a requirement, not an optimisation: a
boundary's ``parent_id`` points at a row the pass before it wrote.

The parent is found **by code**, not by a spatial test:

.. code-block:: sql

   parent.source_id = left(staging.dtmnfr, 4)

``dt`` is a prefix of ``dtmn`` is a prefix of ``dtmnfr``, without a single exception in
the published data, so this is exact — and it costs nothing next to 3 596 polygon
containment tests, which would also have to cope with parishes that touch their
municipality's border.

Editions live side by side
--------------------------

The DGT republishes the CAOP every year and the boundaries genuinely change. The 2013
reform merged Portugal's parishes from about 4 260 down to some 3 092 and reassigned
their codes, so a DICOFRE from a 2010 fire may name nothing in CAOP 2025, or name a
differently shaped parish.

Each edition is therefore imported as its own
:class:`~src.data_model.data_provider.DataProvider` row — ``DGT`` /
``Carta Administrativa Oficial de Portugal 2025`` — which is what
``uq_admin_boundary_provider_source`` is scoped by:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.caop.import_admin_boundaries \
       -d /path/to/caop2016 --edition 2016

Without that, importing a second edition would import *nothing*: every code would
collide with the first edition's and be silently skipped. The application warns if a
file's name (``Continente_CAOP2025.gpkg``) names an edition other than the one given.

.. note::

   Which edition a fire should be attributed to is not decided here. This application
   imports boundaries; matching a fire to the boundaries in force when it burnt is the
   business of whatever resolves
   :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.dicofre_code`, and it has the
   ``edition`` column to do it with.

Turning a code into a coordinate
--------------------------------

This is what the import is for. The ICNF publishes where a fire started as
administrative codes and names, never as a coordinate, so the parish polygon is what
locates it:

.. code-block:: sql

   SELECT ST_PointOnSurface(boundary.geometry)
   FROM icnf_wildfire fire
   JOIN admin_boundary boundary ON boundary.source_id = fire.dicofre_code
   JOIN caop_admin_boundary caop ON caop.id = boundary.id
   WHERE caop.kind = 'freguesia' AND caop.edition = '2025';

Two things to know about that point:

``ST_PointOnSurface``, not ``ST_Centroid``
    37 mainland parishes are multipart, and a centroid can fall outside a concave or
    multipart polygon — in the sea, or in the neighbouring parish.

It is worth about 2 km
    The median *freguesia* is 15.8 km², an equivalent radius of 2.2 km; the 95th
    percentile is 100.6 km², 5.7 km. Falling back to the *município* when the parish
    code is missing is much weaker: median 212 km², 8.2 km.

API reference
-------------

.. automodule:: src.apps.imports.admin_boundaries.caop.import_admin_boundaries
   :members:
