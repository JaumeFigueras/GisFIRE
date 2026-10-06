WOD wildfires by cause (New Zealand)
====================================

Counts the New Zealand *Wildfire Occurrence Database* records by cause class, per country
and year: how many fires, how many with a **determined** cause, how they split between
lightning, other natural causes and people, and how much of the recorded area the lightning
fires account for.

The companion of :doc:`wod_wildfire_statistics`, over the same fires and the same scope —
the ``Country``, ``Year`` and ``Fires`` columns of the two agree row for row.

.. important::

   **This dataset names lightning.** 538 records say so — FENZ ``Lightning discharge``, DOC
   ``Lightning`` and ``Lightening Strike`` — so the ``Lightning`` column is lightning and
   not a *natural* proxy as in :doc:`nfdb_wildfire_causes` or :doc:`icnf_wildfire_causes`.
   ``Natural`` is the other natural causes, kept apart: geothermal activity, five records.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes \
       --financial-year --docx causes.docx

   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes \
       --source DOC --csv doc-causes.csv

At least one of ``--csv`` and ``--docx`` is required. The application only reads. The
options are the companion's ``-y/--year``, ``--financial-year``, ``--source`` and
``--country-source``; there is no ``--cause``, the cause being what is counted.

Where to run it
---------------

The same command can be run in three ways, depending on where the database is.
:doc:`running_on_a_server` explains every part of the commands below. The report only
reads the database, and what it writes (``--csv``, ``--docx``) lands on the machine
the command runs on.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes \
       --csv causes.csv

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
Relative output paths are relative to ``~/GisFIRE`` on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes \
       --csv causes.csv \
       > new_zealand_wod_wildfire_causes.log 2>&1 < /dev/null &
   exit

When you log in again, check on it, then copy the report back to your machine:

.. code-block:: bash

   ssh user@server 'pgrep -af new_zealand_wod.wildfire_causes; tail -n 20 GisFIRE/new_zealand_wod_wildfire_causes.log'
   scp user@server:GisFIRE/causes.csv .

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. This is usually the most convenient form for a report: the aggregation runs
on the server, only the summary rows cross the network, and the files are written
straight onto your machine. The password is read into the environment rather than
passed as ``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes \
       --csv causes.csv \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Being read-only, the report can also run as ``gisfire_remoteuser``, provided that role has been
granted ``SELECT`` (see :ref:`pg-readonly-grants`).

Output
------

Over the whole release, imported with ``--all-years``:

===========  =====  ======  ==========  =========  =============  =======  ======  =======  ==============  ===================
Country      Year   Fires   Determined  Lightning  Lightning (%)  Natural  Human   Unknown  Lightning (ha)  Lightning (% of ha)
===========  =====  ======  ==========  =========  =============  =======  ======  =======  ==============  ===================
New Zealand  2024     4703        3904         20           0.51        2    3882      799          6.9475                 0.15
New Zealand  2020     5824        4837         21           0.43        1    4815      987          5.0289                 0.05
New Zealand  2005     4980        4313         21           0.49        0    4292      667          2.3087                 0.04
New Zealand  Total  128020      106842        538           0.50        5  106299    21178       1489.9377                 1.03
===========  =====  ======  ==========  =========  =============  =======  ======  =======  ==============  ===================

From 1998 on: 516 lightning fires out of 105,231 determined — **0.49%** — burning 1,002 ha.

**New Zealand's fires are started by people.** Lightning is one fire in two hundred whose
cause is known, and about one hectare in a hundred. The largest lightning fire in the
release burnt 486 ha, in 1962.

Why the denominator is the determined fires
-------------------------------------------

``Unknown`` gathers what was not recorded or could not be classified — 21,178 records, a
sixth of the archive, and not evenly spread: FENZ's *Information not recorded/Unknown* is
about a tenth of its records. The percentages are therefore of the fires whose cause is
known, as in the other cause reports, and ``Unknown`` is a column so that what was left out
stays visible. A percentage with nothing to divide is left **empty**, not zero. The four
cause columns add up to ``Fires``.

The hectares are the recorded ``AreaHa``; the perimeters are not used here.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.new_zealand_wod.wildfire_causes
   :members:
   :show-inheritance:
