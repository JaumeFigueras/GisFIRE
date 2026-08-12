CONAFOR wildfire causes (Mexico)
=================================

Counts per year of how many Mexican fires there were, how many carry a cause at all, how
many were classified *Naturales* — and, for the years that publish a specific cause, how
many were started by **lightning**.

The companion of :doc:`conafor_wildfire_statistics`, over the same years, so the two can be
read side by side. What that one measures in hectares, this one counts by cause. See
:doc:`../providers/conafor_fire_cause` for the catalogue behind it.

Usage
-----

.. code-block:: console

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_causes \
       --year 2023 --csv 2023.csv --docx 2023.docx

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_causes \
       --cause Intencional --csv arson.csv

At least one of ``--csv`` and ``--docx`` is required.

This dataset publishes lightning
---------------------------------

This is what sets it apart from :doc:`icnf_wildfire_causes`. The ICNF names lightning
nowhere in its classification, so ``Natural`` is the finest answer that report can give and
it says so at length. **CONAFOR answers the question directly**: ``CAUSAESP`` has ``Rayos``,
and the earlier layers spell the same thing ``Descargas electricas``. Both translate to
``Lightning`` in
:data:`~src.providers.mexico_conafor.fire_cause.SPECIFIC_CAUSE_TRANSLATIONS`, and that is
what the ``Lightning`` column counts.

The count is taken on ``specific_cause_en`` rather than on a list of Spanish spellings,
deliberately: the two published wordings are a decade apart, both mean lightning, and a
third would be caught the moment it is added to that table rather than needing a second
edit here.

``Natural`` and ``Lightning`` are not the same number and neither contains the other
cleanly. A fire can be *Naturales* with no specific cause published — and the specific
causes include ``Erupciones volcanicas``, which is natural and is not lightning.

.. warning::

   **``CAUSAESP`` is published in 2010 and 2012-2019 and in no other year.** 2011, and
   every year from 2020, publish a cause and no specific cause — 27,624 fires, three in
   five.

   For those years the ``Lightning`` cell is left **empty, not zero**. A zero would say
   that lightning started no fires in Mexico in 2021, which is not what the absence of a
   column means. Never compare a ``Lightning`` count across that boundary, and never sum
   the column as though the blanks were zeros. The ``Total`` is a total of the years that
   answer the question, not of the period.

   The ``Natural`` column has no such gap: ``CAUSA`` is published by all fourteen layers.

Matching on the reconciled cause, not the published text
----------------------------------------------------------

``--cause`` and the cause column match on
:attr:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause.cause_normalised`, the
canonical Spanish, and **not** on the published string. That is the whole reason the column
exists.

CONAFOR publishes no cause code and the cause is free text, typed sixty-four ways over
fourteen years for about twenty real causes — what the later layers call ``'Naturales'`` is
``'Tormenta Electrica'``, ``'Tormenta Elcetrica'`` and ``'Descargas Electricas'`` in 2011. A
report matching on the published text would find none of those and would report that no
natural fire burnt that year.

The choices offered are therefore the canonical causes of
:data:`~src.providers.mexico_conafor.fire_cause.CAUSE_TRANSLATIONS`, and the column heading
uses the English from it.

.. warning::

   **Reconciling the spellings does not reconcile the categories.** CONAFOR renamed at
   least one outright, and a canonical cause can therefore be zero for a run of years for
   reasons that have nothing to do with fire:

   .. code-block:: text

      --cause Intencional              2013-2019   551 to 1,106 fires a year
                                       2020-2022   zero, in all three years
                                       2023        2,726

      --cause "Actividades ilícitas"   2020-2022   1,564 / 2,363 / 2,030
                                       every other year   zero

   *Intencional* and *Actividades ilícitas* are the same act filed under two
   administrative names three years apart. The three zeros in the middle of an
   ``Intencional`` series are the rename, not a collapse in arson.

   They are kept as two causes rather than merged, because *actividades ilícitas* is the
   broader phrase — it can cover fires set to clear illicit crops, which the archive also
   files separately as ``Cultivos ilícitos``. Merging two published categories on a guess
   would be a worse error than reporting them apart. Run the report twice and add the
   columns if a continuous series is what is wanted.

   The same caution applies less dramatically to ``Actividades agropecuarias``, which
   splits into ``Actividades agrícolas`` and ``Actividades pecuarias`` from 2018.

.. note::

   A fire whose published cause reached no canonical form has ``cause_normalised`` ``NULL``:
   it is **classified** and can never **match**, whatever ``--cause`` asks for. Three fires
   of the published archive are in that state, all in 2011, all of them a bare ``'12'``
   typed into the cause field.

   The run says so at ``WARNING`` rather than letting it be a silent discrepancy between
   two columns.

Why ``Classified`` is a column and the percentage is of it
-----------------------------------------------------------

160 fires of the archive carry no cause at all — 2010 writes ``'0'`` into ``CAUSA`` seven
times and 2011 writes ``'No'`` 153 times, both null tokens rather than causes.

That is a far smaller hole than the ICNF's, where two fires in three are unclassified, but
the denominator is the classified fires all the same and for the same reason: a percentage
of *all* fires would be partly a statement about how complete the classification is. Where
nothing is classified the cell is left empty rather than filled with a zero that would be a
claim.

.. warning::

   Take the classified share as a floor. ``Desconocidas`` is the second largest cause in
   the archive — 6,247 fires, one in seven — and a fire whose cause was never determined
   may well have been natural.

Which fires are counted
-----------------------

**Every fire**: no country test, and no requirement to have a perimeter.

This differs by a handful from the companion report, which counts every fire the chosen
``--area-method`` can measure — nine fewer under a measured method, and one fewer under
``reported``. The difference is stated rather than engineered away: a fire with no polygon
still has a cause, and a causes report that dropped it would be answering a question about
polygons.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.mexico_conafor.wildfire_causes
   :members:
   :show-inheritance:
