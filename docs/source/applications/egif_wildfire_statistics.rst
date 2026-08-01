EGIF wildfire statistics (Spain)
=================================

Reports the Spanish EGIF fire statistics per campaign: how many fires there were, and the
smallest single fire, the largest single fire and the total burnt area, in hectares.

The fourth of the burnt-area reports, alongside :doc:`gwis_wildfire_statistics`,
:doc:`gfa_wildfire_statistics` and :doc:`icnf_wildfire_statistics`, and deliberately the
same shape: same columns, same grouping, same two output formats, so the four CSVs can be
concatenated and compared.

It is also the odd one out, in one way that matters more than everything else on this
page.

.. important::

   **These hectares are reported, not measured.** The other three reports measure a
   polygon. EGIF publishes no polygon in any of its exports and never will — see
   :doc:`../providers/egif_wildfire` — so what this report sums is the burnt area written
   on the fire report form.

   There is therefore no ``--area-method``: nothing is projected, nothing is measured on
   an ellipsoid, and no choice of CRS will make these figures agree with a perimeter
   dataset. Where they differ from a measured area, that difference is a fact about the
   two archives, not an error in either.

Usage
-----

Over everything, or narrowed to one campaign, one surface, or the fires above a size:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics \
       --year 2023 --csv 2023.csv --docx 2023.docx

   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics \
       --surface burnt --min-area 5 --csv over-5-ha.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   **There is no** ``--country``. EGIF is the Spanish national statistic, so every fire in
   it is filed in Spain and there is nothing to select between. The column stays, holding
   the constant ``Spain``, so this report's CSV has the same shape as the other three.

   Unlike the ICNF report there is not even a ``--country-source``: with no perimeter
   there is nothing to test against a boundary, and EGIF's own answer to where a fire is —
   *comunidad*, province, municipality — is administrative and never in doubt about the
   country.

Output
------

=============  ======  =======  ============  ============  ============
Country        Year      Fires  Minimum (ha)  Maximum (ha)  Total (ha)
=============  ======  =======  ============  ============  ============
Spain          2023       6294          0.00       9520.00      75236.41
Spain          2022       7362          0.00      31500.00     243610.28
Spain          Total     13656          0.00      31500.00     318846.69
=============  ======  =======  ============  ============  ============

.. important::

   The ``Total`` row is **not** a total of every column above it. ``Fires`` and
   ``Total (ha)`` are sums; ``Minimum`` and ``Maximum`` are the smallest and largest fire
   of *any* campaign in scope.

The ``.csv`` writes bare numbers because it is read by another program more often than by
a person; the ``.docx`` writes them with thousands separators and right-aligned, with the
summary row in bold, because it is not.

A minimum of ``0.00`` is normal here and is not a missing value — see
:ref:`egif-reported-zero`.

Which surface
-------------

EGIF does not publish *one* burnt area. It publishes five, and ``--surface`` picks which
one the report is of.

====================  ================================  =========================
``--surface``         EGIF column                       Part of the forest total?
====================  ================================  =========================
``forest`` (default)  ``SuperficieTotalForestal``       is the forest total
``wooded``            ``SuperficieArbolada``            yes
``non-wooded``        ``SuperficieNoArbolada``          yes
``agricultural``      ``SuperficieAgricola``            **no**
``other-non-forest``  ``OtrasSuperficiesNoforestales``  **no**
``burnt``             all three of the above added      n/a, not published
====================  ================================  =========================

``forest`` is the default because summing it over fires reproduces the published national
figure — it is what a Spanish fire year is quoted in. ``wooded`` and ``non-wooded`` are
the two parts it is exactly the sum of, checked on every row of the 2022-2023 sample.

``agricultural`` and ``other-non-forest`` are **outside** the forest total: EGIF counts
forest and non-forest separately, so adding either to the national figure double-counts
nothing but also answers a different question. ``burnt`` adds all three, which EGIF does
not publish and which should not be quoted as *the* burnt area of a Spanish fire year.

.. warning::

   **Do not add two runs of this report together.** ``wooded`` and ``non-wooded`` sum to
   ``forest`` in the ``Total (ha)`` column and nowhere else: a minimum of minima over two
   different columns is not the minimum of their sum, because the two ends need not belong
   to the same fire. Ask for ``burnt`` and let the database add the rows up.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.spain_egif.wildfire.EgifWildfire.campaign` — the campaign the
*parte* is filed under, which is also the first four characters of its report number —
and **not** the year of the detection date, exactly as the ICNF report uses the published
``Ano``.

The two are normally the same and can disagree at a New Year's Eve fire. Where they do,
the report follows the filing, because a published yearly total is a total of what the
service filed that year. ``campaign`` is ``NOT NULL`` and indexed, and needs no timezone
applied to it — which the detection date would, EGIF's instants being local wall-clock
readings in two different zones (the Canaries are an hour behind).

Which fires are counted
-----------------------

Those whose chosen surface **is reported**. A fire whose ``SuperficieTotalForestal`` is
``NULL`` is not a fire that burnt no forest; it is a fire whose form does not say, and it
is left out of the count as well as out of the areas — so the ``Fires`` column always
counts exactly the fires the three figures beside it were computed from.

This is per surface, not per fire: a fire that reports an agricultural area and no forest
one is counted in an ``--surface agricultural`` run and absent from a ``forest`` one.

.. _egif-reported-zero:

A reported zero is an answer
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A fire that burnt only farmland has a forest total of ``0.00`` ha, and that is a
measurement, not a silence. It is counted, and it is why a minimum of ``0.00`` is normal
in this report. Under ``--surface burnt`` the same fire shows its farmland hectares
instead.

Under ``burnt``, a fire counts if *any* of the three components is reported; the ones that
are not contribute nothing.

Counting only the larger fires
------------------------------

``--min-area HECTARES`` counts only the fires that burnt at least that much of the chosen
surface. There is no threshold by default. It behaves exactly as in
:doc:`icnf_wildfire_statistics`: it selects fires rather than rows of the report, a
campaign whose fires are all below the threshold disappears rather than showing zeros, and
the ``Total`` row summarises only what was counted.

Note that any positive threshold drops every reported zero, which for ``--surface forest``
means every fire that burnt no forest at all.

.. warning::

   **A campaign's total is a floor, not the year's burnt area.**

   Every fire the service exports is in state *Cerrado Revisión*, and a region's fires
   appear only once that region has closed them, so a freshly exported year is missing
   whole regions. The 2022+2023 export checked in :doc:`../providers/egif_provider` is
   missing Cantabria and Navarra for 2022 and Cataluña, Extremadura and Canarias for 2023;
   its 2022 forest total of 243,610 ha is well below the ~306,000 ha eventually published.

   A year has to be re-exported and re-imported later. Comparing two campaigns of
   different vintages compares two degrees of completeness, not two fire seasons. The
   ``.docx`` says so on its front page for the same reason.

One statement, not one per year
-------------------------------

The other three reports issue one statement **per year**, because the memory a
point-in-polygon test against a country polygon needs is only released when the statement
ends, and a single pass over twenty million perimeters took a 30 GB machine to the OOM
killer.

This report does **no geometry at all** — it is an indexed aggregate over one column of
one table, and it does not even join the parent ``wildfire`` row, everything it reads
being on ``egif_wildfire``. So there is nothing to spread over several statements and it
runs as one ``GROUP BY campaign``, under one spinner. The ``Total`` row is still arithmetic
over the campaigns, by
:func:`~src.apps.statistics.wildfires.spain_egif.wildfire_statistics.combine`, so the
output is the same shape as the other three.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.spain_egif.wildfire_statistics
   :members:
   :show-inheritance:
