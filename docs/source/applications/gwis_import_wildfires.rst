Import GWIS GlobFire wildfires
==============================

Imports the GWIS *Global Wildfire Database v3* (GlobFire) perimeters into
:class:`~src.providers.gwis.wildfire.GwisWildfire` rows. See :doc:`../providers` for the
model the fires land in.

The dataset is published one zipped shapefile per year at
https://doi.pangaea.de/10.1594/PANGAEA.943975 — 22 archives for 2000-2021, 23,299,416
fires in total. Each layer carries three attributes and nothing else:

==========  ================================================================
``Id``      the fire's identifier — **not unique**, see below
``IDate``   the date the fire started; a bare date, no time
``FDate``   the date it was last observed burning; likewise
==========  ================================================================

Usage
-----

Point it at the directory the archives were downloaded into:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gwis.import_wildfires -d /path/to/zip/

or import a single archive with ``-s``:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gwis.import_wildfires \
       -s Final_GlobFirev3_GWIS_MCD64A1__2021.zip

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line —
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import these first
------------------

Neither is required, and the fires import without them, but both are resolved *at import
time* and cannot be filled in afterwards without re-importing:

:doc:`time_zone_import_time_zones`
    Without the time zone areas every fire is dated in UTC rather than in local time.
    The application warns when the table is empty.

:doc:`ocha_import_admin_boundaries`
    Without the boundaries no fire gets a country. The application warns likewise.

The archives are never unpacked
-------------------------------

The 2021 archive is 316 MB compressed and holds a 291 MB shapefile. Nothing is written
to disk: GDAL's ``/vsizip/`` handler reads the ``.shp`` straight out of the ``.zip``, and
the application only opens the archive with :mod:`zipfile` to find out what is inside it.

The layer name is taken from the shapefile rather than configured, because it carries the
year — ``Final_GlobFirev3_GWIS_MCD64A1__2021`` — and so differs for every archive.

How it works
------------

Each archive is imported in two stages, in a transaction of its own:

1. ``ogr2ogr`` copies the layer verbatim into a staging table, promoting geometries to
   ``MULTIPOLYGON`` and forcing EPSG:4326.
2. One SQL statement resolves the time zone and the country, converts the dates and maps
   the result onto the two tables of the model. The staging table is then dropped.

Since each year is its own transaction, a run interrupted at the tenth file keeps those
ten whole.

.. note::

   The staging table is ``ANALYZE``\ d before the mapping statement runs. ``ogr2ogr``
   leaves it with no statistics at all, and without them the planner sizes a
   million-row table as if it held a handful and picks nested loops for the spatial
   joins.

From a bare date to an instant
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``IDate`` and ``FDate`` have no time. The dataset's convention is that a fire starts at
the beginning of its start date and stops at the end of its end date, *locally*, where it
burnt. Storing that as written would leave dates that cannot be compared with any other
provider's, so the importer resolves them into instants — see
:mod:`src.data_model.wildfire` for the rule the whole project follows:

1. an interior point of the perimeter is looked up in
   :class:`~src.data_model.geography.time_zone.TimeZone` to get the IANA zone name;
2. ``00:00:00`` on ``IDate`` and ``23:59:59`` on ``FDate`` are interpreted in that zone by
   PostgreSQL's ``AT TIME ZONE``;
3. the zone name is stored on the fire, so the published local reading is recoverable
   with ``start_date_time AT TIME ZONE time_zone``.

Because ``AT TIME ZONE`` resolves the offset from each date, the same place gets different
offsets in January and July. A fire in Spain starting on 15 January is stored at UTC+1 and
one starting on 1 July at UTC+2, which is why the zone is kept as a *name* and never as an
offset.

.. note::

   The point looked up is ``ST_PointOnSurface``, not ``ST_Centroid``. The centroid of a
   burn that wraps around an unburnt pocket lands in the pocket — outside the fire — and
   so potentially in the wrong zone, or in none. ``ST_PointOnSurface`` is guaranteed to
   fall inside the polygon.

Fires whose interior point matches no zone are dated in UTC and left with a NULL
``time_zone``, which is what distinguishes them from fires genuinely in UTC.

Which country a fire burnt in
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each fire is attributed to the OCHA level-0 boundary it **overlaps most**, stored on
:attr:`~src.data_model.wildfire.Wildfire.admin_boundary_id`. Resolving it once here rather
than by a spatial join on every later query is the whole point — see the note on
:class:`~src.data_model.geography.admin_boundary.AdminBoundary`.

A fire straddling a border therefore goes to the country holding the larger share of the
burnt area. Computing that share means intersecting polygons, which is expensive against
country-sized geometries, so the statement does it only where it matters: candidates are
first collected by an index-backed ``ST_Intersects``, and the intersection areas are
computed solely for the fires that came back with more than one. Practically every fire
comes back with exactly one and costs nothing extra.

Re-running the import
^^^^^^^^^^^^^^^^^^^^^

.. warning::

   **Re-running duplicates.** Unlike :doc:`ocha_import_admin_boundaries`, this import is
   not idempotent, and cannot be.

GWIS ``Id`` values repeat across genuinely different fires — 359 times over the published
dataset, some spanning two years' files. ``Id`` 24935861 is a fire in Papua New Guinea on
8 January 2021 *and* one in California on 23 February. There is therefore no key by which
a fire already imported can be told apart from a new one that happens to share an
identifier, so nothing is skipped: importing a file twice stores it twice.

Treating a repeated ``Id`` as "already imported" was considered and rejected — it would
silently discard the second fire of each of those 359 pairs, which is real data. The
application warns when the database already holds GWIS fires. After an interrupted run,
restart it from the archives that did not get in.

The staging schema
^^^^^^^^^^^^^^^^^^

As for the boundary import, the staging table goes in a ``staging`` schema rather than
``public``, so that Alembic autogenerate cannot see it and write a ``DROP TABLE`` for it
into the next migration. ``--keep-staging`` leaves it behind for inspection;
``--staging-schema`` and ``--staging-table`` move it.

The data provider
^^^^^^^^^^^^^^^^^

Created on first run and reused afterwards, looked up by the ``(name, product)`` pair:

==============  =========================================================
Name            ``GWIS``
Full name       Global Wildfire Information System
Product         ``Global Wildfire Database v3``
==============  =========================================================

The product carries the version deliberately: GlobFire v3 and a future v4 are different
datasets with different fire identifiers and must not share a provider row.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.gwis.import_wildfires
   :members:
   :show-inheritance:
