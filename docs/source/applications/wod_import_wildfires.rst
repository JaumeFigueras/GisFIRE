WOD wildfire import (New Zealand)
=================================

Imports the New Zealand *Wildfire Occurrence Database*: one folder, ``WOD_shp_*``, holding
two shapefiles in NZTM2000 — ``WOD_points`` and ``WOD_polygons`` — with **128,020 records
over 1931-2025**, every one of them carrying 109 attributes. See :doc:`../providers` for the
dataset.

Each record becomes **four rows**: the record (:doc:`../providers/wod_wildfire`), its
published point (:doc:`../providers/wod_ignition`), and the terrain and weather the
compilers attached (:doc:`../providers/wod_terrain`, :doc:`../providers/wod_weather`).

Usage
-----

.. code-block:: console

   python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s /path/to/WOD_shp_1931-2025

   python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s WOD_shp_1931-2025 --all-years

   python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s WOD_shp_1931-2025 --year 2024 --dry-run

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` and the
:doc:`time zone areas <time_zone_import_time_zones>` first, so a fire gets a country and a
zone from its point. Without them every fire is dated in the fallback zone — mainland, or
Chatham by district — and has no country.

``-s`` is the release's folder; both shapefiles have to be in it, because importing one
would replace every year with half its records. By default the import reads from **1998**,
when the FENZ records start — before that the WOD is DOC alone and, in its authors' words,
does not give good overall coverage. ``--all-years`` imports from 1931, ``--from-year``
moves the cut anywhere, and ``--year`` (repeatable) re-imports single years.

The whole release imports in about two and a half minutes on a database with neither the
boundaries nor the time zone areas loaded; the spatial lookups add to that.

Where to run it
---------------

The same command can be run in three ways, depending on where the data and the database
are. :doc:`running_on_a_server` explains every part of the commands below.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s /path/to/WOD_shp_1931-2025

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
The release folder has to be copied to the server first (``rsync -avP``), and the
paths below are paths on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s /path/to/WOD_shp_1931-2025 \
       > new_zealand_wod_import_wildfires.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f new_zealand_wod_import_wildfires.log    # Ctrl-C stops tail, not the run
   pgrep -af new_zealand_wod.import_wildfires    # still running?
   grep -E 'ERROR|WARNING' new_zealand_wod_import_wildfires.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. The files stay on your machine and every geometry goes over the network, so
it is slower than running it on the server. The password is read into the environment
rather than passed as ``--db-password``, which would show in ``ps`` and in the shell
history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.wildfires.new_zealand_wod.import_wildfires \
       -s /path/to/WOD_shp_1931-2025 \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Nothing is refused
------------------

Unlike most imports in GisFIRE, **no record in scope is dropped.** Every decision about the
dirt in this dataset is *keep and correct*, and every correction is counted and reported:

============================================  ====================================  =====
Published                                     Stored                                 2025
============================================  ====================================  =====
``-9999`` in any column, ``NA:NA``, ``Null``  ``NULL``                                  —
``WOD1e+05``                                  ``WOD100000``                             1
A negative ``AreaHa``                         0                                         1
An invalid polygon                            made valid with ``ST_MakeValid``         52
A record with no time (DOC)                   local midnight, ``report_time`` NULL  5,482
A point in the sea                            as published, no country                 92
…on the placeholder coordinate                as published                             15
A Chatham Islands record                      dated in ``Pacific/Chatham``             18
============================================  ====================================  =====

and the last column is what the real run over the 2025 release reported, with
``--all-years``: 128,020 records read and 128,020 stored, each with its terrain and weather
row; 538 lightning, 5 natural, 106,299 human and 21,178 unknown; 8 report times in a
daylight-saving overlap and none in a gap. The point of a point record was never found to
differ from its published ``X``/``Y``.

The point is always the published ``X``/``Y``
    For polygon records too: it is the location of the original record, neither the
    polygon's centroid nor its origin — only one in five falls inside its own polygon — and
    it is stored untouched.

What the import does refuse is a release it does not understand
---------------------------------------------------------------

Before anything is deleted, the staged records are checked against what the model can
hold, and the run stops — listing up to ten offending values per check — if any fails:

* an identifier that is not a WOD identifier, or two records sharing one once repaired;
* an ``IgnSource`` that :data:`~src.providers.new_zealand_wod.CAUSE_MAP` does not classify;
* a record with no year, a date that does not exist, or a time that is neither ``HH:MM``
  nor ``NA:NA``;
* a record with no location;
* a fire year (``StartFY``) that is not the year or the one before;
* a source, season, area category or ENSO phase outside the published vocabulary, or a
  fire danger class that is not a whole number from 1 to 5.

.. important::

   **An unmapped cause stops the run.** A future release's new spelling has to be added to
   :data:`~src.providers.new_zealand_wod.CAUSE_MAP` and classified by a person: a new
   lightning spelling silently counted as *unknown* is exactly the mistake the cause classes
   exist to prevent. The first run of this import against the real data is what found
   ``Flare: Warning, Safety, Boat``, which the dataset analysis had missed.

The rules are Python's, applied in SQL
--------------------------------------

The identifier repair and the cause classification are defined once, in
:mod:`src.providers.new_zealand_wod`. The import reads the distinct published values from
the staged table, runs them through
:func:`~src.providers.new_zealand_wod.wod_id` and
:func:`~src.providers.new_zealand_wod.fire_cause`, and hands the results to the transform as
arrays — so the SQL applies exactly the Python rule and nothing is written twice.

The two layers become one staging table
---------------------------------------

Both shapefiles are loaded by ``ogr2ogr`` into one table, points first and polygons
appended, with a ``GEOMETRY`` column that holds both. Several numeric attributes are
published as **text** — ``WS``, every ``FDC*``, ``HFI*`` and ``ROS*`` — and are converted
there, once. ``Day``, ``Month`` and ``Year`` are published as ``Integer64`` and are
converted to ``integer`` for ``make_date``: the real run is what found that, the test
fixture's integers arriving as ``integer`` already.

A year is the unit, and a year is the step
------------------------------------------

The staged release is transformed **one year per statement, each in a transaction of its
own**, as :doc:`nfdb_import_wildfires` does and for its reason: one statement over the whole
archive materialises the row set several times over.

.. code-block:: text

   28 year(s) to import: 1998-2025
   [1/28] 1998: imported 1995 fire(s) in 4s
   ...

Replacing a year deletes its fires — and any fire elsewhere whose ``wod_id`` the year now
carries, because the identifier is unique and stable and a record a new release moved to
another year would otherwise collide with its own old copy — and writes the staged ones in
the same transaction. The terrain and weather rows go with their fire by ``ON DELETE
CASCADE``. ``--dry-run`` rolls every year back.

.. danger::

   **Never run two imports against the same staging table at once.** A run holds a
   PostgreSQL advisory lock on it for its whole length and a second run is refused; if the
   staged table changes underneath a run anyway, the year being written is not committed.
   See :doc:`nfdb_import_wildfires` for the incident that taught the project this.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.new_zealand_wod.import_wildfires
   :members:
   :show-inheritance:
