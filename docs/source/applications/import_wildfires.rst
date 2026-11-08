Wildfire imports
================

One importer per source, each writing the generic
:class:`~src.data_model.wildfire.Wildfire` and
:class:`~src.data_model.ignition.Ignition` rows plus its provider's own table — see
:doc:`../providers`. They live under ``src/apps/imports/wildfires/<source>/``, one
package per source, and are grouped here by the region the source covers: the global
products first, then by continent.

.. note::

   The administrative boundaries and the time zone areas are resolved *at import time*
   and cannot be filled in afterwards without re-importing, so import them first — see
   :doc:`import_boundaries`.

Some sources publish only through a paged API; their downloaders, which put the files
on disk for these importers to read, are under :ref:`applications-data-download`.

.. contents::
   :local:
   :depth: 2

World
-----

Global products derived from satellite observation, covering every country with one method.

:doc:`gwis_import_wildfires`
    Imports the GWIS *Global Wildfire Database v3* (GlobFire) perimeters — 23 million
    fires across 22 zipped shapefiles, read without ever being unpacked. Resolves each
    fire's local start and end time and the country it burnt in as it goes.

:doc:`gfa_import_wildfires`
    Imports the *Global Fire Atlas* perimeters — one loose shapefile per year, 2002
    onwards, each carrying an ignition point and a set of measurements of how the fire
    spread. Collects the multipart fires into one row each, repairs the invalid
    perimeters, and resolves the zone and the country from the ignition point. Unlike the
    GWIS import, re-running it is a no-op.

.. toctree::
   :maxdepth: 1
   :hidden:

   gwis_import_wildfires
   gfa_import_wildfires

Europe
------

National and regional agency records: Portugal, Spain and two of its regions, and Greece.

:doc:`icnf_import_wildfires`
    Imports the Portuguese national burnt area cartography — twenty zipped shapefiles
    covering 1975 to 2025, read without ever being unpacked. The dataset publishes two
    attributes for its first forty years and twenty-two for its last twelve, so the
    import normalises the staging table and reads both eras with one mapping. Keeps the
    published EPSG:3763 geometry as well as the EPSG:4326 one, and records per row how
    much of its date the provider actually published.

:doc:`icnf_resync_wildfires`
    Goes back to the ICNF's WFS for the times the shapefile export truncated — a
    shapefile's DBF has no datetime type, so every published instant arrived as a bare
    date — and refreshes the rest of the published attributes while it is there. One
    HTTP request per year, rate-limited and retrying, restartable a layer at a time.

:doc:`egif_import_wildfires`
    Imports the Spanish national fire statistics (EGIF) in two steps — every Excel export
    first, then every XML export — because the two formats each drop what the other keeps.
    The Excel is the only public source of the cause and motivation labels; the XML has the
    INE municipal code, the weather, the fuel and fire-type codes and ``diastormenta``, the
    holdover interval that makes the lightning work possible. Each step writes only the
    columns its own format publishes, so neither undoes the other. Needs no ``ogr2ogr``.

:doc:`darpa_import_wildfires`
    Imports the Catalan burnt area perimeters — thirty-nine shapefiles covering 1986 to
    2024 — as GisFIRE's first *regional* perimeter source, which exists because EGIF has
    none. Three of the layers were vectorised from a raster and never dissolved, so the
    import groups fragments into one fire per published ``(code, date)``: 4,533 burnt
    features are 860 fires, and one of 1994's is 1,309 polygons. Keeps the published
    EPSG:25831 geometry as well as the EPSG:4326 one, and passes no ``ENCODING`` — the
    layers are a mix of two character sets and each one says which it is.

:doc:`rediam_import_wildfires`
    Imports the Andalusian burnt area perimeters — 2008 onwards — as GisFIRE's second
    *regional* perimeter source. Reads the combined layer for the perimeters and the four
    yearly layers that publish ``X_INIC``/``Y_INIC`` for the ignition points, so a fire
    gets both observations where the service published both. Dissolves the 55 codes
    published twice into one fire each, keeps the published EPSG:25830 geometry as well as
    the EPSG:4326 one, and asserts that CRS rather than the EPSG:3042 the ``.prj`` resolves
    to — same projection, opposite axis order. Replaces the **years** it reads rather than
    the layer, because the combined file is renamed every publication.

:doc:`greece_ffa_import_wildfires`
    Imports the Greek national fire statistic — 260,194 records over 2000-2025, in
    fifteen Excel workbooks — as GisFIRE's first source outside the Iberian peninsula
    and its second administrative statistic after EGIF. The sheets have six different
    column arrangements under a header two rows deep, so every field is found by name
    and none by position; the year is the unit replaced, because nothing in the dataset
    identifies a fire. Converts στρέμματα to hectares, and builds a point for the 54,491
    fires that have one — no year before 2020 publishes a coordinate at all. Needs no
    ``ogr2ogr``, and no time zone areas either: Greece is one zone.

.. toctree::
   :maxdepth: 1
   :hidden:

   icnf_import_wildfires
   icnf_resync_wildfires
   egif_import_wildfires
   darpa_import_wildfires
   rediam_import_wildfires
   greece_ffa_import_wildfires

America
-------

National agency records from Canada to Chile.

North America
^^^^^^^^^^^^^

:doc:`nbac_import_wildfires`
    Imports the Canadian National Burned Area Composite — 53 zipped shapefiles, one per
    year, 52,276 polygons that dissolve to **51,818 fire events** and 132.7 Mha of mapped
    burn. GisFIRE's first source outside Europe. The published features are cut at
    provincial and park boundaries, so a fire that crossed one is dissolved into a single
    row carrying ``part_count`` and a ``"; "``-joined list of the administrations it burnt
    in. Two independent date pairs are published and some fires have neither, so the start
    is resolved agency-date, then hotspot, then the bare year, recording which and how
    much of it is real. Keeps the published EPSG:3978 geometry as well as the EPSG:4326
    one — and **asserts** that CRS, the ``.prj`` naming no EPSG code at all.

:doc:`nfdb_import_wildfires`
    Imports the Canadian National Fire Database agency fire points — one 1.1 GB shapefile,
    448,602 reports from thirteen agencies, of which **195,240 are natural-cause**, the
    largest lightning-attributable set in the project. Each row becomes a fire report and
    the point it was filed at, the EGIF shape. Reads 1973 onwards to line up with NBAC, and
    refuses a row with no report date rather than inventing one — this dataset has no
    second date to fall back on. A coordinate outside Canada drops the *point* and keeps
    the fire.

:doc:`conafor_import_wildfires`
    Imports Mexico's national burnt area cartography — 14 zipped shapefiles, one per year
    from 2010 to 2023, 45,914 polygons — as GisFIRE's first Latin American source. **No two
    consecutive years have the same attributes** — 58 published names across the fourteen
    files, and 2015 renames almost all of them, its key included — so the import renames
    the aliases, supplies what a layer omits and reads all fourteen with one mapping. The dates come in
    four written formats, all four inside the 2022 layer, and are parsed in Python because
    ``to_date`` would silently accept a twentieth month — a value the 2021 archive
    contains. The year comes from the file name and is verified against the keys before
    anything is written. Five features are exact duplicates of five others and are
    de-duplicated, which is what lets ``fire_code`` be unique.

.. toctree::
   :maxdepth: 1
   :hidden:

   nbac_import_wildfires
   nfdb_import_wildfires
   conafor_import_wildfires

Central America
^^^^^^^^^^^^^^^

:doc:`inab_import_wildfires`
    Imports Guatemala's *Monitoreo de Incendios Forestales* — 4,615 fire reports over
    2023-2026 — as GisFIRE's first Central American source and the first whose input is an
    API download rather than a published archive. A row is a **report**, not a fire and not
    an area: the provider publishes no perimeter and no hectares at all, so there is
    nothing here for a statistics application to measure. Reads every file before writing
    anything and then commits **one year at a time**, even though the whole dataset would
    fit in one transaction. The delete that replaces a year also keys on ``global_id``, so
    a record this program and the ArcGIS server disagree about the year of moves rather
    than vanishing. Parses the GeoJSON in Python rather than staging it with ``ogr2ogr``,
    because the layer carries the **name and telephone number of whoever reported each
    fire** and those must never reach a table. Needs no ``ogr2ogr`` and no time zone
    areas: Guatemala is one zone.

.. toctree::
   :maxdepth: 1
   :hidden:

   inab_import_wildfires

South America
^^^^^^^^^^^^^

:doc:`conaf_import_wildfires`
    Imports Chile's seasonal fire reports — 23 RAR archives, **95,868 fires** over
    2010-2011 to 2024-2025 — as GisFIRE's first South American source. The archives are
    RAR and GDAL has no ``/vsirar/``, so they are unpacked to a temporary directory first.
    Each layer is staged on **one of two grids**, chosen from its own ``.prj``: UTM 19S for
    the mainland, UTM 12S for Rapa Nui — and UTM 19S for the season that ships no
    projection at all. **Half the archive publishes no start date**, so the import writes
    1 July of the season and records a precision saying so on every row. The 23 layers name
    the same attribute up to four ways and omit whole columns, so only seven signature
    attributes are required. Three records whose DBF has come apart are dropped, cause
    catalogue included. The delete that replaces a season keys on the season **and the
    territory**, because the mainland and Easter Island are separate archives for the same
    season.

:doc:`conaf_magnitud_import_wildfires`
    Imports Chile's *incendios de magnitud* — 13 archives, 781 features, **743 fires** —
    the mapped shapes of the fires that reached roughly 200 hectares. A fire is several
    published features with no ``GID`` to group them by, so the import dissolves on the
    season, the folded name **and** the office's number: without the number, four pairs of
    genuinely different fires sharing a name became four fires instead of eight.
    ``SUPERFICIE`` is the *feature's own polygon area* rather than a reported burnt area,
    so the mapped area is computed from the union and the published sum is kept beside it.
    Splits the ``'402 - SAN GUILLERMO'`` prefix into a number and a name, which is what
    :doc:`conaf_magnitud_bind_wildfires` then matches on.

.. toctree::
   :maxdepth: 1
   :hidden:

   conaf_import_wildfires
   conaf_magnitud_import_wildfires

Asia
----

:doc:`kfs_import_wildfires`
    Imports the Korea Forest Service wildfire statistics — one CP949 CSV, **2,020 fires
    over 2022 to September 2025** — as GisFIRE's first Asian source. No coordinate in any
    row, so no geometry and no boundaries: place names are stored as published and
    romanized, and each free-text cause is translated and classified. A year is replaced
    wholesale, since nothing identifies a fire; a cause text nobody has classified stops
    the import before anything is deleted; the fourteen impossible ends are stored as no
    end, with the reason. ``--dry-run`` checks a release without a database.

.. toctree::
   :maxdepth: 1
   :hidden:

   kfs_import_wildfires

Oceania
-------

:doc:`csiro_import_wildfires`
    Imports the Australian historical bushfire extents — one file geodatabase, two feature
    classes, **347,834 polygons stored one row each** over 1898-2025 — as GisFIRE's first
    Oceanian source. Alone among the imports it **chooses its own unit of work**: the
    archive is a single 860 MB file rather than one publication per period, so the import
    stages a feature class once and then deletes, rewrites and commits **one year at a
    time**, logging each. **Nothing is merged**: grouping the patches of a burn on the
    tightest published key joins features 2,403 km apart, so the published feature is the
    unit stored. Runs ``ogr2ogr`` with ``-preserve_fid`` to keep the
    geodatabase's ``OBJECTID``, and opens the archive through a temporary ``.gdb`` symlink
    because GDAL reads a geodatabase by its suffix and the distribution has none. **Half of
    what it writes is prescribed burning**, kept and typed rather than dropped.

:doc:`wod_import_wildfires`
    Imports the New Zealand *Wildfire Occurrence Database* — two shapefiles, **128,020
    records over 1931-2025** — as GisFIRE's second Oceanian source. Each record becomes
    four rows: the record, its published point, and the terrain and weather the compilers
    attached, every one of the 109 attributes kept. **Nothing in scope is refused**: the
    dirt is corrected and counted — a scientific-notation identifier, a negative area,
    invalid polygons, points in the sea kept as published — but a release the model cannot
    hold, above all one with a cause spelling nobody has classified, is refused **whole**
    before anything is deleted. Reads from 1998, when the FENZ records start, unless
    ``--all-years``; a year at a time, the NFDB shape.

.. toctree::
   :maxdepth: 1
   :hidden:

   csiro_import_wildfires
   wod_import_wildfires
