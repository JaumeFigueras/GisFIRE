NBAC wildfires by cause (Canada)
================================

Counts the Canadian burned-area perimeters by published cause, per year: how many fires
there were, how many have a **determined** cause, how many of those were natural, and
how many hectares those natural fires burnt.

The companion of :doc:`nbac_wildfire_statistics`, over the same fires, the same years
and the same scope — so the ``Country``, ``Year`` and ``Fires`` columns of the two
agree row for row and the pair can be read side by side. What that one measures in
hectares, this one counts by cause. It is also the twin of
:doc:`nfdb_wildfire_causes`, and the two are meant to be read together.

.. warning::

   **NBAC publishes no lightning category.** ``FIRECAUS`` takes exactly three values,
   and the published metadata glosses the relevant one *"Ignition source by natural
   cause. Most often lightning."*

   ``Natural`` is the finest answer this dataset supports and is what the report counts
   by default. In the Canadian boreal it is dominated by lightning, so it is a good
   proxy — and it is a proxy, which is why the column is headed ``Natural`` and never
   ``Lightning``.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_causes \
       --year 2023 --csv 2023.csv --docx 2023.docx

   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_causes \
       --cause human --csv human.csv

At least one of ``--csv`` and ``--docx`` is required. The application only reads.
Settings come from the environment (``.env``, see :doc:`../setup/configuration`).

Output
------

=======  ======  =====  ==========  =======  ===========  ============  =================
Country  Year    Fires  Determined  Natural  Natural (%)  Natural (ha)  Natural (% of ha)
=======  ======  =====  ==========  =======  ===========  ============  =================
Canada   2025     1919        1783      958        53.73    5500397.75              76.33
Canada   2024     1948        1864     1350        72.42    4752551.22              99.09
Canada   2023     2215        1999     1399        69.98   13889929.12              97.09
Canada   1977     1126         175      111        63.43     754594.83              92.00
Canada   Total   51418       38656    25971        67.18  104179051.12              90.54
=======  ======  =====  ==========  =======  ===========  ============  =================

(a run over the whole published archive, prescribed burns excluded; four of its
fifty-four rows.)

**1977 is the row to read twice**: 1,126 fires and 175 determined causes. Its 63.43% is
a percentage of a seventh of the year.

Nine hectares in ten, and both datasets agree on it
-----------------------------------------------------

This is the finding the report exists to make visible, and the reason it has an area
column where :doc:`the Portuguese <icnf_wildfire_causes>` and :doc:`Spanish
<egif_wildfire_causes>` counts-by-cause reports have none.

=========================================  =============  ================
Over the whole archive                     …of the fires  …of the hectares
=========================================  =============  ================
NBAC perimeters (this report)                     67.18%            90.54%
:doc:`NFDB points <nfdb_wildfire_causes>`         46.02%            90.70%
=========================================  =============  ================

The two Canadian archives disagree by **twenty-one points** about how many fires are
natural, and agree to **two tenths of a point** about how much of the area is.

They count different populations — NBAC maps what burnt, so it is dominated by large
remote fires; NFDB records every call-out thirteen agencies filed, two thirds of which
are under one hectare — and they are looking at the same hectares. Two independently
built archives converging on the same answer to the question that matters is worth
considerably more than either saying it alone, and a report that counted only fires
would show the disagreement and hide the agreement.

Why the denominator is the determined fires
---------------------------------------------

``Undetermined`` is a **published category here and not a missing value** — 12,762 of
the 51,418 fires — and it is not evenly spread:

=========  =======  ============  =================  ========================
Decade     Fires    Undetermined  Natural, % of all  Natural, % of determined
=========  =======  ============  =================  ========================
1970s        5,386         3,777               17.1                      57.2
1980s        5,233         1,355               48.4                      65.3
1990s        6,773         2,845               44.6                      76.9
2000s       10,713         3,109               49.5                      69.8
2010s       13,349           910               61.1                      65.6
2020s        9,964           766               60.5                      65.5
=========  =======  ============  =================  ========================

The right-hand column is a fire statistic. The one beside it is a **reporting**
statistic wearing the same units: its rise from 17.1% to 60.5% is almost entirely the
fall in how many causes were left undetermined, not a change in what started the fires.

So the denominator is the determined fires, and ``Determined`` is a column of its own
so that it is never out of sight — the same decision :doc:`icnf_wildfire_causes` makes
about its ``Classified`` column. ``Fires`` minus ``Determined`` is the undetermined
count, and the run logs it.

Where nothing is determined there is no percentage to give, and the cell is **empty**
rather than zero, which would be a claim.

.. warning::

   Even the determined share is a **floor** for the natural one. ``Undetermined`` fires
   are not causeless, they are uninvestigated — and in the remote boreal an
   uninvestigated fire is more likely than average to be a lightning fire, because
   nobody was there to see it start or to be blamed for it. The bias in the missing
   quarter runs the same way as the answer.

Why ``undetermined`` cannot be counted
----------------------------------------

``--cause`` takes ``natural`` or ``human``. ``Undetermined`` is the complement of the
denominator rather than one of the things being compared against it: its share of the
determined fires is zero by construction, every time. It is not hidden — it is
``Fires`` minus ``Determined``.

The hectares are ``POLY_HA``, and that costs nothing
------------------------------------------------------

The companion report measures the perimeter geodesically by default; this one reads the
published ``POLY_HA``. They are the **same quantity** — the service computes it on an
equal-area projection, and over the archive the two differ by seven tenths of a hectare
in 132.7 million, 0.0000005%. Reading a column costs nothing where ``ST_Area`` over a
geography is the most expensive thing the companion does, and a counts-by-cause report
has no business being the slower of the two.

Which fires are counted
-----------------------

Exactly its companion's rule, so the two agree: every imported perimeter of the year,
prescribed burns excluded unless ``--include-prescribed``. Nothing is tested against a
boundary, so there is no ``--country`` or ``--country-source`` and the ``Country``
column is the constant ``Canada``.

One year at a time
------------------

One statement per year, as in every report here. Counts and sums both decompose over a
partition of the fires, so the ``Total`` row is exactly what a single pass would have
returned.

Shared with the companion report
---------------------------------

The years query, the scope conditions, the country name and the percentage helpers are
**imported from** :doc:`nbac_wildfire_statistics` rather than copied. Two reports over
one dataset that disagreed about which fires are in scope would be worse than one
report, and a copy is a thing that drifts.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.canada_nbac.wildfire_causes
   :members:
   :show-inheritance:
