Database migrations (Alembic)
=============================

.. contents::
   :local:
   :depth: 2

Overview
--------

The database schema is defined by the SQLAlchemy models in ``src/data_model/``, but a
real database that already holds data cannot simply be rebuilt from them: it has to be
*migrated* from the shape it has to the shape the models describe.
`Alembic <https://alembic.sqlalchemy.org>`_ handles that. Each schema change is a
**revision** — a small Python file with an ``upgrade()`` and a ``downgrade()`` — and the
revisions form a chain the database walks along.

Alembic records which revision a database is at in an ``alembic_version`` table, so
upgrading is idempotent: applying the same revision twice is a no-op.

.. note::

   The test suite does **not** use the migrations: ``test/conftest.py`` builds the schema
   straight from the models with ``Base.metadata.create_all()`` because it is faster and
   the ephemeral database starts empty every time. The migrations are exercised
   separately by ``test/test_migrations.py``, which upgrades a real ephemeral database
   and asserts the result matches ``Base.metadata`` — see :ref:`migrations-drift`.

Layout
------

``alembic.ini``
    Alembic's configuration. It deliberately contains **no** ``sqlalchemy.url``: the URL
    is built at run time from the ``GISFIRE_DB_*`` environment variables, so no
    credentials live in a tracked file. See :doc:`configuration`.

``alembic/env.py``
    Wires Alembic to the project: sets the URL from :func:`src.settings.database_url`
    (unless the caller supplied one), points autogenerate at
    :attr:`src.data_model.Base.metadata`, and installs GeoAlchemy2's ``alembic_helpers``
    so PostGIS is handled correctly.

``alembic/versions/``
    The revision files, named with a UTC timestamp prefix so they sort chronologically.

Everyday use
------------

All commands act on the database configured in your ``.env``. The ``Makefile`` wraps
the common ones:

.. code-block:: bash

   make migrate                      # upgrade the database to the latest revision
   make migration M="add fire cause" # autogenerate a revision from model changes
   make migrate-down                 # undo the last revision
   make migrate-history              # show the revision chain and where the DB stands
   make migrate-sql                  # print the SQL instead of applying it

or use Alembic directly for anything else::

   .venv/bin/alembic upgrade head
   .venv/bin/alembic downgrade -1
   .venv/bin/alembic current

Adding a schema change
----------------------

#. Change the model in ``src/data_model/`` (and make sure it is imported in
   ``src/data_model/__init__.py``, or its table will not be in ``Base.metadata`` and
   autogenerate will not see it).
#. Run ``make migration M="short description"``. Alembic compares the models against
   the current database and writes a revision with the difference.
#. **Read the generated file.** Autogenerate is a starting point, not an oracle.
#. Apply it with ``make migrate``, and check ``downgrade()`` works too.
#. Commit the model change and its revision together.

.. warning::

   Autogenerate compares *structures*, so it cannot see intent. It renders a renamed
   column as a drop plus an add — which silently destroys the data in it — and it does
   not detect renamed tables, ``CREATE EXTENSION``, or any data migration. Those must be
   written by hand, using ``op.alter_column(..., new_column_name=...)``,
   ``op.rename_table()`` or ``op.execute()``.

PostGIS
-------

Two details make PostGIS work with Alembic, both already handled in ``alembic/env.py``:

- GeoAlchemy2's ``alembic_helpers.include_object`` filters out the objects PostGIS
  manages itself (``spatial_ref_sys``, the ``geometry_columns`` view, ...). Without it
  autogenerate would see them as tables the models do not define and generate a
  revision that drops them.
- ``alembic_helpers.render_item`` and ``alembic_helpers.writer`` make the generated
  scripts use the geospatial operations (``op.create_geospatial_table()``,
  ``op.create_geospatial_index()``) and the ``geoalchemy2`` column types, so spatial
  indexes are created and dropped along with their tables.

The extension itself is created by the initial revision, which runs
``CREATE EXTENSION IF NOT EXISTS postgis`` before any geometry column. Its
``downgrade()`` does not drop the extension: other schemas in the same database may
depend on it.

.. _migrations-views:

Views
-----

Each dataset is stored across two tables — the generic ``wildfire`` or ``ignition`` row
and the provider's own columns beside it (joined table inheritance, see
:doc:`../providers`). That is right for the model and wrong for QGIS, which wants one
relation with everything on it. So the schema also carries a **view per dataset**,
flattening the two tables and resolving the foreign keys to names:

==============================================  ==========================================  =======================
View                                            Flattens                                    Geometry
==============================================  ==========================================  =======================
``v_gwis_wildfire``                             ``wildfire`` + ``gwis_wildfire``            ``MULTIPOLYGON``, 4326
``v_gfa_wildfire``                              ``wildfire`` + ``gfa_wildfire``             ``MULTIPOLYGON``, 4326
``v_gfa_ignition``                              ``ignition`` + ``gfa_ignition``             ``POINT``, 4326
``v_icnf_wildfire_4326``                        ``wildfire`` + ``icnf_wildfire``            ``MULTIPOLYGON``, 4326
``v_icnf_wildfire_3763``                        ``wildfire`` + ``icnf_wildfire``            ``MULTIPOLYGON``, 3763
``v_egif_ignition``                             ``ignition`` + ``egif_ignition``            ``POINT``, 4326
``v_egif_wildfire``                             ``wildfire`` + ``egif_wildfire``            ``POINT``, 4326
``v_darpa_wildfire_4326``                       ``wildfire`` + ``darpa_wildfire``           ``MULTIPOLYGON``, 4326
``v_darpa_wildfire_25831``                      ``wildfire`` + ``darpa_wildfire``           ``MULTIPOLYGON``, 25831
``v_rediam_wildfire_4326``                      ``wildfire`` + ``rediam_wildfire``          ``MULTIPOLYGON``, 4326
``v_rediam_wildfire_25830``                     ``wildfire`` + ``rediam_wildfire``          ``MULTIPOLYGON``, 25830
``v_rediam_ignition``                           ``ignition`` + ``rediam_ignition``          ``POINT``, 4326
``v_greece_ffa_ignition``                       ``ignition`` + ``greece_ffa_ignition``      ``POINT``, 4326
``v_greece_ffa_wildfire``                       ``wildfire`` + ``greece_ffa_wildfire``      ``POINT``, 4326
``v_nbac_wildfire_4326``                        ``wildfire`` + ``nbac_wildfire``            ``MULTIPOLYGON``, 4326
``v_nbac_wildfire_3978``                        ``wildfire`` + ``nbac_wildfire``            ``MULTIPOLYGON``, 3978
``v_nfdb_ignition``                             ``ignition`` + ``nfdb_ignition``            ``POINT``, 4326
``v_nfdb_wildfire``                             ``wildfire`` + ``nfdb_wildfire``            ``POINT``, 4326
``v_wod_wildfire``                              ``wildfire`` + ``wod_wildfire``             ``MULTIPOLYGON``, 4326
``v_wod_wildfire_2193``                         ``wildfire`` + ``wod_wildfire``             ``MULTIPOLYGON``, 2193
``v_wod_ignition``                              ``ignition`` + ``wod_*`` (four tables)      ``POINT``, 4326
``v_wod_ignition_2193``                         ``ignition`` + ``wod_*`` (four tables)      ``POINT``, 2193
``v_meteocat_lightning_4326``                   ``lightning`` + ``meteocat_lightning``      ``POINT``, 4326
``v_meteocat_lightning_4258``                   ``lightning`` + ``meteocat_lightning``      ``POINT``, 4258
``v_meteocat_lightning_25831``                  ``lightning`` + ``meteocat_lightning``      ``POINT``, 25831
``v_thunderstorm``                              ``thunderstorm`` + run                      ``POLYGON``, 4326
``v_thunderstorm_25831``                        ``thunderstorm`` + run                      ``POLYGON``, 25831
``v_thunderstorm_convex_hull``                  ``thunderstorm`` + run                      ``POLYGON``, 4326
``v_thunderstorm_convex_hull_25831``            ``thunderstorm`` + run                      ``POLYGON``, 25831
``v_thunderstorm_evolution``                    ``thunderstorm_evolution`` + run            ``POINT``, 4326
``v_thunderstorm_evolution_25831``              ``thunderstorm_evolution`` + run            ``POINT``, 25831
``v_thunderstorm_evolution_hull``               ``thunderstorm_evolution`` + run            ``POLYGON``, 4326
``v_thunderstorm_evolution_hull_25831``         ``thunderstorm_evolution`` + run            ``POLYGON``, 25831
``v_thunderstorm_evolution_convex_hull``        ``thunderstorm_evolution`` + run            ``POLYGON``, 4326
``v_thunderstorm_evolution_convex_hull_25831``  ``thunderstorm_evolution`` + run            ``POLYGON``, 25831
``v_thunderstorm_vector``                       ``thunderstorm_evolution`` + run            ``LINESTRING``, 4326
``v_thunderstorm_vector_25831``                 ``thunderstorm_evolution`` + run            ``LINESTRING``, 25831
``v_thunderstorm_path``                         ``thunderstorm_evolution`` + run            ``LINESTRING``, 4326
``v_thunderstorm_path_25831``                   ``thunderstorm_evolution`` + run            ``LINESTRING``, 25831
``v_thunderstorm_cellsearch_centre``            ``thunderstorm_cellsearch_flash`` + run     ``POINT``, 4326
``v_thunderstorm_cellsearch_centre_25831``      ``thunderstorm_cellsearch_flash`` + run     ``POINT``, 25831
``v_thunderstorm_cellsearch_path``              ``thunderstorm_cellsearch_flash`` + run     ``LINESTRING``, 4326
``v_thunderstorm_cellsearch_path_25831``        ``thunderstorm_cellsearch_flash`` + run     ``LINESTRING``, 25831
==============================================  ==========================================  =======================

Portugal, Catalonia, Andalusia and Canada each appear twice, because a QGIS layer takes a
single geometry column and all four datasets have two perimeters: the one the provider
publishes on its own national or regional grid — EPSG:3763 (ETRS89 / PT-TM06) on
``icnf_wildfire``, EPSG:25831 (ETRS89 / UTM 31N) on ``darpa_wildfire``, EPSG:25830 (UTM
30N) on ``rediam_wildfire``, EPSG:3978 (NAD83 / Canada Atlas Lambert) on ``nbac_wildfire``
— and the EPSG:4326 one the import reprojects onto ``wildfire``. All eight views name it
``perimeter``, so a style or an expression written against one works on the others.

.. note::

   ``v_rediam_wildfire_25830`` is **25830 and not the 3042** the published ``.prj``
   resolves to. They are the same projection; 3042 declares a northing-easting axis order
   that the published coordinates do not follow. See :doc:`../providers`.

``v_darpa_wildfire_*`` and ``v_rediam_wildfire_*`` also carry ``egif_report_number``,
resolved through their ``egif_wildfire_id``. Nothing fills that link in for either
dataset yet — see :doc:`../providers` — so today the column is NULL on every row. It is in
the views because the layer that will show whether the binding worked should not need a
migration first.

``v_rediam_ignition`` is the third ignition view. It exists because 201 Andalusian fires
publish a start point as well as a perimeter, and the two frequently disagree: a single
layer cannot show both geometries, and a fire's point is not an attribute of its polygon.

The perimeter views carry the same point as ``ignition_x`` / ``ignition_y``, which is what
makes it visible in an attribute table.

``v_greece_ffa_ignition`` is the fourth, on the same argument: the Greek Fire Service
publishes a point for its last six years. ``v_nfdb_ignition`` is the fifth, and the first
whose provider table carries a **projected copy of the point** as well — the Canadian
agencies publish metres on a national grid, so the EPSG:4326 geometry is a reprojection
rather than the published pair.

.. warning::

   ``v_greece_ffa_wildfire`` is the second wildfire view with a ``POINT`` geometry, after
   ``v_egif_wildfire`` and for the same reason — neither service publishes a perimeter —
   and it is the one view in the schema that shows a **minority** of its own dataset.
   The join to the ignition is an inner one, and only 54,491 of the 260,194 Greek fires
   have a point: no year before 2020 publishes a coordinate at all.

   So the layer is the mappable fifth of the dataset, and a feature count taken from it
   is not a count of Greek fires. Anything counting fires reads ``greece_ffa_wildfire``.
   A ``LEFT JOIN`` was the alternative and is worse for the one job a view has here: it
   would hand QGIS 205,703 features that render as nothing and select as nothing.

``v_nfdb_wildfire`` is the third such view and takes the **opposite** decision: it
``LEFT JOIN``\ s its ignition. The Greek inner join hides four fires in five, which is a
structural property of that archive; here the coordinate is the point of the dataset and
only a handful of rows lack a usable one, so dropping them would hide a defect rather than
depict an absence. A NULL geometry in QGIS is a feature that does not draw, which is the
correct depiction of a fire report with no usable location.

New Zealand's WOD gets a pair per spatial table, EPSG:4326 and the NZTM2000 grid
(EPSG:2193) it publishes on. ``v_wod_wildfire*`` hold **every** record, the point records
with a NULL ``perimeter`` — a feature that does not draw — so the layer's feature count is
the dataset's; ``has_perimeter`` selects the ones that draw. ``v_wod_ignition*`` join the
point to its record **and to all of** ``wod_terrain`` **and** ``wod_weather``, which makes
them the layer for fire-environment analysis, and also means they block
``ALTER COLUMN ... TYPE`` on every terrain and weather column.

MeteoCat's lightning strokes get **three** views of the same rows, one per CRS:
EPSG:4326 for a layer beside every other dataset, the ETRS89 point as published
(EPSG:4258), and ETRS89 / UTM 31N (EPSG:25831), the grid Catalonia measures and draws on.
All three name the column ``geometry``. The 25831 one is the only view in the schema
whose geometry is **computed** rather than selected — the UTM point is not stored — so it
breaks the rule above in the one way the rule allows: it reprojects the ETRS89 point and
casts the result back to ``geometry(Point,25831)``, which keeps the type modifier. A
reprojection in a view also defeats the spatial index, and over six million points every
QGIS pan would be a sequential scan, so ``meteocat_lightning`` carries an **expression
index**, ``idx_meteocat_lightning_geometry_25831``, on exactly the view's expression,
declared on the model and created by revision ``5b7e2c9d4a13``. The two must stay the
same expression for the planner to use it, and ``test/test_migrations.py`` checks that it
does. There is no ``date_time_local``: the XDDE publishes UTC, so the published reading
is ``date_time``.

Thunderstorms get **eighteen** views: nine layers, each in EPSG:4326 and in ETRS89 /
UTM 31N (EPSG:25831), the grid of the only lightning provider so far. "Run" in the table
is the experiment — and, for the window layers, the tracking — the rows belong to; see
:doc:`../data_model/thunderstorm`. A view takes one geometry, so the concave and the
convex hull of a storm are two layers, and so are a window's centre and its hulls:

- ``v_thunderstorm`` — each storm's concave hull, with its duration and strokes per
  minute (counting at least one minute) and, from revision ``e7147a41b62b``, its
  ``number_of_flashes``, ``area_km2`` and ``density_per_100km2`` (100 · flashes / area,
  as Tuomi & Larjavaara report it; all three NULL for a stroke-based algorithm or an
  undefined area); ``v_thunderstorm_convex_hull`` — the same rows with ``ST_ConvexHull``
  of that hull, which is the convex hull of the points it was drawn from.
- ``v_thunderstorm_evolution`` — each window's gravity centre, stamped at the window's
  **midpoint**, with the **direction vector** that brought the storm there: computed with
  ``LAG()`` over the window sequence on the WGS 84 spheroid — ``displacement_m``,
  ``bearing_deg`` (0 = north, clockwise), ``elapsed_s``, ``speed_m_s`` and the east and
  north components ``u_m_s`` / ``v_m_s``. The first window has none; a centre that did
  not move has a velocity of zero. ``v_thunderstorm_evolution_hull`` and
  ``…_convex_hull`` are the window hulls.
- ``v_thunderstorm_vector`` — each vector as a segment from the previous centre, to draw
  with an arrow; its ``id`` is that of the window at the arrow's head.
- ``v_thunderstorm_path`` — one line per tracking and storm through its centres, with
  total and net distance, mean speed, mean *u*/*v* and the bearing of the mean velocity.
  A storm seen in a single window has no path; the ``id`` is that of its first window.
- ``v_thunderstorm_cellsearch_centre`` — for a Cellsearch run, one point per flash of a
  kept cell: the cell's running centre right after it (the article's Fig. 8), with its
  ``sequence``, the representative stroke and its instant.
- ``v_thunderstorm_cellsearch_path`` — one line per Cellsearch cell through those
  centres in sequence, with the article's statistics computed from the **flashes**:
  ``lifetime_min`` (last − first flash), ``flash_rate_per_min`` (NULL for a lifetime of
  zero), ``area_km2``, ``density_per_100km2``, and the geodesic ``path_length_m`` and
  ``net_displacement_m``. Its ``id`` is the cell's. ``duration_s`` on ``v_thunderstorm``
  spans all the linked strokes, so it can exceed ``lifetime_min`` by the span of a
  merged flash.

They show **complete runs only**: a run being built, or one that failed, is half a
result. Only the stored 4326 hulls and centres are selected straight from a table; every
other geometry is computed and cast back to ``geometry(<type>,<srid>)``, so all eighteen
register in ``geometry_columns``. None is backed by an expression index: a run is of the
order of 60,000 storms and 600,000 windows, not six million strokes. The exception in
size is ``v_thunderstorm_cellsearch_centre``, one row per kept flash, which over the
whole archive is of the order of the strokes: its 4326 layer selects the stored centre,
which has a GiST index, while the ``_25831`` one reprojects it and has none, so over a
long run filter it on ``experiment_id`` and a time span, or use the 4326 layer. Nothing
they show is stored, so nothing in them can go stale — ``test/test_migrations.py`` checks their
distances and bearings against an independent geodesic computation.

``v_egif_wildfire`` is the odd one out: a wildfire view whose geometry is a ``POINT``.
EGIF publishes no perimeter at all — see :doc:`../providers` — so a ``perimeter`` column
would be a layer of NULLs, and the useful layer is the fire's attributes mapped at the
point it started. The view therefore joins through to ``egif_ignition`` and exposes that
point. It also carries ``has_full_report``, which says whether the fire has been read
from the XML export as well as the Excel one.

The views are read-only, add no storage and no constraints, and every wildfire and
ignition datetime comes with a ``*_local`` companion giving the reading as the provider
published it. Lightning and thunderstorm instants have none: the networks publish UTC.

Writing them
^^^^^^^^^^^^

Alembic has no view construct: it diffs tables and columns, and a view has no diffable
state — it is a definition that is either there or not. So the project uses the
cookbook's `replaceable objects
<https://alembic.sqlalchemy.org/en/latest/cookbook.html#replaceable-objects>`_ recipe,
implemented in :doc:`../data_model/replaceable`. A view is a
:class:`~src.data_model.replaceable.ReplaceableObject`, and a revision gets
``op.create_view()``, ``op.drop_view()`` and ``op.replace_view()``:

.. code-block:: python

   from src.data_model.replaceable import ReplaceableObject

   my_view = ReplaceableObject("v_something", "SELECT ...")

   def upgrade() -> None:
       op.create_view(my_view)

   def downgrade() -> None:
       op.drop_view(my_view)

To change an existing view, write the new definition in a **new** revision and point it
at the old one by ``<revision>.<variable name>``; the downgrade is the mirror image:

.. code-block:: python

   def upgrade() -> None:
       op.replace_view(my_view, replaces="e4b7c1a90f3d.gwis_wildfire_view")

   def downgrade() -> None:
       op.replace_view(my_view, replace_with="e4b7c1a90f3d.gwis_wildfire_view")

Every revision therefore keeps its **own copy** of the SQL, rather than importing a
shared definition that later edits would change underneath it. A migration has to stay a
faithful snapshot of the schema as it was, or downgrading a database that has been
sitting at an old revision stops working.

.. note::

   Autogenerate never sees views — Alembic reflects tables only. That means it will not
   propose creating or updating one (they are written by hand), but also that a view can
   never turn into a spurious ``drop_table`` in a generated revision, and that
   ``test_migrations_match_the_models`` keeps passing with the views in place.

.. warning::

   PostgreSQL records a dependency from a view to every column it selects, so while a
   view exists, ``ALTER COLUMN ... TYPE`` or ``DROP COLUMN`` on one of those columns
   **fails**. A revision that changes such a column has to ``op.drop_view()`` first and
   ``op.create_view()`` again at the end — which is the reason the definitions are worth
   keeping tidy and in one file per revision.

What makes them work in QGIS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Four properties, all asserted by ``test/test_migrations.py`` so a future edit cannot
quietly break a layer:

``id`` is the parent's integer primary key
    QGIS cannot infer a key for a view and needs a unique integer column to identify
    features with.

The geometry column is selected straight from its table
    Never wrapped in a function. That preserves the type modifier
    (``geometry(MultiPolygon,4326)``), which is what registers the view in PostGIS's
    ``geometry_columns`` and lets QGIS detect geometry type and SRID on its own. A
    wrapped expression such as ``ST_Transform(perimeter, 3763)`` returns an untyped
    ``geometry``: the layer still loads, but the user has to fill in type and SRID by
    hand. Cast it back — ``::geometry(MultiPolygon,3763)`` — if a transform is ever
    genuinely needed.

One geometry per view
    Hence the two Portugal views.

Foreign keys come with their names
    ``data_provider_name``, ``admin_boundary_name`` and the ICNF cause columns, so the
    attribute table reads as text instead of integers. Both lookups are ``LEFT JOIN``\ s:
    a fire whose boundary was never resolved must not vanish from the view.

Loading a view in QGIS is the same as loading a table (*Add PostGIS Layers*); pick ``id``
as the feature id if the browser asks. If the perimeter tables grow to the point where
the join costs real time, the next step is a materialised view with its own GiST index
and a refresh in the importers — not built, and not worth building until something is
measurably slow.

.. _migrations-drift:

Keeping migrations and models in sync
-------------------------------------

The failure mode this setup is most exposed to is changing a model and forgetting to
generate the revision that goes with it: the tests keep passing, because they build the
schema from the models, while the real database silently falls behind.

``test/test_migrations.py`` closes that gap. It upgrades an ephemeral PostgreSQL to
``head`` and then asks Alembic to diff the result against ``Base.metadata``, failing if
there is any difference. If it fails, the fix is nearly always to run
``make migration M="..."`` and commit the result.

It also checks that ``upgrade head`` builds the schema from empty and that
``downgrade base`` removes it again, so the ``downgrade()`` paths do not rot unnoticed.
