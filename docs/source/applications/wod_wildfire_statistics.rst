WOD wildfire statistics (New Zealand)
=====================================

Burnt-area statistics for the New Zealand *Wildfire Occurrence Database*, per country and
year: how many fires, the smallest, the largest and the total, in hectares — and, this
dataset's own columns, how many of the fires each agency recorded and how many have a
perimeter.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics --csv burnt.csv

   # by New Zealand fire year, 1 July to 30 June, as FENZ counts
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --financial-year --docx fire-years.docx

   # the measured perimeters instead of the recorded areas
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --area-method perimeter --csv mapped.csv

   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --cause lightning --min-area 1 --csv lightning.csv

At least one of ``--csv`` and ``--docx`` is required. The application only reads.

Options
-------

``--area-method reported|perimeter``
    ``reported`` (default) is the area the agency recorded, ``AreaHa``, for every fire; a
    recorded 0 counts. ``perimeter`` is the area of the published perimeter measured on
    NZTM2000, so **only the fires with a perimeter are counted** — 2,089 of them, none in
    2012-2016.
``--financial-year``
    Count by fire year (``2005/2006``) rather than calendar year. ``--year`` then names the
    year the fire year starts in.
``--min-area``, ``--cause``, ``--source``, ``-y/--year``
    Narrow the fires: a size, one of the four cause classes, one agency, one year.
``--country-source filed|geometry``
    ``filed`` (default) counts every record as New Zealand's, the points in the sea
    included — the opposite default to :doc:`nfdb_wildfire_statistics`, because every WOD
    record is a New Zealand agency's record of a New Zealand fire. ``geometry`` tests the
    point against the OCHA countries and logs how many fires it leaves out.

Where to run it
---------------

The same command can be run in three ways, depending on where the database is.
:doc:`running_on_a_server` explains every part of the commands below. The report only
reads the database, and what it writes (``--csv``, ``--docx``) lands on the machine
the command runs on.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --csv burnt.csv

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
Relative output paths are relative to ``~/GisFIRE`` on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --csv burnt.csv \
       > new_zealand_wod_wildfire_statistics.log 2>&1 < /dev/null &
   exit

When you log in again, check on it, then copy the report back to your machine:

.. code-block:: bash

   ssh user@server 'pgrep -af new_zealand_wod.wildfire_statistics; tail -n 20 GisFIRE/new_zealand_wod_wildfire_statistics.log'
   scp user@server:GisFIRE/burnt.csv .

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. This is usually the most convenient form for a report: the aggregation runs
on the server, only the summary rows cross the network, and the files are written
straight onto your machine. The password is read into the environment rather than
passed as ``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics \
       --csv burnt.csv \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Being read-only, the report can also run as ``gisfire_remoteuser``, provided that role has been
granted ``SELECT`` (see :ref:`pg-readonly-grants`).

Output
------

The first six columns are the other burnt-area reports', in their order, so the CSVs can be
concatenated on them; the last three are this dataset's. Areas have **four decimals**,
because most WOD fires are a few square metres.

Over the whole release, imported with ``--all-years``:

===========  =====  ======  ============  ============  ===========  ======  =====  ==========
Country      Year   Fires   Minimum (ha)  Maximum (ha)  Total (ha)   FENZ    DOC    Perimeters
===========  =====  ======  ============  ============  ===========  ======  =====  ==========
New Zealand  2024     4703        0.0000     1026.0000    5641.3330    4703      0         166
New Zealand  2020     5824        0.0000     5033.0000   13850.6388    5824      0         180
New Zealand  2005     4980        0.0000     1400.0000    6221.1313    4815    165          55
New Zealand  Total  128020        0.0000     6159.0000  210731.3752  122538   5482        2089
===========  =====  ======  ============  ============  ===========  ======  =====  ==========

From the default cut, 1998 on, the report gives 125,407 fires and 145,069 ha. Over the
whole release, ``--min-area 200`` keeps 181 fires and 133,934 ha — **64% of the recorded
area in 0.14% of the fires**.

.. note::

   By fire year, **1998/1999 comes to 11,415 ha** — exactly the WOD total the paper gives
   for that year when it compares the WOD with the annual summaries (which record
   17,693 ha). The report reproduces the published figure from the imported records.

.. warning::

   **A count of WOD fires is a count of incidents.** The median FENZ record is five square
   metres. Before 1998 the record is DOC's alone and sparse, from 2012 FENZ's alone, and
   calendar 2025 runs only to 30 June. Read ``FENZ`` and ``DOC`` before reading a trend.

The two areas are different quantities
--------------------------------------

Under ``perimeter`` the 2,089 perimeters measure 82,995 ha, against the agencies' recorded
area for the same fires. FENZ perimeters were often traced from helicopters and include
unburnt islands; DOC's were mostly digitised from paper maps. A row is always one or the
other, never a mixture.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.new_zealand_wod.wildfire_statistics
   :members:
   :show-inheritance:
