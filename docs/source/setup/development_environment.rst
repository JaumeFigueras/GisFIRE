Development Environment
=======================

.. contents::
   :local:
   :depth: 1

Project virtual environment
---------------------------

The core project (data model, FastAPI backend, algorithms) uses a plain virtual
environment::

   make venv       # python3 -m venv .venv
   make install    # pip install -r requirements/dev.txt

This environment requires Python 3.11 or above and never contains QGIS/Qt
dependencies.

QGIS virtual environment
------------------------

The QGIS v4 plugins run inside QGIS's own Python interpreter (Qt6 / PyQt6). To develop
them without breaking a regular QGIS installation, create a dedicated environment
layered on QGIS with ``--system-site-packages`` so it inherits the ``qgis`` module and
Qt6 binding, and use a **dedicated QGIS user profile** (for example ``gisfire-dev``) for
interactive runs.

.. code-block:: bash

   sudo mkdir /opt/qgis-gisfire-dev
   sudo chown <user>:<group> /opt/qgis-gisfire-dev/
   cd /opt/qgis-gisfire-dev
   python3 -m venv ./venv --system-site-packages

Install the plugin development dependencies into it::

   make install-qgis   # pip install -r requirements/qgis-dev.txt

.. note::

   The interactive ``gisfire-dev`` QGIS profile and the plugin **tests** are
   independent. ``pytest-qgis`` runs against a throwaway, isolated QGIS profile
   (``QGIS_CUSTOM_CONFIG_PATH``), so the test suite never touches your interactive
   profile.

Dependency direction
--------------------

The plugins talk to the backend over the HTTP API (``requests``) and must not import
the server / data-model packages. This one-way, thin coupling keeps the QGIS
environment free of SQLAlchemy, FastAPI and psycopg.
