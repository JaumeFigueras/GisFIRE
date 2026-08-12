NBAC wildfire statistics (Canada)
=================================

Reports the Canadian National Burned Area Composite per year: how many fires there
were, the smallest single fire, the largest single fire and the total area burnt in
hectares — and, this dataset's own pair, **how many of the year's fires carry a real
published date**.

The eighth of the burnt-area reports and GisFIRE's first outside Europe. Its first six
columns are the :doc:`GWIS <gwis_wildfire_statistics>`, :doc:`GFA
<gfa_wildfire_statistics>`, :doc:`ICNF <icnf_wildfire_statistics>`, :doc:`EGIF
<egif_wildfire_statistics>`, :doc:`DARPA <darpa_wildfire_statistics>`, :doc:`REDIAM
<rediam_wildfire_statistics>` and :doc:`Greek <greece_ffa_wildfire_statistics>`
reports', in their order, so the CSVs can still be concatenated on them; the two after
them are this dataset's own.

Its companion is :doc:`nfdb_wildfire_statistics`, which reports the same country's
fires as the agencies filed them. **The two do not agree and neither is wrong** — see
that page.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_statistics \
       --year 2023 --csv 2023.csv --docx 2023.docx

   # the service's own large-fire threshold
   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_statistics \
       --min-area 200 --csv large-fires.csv

   # natural-cause fires, which is not the same thing as lightning fires
   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_statistics \
       --cause natural --csv natural.csv

   # the hectares the service publishes, rather than the ones this measures
   python3 -m src.apps.statistics.wildfires.canada_nbac.wildfire_statistics \
       --surface published --csv published.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden
with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

.. important::

   **There is neither** ``--country`` **nor** ``--country-source``. Natural Resources
   Canada maps Canada's fires and nothing else, so there is nothing to select between
   and nothing worth testing against a boundary: the import already resolved one for
   51,816 of the 51,818 fires and every one of them is Canada. Both options are
   accepted by the parser and then refused with a message saying why, because anyone
   reaching for one has copied a command line from another report.

   The two fires with no boundary are a 0.76 ha burn off Nova Scotia and a 1.68 ha one
   beside it, which fall outside the OCHA coastline rather than outside Canada. Under a
   containment test they would simply vanish.

Output
------

=======  ======  =====  ============  ============  =============  =====  =========
Country  Year    Fires  Minimum (ha)  Maximum (ha)     Total (ha)  Dated  Dated (%)
=======  ======  =====  ============  ============  =============  =====  =========
Canada   2025     1919          0.00     632231.48     7304324.18   1906      99.32
Canada   2024     1948          0.00     451987.21     4916944.65   1911      98.10
Canada   2023     2215          0.00    1146936.73    14796456.54   2176      98.24
Canada   2013     1479          0.00     501737.41     3958255.12   1387      93.78
Canada   1995      789          0.00     828060.14     5772195.61    593      75.16
Canada   1977     1126          0.00      80309.35     1211977.72    176      15.63
Canada   1973      512          4.78     139772.45     1845111.03    268      52.34
Canada   Total   51418          0.00    1146936.73   132557203.23  41491      80.69
=======  ======  =====  ============  ============  =============  =====  =========

(a run over the whole published archive, measured geodesically, prescribed burns
excluded; seven of its fifty-four rows.)

.. important::

   The ``Total`` row is **not** a total of every column above it. ``Fires``,
   ``Total (ha)`` and ``Dated`` are sums; ``Minimum`` and ``Maximum`` are the smallest
   and largest fire of *any* year in scope; ``Dated (%)`` is recomputed from the summed
   counts — the ratio of the totals, not the mean of the years' ratios.

A minimum of ``0.00`` is normal and is not a missing value: 427 fires are under a
hundredth of a hectare and the smallest mapped polygon in the archive is about a
hundredth of a square metre.

The ``.csv`` writes bare numbers because it is read by another program more often than
by a person; the ``.docx`` writes them with thousands separators and right-aligned,
with the summary row in bold.

.. note::

   2023's 14,796,457 ha is the Canadian fire season that burnt more than the previous
   six put together, and its 1,146,937 ha single fire is the largest event in the
   archive. Nothing in the pipeline checks these figures against the outside world, so
   it is worth recording that they line up with what is publicly known of that year.

Measured, published or adjusted
--------------------------------

Like Andalusia, this dataset publishes **both** a perimeter and a burnt area, and
``--surface`` chooses which the report is of:

====================  ==============================================================
``--surface``         What it reports
====================  ==============================================================
``measured``          the area of the dissolved perimeter, by ``--area-method``
``published``         ``POLY_HA`` as the service computes it, summed over the parts
``adjusted``          ``ADJ_HA``, the adjusted area burned
====================  ==============================================================

Unlike Andalusia, ``measured`` and ``published`` here are the **same quantity**:

============================  ================
Surface                             Total (ha)
============================  ================
``measured`` (geodesic)         132,738,031.02
``measured`` (equal-area)       132,738,036.27
``published`` (``POLY_HA``)     132,738,030.32
``adjusted`` (``ADJ_HA``)       131,979,655.87
============================  ================

(the whole archive, prescribed burns included.)

The first three agree to 0.0000005%, and that is not luck: the published metadata says
``POLY_HA`` is computed on the Canada Albers Equal Area Conic projection, and an
equal-area projection and a geodesic measurement are two ways of answering the same
question. So there is no warning here of the kind :doc:`rediam_wildfire_statistics`
has to give — the two can be quoted interchangeably, and ``published`` is worth asking
for mainly as a check on the import.

.. warning::

   ``adjusted`` **is** a different quantity. It equals ``POLY_HA`` exactly on the
   49,306 fires no model was applied to, and on the 2,512 flagged ``ADJ_FLAG`` it comes
   out lower — 5,341,008.62 ha against 6,099,383.05. Read
   :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.area_adjusted` before
   quoting it: it is the flag saying whether a row's adjusted figure is a model output
   at all.

``--area-method`` applies to ``measured`` and to nothing else, and passing it with a
published surface is **refused rather than ignored**: nothing is measured there, so a
choice of how to measure would be a claim about a number that was read off a form.

How the measured area is measured
----------------------------------

``geodesic`` on the WGS84 ellipsoid (the default) or ``equal-area`` in EPSG:6933, as in
the GFA, ICNF, Catalan and Andalusian reports. Over this archive they agree to within
0.000004% — five hectares in a hundred and thirty-two million.

.. warning::

   **The published EPSG:3978 grid is not offered, and here that is not a rounding
   detail.** NAD83 / Canada Atlas Lambert is a Lambert *conformal* conic: it preserves
   angles, not areas, and over a country spanning 41°N to 83°N the distortion does not
   cancel. Measured there the archive totals **127,114,627 ha against 132,738,031** —
   4.2% short, silently and consistently.

   To reproduce a figure on the service's own grid, measure there explicitly:

   .. code-block:: sql

      SELECT year, sum(ST_Area(perimeter_lambert) / 10000.0) AS grid_ha
      FROM nbac_wildfire GROUP BY year ORDER BY year DESC;

How many carry a real date
---------------------------

``Dated`` counts the fires of the year whose start came from a published date — the
agency's ``AG_SDATE`` or the first satellite hotspot ``HS_SDATE`` — rather than from
the published ``YEAR`` alone, and ``Dated (%)`` is that as a share of the ``Fires``
beside it.

**9,941 of the 51,818 fires publish no date at all.** They carry
``date_time_precision = 'year'`` and a ``start_date_time`` of 1 January, which is a
placeholder satisfying a ``NOT NULL`` column rather than a claim about the fire.

It is very unevenly spread, which is why it is a column and not a footnote:

* 2010 onwards is over 90% dated every year, and usually over 98%;
* 1977 is **15.63%** and 1978 21.93% — four fires in five with no date;
* satellite hotspots only start in 1989, so before that a fire is dated if and only if
  an agency wrote a date down.

.. warning::

   **This report is sound, but a report grouped by month or day over the same data
   would not be.** A fifth of the archive would fall on the 1st of January, and in 1977
   it would be four fifths of that year. Anything finer than a year has to filter on
   :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.date_time_precision` first
   — which is exactly what this column is here to make visible.

Like the match columns of the Catalan and Andalusian reports, ``Dated`` is **a column
and not a filter**: an undated fire still contributes its hectares. And it follows the
scope, so the percentage always has the ``Fires`` column beside it as its denominator.

Which year a fire counts towards
---------------------------------

The published ``YEAR``, and not the year of the resolved ``start_date_time``. That is
the rule every report in this project follows, and here it matters twice over: a fifth
of the instants are placeholders, and 35 fires would move into a year the service did
not file them under.

Which fires are counted
-----------------------

Every imported fire, which is every fire of the 1973-2025 archive the service
distributes. 1972 is described in the published metadata and not distributed; nothing
here depends on it.

.. note::

   **A fire is one published ``GID``, not one polygon.** The published features are cut
   at provincial, territorial and national park boundaries, so a fire that crossed one
   is published as several polygons sharing a ``GID``. The import dissolves them —
   52,276 polygons are 51,818 fires — so nothing here counts or sums a fire twice, and
   ``POLY_HA`` and ``ADJ_HA`` are summed over the parts.

``--min-area HECTARES`` narrows it to the fires of at least that much **of the surface
being reported**, so the fires counted are always the fires the figures beside them
were computed from. 200 ha is the threshold the service's own *large fire*
distribution uses.

Prescribed burns are excluded by default
-----------------------------------------

400 of the 51,818 fires carry ``PRESCRIBED``, and a prescribed burn is a deliberate
fire rather than a wildfire. They are left out, the log says how many, and
``--include-prescribed`` counts them. On the archive total the exclusion is worth
180,828 ha — about 0.13% — but it is not evenly spread: none before 1980, 143 in the
2000s, and those 143 burnt 71,368 ha between them.

One cause, if you want one
---------------------------

``--cause`` narrows the report to ``natural``, ``human`` or ``undetermined`` fires.
The three values of ``FIRECAUS`` are ``NOT NULL`` on every fire and constrained to
those three, so the three runs partition the archive between them.

.. warning::

   ``--cause natural`` is **not a lightning filter**. The published metadata glosses
   ``Natural`` as *"Ignition source by natural cause. Most often lightning"* — a proxy,
   not a category, exactly like :doc:`ICNF's <icnf_wildfire_causes>` and unlike EGIF's
   named ``100 — Rayo``. Anything counting lightning fires from this report is counting
   natural-cause fires and should say so.

   The cause is also unevenly reported: **1976 and 1977 are 80% undetermined and 2017
   and 2018 barely 2%**, so a trend in ``--cause natural`` across fifty years is partly
   a trend in how willing an agency was to write ``Undetermined``.

There is no counts-by-cause companion application, unlike :doc:`icnf_wildfire_causes`
and :doc:`egif_wildfire_causes`: three values with no codes, no hierarchy and no labels
to translate are a filter on this report rather than a catalogue worth a report of its
own.

One year at a time
------------------

The years are found first, then each is measured by a statement of its own and the
summary rows are computed from their results — the :doc:`GWIS
<gwis_wildfire_statistics>` shape.

Fifty-one thousand perimeters do not need it the way twenty million do. It is built
this way because ``ST_Area`` over a geography is the expensive thing here and its
memory is only released when the statement ends, because these polygons are large, and
because five reports meant to be read side by side are worth keeping as one program
over five datasets. Nothing about the figures changes: all four aggregates decompose
over a partition of the fires, and every statement runs in one transaction and so
against one snapshot.

Progress
--------

One spinner per year, then what was computed:

.. code-block:: text

   INFO Finding the years the Canada perimeters cover: done in 0s
   / Measuring the burnt area of the Canada perimeters (measured, every cause, 2023: 3 of 53)... 0:00:28
   INFO Computed 54 rows over 53 year(s) (measured hectares, geodesic, every fire, every cause)
   INFO Excluded 400 prescribed burn(s) in scope; pass --include-prescribed to count them
   INFO 41491 of 51418 fire(s) carry a published date (80.69%); the rest are dated to 1 January of their year

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.canada_nbac.wildfire_statistics
   :members:
   :show-inheritance:
