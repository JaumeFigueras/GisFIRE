INAB wildfire statistics (Guatemala)
=====================================

Counts the Guatemalan fire reports per year: how many fires INAB was told about, how many
of those reports were false alarms, how many carry a coordinate and how many fell inside a
protected area.

The eighth of the burnt-area reports, after :doc:`GWIS <gwis_wildfire_statistics>`,
:doc:`GFA <gfa_wildfire_statistics>`, :doc:`ICNF <icnf_wildfire_statistics>`,
:doc:`EGIF <egif_wildfire_statistics>`, :doc:`DARPA <darpa_wildfire_statistics>`,
:doc:`REDIAM <rediam_wildfire_statistics>` and :doc:`Greece
<greece_ffa_wildfire_statistics>` — and the first with **no hectares in it at all**.

Usage
-----

.. code-block:: console

   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_statistics \
       --csv guatemala.csv --docx guatemala.docx

   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_statistics \
       --year 2025 --csv 2025.csv

   python3 -m src.apps.statistics.wildfires.guatemala_inab.wildfire_statistics \
       --include-false-alarms --csv every-call.csv

At least one of ``--csv`` and ``--docx`` is required. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and ``--db-password``.

There is no burnt area, and the columns are empty rather than absent
---------------------------------------------------------------------

.. warning::

   **INAB publishes no size of any kind.** Not a perimeter, not a hectare figure, not a
   land-cover split — nothing in the thirty-three published attributes says how big a
   fire was. :doc:`EGIF <egif_wildfire_statistics>` and :doc:`Greece
   <greece_ffa_wildfire_statistics>` publish no perimeter but do publish burnt areas, so
   their reports sum hectares; this one has nothing to sum.

   There is therefore no ``--area-method`` and no ``--surface``, and passing either is
   refused with that explanation rather than with argparse's *unrecognized argument*.

``Minimum (ha)``, ``Maximum (ha)`` and ``Total (ha)`` are nevertheless in the report, in
the position and the order the other seven put them, and **every one of their cells is
empty**:

* an empty cell is a claim that nothing was published, which is true. A zero would be a
  claim that nothing burnt, which is not — these fires burnt an unknown amount;
* the CSV still concatenates with the other seven reports' on their first six columns, so
  a reader comparing the eight countries sees Guatemala's gap *in* the table instead of
  having to notice its absence *from* it.

What this dataset answers is *where and when*. The four columns after the empty three are
what it answers with.

The columns
-----------

=====================  ========================================================
Column                 What it holds
=====================  ========================================================
``Country``            ``Guatemala`` on every row; nothing is tested to get there
``Year``               the Guatemalan calendar year — see below
``Fires``              how many fires, false alarms excluded by default
``Minimum (ha)``       empty
``Maximum (ha)``       empty
``Total (ha)``         empty
``False alarms``       how many of the year's records said there was no fire
``Located``            how many of ``Fires`` publish a coordinate
``Located (%)``        that as a share of ``Fires``
``In protected area``  how many of ``Fires`` fell inside one, as INAB reports it
=====================  ========================================================

Which year a fire counts towards
---------------------------------

The **Guatemalan calendar year** of the fire's own instant, resolved through
:data:`~src.providers.guatemala_inab.DEFAULT_TIME_ZONE`.

That is a departure from the rule the other reports follow, and it is forced. The ICNF
report groups on the published ``Ano``, the EGIF one on the filed ``Campania`` and the
Greek one on the sheet the row came from, because those sources publish a year. **INAB
publishes none**: ``fecha_hora_incendio`` is the only thing in the record that says when,
so the year is derived from it — and the local year is the one that means something, a
fire reported at nine in the evening on 31 December being a fire of that year rather than
of the next.

It is the same arithmetic :doc:`the import <inab_import_wildfires>` uses to decide which
year a record replaces, so a year in this report is exactly a year there. Both are six
hours from the UTC year, which is what the ArcGIS server's own ``EXTRACT`` may be counting
in.

False alarms are excluded, and counted
---------------------------------------

140 of the 4,615 published records are ``estado_aviso = 'falso'`` — the report was false,
there was no fire. They are records of a *call*, not of a fire, so ``Fires`` leaves them
out, as the Greek report leaves out ``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ``. ``--include-false-alarms``
counts them in.

Unlike the Greek report, this one gives them a column of their own rather than a line in
the log. They are 3% of the archive, they are not evenly spread, and a reader who cannot
see them in the table cannot tell a quiet year from a well-checked one. ``False alarms``
counts them either way; the Word document says which scope is in force.

.. note::

   Records whose status is ``no_verificado`` — nobody went to look, 90 of them — are a
   different claim and stay in ``Fires``. Folding the two together would turn 90 unknowns
   into 90 non-events. :doc:`inab_wildfire_classification` counts both, separately.

.. warning::

   The filter is ``IS DISTINCT FROM`` and not ``<>``. ``report_status`` is ``NULL`` on the
   records that carry no attributes at all, where ``<>`` evaluates to ``NULL``, so the
   obvious filter would drop them from ``Fires`` while leaving them in every other column
   of their row.

Every fire is located, which is worth a column for the opposite reason
------------------------------------------------------------------------

``Located`` is here because it is in the Greek report, and it reads the other way round:
**all 4,615 published records carry an EPSG:4326 point**, so the column is 100% throughout
rather than zero for twenty years and then 94%. That makes this the best-located
administrative fire statistic in the project, and it belongs in the table rather than in a
footnote — a column that stops being 100% is then a fact about a future publication,
visible immediately.

``In protected area`` is Guatemala's own column: the fires whose point fell inside one,
1,455 of them, close to one in three. That is a real property of Guatemalan fire rather
than a gap in the data. It counts a fire when ``nombre_ap_1`` is filled, which is INAB's
own containment test — no Guatemalan protected-area boundaries are imported that a point
could be tested against.

.. warning::

   That column is only correct because the import folded this source's ``""`` to ``NULL``.
   ``nombre_ap_1`` is ``null`` on 80 records and ``""`` on 3,080, so a database loaded
   without :func:`~src.providers.guatemala_inab.blank_to_none` would report 4,535 fires
   inside a protected area instead of 1,455. The report cannot detect that.

No country, and no cause
-------------------------

No ``--country`` and no ``--country-source``, as for the Greek, Catalan and Andalusian
reports: INAB publishes Guatemala's fires and nothing else, so the ``Country`` column is a
constant and nothing is tested against a boundary. Three of the published points are not
in Guatemala and all three are already flagged ``falso``, so they leave the count with the
other false alarms.

And there is no counts-by-cause companion, as there is for Portugal, Spain, Canada and
Mexico: **nothing in the thirty-three published attributes says why a fire started.** What
this dataset does carry is four published vocabularies describing the fire and the report,
and :doc:`inab_wildfire_classification` is what counts those.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.guatemala_inab.wildfire_statistics
   :members:
   :show-inheritance:
