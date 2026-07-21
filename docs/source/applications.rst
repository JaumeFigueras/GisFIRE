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
   src/apps/imports/time_zones/timezone_boundary_builder/import_time_zones.py
   src/apps/imports/wildfires/gwis/import_wildfires.py

so that a second source for the same kind of data — OSM for the administrative levels
below the country, another agency's fire perimeters — sits beside the first rather than
somewhere unrelated.

What they all have in common — resolving the database settings, driving ``ogr2ogr``,
creating the :class:`~src.data_model.data_provider.DataProvider` row, cleaning the staging
table up — lives in :mod:`src.apps.imports.common`. What deliberately does *not* live
there is the mapping from staging table to model: it differs for every source, and it is
the only interesting part of an importer.

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

:doc:`applications/time_zone_import_time_zones`
    Imports IANA time zone polygons from *timezone-boundary-builder*. Reference data with
    one job: turning a coordinate into a zone name, so that a provider publishing local
    wall-clock time can be converted to an instant at import time.

:doc:`applications/gwis_import_wildfires`
    Imports the GWIS *Global Wildfire Database v3* (GlobFire) perimeters — 23 million
    fires across 22 zipped shapefiles, read without ever being unpacked. Resolves each
    fire's local start and end time and the country it burnt in as it goes.

.. note::

   Order matters for the wildfire import: the boundaries and the time zone areas are
   resolved *at import time* and cannot be filled in afterwards without re-importing.
   Import those two first.

Statistics
----------

Statistics applications read the imported data back out and aggregate it into reports.
They never modify anything, and live under ``src/apps/statistics/``, grouped the same way
as the importers::

   src/apps/statistics/wildfires/gwis/wildfire_statistics.py

:doc:`applications/gwis_wildfire_statistics`
    Burnt area of the GWIS GlobFire wildfires, per country and year — smallest fire,
    largest fire and total, in hectares, measured geodesically on the WGS84 ellipsoid.
    Writes CSV and Word (``.docx``).

.. note::

   Further application pages are added as the applications are ported into
   ``src/apps/``.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/ocha_import_admin_boundaries
   applications/time_zone_import_time_zones
   applications/gwis_import_wildfires
   applications/gwis_wildfire_statistics
