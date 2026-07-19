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
