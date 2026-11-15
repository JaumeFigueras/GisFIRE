USWFS (Alaska) lightning import
===============================

Imports the strokes of the Alaska Lightning Detection Network from the U.S. Wildland
Fire Service's yearly release, read as it is downloaded, the zip or the ``.txt``
extracted from it. The strokes are a CSV with the coordinates in two columns, so this
needs no ``ogr2ogr``: they are read in Python and streamed to PostgreSQL with ``COPY``.
See :doc:`../providers` for the dataset and :doc:`../providers/alaska_uswfs_lightning`
for what each column means.

Getting the release
-------------------

There is no API and no downloader. The release is one zip,
``Historical_Lightning_2012_forward_as_txt.zip`` (about 72 MB), linked from the
publisher's maps page, `fire.ak.blm.gov/predsvcs/maps.php
<https://fire.ak.blm.gov/predsvcs/maps.php>`_, and downloaded with a browser.

- **It is cumulative:** every stroke since 2012.
- **It is re-published every year.** The release of 2026-11-06 runs to 2026-09-28.
- **What it holds:** the strokes (``Historical_Lightning_2012_2026_TOA_WGS84.txt``),
  their FGDC metadata and a README on the network's history.

Keep the zip as downloaded. The import checks the strokes against the metadata's count
of rows, and only the zip has the metadata beside them.

Usage
-----

.. code-block:: console

   python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip

   python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip \
       --from-year 2024 --to-year 2026

   python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip --dry-run

``-s``
    The release, required: the zip as downloaded, or the ``.txt`` extracted from it. A
    ``.txt`` is imported with a warning, since nothing then checks that it is whole.
``--from-year``, ``--to-year``
    Keep only the years asked for.
``--dry-run``
    Reads, checks, groups and reports without connecting to a database. It takes about a
    minute over the whole release.
``--drop-thunderstorms``
    Lets a year that thunderstorm experiments depend on be replaced, by deleting those
    experiments first. With ``--dry-run`` it connects, read only, just to list them.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``. The database must be at revision ``fdc1d32daef2`` or later
(``make migrate``).

What it does
------------

**The release is checked before anything is written.**

- The header must be the fifteen columns of the release.
- When the zip holds the FGDC metadata, the number of rows must equal its point count
  (2,226,185 in the release of 2026-11-06). A release that disagrees is incomplete or
  altered and is refused whole: download it again.
- Each year's rows must be together, so the import holds one year in memory at a time.

**A UTC year is replaced wholesale.** Nothing in a row identifies a stroke, so each year
of the release is deleted — the network's strokes of it, no other provider's — and
re-inserted in one transaction. A failure leaves the year as it was. Importing a new
release replaces every year it holds, or the years asked for. Its last year may be
incomplete, and the next release completes it.

**Every row is checked and converted.** A row is refused (logged with its line and the
reason, counted and skipped) when:

- a value is not a number or not a date;
- the stroke type is unknown;
- a ground stroke has no amplitude, or a cloud stroke has one;
- a value would break a constraint of ``alaska_uswfs_lightning``.

No row of the 2012-2026 release is refused. Then:

- the instant is ``UTCDATETIME`` plus ``MILLISECONDS``, which is the fraction of the
  second, whatever the metadata says;
- the amplitude becomes kiloamperes, and ``NULL`` on a cloud stroke;
- the ellipse's semi-axes become **metres**, and a semi-major axis of 0 becomes
  ``NULL``;
- the local time, the minute string and the polarity are not kept. A polarity that
  contradicts the amplitude's sign is counted and logged (22 strokes of 2019).

**The strokes get their identifiers in an order of their own.** Within a millisecond the
file's order is arbitrary, and 40,740 strokes share their millisecond with another. Each
year is sorted by the strokes' **values** (instant first), and the identifiers are drawn
in that order, so the same release imported again gets the same order. That matters
because the thunderstorm algorithms break ties by identifier. Strokes identical in
everything but the sequence number are one stroke published twice, and only the first is
kept (24 strokes, all on 2012-06-15).

**The strokes are grouped into flashes**, which the network does not publish, with the
NLDN rule, on Alaska Albers metres, ground and cloud strokes apart; see
:doc:`../algorithms/flash_grouping_nldn`. ``flash_id`` is the identifier of the flash's
first stroke, and ``multiplicity`` and ``stroke_index`` are set in the same insert. The
table's CHECKs refuse a stroke whose numbering is inconsistent. Grouping runs within the
UTC year; the import warns about a stroke within a second of the year's edges, where a
flash could be cut, and there is none in 2012-2026.

**The point is stored once**, as published: WGS 84 is EPSG:4326.

**The country is resolved by spatial join** against the OCHA level-0 boundaries:

- They are **clipped to the network's area** and cut once per run into pieces of at most
  256 vertices, as for FMI and MeteoCat; see :mod:`src.apps.imports.lightnings.common`.
- The area runs from 168.8° E **across the antimeridian** to 97° W, so the boundaries
  are clipped on both sides of it. The clipping box is kept in the area's own longitudes
  and split in two at 180°.
- Strokes at sea get no country.
- Without the OCHA boundaries every stroke is stored with no country and a warning:
  import them first with :doc:`ocha_import_admin_boundaries`.

**A year thunderstorms depend on is refused**, exactly as for MeteoCat and FMI. The
network's experiments whose period overlaps the year, and any experiment holding one of
its strokes, stop the year unless ``--drop-thunderstorms`` deletes them, whole, first, in
the year's transaction.

The run ends with the strokes and flashes per year and, when writing, how many found no
country. The release of 2026-11-06 — **2,226,161 strokes in 1,752,517 flashes** over
fifteen years — imported with the OCHA boundaries in **6 min 13 s**:

- 8 s to check the release;
- one 40 s cut of the boundaries;
- 7 to 27 s of writing per year.

It takes 854 MB in the database, about 402 bytes a stroke with its indexes (FMI takes
505, since it stores a second point). Every stroke got the same country as with the
whole, unclipped polygons:

- United States: 1,569,069;
- Canada: 616,993;
- Russia: 316;
- none (at sea): 39,783, the 535 strokes beyond 180° among them.

In QGIS the strokes are the ``v_alaska_uswfs_lightning_4326`` and
``v_alaska_uswfs_lightning_3338`` views: the same rows as published and in NAD83 /
Alaska Albers; see :ref:`migrations-views`. Filter on ``stroke_index = 1`` for one point
per flash, on ``cloud_to_ground`` for the kind of stroke, and on
``ellipse_semi_major_axis IS NULL`` for the strokes of unknown error.

Where to run it
---------------

The same command can be run in three ways, depending on where the release and the
database are. :doc:`running_on_a_server` explains every part of the commands below.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
Copy the zip there first, with ``rsync -avP``:

.. code-block:: bash

   rsync -avP ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip \
       user@server:data/alaska/
   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip \
       > alaska_import_lightnings.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f alaska_import_lightnings.log    # Ctrl-C stops tail, not the run
   pgrep -af alaska_uswfs.import_lightnings    # still running?
   grep -E 'ERROR|WARNING' alaska_import_lightnings.log

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. Every stroke goes over the network, so it is slower than running it on the
server. The password is read into the environment rather than passed as
``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.lightnings.alaska_uswfs.import_lightnings \
       -s ~/data/alaska/Historical_Lightning_2012_forward_as_txt.zip \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user

API reference
-------------

.. automodule:: src.apps.imports.lightnings.alaska_uswfs.import_lightnings
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.lightnings.alaska_uswfs.readers
   :members:
   :show-inheritance:
