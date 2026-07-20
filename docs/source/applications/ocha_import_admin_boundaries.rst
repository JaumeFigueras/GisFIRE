Import OCHA administrative boundaries
=====================================

Imports the OCHA *Global International Boundaries (OSM)* GeoPackage into
:class:`~src.providers.ocha.admin_boundary.OchaAdminBoundary` rows, as administrative
level 0. See :doc:`../providers` for the dataset and the quirks of its fields.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ocha.import_admin_boundaries -g adm0_polygons.gpkg

Database settings are read from the environment (``.env``, see :doc:`../setup/configuration`)
and each can be overridden on the command line — ``--db-host``, ``--db-port``,
``--db-name``, ``--db-user``, ``--db-password`` — which is how you import into a database
other than the configured one without editing ``.env``:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ocha.import_admin_boundaries \
       -g adm0_polygons.gpkg --db-name gisfire_staging

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

How it works
------------

The import runs in two stages:

1. ``ogr2ogr`` copies the GeoPackage layer verbatim into a staging table, promoting
   geometries to ``MULTIPOLYGON`` and forcing EPSG:4326.
2. One SQL statement maps the staging table onto the two tables of the model, then the
   staging table is dropped.

Splitting it this way leaves everything GDAL does better than we would — GeoPackage
parsing, polygon promotion, coordinate transformation, invalid geometries — to GDAL, and
reduces what the project maintains to column-to-column SQL.

Why not ogr2ogr alone
^^^^^^^^^^^^^^^^^^^^^

``ogr2ogr`` can rename columns, add constants and transform geometries, so it is a fair
question. It cannot do the last step: joined table inheritance splits one feature across
``admin_boundary`` and ``ocha_admin_boundary``, which share a primary key the database
only assigns on insert. ``ogr2ogr`` writes one table, and has no way to thread a
generated ``SERIAL`` value from one insert into another.

The mapping statement solves that with a data-modifying CTE. The inner insert returns
the ids it generated alongside ``source_id``; the outer insert joins on ``source_id`` —
safe, because it is unique per provider — to attach each child row to its parent.

The staging schema
^^^^^^^^^^^^^^^^^^

The staging table is created in a ``staging`` schema, not in ``public``, and this is
deliberate.

.. warning::

   A staging table in ``public`` is visible to Alembic autogenerate, which would see a
   table that is in the database but not in the models and write a ``DROP TABLE`` for it
   into the next migration. ``alembic/env.py`` does not set ``include_schemas``, so
   autogenerate inspects only the default schema and a separate one sidesteps the problem
   entirely.

Pass ``--keep-staging`` to leave the table behind and inspect what was actually loaded;
``--staging-schema`` and ``--staging-table`` change where it goes.

Re-running the import
^^^^^^^^^^^^^^^^^^^^^

Safe: the mapping statement uses ``ON CONFLICT (data_provider_id, source_id) DO NOTHING``,
so a second run imports nothing and reports ``0``. That also keeps the two inserts
consistent — a conflicting row is not returned by the CTE, so no orphan child row is
written for it.

Updating to a newer release of the dataset is a different matter, and is *not* handled:
because ``adm0_id`` carries the release date, a new release has entirely new identifiers
and its features would be imported alongside the old ones rather than replacing them.

The data provider
^^^^^^^^^^^^^^^^^

The application creates the :class:`~src.data_model.data_provider.DataProvider` row on
first run and reuses it afterwards, looked up by the ``(name, product)`` pair:

==============  =========================================================
Name            ``OCHA``
Full name       United Nations Office for the Coordination of Humanitarian Affairs
Product         ``Global International Boundaries - OSM``
==============  =========================================================

API reference
-------------

.. automodule:: src.apps.imports.admin_boundaries.ocha.import_admin_boundaries
   :members:
   :show-inheritance:
