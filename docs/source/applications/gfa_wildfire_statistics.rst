GFA wildfire statistics
=======================

Reports the Global Fire Atlas wildfires per country and year: how many there were, and
the smallest single fire, the largest single fire and the total burnt area, in hectares.

This is :doc:`gwis_wildfire_statistics` over a different dataset, and deliberately so —
same four figures, same grouping, same two output formats. The two Atlases derive fire
events from the same MODIS MCD64A1 burnt-area product by different algorithms, so putting
their reports side by side is a real question; it is only answerable if the method is held
fixed.

Usage
-----

Over everything, or narrowed to one country, one year, or both:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.gfa.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.gfa.wildfire_statistics \
       --country Spain --year 2021 --csv spain_2021.csv --docx spain_2021.docx

``--country`` takes either a name (``Spain``) or an ISO 3166-1 alpha-3 code (``ESP``),
case-insensitively. At least one of ``--csv`` and ``--docx`` is required.

``--country-source`` decides whether a fire's country is taken from the real country
geometry (the default) or from what the import stored — see *Which country a fire
counts towards* below.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

Output
------

Both formats carry the same table. Each country's years run newest first, closed by a
``Total`` row:

=============  ======  =======  ============  ============  ============
Country        Year      Fires  Minimum (ha)  Maximum (ha)  Total (ha)
=============  ======  =======  ============  ============  ============
Spain          2021       1204         21.47      21985.45      91721.90
Spain          2020        876         21.47        193.30        622.93
Spain          Total      2080         21.47      21985.45      92344.83
France         2021        331         21.51       7978.39      11271.13
France         Total       331         21.51       7978.39      11271.13
=============  ======  =======  ============  ============  ============

.. important::

   A country's ``Total`` row is **not** a total of every column above it. ``Fires`` and
   ``Total (ha)`` are sums; ``Minimum`` and ``Maximum`` are the smallest and largest fire
   that country had in *any* year in scope. Summing a column of minima would produce a
   number with no meaning.

The two formats differ deliberately in one respect: the ``.csv`` writes bare numbers
(``21985.45``, ``1204``) because it is read by another program more often than by a
person, while the ``.docx`` writes them with thousands separators and right-aligned,
because it is not. In the Word document each ``Total`` row is bold, which is what
separates the country blocks visually.

.. note::

   **Why DOCX rather than RTF.** Both open in Word, but ``.docx`` is Word's own current
   format and carries a real table object — one that can be sorted, restyled, or pasted
   into Excel with its cells intact. RTF would carry the same characters as a formatting
   stream, which Word renders but cannot manipulate as a table nearly as well. It is also
   already a project dependency (`python-docx <https://python-docx.readthedocs.io>`_, pure
   Python, no system package), used by the GWIS report. The import is done inside the
   writer rather than at module scope, so ``--csv`` keeps working even where it is not
   installed.

How the area is measured
------------------------

The perimeters are stored in EPSG:4326, whose units are degrees, so an area has to come
from somewhere that yields metres. Two ways are offered, selected with ``--area-method``:

.. list-table::
   :header-rows: 1
   :widths: 18 46 36

   * - Method
     - SQL
     - What it is
   * - ``geodesic`` *(default)*
     - ``ST_Area(perimeter::geography)``
     - The true area on the WGS84 ellipsoid. No projection is chosen, so none has to be
       justified. What the GWIS report uses.
   * - ``equal-area``
     - ``ST_Area(ST_Transform(perimeter, 6933))``
     - Projected into NSIDC EASE-Grid 2.0 Global — a cylindrical **equal-area**
       projection defined worldwide — and measured there in metres.

**They agree.** Measured against each other on the same polygons the two differ by at most
0.003%:

.. code-block:: text

   where                geodesic ha      EASE-Grid ha    difference
   equator      (0N)      49,236.24         49,236.19       -0.000%
   Spain       (41N)      37,318.24         37,318.25        0.000%
   Sweden      (63N)      22,515.27         22,515.30        0.000%
   Arctic      (70N)      16,959.15         16,959.18        0.000%
   Tasmania    (42S)      36,752.95         36,752.96        0.000%
   1° x 1° square        954,946.89        954,952.01        0.001%

So the choice does not move any number in this report. The default is ``geodesic`` only
because it needs no CRS argued for, and because it is what the GWIS report uses.

.. warning::

   What **does** move the numbers is projecting into something that is not equal-area.
   The same polygons measured in Web Mercator (EPSG:3857) come out:

   .. code-block:: text

      Spain       (41N)      +76%
      Tasmania    (42S)      +82%
      Sweden      (63N)     +387%
      Arctic      (70N)     +759%

   because Mercator's area distortion grows as ``sec²(latitude)``. For a dataset spanning
   every latitude MODIS sees, "convert to projected coordinates and compute the surface"
   is safe **only** if the projection is chosen for area. That is why the option is named
   ``equal-area`` and not ``projected``, and why it is a fixed choice rather than a CRS
   the caller passes in.

The result is cross-checked in the test suite against :mod:`pyproj`, which computes the
same geodesic area through PROJ rather than through PostGIS — two independent
implementations rather than a number copied out of the first run. A further test asserts
that the two methods agree with each other, and one asserts that Web Mercator would not.

The Atlas's own size is not used
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:attr:`~src.providers.gfa.wildfire.GfaWildfire.size_km2` is what the Global Fire Atlas
publishes as the fire's size, and it is **not** what this reports. It is kept as published
and is worth having as an independent check — a systematic gap between it and the measured
area would say something about either the perimeter or the Atlas — but a report that mixed
the two would be comparing a measurement with a claim.

.. code-block:: sql

   -- how well the published size agrees with the measured perimeter
   SELECT gfa_id,
          size_km2 * 100                                     AS published_ha,
          ST_Area(perimeter::geography) / 10000.0             AS measured_ha
   FROM gfa_wildfire JOIN wildfire USING (id)
   WHERE size_km2 IS NOT NULL
   ORDER BY abs(size_km2 * 100 - ST_Area(perimeter::geography) / 10000.0) DESC
   LIMIT 20;

Which country a fire counts towards
-----------------------------------

Chosen with ``--country-source``:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Mode
     - What it does
   * - ``geometry`` *(default)*
     - Asks the database which country actually contains the fire, **at report
       time**, by testing an interior point of its perimeter against the real
       country polygons. A fire inside no country is excluded.
   * - ``reported``
     - Uses the ``admin_boundary_id`` the import stored.

The default is the cautious one, and it is the default because of datasets other
than this one.

**Here the two agree.** GFA resolves each fire's country by containment at import
time, so ``reported`` is simply the faster path — and materially so:

.. code-block:: text

   60,000 fires, 5 countries of 2,000 vertices each
     --country-source geometry    1.47 s
     --country-source reported    0.14 s     (10.7x faster)

   ~25 s per million fires -> the whole 23.3M-fire GWIS dataset ~ 10 minutes

(Indicative: real OCHA outlines are more complex than the synthetic ones measured
here, and ``ST_PointOnSurface`` on a large multipart perimeter costs more than on
a small one. The ratio is the part to trust, not the absolute.)

**Elsewhere they do not.** EGIF resolves its boundary from an INE municipal code
rather than from a coordinate, so a *parte* filed in Ourense whose published
northing is missing three digits keeps its Spanish boundary while its point sits
in the Gulf of Guinea. Under ``reported`` that fire is in Spain's total; under
``geometry`` it is in nobody's. The same applies to any dataset that states a
region administratively — which, outside the two global Atlases, is most of them.


For GFA the two can also differ for a reason that is nobody's error. ``reported``
follows the **ignition point** — that is what :doc:`the import <gfa_import_wildfires>`
resolves the country from — while ``geometry`` follows an interior point of the
**perimeter**. A fire that ignites one side of a border and burns across it is
attributed differently by the two, which makes running both a practical way to
find such fires.

.. note::

   Both modes attribute a fire's **whole** area to one country. Splitting a
   border-crossing fire between the countries it actually burnt in is a different
   and larger question, and this report does not attempt it: ``Total (ha)`` is the
   area of fires attributed to a country, not the area burnt inside its borders.

.. tip::

   Running the same report both ways is a cheap consistency check on a dataset:
   any country whose figures move is a country whose attribution and whose
   coordinates disagree.

Which fires are counted
^^^^^^^^^^^^^^^^^^^^^^^

Fires with **no country are excluded**: mid-ocean perimeters, and any fire whose ignition
point matched no OCHA boundary. Fires with no perimeter are excluded too, having no area
to contribute.

A report therefore does not necessarily account for every hectare in the database. The
totals are totals of *attributable* burnt area. If that share matters for a given run,
compare the row counts against the database:

.. code-block:: sql

   SELECT count(*), count(admin_boundary_id) FROM wildfire
   WHERE id IN (SELECT id FROM gfa_wildfire);

.. note::

   The ``Fires`` column counts exactly the fires that survived these rules, so it never
   disagrees with the areas beside it — but it is therefore a count of *attributable*
   fires, not of every fire in the database.

.. note::

   GFA attributes a fire to a country through its **ignition point**, not through a point
   on the perimeter — see :doc:`gfa_import_wildfires`. For a fire that crosses a border the
   whole burnt area is therefore counted against the country it started in. That is a
   property of the import, not of this report, and it is the same rule the local start
   time was resolved with, so the two always agree.

Which year a fire counts towards
--------------------------------

The year of its **local** start date — ``start_date_time AT TIME ZONE time_zone`` — which
is the year of the ``start_date`` GFA published, and so the year of the file the fire came
from. Reading the year off the raw UTC instant instead would move fires across the New Year
boundary: a fire starting on 1 January in Sydney is still 31 December in UTC. See
:doc:`../data_model` for why both halves are stored.

.. note::

   ``fire_ID`` also encodes the year — ``2xxxxxxx`` for 2002 through ``26xxxxxxx`` for
   2026 — so it can be used as a cross-check on the grouping, but it is not what the report
   groups by. The local start date is the fire's own date; the identifier is the file's.

Performance
-----------

The areas are computed on every run rather than stored on the row, and the filters apply
before the areas are measured, so ``--country`` or ``--year`` is faster than a whole-world
run by roughly the fraction of fires they keep.

If that ever becomes the bottleneck, the fix is the same as for the GWIS report: add an
area column to :class:`~src.data_model.wildfire.Wildfire`, fill it at import and backfill
the existing rows with a single ``UPDATE`` — no re-import needed. It would serve both
reports at once.

.. note::

   The statistics are produced by one statement. The areas are computed once in a subquery
   rather than three times in the outer aggregate, and ``GROUPING SETS`` yields the
   per-year rows and the per-country summary from that same single pass.

Built from the models, not from SQL text
----------------------------------------

The query is a SQLAlchemy Core ``select()`` over the mapped classes — see
:func:`~src.apps.statistics.wildfires.gfa.wildfire_statistics.statistics_query` — rather
than a SQL string, for the reasons set out in :doc:`gwis_wildfire_statistics`: column names
are checked at import time, and ``--country``/``--year`` stay plain conditionals instead of
becoming "unset, or matching" disjunctions that are dead on every actual run.

``gfa_wildfire`` is joined by table rather than filtered on ``wildfire.type``, so this
stays a GFA report even if another provider ever adopts the same discriminator — and
joining the table directly keeps SQLAlchemy from adding the polymorphic join of its own.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.gfa.wildfire_statistics
   :members:
   :show-inheritance:
