Testing
=======

.. contents::
   :local:
   :depth: 2

Overview
--------

Testing ensures the code behaves as expected, catches regressions early and documents
behaviour. GisFIRE uses `pytest <https://docs.pytest.org/en/stable/>`_ with coverage
enabled by default.

Because of the two-environment split (see :doc:`setup`), there are **two test roots**,
each with its own ``pytest.ini`` so pytest never imports the wrong environment's
dependencies at collection time:

- ``test/`` — the core suite, run in the project virtual environment with ``make test``.
- ``qgis_plugins/test/<package>/`` — the plugin suites, run in the QGIS virtual
  environment with ``make test-qgis``.

Core tests
----------

The core suite tests the data model, backend and algorithms. ``test/conftest.py`` spins
up an **ephemeral PostgreSQL instance** with ``pytest-postgresql``, enables PostGIS on
it and builds the schema with ``Base.metadata.create_all()`` — the models are the single
source of truth, so there are no hand-written SQL files to keep in sync (this is a
deliberate departure from GisFIRE2). The ``db_session`` fixture yields a SQLAlchemy
``Session`` bound to it; the database is created fresh per test, so tests are isolated
without any truncation step.

The test tree mirrors the source tree: ``test/data_model/`` for the generic models,
``test/providers/<provider>/`` for the provider-specific ones.

Migration tests
^^^^^^^^^^^^^^^

Because the suite builds its schema from the models, it would never notice a model
changed without its Alembic revision. ``test/test_migrations.py`` covers that gap: it
upgrades an ephemeral database to ``head``, diffs the result against ``Base.metadata``
and fails if they differ, and checks the ``downgrade()`` path back to ``base``. See
:doc:`setup/database_migrations`.

QGIS plugin tests
-----------------

The plugin suites use `pytest-qgis <https://pypi.org/project/pytest-qgis/>`_, which boots
a headless ``QgsApplication`` and provides fixtures such as ``qgis_app`` and
``qgis_iface``, together with `pytest-qt <https://pytest-qt.readthedocs.io>`_ and its
``qtbot`` fixture for driving Qt6 dialogs and widgets. The QGIS targets run Qt headless
and point ``QGIS_CUSTOM_CONFIG_PATH`` at a throwaway profile, so tests never touch an
interactive QGIS profile.

Coverage
--------

Coverage is enabled by default through the ``addopts`` in each ``pytest.ini`` (terminal
report). The ``make test-full`` and ``make test-qgis-full`` targets additionally write an
HTML report under the corresponding ``test/coverage_reports`` directory and run
extra-verbose, stopping on the first failure.

Running the tests
-----------------

.. code-block:: bash

   make test            # core suite + coverage
   make test-qgis       # plugin suites + coverage
   make test-all        # both
   make test-full       # core, verbose + HTML coverage
   make test-qgis-full  # plugins, verbose + HTML coverage
