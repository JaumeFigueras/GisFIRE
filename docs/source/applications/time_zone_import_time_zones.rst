Import time zone areas
======================

Imports IANA time zone polygons into
:class:`~src.data_model.geography.time_zone.TimeZone` rows, so that a coordinate can be
turned into a zone name.

Why this is needed at all
-------------------------

The IANA time zone database — the thing behind Python's :mod:`zoneinfo` and behind
PostgreSQL's ``AT TIME ZONE`` — defines a zone as a *name* with a history of offsets and
daylight-saving rules. It says nothing about **where on Earth** that name applies.

So neither Python nor PostgreSQL can answer "which zone is this fire in?", and any
provider that publishes local wall-clock time cannot be converted to an instant without a
set of polygons drawn by somebody else. GWIS is exactly such a provider: its dates are
bare, and mean local midnight (see :doc:`gwis_import_wildfires`).

Getting the data
----------------

`timezone-boundary-builder <https://github.com/evansiroky/timezone-boundary-builder>`_ is
the de facto standard set: it derives the polygons from OpenStreetMap and publishes a
release per IANA update. From the latest release at
https://github.com/evansiroky/timezone-boundary-builder/releases, download

.. code-block:: text

   timezones-with-oceans.shapefile.zip

Every release ships six ``.shapefile.zip`` assets (plus the same six as GeoJSON), which
combine two independent choices. Pick the wrong one and the import still succeeds — it
just stores a different set of zone names.

**Coverage** — with or without ``with-oceans``:

``with-oceans``
   Land plus the maritime areas out to the EEZ. **Use this one.** Without it a coordinate
   at sea matches no zone at all, and every fire on a coastline or an island whose
   interior point falls just offshore would silently fall back to UTC.

**Zone set** — the ``-1970`` and ``-now`` suffixes, which merge zones that never actually
differ:

*(no suffix)*
   Every distinct IANA zone name. **Use this one.**

``-1970``
   Merges zones that have agreed on timekeeping since 1970-01-01, the point at which the
   IANA database itself stops guaranteeing that separate names mean anything. Fewer and
   simpler polygons, but names disappear: a fire in Norway comes back as
   ``Europe/Berlin``, because ``Europe/Oslo`` has had identical offsets and DST rules
   since 1970. Correct arithmetic, confusing data — and wrong outright for any provider
   with pre-1970 dates.

``-now``
   Merges zones agreeing as of the release date. Suitable only for "what time is it there
   right now" and unfit here, where dates are historical.

.. note::

   The suffix goes after the coverage in the file name — ``timezones-with-oceans-1970``,
   not ``timezones-1970-with-oceans``.

Usage
-----

The database has to be at the latest revision first — the ``time_zone`` table is created
by a migration, not by the importer:

.. code-block:: bash

   make migrate

Then run the import once, and again whenever a newer release is wanted:

.. code-block:: bash

   python3 -m src.apps.imports.time_zones.timezone_boundary_builder.import_time_zones \
       -s timezones-with-oceans.shapefile.zip

The archive is read in place — GDAL's ``/vsizip/`` handler reads the shapefile straight
out of it — so the 100 MB download needs no temporary space and does not have to be
unpacked.

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line —
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

How it works
------------

The same two stages as the other importers: ``ogr2ogr`` copies the layer into a staging
table, then one SQL statement maps it onto the model and the staging table is dropped.

The mapping groups by zone name, because nothing guarantees one feature per zone — the
``with-oceans`` build splits some maritime zones into several bands. The parts are
combined with ``ST_Collect`` rather than ``ST_Union``: they are disjoint by construction,
so there is nothing to dissolve, and collecting them costs a fraction of what unioning
polygons this large would.

.. note::

   The result is passed through ``ST_CollectionExtract(..., 3)`` and not ``ST_Multi``.
   Collecting geometries that are *already* multipolygons nests them, so ``ST_Collect``
   returns a ``GEOMETRYCOLLECTION``, which ``ST_Multi`` does not flatten and the column
   rejects. Extracting the polygons pulls every ring back up into one ``MULTIPOLYGON``.

Re-running the import
^^^^^^^^^^^^^^^^^^^^^

Re-running is how the table is **upgraded** to a newer IANA release. The mapping uses
``ON CONFLICT (name) DO UPDATE``, so a zone whose area changed ends up with the new
geometry, and a zone that is new is added. It reports the number of zones written, which
is the whole table rather than zero — unlike :doc:`ocha_import_admin_boundaries`, which
skips conflicts.

Zones that IANA has *retired* are not deleted, since nothing in a release says which names
disappeared. They are harmless: they no longer match any newer zone's area, and fires
already located against them keep a name PostgreSQL still resolves.

Zone names and the server's tzdata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Only the zone *name* is stored on an event, never an offset, because the offset depends on
the date. That makes the name useless unless PostgreSQL recognises it, so
:doc:`gwis_import_wildfires` checks the whole table against ``pg_timezone_names`` before
importing anything and refuses to start if any name is unknown — which happens when the
imported release is newer than the server's own tzdata.

Nothing references this table by foreign key: models store the resolved IANA name as text.
A release can therefore be replaced without rewriting the events located against it.

API reference
-------------

.. automodule:: src.apps.imports.time_zones.timezone_boundary_builder.import_time_zones
   :members:
   :show-inheritance:
