EGIF wildfire counts by cause (Spain)
======================================

Counts the Spanish EGIF wildfires per campaign: how many there were, how many carry a
cause at all, and how many of those were started by **lightning** — and then the same
three counts again over the fires whose published ignition point really falls inside
Spain.

The companion of :doc:`egif_wildfire_statistics`, over the same archive and the same
campaigns. What that one measures in hectares, this one counts by cause.

.. important::

   **EGIF names lightning outright.** ``idcausa`` is a three-digit code whose first digit
   is the family, and the ``1`` family is :data:`~src.providers.spain_egif.CAUSE_LIGHTNING`,
   *Rayo*.

   So this report's default column is a count of lightning fires and means exactly that.
   Contrast :doc:`icnf_wildfire_causes`, whose dataset publishes no lightning category at
   all and has to count ``Natural`` as a proxy — the two reports are deliberately shaped
   alike, but only one of them is counting the thing it is named after.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \
       --year 2023 --csv 2023.csv --docx 2023.docx

   # any of the six families, not just the default
   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \
       --cause-family intentional --csv arson.csv

   # one autonomous community instead of the whole country
   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \
       --region Catalonia --csv catalonia-lightning.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

Output
------

Eleven columns, in two blocks. The ``.docx`` puts them on a **landscape** page, because
they do not fit across a portrait one.

.. code-block:: text

   Country  Year    Fires  Classified  Lightning  Lightning %  Fires inside  Fires inside (%)  Classified inside  Lightning inside  Lightning inside (%)
   Spain    2023     5223        5223        328         6.28          5221             99.96               5221               328                  6.28
   Spain    2022     8433        8433        879        10.42          8383             99.41               8383               877                 10.46
   Spain    1986     7514        7514        247         3.29             0              0.00                  0                 0
   Spain    Total  586157      586157      25863         4.41        289982             49.47             289982             13900                  4.79

The real 1982-2023 archive, verbatim. 1986 is the shape of a pre-1998 campaign: every fire
filed and classified, and not one of them with a coordinate to place — which is why the
``Total`` row can place only 49.47% of the archive. The ``Country`` column is ``Spain`` on
every row.

The ``.csv`` writes bare numbers because it is read by another program more often than by a
person; the ``.docx`` writes them with thousands separators and right-aligned, with the
summary row in bold, because it is not.

The two blocks
--------------

The left-hand block is **every fire EGIF filed**. The right-hand one repeats the same
counts over the fires whose published ignition point the database finds inside the real
Spanish polygon, tested against the OCHA country outlines at report time. ``Fires inside
(%)`` is the gap between them: how much of a campaign can be placed on the ground at all.

This is deliberately **not an option**, unlike the ``--country-source`` of
:doc:`egif_wildfire_statistics`. There, testing the point *removes* fires from the report
and switching it on silently halves the archive, so it has to be chosen consciously; here
both answers sit in the same row and neither can hide the other. Passing
``--country-source`` is refused with a message saying so.

Why a point can be outside
--------------------------

EGIF publishes no perimeter, but it does publish a coordinate — and that coordinate
can be somewhere a Spanish fire is not. The importer's only geometric guard is a
plausibility box on the published UTM easting and northing
(:data:`~src.providers.spain_egif.PLAUSIBLE_UTM_EASTING`), a rectangle containing a
great deal of Atlantic and Mediterranean; and where the published *huso* is not a
zone Spain lies in, the zone is replaced with the modal one for the province, which
can walk a coastal point out to sea or over a border.

A fire is outside for two different reasons, and the log gives the one that is free
to count:

**no point published**
    The big number, and an ordinary property of the archive rather than a fault:
    **294,052 of the 586,157 fires publish no coordinate at all**, every fire before
    1998 among them. It improves monotonically — 1998-1999 publishes one for 29% of
    fires, 2011-2013 for 98%, and from 2017 on every fire has one.

