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

===========================  ==========================================  =====================
View                         Flattens                                    Geometry
===========================  ==========================================  =====================
``v_gwis_wildfire``          ``wildfire`` + ``gwis_wildfire``            ``MULTIPOLYGON``, 4326
``v_gfa_wildfire``           ``wildfire`` + ``gfa_wildfire``             ``MULTIPOLYGON``, 4326
``v_gfa_ignition``           ``ignition`` + ``gfa_ignition``             ``POINT``, 4326
``v_icnf_wildfire_4326``     ``wildfire`` + ``icnf_wildfire``            ``MULTIPOLYGON``, 4326
``v_icnf_wildfire_3763``     ``wildfire`` + ``icnf_wildfire``            ``MULTIPOLYGON``, 3763
``v_egif_ignition``          ``ignition`` + ``egif_ignition``            ``POINT``, 4326
``v_egif_wildfire``          ``wildfire`` + ``egif_wildfire``            ``POINT``, 4326
``v_darpa_wildfire_4326``    ``wildfire`` + ``darpa_wildfire``           ``MULTIPOLYGON``, 4326
``v_darpa_wildfire_25831``   ``wildfire`` + ``darpa_wildfire``           ``MULTIPOLYGON``, 25831
``v_rediam_wildfire_4326``   ``wildfire`` + ``rediam_wildfire``          ``MULTIPOLYGON``, 4326
``v_rediam_wildfire_25830``  ``wildfire`` + ``rediam_wildfire``          ``MULTIPOLYGON``, 25830
``v_rediam_ignition``        ``ignition`` + ``rediam_ignition``          ``POINT``, 4326
===========================  ==========================================  =====================

Portugal, Catalonia and Andalusia each appear twice, because a QGIS layer takes a single
geometry column and all three datasets have two perimeters: the one the provider publishes
on its own national or regional grid — EPSG:3763 (ETRS89 / PT-TM06) on ``icnf_wildfire``,
EPSG:25831 (ETRS89 / UTM 31N) on ``darpa_wildfire``, EPSG:25830 (UTM 30N) on
``rediam_wildfire`` — and the EPSG:4326 one the import reprojects onto ``wildfire``. All
six views name it ``perimeter``, so a style or an expression written against one works on
the others.

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

``v_egif_wildfire`` is the odd one out: a wildfire view whose geometry is a ``POINT``.
EGIF publishes no perimeter at all — see :doc:`../providers` — so a ``perimeter`` column
would be a layer of NULLs, and the useful layer is the fire's attributes mapped at the
point it started. The view therefore joins through to ``egif_ignition`` and exposes that
point. It also carries ``has_full_report``, which says whether the fire has been read
from the XML export as well as the Excel one.

The views are read-only, add no storage and no constraints, and every datetime comes
with a ``*_local`` companion giving the reading as the provider published it.

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
