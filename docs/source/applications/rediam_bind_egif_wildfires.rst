REDIAM ↔ EGIF wildfire binding
===============================

Links each Andalusian perimeter to the Spanish *parte* for the same fire, filling in
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id` and
the three columns that account for it.

The twin of :doc:`darpa_bind_egif_wildfires` over the other regional dataset: same
cascade shape, same confidences for the rules they share, same CSV, same refusal to
guess. Read that page for the argument; this one is about what is **different** here,
which is mostly that this dataset is easier.

.. important::

   ``CODIGO`` **is** the EGIF ``report_number`` — on all 962 published features, from
   the first year. The Catalan code only becomes one in 1997 and takes six forms before
   that, so where that application needs a cascade this one mostly needs a lookup.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires

   # one year, and a report of what happened to every fire in it
   python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires \
       --year 2022 --csv 2022-bindings.csv

   # work it all out and write nothing
   python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires --dry-run

Import both datasets first — :doc:`rediam_import_wildfires` and
:doc:`egif_import_wildfires`. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host`` and the
rest. No ``ogr2ogr``, no files, no network: this application only reads and writes the
database.

.. note::

   It writes **four columns on one table** and nothing else. No row is created, no
   perimeter is touched, no EGIF column is written. That is what makes it safe to
   re-run at any time, and it is asserted by a test.

The cascade
-----------

Each stage narrows a set of candidate *partes*, and a link is written **only when
exactly one candidate is left**. Every stage is a filter, never a ranking.

**Stage 1 — the code.** ``CODIGO`` equals an EGIF ``report_number``: year, INE
province, four-digit sequence. ``report_number`` is unique nationally and the 907 fires
decode to 907 distinct ones, so there is nothing to disambiguate. The two published
dates are then compared, which makes the stage self-checking rather than merely
assumed.

**Stage 1b — the code read rather than compared.** Two published shapes are the same
identifier written differently:

=================  ==================  ==============
Shape              Example             Report number
=================  ==================  ==============
``IIFF`` prefix    ``IIFF2025040059``  ``2025040059``
nine digits        ``201918023``       ``2019180023``
=================  ==================  ==============

A decode is a reading of a format rather than string equality, so it is recorded as
``code_reformatted`` when the dates agree and as ``code_date_mismatch`` when they do
not — but it still binds, because an identifier read correctly is still an identifier.
Refusing there would make a missing zero the difference between a link and none.

**Stage 2 — date, province, name, and then the map.** Only for the fires whose report
number EGIF does not have at all. The province comes from the code and is always
present, so the candidate set starts as *the partes of that province on that date*,
narrows by the municipality name, and finally by testing which EGIF ignition points
fall inside the perimeter.

**Stage 3 — nothing.** A fire with no candidate, or with several after all of that, is
left unbound and reported.

What actually happens, on the published data
--------------------------------------------

907 Andalusian perimeters against 40,757 Andalusian *partes* of campaigns 1982-2023:

======================  ======  ================================================
``match_method``        Fires   Notes
======================  ======  ================================================
``code``                   702  string equality with the ``report_number``
``code_reformatted``         5  five of the six nine-digit 2019 codes
``code_date_mismatch``      42  the dates differ by 1 day to 5 weeks
``date_province_name``       2  where EGIF has no such report number
``date_province``            8  same, and the only *parte* of that day and province
``geometry``                 0  see below
*(unbound)*                148  **133 of them are 2024 and 2025**
======================  ======  ================================================

**759 of the 907 perimeters are bound — 83.7%** — and **749 of those rest on the
published identifier**, which is 98.7% of the bindings.

Beside Catalonia's 90.5% bound and 77% on an identifier: fewer bound here, and far more
of them certain. Both numbers have the same cause — the EGIF exports stop at campaign
2023, and this dataset runs to 2025.

.. code-block:: text

   INFO Bound 759 of 907 Andalusian fire(s)
   INFO   code                   702  (confidence 1.00)
   INFO   code_reformatted         5  (confidence 0.95)
   INFO   code_date_mismatch      42  (confidence 0.90)
   INFO   date_province_name       2  (confidence 0.75)
   INFO   date_province            8  (confidence 0.60)
   INFO   unbound: no candidate           145
   INFO   unbound: several candidates       1
   INFO   unbound: parte claimed by another perimeter     2
   INFO 133 of the unbound fire(s) are in 2024, 2025, which the EGIF exports do not
        reach at all (campaigns 1982-2023 are imported)

That last line is the one to read before treating the unbound count as a defect. Of the
15 unbound fires that are *not* 2024 or 2025, nine are 2023, where the export is
partial. **The real residue is six fires in fifteen years.**

Two rules the Catalan cascade has and this one does not
-------------------------------------------------------

``date`` and ``date_name`` are the branches taken when a code carries **no province**: a
third of the Catalan archive uses formats that encode none. Every Andalusian code
encodes one, so those branches cannot be reached — and the migration that added the
check constraint refuses them outright, so a database cannot hold a binding this
cascade must never write.

A fire whose code did not decode is therefore left unbound, with a reason of its own
(``code carries no province``), rather than bound on a date alone. That is not timidity:
a date alone, against a region with 40,757 *partes*, is not evidence.

The municipality name is weaker here than in Catalonia
-------------------------------------------------------

``Municipio`` is often not a municipality. It is frequently the *paraje* — the site — and
sometimes the site hyphenated with the municipality: ``DEHESA DE LAS YEGUAS`` for a fire
EGIF files in Puerto Real, ``RETIN-BARBATE`` for one it files in Barbate.

Measured on the 749 fires stage 1 has already matched, which is the only ground truth
available:

===========================  =========
Rule                         Agreement
===========================  =========
published strings                81.0%
after ``normalise_name``         89.5%
also splitting on a hyphen       90.0%
===========================  =========

The Catalan pair reaches 94.4%. The third row was **measured and rejected**: it gains
four fires, and one of the four is ``CULLAR-BAZA`` matching ``Cúllar``, where Cúllar and
Baza are two different municipalities and the rule is right by accident. A rule that
gains 0.5% and can be wrong for the reason it is right does not belong in a cascade
whose whole discipline is refusing to guess.

What ``normalise_name`` does do is fold case and accents and un-invert the article:
REDIAM writes ``EJIDO (EL)`` and EGIF ``EJIDO, EL``, and by the time the words are
compared the parentheses and the comma have both become spaces, so one rule covers both.

The geometry test is evidence, not proof
-----------------------------------------

EGIF publishes an ignition coordinate for 12,378 of the 12,389 Andalusian *partes* of
2008-2023 — unlike Catalonia, where it publishes none at all before 1998, which is
exactly where the unresolved Catalan fires are. So the containment test is nearly always
available here.

It is nevertheless used only to **narrow**, never to reject:

.. warning::

   Of the 748 fires bound by identifier that have an EGIF point, **only 417 have that
   point inside the perimeter**. A published start point and a perimeter mapped
   afterwards disagree at this scale routinely — REDIAM's own points are inside their
   own perimeter 88 times out of 201.

   So a candidate whose point is outside is not thereby excluded. A containment test
   that would leave no candidate standing has said nothing, and the cascade carries on
   with the set it had.

On today's data the rule binds nothing: the ten fires that reach stage 2 are settled by
the province or the name first. It stays because it is the strongest evidence available
when they are not.

One *parte*, one perimeter — and here an identifier wins
---------------------------------------------------------

Two perimeters claiming the same *parte* means at least one claim is wrong. What happens
next is **the one place this application genuinely disagrees with its Catalan twin**:

* **an identifier against a guess** — the identifier wins and the guess is dropped;
* **guesses only** — all of them are dropped, because nothing in the data would make the
  choice.

The Catalan application drops every claim on a contested *parte*, on the grounds that
stage 1 cannot produce a contest. That is true of the Catalan data and not of this one.
Two real fires need the difference:

.. code-block:: text

   WARNING EGIF parte 2014040066 is claimed by 2 perimeters (2014040065, 2014040066);
           kept 2014040066, which matched on the published identifier, and dropped the rest
   WARNING EGIF parte 2018140034 is claimed by 2 perimeters (2018140033, 2018140034);
           kept 2018140034, which matched on the published identifier, and dropped the rest

In both, the *previous* fire of the same day and province reaches the same *parte*
through the date-and-province rule. Dropping both would throw away an identifier match
because a guess collided with it.

.. note::

   This is enforced in the application rather than by a unique constraint on
   ``egif_wildfire_id``, for the Catalan module's reason: a constraint would make a
   re-run *fail* on a conflict instead of reporting it, and the two datasets are
   published independently and will disagree again.

Re-running
----------

Every run **recomputes** the bindings in scope: the four columns are cleared first, then
written. A fire that no longer matches loses its link, which is what makes a correction
to either dataset take effect — a test renumbers a *parte* and checks that the binding
follows.

``--only-unbound`` restricts it to fires with no link yet, for the case where something
outside this application has bound a fire by hand.

``--csv`` writes one row per fire in scope, **bound and unbound alike**, with the
province beside the municipality:

.. code-block:: text

   code,fire_date,year,municipality_name,province_name,source_layer,outcome,method,...
   2022040091,2022-08-01,2022,DALIAS,Almería,PERIMETROS_COR_2008_2025,bound,code,1.00,...
   IIFF2025040059,2025-08-28,2025,LUBRIN,ALMERÍA,PERIMETROS_COR_2008_2025,unbound,,,,,0

A report of the successes says nothing about whether the rules are right; the unbound
rows and their candidate counts are what shows where the cascade ran out of evidence.

API reference
-------------

.. automodule:: src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires
   :members:
   :show-inheritance:
