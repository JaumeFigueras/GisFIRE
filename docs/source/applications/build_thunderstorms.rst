Build thunderstorms
===================

.. contents::
   :local:
   :depth: 1

Clusters one provider's lightning strokes into thunderstorms with one of the algorithms of
:doc:`../algorithms`, and stores the run as a **thunderstorm experiment**: the provider,
the period, the stroke filter, the algorithm with its complete parameters, the hull
settings and the version of ``gisfire_algorithms``, with every thunderstorm found, its
strokes and whatever the algorithm stores of its own. See
:doc:`../data_model/thunderstorm` for the tables.

Usage
-----

.. code-block:: console

   python3 -m src.apps.thunderstorms.build_thunderstorms \
       --provider MeteoCat --from 2020-07-13 --to 2020-07-14 \
       --algorithm cellsearch_tuomi_larjavaara

   python3 -m src.apps.thunderstorms.build_thunderstorms \
       --provider MeteoCat --from 2020-07-13 --to 2020-07-14 \
       --algorithm cellsearch_tuomi_larjavaara --time-distance-limit 50 --dry-run

   python3 -m src.apps.thunderstorms.build_thunderstorms \
       --algorithm cellsearch_tuomi_larjavaara --help

``--provider``, ``--from``, ``--to`` and ``--algorithm`` are required.

``--from`` and ``--to``
    The period, **half-open**: ``from <= date_time < to``, and ``--to`` must be later
    than ``--from``. A date (``2020-07-13``) is its midnight UTC; an instant with no
    offset (``2020-07-13T12:00``) is UTC; one with an offset (``2020-07-13T14:00+02:00``)
    is converted.
``--algorithm``
    The algorithm's flags come from its parameters (for Cellsearch, see
    :doc:`../algorithms/cellsearch_tuomi_larjavaara`): each field becomes a flag named
    without its unit, ``attraction_radius_km`` becoming ``--attraction-radius KM``, with
    the field's type and default. A flag left out takes its default, and the experiment
    stores every parameter, defaults included. ``--algorithm NAME --help`` lists them.
``--dry-run``
    Does everything — reads, clusters, writes — in one transaction and rolls it back, and
    logs what it would have stored. It still connects, and still refuses a configuration
    that is already stored.
``--log-file``, ``--log-level``
    Also write the log to a file; the verbosity (``GISFIRE_LOG_LEVEL``, ``INFO`` by
    default).

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``. The database must be at revision ``e7147a41b62b`` or later
(``make migrate``); the run stops before anything else if a table is missing.

What it does
------------

**One run, one experiment.** The parameters are validated and the provider looked up.
If the whole configuration — provider, algorithm, parameters, filter, hull settings,
period and software version — is already stored, the run is **refused**, whatever that
experiment's status, with its id: delete it to run again. Otherwise the experiment is
inserted as ``running`` and committed, so it is visible while the run goes on.

**The strokes are read in time order** by the provider's reader (``src/apps/
thunderstorms/readers.py``), streamed with a server-side cursor in batches of 50,000.
For MeteoCat:

- the **flash** is ``(network_version, flash_id)``, folded into one key, so the two
  networks' flash numbers never collide;
- the **location error** is ``ellipse_major_axis`` as published, in metres;
- the **coordinates** are the ETRS89 point projected to the algorithm's CRS — for
  EPSG:25831, exactly the expression of the indexed ``v_meteocat_lightning_25831``;
- the filter, stored as ``lightning_filter = {"network": "newest"}``, handles the month
  the two networks overlap (version 1 until 2009-09-29 23:59 UTC, version 2 from
  2009-09-01 00:06 UTC), where the same discharge located twice would make two flashes:
  a network's strokes are **dropped from the first stroke of any newer network on**.
  That instant is read from the database, not from the run window, so September 2009
  is version 2 only whichever period is asked for.

Every stroke is read: the database holds only cloud-to-ground strokes, and there is no
polarity filter.

**The strokes are clustered in pieces.** They are cut, about every 200,000 strokes, at a
quiet gap longer than the algorithm's own — for Cellsearch, *T*, which closes every
cell — and never through a flash. Each piece is clustered with the label counter carried
over, written and **committed on its own**, so a period of years needs neither the
memory nor the transaction of all of it, and the result is exactly that of one run over
everything (a test checks it).

**What is stored**, for each kept cell, through ``COPY`` into temporary tables and one
``INSERT … SELECT`` per table (``src/apps/thunderstorms/writers.py``):

- a ``thunderstorm`` row with its label, its number of flashes and its area from the
  algorithm, and its time span and number of strokes computed **in the database** from
  its linked strokes, so they are exactly theirs;
- its **concave hull**, ``ST_ConcaveHull(points, 0.3, false)`` over the points the
  algorithm clustered (for Cellsearch, each flash's representative stroke, the same
  points as the area), in the projected CRS and reprojected to EPSG:4326; ``NULL`` when
  it is not a polygon;
- a ``thunderstorm_lightning`` row for **every stroke** of every flash of the cell —
  so a merged MeteoCat flash with a stroke 30 km away is linked, but that stroke does not
  stretch the hull;
- the algorithm's own rows: for Cellsearch, ``thunderstorm_cellsearch_flash``, one per
  flash with the cell's running centre after it.

**The window is strict.** A storm across ``--from`` or ``--to`` becomes cut cells: no
stroke outside the period is clustered. (The read starts one gap before ``--from``, but
those strokes only set the flag below.) The run records it in the summary and warns
about it:

- ``cells_open_at_end`` — cells of any size whose latest flash is within the gap of
  ``--to``, so a later flash could have joined them;
- ``activity_before_start`` — whether there are accepted flashes within the gap before
  ``--from``, which could have started cells the period cuts.

Run a long period as **one** experiment rather than as consecutive ones, and the only
boundaries are its two ends.

**The run ends** by storing the summary — the algorithm's, plus ``strokes_total`` and
the two flags above — and marking the experiment ``complete``. On any error, or an
interrupt (Ctrl-C), the experiment's thunderstorms are deleted and it is marked
``failed``; the error is logged and the exit status is 1. An empty period is not an
error: the experiment is complete with no thunderstorms, and a warning says so.

Where to run it
---------------

The same command can be run in three ways, depending on where the database is.
:doc:`running_on_a_server` explains every part of the commands below. The run reads the
strokes from the database and writes back to it, so it belongs next to the database:
on the server for a long period.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.thunderstorms.build_thunderstorms \
       --provider MeteoCat --from 2006-01-01 --to 2021-01-01 \
       --algorithm cellsearch_tuomi_larjavaara

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.thunderstorms.build_thunderstorms \
       --provider MeteoCat --from 2006-01-01 --to 2021-01-01 \
       --algorithm cellsearch_tuomi_larjavaara \
       > build_thunderstorms.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f build_thunderstorms.log    # Ctrl-C stops tail, not the run
   pgrep -af build_thunderstorms      # still running?
   grep -E 'ERROR|WARNING' build_thunderstorms.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. Every stroke and every row written goes over the network, so it is slower
than running it on the server. The password is read into the environment rather than
passed as ``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.thunderstorms.build_thunderstorms \
       --provider MeteoCat --from 2020-07-13 --to 2020-07-14 \
       --algorithm cellsearch_tuomi_larjavaara \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Following the progress
----------------------

The run logs its configuration when it starts, a line every 100,000 flashes, the
window-boundary warnings and the summary when it ends. The regression day of the tests,
2020-07-13 with the defaults, gives:

.. code-block:: text

   INFO Running experiment 1: CELLSEARCH_TUOMI_LARJAVAARA_2005 on MeteoCat strokes, 2020-07-13T00:00:00+00:00 to 2020-07-14T00:00:00+00:00, {'attraction_radius_km': 15.0, 'max_waiting_time_min': 15.0, 'time_distance_limit_min_km': None, 'inertia': 20, 'max_location_error_km': 10.0, 'min_flashes': 5, 'srid': 25831}
   INFO Clustered 2947 stroke(s) into 46 thunderstorm(s) in 1s: {'flashes_total': 2224, 'flashes_discarded_error': 15, 'flashes_kept': 2130, 'cells_total': 92, 'cells_kept': 46, 'strokes_total': 2947, 'cells_open_at_end': 0, 'activity_before_start': False}

That is 2,224 flashes, 15 of them discarded for an error of 10 km or more, in 92 cells,
of which 46 have at least five flashes and hold 2,130 flashes; no cell is near either end
of the day. The size classes are in the stored summary. A run over the whole archive has
not been timed yet.

In QGIS
-------

A run's thunderstorms are the ``v_thunderstorm`` (concave hull) and
``v_thunderstorm_convex_hull`` layers, with each storm's flashes, area and density; a
Cellsearch run adds ``v_thunderstorm_cellsearch_centre`` (the centre after each flash)
and ``v_thunderstorm_cellsearch_path`` (one line per cell, with its lifetime and flash
rate). Each comes in EPSG:4326 and in EPSG:25831 (``_25831``), and shows complete runs
only. Filter on ``experiment_id`` to look at one run; see :ref:`migrations-views`.

API reference
-------------

.. automodule:: src.apps.thunderstorms.build_thunderstorms
   :members:
   :show-inheritance:

.. automodule:: src.apps.thunderstorms.readers
   :members:
   :show-inheritance:

.. automodule:: src.apps.thunderstorms.writers
   :members:
   :show-inheritance:
