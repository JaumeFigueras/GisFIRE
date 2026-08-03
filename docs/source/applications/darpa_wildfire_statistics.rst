DARPA wildfire statistics (Catalonia)
======================================

Reports the Catalan DARPA burnt area cartography per year: how many fires there were, the
smallest single fire, the largest single fire and the total burnt area in hectares — and
**how many of those fires are bound to the EGIF *parte* for the same fire**.

The fifth of the burnt-area reports, alongside :doc:`gwis_wildfire_statistics`,
:doc:`gfa_wildfire_statistics`, :doc:`icnf_wildfire_statistics` and
:doc:`egif_wildfire_statistics`. Its first six columns are theirs, in their order, so the
CSVs can still be concatenated on them; the two after them are this dataset's own.

.. important::

   **These hectares are measured, and this dataset publishes none of its own.** DARPA
   publishes ``CODI_FINAL``, ``DATA_INCEN``, ``MUNICIPI`` and ``GRID_CODE`` and no burnt
   area in any layer of any year — see :doc:`../providers/darpa_provider`. Every figure
   here comes off the polygon.

   That is the exact complement of :doc:`egif_wildfire_statistics`, whose hectares are
   written on a report form and whose polygon does not exist. The same Catalan fire has
   an area in both reports and the two are **different quantities**, not a figure and a
   correction of it. The ``EGIF matched`` column is what makes putting them side by side
   possible at all.

Usage
-----

Over everything, or narrowed to one year, to the fires above a size, or to the bindings
you are willing to trust:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics \
       --year 2013 --csv 2013.csv --docx 2013.docx

   python3 -m src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics \
       --min-area 5 --csv over-5-ha.csv

   # only the fires bound to a parte on the published identifier
   python3 -m src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics \
       --min-confidence 0.9 --csv identifier-matches.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database — not the fires and not the
bindings it counts. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host``,
``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   **There is neither** ``--country`` **nor** ``--country-source``. The department
   publishes the fires of Catalonia and nothing else, so there is nothing to select
   between and nothing to test against a boundary. Both are refused with a message saying
   why. See :ref:`darpa-no-country` below.

Output
------

=========  ======  =====  ============  ============  ==========  ============  ================
Country    Year    Fires  Minimum (ha)  Maximum (ha)  Total (ha)  EGIF matched  EGIF matched (%)
=========  ======  =====  ============  ============  ==========  ============  ================
Spain      2024       23          4.79        431.29     1213.13             0              0.00
Spain      2023       22          4.32        856.64     2406.44             0              0.00
Spain      2022       43          4.31       2683.60     6487.73            40             93.02
Spain      2013       10         13.79        734.28     1200.69            10            100.00
Spain      1994      109          6.75      22932.24   117633.58           100             91.74
Spain      Total     860          2.42      22932.24   318497.58           778             90.47
=========  ======  =====  ============  ============  ==========  ============  ================

(a run over the whole published archive, geodesic areas, every binding counted; six of its
forty rows.)

.. important::

   The ``Total`` row is **not** a total of every column above it. ``Fires``,
   ``Total (ha)`` and ``EGIF matched`` are sums; ``Minimum`` and ``Maximum`` are the
   smallest and largest fire of *any* year in scope; ``EGIF matched (%)`` is recomputed
   from the summed counts — the ratio of the totals, not the mean of the years' ratios.

The ``.csv`` writes bare numbers because it is read by another program more often than by
a person; the ``.docx`` writes them with thousands separators and right-aligned, with the
summary row in bold, because it is not.

How many matched the EGIF data
------------------------------

``EGIF matched`` counts the fires of the year carrying a link to an EGIF *parte*
(:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`), and
``EGIF matched (%)`` is that as a share of the ``Fires`` beside it.

The links are written by :doc:`darpa_bind_egif_wildfires`, which is where the rules and
the cascade behind them are set out. This report only counts what it finds.

* **It is a column, not a filter.** An unbound fire is still a fire and still contributes
  its hectares to its row. This is a report of the Catalan cartography that says how much
  of it can be joined to the national statistic — not a report of the joinable part.
* **It follows the scope.** Whatever ``--year`` and ``--min-area`` select, the matched
  count is counted over exactly those fires, so the percentage always has the ``Fires``
  column as its denominator.
* **A zero is usually a fact about EGIF's coverage.** The binding can only reach the
  campaigns that have been imported. In the table above, 2023 and 2024 are at 0% — 45
  perimeters with no EGIF campaign behind them at all — and that is the state of the
  exports, not a failure of the rules.

.. note::

   If nothing has ever been bound, every value in the column is zero, which looks exactly
   like a dataset that matched nothing. The log tells the two apart:

   .. code-block:: text

      WARNING No fire in scope is bound to an EGIF parte, so every EGIF matched column
              is zero. Nothing here can tell an unrun binding from a real absence of
              matches — run
              src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires, and note
              that it can only reach the EGIF campaigns that are imported

Not every binding is the same claim
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``--min-confidence`` counts only the bindings at or above a given
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.match_confidence`. Without it
every binding counts, whatever produced it.

Roughly three quarters of the links rest on an **identifier** — from 1997 the published
``CODI_FINAL`` *is* the EGIF ``report_number``, and four of the older formats decode into
one — and the rest on a date narrowed by a province and a municipality name, which is a
good rule and not a certainty. ``0.9`` is the boundary between the two kinds:

.. code-block:: bash

   # 601 of the 860 perimeters, against 778 counting every binding
   python3 -m src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics \
       --min-confidence 0.9 --csv identifier-matches.csv

The threshold changes no area and no fire count: it selects what counts as *matched*, and
nothing else in the row moves.

.. warning::

   The confidences are **an ordering, not probabilities**. Nothing has been calibrated
   against ground truth — there is no independent answer key for a 1989 fire — so
   ``--min-confidence 0.75`` selects a class of matching rule and does not mean "matches
   that are 75% likely to be right". See
   :data:`~src.providers.catalonia_darpa.wildfire.MATCH_METHOD_CONFIDENCE`.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.year` — the year of the
published layer the fire was read from — exactly as :doc:`icnf_wildfire_statistics` uses
the published ``Ano`` and :doc:`egif_wildfire_statistics` the filed ``Campania``.

Here the candidate years agree by construction, and it is **checked rather than assumed**:
the import verifies on every fire that the year of the published ``DATA_INCEN`` is the
year of the layer it is in, and it is true of all 4,533 burnt features. The column is
``NOT NULL`` and indexed and needs no timezone applied to it, which
``start_date_time`` would — a Catalan fire's instant is local midnight, the dataset
publishing no time of day anywhere.

Which fires are counted
-----------------------

Every imported Catalan fire with a perimeter, which on this dataset is every one of them.
A fire here *is* a perimeter: the features with no geometry, no code and no date are the
raster background class, and the import drops them before anything is stored.

.. note::

   **A fire is one published ``(code, date)``, not one polygon.** Three layers were
   vectorised from a raster and never dissolved — 4,533 burnt features are 860 fires, and
   one fire of 1994 is published as 1,309 separate polygons. The ``Fires`` column counts
   fires and the areas are of the dissolved perimeter; anything counting features would
   report 1994 as five times the fire year it was.

``--min-area HECTARES`` narrows it to the fires of at least that much. It behaves exactly
as in :doc:`icnf_wildfire_statistics`: the threshold is compared against the area this
report measures, it selects fires rather than rows of the report, a year whose fires are
all below it disappears rather than showing zeros, and the ``Total`` row summarises only
what was counted.

.. _darpa-no-country:

No country test
---------------

Every fire in this dataset is Catalan and therefore Spanish, because the department
publishes the fires of Catalonia and nothing else. The ``Country`` column is the constant
``Spain`` on every row and **nothing is tested against a boundary**.

That is :doc:`egif_wildfire_statistics`'s ``filed`` mode and not
:doc:`icnf_wildfire_statistics`'s default, and the difference is deliberate. There the
point of a containment test is to catch a perimeter digitised into the sea; here the
perimeters are the department's own cartography of its own territory, published on its own
grid, and there is nothing for such a test to find. Offering the option would be offering
to spend a point-in-polygon test per fire on a question already answered.

.. warning::

   The column says ``Spain`` and the report is **Catalonia's fires alone**. A total here
   is not a Spanish total and must not be read beside the EGIF report's as one: it is one
   autonomous community of seventeen. The region is in the title of the ``.docx`` and on
   this page, not in a column, so that the CSV keeps the shape the other four reports
   have.

How the area is measured
------------------------

The same two ways as the GFA and ICNF reports, chosen with ``--area-method``: ``geodesic``
on the WGS84 ellipsoid (the default) or ``equal-area`` in EPSG:6933. They agree to within
0.003%; see :doc:`gfa_wildfire_statistics` for the measurements behind that.

Why not the CRS the department publishes in
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The perimeters are also stored as published, in EPSG:25831 (ETRS89 / UTM zone 31N), on
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.perimeter_etrs89_utm31n` — a
projected grid in metres, and the one the department itself measures on. It is **not**
offered as an area method, for :doc:`the ICNF report's <icnf_wildfire_statistics>` reason:
UTM is a *transverse Mercator*, conformal and not equal-area.

The error is far smaller than the Portuguese case — Catalonia is one zone wide, with no
islands — but it is not nothing, and it is systematic:

.. code-block:: text

   the same polygon, EPSG:25831 vs geodesic
     Tortosa           (0.5E)    +0.028%
     Lleida            (0.6E)    +0.016%
     Val d'Aran        (0.8E)    +0.001%
     Barcelona         (2.2E)    -0.068%
     Girona            (2.8E)    -0.079%
     Cap de Creus      (3.3E)    -0.078%

A tenth of a percent, and it **varies with longitude** — over-measuring in the west,
under-measuring towards the central meridian in the east — so it does not cancel over a
year whose fires are not evenly spread across the country, which no fire year is. The two
methods that are offered differ by 0.003%, which is two ways of measuring the same thing
rather than a projection's distortion. A test asserts the omission stays deliberate.

To reproduce a figure measured on the department's grid, measure it there explicitly:

.. code-block:: sql

   SELECT year, sum(ST_Area(perimeter_etrs89_utm31n) / 10000.0) AS grid_ha
   FROM darpa_wildfire GROUP BY year ORDER BY year DESC;

One statement
-------------

The GWIS, GFA and ICNF reports issue one statement **per year**, because the memory a
point-in-polygon test against a country polygon needs is only released when the statement
ends, and a single pass over twenty million perimeters took a 30 GB machine to the OOM
killer.

This report is one statement, like the EGIF one. It tests nothing against a boundary at
all, and the whole archive is **860 fires** — four orders of magnitude short of the case
that died. The areas are computed once in a subquery and aggregated over; the ``Total`` row
is arithmetic over the years, by
:func:`~src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics.combine`, so the
output is the same shape as the other four either way.

Progress
--------

One spinner for the one statement. PostgreSQL does not report partial progress on an
aggregate, so what is shown is that the process is alive and how long it has been going:

.. code-block:: text

   \ Measuring the burnt area of the Catalonia fires and their EGIF matches... 0:00:02

Followed by what was computed and what matched:

.. code-block:: text

   INFO Computed 40 rows over 39 year(s) (geodesic areas, every fire)
   INFO 778 of 860 fire(s) are bound to an EGIF parte (90.47%)

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.catalonia_darpa.wildfire_statistics
   :members:
   :show-inheritance:
