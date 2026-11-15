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

A thunderstorm application is tested against real data too, on two days, both in the
repository.
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

**Alaska, 2019-06-30 — in the repository, always run.**
``test/fixtures/data/alaska_uswfs_regression/`` holds the Alaska network's 5,892 strokes
of 2019-06-30 11:00 to 2019-07-01 12:00 UTC, cut verbatim from the U.S. Wildland Fire
Service's release, and ``cellsearch_2019-06-30_expected.json``, frozen with
``freeze_cellsearch_2019-06-30.py`` from an empty scratch database, in EPSG:3338, and
checked in QGIS on 2026-11-15.

- **The window is 12:00 to 12:00 UTC**, 04:00 to 04:00 in Alaska. A UTC day would cut
  the afternoon storms, which peak around midnight UTC. The file also holds the hour
  before the window.
- **Through the importer.** The test loads the day with the Alaska importer's own
  command-line path, so the flashes are the importer's and the identifiers follow its
  content order. A shuffled copy of the file must give the same result.
- **Unknown errors.** The day includes a run of strokes published with a semi-major axis
  of 0: 30 flashes with no known error, which every E\ :sub:`max` must discard.
- **Edges.** The window starts quiet and ends with storms still going, the opposite of
  FMI's day.

The folder's ``README.md`` says why this day and gives the citation.

**No MeteoCat day.** MeteoCat's data is not licensed for redistribution, so no real
MeteoCat strokes are in the repository. What is MeteoCat's own is tested on synthetic
strokes, in tests that always run:

- the reader: the flash key that folds in the network version, the "newest network"
  filter, the 25831 projection;
- the importer, in ``test/apps/imports/lightnings/catalonia_meteocat/``;
- the model.

When an algorithm's output changes **on purpose**, bump ``gisfire_algorithms.__version__``
(tests check that FMI's and Alaska's references were frozen with the current version),
then rewrite both references with their freeze scripts and check the runs in QGIS.

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

Alaska data in the fixtures
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Alaska network's release is public domain ("None, these data are considered public
domain"). The U.S. Wildland Fire Service asks to be cited as the source and that any
modification be described. So real rows are committed, cut verbatim, each folder with a
``README.md`` that gives the citation, *U.S. Wildland Fire Service (USWFS), Alaska
Geographic Area: Alaska Lightning Detection Network (ALDN), public domain*, and states
the modification: a selection of rows, no value changed.

- ``test/fixtures/data/alaska_uswfs/`` — 42 rows chosen for what the import has to get
  right: the first and last rows of the release, the 255 ceilings, the ±500 kA
  saturation, strokes published twice, semi-major axes of 0, missing and contradicted
  polarities, a cloud and a ground stroke in one millisecond, multi-stroke flashes, and
  strokes beyond 180°. The tests zip them with a minimal FGDC metadata file, as the
  release ships them.
- ``test/fixtures/data/alaska_uswfs_regression/`` — the regression day above.

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
