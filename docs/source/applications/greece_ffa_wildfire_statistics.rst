Greek Fire Service wildfire statistics
======================================

Reports the Greek Fire Service records per year: how many fires there were, the smallest
single fire, the largest single fire and the total burnt area in hectares — and, this
dataset's own pair, how many of the year's fires publish a coordinate.

The seventh of the burnt-area reports, alongside :doc:`gwis_wildfire_statistics`,
:doc:`gfa_wildfire_statistics`, :doc:`icnf_wildfire_statistics`,
:doc:`egif_wildfire_statistics`, :doc:`darpa_wildfire_statistics` and
:doc:`rediam_wildfire_statistics`. Its first six columns are theirs, in their order, so
the CSVs can still be concatenated on them; the two after them are this dataset's own.

In kind it is the twin of the :doc:`EGIF report <egif_wildfire_statistics>` rather than of
the perimeter ones: these hectares are **reported, not measured**, because the Fire
Service publishes no polygon in any year.

Usage
-----

Over everything, or narrowed to one year, one land cover, or the fires above a size:

.. code-block:: console

   python3 -m src.apps.statistics.wildfires.greece_ffa.wildfire_statistics \
       --csv burnt.csv --docx burnt.docx

   python3 -m src.apps.statistics.wildfires.greece_ffa.wildfire_statistics \
       --year 2023 --csv 2023.csv

   python3 -m src.apps.statistics.wildfires.greece_ffa.wildfire_statistics \
       --surface forest --csv forest.csv

   python3 -m src.apps.statistics.wildfires.greece_ffa.wildfire_statistics \
       --min-area 100 --csv large.csv

   python3 -m src.apps.statistics.wildfires.greece_ffa.wildfire_statistics \
       --include-false-alarms --year 2025 --csv 2025.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

Output
------

.. code-block:: text

   Country  Year   Fires   Minimum (ha)  Maximum (ha)  Total (ha)  Located  Located (%)
   =======  =====  ======  ============  ============  ==========  =======  ===========
   Greece   2025     7788          0.00       6900.00    48189.30     7788       100.00
   Greece   2024     9777          0.00      10413.80    48307.43     8942        91.46
   Greece   2023     8257          0.00      81834.80   176966.17     7579        91.79
   Greece   2021     9514          0.00      51185.41   133214.07     8508        89.43
   Greece   2019     9500          0.00       2145.10    16275.85        0         0.00
   Greece   2007    11996          0.00      40000.00   264422.22        0         0.00
   Greece   Total  258939          0.00      81834.80  1323259.34    53236        20.56
   =======  =====  ======  ============  ============  ==========  =======  ===========

Years newest first with the summary row last. The ``.csv`` writes bare numbers because it
is read by another program more often than by a person; the ``.docx`` writes them with
thousands separators and right-aligned, with the summary row in bold.

A minimum of ``0.00`` is normal here and is not a missing value: a fire that burnt less
than half a στρέμμα rounds to nothing in every land-cover column, and thousands do.

.. note::

   The figures line up with what is publicly known of these fire seasons, which is worth
   recording because nothing in the pipeline checks them: 2007's 264,422 ha is the
   Peloponnese catastrophe, 2023's single 81,835 ha fire is Alexandroupolis-Dadia — the
   largest wildfire recorded in the EU — and 2021's 51,185 ha one is Evia.

Which burnt area
----------------

The service publishes **eight**, one per land cover, and ``--surface`` picks which the
report is of. There is no published total.

======================  ==================================================
``--surface``           What it sums
======================  ==================================================
``burnt`` *(default)*   all eight land covers — the nearest thing to a total
``forest-total``        ``Δάση`` + ``Δασική Έκταση`` + ``Άλση``
``forest``              ``Δάση``
``forest-land``         ``Δασική Έκταση``
``grove``               ``Άλση``
``grassland``           ``Χορτ/κές Εκτάσεις``
``reeds-marsh``         ``Καλάμια - Βάλτοι``
``agricultural``        ``Γεωργικές Εκτάσεις``
``crop-residue``        ``Υπολλείματα Καλλιεργειών``
``landfill``            ``Σκουπιδότοποι``
======================  ==================================================

.. warning::

   ``forest-total`` is **this report's grouping and not the service's**. There is no
   published Greek figure it corresponds to; it exists because it is the nearest analogue
   to EGIF's ``SuperficieTotalForestal``, which is what a comparison between the two
   countries needs. Treat it as this report's arithmetic.

   ``burnt`` is likewise a sum this report performs, not a figure the service prints —
   but it is the whole of what the service publishes, so nothing is being chosen for you.

The hectares are hectares because the import converted them: the service publishes
στρέμματα, a tenth of a hectare each. See :doc:`greece_ffa_import_wildfires`.

Which fires are counted
^^^^^^^^^^^^^^^^^^^^^^^

Those whose chosen surface **is reported**. Every area column is nullable, ``sum`` and
``min`` skip nulls and ``count`` does not, so a report that did not filter would count
fires whose hectares it had not included — the same rule as
:doc:`egif_wildfire_statistics`.

In practice it bites exactly once over the whole archive: all eight columns are published
in all twenty-six years, and a single cell of the 260,194 rows is empty. That is why
``--surface forest`` reports 258,938 fires where ``--surface burnt`` reports 258,939.

How many were located
---------------------

The two extra columns, and the reason they are columns rather than a footnote: **no year
before 2020 publishes a coordinate at all**. 54,491 of the 260,194 fires have a point; the
rest are locatable only by the prefecture, municipality, forest district and locality
named on them.

So ``Located`` is zero for twenty years and then jumps to about 91%, and **any spatial
analysis of this dataset is an analysis of its last six years**. A reader who cannot see
that in the table will assume otherwise.

It is a column and not a filter: an unlocated fire still contributes its hectares. And a
report whose ``Located`` column is zero throughout is the expected answer for any scope
ending before 2020, not a failed import — the run says so at ``WARNING`` rather than
leaving it to be guessed.

False alarms are excluded by default
------------------------------------

The 2025 file publishes ``Κατηγορία Συμβάντος``, and **1,255 of its 9,043 rows are**
``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ`` — a call-out that found no fire. They are records of a dispatch, so
the report leaves them out and logs how many it left out. ``--include-false-alarms``
counts them, which moves 2025 from 7,788 fires to 9,043.

.. warning::

   The exclusion is written ``IS DISTINCT FROM`` and not ``<>``, and the difference is
   twenty-five years. ``incident_category`` is ``NULL`` for every year before 2025, where
   ``<>`` evaluates to ``NULL`` rather than to true — so a report built on the obvious
   filter would still build, still total, and simply be of the wrong archive. A test
   asserts the SQL, not just the result.

No country, and no cause
------------------------

No ``--country`` and no ``--country-source``, as for the :doc:`Catalan
<darpa_wildfire_statistics>` and :doc:`Andalusian <rediam_wildfire_statistics>` reports:
the Fire Service publishes Greece's fires and nothing else, so the ``Country`` column is
the constant ``Greece`` and nothing is tested against a boundary. Three quarters of the
archive publishes no coordinate to test in any case.

No ``--area-method`` either, for the EGIF reason: there is no perimeter to measure.

All three options are *accepted* by the parser and then refused with an explanation,
because anyone reaching for one has copied a command line from another report — a
reasonable thing to have done — and argparse's own message would not say why this report
is different.

.. warning::

   **There is no counts-by-cause companion to this report**, unlike
   :doc:`icnf_wildfire_causes` and :doc:`egif_wildfire_causes`.

   Nothing in any of the twenty-six published sheets says why a fire started. There is no
   equivalent of EGIF's ``idcausa``, no lightning category, and no cause column of any
   kind — so there is no catalogue to seed, and **no lightning question that can be put to
   this dataset** by counting. See :doc:`../providers`.

   What the dataset does carry is 54,491 ignition points with instants, for 2020 onwards.
   That is the only handle a lightning attribution could ever use here, and it would be a
   spatio-temporal join against a Greek lightning dataset — which GisFIRE does not import
   yet — rather than a report over a published cause.

One statement
-------------

Like the EGIF, Catalan and Andalusian reports and unlike the GWIS and GFA ones, this is a
single aggregate: 260,194 rows with no geometry work in them at all, four orders of
magnitude short of the twenty-million-perimeter case that made the others read a year at a
time. The whole archive reports in about a tenth of a second.

Progress
--------

One spinner for the one statement, then what was computed:

.. code-block:: text

   INFO Computed 27 rows over 26 year(s) (burnt hectares as published, every fire)
   INFO Excluded 1255 false alarm(s) (ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ); pass --include-false-alarms to count them
   INFO 53236 of 258939 fire(s) publish a coordinate (20.56%)

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.greece_ffa.wildfire_statistics
   :members:
   :show-inheritance:
