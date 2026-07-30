Import EGIF fire statistics (Spain)
===================================

Imports the Spanish national fire statistics — the *Estadística General de Incendios
Forestales* — into :class:`~src.providers.egif.wildfire.EgifWildfire` and
:class:`~src.providers.egif.ignition.EgifIgnition` rows, in **two steps**: every Excel
export first, then every XML export.

.. contents::
   :local:
   :depth: 2

Usage
-----

Migrate the database first — the ``egif_*`` tables are created by migrations, not by the
importer — then point it at the directory the exports were downloaded into:

.. code-block:: bash

   make migrate
   python3 -m src.apps.imports.wildfires.egif.import_wildfires -d /path/to/egif/

Every ``.xlsx`` in the directory is read before every ``.xml``, both in name order, which
for these files is chronological. Individual files can be given instead:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.egif.import_wildfires \
       -s 2020-2023.xlsx 2020-2023.xml

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line.

.. note::

   Unlike the other wildfire importers this one needs **no ogr2ogr**. Both formats are
   read in Python and the only geometry work — turning the published easting and northing
   into the stored EPSG:4326 point — is done by PostGIS with ``ST_Transform``.

Import these first
------------------

:doc:`ign_import_admin_boundaries`
    Without the IGN municipal boundaries no fire gets an ``admin_boundary_id``. It is
    resolved *at import time* from the INE municipal code and cannot be filled in
    afterwards without re-importing.

    Note that the code itself is published **only in the XML**, so the boundary is
    resolved during step 2. A database built from Excel exports alone has no municipal
    code to match on.

The time zone areas are *not* needed. EGIF is a national dataset and the zone follows from
the province — :data:`~src.providers.egif.CANARY_PROVINCE_INE_CODES` — rather than from a
point-in-polygon test, which is also why it works for the 22,855 fires that have no point.

Why two steps
-------------

The service exports the same fires two ways and **each drops something the other keeps**.
Neither is sufficient, so the importer reads both and each step writes only the columns
its own format publishes.

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * -
     - Excel "resumen"
     - XML
   * - Shape
     - one flat row per fire, 31 columns
     - the full *parte*, 13 blocks + ``ParteMonte``
   * - Cause and motivation
     - **code with its label** — ``[213]  Quema de restos agrícolas``
     - bare code — ``213``
   * - Administrative location
     - **names** (``CATALUÑA``, ``PIERA``)
     - numeric ids only
   * - INE municipal code
     - —
     - **yes** (``idprovincia`` + ``idmunicipio``)
   * - *Paraje*, ``idpif``
     - —
     - **yes**
   * - Control time, response times, weather, cause certainty, fuel model, fire type
     - —
     - **yes**
   * - ``diastormenta`` (holdover interval)
     - —
     - **yes**

The order is not a preference. The Excel is the only public source of the cause and
motivation labels — the service's own ``Search/getCausasIncendio`` endpoint is behind a
login — so it has to seed :doc:`../providers/egif_fire_cause` and
:doc:`../providers/egif_fire_motivation` before the XML's bare codes can be resolved.
Running both steps in one command is what makes that automatic.

Both steps upsert on ``numeroparte``, so the same fire read from both formats lands on one
row.

.. important::

   **Each step writes only the columns its own format publishes.** This is the mechanism
   that stops the second step undoing the first, and it is why
   :data:`~src.apps.imports.wildfires.egif.import_wildfires.XML_WILDFIRE_COLUMNS` is
   deliberately *not* a superset of
   :data:`~src.apps.imports.wildfires.egif.import_wildfires.EXCEL_WILDFIRE_COLUMNS`.

   Without it, re-importing an Excel export to pick up a revised campaign would set
   ``egif_id``, ``municipality_ine_code`` and the *paraje* back to ``NULL`` — and nothing
   would report it.

One transaction per file
------------------------

A file is read to its end and then committed, so a run interrupted half way through a
285 MB export leaves the database exactly as it found it.

A *fire* that cannot be stored is a different matter: it is logged with its report number
and the reason, counted, and skipped, and the rest of the file is still committed. Losing
30,000 good fires to one bad one would be the wrong trade at every scale this dataset
comes in.

What makes a fire unstorable is deliberately short — **no report number, or no detection
instant**. ``wildfire.start_date_time`` is ``NOT NULL`` and EGIF publishes nothing that
could stand in for it. Everything else is degraded rather than refused.

Four things the published data does that the importer has to handle
--------------------------------------------------------------------

All four were found by profiling the whole 1982-2023 archive rather than one sample, and
each one silently corrupts an import that does not know about it.

A row's cells are addressed, not ordered
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Excel normally writes all 31 cells of every row including the empty ones — but not
always. Two fires in the 2008-2010 export have no extinction time and the writer **omitted
the cell for it altogether**, leaving those rows with 30 cells running ``A``-``Q``,
``S``-``AE``.

Read by position, everything from ``Extinguido`` on shifts one column left:

.. code-block:: text

   read by position:    Extinguido = '[400]  Intencionado'      <- the cause
                        Causa      = '[400]  Motivación desc…'  <- the motivation
                        SupArbolada= '0,0000'                   <- the next area

   read by reference:   Extinguido = NULL
                        Causa      = '[400]  Intencionado'
                        SupArbolada= '0,3500'

Every value in the wrong reading is well-formed, so nothing would complain. The reader
places each cell where its own ``r`` reference says it goes.

22,855 fires have no coordinate at all
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

9.2% of the archive, and almost all of it early — 10,865 of the 46,888 fires of 2004-2005,
1,037 in 2011-2013, **none from 2017 on**. Those fires get no
:class:`~src.providers.egif.ignition.EgifIgnition` row and a ``NULL`` ``ignition_id``,
rather than an ignition with a hole where the point should be.

If a later XML export supplies a coordinate for a fire that had none, the import gives it
one; the ignition is looked up by its own report number so an existing row is reused
rather than duplicated.

The datum is missing for most of the archive, and has three values
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``iddatum`` does not exist in the XML before the 2014-2016 campaigns, and the Excel's
``Datum`` column is blank over the same span. Where it does appear it takes three values,
of which two resolve: ``2`` ETRS89, ``5`` REGCAN95, and ``3`` on three records in the whole
archive, which maps to nothing published.

A fire with no datum is reprojected **as ETRS89**, which is what every fire that does say
anything says bar the Canarian ones — and those are caught by the zone, where
``(ETRS89, 28)`` is a metre-level difference from REGCAN95 rather than a wrong place. A
fire whose ``iddatum`` is the unmappable ``3`` keeps the raw code in
:attr:`~src.providers.egif.ignition.EgifIgnition.datum_code` beside a ``NULL`` datum.

The published zone is sometimes wrong, and so is the published lat/lon
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sixteen fires in the archive carry a ``huso`` outside 28-31 — ``3``, ``27``, ``32``,
``33``, ``39``, ``50``, ``63``, ``71``. The important part is that the service's own
``latitud`` and ``longitud`` are computed **from that bad zone**:

.. code-block:: text

   2011331154  huso 71  x 479930  y 4709201  ->  lat 42.53  lon -117.24   (Pacific)
   2011260019  huso 50  x 522617  y 4691013  ->  lat 42.37  lon  117.27   (Mongolia)

So the published geographic coordinate is **derived, not independent**, and cannot be used
to check the projected one. The importer derives the zone from the province instead, using
:data:`~src.providers.egif.PROVINCE_UTM_ZONES`, and reports every substitution.

.. warning::

   That map is **modal, not authoritative**. Eleven provinces genuinely straddle two
   zones, and across the whole archive the modal zone agrees with the published one on
   only 92.7% of fires. It is therefore consulted **only** when the published zone is not
   a zone Spain lies in — never to override a good value, which would move a quarter of a
   million points.

A coordinate that cannot be in Spain is refused, not reprojected
----------------------------------------------------------------

339 fires of the 292,447 that publish a coordinate — 0.12%, nearly all before 2011 —
publish one the fire cannot have been at. The failures are ordinary data entry and are
obvious once reprojected:

.. code-block:: text

   2022320419  Ourense   y = 4655        three digits missing   -> Gulf of Guinea
   2005230258  Jaén      434047, 434047  easting in both fields
   2006490039  Zamora    y = 46648500    an extra digit

Reprojected faithfully they scatter across the ocean, where nothing excludes them from a
spatial query. A fire whose coordinate falls outside
:data:`~src.providers.egif.PLAUSIBLE_UTM_EASTING` and
:data:`~src.providers.egif.PLAUSIBLE_UTM_NORTHING` is therefore stored **without an
ignition**, exactly like the 293,710 that publish none, and the substitution is logged.

