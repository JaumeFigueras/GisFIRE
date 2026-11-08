Boundary and time zone imports
==============================

Reference data rather than observations: the description of the world the observations
sit in. The administrative boundaries attribute an event to a country (and, for some
sources, to a municipality); the time zone areas turn a coordinate into an IANA zone, so
that a provider publishing local wall-clock time can be converted to an instant. Both are
read by the other importers **at import time**, so they are imported first::

   src/apps/imports/admin_boundaries/ocha/import_admin_boundaries.py
   src/apps/imports/admin_boundaries/caop/import_admin_boundaries.py
   src/apps/imports/admin_boundaries/ign/import_admin_boundaries.py
   src/apps/imports/time_zones/timezone_boundary_builder/import_time_zones.py

.. contents::
   :local:
   :depth: 1

Administrative boundaries
-------------------------

The countries come from OCHA, worldwide; the levels below the country from each country's own mapping agency.

:doc:`ocha_import_admin_boundaries`
    Imports the OCHA *Global International Boundaries (OSM)* GeoPackage as
    administrative level 0 — the country outlines used to clip data and to attribute a
    wildfire to a country. Drives ``ogr2ogr`` for the geometry handling and maps the
    result onto the model in SQL.

:doc:`caop_import_admin_boundaries`
    Imports the Portuguese *distritos*, *municípios* and *freguesias* from the Carta
    Administrativa Oficial de Portugal as levels 1 to 3 below the country. What turns an
    ICNF fire's DICOFRE code into a location, since that dataset publishes no coordinate
    for where a fire started.

:doc:`ign_import_admin_boundaries`
    Imports the Spanish *comunidades autónomas*, *provincias* and *municipios* from the
    IGN's administrative database as levels 1 to 3 below the country. Carries the INE
    municipal code, which is what Spanish statistical and wildfire sources join on.

.. toctree::
   :maxdepth: 1
   :hidden:

   ocha_import_admin_boundaries
   caop_import_admin_boundaries
   ign_import_admin_boundaries

Time zones
----------

:doc:`time_zone_import_time_zones`
    Imports IANA time zone polygons from *timezone-boundary-builder*. Reference data with
    one job: turning a coordinate into a zone name, so that a provider publishing local
    wall-clock time can be converted to an instant at import time.

.. toctree::
   :maxdepth: 1
   :hidden:

   time_zone_import_time_zones
