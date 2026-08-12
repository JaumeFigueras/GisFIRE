NFDB wildfire statistics (Canada)
=================================

Reports the Canadian National Fire Database agency fire data per country and year: how
many fires the agencies filed, the smallest, largest and total area they **reported**
in hectares — and, this dataset's own column, **how many agencies filed anything at all
that year**.

The ninth of the burnt-area reports and the companion of
:doc:`nbac_wildfire_statistics`: the same country, the same fires, two different
measurements of them. Its first six columns are the other eight reports', in their
order, so the CSVs can still be concatenated on them; the seventh is this dataset's
own.

In kind it is the twin of the :doc:`EGIF <egif_wildfire_statistics>` and :doc:`Greek
<greece_ffa_wildfire_statistics>` reports rather than of the perimeter ones: these
hectares are **reported, not measured**, because the agencies publish a fire's location
and size and never its shape.

.. warning::

   **This report and the NBAC one do not agree, and neither is wrong.** Over the
   archive the agencies' reported sizes sum to about 166.5 million hectares against
   NBAC's 132.7 million of mapped burn. One is what somebody recorded at the time, the
   other what a satellite could see afterwards. Do not quote one as a correction of the
   other, and do not add them: they are the same fires counted twice.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics \
       --year 2023 --csv 2023.csv --docx 2023.docx

   # the service's own large-fire threshold
   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics \
       --min-area 200 --csv large-fires.csv

   # one agency's natural-cause fires, which is the only series that means one thing
   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics \
       --cause natural --agency BC --csv bc-natural.csv

   # take the agencies' word for the country instead of testing the point
   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics \
       --country-source filed --csv filed.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden
with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

.. important::

   **There is no** ``--surface`` **and no** ``--area-method``. The agencies report one
   burnt area per fire, ``SIZE_HA``, and this dataset publishes no perimeter, so
   nothing is measured and no CRS is involved. Both options are accepted by the parser
   and then refused with a message saying why, because anyone reaching for one has
   copied a command line from a perimeter report — the companion NBAC one, most likely.

Output
------

The columns, in order:

=======  ====  =====  ============  ============  ==========  ========
Country  Year  Fires  Minimum (ha)  Maximum (ha)  Total (ha)  Agencies
=======  ====  =====  ============  ============  ==========  ========

Each country gets its years newest first and then its summary row, as in
:doc:`egif_wildfire_statistics` under ``--country-source geometry``. There is **no
World block**: this is one country's archive, and a block summarising Canada and the
handful of border fires beside it would be a total of two things that are not
comparable.

.. important::

   The summary row is **not** a total of every column above it. ``Fires`` and
   ``Total (ha)`` are sums; ``Minimum`` and ``Maximum`` are the smallest and largest
   fire of *any* year in scope; ``Agencies`` is the number of **distinct** agencies
   over the whole period — a union, not a sum. Thirteen agencies filing every year for
   fifty years are thirteen agencies, not six hundred and fifty.

A minimum of ``0.00`` is normal and is a real answer, not a missing value: tens of
thousands of rows report zero hectares and two thirds of the archive is under one
hectare. That is what ``--min-area`` is for — the service's own *large fire*
distribution keeps only the fires of 200 ha or more, which are about a twentieth of
the rows and over 97% of the area.

The ``.csv`` writes bare numbers because it is read by another program more often than
by a person; the ``.docx`` writes them with thousands separators and right-aligned,
with each summary row in bold.

Which country a fire counts towards
------------------------------------

This is the half of the report that matters most, and the reason its default is the
**opposite** of the Spanish one's.

Every stored fire is a point, not a polygon, and the points are agency reports: the
published summary says outright that *"locations are approximate"*. The import's only
geometric guard is a plausibility box round Canada, and a box round a country is not
the country — it contains a great deal of the United States, of Greenland and of three
oceans. A good many published coordinates land there, which is visible the moment the
layer is opened over a basemap in QGIS.

==========================  ====================================================
``--country-source``        What it does
==========================  ====================================================
``geometry`` *(default)*    tests the published point against the real OCHA
                            country polygons at report time
``filed``                   takes the agency's word for it: every report is a
                            Canadian one, so ``Country`` is the constant ``Canada``
==========================  ====================================================

Under ``geometry`` a fire inside no country is **dropped** and a fire over the American
border is reported as a ``United States of America`` row rather than folded into
Canada's. That is the point of it: the alternative quietly credits Canada with fires
whose own coordinates say otherwise.

.. note::

   Unlike :doc:`egif_wildfire_statistics`, where ``geometry`` costs half the archive
   because half of it publishes no coordinate at all, here it costs almost nothing:
   this dataset is points first, and only a couple of hundred imported fires have no
   usable one. That is what makes the cautious mode affordable as a default.

Whenever ``geometry`` is in force the log says how many fires were left out and why,
split between the two:

*no point published*
    the import could not use the published coordinate — a null, a zero, or projected
    metres that leaked into the degrees columns. A handful of rows.
*point in no country*
    the coordinate resolves to nowhere, which for a fire report means the sea. This is
    the number that says how much the plausibility box let through, and it is logged at
    ``WARNING``.

A point over a border is in **neither** count: it is inside a country, so it is
reported, as that country's row.

.. note::

   A fire's whole reported area is attributed to one country. Nothing here splits a
   fire between countries, and nothing needs to: these are points, and a point is in
   one place.

The Agencies column
-------------------

Thirteen provincial, territorial and Parks Canada agencies contribute, over wildly
different periods and at wildly different volumes — British Columbia files well over a
hundred thousand of the 448,602 published points and Prince Edward Island fifty-five.

.. warning::

   **A count over this archive is a count of what thirteen agencies chose to file.**
   Coverage, accuracy, vocabulary and start year all vary between them, so a trend
   across fifty years is partly a trend in reporting practice and a comparison between
   two provinces is partly a comparison of two filing standards.

``Agencies`` is that caveat made visible: it counts the distinct ``SRC_AGENCY`` values
behind the row. A year reported by nine agencies is not comparable with a year reported
by thirteen, however similar the hectares look.

``--agency CODE`` narrows the report to one of them — ``BC``, ``AB``, ``ON``, ``PC``, …
— which is the only way to make a series across the years mean one thing. Case does not
matter; an unrecognised code is answered with the list of the ones that are imported,
read from the database rather than written into the source, so a fourteenth agency
appearing in a future distribution needs no code change. Under ``--agency`` the
``Agencies`` column is the constant 1.

Which year a fire counts towards
---------------------------------

The published ``YEAR``, and not the year of ``start_date_time``. The two rarely
disagree here — the instant is resolved from ``REP_DATE`` — but the published year is
indexed and needs no timezone applied to it, which the instant would: Canada spans six
zones.

.. note::

   The column is nullable on the model, for the 95 published rows carrying the
   ``YEAR = -999`` sentinel. None can reach the database, the import's ``--from-year``
   floor being a lower bound on the same column. The report checks anyway and warns
   rather than silently leaving such a fire out of every year.

Which fires are counted
-----------------------

Every imported fire: the archive from 1973 on that publishes a report date, an agency
and one of the three causes. **The 1930-1972 points are published and deliberately not
imported** — see :doc:`nfdb_import_wildfires` — so a run of this report is a run over
1973 onwards whatever ``--year`` says.

``--min-area HECTARES`` narrows it to the fires reporting at least that much. A
reported zero counts by default.

One cause, if you want one
---------------------------

``--cause`` narrows the report to ``natural``, ``human`` or ``unknown`` fires. The
column is ``NOT NULL`` and constrained to the three values, so the three runs partition
the archive between them.

.. warning::

   ``--cause natural`` is **not a lightning filter**, exactly as in
   :doc:`nbac_wildfire_statistics`. It is the nearest thing this archive has to one, it
   is dominated by lightning in the Canadian boreal, and it is not defined as
   lightning.

   It is also, at roughly 195,000 fires, **the largest natural-cause set in GisFIRE**,
   and every one of them has a coordinate and a date. That is the reason this dataset
   is here.

Prescribed burns are excluded by default
-----------------------------------------

A prescribed burn is a deliberate fire rather than a wildfire, so the fires flagged
``PRESCRIBED`` are left out, the log says how many, and ``--include-prescribed`` counts
them.

.. warning::

   The flag is a weak one and the report does not pretend otherwise. Most agencies do
   not publish the column at all, and
   :func:`~src.providers.canada_nfdb.is_prescribed` reads silence as *not prescribed* —
   a deliberate, conservative choice. So this exclusion removes the prescribed burns
   that were **declared**, not the ones that happened.

   ``CAUSE2 = 'H-PB'`` on
   :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.fire_cause_detail` is the
   other, independent statement of the same thing. It is deliberately not folded in
   here: it is a *cause*, and mixing a cause into a flag would make the exclusion two
   different questions at once.

One year at a time
------------------

The years are found first, then each is measured by a statement of its own and the
summary rows are computed from their results — the :doc:`GWIS
<gwis_wildfire_statistics>` shape.

Under ``filed`` it would not be needed: that mode is an indexed aggregate over one
column of one table. Under ``geometry``, which is the default, each fire means a
point-in-polygon test against country polygons of millions of vertices, and the memory
that goes into them is only released when the statement ends. Half a million points is
well short of the twenty-million-perimeter case that met the OOM killer, but the shape
that survives it costs nothing here and the two modes are worth keeping identical.

Nothing about the figures changes. All four aggregates decompose over a partition of
the fires, and the agencies are unioned rather than added, so the summary rows are
exactly what one pass would have returned. Every statement runs in one transaction and
so against one snapshot.

Progress
--------

One spinner per year, then the audit and what was computed. The counts below are
written as ``N`` because they depend on the scope; the shape of each line does not:

.. code-block:: text

   INFO Finding the years the NFDB reports cover: done in 0s
   / Summing the reported burnt area of the NFDB fires (every agency, 2023: 3 of 53)... 0:00:09
   INFO Excluded N of N fire(s): N have no usable published point, N have one that is inside no country
   WARNING N fire(s) have a published coordinate that is inside no country — the import's only geometric guard is a plausibility box round Canada, and a box round a country contains a great deal of sea
   INFO Computed N rows over N country/countries and 53 year(s) (reported hectares, country from geometry, every fire, every agency)
   INFO 13 agency/agencies filed the fires reported: AB, BC, MB, NB, NL, NS, NT, ON, PC, PE, QC, SK, YT

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.canada_nfdb.wildfire_statistics
   :members:
   :show-inheritance:
