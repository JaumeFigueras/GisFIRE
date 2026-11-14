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
``test/providers/<provider>/`` for the provider-specific ones, ``test/apps/`` for the
applications and ``test/algorithms/`` for ``gisfire_algorithms``.

Algorithm tests
^^^^^^^^^^^^^^^

``test/algorithms/`` needs no database. Its tests also run with the QGIS virtual
environment, whose numpy is older than the project's, since the plugins will run the
same code: ``make test-algorithms-qgis`` (see :doc:`algorithms`). Coverage covers
``gisfire_algorithms`` as well as ``src``.

A thunderstorm application is tested against real data too:
``test/fixtures/data/meteocat_lightning_2020-07-13.csv`` holds MeteoCat's 2,947 strokes
of 2020-07-13, exported from the database, and
``test/apps/thunderstorms/test_build_thunderstorms.py`` runs Cellsearch over them once
per value of *C* (off, 10, 15, 25, 50, 100 and 200 min·km). Each run must give exactly
what the same run stored in the database, checked in QGIS:
``cellsearch_2020-07-13_expected.json`` holds, for each, the summary and every
thunderstorm by label — counts, time span, area, a digest of its flashes' times and its
last centre. Since the database read its own strokes and the test reads the export, it
also shows that the fixture reproduces the database.

Both files are **kept locally, not in the repository**: MeteoCat's data is not licensed
for redistribution, so they are git-ignored, and these eight tests are skipped (with the
reason) wherever the files are missing — in CI, for instance. Where gisfire_db is
available they can be recreated: the export script's docstring gives the ``COPY`` that
writes the strokes, and the script writes the reference. A synthetic day that can be
published is planned to take the regression's place in the repository.

When an algorithm's output changes **on purpose**, bump ``gisfire_algorithms.__version__``,
run the experiments again with :doc:`applications/build_thunderstorms`, check them, and
rewrite the reference with ``test/fixtures/data/export_cellsearch_2020-07-13.py``
(read only), giving the experiment ids.

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

   make test                  # core suite + coverage
   make test-algorithms-qgis  # test/algorithms with the QGIS venv
   make test-qgis             # plugin suites + coverage
   make test-all              # all three
   make test-full             # core, verbose + HTML coverage
   make test-qgis-full        # plugins, verbose + HTML coverage
