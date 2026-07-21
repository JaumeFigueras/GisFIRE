GWIS wildfire statistics
========================

Reports the burnt area of the GWIS GlobFire wildfires, per country and year: the smallest
single fire, the largest single fire and the total, in hectares.

Usage
-----

Over everything, or narrowed to one country, one year, or both:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.gwis.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.gwis.wildfire_statistics \
       --country Spain --year 2021 --csv spain_2021.csv --docx spain_2021.docx

``--country`` takes either a name (``Spain``) or an ISO 3166-1 alpha-3 code (``ESP``),
case-insensitively. At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

Output
------

Both formats carry the same table. Each country's years run newest first, closed by a
``Total`` row:

=============  ======  ============  ============  ============
Country        Year    Minimum (ha)  Maximum (ha)  Total (ha)
=============  ======  ============  ============  ============
Spain          2021           21.47      21985.45      91721.90
Spain          2020           21.47        193.30        622.93
Spain          Total          21.47      21985.45      92344.83
France         2021           21.51       7978.39      11271.13
France         Total          21.51       7978.39      11271.13
=============  ======  ============  ============  ============

.. important::

   A country's ``Total`` row is **not** a total of the column above it. Its minimum is the
   smallest fire that country has had in *any* year in scope and its maximum the largest;
   only the last column is a sum. Summing a column of minima would produce a number with
   no meaning.

The two formats differ deliberately in one respect: the ``.csv`` writes bare numbers
(``21985.45``) because it is read by another program more often than by a person, while
the ``.docx`` writes them with thousands separators and right-aligned, because it is not.
In the Word document each ``Total`` row is bold, which is what separates the country
blocks visually.

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

Which year a fire counts towards
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.gwis.wildfire_statistics
   :members:
   :show-inheritance:
