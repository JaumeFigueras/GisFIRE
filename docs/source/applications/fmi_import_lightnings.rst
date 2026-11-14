FMI lightning import
====================

Imports the Finnish Meteorological Institute's lightning strokes from the monthly files of
:doc:`fmi_download_lightnings` — ``fmi_lightning_YYYY-MM.csv.gz`` and their
``.meta.json`` sidecars. The files are gzip CSV with the coordinates in two columns, so
this needs no ``ogr2ogr``: they are read in Python and streamed to PostgreSQL with
``COPY``. See :doc:`../providers` for the dataset and :doc:`../providers/fmi_lightning`
for what each column means.

Usage
-----

Over one or more monthly files, or over the directory holding them:

.. code-block:: console

   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -s ~/data/fmi/fmi_lightning_2018-07.csv.gz

   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -d ~/data/fmi --from-year 2018 --to-year 2019

   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -d ~/data/fmi --dry-run

   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -s ~/data/fmi/fmi_lightning_2018-07.csv.gz --drop-thunderstorms

``-d`` and ``-s`` are mutually exclusive and one is required. With ``-d`` every
``fmi_lightning_YYYY-MM.csv.gz`` in the directory is imported, in month order, and one
whose header is not the downloader's is skipped with a warning; with ``-s`` such a file
stops the run before anything is written. ``--from-year`` and ``--to-year`` keep only the
months of those years. ``--dry-run`` reads, checks and reports without connecting to a
database. ``--drop-thunderstorms`` lets a month that thunderstorm experiments depend on
be replaced, by deleting those experiments first; with ``--dry-run`` it connects, read
only, just to list them.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``. The database must be at revision ``95b95aac852f`` or later
(``make migrate``).

What it does
------------

**A UTC month is replaced wholesale.** Nothing in a row identifies a stroke, so each
file's month is deleted — FMI's strokes of it, no other provider's — and re-inserted in
one transaction; a failure leaves the month as it was. The downloader writes one file
per month, so importing a file again replaces exactly what it holds. A file with no
strokes — a winter month of the early years — just empties its month.

**The sidecar is checked.** The downloader's ``.meta.json`` says how many strokes it
wrote. A file whose row count disagrees is incomplete or altered: its month is **not
imported**, the other months are, and the run ends with an error saying to download the
month again. A sidecar for another month is refused the same way. A month the sidecar
calls incomplete (fetched with ``--include-current``) is imported with a warning — import
it again once it has been downloaded whole — and a file with no sidecar is imported with
a warning, since nothing then says it is whole.

**Every row is checked and converted.** A row is refused — logged with its line and the
column at fault, counted and skipped — when a value is not a number, is ``NaN`` or
infinite, is not an integer where one is expected, falls outside the file's month, or
would break a constraint of ``fmi_lightning``. No row of the samples from 1998 to 2025
is. Then:

- the published ``peak_current`` of ``0`` (not recorded, 2005-2008) becomes ``NULL``;
- ``cloud_indicator`` becomes ``cloud_to_ground`` (0 is cloud-to-ground);
- the ellipse axes become **metres**, rounded to 0.1 m, so 0.3 km is exactly 300.0 m;
- ``multiplicity`` is kept as ``published_multiplicity``; every other field, the
  undocumented indicators and status included, as published.

**The strokes get their identifiers in an order of their own.** FMI publishes whole
seconds, and returns the strokes of one second in no stable order, so two downloads of a
month hold the same rows in different orders. The reader sorts each month by the
strokes' **values** — instant, flash, the flash's first stroke first, then every other
value — and the identifiers are drawn from ``lightning``'s sequence in that order. A
month downloaded twice is therefore imported with its identifiers in the same order,
which matters: the thunderstorm algorithms break ties between strokes of one second by
identifier, and on a real day a different order gives different cells.

**Every flash is numbered** in the database, before the insert: ``multiplicity`` is the
number of strokes of the ``flash_id`` stored, and ``stroke_index`` puts first the stroke
FMI marks as first, then the others by instant and by the month's order. A flash lasts
about a second, so one can straddle two months: the numbering takes in the strokes
already stored for the same flashes within a minute outside the month, and updates them.
Whichever month is imported first, the flash ends up numbered whole. About 0.01 % of
flashes have lost strokes to FMI's quality filter, so their ``multiplicity`` is smaller
than their ``published_multiplicity``, and a few have no first stroke at all.

**The point is stored twice**: as published in ETRS89 on ``fmi_lightning``, and
reprojected to EPSG:4326 on ``lightning``.

**The country is resolved by spatial join** against the OCHA level-0 boundaries, cut
with ``ST_Subdivide`` into pieces of at most 256 vertices, as for MeteoCat. Strokes at
sea get none. Without the OCHA boundaries every stroke is stored with no country and a
warning: import them first with :doc:`ocha_import_admin_boundaries`.

**A month thunderstorms depend on is refused**, exactly as a year is for MeteoCat (see
:doc:`meteocat_import_lightnings`): FMI's experiments whose period overlaps the month,
and any experiment holding one of its strokes, stop the month unless
``--drop-thunderstorms`` deletes them whole first, in the month's transaction.

The run ends with the strokes and flashes per month and, when writing, how many found no
country. 2018 — 2,144,941 strokes in 1,712,147 flashes — imports in about four minutes
without boundaries (July alone, 906,338 strokes, in 19 s of reading and 80 s of
writing), and takes about 1 GB in the database, some 505 bytes a stroke with its
indexes:

.. code-block:: text

   fmi_lightning_2018-07.csv.gz: 906338 stroke(s) read
   fmi_lightning_2018-07.csv.gz: 2018-07: 906338 stroke(s) in 709590 flash(es), 906338 with no country
   Imported 2144941 stroke(s) in 1712147 flash(es) over 12 month(s) in 236s

In QGIS the strokes are the ``v_fmi_lightning_4326``, ``v_fmi_lightning_4258`` and
``v_fmi_lightning_3067`` views — the same rows in three CRSs, the last on Finland's
TM35FIN grid; see :ref:`migrations-views`. Filter on ``stroke_index = 1`` for one point
per flash, and on ``cloud_to_ground`` to tell the two kinds of stroke apart.

Where to run it
---------------

The same command can be run in three ways, depending on where the files and the database
are. :doc:`running_on_a_server` explains every part of the commands below.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -d ~/data/fmi

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs. The
files have to be there first — downloaded on the server, or copied with ``rsync -avP``:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -d ~/data/fmi \
       > fmi_import_lightnings.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f fmi_import_lightnings.log    # Ctrl-C stops tail, not the run
   pgrep -af finland_fmi.import_lightnings    # still running?
   grep -E 'ERROR|WARNING' fmi_import_lightnings.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. Every stroke goes over the network, so it is slower than running it on the
server. The password is read into the environment rather than passed as
``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.lightnings.finland_fmi.import_lightnings \
       -d ~/data/fmi \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user

API reference
-------------

.. automodule:: src.apps.imports.lightnings.finland_fmi.import_lightnings
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.lightnings.finland_fmi.readers
   :members:
   :show-inheritance:
