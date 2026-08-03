DARPA ↔ EGIF wildfire binding
==============================

Links each Catalan perimeter to the Spanish *parte* for the same fire, filling in
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id` and
the three columns that account for it.

The two datasets are complements, which is the whole reason for this application.
EGIF publishes the cause, the motivation, the burnt area split five ways and an
ignition point — and **no perimeter, ever**. DARPA publishes the shape and four
attributes, and **no burnt area at all**. A Catalan fire is one event with its
evidence split between two agencies, and this is what puts it back together.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires

   # one year, and a report of what happened to every fire in it
   python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires \
       --year 1994 --csv 1994-bindings.csv

   # work it all out and write nothing
   python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires --dry-run

Import both datasets first — :doc:`darpa_import_wildfires` and
:doc:`egif_import_wildfires`. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host`` and the
rest. No ``ogr2ogr``, no files, no network: this application only reads and writes
the database.

.. note::

   It writes **four columns on one table** and nothing else. No row is created, no
   perimeter is touched, no EGIF column is written. That is what makes it safe to
   re-run at any time, and it is asserted by a test.

The cascade
-----------

Each stage narrows a set of candidate *partes*, and a link is written **only when
exactly one candidate is left**. Every stage is a filter, never a ranking — nothing
here picks a best guess.

**Stage 1 — the code.** If a Catalan ``CODI_FINAL`` equals an EGIF
``report_number``, that is the fire. From 1997 the Catalan code *is* the report
number: ten characters, year plus INE province plus sequence. ``report_number`` is
unique nationally, so there is nothing to disambiguate.

**Stage 1b — the code rearranged.** The older formats are the same identifier in a
different layout, and decoding them is worth 122 more fires:

===============  ==================  ==============  ==============
Years            Form                Example         Decodes to
===============  ==================  ==============  ==============
1986             ``PPYYNNNNN``       ``178600064``   ``1986170064``
1992, 1993       ``YYPPNNNNN``       ``920800034``   ``1992080034``
1994-1996        ``PYYNNN``          ``894496``      ``1994080496``
1994-1996        ``PPYYNNN``         ``4394032``     ``1994430032``
===============  ==================  ==============  ==============

The nine-digit form is genuinely ambiguous — province-first in 1986, year-first in
1992 — so the reading is chosen by which one puts the fire in the year of its own
layer. A decode is a reading of a format rather than string equality, so it **has to
be confirmed by the date**; one the date contradicts falls through to stage 2.

The 1987-1991 letter forms (``G0870016``, ``L89004001``) are **not** decoded. They
carry six digits where a report number has four, and no reading matches EGIF at a
rate distinguishable from chance.

**Stage 2 — the date, narrowed.** For everything else, the candidates are the
Catalan *partes* whose local start date is the perimeter's published date. That set
is narrowed, in order, by whatever is available: the **province** the code carries
(five of the six historical code formats carry one), then the **municipality
name**, then the **geometry** — keeping only candidates whose ignition point falls
inside the perimeter.

**Stage 3 — nothing.** A fire with no candidate, or with several after all of that,
is left unbound and reported.

What actually happens, on the published data
---------------------------------------------

860 Catalan perimeters against 25,376 Catalan *partes* of campaigns 1982-2022:

======================  ======  ================================================
``match_method``        Fires   Notes
======================  ======  ================================================
``code``                   470  1998-2022
``code_reformatted``       122  1986-1994; **all 122 agree on the date**
``code_date_mismatch``       9  2005-2021
``date_province_name``     123  1987-2021
``date_province``           44  1987-2021
``date``                     8  1989-2020
``date_name``                2  1999-2021
*(unbound)*                 82  **45 of them are 2023-2024**
======================  ======  ================================================

**778 of the 860 perimeters are bound — 90.5%** — and **601 of those rest on an
identifier rather than a name**, which is 77% of the bindings.

Of the 82 unbound, 45 are DARPA 2023 and 2024, which the EGIF exports do not reach.
The real residue is **37 fires in forty years** that both agencies recorded and the
cascade could not pair: 47 have no EGIF fire on their date at all, 35 have several it
could not separate.

Stage 1 misses 73 of the 553 fires from 1997 on — but **45 of those are DARPA 2023
and 2024, which the EGIF exports do not reach at all**. On comparable years it
matches 480 of 508.

.. warning::

   **Stage 2's geometry test is almost never available.** EGIF publishes no
   coordinate whatsoever before 1998 — 0 of the 10,010 Catalan fires of 1982-1997 —
   and nearly every fire that reaches stage 2 is pre-1998.

   So the municipality name does nearly all of the work in the era that needs the
   most help. Date alone is no use there either: it leaves a median of 8 candidates
   and as many as 29.

Why the method is recorded
---------------------------

Because the two kinds of binding are not the same claim.

``match_method`` names the rule that fired, ``match_confidence`` orders them, and
``matched_at`` says when — ``updated_at`` cannot, because it moves for any edit,
and what matters is whether a binding predates the last EGIF import.

===========================  ============  ==================================================
``match_method``             Confidence    What it means
===========================  ============  ==================================================
``code``                     1.00          The published identifier, dates agreeing
``code_reformatted``         0.95          The identifier rearranged, dates agreeing
``code_date_mismatch``       0.90          The identifier, dates disagreeing
``geometry``                 0.85          The ignition point is inside the perimeter
``date_province_name``       0.75          One *parte* that day, province and municipality
``date_name``                0.65          One that day in that municipality
``date_province``            0.60          One that day in that province
``date``                     0.50          The only *parte* in Catalonia that day
===========================  ============  ==================================================

The confidence is **an ordering, not a probability**. Nothing here is calibrated
against ground truth — there is no answer key for a 1989 fire — so it says "trust
this more than that" and nothing arithmetical. The gap that matters is the one
between the top two and the rest, and the query worth remembering is:

.. code-block:: sql

   SELECT * FROM v_darpa_wildfire_4326 WHERE match_confidence >= 0.9;

Both Catalan views expose all three columns, so a QGIS layer can be styled by
confidence and the boundary between the identifier matches and the name matches is
visible on the map.

Municipality names are not the same string
-------------------------------------------

Comparing the published names directly would fail on a quarter of the dataset. The
normalisation folds case and accents, treats the interpunct of a Catalan geminate
``l·l`` as joining rather than separating, and — the rule that pays — **un-inverts
the article**: EGIF writes ``VALL DE BOI, LA`` where DARPA writes ``La Vall de
Boí``.

On the fires stage 1 has already matched, that takes agreement from **76.7% to
94.4%**, which is what makes the tiebreak measurable at all.

The residual 5.6% are left alone on purpose. They are municipal mergers
(``Montagut`` against ``MONTAGUT I OIX``), spelling drift (``Reixach`` / ``Reixac``,
``Gramenet`` / ``Gramanet``), DARPA naming two municipalities at once (``Albiol i
Alcover``), and genuine disagreements about which municipality a boundary-crossing
fire belongs to. A fuzzy threshold would recover perhaps twenty of them and
introduce a number nobody can validate; a missed binding is the better failure.

.. note::

   **Les**, in the Val d'Aran, is a municipality whose entire name is the definite
   article. The article rule only strips a word that has something to be the
   article *of*, or that fire would normalise to the empty string and be lost by a
   rule meant to save it.

The refusals
------------

Everything this application declines to do is deliberate, and it is the half that
makes the rest usable. A wrong binding silently attaches another fire's cause and
burnt area to a perimeter and nothing downstream could ever detect it; a missing
binding is visible in the first report anyone runs.

**Several candidates → unbound.** No scoring, no best guess.

**One *parte* claimed by two perimeters → neither is bound**, and the *parte* is
named in the log. Stage 1 cannot produce a contest — ``report_number`` is unique —
so a contested *parte* is always two fuzzy matches, which means neither is
trustworthy.

This is enforced in the application rather than by a unique constraint, so that a
genuine many-to-one — a regional dataset that splits what EGIF files as one fire —
is a data question to look at rather than a crash halfway through a run.

**A province that excludes every candidate is not applied.** A code and a *parte*
disagreeing about the province is a disagreement, not a filter; applying it would
empty the candidate set and lose a fire the municipality name would have matched.

Re-running
----------

The four columns belong to this application and to nothing else, so a run
**recomputes them from scratch** for every fire in scope: it clears them, works the
bindings out again, and writes what it finds, in one transaction. That is what makes
a re-run after a new EGIF import actually correct an old binding, which is the point
of running it again.

``--only-unbound`` restricts it to fires with no link yet, for the case where
something outside this application has bound a fire by hand. With that flag, having
nothing left to do is a success rather than an error.

The report
----------

``--csv`` writes one row per fire in scope, **bound and unbound alike**, with the
method, the confidence, the *parte*, and how many candidates were in play. A report
of the successes says nothing about whether the rules are right; the unbound rows
and their candidate counts are what show where the cascade runs out of evidence and
what a further rule would have to work with.

.. code-block:: text

   code,fire_date,year,municipality_name,source_layer,outcome,method,confidence,...
   894496,1994-08-11,1994,Sant Cugat del Vallès,incendis1994,unbound,,,,,8
   2013080287,2013-07-24,2013,Sant Mateu de Bages,incendis2013,bound,code,1.00,...

API reference
-------------

.. automodule:: src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires
   :members:
   :show-inheritance:
