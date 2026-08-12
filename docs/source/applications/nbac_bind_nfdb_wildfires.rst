NBAC ↔ NFDB wildfire binding (Canada)
=====================================

Links each Canadian burned-area perimeter to the agency fire report for the same fire:
the shape to the cause, the response, the protection zone and the reported size, which
is the pairing neither dataset can supply on its own.

Fills in :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id` and
the three columns that account for it — ``match_method``, ``match_confidence`` and
``matched_at``. **It writes nothing else, ever**: no row is created, no perimeter is
touched, no NFDB column is written, and running it on an empty database is a no-op.

The lightning work is why it matters. NFDB's 195,240 natural-cause fires are the
largest such set in GisFIRE and every one has a point and a date; NBAC is where the
area actually burnt is. Binding them is what makes *how much burnt, by what cause* a
question this project can ask of Canada at all.

.. danger::

   **This binding has no identifier behind it, and its two Spanish predecessors do.**

   :doc:`darpa_bind_egif_wildfires` rests on ``CODI_FINAL`` being the EGIF
   ``report_number`` and :doc:`rediam_bind_egif_wildfires` on ``CODIGO`` being it —
   749 of that one's 759 bindings. NBAC publishes nineteen fields, the same nineteen in
   every one of its fifty-three yearly archives, and **not one of them is an agency fire
   number**::

      YEAR NFIREID BASRC FIREMAPS FIREMAPM FIRECAUS HS_SDATE HS_EDATE AG_SDATE
      AG_EDATE CAPDATE POLY_HA ADJ_HA ADJ_FLAG ADMIN_NAME ADMIN_DIV PRESCRIBED
      VERSION GID

   ``NFIREID`` is NBAC's own within-year sequence and ``GID`` is the year and that
   sequence run together. Neither has any relationship to NFDB's ``NFDBFIREID`` or
   ``FIRE_ID``.

   So every binding here is an inference from place, date and agency, and **no method
   scores 1.00**. A ``--min-confidence 0.9`` that means *identifier matches only* in
   Spain has no equivalent here; the nearest thing is ``>= 0.95``, which means *the
   point is inside the polygon and both sources agree on the agency and the day*.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires

   python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires --year 2023

   # see what it would do, and why, without writing anything
   python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires \
       --dry-run --csv bindings.csv

   # containment only: no point outside a burnt perimeter is accepted
   python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires \
       --max-distance 0

Import both datasets first — :doc:`nbac_import_wildfires` and
:doc:`nfdb_import_wildfires`. Settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden with ``--db-host``,
``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

What the two datasets do share
------------------------------

Three things, measured rather than assumed.

**The geometry.** Both are published on EPSG:3978 and both keep the published geometry
unchanged, so the containment test is metres on a common national grid with no
reprojection and no assumption about whose CRS is authoritative. That is a better
position than the Spanish binder is in, where the test only works at all for the half
of EGIF that publishes a coordinate.

**The date.** NBAC's ``AG_SDATE`` is *the agency's* start date, so it comes from the
same records NFDB publishes as ``REP_DATE`` — and it shows: on the perimeters that
contain a point, the two agree exactly on 157 of 1985's 177 dated pairs.

.. important::

   **The exactness is the signal.** Widening the comparison to ±3 days makes the
   binding *worse*, not better — on 1974 it takes the unambiguous matches from 193 down
   to 180 — because a tolerance re-admits the neighbours the exact date was
   discriminating against. This is the opposite of the usual intuition about fuzzy
   matching and it is why there is no ``--date-tolerance`` option.

**The agency.** ``ADMIN_NAME`` and ``SRC_AGENCY`` are the same vocabulary of
provincial, territorial and Parks Canada codes: 178 agreements in 181 in 1985, 128 in
128 in 1986. A perimeter cut at a provincial boundary carries several, joined by
``'; '`` — ``'AB; SK'`` is one fire in two provinces — so the test is **membership and
not equality**, which matters for 450 of the 51,818 perimeters.

Together, ``(agency, exact day)`` is the pseudo-identifier this pair of datasets does
not otherwise have.

The cascade
-----------

Every candidate is labelled with the **strongest rule it satisfies**, the best-labelled
group is taken, and a link is written **only when that group holds exactly one
candidate**.

===  ===================================================  ===============================  ==========
#    The candidate…                                       Method                           Confidence
===  ===================================================  ===============================  ==========
1    is inside the perimeter, same agency, same day       ``inside_agency_day``            0.95
2    is inside, same agency, NBAC publishes no date       ``inside_agency_undated``        0.85
3    is inside, same agency, the dates disagree           ``inside_agency_date_mismatch``  0.80
4    is inside, and the agency does not match             ``inside``                       0.70
5    is within ``--max-distance``, same agency, same day  ``near_agency_day``              0.60
===  ===================================================  ===============================  ==========

Anything else is **not a candidate at all**: being within two kilometres of a burnt
area, from another agency, on another day, is not evidence of anything, and admitting
it would only make well-determined fires ambiguous.

The labels are disjoint and ordered, so an ambiguous best group **ends** the cascade
rather than falling through to rule 5. Every later rule is a weaker kind of claim, not
a narrower set, and widening can only add candidates — there is nothing below that
could separate what the best evidence could not.

A perimeter whose best group holds two or more is left **unbound and reported**. That
is the conservative half of the design and it is deliberate: a wrong binding silently
attaches another fire's cause and reported size to a perimeter and nothing downstream
could ever detect it, while a missing binding is visible in the first report anyone
runs.

Rule 5 is half the work, and all of the risk
---------------------------------------------

On 1985-1995 it produces about as many bindings as all four containment rules together
— 143 of 1985's 279, 118 of 1986's 225. It has to exist: an agency point is *where
somebody said the fire was*, the published summary says outright that *"locations are
approximate"*, and a point a kilometre outside a burnt polygon is the normal case
rather than a fault.

But it is a claim about proximity rather than containment, so how far is too far was
**measured**. Taking the 1,359 perimeters of 1985-1995 that have a known-good contained
partner, and asking how often a *wrong* point is also nearby with the same agency and
the same day:

====================  ===================  ===============
``--max-distance``    rule 5 bindings      decoy density
====================  ===================  ===============
500 m                 1,034                3.7%
1 km                  1,478                5.7%
**2 km** *(default)*  **1,685**            **7.5%**
5 km                  1,730                13.0%
====================  ===================  ===============

There is a knee at 2 km. Going on to 5 km buys 45 more bindings — 2.7% — and nearly
doubles the chance that the single candidate a fire is bound to is somebody else's
fire.

.. warning::

   The decoy density is a property of the neighbourhood, not a false-positive rate:
   rule 5 fires only where exactly one candidate exists, so a crowded neighbourhood is
   refused rather than guessed at. What it measures is the risk in the case that
   cannot be checked — the true partner missing from NFDB and one wrong point present.

   For an analysis that will not tolerate that, filter on ``match_confidence >= 0.7``,
   or run with ``--max-distance 0`` and take containment only.

One report, one perimeter
-------------------------

Two perimeters must never end up bound to the same NFDB report. Nothing prevents it —
there is no identifier to be unique, unlike the Catalan cascade where the code stage
could not produce a contest — and it happens a couple of times a year, where one agency
report sits between two mapped polygons.

Where it happens **neither is bound**, and both are reported. Nothing in the data would
make the choice, and picking anyway is exactly the silent wrong answer this application
is built to avoid. It is enforced in the application rather than by a unique constraint
so that a genuine many-to-one — NBAC splitting what an agency filed as one fire — stays
a data question to be looked at rather than a crash halfway through a run.

A year at a time
----------------

The candidates are generated one year per statement. It is not optional here: 51,818
perimeters against 380,000 points is a spatial join that has no business being asked in
one piece, and a year of it is a few thousand rows either side. The cascade itself then
runs in Python over that year's candidates.

Every year is committed as it goes, so an interrupted run keeps the years it finished.
``--dry-run`` does all the work and rolls it back.

Re-running recomputes rather than accumulates
----------------------------------------------

The four columns are cleared for the whole scope before the cascade writes: a
perimeter that used to match and no longer does has to **lose** its link, or a
correction to either dataset could never take effect. ``--only-unbound`` narrows the
scope to the perimeters that have no link, which is the way to add to an existing run
rather than redo it.

Options
-------

===================  =========================================================
``--year``           bind one year's perimeters against that year's reports
``--max-distance``   how far outside a perimeter a point may be (default 2000 m;
                     ``0`` keeps containment only)
``--only-unbound``   leave existing links alone and try only the unbound
``--dry-run``        run the cascade and report, writing nothing
``--csv``            write every perimeter in scope, bound or not, to a file
===================  =========================================================

The ``--csv`` report holds the **unbound** fires too, and they are the point of it: a
binding that happened needs no looking at, and one that did not is either a fire to
check or a gap in coverage. Each row carries the rule, the confidence and the distance
that was used.

API reference
-------------

.. automodule:: src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires
   :members:
   :show-inheritance:
