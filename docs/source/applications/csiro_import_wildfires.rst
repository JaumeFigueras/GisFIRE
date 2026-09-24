CSIRO bushfire extent import (Australia)
========================================

Imports the Australian historical bushfire extents — **one file geodatabase, two feature
classes, 347,834 polygons, 1898-2025** — into :doc:`../providers/csiro_wildfire`.

Each feature class is staged with ``ogr2ogr`` once, its published attributes are resolved
into normalised columns once, and then **each year is deleted, rewritten and committed in
a transaction of its own**. Re-importing a year replaces it.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
         -g perimetres-gdb

   # only the Northern Territory class
   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
         -g perimetres-gdb --layer nt

   # only one year, read from the resolved start date
   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
         -g perimetres-gdb -y 2019 -y 2020

   # do all the work and roll every year back
   $ python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
         -g perimetres-gdb --dry-run

Import the boundaries and the time zone areas first —
:doc:`ocha_import_admin_boundaries` and :doc:`time_zone_import_time_zones` — because both
are resolved at import time and cannot be filled in afterwards without re-importing.
Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host``,
``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

Where to run it
---------------

The same command can be run in three ways, depending on where the data and the database
are. :doc:`running_on_a_server` explains every part of the commands below.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
       -g perimetres-gdb

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
The files have to be copied to the server first (``rsync -avP``), and the
paths below are paths on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
       -g perimetres-gdb \
       > australia_csiro_import_wildfires.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f australia_csiro_import_wildfires.log    # Ctrl-C stops tail, not the run
   pgrep -af australia_csiro.import_wildfires    # still running?
   grep -E 'ERROR|WARNING' australia_csiro_import_wildfires.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. The files stay on your machine and every geometry goes over the network, so
it is slower than running it on the server. The password is read into the environment
rather than passed as ``--db-password``, which would show in ``ps`` and in the shell
history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.wildfires.australia_csiro.import_wildfires \
       -g perimetres-gdb \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

A year at a time, on purpose
----------------------------

The sibling imports inherit their unit of work from the way their source is published:
NBAC arrives as one shapefile per year, CONAF as one per season. **This archive arrives as
a single 860 MB geodatabase holding 128 years and 155.8 million vertices**, and nothing in
it suggests a unit of work at all.

Transformed in one statement it would hold every lock it takes for the length of the run,
roll back an hour on one bad row, and show no progress in between. So the import chooses
the unit the data can be cut along:

.. code-block:: text

   stage the feature class            (once, ogr2ogr)
   resolve the published attributes   (once, two UPDATEs)
   cut the boundary and zone pieces   (once, ST_Subdivide)
   for each year:
       delete that year  ─┐
       transform it       ├─ one transaction
       commit            ─┘
       log what happened

The largest year in the archive is 2021 with 16,363 features, against 345,345 in the
class. That is the size of the biggest statement this import ever runs, and a failure
costs one year rather than the run.

This is why :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.year` exists and
is ``NOT NULL``: it is the replacement key, and the geodatabase publishes no year column
of its own.

Nothing is merged
-----------------

One published feature is one row. The import does **not** dissolve the patches of a burn
into a fire.

It did, in its first version, on ``(source_layer, state_code, fire_id, ignition_date)`` —
and measuring the result is what removed it. That key merges 4,078 groups in the national
class, of which **23.4% span more than 10 km** and the widest joins two Western Australian
features **2,403 km apart**, both publishing ``fire_id`` ``23`` on 2010-11-24. The numbers
it keyed on are district sequences reused across the state: placeholders exactly as
``'999'`` is, without saying so.

A fire has several fronts; it does not have one on either side of Western Australia. So
the import stores the unit that is certainly true — the published feature — and leaves
reassembling fires to an application that can bring a rule to it. Merging is the one
operation an import cannot undo.

That also makes the year loop trivially safe: with nothing to group, a year's rows do not
depend on which years were imported before it.

What the run reports
--------------------

Every step, and every year. Per feature class: how many features were staged, how many
could not be dated, how many boundary and zone pieces were cut, and which years were
found. Per year: the fires already stored that were removed, the features read, the rows
written, how many were prescribed burns, and how long it took. At the end, over the whole
run: the date sources, the implausible dates, and how many fires matched no time zone area
or no country.

.. code-block:: text

   national: Staged 345345 feature(s)
   national: Resolved the published attributes into normalised columns
   national: Cut 148 boundary piece(s) and 61 time zone piece(s) for POLYGON(...) in 4.1s
   national: Importing 1898 to 2025 (109 years), one transaction each
   national: Year 96 of 109: 2018
   2018: read 13538 feature(s), wrote 13538 fire(s) (6822 prescribed) in 41.2s

.. note::

   **The geodatabase has to be named** ``.gdb``. GDAL identifies a file geodatabase by the
   suffix on its directory and the archive as distributed has none, so
   :func:`~src.apps.imports.wildfires.australia_csiro.import_wildfires.geodatabase` puts a
   ``.gdb`` symlink to it in a temporary directory and hands GDAL that. The data is left
   where it is and nothing has to be renamed.

.. note::

   The staged features keep the geodatabase's own ``OBJECTID`` — ``ogr2ogr`` is run with
   ``-preserve_fid`` — because unlike a shapefile's FID it identifies something, and
   :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.object_id` stores it.

.. warning::

   345,345 perimeters each need a country and a time zone, and Australia's OCHA boundary
   is one polygon of hundreds of thousands of vertices. Tested whole that lookup is about
   100 ms a fire and the run never finishes, so the import cuts the boundaries and the
   zones into ≤256-vertex pieces first, as
   :doc:`conaf_import_wildfires` does. The pieces are staging tables beside the features,
   dropped with them, and kept between the two feature classes.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.australia_csiro.import_wildfires
   :members:
   :show-inheritance:
