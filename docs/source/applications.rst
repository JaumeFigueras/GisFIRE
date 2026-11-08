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
under ``src/apps/imports/`` (see `Data import`_), so that a second source for the same
kind of data — OSM for the administrative levels below the country, another agency's
fire perimeters — sits beside the first rather than somewhere unrelated.

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

Running on a server
-------------------

:doc:`applications/running_on_a_server`
    Every import, binding, resync and statistics page has a *Where to run it* section giving
    its command in three forms. **Locally**, when the files and the database are on the
    machine you are typing on. **On the server over SSH**, started with ``nohup`` and its
    output redirected to a log, so you can close the connection and check the result
    later. **Against a remote database**, from your machine, through an SSH tunnel to the
    server's PostgreSQL, with the ``--db-*`` options. This page explains the pieces those
    commands are made of: why ``-u``, why ``< /dev/null``, how to keep the exit status,
    and why the password goes in the environment rather than on the command line.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/running_on_a_server

.. _applications-data-download:

Data download
-------------

An importer reads a file that is already on disk; a downloader is what puts it there. Most
providers need none — they publish an archive you fetch once with a browser — but some
publish only through a paged API, where a complete copy means issuing hundreds of requests
politely and checking that nothing was silently truncated. That is a program, and it lives
under ``src/apps/download/``::

   src/apps/download/wildfires/guatemala_inab/download_wildfires.py
   src/apps/download/wildfires/south_korea_kfs/download_wildfires.py

These touch no database at all.

:doc:`applications/inab_download_wildfires`
    Downloads the Guatemalan fire layers from INAB's ArcGIS REST server, which publishes
    **no WFS** for any of them. Three modes: report what is there per year, fetch one year,
    fetch the lot. Pages politely — a delay between requests, retries with backoff, a
    ``User-Agent`` that identifies itself, and page sizes far below what the server would
    allow, because it **truncates an over-large response mid-JSON instead of refusing
    it**. Verifies each download against a count fetched first, and writes a provenance
    sidecar the source itself does not supply.

    Run its ``years`` mode before anything else: the burn-scar layers turn out to hold one
    season rather than the archive their names suggest. What it writes is read by
    :doc:`applications/inab_import_wildfires`.

:doc:`applications/kfs_download_wildfires`
    Downloads the Korea Forest Service wildfire history (*산불발생이력*) from the Safemap
    open API, service ``IF_0088``. Needs a Safemap service key **approved for this
    dataset** — issuing the key is only the first step. The API pages but does not
    filter, so it fetches the whole history, converts the Web Mercator ``x``/``y`` to a
    WGS84 point, checks the result against ``totalCount`` and for repeated ids, and
    prints the records per year. The data is KOGL Type 4: non-commercial, no derivatives.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/inab_download_wildfires
   applications/kfs_download_wildfires

Data import
-----------

Import applications are grouped by the **kind of data** they bring in, and within a kind
by source — the same split as the code under ``src/apps/imports/``::

   src/apps/imports/admin_boundaries/<source>/import_admin_boundaries.py
   src/apps/imports/time_zones/<source>/import_time_zones.py
   src/apps/imports/wildfires/<source>/import_wildfires.py
   src/apps/imports/lightnings/<source>/import_lightnings.py

Each kind has a page of its own:

:doc:`applications/import_boundaries`
    The reference data every other import reads: administrative boundaries (OCHA
    countries worldwide; the Portuguese and Spanish divisions below them) and the IANA
    time zone areas. Imported first.

:doc:`applications/import_wildfires`
    Fire perimeters, ignition points and agency fire reports from 16 sources, grouped by
    region: the global satellite products, then Europe, America, Asia and Oceania.

:doc:`applications/import_lightnings`
    Lightning strokes from detection networks: MeteoCat's XDDE over Catalonia so far.

A new kind of data — meteorological observations, NDVI, fuel moisture — gets its own
package under ``src/apps/imports/`` and its own page here, rather than joining one of the
lists above.

.. note::

   The administrative boundaries and the time zone areas are resolved *at import time*
   and cannot be filled in afterwards without re-importing, so import them first — see
   :doc:`applications/import_boundaries`.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/import_boundaries
   applications/import_wildfires
   applications/import_lightnings

Bindings
--------

A binding decides that a row of one provider's data and a row of another's describe
the same real event. That is a different kind of statement from an import: it is
inference rather than transcription, it can be wrong, and it therefore records how it
was arrived at. They live under ``src/apps/bindings/``, grouped like the importers::

   src/apps/bindings/wildfires/catalonia_darpa/bind_egif_wildfires.py
   src/apps/bindings/wildfires/andalusia_rediam/bind_egif_wildfires.py
   src/apps/bindings/wildfires/canada_nbac/bind_nfdb_wildfires.py
   src/apps/bindings/wildfires/chile_conaf_magnitud/bind_conaf_wildfires.py

:doc:`applications/darpa_bind_egif_wildfires`
    Links each Catalan perimeter to the Spanish *parte* for the same fire — the shape
    to the cause, the burnt area and the ignition point, which is the pairing neither
    dataset can supply on its own. From 1997 the Catalan ``CODI_FINAL`` **is** the EGIF
    ``report_number``, which settles 480 of the 860 outright; before that it falls back
    to the date narrowed by province, municipality name and finally the perimeter
    itself. A perimeter is bound only when exactly one *parte* survives, and every
    binding records which rule produced it, because an identifier match and a name
    match are not the same claim.

:doc:`applications/rediam_bind_egif_wildfires`
    The same application over the Andalusian perimeters, and the easier half of the
    job: ``CODIGO`` **is** the EGIF ``report_number`` from the first year, so 749 of
    the 759 bindings rest on an identifier and only ten on a date and a name. Two of
    the Catalan rules are absent — every Andalusian code carries a province, so nothing
    is ever bound on a date alone — and one rule differs: where a guess collides with an
    identifier match on the same *parte*, the identifier wins rather than both being
    dropped. 759 of 907 perimeters are bound; 133 of the rest are 2024 and 2025, which
    the EGIF exports do not reach.

:doc:`applications/nbac_bind_nfdb_wildfires`
    The same job over the two Canadian datasets, and the hard case: **they share no
    published identifier at all.** NBAC publishes nineteen fields in every one of its
    fifty-three yearly archives and not one of them is an agency fire number, so there
    is no code stage, nothing is certain, and no rule here scores 1.00. What binds them
    instead is place, date and agency — the NFDB point inside the burnt perimeter, on
    the ``AG_SDATE`` the agency also filed as ``REP_DATE``, from the agency that mapped
    it. Both sides are published on EPSG:3978, so the containment test is metres on a
    common grid. About half the bindings come from a tolerance stage for points that
    fall just outside the polygon, whose 2 km default was measured rather than chosen.

:doc:`applications/conaf_magnitud_bind_wildfires`
    The same job over CONAF's two Chilean products, and the case in between the Spanish
    and the Canadian ones: they **do** share an identifier — the office's ``NUMERO_REG``,
    the same number in both files — but it is **not unique**, repeating within a season
    and even within a región, so 93 perimeters of 2016-2017 match two reports on it. The
    cascade therefore puts two tie-breaks above the número: the fire's name, which settles
    83 of those 93, and containment of the report's point, which settles 77. No rule
    scores 1.00 for that reason, and the número rules are deliberately not gated on
    distance — a report's point can be the comuna's centre. **706 of 743 bound, 95.0%**;
    a report two perimeters both claim unbinds them both, because that usually means a
    dissolve the import did not make.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/darpa_bind_egif_wildfires
   applications/rediam_bind_egif_wildfires
   applications/nbac_bind_nfdb_wildfires
   applications/conaf_magnitud_bind_wildfires

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
   src/apps/statistics/wildfires/andalusia_rediam/wildfire_statistics.py
   src/apps/statistics/wildfires/greece_ffa/wildfire_statistics.py
   src/apps/statistics/wildfires/canada_nbac/wildfire_statistics.py
   src/apps/statistics/wildfires/canada_nfdb/wildfire_statistics.py
   src/apps/statistics/wildfires/guatemala_inab/wildfire_statistics.py
   src/apps/statistics/wildfires/chile_conaf/wildfire_statistics.py
   src/apps/statistics/wildfires/chile_conaf_magnitud/wildfire_statistics.py
   src/apps/statistics/wildfires/australia_csiro/wildfire_statistics.py
   src/apps/statistics/wildfires/new_zealand_wod/wildfire_statistics.py
   src/apps/statistics/wildfires/south_korea_kfs/wildfire_statistics.py
   src/apps/statistics/wildfires/portugal_icnf/wildfire_causes.py
   src/apps/statistics/wildfires/spain_egif/wildfire_causes.py
   src/apps/statistics/wildfires/canada_nbac/wildfire_causes.py
   src/apps/statistics/wildfires/canada_nfdb/wildfire_causes.py
   src/apps/statistics/wildfires/chile_conaf/wildfire_causes.py
   src/apps/statistics/wildfires/new_zealand_wod/wildfire_causes.py
   src/apps/statistics/wildfires/south_korea_kfs/wildfire_causes.py
   src/apps/statistics/wildfires/guatemala_inab/wildfire_classification.py

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

:doc:`applications/rediam_wildfire_statistics`
    The same report over the Andalusian REDIAM perimeters, with the same two EGIF-match
    columns as the Catalan one — and one option no other report can offer: this is the
    only dataset with **both** a perimeter and a published burnt area, so ``--surface``
    reports either the measured polygon or the hectares the service publishes (wooded,
    scrub, grassland, or the three added). Over the archive the two differ by 7.8%, and
    neither is a correction of the other. No ``--country`` and no ``--country-source``.

:doc:`applications/greece_ffa_wildfire_statistics`
    The same report over the Greek Fire Service records, and the twin of the EGIF one
    in kind: these hectares are **reported**, not measured, because this dataset
    publishes no perimeter either. ``--surface`` picks which of the **eight** land
    covers the service publishes — or the sum of all eight, which is the default and
    the nearest thing to the total it does not publish. Its two extra columns count
    how many of each year's fires carry a coordinate, which is 0% until 2020 and
    about 91% after: the single most important thing to know before doing anything
    spatial with it. Excludes the 1,255 false alarms of 2025 unless asked not to. No
    ``--country``, no ``--country-source`` and no ``--area-method``.

:doc:`applications/nbac_wildfire_statistics`
    The same report over the Canadian National Burned Area Composite — GisFIRE's first
    outside Europe, and the second dataset with **both** a perimeter and a published
    burnt area. Unlike Andalusia's the two agree to 0.0000005%, ``POLY_HA`` being
    computed on an equal-area projection; ``--surface`` also offers the modelled
    ``ADJ_HA``, which is a different quantity. Declines to measure in Canada's own
    EPSG:3978 grid, a conformal conic that understates the archive by 4.2%. Its two
    extra columns count how many of each year's fires carry a real published date —
    over 90% since 2010, 15.63% in 1977 — which is what stops anyone grouping a fifth
    of the archive by month. Adds ``--cause`` and excludes prescribed burns by default.
    No ``--country`` and no ``--country-source``.

:doc:`applications/nfdb_wildfire_statistics`
    The same report over the Canadian agency fire reports, and the companion of the
    NBAC one: same country, same fires, **34 million hectares apart**, because one is
    what an agency recorded and the other what a satellite could see. Reported hectares
    like EGIF's and Greece's, so no ``--surface`` and no ``--area-method``. Its
    ``--country-source`` defaults to ``geometry`` — the opposite of EGIF's — because
    almost every fire here has a point and a good many of those points are not in
    Canada. Its extra column counts the agencies behind each row, thirteen contributing
    at wildly different volumes, and ``--agency`` narrows it to one of them.

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

:doc:`applications/nbac_wildfire_causes`
    The companion of the NBAC report, counting instead of measuring — and the first of
    these to carry an **area** column, because the two Canadian datasets disagree by
    twenty-one points about the share of natural *fires* and agree to two tenths of a
    point about the share of natural *hectares*. NBAC publishes no lightning category
    either, so ``Natural`` is the proxy. The percentages are of the fires whose cause
    somebody **determined**: ``Undetermined`` is a published category here rather than a
    missing value, and it covers 70% of the 1970s against 8% of the 2020s, so a share of
    all fires would measure investigation rather than fire.

:doc:`applications/nfdb_wildfire_causes`
    The same report over the agency fire reports, and the twin of the one above. Its
    172,430 natural-cause fires are the largest such set in GisFIRE and every one has a
    point and a date. The national figure is a weighted average of thirteen very
    different fire regimes — 83% natural in the Northwest Territories, 2.6% in Nova
    Scotia — so ``--agency`` is how to get a number that means one thing.

:doc:`applications/conafor_wildfire_statistics`
    The same report over the Mexican CONAFOR burnt area cartography, and the only one that
    offers a third ``--area-method``: ``reported``, CONAFOR's own published ``AREA_HA``,
    beside the two measured ones. This dataset publishes both a perimeter and an area, and
    from 2016 the second *is* the first's own area — so running the report twice is what
    turns the 2010 layer's threefold disagreement into a number. No ``--country`` and **no
    containment test at all**: every CONAFOR perimeter is inside Mexico, so this is the one
    report in the family that needs no boundaries imported.

:doc:`applications/conafor_wildfire_causes`
    Counts by cause over the same fires, and the one report in the project that can answer
    the lightning question **directly**: CONAFOR publishes ``Rayos`` as a specific cause,
    where the ICNF publishes no lightning category at all. It publishes it for 2010 and
    2012-2019 only, so the ``Lightning`` cell is blank — not zero — for 2011 and for every
    year from 2020. Causes are matched on the reconciled canonical form, without which the
    2011 spellings of *Naturales* would count as nothing.

:doc:`applications/inab_wildfire_statistics`
    The same report over the Guatemalan INAB fire reports, and the first with **no
    hectares in it at all**: INAB publishes no perimeter, no burnt area and no land-cover
    split, so there is nothing to measure and no ``--area-method`` or ``--surface`` to
    choose with. The three area columns are kept in the shared position and left **empty**
    on every row — an empty cell says nothing was published, where a zero would say
    nothing burnt — so the CSV still reads beside the other seven. Groups on the
    Guatemalan calendar year of each fire's own instant, this source publishing no year
    field at all. Its four extra columns count the false alarms, the fires that publish a
    coordinate (100%, the opposite of Greece) and those inside a protected area (one in
    three). No ``--country`` and no ``--country-source``.

:doc:`applications/inab_wildfire_classification`
    The companion of the INAB report, counting instead of measuring — and deliberately
    **not** a causes report, because Guatemala publishes no cause. ``--classification``
    picks one of the four vocabularies it does publish: ``tipo_incendio``, the only
    classification of the fire itself and filled on one record in ten; ``estado_aviso``,
    what became of the report; ``institucion``; and ``forma_comunicacion``. Percentages
    are shares of the **classified** fires, which with a tenth classified is a
    factor-of-nine difference from a share of all of them. Columns come from the
    provider's published vocabulary where there is one — so a value nobody carries shows
    a zero rather than vanishing — and from the data where there is not, which is
    ``institucion`` alone. ``--cause`` is accepted only in order to be refused.

:doc:`applications/conaf_wildfire_statistics`
    The same report over the Chilean CONAF seasonal fire reports — reported hectares, like
    EGIF's and Greece's, this product publishing no perimeter — and the first grouped by a
    **fire season** rather than a calendar year: 1 July to 30 June, as CONAF files it and
    as every one of its dated features confirms. Its extra ``Dated`` column exists because
    **half this archive has no start date at all**: eight of fifteen mainland seasons
    publish none, so 49,470 fires sit at 1 July midnight and any month, hour or duration
    statistic is about the other half. ``--dated-only`` is how to ask for that half.
    ``--surface`` picks one of the four published areas — the whole fire, the plantations,
    the natural vegetation or the rest — and ``--reporter`` separates CONAF's own offices
    from the forestry companies' brigades, which are two different reporting systems.

:doc:`applications/conaf_wildfire_causes`
    Counts by cause over the same fires, and the report with the sharpest discontinuity in
    the project: CONAF **renumbered its taxonomy in 2023-2024 and reused the numbers**, so
    it groups on the canonical name and never on the code — ``4.1`` means *causa
    desconocida* on one side of the break and *faenas forestales* on the other. Ten
    categories were renamed into narrower or broader ones, so their series stop or start
    there; the report names every one that does, and ``--bridge-schemes`` joins them under
    the current name for a reader who wants to cross the break deliberately. Three
    synthetic rows keep the unclassified fires visible and apart: a specific cause with no
    general one is not the same thing as no cause at all.

:doc:`applications/conaf_magnitud_wildfire_statistics`
    The same report over CONAF's mapped perimeters, and the counterpart of the one above:
    the same fires, measured instead of reported. Its two area columns are **Mapped** and
    **Reported** — the polygon's area and the bound report's ``SUPERFICIE`` — which is a
    comparison only :doc:`applications/nbac_wildfire_statistics` can otherwise make, and
    ``--bound-only`` narrows the scope to the fires for which the two columns cover the
    same rows. ``--area-method`` measures published, geodesically or in an equal-area
    projection; the measured methods work from the EPSG:4326 perimeter rather than either
    published grid, since Chile's two are seven zones apart and could not be added
    together.

:doc:`applications/csiro_wildfire_statistics`
    The Australian historical bushfire extents, and the only report grouped by **fire
    season** (July to June) rather than by year. Each season has a triplet — fires,
    reported hectares, measured hectares — for every fire, for each of the three
    published fire types (which add up to it) and for the natural-cause fires, whose cells
    are left empty where no cause was published. Writes a national file and **one file
    per state**, CSV and Word. Starts at 1970-71 by default, the first season every state
    but the Northern Territory reports every year. Fires are published features, nothing
    merged, so there are no minimum or maximum columns.

:doc:`applications/wod_wildfire_statistics`
    The New Zealand WOD: the shared six columns plus how many of each row's fires FENZ and
    DOC recorded and how many have a perimeter — the coverage caveat made visible, DOC
    alone before 1998 and FENZ alone from 2012. ``--area-method`` chooses the **recorded**
    area of every fire or the **measured** area of the 2,089 perimeters, never a mixture;
    ``--financial-year`` counts by New Zealand fire year, July to June. Its
    ``--country-source`` defaults to ``filed``: every record is a New Zealand fire, the
    points in the sea included. By fire year it reproduces the paper's 11,415 ha for
    1998/1999.

:doc:`applications/wod_wildfire_causes`
    Counts by cause over the same fires — and a dataset that **names lightning**, 538
    records of it, kept apart from the five other natural fires. Lightning is half a
    percent of the fires whose cause is known and about one hectare in a hundred: New
    Zealand's fires are started by people.

:doc:`applications/kfs_wildfire_statistics`
    The Korea Forest Service statistics: the shared six columns, nothing else. The
    hectares are reported — no perimeter — and there is no ``--country``; ``--province``
    selects one province by its published abbreviation. **Flags the last year of a
    release as partial**, by the date of its last fire.

:doc:`applications/kfs_wildfire_causes`
    Counts by cause over the same fires, in two tables: the New Zealand report's columns,
    so the two countries compare, and the eighteen classes the import gives the
    free-text cause, with each class's share of fires and area and how many are only
    suspected. Lightning is nine fires in 2,020.

.. note::

   **There is no counts-by-cause report for Greece or Guatemala**, and there cannot
   be. Nothing in any of the twenty-six sheets the Greek Fire Service publishes says why a
   fire started, and nothing in INAB's thirty-three attributes does either — no cause
   column, no lightning category, nothing to seed a catalogue from. Portugal, Spain,
   Canada and Mexico have one because their sources publish a cause; these two do not.

   Guatemala gets :doc:`applications/inab_wildfire_classification` in that slot, which
   counts the vocabularies it *does* publish and says in its own title that they are not
   causes. Greece has no equivalent: its sheets publish no vocabulary about the fire
   either, only an incident category from 2025. See :doc:`providers`.

.. note::

   Further application pages are added as the applications are ported into
   ``src/apps/``.

.. toctree::
   :maxdepth: 1
   :hidden:

   applications/gwis_wildfire_statistics
   applications/gfa_wildfire_statistics
   applications/icnf_wildfire_statistics
   applications/egif_wildfire_statistics
   applications/darpa_wildfire_statistics
   applications/rediam_wildfire_statistics
   applications/greece_ffa_wildfire_statistics
   applications/nbac_wildfire_statistics
   applications/nfdb_wildfire_statistics
   applications/inab_wildfire_statistics
   applications/icnf_wildfire_causes
   applications/egif_wildfire_causes
   applications/nbac_wildfire_causes
   applications/nfdb_wildfire_causes
   applications/inab_wildfire_classification
   applications/conafor_wildfire_statistics
   applications/conafor_wildfire_causes
   applications/conaf_wildfire_statistics
   applications/conaf_wildfire_causes
   applications/conaf_magnitud_wildfire_statistics
   applications/csiro_wildfire_statistics
   applications/wod_wildfire_statistics
   applications/wod_wildfire_causes
   applications/kfs_wildfire_statistics
   applications/kfs_wildfire_causes