**a point that is not in Spain**
    A coordinate in the sea or over a border. It is the difference between the two
    numbers the log gives and needs no extra work to see.

.. code-block:: text

   INFO Of 586157 fire(s), 289982 have a point inside Spain (49.47%);
        294052 publish no point at all

**Which** other country such a point falls in is deliberately not asked — see below.

.. warning::

   If the OCHA country boundaries are not imported there is no Spanish polygon to be
   inside, every ``... inside`` column is zero, and a table of zeros looks exactly
   like an answer. The report checks for that case and says so. See
   :doc:`ocha_import_admin_boundaries`.

One autonomous community
------------------------

``--region`` counts one *comunidad autónoma* instead of the whole country —
``--region Catalonia``, ``--region Andalucía``, ``--region 09``. It takes the same names,
codes and spellings as the companion report's option of the same name, resolved by the
same code: see :ref:`egif-region` for the whole rule and for why the selection is on the
province the *parte* is filed to rather than on the published coordinate.

.. code-block:: bash

   # lightning fires in Catalonia, campaign by campaign
   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \
       --region Catalonia --csv catalonia-lightning.csv

   # and the same community's arson
   python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \
       --region Catalonia --cause-family intentional --csv catalonia-arson.csv

A campaign in which the community filed nothing is **absent** from the report rather than
present as a row of zeros: a zero row would say the community had a fire-free year, which
is not the same statement as the export not reaching it.

.. important::

   **The** ``... inside`` **columns still test the point against Spain**, not against the
   community. That is the question this report always asks — can this fire be placed on
   the ground at all — and its answer is not a claim that the point lies inside the
   community the fire was filed in. A fire filed in Girona whose coordinate landed in
   France is *outside*; one that landed in Aragón is *inside*.

   Asking whether a point falls inside the community it was filed in is a different
   report, and a useful one, but it is not this one. The ``.docx`` says as much on its
   front page whenever a region is in force.

One polygon, one campaign at a time
------------------------------------

The report is eight numbers per campaign, and it is computed exactly that way: one
statement per campaign, then the ``Total`` row by addition. Six aggregates over the
same rows come out of that statement together — splitting them would read the same
fires six times — and doing a campaign at a time bounds what any statement holds and
lets a long run say which year it is on.

.. warning::

   **The geometry is one** ``ST_Contains`` **per fire against one prepared polygon**,
   and it has to stay that way.

   This report once asked, for every fire, *which* of the world's countries contained
   its point: a lateral over every level-0 boundary, ordered so Spain would win a tie,
   taking the first. That is 318 polygon tests per fire instead of one, and the
   ``ORDER BY`` stopped the ``LIMIT 1`` from exiting early.

   Measured on the real archive: **0.6 seconds per located fire** — 200 fires in 120
   seconds, which over the 292,105 fires that publish a point is about **49 hours**.
   One campaign of 8,433 fires did not finish in two minutes.

   ================================  ===========  ===========
   \                                 Old          New
   ================================  ===========  ===========
   Campaign 2022 (8,433 fires)       >120 s       1.0 s
   Whole archive (586,157 fires)     ~49 h        **17 s**
   ================================  ===========  ===========

   The fix was not a faster query but a smaller question. *Is this point in Spain?*
   needs Spain's polygon and nothing else. A test asserts the statement still selects
   the country by name, because a change that dropped that filter would give the same
   answers and quietly restore the hours.

Which fires are counted
-----------------------

**Every EGIF fire of the campaign.** There is no ``--surface`` and no ``--min-area``: this
report counts fires, and a fire whose report form leaves the burnt area blank is still a
fire.

.. warning::

   That means this report's ``Fires`` column does **not** match
   :doc:`egif_wildfire_statistics`'s, and is not meant to. The companion report excludes
   any fire that does not report the surface asked for — it has to, or its ``Fires`` column
   would stop counting the fires its three area figures were computed from. The difference
   between the two is exactly the fires with a blank surface on the form.

   This is the one place where the EGIF pair behaves differently from the ICNF pair
   (:doc:`icnf_wildfire_statistics` and :doc:`icnf_wildfire_causes`), which are built to
   agree row for row and have a test holding them together.

Which causes are counted
------------------------

``--cause-family`` selects one of the six families by the leading digit of ``idcausa``:

=================  =======  =========================================================
Value                Digit  EGIF
=================  =======  =========================================================
``lightning``      ``1``    *Rayo* — the default
``negligence``     ``2``    Negligence in activities that use fire: agricultural and
                            livestock burns, forestry residue, campfires, smokers
``accident``       ``3``    Accidents in activities with no implicit use of fire:
                            railway, power lines, machinery, vehicles, military
``intentional``    ``4``    *Intencionado*, whose detail is in ``idmotivacion``
``unknown``        ``5``    *Desconocida*
``rekindle``       ``6``    *Reproducido*
=================  =======  =========================================================

The ``2``/``3`` boundary is close to "with or without an implicit use of fire" but is not
clean at the edges — ``292`` *Fuegos artificiales* is in the first and ``300`` *Quema de
cables para extraer cobre* in the second — which is why GisFIRE stores the digit and does
not materialise a column naming the split.

Matching is on the **family digit**, not on the exact code. ``100`` is today the whole of
the lightning family, but the catalogue is versioned — the *Instrucciones para cumplimentar
el parte de incendio forestal* are at v3.6, *9ª actualización*, and every revision so far
has added subcodes — so a future ``101`` *Rayo seco* is counted the day it appears rather
than the day someone notices the source file.

The digits of the four families :mod:`src.providers.spain_egif` names are taken from its
constants rather than written out again, so a renumbering there cannot leave this report
counting the old digit. ``2`` and ``3`` have no constant: they are families of subcodes
with no bare parent.

The percentage and its denominator
----------------------------------

Of the **classified** fires, not of all of them, in both blocks — and where nothing is
classified there is no percentage to give, so the cell is left **empty** rather than filled
with a zero that would be a claim. In the CSV that is an empty field, which reads as *no
answer* to whatever parses it.

EGIF's Excel export classifies every fire, so ``Classified`` normally equals ``Fires``; an
XML import into a database whose cause catalogue was never seeded cannot resolve one, and
that is a case worth being able to see. A run whose whole scope is unclassified says so:

.. code-block:: text

   WARNING No fire in scope carries a cause at all, so every Lightning count is zero and no
           percentage can be given: an XML import cannot resolve idcausa unless the cause
           catalogue has been seeded first

The ``Total`` row's shares are the **ratio of the totals**, not the mean of the campaigns'
shares — a campaign with three classified fires must not weigh as much as one with a
thousand.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.spain_egif.wildfire.EgifWildfire.campaign`, the filed ``Campania``,
exactly as in the companion report and for the same reasons: it is what a published yearly
total is a total of, it is ``NOT NULL`` and indexed, and it needs no timezone applied to it
— which ``start_date_time`` would, EGIF's instants being local wall-clock readings in two
different zones.

One statement
-------------

One, for the whole report. The grouping is by campaign **and placement**, so both blocks of
counts, the ``Total`` row and the whole outside-the-border audit come out of a single pass —
which means the point-in-polygon test is paid once per fire rather than once per number.
There is no year-at-a-time machinery here for the same reason as in the companion report: a
point is a far cheaper thing to contain than a multipolygon.

Shared with the companion report
--------------------------------

The country name, the country level, the campaign column, the ``Total`` label and the
country ordering are **imported from**
:mod:`~src.apps.statistics.wildfires.spain_egif.wildfire_statistics` rather than copied. Two
reports over one dataset that disagreed about which campaign a fire is filed under would be
worse than one report, and a copy is a thing that drifts.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.spain_egif.wildfire_causes
   :members:
   :show-inheritance:
