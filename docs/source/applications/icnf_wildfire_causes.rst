ICNF wildfire counts by cause (Portugal)
=========================================

Counts the Portuguese ICNF wildfires per year: how many there were, how many carry a
cause at all, and how many of those were classified ``Natural``.

The companion of :doc:`icnf_wildfire_statistics`, over the same fires, the same years and
the same rule for which fires count — so the ``Country``, ``Year`` and ``Fires`` columns
of the two agree row for row and the pair can be read side by side. What that one measures
in hectares, this one counts by cause.

.. important::

   **The ICNF publishes no lightning category.** Its ``Causa_Tipo`` has five values —
   ``Negligente``, ``Intencional``, ``Desconhecida``, ``Reacendimento`` and ``Natural`` —
   and of its twenty-four ``Causa_Desc`` values exactly one is natural, ``Naturais``,
   which is not broken down further. Lightning is not named anywhere in the
   classification.

   ``Natural`` is the finest answer this dataset supports and is what the report counts.
   On the Iberian peninsula a natural fire is overwhelmingly a lightning fire — Spain's
   EGIF, which *does* separate them, has ``Rayo`` as its whole ``100`` family — so it is a
   good proxy. It is a proxy all the same, and the column is called ``Natural`` rather
   than ``Lightning`` so nothing downstream mistakes one for the other.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.portugal_icnf.wildfire_causes --csv causes.csv

   python3 -m src.apps.statistics.wildfires.portugal_icnf.wildfire_causes \
       --year 2024 --csv 2024.csv --docx 2024.docx

   # any of the five published types, not just the default
   python3 -m src.apps.statistics.wildfires.portugal_icnf.wildfire_causes \
       --cause-type Intencional --csv arson.csv

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

``--cause-type`` is matched against the **published Portuguese**, which is what the column
holds and what is ``NOT NULL``; the report's headings use the English from
:data:`~src.providers.portugal_icnf.fire_cause.TYPE_TRANSLATIONS`. The choices are read
from that same table, so a type the ICNF adds becomes selectable as soon as it is
translated on the model.

Output
------

=============  ======  =======  ============  ========  ===========================
Country        Year      Fires    Classified   Natural   Natural (% of classified)
=============  ======  =======  ============  ========  ===========================
Portugal       2024         22            20         3                       15.00
Portugal       2023         16            16         1                        6.25
Portugal       2013          7             0         0
Portugal       Total        45            36         4                       11.11
=============  ======  =======  ============  ========  ===========================

The ``.csv`` writes bare numbers because it is read by another program more often than by
a person; the ``.docx`` writes them with thousands separators and right-aligned, with the
summary row in bold, because it is not.

Only fires from 2014 on carry a cause
--------------------------------------

**18,955 of 68,435.** Every fire before that has ``cause_id`` ``NULL``, and so does an
unclassified fire in a year that otherwise has them.

That is why ``Classified`` is a column of its own and why the percentage is of it. A
percentage of *all* fires would be a statement about how much of the archive has been
classified rather than about what caused the fires: it would read 0.00 for every year from
1975 to 2013, and those were not years without natural fires.

.. warning::

   Do not compare a ``Natural %`` from before 2014 with one from after — there is no such
   thing as the first.

   And take even the classified share as a floor. ``Desconhecida`` and ``Indeterminadas``
   are real categories here, and a fire whose cause was never determined may well have
   been natural.

Where nothing is classified there is no percentage to give, and the cell is left **empty**
rather than filled with a zero that would be a claim. In the CSV that is an empty field,
which reads as *no answer* to whatever parses it. A run whose whole scope is unclassified
also says so in the log:

.. code-block:: text

   WARNING No fire in scope carries a cause at all, so every Natural count is zero and
           no percentage can be given: the ICNF publishes a cause only from 2014 on

The ``Total`` row's share is the **ratio of the totals**, not the mean of the years'
shares — a year with two classified fires must not weigh as much as one with a thousand.

Which fires are counted
-----------------------

Exactly the rule :doc:`icnf_wildfire_statistics` uses, so the two agree: a fire needs a
perimeter and a country. Fires with no country are excluded — a perimeter in the sea, and
any fire that matched no OCHA boundary — and so is any fire with no perimeter.

Counting a fire the other report cannot measure would be defensible on its own, but it
would mean the ``Fires`` column of the two reports quietly disagreeing, and the whole
value of a companion report is that it does not. A test holds the two together.

``--country-source`` behaves exactly as it does there, and is in fact the same code:
``geometry`` (default) tests the perimeter against the real country polygons at report
time, ``reported`` trusts the stored ``admin_boundary_id``. There is no ``--country``, for
the same reason as there.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.year`, the published ``Ano``,
exactly as in the companion report and for the same reason: 71% of these fires publish no
date and carry a 1 January placeholder built from this column in the first place.

Shared with the companion report
--------------------------------

``--country-source``, the years query and the country ordering are **imported from**
:mod:`~src.apps.statistics.wildfires.portugal_icnf.wildfire_statistics` rather than copied.
Two reports over one dataset that disagreed about which country a fire is in would be
worse than one report, and a copy is a thing that drifts.

It follows that this report is also one statement **per year**, under a spinner of its
own, with the ``Total`` row computed from the years' results — the same shape, and for the
same reason: whatever the point-in-polygon test of ``geometry`` costs, it is released when
its statement ends.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.portugal_icnf.wildfire_causes
   :members:
   :show-inheritance:
