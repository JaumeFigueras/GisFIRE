NFDB wildfire import (Canada)
=============================

Imports the *Canadian National Fire Database — Agency Fire Data*: one zipped shapefile,
1.1 GB of it, holding **448,602 fire points** filed by thirteen provincial, territorial and
Parks Canada agencies over 1930-2025. **195,240 are natural-cause**, which makes this the
largest lightning-attributable set in GisFIRE and the reason the archive is worth importing.

Each published row becomes two: a fire report and the point it was filed at — the EGIF and
Greek shape, and what this dataset is. The Canadian perimeters are
:doc:`nbac_import_wildfires`'s to import, into a provider of their own.

Usage
-----

.. code-block:: console

   python3 -m src.apps.imports.wildfires.canada_nfdb.import_wildfires \
       -s /path/to/NFDB_point_shp.zip

   python3 -m src.apps.imports.wildfires.canada_nfdb.import_wildfires \
       -s NFDB_point_shp.zip --year 2023

   python3 -m src.apps.imports.wildfires.canada_nfdb.import_wildfires \
       -s NFDB_point_shp.zip --from-year 1930

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` and the
:doc:`time zone areas <time_zone_import_time_zones>` first. The whole archive imports in
about a minute — 382,412 fires from 1973 on.

What the import refuses, and why each
-------------------------------------

The published summary is unusually frank — *"the data contained in the CNFDB are not
complete nor are they without error. Locations are approximate."* — and the import takes it
at its word. Four filters, each counted and reported:

Before 1973
    To line the archive up with NBAC, which the service distributes no earlier year of.
    About 2% of the rows, with no perimeter to bind to and no lightning data of that period
    to attribute them against. ``--from-year`` moves the cut; ``--from-year 1930`` takes
    everything.

No year
    95 rows carry ``YEAR = -999``, the service's sentinel for *not known*.

No report date
    4,047 rows. ``wildfire.start_date_time`` is ``NOT NULL`` and, unlike NBAC, this dataset
    publishes no second date to fall back on — so such a row is refused rather than dated to
    1 January. Inventing a date would put four thousand fires on New Year's Day, which is
    exactly the artefact that makes the Portuguese archive hard to reason about.

A coordinate that is not in Canada
    244 rows: 154 null or exactly ``(0, 0)`` and the rest projected metres that have leaked
    into the published degrees columns — the published ``LONGITUDE`` minimum is
    **−5,617,700**, which is an easting.

The last of these does **not** refuse the fire. A report whose location is unusable is
still a report, so it is stored with a ``NULL`` ``ignition_id`` and no point, exactly as a
Spanish *parte* with no coordinate is. Only the point is dropped.

The published columns are checked against the geometry
------------------------------------------------------

The shapefile carries ``LATITUDE`` and ``LONGITUDE`` as attributes *and* a projected
geometry, and they can disagree — that is how the bad rows are visible at all. Neither
attribute is stored: the geometry becomes the point, and the columns are used only to test
it, which is why :doc:`../providers/nfdb_ignition` has no coordinate columns of its own.

A row where the two disagree is reported and its point dropped: one of them is wrong, and
the import should not silently prefer either.

``PRESCRIBED`` is read conservatively
-------------------------------------

The agencies write ``1``, ``Yes``, ``0``, ``No``, ``PB`` — and on most rows nothing at all.
:func:`~src.providers.canada_nfdb.is_prescribed` reads a recognised affirmative as true and
**everything else as false**, blanks included, because a prescribed burn is rare and
reading silence as *not prescribed* is wrong far less often than the reverse.

.. note::

   ``PB`` — *prescribed burn* — is by far the commonest affirmative in the archive: **437
   rows against a single ``1``**. It is in the vocabulary because the import reported it as
   an unrecognised spelling on the first real run against the published data, and it is
   unambiguous: 371 of the 437 also carry ``H-PB`` on ``CAUSE2``, which is 371 of that
   value's 372 occurrences in the whole archive.

   A value that is neither a recognised yes nor a recognised no is still stored as false,
   and the run **counts and reports it** — which is what stops the next new spelling being
   absorbed in silence.

A year is the unit, and a year is the step
------------------------------------------

There is one file rather than 53, but the unit replaced is still a **year**: the import
reads which years the staged data holds and replaces exactly those. ``--year 2023``
re-imports 2023 alone out of the 1.1 GB archive without touching anything else.

**And a year is also how much work is done at a time.** The archive is staged once and
then transformed one year per statement, each in a transaction of its own:

.. code-block:: text

   53 year(s) to import: 1973-2025
   [1/53] 1973: imported 4392 fire(s) in 3s
   [2/53] 1974: imported 5203 fire(s) in 3s
   ...

.. important::

   This was one statement over the whole archive, which is the better shape on paper —
   one pass, one plan, one transaction — and it does not survive the real data. The
   mapping materialises the row set six times over, and at 380,000 rows carrying a
   geometry each that is enough to take a machine to the OOM killer, which is where a
   1.1 GB import that reports nothing and stores nothing ends up.

   **A run that finishes slower is worth any number of runs that do not finish.** It is
   the same trade the burnt-area reports make for the same reason — see
   :doc:`nbac_wildfire_statistics`.

   The shapefile is still read **once**. It does not have to be read per year: the
   staged table is already in PostgreSQL and is read year by year from there, and
   re-running ``ogr2ogr`` 53 times over a 1.1 GB archive would cost far more than it
   saved. What was too big was never the load — it was the transform.

Nothing about the figures changes. Every count in the summary is a count over a
partition of the staged rows, so the totals are what one pass would have reported.

What does change is what an interruption leaves behind: **each year is atomic, and no
longer the whole run**. A run killed at year 31 leaves the first thirty years imported
and the rest untouched, where before it left nothing at all — and a year is exactly what
``--year`` picks the run back up by. ``--dry-run`` rolls back each year in turn, so it
still writes nothing.

.. warning::

   If an NBAC perimeter is bound to a fire of a year being replaced, the import **stops**
   and says so rather than dying on a foreign key from inside a 200-line statement. The
   link lives on ``nbac_wildfire`` and points this way, so replacing these rows would leave
   it dangling. Nothing writes that link yet.

   That check runs **once, over every year in scope, before the first year is written**.
   It has to: the years commit one by one now, so a refusal discovered halfway through
   would leave the earlier years replaced and the later ones not.

One run at a time
-----------------

.. danger::

   **Never run two imports of this archive at once.** They share one staged table, and
   the load is ``ogr2ogr -overwrite`` — a ``DROP`` and ``CREATE`` outside any
   transaction this application controls. The second run's load replaces the table the
   first is walking year by year, so the first imports **nothing** into every year it
   has not yet reached — having already deleted those years — and then drops the table
   out from under the second one's ``COPY``.

   This is not hypothetical. On 2026-08-05 one run reported ``imported 94480 fire(s)
   over 1973-2025`` while leaving 1986 onwards empty, and the other died with
   ``relation "staging.nfdb_points" does not exist``.

The application now stops that happening, in two places:

* a run holds a **PostgreSQL advisory lock** on its staged table for its whole length,
  and a second run is refused immediately — not queued, since it would be waiting on a
  table the first is about to drop. The lock goes with the connection, so a killed run
  leaves nothing to clean up. ``--staging-table`` gives a run a table of its own if two
  really are wanted at once;
* **no year is committed if its staged rows have gone missing.** The years were listed
  by reading the staged table and the transform applies the same condition to it, so a
  year that is on the list and turns out to have no rows means the table changed
  underneath the run. The transform shares a transaction with the delete that emptied
  the year, so refusing there rolls both back and the year keeps the fires it had.

The first stops the collision; the second means that if one happens anyway, the run
fails loudly instead of quietly emptying half the archive.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.canada_nfdb.import_wildfires
   :members:
   :show-inheritance:
