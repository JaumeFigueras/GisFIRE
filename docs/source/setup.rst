Setup
=====

.. contents::
   :local:
   :depth: 2

Overview
--------

GisFIRE integrates several components that must be configured before use: a Python
environment for the backend and algorithms, a second environment for the QGIS plugins,
a PostgreSQL/PostGIS database, and the Sphinx documentation system. This page gives an
overview and explains the ``Makefile`` that ties the common tasks together.

Two isolated environments
-------------------------

GisFIRE deliberately uses **two separate virtual environments**, because the QGIS
plugins can only run inside QGIS's own Python interpreter (the ``qgis`` module and Qt6
cannot be installed with ``pip``). This is structural, not a preference.

- **Project virtual environment** (``.venv``, a plain ``python3 -m venv``): the data
  model, the FastAPI backend, the algorithms and their tests. Installs
  ``requirements/dev.txt`` (which pulls in ``requirements/base.txt``). It never imports
  ``qgis`` or PyQt6.
- **QGIS virtual environment** (created with ``--system-site-packages`` so it inherits
  QGIS's Qt6/PyQt6 and the ``qgis`` module): the QGIS v4 plugins. Installs
  ``requirements/qgis-dev.txt`` (which pulls in ``requirements/qgis.txt``).

The two dependency sets do not overlap, so neither environment pollutes the other.
See :doc:`setup/development_environment` for step-by-step instructions (including the
dedicated QGIS user profile).

The Makefile
------------

A top-level ``Makefile`` wraps the recurring developer tasks so the two environments do
not have to be juggled by hand. Run ``make help`` to list the targets.

Targets
^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 24 16 60

   * - Target
     - Environment
     - Action
   * - ``make venv``
     - project
     - Create the project virtual environment (``.venv``).
   * - ``make install``
     - project
     - Install core + dev dependencies (``requirements/dev.txt``) into ``.venv``.
   * - ``make install-qgis``
     - QGIS
     - Install plugin dev dependencies (``requirements/qgis-dev.txt``) into the QGIS venv.
   * - ``make test``
     - project
     - Run the core test suite with coverage.
   * - ``make test-qgis``
     - QGIS
     - Run the QGIS plugins test suite with coverage.
   * - ``make test-all``
     - both
     - Run both suites in sequence.
   * - ``make test-full``
     - project
     - Full verbose core run with an HTML coverage report, stopping on first failure.
   * - ``make test-qgis-full``
     - QGIS
     - Full verbose plugins run with an HTML coverage report, stopping on first failure.
   * - ``make docs``
     - project
     - Build the Sphinx documentation (``docs/build/html``).
   * - ``make clean``
     - --
     - Remove coverage reports, caches and the throwaway QGIS test profile.

How it invokes each environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Coverage is **on by default**: the ``addopts`` in each ``pytest.ini`` enable
  ``--cov`` with a terminal report. The ``*-full`` targets additionally produce an HTML
  report and run extra-verbose (matching the usual manual invocation
  ``-x -v -s -vv``).
- The QGIS targets ``cd`` into ``qgis_plugins/`` so pytest auto-discovers that suite's
  ``pytest.ini`` and each plugin imports top-level, exactly as QGIS loads it.
- Because PyQGIS lives outside the standard site-packages, the QGIS targets export
  ``PYTHONPATH`` (default ``/usr/share/qgis/python``) and run Qt headless
  (``QT_QPA_PLATFORM=offscreen``). Tests are always invoked as ``python -m pytest``
  rather than the ``pytest`` script, since ``pytest`` is provided via
  system-site-packages and has no console script inside the QGIS venv.

Overridable variables
^^^^^^^^^^^^^^^^^^^^^^

Several paths can be overridden on the command line if your installation differs::

   make test-qgis QGIS_VENV=/path/to/qgis/venv
   make test-qgis QGIS_PYTHONPATH=/usr/share/qgis/python
   make test-qgis QGIS_QT_PLATFORM=offscreen

Typical first-time flow
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   make venv          # create .venv
   make install       # core + dev deps
   make install-qgis  # plugin deps into the QGIS venv
   make test-all      # run both test suites

Setup guides
------------

.. toctree::
   :maxdepth: 1

   setup/development_environment
   setup/postgresql_database
   setup/documentation
