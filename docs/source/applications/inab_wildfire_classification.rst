INAB wildfire classification (Guatemala)
=========================================

Counts the Guatemalan fire reports by the vocabularies INAB publishes: what the fire was,
what became of the report, who called it in and how.

The companion of :doc:`inab_wildfire_statistics`, over the same fires, the same years and
the same scope — so the ``Country``, ``Year`` and ``Fires`` columns of the two agree row
for row. What that one counts, this one breaks down.

.. important::

   **This is not a causes report, and it must not be read as one.**

   Portugal, Spain, Canada and Mexico have a counts-by-cause report because those sources
   publish a cause: EGIF has ``idcausa``, the NFDB has ``CAUSE``, CONAFOR publishes
   ``Rayos`` outright. **Nothing in INAB's thirty-three published attributes says why a
   fire started** — no cause column, no lightning category, no arson category — and no
   amount of aggregation over what *is* published will produce one.

   What this report counts is the four closed vocabularies the source does publish. One of
   them classifies the fire; the other three classify the report. None is a cause, which
   is why the application is named ``wildfire_classification`` and not
   ``wildfire_causes``, why no column of it is ever headed *Cause*, and why ``--cause`` is
   accepted only in order to be refused with that explanation.

Usage
-----

.. code-block:: console

   # what each classification counts, and which have a published vocabulary
   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_classification \
       --list-classifications

   # the default: tipo_incendio, inside or outside forest
   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_classification \
       --csv location.csv --docx location.docx

   # what became of the reports, false alarms included so their column fills
   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_classification \
       --classification status --include-false-alarms --csv status.csv

   # who reported the fires of one year
   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_classification \
       --classification institution --year 2025 --csv institutions-2025.csv

At least one of ``--csv`` and ``--docx`` is required.

The four classifications
-------------------------

``location`` — ``tipo_incendio``, the default
    Whether the fire was inside or outside forest. **The only classification of the fire
    itself that this dataset carries**, and the nearest thing in it to the kind of column
    a causes report would count.

    It is filled on **489 of the 4,615 records, 10.6%** — the single most important thing
    to know about this report. A table of it describes one record in ten, which is why
    ``Classified (%)`` is the fifth column and not a footnote.

``status`` — ``estado_aviso``
    What became of the report: closed, false, unverified, confirmed, still burning. Filled
    on effectively everything, and the one classification here with real coverage. It is
    also where the 140 false alarms and the 90 unverified reports become visible side by
    side, which :doc:`inab_wildfire_statistics` shows only for the first of the two.

    Note that the default scope **excludes** the false alarms, which empties their own
    column. ``--include-false-alarms`` is how this breakdown is meant to be read.

``institution`` — ``institucion``
    Which organisation called the fire in. Fourteen values, led by ``conred`` and
    ``conap``.

``channel`` — ``forma_comunicacion``
    How the report reached INAB: by telephone, in person, through the app, through social
    media, by radio. A measure of how a country hears about its fires, and the only such
    measure in the project.

Why the denominator is the classified fires
---------------------------------------------

``Classified`` counts the fires that carry any value at all, and every percentage after it
is a share of **that**, not of ``Fires``. This is the choice the Canadian causes reports
make about their ``Undetermined`` category, and it matters far more here: ``U`` is under
2% of the NFDB, while ``tipo_incendio`` is absent from **89%** of this archive.

So ``In forest (%)`` says *of the fires somebody classified, this share were in forest*.
Reading it as a share of all Guatemalan fires would be wrong by a factor of nine. Where
nothing in a year is classified there is no percentage to give and the cell is left
**empty** rather than filled with a zero that would be a claim.

.. warning::

   **The coverage is not evenly spread, and the report cannot correct for that.**
   ``tipo_incendio`` is filled by whoever handled the report, so the classified tenth is a
   sample of INAB's reporting practice rather than a random sample of Guatemalan fire.
   ``--year`` and the ``Classified (%)`` column are what make that visible; there is no
   weighting that would make the other nine tenths speak.

   The run warns when a breakdown covers less than half the fires in scope.

Where the columns come from, and why one of them is different
---------------------------------------------------------------

Three of the four vocabularies are **published constants** —
:data:`~src.providers.guatemala_inab.FIRE_LOCATIONS`,
:data:`~src.providers.guatemala_inab.REPORT_STATUSES` and
:data:`~src.providers.guatemala_inab.REPORT_CHANNELS` — and their columns come from those
tuples, in the order the provider module lists them. So the report has the same columns
whatever happens to be in the database, two runs over different scopes can be compared,
and a value nobody in scope carries shows as a zero rather than as a missing column.

``institution`` has no such constant, because the provider module has none to give: the
fourteen values were observed once and never published as a list. Its columns are
therefore **built from the data in scope**, most frequent first with the value itself as
the tie-break. That is a real difference and the Word document states it — two runs of
``--classification institution`` over different years can have different columns, and
their CSVs cannot be concatenated on anything but the first five.

A value found in the data that is **not** in the published tuple is reported at ``WARNING``
and then counted anyway, in a column of its own after the published ones. The provider
module gives these vocabularies no ``CHECK`` constraint precisely because they are one
publication observed once, so the first value INAB adds must not vanish from a report —
this is where it first becomes visible.

An example
----------

.. code-block:: text

   Country    Year   Fires  Classified  Classified (%)  In forest  In forest (%)  Outside forest  Outside forest (%)
   Guatemala  2025    1735         188           10.83        147          78.19              41               21.81
   Guatemala  2024     704          78           11.08         61          78.21              17               21.79
   Guatemala  Total   4471         489           10.94        383          78.32             106               21.68

Read the fifth column before anything after it.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.guatemala_inab.wildfire_classification
   :members:
   :show-inheritance:
