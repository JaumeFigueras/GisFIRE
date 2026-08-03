REDIAM wildfire statistics (Andalusia)
======================================

Reports the Andalusian REDIAM burnt area cartography per year: how many fires there
were, the smallest single fire, the largest single fire and the total burnt area in
hectares — and **how many of those fires are bound to the EGIF *parte* for the same
fire**.

The sixth of the burnt-area reports and the twin of
:doc:`darpa_wildfire_statistics`: same columns, same EGIF-match columns, same refusal
to test anything against a boundary. Its first six columns are the
:doc:`GWIS <gwis_wildfire_statistics>`, :doc:`GFA <gfa_wildfire_statistics>`,
:doc:`ICNF <icnf_wildfire_statistics>` and :doc:`EGIF <egif_wildfire_statistics>`
reports', in their order, so the CSVs can still be concatenated on them.

.. important::

   **This is the only dataset in GisFIRE with both a perimeter and a published burnt
   area**, and ``--surface`` chooses which the report is of. The two are different
   quantities and neither is a correction of the other — see :ref:`rediam-surface`.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics \
       --year 2022 --csv 2022.csv --docx 2022.docx

   python3 -m src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics \
       --min-area 5 --csv over-5-ha.csv

   # the hectares the service publishes, rather than the ones this measures
   python3 -m src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics \
       --surface published --csv published.csv

   # count only the fires bound to a parte on the published identifier
   python3 -m src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics \
       --min-confidence 0.9 --csv identifier-matches.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database — not the fires and not the
bindings it counts. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host``,
``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   **There is neither** ``--country`` **nor** ``--country-source``. The service
   publishes the fires of Andalusia and nothing else, so there is nothing to select
   between and nothing to test against a boundary. Both are refused with a message
   saying why.

Output
------

=========  ======  =====  ============  ============  ==========  ============  ================
Country    Year    Fires  Minimum (ha)  Maximum (ha)  Total (ha)  EGIF matched  EGIF matched (%)
=========  ======  =====  ============  ============  ==========  ============  ================
Spain      2025       97         10.24       1439.68    10015.74             0              0.00
Spain      2024       36         10.56       2169.34     8328.29             0              0.00
Spain      2023       40         10.45        425.49     2442.62            31             77.50
Spain      2022       58          3.05       5198.20    18689.75            58            100.00
Spain      2012       42          5.09       8593.70    12980.98            42            100.00
Spain      2008       36          0.41        488.98     2298.51            36            100.00
Spain      Total     907          0.02      15249.70   165522.45           759             83.68
=========  ======  =====  ============  ============  ==========  ============  ================

(a run over the whole published archive, measured geodesically, every binding counted;
seven of its nineteen rows.)

.. important::

   The ``Total`` row is **not** a total of every column above it. ``Fires``,
   ``Total (ha)`` and ``EGIF matched`` are sums; ``Minimum`` and ``Maximum`` are the
   smallest and largest fire of *any* year in scope; ``EGIF matched (%)`` is recomputed
   from the summed counts — the ratio of the totals, not the mean of the years' ratios.

The ``.csv`` writes bare numbers because it is read by another program more often than
by a person; the ``.docx`` writes them with thousands separators and right-aligned,
with the summary row in bold, because it is not.

.. _rediam-surface:

Measured or published
---------------------

``--surface`` chooses what the hectares are:

====================  ==============================================================
``--surface``         What it reports
====================  ==============================================================
``measured``          the area of the published perimeter, by ``--area-method``
``wooded``            ``SUP_ARBOLA`` as published
``scrub``             ``SUP_MATORR`` as published
``grassland``         ``SUP_PASTIZ`` as published
``published``         the three added, the nearest thing to a published total
====================  ==============================================================

``measured`` is the default because it is what makes a row here comparable with a row
of the five reports this one is read beside. Over the whole archive:

============================  ============
Surface                       Total (ha)
============================  ============
``measured`` (geodesic)         165,522.45
``published``                   152,696.29
``wooded``                       50,528.09
============================  ============

.. warning::

   **The two are different quantities and neither is a correction of the other.** The
   7.8% gap is what one expects of three vegetation classes measured against an outline
   that also encloses everything that is none of them — bare rock, farmland, a road.

   So a ``measured`` run and a ``published`` run answer different questions. Do not add
   them, and do not quote one as a correction of the other. The ``.docx`` says which it
   is of on its front page, and says this too, because the two tables look identical.

The three classes sum to ``published`` **in the** ``Total (ha)`` **column and nowhere
else**: a minimum of minima over three columns is not the minimum of their sum, because
the three ends need not belong to the same fire. Ask for ``published`` and let the
database add the rows up.

``--area-method`` applies to ``measured`` and to nothing else, and passing it with a
published surface is **refused rather than ignored**: nothing is measured there, so a
choice of how to measure would be a claim about a number that was read off a form.

How the measured area is measured
----------------------------------

The same two ways as the GFA, ICNF and Catalan reports: ``geodesic`` on the WGS84
ellipsoid (the default) or ``equal-area`` in EPSG:6933. They agree to within 0.003%.

The published EPSG:25830 grid is **not** offered, for the reason the Catalan report
declines EPSG:25831 and the ICNF one EPSG:3763: UTM is a transverse Mercator, conformal
rather than equal-area. Andalusia is wide for a single zone — the region runs from
1.6°W to 7.5°W against a central meridian at 3°W — so the distortion is not uniform
across it and does not cancel over a year whose fires are not evenly spread. Measured
on that grid the archive totals 165,582 ha against the geodesic 165,522, a difference
of 0.04%; to reproduce a figure on the service's own grid, measure there explicitly:

.. code-block:: sql

   SELECT year, sum(ST_Area(perimeter_etrs89_utm30n) / 10000.0) AS grid_ha
   FROM rediam_wildfire GROUP BY year ORDER BY year DESC;

How many matched the EGIF data
------------------------------

``EGIF matched`` counts the fires of the year carrying a link to an EGIF *parte*
(:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`), and
``EGIF matched (%)`` is that as a share of the ``Fires`` beside it. The links are
written by :doc:`rediam_bind_egif_wildfires`; this report only counts what it finds.

* **It is a column, not a filter.** An unbound fire is still a fire and still
  contributes its hectares to its row.
* **It follows the scope.** Whatever ``--year``, ``--surface`` and ``--min-area``
  select, the matched count is counted over exactly those fires, so the percentage
  always has the ``Fires`` column as its denominator — including when a fire is dropped
  for not reporting the surface, which takes its binding with it.
* **A zero is usually a fact about EGIF's coverage.** The exports stop at campaign
  2023, so 2024 and 2025 are at 0% — 133 perimeters with no *parte* to match at all —
  and that is the state of the exports, not a failure of the rules.

.. note::

   If nothing has ever been bound, every value in the column is zero, which looks
   exactly like a dataset that matched nothing. The log tells the two apart, and names
   the application to run.

Not every binding is the same claim
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``--min-confidence`` counts only the bindings at or above a given
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.match_confidence`.

Here it changes very little, and that is worth seeing: **749 of the 759 links rest on
the published identifier**, because ``CODIGO`` *is* the EGIF ``report_number``.
``--min-confidence 0.9`` removes ten fires, against Catalonia's 177.

.. warning::

   The confidences are **an ordering, not probabilities**. Nothing has been calibrated
   against ground truth, so ``--min-confidence 0.75`` selects a class of matching rule
   and does not mean "matches that are 75% likely to be right".

Which fires are counted
-----------------------

Under ``measured``, every imported Andalusian fire with a perimeter — which is every
one of them. Under a published surface, the fires that **report** it: a ``NULL`` there
is a form that does not say, not a fire that burnt none of it. A published **zero is
counted**, and is a real answer.

No fire in the 2008-2025 archive fails either test, which is exactly why the report
counts what it dropped rather than assuming it dropped nothing — a later publication
that leaves a column out would otherwise quietly shrink the ``Fires`` column with
nothing to say it had.

.. note::

   **A fire is one published ``(code, date)``, not one feature.** 962 published
   features are 907 fires — 55 codes are published twice — and the import dissolves
   them, so nothing here counts or sums a fire twice.

``--min-area HECTARES`` narrows it to the fires of at least that much **of the surface
being reported**, so the fires counted are always the fires the figures beside them were
computed from. It behaves as in :doc:`icnf_wildfire_statistics`: it selects fires rather
than rows, a year whose fires are all below it disappears rather than showing zeros, and
the ``Total`` row summarises only what was counted.

No country test
---------------

Every fire in this dataset is Andalusian and therefore Spanish. The ``Country`` column
is the constant ``Spain`` on every row and **nothing is tested against a boundary** —
the same decision, for the same reason, as :doc:`darpa_wildfire_statistics`: these
perimeters are the service's own cartography of its own territory.

.. warning::

   The column says ``Spain`` and the report is **Andalusia's fires alone**. A total here
   is not a Spanish total: it is one autonomous community of seventeen. The region is in
   the title of the ``.docx`` and on this page, not in a column, so that the CSV keeps
   the shape the other five reports have.

   To compare it with the national statistic, run
   :doc:`egif_wildfire_statistics` ``--region Andalusia``, which selects the *partes*
   filed in the same eight provinces.

One statement
-------------

The GWIS, GFA and ICNF reports issue one statement per year, because the memory a
point-in-polygon test against a country polygon needs is only released when the
statement ends. This report is one statement, like the EGIF and Catalan ones: it tests
nothing against a boundary and the whole archive is **907 fires**. A second, cheap
statement follows it to count the fires that do not report the chosen surface. The
``Total`` row is arithmetic over the years, by
:func:`~src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics.combine`.

Progress
--------

One spinner for the one statement, then what was computed and what matched:

.. code-block:: text

   \ Measuring the burnt area of the Andalusia fires and their EGIF matches... 0:00:03
   INFO Computed 19 rows over 18 year(s) (geodesic areas, every fire)
   INFO 759 of 907 fire(s) are bound to an EGIF parte (83.68%)

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.andalusia_rediam.wildfire_statistics
   :members:
   :show-inheritance:
