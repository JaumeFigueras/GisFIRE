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

A thunderstorm application is tested against real data too, on two days.
``test/apps/thunderstorms/test_build_thunderstorms.py`` runs Cellsearch over each once per
value of *C* (off, 10, 15, 25, 50, 100 and 200 min·km), and each run must give exactly the
result frozen for it, checked in QGIS: for each, the summary and every thunderstorm by
label — counts, time span, area, a digest of its flashes' times and its last centre.

**FMI, 2018-07-03 — in the repository, always run.**
``test/fixtures/data/fmi_regression/`` holds FMI's 3,178 strokes of that day and the hour
before it, cut
unchanged from a monthly file of :doc:`applications/fmi_download_lightnings`, and
``cellsearch_2018-07-03_expected.json``, frozen with
``freeze_cellsearch_2018-07-03.py`` from an empty scratch database and checked in QGIS
on 2026-11-14. The test loads the day through the FMI importer, so the strokes get their
identifiers in the importer's content order, as in gisfire_db; a further test shuffles
the file, as a second download would, and must get the same result. The folder's
``README.md`` says why this day, and how to regenerate the reference.

**MeteoCat, 2020-07-13 — kept locally.**
``test/fixtures/data/meteocat_lightning_2020-07-13.csv`` holds MeteoCat's 2,947 strokes of
that day, exported
from the database, and ``cellsearch_2020-07-13_expected.json`` what the same runs stored
in the database, checked in QGIS; since the database read its own strokes and the test
reads the export, it also shows that the fixture reproduces the database. Both files are
**not in the repository**: MeteoCat's data is not licensed for redistribution, so they
are git-ignored, and those tests are skipped (with the reason) wherever the files are
missing — in CI, for instance. Where gisfire_db is available they can be recreated: the
export script's docstring gives the ``COPY`` that writes the strokes, and the script
writes the reference. A synthetic day is still planned, for MeteoCat's format and its
"newest network" filter in a test that always runs (``TODO.md``).

When an algorithm's output changes **on purpose**, bump ``gisfire_algorithms.__version__``
(a test checks that FMI's reference was frozen with the current version), rewrite FMI's
reference with its freeze script and check it in QGIS, run MeteoCat's experiments again
with :doc:`applications/build_thunderstorms`, check them, and rewrite its reference with
``test/fixtures/data/export_cellsearch_2020-07-13.py`` (read only), giving the experiment
ids.

FMI data in the fixtures
^^^^^^^^^^^^^^^^^^^^^^^^

FMI's open data is licensed CC BY 4.0, so real FMI responses and strokes are committed,
unmodified, each folder with a ``README.md`` giving the source and the attribution —
*Finnish Meteorological Institute (FMI), open data, CC BY 4.0*:

- ``test/fixtures/data/fmi_wfs/`` — four responses of the WFS, for the downloader's tests,
  which run with no network: a minute of 17 strokes, an empty hour, and the two
  ``ExceptionReport`` answers to a bad request (an interval too long, an unknown
  parameter). The importer's tests build their monthly files from the 17 strokes, turned
  into rows by the downloader's own parser, so they also check that the importer reads
  what the downloader writes.
- ``test/fixtures/data/fmi_regression/`` — the regression day above.

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