The published numbers survive on the fire's own row either way, so refusing the *point*
loses nothing.

Dates
-----

Both exports publish naive local wall-clock — ``29/01/2022 15:22:00`` in the Excel,
``2020-01-01T16:30:00`` in the XML — and the instant they name depends on where the fire
was. The zone is chosen from the **province**: Las Palmas and Santa Cruz de Tenerife take
``Atlantic/Canary``, everything else ``Europe/Madrid``.

.. note::

   The province, not the *comunidad*, because the province code is the one identifier both
   exports agree on and neither can garble — it is characters 5-6 of ``numeroparte`` and
   equals ``idprovincia`` on all 29,926 fires checked. The XML's ``idcomunidad`` is **not**
   the INE autonomous-community code: EGIF numbers them its own way, with Cataluña as
   ``2``.

:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **detection**, not the
ignition: ``deteccion`` is the earliest instant the report carries and nothing in EGIF says
when the fire actually started.

.. warning::

   The interval between detection and extinction is unreliable at the tail. One 0.02 ha
   fire is stamped as burning for exactly 365 days. Treat a duration above about a week as
   suspect.

The catalogues
--------------

``Causa`` and ``Motivacion`` become rows of :doc:`../providers/egif_fire_cause` and
:doc:`../providers/egif_fire_motivation`, seeded from whatever the Excel exports actually
contain — 87 cause codes and 29 motivation codes over 1982-2023.

They are **two tables and never one**: ``400`` is *Intencionado* as a cause and
*Motivación desconocida* as a motivation, so joining them on the code alone would merge
two different things.

Each is unique on ``(code, label)`` rather than on the code, so an edition that renames a
code keeps both meanings. Since the XML publishes only the bare code, a code holding more
than one label is resolved to the label seen on the most fires and the situation is
reported. No code in the 1982-2023 archive is actually ambiguous; the rule exists so that a
future rename degrades to "the common meaning, with a warning" instead of to chance.

Running the XML step against a database whose catalogues were never seeded stores the
fires with a ``NULL`` cause and says so:

.. code-block:: text

   WARNING  87 egif_fire_cause code(s) are not in the catalogue, so those fires have
            no cause: 100 x2110, 400 x15704, … Import an Excel export covering them —
            it is the only source of the labels.

Progress and problems
---------------------

Each file gets a progress display: a bar rewritten in place when stderr is a terminal,
periodic log lines when it is redirected.

.. code-block:: text

   2020-2023.xml: [########------------]  38%  11,412/29,926  1,840/s  eta 0:00:10

The Excel row count is known in advance — a cheap second pass over the same zip — so those
bars carry a percentage and an estimate. An XML export cannot be counted without parsing
it, so its display shows the running count and rate instead.

Problems are logged per fire with its report number, up to
:data:`~src.apps.imports.wildfires.egif.import_wildfires.MAX_REPORTED_PROBLEMS` per file,
after which they are only counted — a file that is wrong in some systematic way would
otherwise write one line per fire and bury the summary that says so.

.. code-block:: text

   2011-2013.xlsx: imported 43208 of 43208 fire(s) in 19s (1037 without a point)
   WARNING  2011040074: huso '3' is not a zone Spain lies in; reprojected as zone 30,
            the usual one for province 04

What is not imported
--------------------

The XSD carries 13 ``pif_*`` blocks, a per-forest-unit ``ParteMonte`` block and 25
``Rel*`` relations, **all of which are populated** in the real exports. This import reads
the fire — where, when, why, how certain the why is, what burnt, the weather, and the fuel
and behaviour codes — and leaves the response and the accounting: ``pif_medios``,
``pif_tecnicas``, the casualty and by-ownership breakdowns, ``pif_anexo``'s regeneration
and erosion indices, and the whole ``ParteMonte`` tree.

See :mod:`src.providers.egif` for the scope decision and what it rests on. Adding any of
it later is additive: the report is 1:1 on the wildfire's primary key and ``numeroparte``
is a stable unique key, so a re-import backfills new columns by upsert.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.egif.import_wildfires
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.wildfires.egif.readers
   :members:
   :show-inheritance:
