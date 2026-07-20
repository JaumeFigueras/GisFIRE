Applications
============

.. contents::
   :local:
   :depth: 1

Overview
--------

GisFIRE provides several command-line applications that support its data and analysis
tasks — for example importing provider data, running clustering and generating analysis
outputs. They are argparse-based scripts run as modules::

   python3 -m src.apps.<...>

Applications are grouped by purpose. Domain applications (data import and analysis) are
documented here; database/DDL helper tools have their own section
(:doc:`auxiliary_applications`).

Import applications are grouped by the kind of data they bring in and then by source,
under ``src/apps/imports/``::

   src/apps/imports/admin_boundaries/ocha/import_admin_boundaries.py

so that a second source for the same kind of data — OSM for the administrative levels
below the country — sits beside the first rather than somewhere unrelated.

.. note::

   The package is ``imports``, not ``import``: ``import`` is a reserved word and cannot
   be a package name. Every path segment has to be a valid Python identifier, which also
   rules out hyphens — hence ``admin_boundaries`` rather than
   ``administrative-boundaries``.

Data import
-----------

:doc:`applications/ocha_import_admin_boundaries`
    Imports the OCHA *Global International Boundaries (OSM)* GeoPackage as
    administrative level 0 — the country outlines used to clip data and to attribute a
    wildfire to a country. Drives ``ogr2ogr`` for the geometry handling and maps the
    result onto the model in SQL.

.. note::

   Further application pages are added as the applications are ported into
   ``src/apps/``.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/ocha_import_admin_boundaries
