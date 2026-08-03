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
   src/apps/imports/wildfires/gfa/import_wildfires.py
   src/apps/imports/wildfires/portugal_icnf/import_wildfires.py
   src/apps/imports/wildfires/spain_egif/import_wildfires.py
   src/apps/imports/wildfires/catalonia_darpa/import_wildfires.py

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

:doc:`applications/caop_import_admin_boundaries`
    Imports the Portuguese *distritos*, *municípios* and *freguesias* from the Carta
    Administrativa Oficial de Portugal as levels 1 to 3 below the country. What turns an
    ICNF fire's DICOFRE code into a location, since that dataset publishes no coordinate
    for where a fire started.

:doc:`applications/ign_import_admin_boundaries`
    Imports the Spanish *comunidades autónomas*, *provincias* and *municipios* from the
    IGN's administrative database as levels 1 to 3 below the country. Carries the INE
    municipal code, which is what Spanish statistical and wildfire sources join on.

:doc:`applications/time_zone_import_time_zones`
    Imports IANA time zone polygons from *timezone-boundary-builder*. Reference data with
    one job: turning a coordinate into a zone name, so that a provider publishing local
    wall-clock time can be converted to an instant at import time.

:doc:`applications/gwis_import_wildfires`
    Imports the GWIS *Global Wildfire Database v3* (GlobFire) perimeters — 23 million
    fires across 22 zipped shapefiles, read without ever being unpacked. Resolves each
    fire's local start and end time and the country it burnt in as it goes.

:doc:`applications/gfa_import_wildfires`
    Imports the *Global Fire Atlas* perimeters — one loose shapefile per year, 2002
    onwards, each carrying an ignition point and a set of measurements of how the fire
    spread. Collects the multipart fires into one row each, repairs the invalid
    perimeters, and resolves the zone and the country from the ignition point. Unlike the
    GWIS import, re-running it is a no-op.

:doc:`applications/icnf_import_wildfires`
    Imports the Portuguese national burnt area cartography — twenty zipped shapefiles
    covering 1975 to 2025, read without ever being unpacked. The dataset publishes two
    attributes for its first forty years and twenty-two for its last twelve, so the
    import normalises the staging table and reads both eras with one mapping. Keeps the
    published EPSG:3763 geometry as well as the EPSG:4326 one, and records per row how
    much of its date the provider actually published.

:doc:`applications/egif_import_wildfires`
    Imports the Spanish national fire statistics (EGIF) in two steps — every Excel export
    first, then every XML export — because the two formats each drop what the other keeps.
    The Excel is the only public source of the cause and motivation labels; the XML has the
    INE municipal code, the weather, the fuel and fire-type codes and ``diastormenta``, the
    holdover interval that makes the lightning work possible. Each step writes only the
    columns its own format publishes, so neither undoes the other. Needs no ``ogr2ogr``.

:doc:`applications/darpa_import_wildfires`
    Imports the Catalan burnt area perimeters — thirty-nine shapefiles covering 1986 to
    2024 — as GisFIRE's first *regional* perimeter source, which exists because EGIF has
    none. Three of the layers were vectorised from a raster and never dissolved, so the
    import groups fragments into one fire per published ``(code, date)``: 4,533 burnt
    features are 860 fires, and one of 1994's is 1,309 polygons. Keeps the published
    EPSG:25831 geometry as well as the EPSG:4326 one, and passes no ``ENCODING`` — the
    layers are a mix of two character sets and each one says which it is.

:doc:`applications/icnf_resync_wildfires`
    Goes back to the ICNF's WFS for the times the shapefile export truncated — a
    shapefile's DBF has no datetime type, so every published instant arrived as a bare
    date — and refreshes the rest of the published attributes while it is there. One
    HTTP request per year, rate-limited and retrying, restartable a layer at a time.

.. note::

   Order matters for the wildfire import: the boundaries and the time zone areas are
   resolved *at import time* and cannot be filled in afterwards without re-importing.
   Import those two first.

Bindings
--------

A binding decides that a row of one provider's data and a row of another's describe
the same real event. That is a different kind of statement from an import: it is
inference rather than transcription, it can be wrong, and it therefore records how it
was arrived at. They live under ``src/apps/bindings/``, grouped like the importers::

   src/apps/bindings/wildfires/catalonia_darpa/bind_egif_wildfires.py

:doc:`applications/darpa_bind_egif_wildfires`
    Links each Catalan perimeter to the Spanish *parte* for the same fire — the shape
    to the cause, the burnt area and the ignition point, which is the pairing neither
    dataset can supply on its own. From 1997 the Catalan ``CODI_FINAL`` **is** the EGIF
    ``report_number``, which settles 480 of the 860 outright; before that it falls back
    to the date narrowed by province, municipality name and finally the perimeter
    itself. A perimeter is bound only when exactly one *parte* survives, and every
    binding records which rule produced it, because an identifier match and a name
    match are not the same claim.

Statistics
----------

Statistics applications read the imported data back out and aggregate it into reports.
They never modify anything, and live under ``src/apps/statistics/``, grouped the same way
as the importers::

   src/apps/statistics/wildfires/gwis/wildfire_statistics.py
   src/apps/statistics/wildfires/gfa/wildfire_statistics.py
   src/apps/statistics/wildfires/portugal_icnf/wildfire_statistics.py
   src/apps/statistics/wildfires/spain_egif/wildfire_statistics.py
   src/apps/statistics/wildfires/catalonia_darpa/wildfire_statistics.py
   src/apps/statistics/wildfires/portugal_icnf/wildfire_causes.py
   src/apps/statistics/wildfires/spain_egif/wildfire_causes.py

:doc:`applications/gwis_wildfire_statistics`
    Burnt area of the GWIS GlobFire wildfires, per country and year — smallest fire,
    largest fire and total, in hectares, measured geodesically on the WGS84 ellipsoid.
    Writes CSV and Word (``.docx``).

:doc:`applications/gfa_wildfire_statistics`
    The same report over the Global Fire Atlas perimeters — same three figures, same
    grouping, same two formats, so a GFA report and a GWIS one can be read side by side as
    a difference between the datasets rather than between two ways of counting. Adds
    ``--area-method`` to measure either geodesically or in an equal-area projection; the
    two agree to within 0.003%.

:doc:`applications/icnf_wildfire_statistics`
    The same report over the Portuguese ICNF burnt area cartography. No ``--country``:
    the ICNF publishes one country. Groups on the published ``Ano`` rather than on the
    start date, because 71% of these fires publish no date and carry a 1 January
    placeholder — and declines to measure in Portugal's own EPSG:3763 grid, which is
    conformal rather than equal-area and 7.6% out in the Azores.

:doc:`applications/egif_wildfire_statistics`
    The same report over the Spanish EGIF fire statistics, and the only one of the four
    whose hectares are **reported rather than measured**: EGIF publishes no perimeter, so
    there is no ``--area-method``. It publishes five burnt areas instead, and ``--surface``
    picks which one — ``forest`` by default, the figure the national statistic is quoted
    in. Groups on the filed ``Campania``. Its ``--country-source`` tests the published
    ignition point rather than a perimeter, which is how a coordinate that landed in the
    sea gets caught.

:doc:`applications/darpa_wildfire_statistics`
    The same report over the Catalan DARPA burnt area perimeters, and the complement of
    the EGIF one: these hectares are **measured**, because this dataset publishes a shape
    and no burnt area at all. Adds two columns the other four do not have — how many of
    each year's fires are bound to the EGIF *parte* for the same fire, and that as a
    percentage — with ``--min-confidence`` to count only the bindings resting on the
    published identifier. No ``--country`` and no ``--country-source``: the department
    publishes Catalonia and nothing else, so nothing is tested against a boundary.

:doc:`applications/icnf_wildfire_causes`
    The companion of the ICNF report, over the same fires under the same rule, counting
    instead of measuring: how many fires there were, how many carry a cause at all, and
    how many of those were ``Natural``. The ICNF publishes no lightning category, so
    ``Natural`` is the nearest proxy — and only fires from 2014 on are classified, which
    is why the percentage is of the classified ones and not of all.

:doc:`applications/egif_wildfire_causes`
    The companion of the EGIF report, counting instead of measuring — and the one that
    can name lightning, EGIF's ``idcausa`` family ``100`` being *Rayo*. Gives every count
    **twice**: over the fires as filed, and over the fires whose published ignition point
    really falls inside Spain, since a coordinate here can land in the sea or over a
    border and half the archive publishes none at all. No ``--surface``: it counts fires,
    so a blank burnt area is no reason to leave one out.

.. note::

   Further application pages are added as the applications are ported into
   ``src/apps/``.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/ocha_import_admin_boundaries
   applications/caop_import_admin_boundaries
   applications/ign_import_admin_boundaries
   applications/time_zone_import_time_zones
   applications/gwis_import_wildfires
   applications/gfa_import_wildfires
   applications/icnf_import_wildfires
   applications/icnf_resync_wildfires
   applications/egif_import_wildfires
   applications/darpa_import_wildfires
   applications/darpa_bind_egif_wildfires
   applications/gwis_wildfire_statistics
   applications/gfa_wildfire_statistics
   applications/icnf_wildfire_statistics
   applications/egif_wildfire_statistics
   applications/darpa_wildfire_statistics
   applications/icnf_wildfire_causes
   applications/egif_wildfire_causes
