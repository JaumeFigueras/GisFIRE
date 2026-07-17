QGIS Plugins
============

.. contents::
   :local:
   :depth: 1

Overview
--------

GisFIRE ships a **suite of independent QGIS v4 plugins**, not a single plugin. They live
under ``qgis_plugins/`` — a container directory (not a Python package) where each
subfolder is one self-contained, deployable plugin with its own ``metadata.txt`` and
``classFactory`` entry point, imported by QGIS as a top-level package named after the
folder.

Plugins
-------

.. list-table::
   :header-rows: 1
   :widths: 34 40 26

   * - Plugin
     - Purpose
     - Package
   * - **GISFire Thunderstorm**
     - Thunderstorm detection and clustering for wildfire risk analysis.
     - ``gisfire_thunderstorm``
   * - **GISFire Minimum Geometric Cover**
     - Minimum geometric cover computation for wildfire resource coverage.
     - ``gisfire_minimum_geometric_cover``
   * - **GISFire Helicopter Routes**
     - Helicopter route planning for wildfire operations.
     - ``gisfire_helicopter_routes``

Runtime and dependencies
------------------------

The plugins run inside QGIS's own Python interpreter (Qt6 / PyQt6) and are developed and
tested from the QGIS virtual environment (see
:doc:`setup/development_environment`). They communicate with the backend exclusively over
its HTTP API using ``requests`` and do not import the server or data-model packages, so
the QGIS environment stays free of SQLAlchemy, FastAPI and psycopg.

Testing
-------

Each plugin has its own tests under ``qgis_plugins/test/<package>/``. Run them with
``make test-qgis`` (or ``make test-qgis-full`` for verbose output and an HTML coverage
report); see :doc:`testing`.

.. note::

   Per-plugin reference pages are added as the plugins are built out.
