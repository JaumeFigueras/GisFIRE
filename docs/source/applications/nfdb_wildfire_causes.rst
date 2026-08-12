NFDB wildfires by cause (Canada)
================================

Counts the Canadian agency fire reports by published cause, per country and year: how
many fires the agencies filed, how many have a **determined** cause, how many of those
were natural, and how many hectares those natural fires reported burning.

The companion of :doc:`nfdb_wildfire_statistics`, over the same fires, the same years
and the same scope — so the ``Country``, ``Year`` and ``Fires`` columns of the two agree
row for row. It is also the twin of :doc:`nbac_wildfire_causes`, the same fires seen
from the other side, and the two are meant to be read together.

.. warning::

   **The NFDB publishes no lightning category either.** ``CAUSE`` takes three values —
   ``N``, ``H`` and ``U`` — and ``N`` is the nearest thing to one. It is dominated by
   lightning in the Canadian boreal and is not defined as lightning, so the column is
   headed ``Natural`` and never ``Lightning``.

   At **172,430 fires** it is by a wide margin the largest natural-cause set in GisFIRE,
   and unlike NBAC's every one of them has a point and a date. That is what this dataset
   is here for.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_causes \
       --year 2023 --csv 2023.csv --docx 2023.docx

   # the only way to get a number that means one thing
   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_causes \
       --agency NT --csv northwest-territories.csv

   python3 -m src.apps.statistics.wildfires.canada_nfdb.wildfire_causes \
       --cause human --csv human.csv

At least one of ``--csv`` and ``--docx`` is required. The application only reads.

Output
------

The columns, in order — the same headings as :doc:`nbac_wildfire_causes` uses, so the
two CSVs can be concatenated and compared, which is most of the reason for reading them
as a pair:

=======  ====  =====  ==========  =======  ===========  ============  =================
Country  Year  Fires  Determined  Natural  Natural (%)  Natural (ha)  Natural (% of ha)
=======  ====  =====  ==========  =======  ===========  ============  =================

Each country gets its years newest first and then its summary row. Under the default
``--country-source geometry`` there can be a ``United States of America`` block: a
Canadian agency's report whose published point falls over the border is counted where
the point is.

Over the whole archive, under ``--country-source filed``:

=======  ======  =======  ==========  =======  ===========  =============  =================
Country  Year     Fires   Determined  Natural  Natural (%)  Natural (ha)   Natural (% of ha)
=======  ======  =======  ==========  =======  ===========  =============  =================
Canada   2023       6830        6517     3825        58.69   16220878.79               97.03
Canada   1995       8451        8250     3518        42.64    7002347.75               95.34
Canada   Total    382047      374651   172430        46.02  129128595.02               90.70
=======  ======  =======  ==========  =======  ===========  =============  =================

Half the fires, nine tenths of the hectares
---------------------------------------------

=============================================  =============  ================
Over the whole archive                         …of the fires  …of the hectares
=============================================  =============  ================
NFDB points (this report)                             46.02%            90.70%
:doc:`NBAC perimeters <nbac_wildfire_causes>`         67.18%            90.54%
=============================================  =============  ================

.. important::

   The two archives are **not** contradicting each other. They count different
   populations: NBAC maps what burnt, so it is dominated by large remote fires; the
   NFDB records every call-out thirteen agencies filed, including tens of thousands of
   small human-caused fires near roads and towns that were never worth mapping — two
   thirds of this archive is under one hectare.

   That they disagree so much about the **count** and so little about the **area** is
   the most useful thing either of them says: the answer to *how much of Canada's burnt
   area is natural-cause* does not depend on which archive you ask, and it is about nine
   hectares in ten.

Why the denominator is the determined fires
---------------------------------------------

``U`` is a published category here too, and unlike NBAC's ``Undetermined`` it is small —
7,396 fires, under 2% — so the choice of denominator changes this report much less than
it changes that one.

It is made the same way regardless, for two reasons: so the two reports' percentages are
the same kind of number and can be compared at all, and because ``U`` is not evenly
spread **between the agencies**, which is where it bites here.

The natural share is a property of the agency
-----------------------------------------------

==========  ========  ==========================  ================
Agency      Fires     Natural, % of determined    ``U``, % of all
==========  ========  ==========================  ================
NT            13,646                        83.0               2.7
PC             3,660                        65.0               3.9
YT             6,713                        62.4               3.1
BC           109,377                        53.6               0.4
MB            23,634                        50.9               0.1
ON            65,650                        49.0               2.0
SK            26,990                        47.2               0.2
AB            60,483                        44.6               2.9
QC            43,886                        28.4               0.0
NB            12,181                        10.0              12.2
NL             4,695                         9.8               0.3
NS            11,078                         2.6              14.7
PE                54                         0.0               0.0
==========  ========  ==========================  ================

.. warning::

   **The national figure is a weighted average of thirteen different fire regimes, and
   the weights are reporting volumes rather than areas.** The Northwest Territories file
   83% natural and Nova Scotia 2.6%; British Columbia alone contributes 109,377 of the
   382,047 rows, so the national percentage is largely British Columbia's.

   ``--agency`` is how to get a number that means one thing, and a trend across the whole
   archive is partly a trend in which agencies were filing.

Why ``unknown`` cannot be counted
-----------------------------------

``--cause`` takes ``natural`` or ``human``, for the reason :doc:`nbac_wildfire_causes`
gives: ``U`` is the complement of the denominator, so its share of the determined fires
is zero by construction. ``Fires`` minus ``Determined`` is the unknown count.

The hectares are the agencies' own
------------------------------------

``SIZE_HA`` as filed, and **not** NBAC's mapped area: this dataset publishes no
perimeter. A reported zero counts as a fire and contributes nothing to the hectares,
which is what it is.

Which fires are counted
-----------------------

Exactly its companion's rule, so the two agree: every imported fire, declared prescribed
burns excluded unless ``--include-prescribed``, and — under the default
``--country-source geometry`` — only those whose published point falls inside a country.

One year at a time
------------------

One statement per year, and here it is not a formality: under ``--country-source
geometry`` every fire is a point-in-polygon test against country polygons of millions of
vertices, and the memory that goes into them is only released when the statement ends.

.. note::

   **A full-archive run in ``geometry`` mode takes about twenty minutes** — it is
   380,000 containment tests against country polygons of millions of vertices — and
   ``--country-source filed`` answers the same question about the causes in seconds.

   The two modes were run against each other over the whole archive to find out what
   the shortcut costs:

   ===================================  =========  ==============  ================
   Whole archive                        Fires      Natural (%)     Natural (% of ha)
   ===================================  =========  ==============  ================
   ``filed`` (every fire is Canadian)     382,047           46.02             90.70
   ``geometry``, Canada row               380,010           46.21             90.71
   ``geometry``, United States row            154           54.73             28.78
   ===================================  =========  ==============  ================

   Testing the points moves 154 fires into a United States row and drops **1,883**
   whose coordinate is inside no country — and it changes the national natural share by
   0.19 of a point and the area share by 0.01. So for a question about *causes*,
   ``filed`` is a sound shortcut and the twenty minutes buy very little.

   It is still the default, because it is the honest answer and because the companion
   :doc:`nfdb_wildfire_statistics` needs it for the same reason: a report that credits
   Canada with fires whose own coordinates say otherwise is wrong even when the
   difference rounds away.

Shared with the companion report
---------------------------------

The years query, the scope conditions, the country resolution, the agency lookup and the
country ordering are **imported from** :doc:`nfdb_wildfire_statistics` rather than
copied. Two reports over one dataset that disagreed about which fires are in scope, or
about which country one is in, would be worse than one report.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.canada_nfdb.wildfire_causes
   :members:
   :show-inheritance:
