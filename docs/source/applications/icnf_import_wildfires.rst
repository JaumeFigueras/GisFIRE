Import ICNF burnt areas (Portugal)
==================================

Imports the Portuguese national burnt area cartography — the ICNF *áreas ardidas*
layers — into :class:`~src.providers.icnf.wildfire.IcnfWildfire` rows, with the generic
columns in ``wildfire`` and the ICNF ones in ``icnf_wildfire``.

.. contents::
   :local:
   :depth: 2

Usage
-----

Migrate the database first — the ``icnf_wildfire`` and ``icnf_fire_cause`` tables are
created by migrations, not by the importer — then point it at the directory the archives
were downloaded into:

.. code-block:: bash

   make migrate
   python3 -m src.apps.imports.wildfires.portugal_icnf.import_wildfires -d /path/to/portugal/

or import a single layer with ``-s``:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.portugal_icnf.import_wildfires -s ardida_2024.zip

The archives are read **in place**: GDAL's ``/vsizip/`` handler reads the shapefile
straight out of the ``.zip``, so nothing is unpacked and no temporary space is needed.

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import these first
------------------

Neither is required, and the fires import without them, but both are resolved *at import
time* and cannot be filled in afterwards without re-importing:

:doc:`time_zone_import_time_zones`
    Without the time zone areas every fire is dated in ``Europe/Lisbon``, which is the
    zone the whole dataset falls in anyway — so this matters less here than for a
    worldwide source. It is still the difference between a resolved zone and an assumed
    one.

:doc:`ocha_import_admin_boundaries`
    Without the boundaries no fire gets a country.

Where the data comes from
-------------------------

The ICNF publishes the layers through the WFS of its ``BDG`` GeoServer, and the archives
are that server's ``SHAPE-ZIP`` export of them:

.. code-block:: text

   https://si.icnf.pt/geoserverplinia/BDG/ows?service=WFS&version=1.0.0
       &request=GetFeature&typeName=BDG:ardida_2024&outputFormat=SHAPE-ZIP

Every archive carries that request in a ``wfsrequest.txt`` beside the shapefile, which is
how a downloaded file says which layer it is. There are twenty: three multi-year layers
covering 1975-2008, then one per year.

Four properties of this dataset shape the mapping
--------------------------------------------------

The attributes change half way through
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is the whole difficulty of the source. The layers differ not in the values they
publish but in *which attributes exist at all*:

.. list-table::
   :header-rows: 1
   :widths: 26 12 62

   * - Layers
     - Features
     - Attributes
   * - ``ardida_1975_1989`` … ``ardida_2013``
     - 47,960
     - ``Ano``, ``AreaHaSIG`` — and no other field in the file
   * - ``ardida_2014`` … ``ardida_2024``
     - 20,475
     - the full 22: the identifiers, the times, the location, the cause, the areas

The poverty of the older layers is real at the source, not an artefact of the export —
the WFS ``DescribeFeatureType`` for ``ardida_1975_1989`` declares those two fields and
nothing else. The 1975-1999 layers also only map fires of 5 ha or more; from 2000 on the
small ones are mapped too, which is why a count of fires per year is not comparable
across 1999.

Rather than two mappings, or a branch on the year, the import **normalises the staging
table**: after ``ogr2ogr`` has loaded whatever the file holds,
:func:`~src.apps.imports.wildfires.portugal_icnf.import_wildfires.normalise_staging_columns`
brings it to
:data:`~src.apps.imports.wildfires.portugal_icnf.import_wildfires.STAGING_COLUMNS`,
adding every attribute the file did not have and converting every one it landed in a type
the mapping cannot read. One mapping then covers both eras.

.. note::

   The type conversion is not pedantry. GDAL's PostgreSQL driver renders any field that
   declares a width as ``NUMERIC(width, scale)``, so ``Ano: Integer (9.0)`` arrives as
   ``numeric(9,0)`` — and ``make_date`` has no ``numeric`` overload. A date field whose
   every value is empty is not recognised as a date at all and arrives as text. Both
   would fail at the moment of use, on a layer nobody happened to test.

Even a modern layer has fires with nothing but a year
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

901 of the 20,475 features of 2014-2025 are polygons the ICNF could not match to a record
in the fire database, so they carry the year and the area and nothing else, exactly like a
1975 feature: 141 in 2014, 348 in 2016, down to none in 2023 and 2024. The era of a layer
is therefore not a reliable guide to what a *row* has — which is why the model records it
per row rather than per layer.

The times were lost in the export, and the duration was not
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``DH_Inicio``, ``DH_1Interv``, ``DH_Fim`` and ``Edicao`` are ``xsd:dateTime`` at the
source. A shapefile's DBF has no datetime type, so the ``SHAPE-ZIP`` export truncated all
four to dates. The same fire, both ways:

.. code-block:: text

   archive:  DH_Inicio 2024-01-31    DH_Fim 2024-02-01    Duracao_m 402
   WFS:      DH_Inicio 2024-01-31T20:03:00    DH_1Interv 2024-01-31T20:50:00
             DH_Fim    2024-02-01T02:45:00    Edicao     2024-11-17T08:44:00

So the import stores the date at local midnight and marks the row ``day``. It does not
ask the WFS for the rest: that is a separate application against a separate source, and
doing it inside a bulk import would put tens of thousands of requests onto the ICNF's
server for data already sitting on disk.

``Duracao_m`` survives intact, and on a ``day`` row it is strictly better information
than the stored instants: a fire with ``duration_minutes = 97`` whose stored start and
end are a day apart burnt for an hour and a half across midnight.

About one polygon in a hundred is invalid
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

179 of the 12,654 in ``ardida_1975_1989``, 111 of the 3,150 in ``ardida_2013``, none at
all in ``ardida_2024``. They are repaired with ``ST_MakeValid`` before either geometry is
stored, and the result goes through ``ST_CollectionExtract(..., 3)`` because the repair
can leave a ``GEOMETRYCOLLECTION``. A polygon degenerate enough to be repaired away to
nothing is left out rather than stored as an empty multipolygon, and the count is
reported.

Dates: instant, zone and precision
----------------------------------

The instant-plus-zone rule is the project's own (see :mod:`src.data_model.wildfire`), and
is applied here as everywhere. What is specific to this dataset is that a row also says
**how much of its date the provider actually published**, in
:attr:`~src.providers.icnf.wildfire.IcnfWildfire.date_time_precision`:

.. list-table::
   :header-rows: 1
   :widths: 14 30 56

   * - Value
     - ``start_date_time`` is
     - When
   * - ``year``
     - 1 January of ``year``, local midnight
     - The layer publishes no date. **48,860 of 68,435 rows.**
   * - ``day``
     - the published date, local midnight
     - Read from an archive that publishes ``DH_Inicio``.
   * - ``minute``
     - the published instant
     - Only reachable from the WFS; nothing this import writes is ever ``minute``.

.. warning::

   A ``year`` row's start is the 1st of January because that is the only instant a year
   supports, **not because anything happened that day**. 71% of the dataset is in that
   state, so an average, a histogram or a seasonality analysis that does not filter on
   ``date_time_precision`` will be wrong by up to twelve months for three rows in four.

   The alternative — leaving ``start_date_time`` ``NULL`` — would have meant making the
   column nullable on the generic model for every provider. The placeholder plus an
   explicit precision keeps the constraint and keeps the fact.

The geometry is stored twice
----------------------------

``ogr2ogr`` loads the polygons in the CRS the ICNF publishes them in, EPSG:3763 (ETRS89 /
Portugal TM06), and the mapping keeps them:

.. code-block:: text

   icnf_wildfire.perimeter_etrs89_tm06   the repaired polygon, EPSG:3763, as published
   wildfire.perimeter                    ST_Transform(that, 4326)

This is not redundancy. EPSG:3763 is a projected national grid in metres, so ``ST_Area``
on it is an area in square metres and matches what ``AreaHaSIG`` says; the same call on
EPSG:4326 is on degrees and means nothing without a geodesic function. Reprojection is
also not free and not lossless — going to 4326 and back does not return the published
coordinates — so a query that needs the national grid needs it stored, not derived.

Deriving the 4326 copy from the stored 3763 one, rather than loading each separately, is
what guarantees the two are the same geometry rather than two computations that could
disagree.

The character set has to be supplied
------------------------------------

The archives carry a ``.cst`` file naming the encoding as ``ISO-8859-1``. That is a
GeoServer convention; the file GDAL reads is ``.cpg``, and there is none. Read without
being told, every accented name comes back mangled:

.. code-block:: text

   default:              Viseu D<?>o Laf<?>es      S<?>o Pedro do Sul
   -oo ENCODING=...:     Viseu Dão Lafões          São Pedro do Sul

The importer passes the encoding explicitly. The damage it prevents is silent — mangled
text is still a valid string, and would sit in the database looking like data.

Re-running an import
--------------------

``Cod_SGIF`` is unique where it is present, but 48,861 of the 68,435 features publish no
identifier of any kind — and nothing else identifies them either, not even within one
layer: ten pairs share a year and a burnt area to fifteen decimal places. There is
therefore no row-level "have I seen this before".

Re-running is controlled **a layer at a time**, through
:attr:`~src.providers.icnf.wildfire.IcnfWildfire.source_layer`:

* a layer already in the database is **skipped**, so re-running the whole directory
  after adding one newly published year imports only that year;
* ``--replace`` deletes what a layer loaded before and imports it again.

.. code-block:: bash

   # the ICNF has revised 2024; reload just that layer
   python3 -m src.apps.imports.wildfires.portugal_icnf.import_wildfires \
       -s ardida_2024.zip --replace

That second form is worth knowing about, because the ICNF does revise published years:
fires of 2024 carry ``Edicao`` dates into March 2025.
:attr:`~src.providers.icnf.wildfire.IcnfWildfire.edition_date_time` is what tells you
whether a year is still moving.

The cause classification
------------------------

``Causa_Cod``, ``Causa_Tipo`` and ``Causa_Desc`` become rows of
:doc:`../providers/icnf_fire_cause` rather than three columns repeated on every one of the
18,955 classified fires: a classification is a thing in its own right, and the repetition
is what a lookup table is for.

.. warning::

   **The code is not the key.** The ICNF has reused four of them for different causes,
   all in the 2025 layer:

   .. code-block:: text

      126  2014-2024  Queimadas de sobrantes florestais ou agrícolas
           2025       Queimadas extensivas - Penetração em áreas de caça e margens dos rios_
      127  2014-2024  Queimadas de sobrantes florestais ou agrícolas
           2025       Queimadas extensivas - Limpeza de caminhos, acessos e instalações_
      128  2014-2023  Queimadas de sobrantes florestais ou agrícolas
           2025       Queimadas extensivas - Protecção contra incêndios_
      129  2014-2024  Queimadas de sobrantes florestais ou agrícolas
           2025       Queimadas extensivas - Outras_

   So there are 97 codes but **101 classifications**, and the unique key is the whole
   ``(code, type, description)`` triple. A code with two meanings gets two rows, and a
   fire joins on all three columns so it links to the meaning *its own layer* published.
   The import reports the situation once the layers are in:

   .. code-block:: text

      WARNING  4 cause code(s) name more than one classification (126 x2, 127 x2,
               128 x2, 129 x2). Both meanings are stored and each fire links to its
               own, but grouping fires by Causa_Cod rather than by cause_id would
               merge them.

   That last sentence is the practical consequence: **group by** ``cause_id``, not by
   ``Causa_Cod``.

The table is **not seeded**. The import inserts whatever triples the layer it is reading
actually contains, so a classification the ICNF adds — a new code, or a new meaning for an
old one — arrives with the first fire that uses it. The English comes from the translation
tables beside the model; a string missing from them is stored untranslated and reported:

.. code-block:: text

   WARNING  No English for 2 cause term(s), stored untranslated: 'Categoria inventada',
            'Descrição que ainda não existe'. Add them to src.providers.icnf.fire_cause.

An existing row is left alone rather than rewritten, so a translation added to the
database by hand survives the next import.

What is stored as published
---------------------------

The Portuguese is never translated away, only translated *beside*: ``Causa_Tipo`` and
``Causa_Desc`` keep their published wording and gain ``type_en``/``description_en``. The
same applies to the administrative names, which are stored exactly as the ICNF spells
them — including the one place that costs something:

.. warning::

   ``PI_Distrit`` spells Viana do Castelo two ways in 2014-2016, ``"Viana Do Castelo"``
   and ``"Viana do Castelo"``, so eighteen districts come back as nineteen names.
   Grouping by the name splits that district in two.
   :attr:`~src.providers.icnf.wildfire.IcnfWildfire.dicofre_code` — the six-digit INE
   code — is the reliable key, and is stored as text so that ``"030415"`` keeps its
   leading zero.

The five areas are all kept, in hectares as published. ``AreaHaSIG`` is measured from the
polygon and ``AreaHaSGIF`` is what the fire database recorded — different measurements of
the same fire, not copies — and the three land-type areas sum to ``AreaHaSGIF`` exactly.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.portugal_icnf.import_wildfires
   :members:
   :show-inheritance:
