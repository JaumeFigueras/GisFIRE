MeteoCat lightning import
=========================

Imports the lightning strokes of MeteoCat's XDDE network from the yearly CSV extracts of
the DATMET-12706 delivery — ``DATMET-12706_cg_cm_2006.csv`` to ``…_2020.csv``,
**6,156,214 cloud-to-ground strokes**.

The extracts are plain ``;``-separated text with coordinates in two columns, so this
needs no ``ogr2ogr``: the file is read in Python and streamed to PostgreSQL with
``COPY``. See :doc:`../providers` for the dataset and
:doc:`../providers/meteocat_lightning` for what each column means.

Usage
-----

Over one or more extracts, or over the directory holding them:

.. code-block:: console

   python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \
       -s meteocat/DATMET-12706_cg_cm_2014.csv

   python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \
       -d meteocat/

   python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \
       -d meteocat/ --year 2009 2010 --dry-run

   python3 -m src.apps.imports.lightnings.catalonia_meteocat.import_lightnings \
       -s meteocat/DATMET-12706_cg_cm_2009.csv --drop-thunderstorms

``-d`` and ``-s`` are mutually exclusive and one is required. With ``-d`` every ``.csv``
in the directory with the extract header is imported and any other is skipped with a
warning; with ``-s`` a file without the header stops the run before anything is written.
Every header is checked before the first file is read. ``--year`` imports only the UTC
years named. ``--dry-run`` reads, checks and reports without connecting to a database.
``--drop-thunderstorms`` lets a year that thunderstorm experiments depend on be replaced,
by deleting those experiments first (see below); with ``--dry-run`` it connects, read
only, just to list them.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``.

What it does
------------

**A UTC year is replaced wholesale.** Nothing in a row identifies a stroke, so each year
in a file is deleted — MeteoCat's strokes of it, no other provider's — and re-inserted in
one transaction; a failure leaves the year as it was. Each extract is one UTC year, so
importing a file again replaces exactly what it holds. Re-importing a year from a CSV
also replaces whatever a future API import stored for it.

**A year thunderstorms depend on is refused.** A thunderstorm experiment
(:doc:`../data_model/thunderstorm`) is computed from MeteoCat's strokes over a period, so
replacing a year under it would change its input silently — and the strokes in its
thunderstorms cannot be deleted at all (``ON DELETE RESTRICT``). Before replacing a year,
in the same transaction, the import looks for the experiments that depend on it:
MeteoCat's experiments whose period overlaps the year, whatever their status and whether
or not any of the year's strokes ended up in a thunderstorm, and any experiment holding
one of the year's strokes. If there is one, the year is **not replaced** — each experiment
is logged with its period and counts, the year is skipped, the other years are imported,
and the run ends with an error naming the years left out:

.. code-block:: text

   2009 is used by thunderstorm experiment 1 (DBSCAN, complete, 2009-01-01 to 2010-01-01): 1 thunderstorm(s), 1 tracking(s)
   2009 not replaced: thunderstorm experiment(s) 1 depend on its strokes; delete them first, or run again with --drop-thunderstorms

With ``--drop-thunderstorms`` those experiments are deleted **whole** — their
thunderstorms, the stroke links, their trackings and windows go by cascade — before the
year is replaced, in its transaction: a failure keeps both the year and the experiments.
The whole experiment goes, not just the year, because a run is one consistent result and
cutting a year out of it would leave storms that crossed New Year half built. Rebuild the
experiment afterwards. Should the check ever miss an experiment, ``RESTRICT`` refuses the
delete, the year is rolled back and the error says its strokes are in thunderstorms.

**Every flash is numbered.** Strokes are grouped by ``(network_version, secidx)`` over
the whole file, before it is split into years, ordered by instant (and by line for the
few at the same microsecond), and stored with their ``multiplicity`` and
``stroke_index``.

**"Not recorded" becomes NULL.** A row with ``numsensors = 0`` is the first network
generation (``network_version = 1``), whose ``0`` sensor count and chi-squared are stored
as ``NULL``. Instants are UTC; ``nuvolterra`` becomes ``cloud_to_ground``; an empty
``idmunicipi`` becomes ``NULL``.

**The point is stored twice**: as published in ETRS89 on ``meteocat_lightning``, and
reprojected to EPSG:4326 on ``lightning``.

**The country is resolved by spatial join** against the OCHA level-0 boundaries, cut
with ``ST_Subdivide`` into pieces of at most 256 vertices so six million points can be
tested in minutes. Strokes at sea get none. Without the OCHA boundaries every stroke is
stored with no country and a warning: import them first with
:doc:`ocha_import_admin_boundaries`, since the country cannot be filled in afterwards
without re-importing.

**A row is refused** — logged with its line and the column at fault, counted and
skipped — when it is not a reading of the format or would break a constraint: a value
that is not a number, an impossible date, a ``nuvolterra`` other than ``t``/``f``, a
municipality code that is not six digits, a coordinate out of range, a minor axis larger
than the major, a negative sensor count, or a chi-squared on a stroke with no sensor
count. No row of the 2006-2020 delivery is refused.

The run ends with the strokes and flashes per year and network generation, and — when
writing — how many found no country. Reading the largest file, 2006, takes about seven
seconds; writing 2009's 331,136 strokes takes about half a minute, so the whole delivery
is of the order of ten minutes. A dry run over those two years reports:

.. code-block:: text

   2006: 861822 stroke(s) in 307162 flash(es) (version 1: 861822)
   2009: 331136 stroke(s) in 220796 flash(es) (version 1: 204788, version 2: 126348)

In QGIS the strokes are the ``v_meteocat_lightning_4326``, ``v_meteocat_lightning_4258``
and ``v_meteocat_lightning_25831`` views — the same rows in three CRSs; see
:ref:`migrations-views`. Filter on ``stroke_index = 1`` for one point per flash, and on
``network_version`` to keep September 2009 from counting twice.

API reference
-------------

.. automodule:: src.apps.imports.lightnings.catalonia_meteocat.import_lightnings
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.lightnings.catalonia_meteocat.readers
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.lightnings.common
   :members:
   :show-inheritance:
