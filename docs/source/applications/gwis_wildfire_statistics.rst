GWIS wildfire statistics
========================

Reports the GWIS GlobFire wildfires per country and year: how many there were, and the
smallest single fire, the largest single fire and the total burnt area, in hectares.

Usage
-----

Over everything, or narrowed to one country, one year, or both:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.gwis.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.gwis.wildfire_statistics \
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

==============  ======  ========  ============  ============  =============
Country         Year       Fires  Minimum (ha)  Maximum (ha)  Total (ha)
==============  ======  ========  ============  ============  =============
World           2021      482119         21.47     229104.55   38104772.10
World           2020      461003         21.47     198441.02   33970118.44
World           Total     943122         21.47     229104.55   72074890.54
Spain           2021        1204         21.47      21985.45      91721.90
Spain           2020         876         21.47        193.30        622.93
Spain           Total       2080         21.47      21985.45      92344.83
France          2021         331         21.51       7978.39      11271.13
France          Total        331         21.51       7978.39      11271.13
==============  ======  ========  ============  ============  =============

The **World** block comes first: every country in scope, year by year and then over all
of them. It is what the rest is read against — the dataset is not "the whole planet" in
any tidy sense, and a country's figures mean little until you know the total they sit in.

.. important::

   Neither the ``World`` rows nor a country's ``Total`` row is a total of every column
   above it. ``Fires`` and ``Total (ha)`` are sums; ``Minimum`` and ``Maximum`` are the
   smallest and largest **single fire** in scope. Summing a column of minima would
   produce a number with no meaning.

.. note::

   The World block is **omitted when** ``--country`` **is given**, where it could only
   repeat that country's rows word for word.

   It also excludes exactly what the countries exclude — a fire attributable to no
   country is in no world total either — so the World row always equals the sum of the
   country rows below it. A "world" that quietly meant "every fire in the database"
   would not.

The two formats differ deliberately in one respect: the ``.csv`` writes bare numbers
(``21985.45``, ``1204``) because it is read by another program more often than by a
person, while the ``.docx`` writes them with thousands separators and right-aligned,
because it is not. In the Word document each ``Total`` row is bold, which is what
separates the country blocks visually.

.. note::

   The ``.docx`` is written with `python-docx <https://python-docx.readthedocs.io>`_, a
   pure-Python dependency with no system package behind it. It is imported inside the
   writer rather than at module scope, so ``--csv`` keeps working even where it is not
   installed.

How the area is measured
------------------------

.. code-block:: sql

   ST_Area(wildfire.perimeter::geography) / 10000.0

That is the true area on the WGS84 ellipsoid, in square metres, converted to hectares.

Deliberately **not** a projected area. Every map projection distorts something, and for a
dataset spanning every latitude from the Arctic to Tasmania there is no projection whose
distortion is negligible throughout — a fire measured in Web Mercator at 70°N comes out
roughly nine times too large. An equal-area projection would avoid that, but it would
still require choosing and defending a CRS, and the geodesic computation is at least as
accurate without one.

The result is cross-checked in the test suite against :mod:`pyproj`, which computes the
same geodesic area through PROJ rather than through PostGIS — two independent
implementations rather than a number copied out of the first run.

.. note::

   A useful sanity check on real output: the minimum comes out at about **21.47 ha**
   almost everywhere. That is exactly one MODIS pixel — GlobFire is derived from the
   500 m MCD64A1 burned-area product, whose cells are 463.31 m on a side — so it is the
   dataset's own floor showing through, not an artefact of the measurement.

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

**Here the two agree.** GWIS resolves each fire's country by containment at import
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

.. note::

   Both modes attribute a fire's **whole** area to one country. Splitting a
   border-crossing fire between the countries it actually burnt in is a different
   and larger question, and this report does not attempt it: ``Total (ha)`` is the
   area of fires attributed to a country, not the area burnt inside its borders.

.. tip::

   Running the same report both ways is a cheap consistency check on a dataset:
   any country whose figures move is a country whose attribution and whose
   coordinates disagree.

.. warning::

   **``equal-area`` is wrong for a perimeter that crosses the antimeridian**, and
   ``geodesic`` is not. ``ST_Transform`` is a planar operation, and a ring running from
   +179.99 to -179.99 is planar nonsense: the 150 ha fire ``210709771`` comes out of
   EPSG:6933 at 368,913 ha. ``ST_Area(::geography)`` reads the same ring correctly.

   58 GFA fires and an unknown number of GWIS ones are affected. It is the reason
   ``geodesic`` is the default, beyond the tidier one given above — so unless you have a
   specific need for the projected figure, leave it alone.

Which fires are counted
^^^^^^^^^^^^^^^^^^^^^^^

Fires with **no country are excluded**: mid-ocean perimeters, and any fire whose interior
point matched no OCHA boundary. Fires with no perimeter are excluded too, having no area
to contribute.

A report therefore does not necessarily account for every hectare in the database. The
totals are totals of *attributable* burnt area. If that share matters for a given run,
compare the row counts against the database:

.. code-block:: sql

   SELECT count(*), count(admin_boundary_id) FROM wildfire;

.. note::

   The ``Fires`` column counts exactly the fires that survived these rules, so it never
   disagrees with the areas beside it — but it is therefore a count of *attributable*
   fires, not of every fire in the database.

Which year a fire counts towards
--------------------------------

The year of its **local** start date — ``start_date_time AT TIME ZONE time_zone`` — which
is the year of the ``IDate`` GWIS published, and so the year of the file the fire came
from. Reading the year off the raw UTC instant instead would move fires across the New
Year boundary: a fire starting on 1 January in Sydney is still 31 December in UTC. See
:doc:`../data_model` for why both halves are stored.

Performance
-----------

The areas are computed on every run rather than stored on the row. Measured on the
published 2021 file — 929,486 fires — the geodesic area of every perimeter takes about
**3 seconds**, so the whole 23.3 million-fire dataset is on the order of 80 seconds.
Narrowing with ``--country`` or ``--year`` is faster still, since the filter applies
before the areas are measured.

If that ever becomes the bottleneck, the fix is to add an area column to
:class:`~src.data_model.wildfire.Wildfire`, fill it at import and backfill the existing
rows with a single ``UPDATE`` — no re-import needed.

.. note::

   The statistics are produced by one statement. The areas are computed once in a
   subquery rather than three times in the outer aggregate, and ``GROUPING SETS`` yields
   the per-year rows and the per-country summary from that same single pass.

Built from the models, not from SQL text
----------------------------------------

The query is a SQLAlchemy Core ``select()`` over the mapped classes — see
:func:`~src.apps.statistics.wildfires.gwis.wildfire_statistics.statistics_query` — rather
than a SQL string, which is worth stating because the *import* applications are the
opposite way round.

They have to be: a bulk import needs data-modifying CTEs, ``nextval`` on a sequence,
``ON CONFLICT``, and a single statement writing both halves of a joined-inheritance row.
None of that is expressible through the ORM, and routing 23 million perimeters through
Python objects would defeat the point of the staging-table design entirely.

A read-only aggregate has no such constraint, and building it from the models buys two
things:

* **Column names are checked.** Renaming a column on a model breaks this query when the
  module is imported, not when a user runs a report.
* **The filters are plain conditionals.** ``--country`` and ``--year`` are added with
  ``if`` statements, so an unfiltered run emits no filter at all. Written as text, each
  would have to become an "unset, or matching" disjunction — ``CAST(:country AS text) IS
  NULL OR ...`` — so that one statement could serve every combination, leaving branches
  in the SQL that are dead on every actual run.

The three constructs that might look like they need raw SQL do not:
``ST_Area`` over a geography cast comes from GeoAlchemy2, ``AT TIME ZONE`` is applied with
``.op()``, and ``GROUPING SETS``/``GROUPING()`` are ``func.grouping_sets`` and
``func.grouping``.


Progress
--------

The report is one ``SELECT``, so there is no n-of-m to show: PostgreSQL does not report
partial progress on an aggregate, and inventing a percentage would be a fiction. What is
shown instead is that the process is alive and how long it has been going.

On a terminal, one line rewritten in place:

.. code-block:: text

   \ Measuring the burnt area of the GWIS fires (every country)... 0:02:47

Redirected to a file, or below ``INFO``, the same thing as two ordinary log records and
no control characters at all:

.. code-block:: text

   14:22:01 INFO Measuring the burnt area of the GWIS fires (every country)...
   14:24:48 INFO Measuring the burnt area of the GWIS fires (every country): done in 167s

A run that fails says ``failed after 167s`` rather than ``done in``: knowing it worked
for three minutes before falling over is worth as much as knowing it finished.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.gwis.wildfire_statistics
   :members:
   :show-inheritance:
