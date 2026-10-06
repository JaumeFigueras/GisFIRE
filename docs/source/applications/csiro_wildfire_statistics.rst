CSIRO wildfire statistics (Australia)
=====================================

Reports the Australian historical bushfire extents per **fire season** (July to June),
with three figures for each group of fires: how many there were, the hectares the
agencies **report** and the hectares this application **measures** from the perimeter.
The groups are every fire, each of the three published fire types, and the fires whose
published cause is natural.

It writes **one national file and one file per state**, in the same format, as CSV and
Word. A state with no fires in the seasons reported gets no file.

Unlike the other burnt-area reports it has no smallest or largest fire columns: the
archive stores published features, not fires (see below), so a "largest fire" would be
the largest mapped patch.

Usage
-----

.. code-block:: bash

   # every season from 1970-71 (the default), national + one file per state
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --csv australia.csv --docx australia.docx

   # the Black Summer only
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --season 2019-20 --csv black-summer.csv

   # a range of seasons; 2000 and 2000-01 mean the same season
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --from-season 2000 --to-season 2019-20 --csv 2000s.csv

   # the whole archive, from 1898-99, including the fires with unbelievable dates
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --all-seasons --include-implausible --csv everything.csv

At least one of ``--csv`` and ``--docx`` is required. The path given is the national
file; the state files are written beside it with the state code appended:
``australia.csv``, ``australia_ACT.csv``, ``australia_NSW.csv``, … ``australia_WA.csv``,
and the same for ``.docx``.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden
with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

Where to run it
---------------

The same command can be run in three ways, depending on where the database is.
:doc:`running_on_a_server` explains every part of the commands below. The report only
reads the database, and what it writes (``--csv``, ``--docx``) lands on the machine
the command runs on.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --csv australia.csv --docx australia.docx

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
Relative output paths are relative to ``~/GisFIRE`` on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --csv australia.csv --docx australia.docx \
       > australia_csiro_wildfire_statistics.log 2>&1 < /dev/null &
   exit

When you log in again, check on it, then copy the reports back to your machine (the
national file and every state file):

.. code-block:: bash

   ssh user@server 'pgrep -af australia_csiro.wildfire_statistics; tail -n 20 GisFIRE/australia_csiro_wildfire_statistics.log'
   scp 'user@server:GisFIRE/australia*.csv' 'user@server:GisFIRE/australia*.docx' .

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. This is usually the most convenient form for a report. The aggregation runs
on the server and only a few thousand summary rows cross the network, and all the files
are written straight onto your machine:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \
       --csv australia.csv --docx australia.docx \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Being read-only, the report can also run as ``gisfire_remoteuser``, provided that role has been
granted ``SELECT`` (see :ref:`pg-readonly-grants`).

The whole archive is measured in **one statement**, about three minutes over the 155.8
million vertices, and every file is a sum of its result. Asking for the state files
costs nothing extra.

Output
------

Seventeen columns: the season, a triplet for each of five groups, and how many fires
publish a cause.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Columns
     - What they count
   * - ``Fires``, ``Reported (ha)``, ``Measured (ha)``
     - every fire of the season: published features, reported hectares (``area_ha``)
       and measured hectares (geodesic)
   * - ``Bushfire …``
     - the same three, fire type ``bushfire``
   * - ``Prescribed burn …``
     - the same three, fire type ``prescribed_burn``
   * - ``Unknown type …``
     - the same three, features that publish no fire type
   * - ``Natural cause …``
     - the same three, features whose published cause is natural
   * - ``Fires with cause``
     - features whose published cause is one the report can read (see
       :ref:`csiro-fires-with-cause`)

Four rows of the national file (default run: 56 seasons and the total):

.. csv-table::
   :header: Season, Fires, Reported (ha), Measured (ha), Bushfire, Prescribed, Natural
   :align: right

   2025-26, 555, "2,846,318.00", "2,846,332.32", 230, 126, 2
   2019-20, "15,544", "15,096,152.00", "15,096,508.29", "3,194", "9,934", 559
   1970-71, 906, "510,178.00", "510,175.47", 253, 482, 0
   **Total**, "**309,300**", "**338,831,639.00**", "**338,836,211.74**", "**81,268**", "**143,040**", "**8,887**"

(only some of the seventeen columns are shown; Bushfire, Prescribed and Natural are the
``Fires`` of their triplets.)

The CSV writes bare numbers; the Word document writes them with thousands separators,
on a landscape page, under a two-row heading (the group over its three figures), with
the ``Total`` row in bold.

Fire seasons
------------

A fire belongs to the season its resolved start date falls in: the published ignition
date, or the extinction or capture date where there is none, the same date the import
derives ``year`` from. A start from July onwards opens a season and one before July
closes the previous one, so 8 November 2019 and 4 January 2020 are both 2019-20.

``--from-season``, ``--to-season`` and ``--season`` take the year a season starts in
(``2019``) or the pair (``2019-20`` or ``2019-2020``). Every season in the range gets a
row, with zeros where there were no fires, so the national file and every state file
have the same rows and can be read side by side.

Why 1970-71 is the default first season
---------------------------------------

The archive runs from 1898, but its early decades are not a national record. The year
from which each state reports **every** year, without a gap:

=====  ====  ====  ====  ====  ====  ====  ====
State  WA    QLD   VIC   NSW   SA    ACT   TAS
=====  ====  ====  ====  ====  ====  ====  ====
From   1925  1937  1942  1944  1950  1964  1969
=====  ====  ====  ====  ====  ====  ====  ====

Before 1970 a national total cannot tell a season without fires from a season without
data, so 1970-71 is the default. ``--all-seasons`` starts from the first season in the
archive instead. The Northern Territory is the exception for good: it publishes 2020,
2021 and 2025 only.

.. warning::

   **The last seasons are incomplete.** The archive ends in September 2025, so 2025-26
   holds the first three months of a season. Queensland publishes 8 features in 2024 and
   6 in 2025, against several hundred a year before. Both are kept in the report, and the
   Word documents for the nation and for Queensland say so.

What "Fires" counts
-------------------

**Published features, not fires.** The import merges nothing (see
:doc:`csiro_import_wildfires`): one row per polygon an agency published, so a burn
mapped as several patches counts several times. That is why there are no minimum and
maximum columns.

Reported and measured
---------------------

``Reported (ha)`` sums the published ``area_ha``. It is whole hectares, and 77,069
features publish 0. ``Measured (ha)`` sums the geodesic area of the perimeter on the
WGS84 ellipsoid, as every burnt-area report in GisFIRE does. Over a season the two agree
to a few hundredths of a percent (338,831,639 against 338,836,212 ha over 1970-2026);
per small feature they do not.

The fire types
--------------

``bushfire``, ``prescribed_burn`` and ``unknown`` — the published type, normalised. Every
feature has exactly one, so **the three type triplets add up to the first one**.
Prescribed burns are almost half the archive and are counted in ``Fires``: read the
``Bushfire`` triplet for wildfires only, and remember that ``Unknown type`` is a mix of
both.

The natural cause
-----------------

``Natural cause`` counts features whose published cause is natural, **of any type**, so
it is not a fourth part of the first triplet.

Causes are published unevenly: every NSW and NT feature has one, about 60% of ACT and
56% of TAS, 9% of WA, almost none in VIC and none in QLD or SA. So a zero is only an
answer where causes were published. **Where no fire of a season, in the file's scope,
publishes any cause, the three natural cells are left empty** rather than written as
zeros. That is why the SA file's natural columns are empty throughout and QLD's are
empty in every season but 2024-25, and why a national natural total is a lower bound.

.. _csiro-fires-with-cause:

Fires with cause
----------------

The last column counts the features of the season whose published cause is one the
provider's vocabulary reads: ``Natural``, ``Accidental``, ``Incendiary`` or
``Undetermined``, including the variant spellings ``NOT DETERMINED`` and
``WF - unknown``. A blank cause is not counted, and neither is a value the vocabulary
does not know (``OTHER``, 57 features in the archive). Undetermined **is** counted: it
is a correctly written answer, even though it says nothing about the cause.

Read it beside ``Fires``. Their ratio is how much of a season the ``Natural cause``
triplet can speak for. Where it is 0, the natural cells are empty.

Implausible dates
-----------------

514 features publish dates that cannot be believed: an epoch placeholder, a year
outside 1900-2100, or an extinction before the ignition. Their season is unknown, so
they are left out by default. ``--include-implausible`` counts them, in whatever season
their resolved date falls in.
