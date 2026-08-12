CONAF seasonal fire report import (Chile)
=========================================

Imports CONAF's seasonal fire reports — **23 published archives, 95,868 features,
2010-2011 to 2024-2025** — into :doc:`../providers/conaf_wildfire` and
:doc:`../providers/conaf_ignition`, with their classifications going into
:doc:`../providers/conaf_fire_cause`.

Each archive is staged with ``ogr2ogr`` and mapped to the models by one statement, and
each season is committed in a transaction of its own. Re-importing a season replaces it.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires -d punts/

   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires \
         -s punts/if_temporada_2023_2024.rar

   # only one season, named by its first year, read from TEMPORADA in the data
   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires \
         -d punts/ -y 2016

   # do all the work and roll it back
   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires \
         -d punts/ --dry-run

Import the boundaries and the time zone areas first —
:doc:`ocha_import_admin_boundaries` and :doc:`time_zone_import_time_zones` — because both
are resolved at import time and cannot be filled in afterwards without re-importing.
Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host``,
``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

The archives are RAR
--------------------

GDAL has no ``/vsirar/``, so the ``/vsizip/`` path the other importers use does not apply.
:func:`~src.apps.imports.wildfires.chile_conaf.archives.archive_datasource` unpacks a
``.rar`` into a temporary directory with ``unrar`` (falling back to ``7z``) and hands the
result to the shared reader; anything that is not a RAR — a zip, an unpacked directory, a
bare ``.shp`` — goes straight there, so a user who has unpacked the archives by hand needs
none of it.

Which grid a season is staged on
--------------------------------

Read from the layer's own ``.prj`` rather than from its file name.
:data:`~src.providers.chile_conaf.SOURCE_SRID_EASTER` for a layer whose projection names
``WGS_1984_UTM_Zone_12S``, :data:`~src.providers.chile_conaf.SOURCE_SRID_MAINLAND`
otherwise — including for ``if_temporada_2024_2025``, which ships **no projection at
all**, just bare geographic WGS 84, and whose 6,262 fires are ordinary mainland ones.
Defaulting the other way would put a whole season on the Rapa Nui grid.

The staged extent is then checked against the plausible bounds of the chosen grid. It is a
warning and not a refusal: the ``.prj`` files are the least reliable part of this archive
and a bounds test wide enough to admit Magallanes is not tight enough to be certain with.
What it *is* certain about is the case that matters — a mainland layer staged on the Rapa
Nui grid, which is out by thousands of kilometres.

One transaction per season, and per territory
---------------------------------------------

.. warning::

   The mainland and Easter Island are **separate archives for the same season**. A delete
   scoped to the season alone therefore wipes the other territory's half of it, which is
   how 234 Rapa Nui fires and 6,262 mainland ones went missing during development.

   The delete is scoped to the season **and the grid**, so importing
   ``if_temporada_2023_2024`` leaves ``if_isla_pascua_2023_2024`` alone.

Twenty-three layers, one mapping
--------------------------------

The published column names drift throughout: ``NOM_INCEN`` / ``NOMBRE`` / ``Nombre_inc``,
``NUMERO_REG`` / ``NUMERO_RE`` / ``N_MERO_RE`` / ``NUMERO``, ``AMBITO`` / ``N_MBITO``,
``PINO_00_10`` / ``PINO_0_10`` / ``PINO_0_A_1``, ``INICIO_IN``+``EXTINCION`` /
``FH_INICIO``+``FH_EXTINCI``. An alias map resolves all of them onto one set of canonical
names.

Whole columns are also simply **absent**, which is normal rather than an error:
``if_isla_pascua_2013_2014`` publishes no ``REGION``, ``PROVINCIA``, ``COMUNA``, ``HUSO``
or dates and has 39 fires, a season and a cause. Only seven attributes are required —
``TEMPORADA``, ``CAUSA_GENE``, ``CAUSA_ESPE``, ``SUPERFICIE``, ``ARBOLADO``, ``MATORRAL``,
``PASTIZAL`` — and a layer carrying all seven is a CONAF report layer whatever else it is
missing.

Everything textual is staged as ``text``, the two coordinates included: 2023-2024
publishes ``UTM_E`` as ``'317709 E'``, which is not a number until the suffix is off it,
and casting the column would lose the row rather than the suffix.

Where a fire is, and why it is quick
------------------------------------

Every fire is given the country and the time zone area its point falls in. Done the
obvious way — ``ST_Contains`` against ``admin_boundary`` — that lookup costs about 100 ms
*per fire*, because Chile's OCHA level 0 boundary is 8.7 million vertices and 134 MB: the
spatial index finds the country immediately and then every row tests against the whole of
it. A season of 5,000 fires took a quarter of an hour, nearly all of it in that one test.

So the run first copies the countries and zones its points could be in into two staging
tables, cut into pieces of at most 256 vertices with ``ST_Subdivide`` and indexed
(:func:`~src.apps.imports.wildfires.chile_conaf.import_wildfires.build_lookup_parts`). The
same lookup against the pieces costs 0.03 ms and gives the same answer, the pieces being a
tiling of the country they came from. The 2010-2011 season imports in about 35 seconds,
half of it the cutting.

The pieces are cut for a box rounded out to
:data:`~src.apps.imports.wildfires.chile_conaf.import_wildfires.EXTENT_SNAP_DEGREES`
degrees around the staged points and kept for the archives that follow, so a run over the
whole directory cuts Chile up two or three times rather than 23. They live beside the
staging table, are dropped with it, and ``--keep-staging`` keeps them too.

.. note::

   The pieces are tested with ``ST_Intersects``, not ``ST_Contains``: subdividing a
   country creates internal edges that were never part of its border, and ``ST_Contains``
   rejects a point sitting exactly on one, so a fire could fall down the crack between two
   pieces of the same country. The difference anywhere else is a point exactly on a real
   border, which now gets one of the two sides instead of neither.

What the run reports
--------------------

Counts, not silence: how many records were read and written, the split of start dates
between minute, day and season-only, how many published an end, how many published an end
*before* their start (stored as published — swapping them would invent a fire that ran the
other way), how many have subtotals that do not sum to their total, how many publish no
cause, how many matched no time zone area, and every published cause the reconciliation
tables do not yet know.

.. warning::

   The run warns when a large share of a season is
   :data:`~src.providers.chile_conaf.PRECISION_SEASON`, because that is what a reader
   needs to know before computing anything about months, hours or durations. Over the
   whole archive it is 51.6%.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.chile_conaf.import_wildfires
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.wildfires.chile_conaf.archives
   :members:
   :show-inheritance:
