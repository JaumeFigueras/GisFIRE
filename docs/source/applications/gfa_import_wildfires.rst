Import GFA wildfire perimeters
==============================

Imports the *Global Fire Atlas* fire perimeters into
:class:`~src.providers.gfa.wildfire.GfaWildfire` rows — one per fire, with the generic
columns in ``wildfire`` and the Atlas measurements in ``gfa_wildfire``.

.. contents::
   :local:
   :depth: 2

Usage
-----

Migrate the database first — the ``ignition``, ``gfa_ignition`` and ``gfa_wildfire``
tables are created by migrations, not by the importer — then point it at the directory the
shapefiles were unpacked into:

.. code-block:: bash

   make migrate
   python3 -m src.apps.imports.wildfires.gfa.import_wildfires -d /path/to/SHP_perimeters/

or import a single year with ``-s``:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gfa.import_wildfires \
       -s GFA_v20260408_perimeters_2021.shp

For the full set, add ``--jobs`` to import several years at the same time. It is
off by default (``1``) and makes a large difference on a multi-core server; see
:ref:`gfa-jobs` below:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gfa.import_wildfires -d /path/to/SHP_perimeters/ --jobs 4

Unlike the GWIS download, the Atlas ships **loose shapefiles**, one per year, rather than
one archive each — so ``-d`` globs ``*.shp`` in the directory. A ``.zip`` is accepted too,
and read in place without unpacking.

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Where to run it
---------------

The same command can be run in three ways, depending on where the data and the database
are. :doc:`running_on_a_server` explains every part of the commands below.

``--jobs 4`` imports four files at a time (see :ref:`gfa-jobs`). On a server with more
cores and a tuned cluster, 6 is a reasonable next step. Leave it out for a serial run.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.wildfires.gfa.import_wildfires \
       -d /path/to/SHP_perimeters/ --jobs 4

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
The files have to be copied to the server first (``rsync -avP``), and the
paths below are paths on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.wildfires.gfa.import_wildfires \
       -d /path/to/SHP_perimeters/ --jobs 4 \
       > gfa_import_wildfires.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f gfa_import_wildfires.log    # Ctrl-C stops tail, not the run
   pgrep -af gfa.import_wildfires    # still running?
   grep -E 'ERROR|WARNING' gfa_import_wildfires.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. The files stay on your machine and every geometry goes over the network, so
it is slower than running it on the server. The password is read into the environment
rather than passed as ``--db-password``, which would show in ``ps`` and in the shell
history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.wildfires.gfa.import_wildfires \
       -d /path/to/SHP_perimeters/ --jobs 4 \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

.. _gfa-jobs:

Importing several years at once
-------------------------------

``--jobs N`` (``-j N``) imports ``N`` shapefiles at the same time, each in its own
process with its own database connection. The default is ``1``, a serial run, so **on a
server it has to be asked for**:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gfa.import_wildfires -d /path/to/SHP_perimeters/ --jobs 4

Why it helps
^^^^^^^^^^^^

Each year spends most of its time in one ``INSERT ... SELECT``: grouping the parts of
every fire, repairing the geometries with ``ST_MakeValid``, and joining the ignition
points against the time zones and the country boundaries. **PostgreSQL does not use a
parallel plan for a statement that writes**, so that statement runs on one core
however many the server has. A serial import of the whole Atlas uses one CPU of the
server and leaves the rest idle. Opening more connections, each importing a different
year, is the only way to put more cores on the work. The GWIS page shows the ``EXPLAIN``
that proves it: :doc:`gwis_import_wildfires`.

Processes are used rather than threads, but not because of the GIL. Both slow phases
release it anyway: the ``ogr2ogr`` load waits on a subprocess and the mapping waits on
the socket. A process per worker simply gives each one its own engine and connection
pool, created after the fork, so no connection is ever shared between two processes.

Why it is safe
^^^^^^^^^^^^^^

- **No two workers can collide on a fire.** ``fire_ID`` carries the year (``2xxxxxxx``
  for 2002 … ``26xxxxxxx`` for 2026), so no identifier appears in two files. The
  "skip fires already held" check of one worker can never race with the insert of
  another.
- **Each worker stages into its own table**: ``staging.gfa_perimeters_00``, ``_01``, …
  ``ogr2ogr -overwrite`` recreates the staging table on every load, so years sharing one
  table would destroy each other's work. A serial run keeps the plain
  ``staging.gfa_perimeters``.
- **Each year is still its own transaction.** A failing year does not stop the others:
  they finish and are kept, the failures are listed together at the end, and the exit
  code is non-zero.

What changes in the output
^^^^^^^^^^^^^^^^^^^^^^^^^^

- The progress bars are suppressed, since several drawn at once cannot be read. Each log
  line is prefixed with its shapefile instead, so interleaved lines can still be told
  apart, and a ``[k/N shapefiles done]`` line marks each year as it completes.
- Years finish in whatever order they finish, not in date order.

How many jobs
^^^^^^^^^^^^^

- **Never more than the number of shapefiles.** Asking for more just runs as many workers
  as there are files, and a single ``-s`` file is always a serial run.
- **Limited by server cores, not client cores.** Each worker keeps roughly one server
  core busy with its ``INSERT ... SELECT``. On top of that it has a Python process that
  mostly waits and an ``ogr2ogr`` that is busy only during the load. When the importer
  runs on the database server itself, as in the SSH form, leave a couple of cores free
  for the WAL writer, checkpointer and autovacuum.
- **Past about 4–6 the gain flattens.** The workers share the WAL, the disk and the GiST
  indexes on the wildfire and ignition geometries, so beyond a point more workers
  mostly wait on each other. As a starting point, use ``--jobs 4`` on an 8-core server
  and ``--jobs 6`` on 12 cores. Then watch ``top``: if the ``postgres`` processes are
  not each near 100 % CPU, the bottleneck is I/O and more jobs will not help.
- **Tune the cluster first.** Every worker is another connection running spatial joins
  with its own ``work_mem``, and they all write WAL at once. On a stock configuration
  (``work_mem`` 4 MB, ``max_wal_size`` 1 GB) the joins spill to disk and checkpoints
  come back to back, and N workers make both N times worse. Apply
  :ref:`pg-tuning` before raising ``--jobs``. Memory is rarely the limit on a large
  server: six workers at ``work_mem = 64MB``, a few operations each, need well under
  2 GB.

Stopping a serial run to restart it in parallel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Because ``fire_ID`` is unique and fires already held are skipped, a GFA import can be
interrupted and restarted at any time. Kill the running import. The year in progress
is rolled back, since it is one transaction. Start it again with ``--jobs``. The years
already imported are staged and skipped: every fire is found to be held already and none
is inserted. Only the remaining years do real work. The warning that the database
already holds GFA fires is expected on the restarted run.

Import these first
------------------

Neither is required, and the fires import without them, but both are resolved *at import
time* and cannot be filled in afterwards without re-importing:

:doc:`time_zone_import_time_zones`
    Without the time zone areas every fire is dated in UTC rather than in local time.

:doc:`ocha_import_admin_boundaries`
    Without the boundaries no fire gets a country.

Three properties of this dataset shape the mapping
--------------------------------------------------

One fire is several features
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The shapefiles have geometry type ``Polygon``, not ``MultiPolygon``. A fire whose burnt
area is in several pieces is therefore published as **several features sharing one**
``fire_ID``, repeating every attribute — the same ignition point, the same ``size``, the
same dates — and differing only in geometry.

The import groups by ``fire_ID`` and collects the parts into one ``MULTIPOLYGON``, so one
fire is one row. This matters beyond tidiness: ``size`` is the size of the *whole* fire
repeated on each part, so ``SUM(size)`` over ungrouped features silently over-counts.

The attributes are aggregated with ``min()``, which is not a choice about which value to
keep — the parts carry identical values, so every aggregate returns the same answer and
``min()`` is simply the cheapest way to write "the value they all share".

``fire_ID`` is a real key, and is used as one
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It encodes the year — ``2xxxxxxx`` for 2002 through ``26xxxxxxx`` for 2026 — so it does
not collide between files, and once the multipart features are grouped it does not repeat
within one either. ``gfa_wildfire.gfa_id`` is therefore ``UNIQUE``, and the import
**skips fires it already holds**:

* re-running it is a no-op that reports ``0 imported``, not a second copy;
* adding a newly published year to a database holding the earlier ones is the normal way
  to use it, and needs no special flag.

This is the opposite of :doc:`gwis_import_wildfires`, whose identifier names genuinely
different fires when it repeats and which consequently cannot skip anything and warns
instead.

The parts of a multipart fire overlap, and are unioned
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**134,301 fires across 2002-2026** are published as several features sharing a
``fire_ID``, and those features do not merely touch — they cover very nearly the same
ground twice. Grouping them is therefore not enough: they have to be **unioned**, or the
shared ground is counted once per part and the fire comes back at nearly double its
published ``size``.

.. code-block:: text

   fire_ID 140400774, two parts     published size   686 ha
     ST_MakeValid(ST_Collect(...))                  1368.37 ha     <- the overlap, twice
     ST_UnaryUnion(...)                              684.18 ha     <- agrees with size

.. warning::

   ``ST_MakeValid`` looks as though it should be enough, and for overlapping *polygons*
   it is. But the staging table is loaded with ``ogr2ogr -nlt MULTIPOLYGON``, so what
   ``ST_Collect`` receives are **MultiPolygons**, and making a nested collection valid
   does not dissolve overlaps *between* its members. ``ST_UnaryUnion`` does, and is a
   no-op for the single-part fires that are the overwhelming majority.

   This was wrong until it was caught by comparing the measured area against the Atlas's
   own ``size``, which is exactly what
   :attr:`~src.providers.gfa.wildfire.GfaWildfire.size_km2` is kept for. A database
   imported before the fix has inflated perimeters for those 134,301 fires and needs them
   re-imported.

About one perimeter in six is invalid
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The polygons are traced around MODIS pixels and self-intersect where the trace doubles
back on itself — 12,357 of the 84,496 features in the 2026 file, 15%. They are repaired
with ``ST_MakeValid`` on the way in, so that the country join here and everything
downstream is safe against ``TopologyException``.

.. note::

   The repair can split a bowtie into two polygons, so its result goes through
   ``ST_CollectionExtract(..., 3)`` for the same reason as in
   :doc:`time_zone_import_time_zones`: what comes back may be a ``GEOMETRYCOLLECTION``,
   which the column rejects. A trace degenerate enough to be repaired away to nothing
   stores ``NULL`` rather than an empty multipolygon.

   The stored geometry is therefore not byte-identical to the published one for those
   15%.

Dates and country
-----------------

``start_date`` and ``end_date`` are bare ``yyyy-mm-dd`` strings meaning local midnight,
exactly as GWIS publishes them, so the same rule applies — they are resolved to instants
and the zone is kept alongside as provenance (see :mod:`src.data_model.wildfire`). The end
of a fire is the last second of its end date, ``23:59:59`` local.

Both the zone and the country come from the **ignition point**, built from the published
``lat``/``lon``:

.. code-block:: sql

   ST_Contains(boundary.geometry, ignition_point)

That is cheaper than intersecting the perimeter, never ambiguous for a fire that straddles
a border, and is the fire's own reported origin rather than something derived from its
shape.

.. warning::

   This differs from :doc:`gwis_import_wildfires`, which attributes a fire to the country
   holding the **largest share of its perimeter**. The two providers therefore answer
   "which country" by different rules, which matters when comparing per-country totals
   between them: a large fire that ignites just inside one country and burns mostly into
   its neighbour is counted differently by each. This is deliberate and permanent: for a
   fire service the ignition point determines the fire's identity — its name, its
   location, its flanks — so for GFA the ignition point is the authority.

The ignition is a row of its own
--------------------------------

The point is not a column on the wildfire. Each import writes an
:doc:`../providers/gfa_ignition` — a point, the instant the fire began, and the country
and zone that follow from the point — and links the wildfire to it through
``gfa_wildfire.gfa_ignition_id``:

.. code-block:: text

   ignition ──< gfa_ignition           gfa_wildfire >── wildfire
     geometry     gfa_id  ◄─────────────  gfa_ignition_id
     date_time                            gfa_id
     time_zone                            size_km2, speed_km_day, …
     admin_boundary_id

An ignition and a perimeter are two different observations, and not every provider
publishes both — modelling the point as an attribute of the perimeter would leave nowhere
to put a detection that never gets a burnt area, and would make "every ignition last year"
a query over a table of polygons. Storing it once, on the ignition, is also about 2 GB
cheaper across the full dataset than carrying it on both.

Because the wildfire's country and start instant are resolved *from* this point, the
ignition and the wildfire always agree on them: ``ignition.date_time`` equals the
wildfire's ``start_date_time``, and ``ignition.admin_boundary_id`` its country. The
Atlas also publishes the ignition points as their own set of shapefiles, but they carry
the same ``lat``/``lon`` these files do, so there is no separate ignitions import — the
ignition is built here.

What is stored as published
---------------------------

The measurements keep the Atlas's own units and are named for them — ``size_km2``,
``perimeter_km``, ``speed_km_day``, ``spread_km2_day``, ``fire_line_km``,
``duration_days`` — so a row can be checked against the published file without arithmetic.
Note that ``size_km2`` is what GFA published and is *not* the geodesic area of the stored
perimeter.

The two sentinels are kept verbatim rather than translated to ``NULL``:

``direction = 'none'``
    No direction dominated; ``direc_frac`` is 0. Common — 46% of the 2026 file.

``landcover = 'Unclassified'``
    The Atlas classifies land cover for 2002-2023 only, so *every* fire in a later file
    carries this. It is also a genuine class within the classified years, and translating
    it away would conflate "not provided" with "provided as unclassified".

API reference
-------------

.. automodule:: src.apps.imports.wildfires.gfa.import_wildfires
   :members:
   :show-inheritance:
