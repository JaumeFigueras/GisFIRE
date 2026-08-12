CONAF perimeter ↔ report binding (Chile)
========================================

Links each *incendio de magnitud* perimeter to the seasonal report of the same fire: the
shape to the cause, the reporter, the administrative location and the fourteen published
areas, which is the pairing neither product carries on its own.

Fills in
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.conaf_wildfire_id`
and the three columns that account for it — ``match_method``, ``match_confidence`` and
``matched_at``. **It writes nothing else, ever**: no row is created, no perimeter is
touched, no report column is written, and running it on an empty database is a no-op.

.. important::

   **These are one agency's two publications of one incident record**, unlike
   :doc:`nbac_bind_nfdb_wildfires`, which joins two agencies' independent accounts. Every
   one of the 743 perimeters *is* a report in :doc:`../providers/conaf_wildfire`; the job
   is to find which one.

   That makes this the most successful binder in GisFIRE that has no unique key behind
   it: **706 of 743, 95.0%**, with 3 finding no candidate at all, 28 ambiguous and 6
   contested.

.. warning::

   **The shared identifier is not unique, and no method scores 1.00.**

   ``NUMERO_REG`` is CONAF's own running number for a fire and it really is the same
   number in both products — but it repeats within a season and even within a región. 93
   perimeters of 2016-2017 have a ``(CODREG, NUMERO_REG)`` that matches **two** reports.

   So the número alone is not an identification, and the cascade has two tie-breaks above
   it: the name, which settles 83 of those 93, and containment of the report's point,
   which settles 77. The strongest rule scores 0.98 and asserts three agreeing
   attributes, not an identifier.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires

   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires \
         -y 2016

   # see what it would do, and why, without writing anything
   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires \
         --dry-run --csv bindings.csv

   # containment only: no report point outside a mapped perimeter is accepted
   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires \
         --max-distance 0

Import both products first — :doc:`conaf_import_wildfires` and
:doc:`conaf_magnitud_import_wildfires`. Settings are read from the environment (``.env``,
see :doc:`../setup/configuration`).

The cascade
-----------

Every candidate report is labelled with the **strongest rule it satisfies**, the
best-labelled group is taken, and the binding is written only if that group holds exactly
one.

============================================  ==========
Method                                        Confidence
============================================  ==========
``number_region_name_season``                       0.98
``number_region_inside_season``                     0.96
``number_region_season``                            0.95
``number_name_season``                              0.93
``name_season_inside``                              0.90
``name_season``                                     0.80
``inside_single``                                   0.70
``near_single``                                     0.60
============================================  ==========

Two properties of the labelling are deliberate and are worth stating.

**A missing value never agrees with a missing value.** ``NUMERO_REG`` is unpublished on
two whole seasons of reports, and treating *neither has one* as agreement would bind every
perimeter of 2013-2014 to whichever report happened to be nearest and score it 0.95. The
same holds for ``CODREG``, which six of the fifteen mainland seasons do not publish.

**The número rules are not gated on distance.** A report's point is where the office
filed it, and for a 200-hectare fire that can be a road junction kilometres away — or, in
the older seasons, the comuna's centre. Gating the strongest evidence in the archive on
the weakest would throw it away.

The candidates are found two ways and unioned: spatially, from the two geometry indexes,
and by attribute, from the season's reports whose ``(region_code, number)`` or folded name
matches. The second is not a refinement of the first, for the reason just given.

The refusals
------------

Three, and each is recorded so the CSV can be acted on rather than merely read.

``no candidate``
    Nothing agreed and nothing was near. Three perimeters.

``several candidates``
    The best-labelled group holds more than one, and nothing in the data separates them.
    Picking one would be picking at random and scoring it 0.95. 28 perimeters.

``report claimed by another perimeter``
    Two perimeters both bound to one report, so **both** are unbound. A contest here
    usually means one report covers a fire CONAF mapped in two separately-named pieces —
    a dissolve :doc:`conaf_magnitud_import_wildfires` did not make — which is worth
    looking at rather than papering over. 6 perimeters, in 3 contests.

Rerunning recomputes every binding in scope from scratch: a binding is a conclusion about
the current data, not a record of a past run. ``--only-unbound`` leaves the existing ones
alone.

API reference
-------------

.. automodule:: src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires
   :members:
   :show-inheritance:
