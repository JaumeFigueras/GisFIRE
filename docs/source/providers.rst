Data Providers
==============

.. contents::
   :local:
   :depth: 1

Overview
--------

The generic models in :doc:`data_model` describe what every wildfire, lightning strike
or weather observation has in common, independently of where it came from. Real data
always arrives from a concrete **provider** with its own identifiers, its own extra
fields and its own quirks. Those live here, under ``src/providers/``, one subpackage per
provider.

A provider model **subclasses** the generic one and adds only what the provider
contributes beyond it. Nothing generic is repeated, so a query on the generic model
still finds provider rows, and code that only cares about "a wildfire" never needs to
know which provider it came from.

Joined table inheritance
------------------------

Provider models use SQLAlchemy's **joined table inheritance**: the subclass gets its own
table, whose primary key is also a foreign key to the parent table's primary key. A row
is therefore split across two tables — the generic columns in the parent, the
provider-specific ones in the child — and reading it joins them.

.. code-block:: text

   wildfire                          gwis_wildfire
   ------------------------          ---------------------
   id            (PK)      <-------- id       (PK, FK)
   type          'gwis_wildfire'     gwis_id  (indexed, NOT unique)
   data_provider_id
   start_date_time
   end_date_time
   time_zone
   perimeter
   admin_boundary_id
   created_at / updated_at

The ``type`` discriminator column on the parent records which subclass a row belongs to,
so loading a :class:`~src.data_model.wildfire.Wildfire` returns the right subclass
instance without asking for it.

Why joined rather than single table
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

With single-table inheritance every provider's columns would be piled into one wide
table and each of them would have to be nullable, because a row from one provider has
nothing to put in another provider's columns. That loses the ability to say *this column
is mandatory for this provider*. With joined tables, ``gwis_wildfire.gwis_id`` can be —
and is — ``NOT NULL``, on a table where every row is a GWIS fire and so must have one.

The cost is a join on read and two inserts on write. For the volumes here that is a
good trade.

.. note::

   The split does have one real limit: a constraint cannot span the two tables. GWIS
   fires would be uniquely identified by ``(Id, IDate)``, but ``Id`` is on the child and
   the start date on the parent — and the parent's is a converted instant rather than the
   date as published. See :doc:`providers/gwis_wildfire`.

Registering the tables
^^^^^^^^^^^^^^^^^^^^^^

Importing :mod:`src.providers` registers every provider table on
:attr:`src.data_model.Base.metadata`. Anything that needs the *whole* schema — the
Alembic environment, the test fixtures — imports ``src.providers`` as well as
``src.data_model``; importing only the latter yields a schema with the provider tables
missing. A new provider module must be imported in ``src/providers/__init__.py`` or
Alembic autogenerate will not see it.

GWIS
----

The `Global Wildfire Information System <https://gwis.jrc.ec.europa.eu>`_ publishes
several products; each one is its own
:class:`~src.data_model.data_provider.DataProvider` row, distinguished by ``product``.

:doc:`providers/gwis_wildfire`
    The *Global Wildfire Database* product: wildfire perimeters. It supplies a start and
    end date, a perimeter in EPSG:4326 and its own identifier — the first three are
    already the generic model's, so the subclass adds only the identifier. Imported by
    :doc:`applications/gwis_import_wildfires`.

.. warning::

   The GWIS ``Id`` is **not unique**: across the 23,299,416 fires of GlobFire v3 there
   are 359 identifiers naming two genuinely different fires. It is therefore indexed but
   not constrained, and the GWIS import cannot be made idempotent — see
   :doc:`providers/gwis_wildfire` for what follows from that.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/gwis_wildfire

GFA
---

The `Global Fire Atlas <https://zenodo.org/records/17669692>`_ derives individual fire
events from the MODIS MCD64A1 burnt area product, publishing perimeters and ignition
points as separate sets of shapefiles, one per year.

:doc:`providers/gfa_wildfire`
    The *Fire Atlas* product: fire perimeters. Beyond the generic model's dates and
    perimeter it adds the Atlas's measurements of how the fire spread — size, duration,
    speed, dominant direction, land cover, GFED region — each kept in the units it was
    published in, and a link to the fire's ignition. Imported by
    :doc:`applications/gfa_import_wildfires`.

:doc:`providers/gfa_ignition`
    The point of origin the Atlas publishes for the same fire. It is a
    :doc:`../data_model/ignition` of its own, not a column on the wildfire — the point
    describes where the fire began, not its burnt area — and the two share the ``fire_ID``
    that matches them. Built from the same perimeter import; there is no separate ignitions
    import.

.. note::

   The GFA ``fire_ID`` **is** unique, unlike the GWIS one: it carries the year, and within
   a year it repeats only across the parts of one multipart fire, which the import
   collects into a single row. It is therefore constrained ``UNIQUE`` on both the wildfire
   and the ignition, and the GFA import *is* idempotent — a second run of the same file
   imports nothing.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/gfa_ignition
   providers/gfa_wildfire

ICNF
----

The Portuguese `Instituto da Conservação da Natureza e das Florestas
<https://www.icnf.pt>`_ publishes the national burnt area cartography — the *áreas
ardidas* layers — through the WFS of its ``BDG`` GeoServer: three multi-year layers
covering 1975-2008, then one per year.

:doc:`providers/icnf_wildfire`
    The *Áreas Ardidas* product: burnt area polygons. Beyond the generic model's dates
    and perimeter it adds the fire's identifiers in the two national systems, the
    administrative location it started at, its duration, its burnt area split by land
    type, and the polygon as published in EPSG:3763. Imported by
    :doc:`applications/icnf_import_wildfires`.

:doc:`providers/icnf_fire_cause`
    The cause classification, as a lookup table: 97 codes naming 101 distinct
    classifications, each with the published Portuguese type and description and an
    English translation beside them.

:doc:`providers/icnf_provider`
    The constants the two models and the importers share.

Three things about this dataset are worth knowing before using it. All three were checked
against the twenty published layers, 68,435 features in total:

The attributes change half way through, and so do the rows
    1975-2013 publishes two attributes — the year and the burnt area. 2014-2025 publishes
    twenty-two. But 901 features *within* those later years are unmatched polygons
    carrying the old two, so the layer a row came from does not tell you what it has.
    :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.date_time_precision` does.

71% of the fires have no date, only a year
    48,860 of 68,435. Their ``start_date_time`` is the 1st of January of their year
    because the ``NOT NULL`` column needs an instant, and ``date_time_precision`` is
    ``year`` to say that nothing happened that day. Any analysis over time has to filter
    on it.

    Even the dated ones are dated to the day and no finer: the archives are
    ``SHAPE-ZIP`` exports and a DBF has no datetime type, so the published times were
    truncated on the way out. ``duration_minutes`` is the only trace of them left.

The perimeter is stored twice, in EPSG:3763 and EPSG:4326
    Deliberately. The national grid is in metres, so an area computed on it is the number
    Portuguese forestry works in; EPSG:4326 is what makes the fire comparable with a GWIS
    or GFA one. Neither can be derived from the other for free, so both are kept, and the
    4326 one is derived from the stored 3763 one at import so they cannot disagree.

.. note::

   There is no :doc:`../data_model/ignition` for an ICNF fire, unlike a GFA one. The
   ``PI_`` attributes name where the fire started — district, municipality, parish,
   place — but the layers publish **no ignition coordinate**, so there would be no point
   to put in it.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/icnf_provider
   providers/icnf_wildfire
   providers/icnf_fire_cause

EGIF
----

The Spanish `MITECO <https://www.miteco.gob.es>`_ compiles the *Estadística General de
Incendios Forestales*, the national fire statistics, from the **PIF** (*Parte de Incendio
Forestal*) — the official report form filled in for every forest fire in the country.
It is published through a public search service:

    https://servicio.mapa.gob.es/incendios/Search/Publico

:doc:`providers/egif_wildfire`
    The report itself: where the fire is filed administratively, what it burnt split by
    land type, its cause and — for an intentional fire — its motivation.

:doc:`providers/egif_ignition`
    The *punto de inicio*, the point the fire started at. A
    :doc:`data_model/ignition` of its own, as for GFA, and the reason this dataset is
    worth importing at all.

:doc:`providers/egif_wildfire_report`
    The blocks of the report that only the XML export publishes, as a one-to-one child
    of the wildfire.

:doc:`providers/egif_fire_cause` and :doc:`providers/egif_fire_motivation`
    The two code catalogues, each with the Spanish label published beside the code.

:doc:`providers/egif_provider`
    The constants the models and the importers share.

Five things about this dataset are worth knowing before using it. All five were checked
against a national Excel export of 13,656 fires (campaigns 2022 and 2023) and the XML
export of Barcelona 2020:

There is no perimeter, and there never will be
    EGIF is an administrative statistic. It publishes a burnt *area* in hectares, split
    by land type, and no polygon in any of its exports. An EGIF fire's
    :attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` for good.

    What it does publish, alone among the Iberian datasets here, is a **coordinate for
    the ignition point** — which is what the ICNF data lacks and what makes the two
    complementary rather than redundant.

The two exports are read together, in a fixed order
    The **Excel** "resumen" is one flat row per fire and prints codes *with their
    labels* — ``[213]  Quema de restos agrícolas (viñas,etc)``. The **XML** carries the
    full report with the numeric identifiers the Excel drops, but every code in it is
    bare. Since the service's own catalogue endpoints are behind a login, the Excel is
    the only public source of the labels, so an Excel export seeds the two lookup tables
    and the XML import resolves its codes against them.

    Both key on ``numeroparte``, so the same fire lands on one row whichever export it
    came from. Whether it has been seen in the XML is recorded by the presence of an
    :doc:`providers/egif_wildfire_report` row and nothing else.

A published year is never complete
    Every fire the service exports is in state *Cerrado Revisión*, and a region's fires
    appear only once that region has closed them. The 2022 campaign in the export
    checked here is missing Cantabria and Navarra; 2023 is missing Cataluña,
    Extremadura and Canarias; Navarra is absent from both. The 2022 forest total of
    243,610 ha is well short of the ~306,000 ha eventually published.

    So a year has to be re-exported and re-imported later, and the import is an upsert
    on the report number rather than an append.

The cause families are not what the paper form suggests
    ``idcausa`` is hierarchical, but ``400`` is *Intencionado*, ``500`` *Desconocida*
    and ``600`` *Reproducido* — one family further along than the order printed on the
    form implies. Reading it the other way would file 7,117 intentional fires of 13,656
    as unknown.

    ``idmotivacion`` is a **different code space** that overlaps: ``400`` is
    *Motivación desconocida* there. The two are separate tables and must never be joined
    on the code alone.

Times are local, and not all in the same zone
    Both exports publish naive wall-clock readings. They are resolved against
    ``Europe/Madrid``, except in the Canary Islands, which are an hour behind. And
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **detection**
    instant: nothing in EGIF says when the fire actually started.

.. note::

   ``v_egif_wildfire`` is the one wildfire view whose geometry is a ``POINT``. Every
   other one exposes a perimeter; EGIF has none, so the fire is mapped where it started,
   by joining the ignition. See :doc:`setup/database_migrations`.

.. warning::

   The interval between detection and extinction is unreliable at the tail. The export
   contains a 0.02 ha fire stamped as burning for exactly 365 days and a 0.10 ha one for
   141 days, alongside genuine multi-week fires such as the 22,233 ha Sierra de la
   Culebra. Treat anything beyond about a week as suspect rather than as data.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/egif_provider
   providers/egif_ignition
   providers/egif_wildfire
   providers/egif_wildfire_report
   providers/egif_fire_cause
   providers/egif_fire_motivation

DARPA
-----

The Catalan `Departament d'Agricultura, Ramaderia, Pesca i Alimentació
<https://agricultura.gencat.cat>`_ publishes the perimeters of the forest fires of
Catalonia, one shapefile per year from 1986 on, in EPSG:25831.

This is GisFIRE's **first regional perimeter source**, and it exists because EGIF has
none. EGIF is the national statistic and publishes a burnt *area* in hectares, on a
report form; what the autonomous regions publish is the shape. The two datasets are
complements rather than alternatives, and neither can answer the other's question.

:doc:`providers/darpa_provider`
    The dataset itself: the two character sets, the three shattered years, the six
    formats of ``CODI_FINAL``, ``GRID_CODE``, and the layer names that must not be
    imported.

:doc:`providers/darpa_wildfire`
    The perimeter model. The date and the polygon are already the generic model's, so the
    subclass adds the published code, the published date, the municipality, how many
    polygons the fire was published as, the perimeter on the Catalan grid, and the link to
    the EGIF *parte*. Imported by :doc:`applications/darpa_import_wildfires`.

Four things about this dataset are worth knowing before using it. All four were checked
against the thirty-nine published layers, 4,712 features in total:

A fire is many polygons, and the import dissolves them
    The layers were vectorised from a raster and never dissolved. 1991, 1993 and **1994**
    publish fragments — one 1994 fire is 1,309 separate features — and 4,533 burnt
    features are 860 fires. The count each row was assembled from is kept in
    :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.part_count`, because a
    perimeter made of 1,309 fragments is a different kind of evidence from one digitised
    as a single ring.

``CODI_FINAL`` is not a key; ``(code, date)`` is
    ``303/22N`` names a fire in Lleida on 19 June 2022 and another in Figueres on 7 July.
    The pair is unique across the whole archive — 860 of them for 859 codes — and a
    unique constraint on the code alone would have merged two unrelated perimeters at
    import time with nothing left to notice it by.

``GRID_CODE`` is a raster class, not an attribute of the fire
    ``2`` is burnt and ``0`` is background. The 179 background features are not fires,
    and they are also where every defect in the dataset lives: the 152 with no code and no
    date, and the twenty whose ``DATA_INCEN`` is ``2,152543589*``. Filtering on it does the
    whole of the data cleaning in one predicate.

There is no burnt area, and there never will be
    The layers publish ``CODI_FINAL``, ``DATA_INCEN``, ``MUNICIPI`` and ``GRID_CODE`` and
    no hectares. The hectares for a Catalan fire are on the EGIF *parte* for the same
    fire, which is much of the point of the link below.

The file names are not regular, and the year comes from them
    ``incendis10`` is 2010 where every other loose file uses four digits, every zip uses
    two, and ``incendis22.zip`` holds a shapefile called plainly ``incendis``. So
    :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.source_layer` is
    canonicalised to ``incendis`` plus four digits, from the name of the file being
    imported rather than of the layer inside it — which is what lets a zip and a loose
    shapefile of the same year replace each other instead of doubling it.

.. warning::

   The ``.dbf`` files are **not all in the same character set** and none carries a
   ``.cpg``: 1986-1988 and 1991-2012 are ISO-8859-1, 1989, 1990 and 2013-2024 are UTF-8.
   Each declares itself in the DBF language-driver byte — ``0x57`` on every Latin-1 file
   and ``0x00`` on every UTF-8 one, exactly — and GDAL reads it, so the import passes **no**
   ``ENCODING`` option. Forcing one, as the ICNF import has to, corrupts half the archive
   whichever way it is forced.

.. note::

   :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id` is the
   link to the Spanish *parte* for the same fire, and the import **never fills it in**.
   :doc:`applications/darpa_bind_egif_wildfires` does, afterwards, and is the only thing
   that writes it or the three columns that account for it — ``match_method``,
   ``match_confidence`` and ``matched_at``.

   Those three exist because the bindings are not all the same kind of claim. All 529 of
   the ten-digit codes (1997 onwards) are exactly an EGIF
   :attr:`~src.providers.spain_egif.wildfire.EgifWildfire.report_number` — year, Catalan
   INE province, four-digit sequence, the year always matching the layer — and matching on
   those is an identity, not a guess. But a third of the archive predates that form and
   uses four others, thirteen recent fires use a code EGIF never issued, and those fall
   back to a date narrowed by province and municipality name. An analysis that could not
   tell the two apart would be claiming a precision half its rows do not have.

   There is no :doc:`data_model/ignition` for a Catalan fire either: the layers publish a
   perimeter and a municipality and no ignition coordinate. EGIF does publish a point,
   which is one more thing the link makes reachable — and, from 1998 on, the last
   tiebreak the binding has.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/darpa_provider
   providers/darpa_wildfire

REDIAM
------

The `Red de Información Ambiental de Andalucía <https://portalrediam.cica.es>`_ publishes
the perimeters of the forest fires of Andalusia from 2008 on, in ETRS89 / UTM 30N — as one
shapefile per year **and** one shapefile holding the whole series.

The **second regional perimeter source**, and the complement of :doc:`providers/egif_wildfire`
in the same way :doc:`providers/darpa_wildfire` is. Read that section first: the argument
for having regional perimeters at all is made there and is not repeated here.

:doc:`providers/rediam_provider`
    The dataset itself: the combined layer and the yearly ones, the two shapes of
    ``CODIGO``, the three published burnt areas, the duplicated records, and the CRS.

:doc:`providers/rediam_wildfire`
    The perimeter model. The date and the polygon are already the generic model's, so the
    subclass adds the published code and date, the municipality and province, the three
    burnt areas, how many features the fire was published as, the perimeter on the
    Andalusian grid, the link to the published ignition point and the link to the EGIF
    *parte*. Imported by :doc:`applications/rediam_import_wildfires`.

:doc:`providers/rediam_ignition`
    Where the fire started, for the 201 fires of 2021-2024 that publish a coordinate.

Five things about this dataset are worth knowing before using it. All five were checked
against the published files, 962 features in the combined layer:

``CODIGO`` **is** the EGIF report number
    Not "is shaped like one": all 962 features decode, always to an Andalusian INE
    province and always to the year of their own ``FECHA_INC``, and the 907 fires have 907
    distinct report numbers. Two published shapes — ten bare digits to 2024,
    ``IIFF`` plus ten digits in 2025 — and six 2019 codes that write the sequence with
    three digits. :func:`~src.providers.andalusia_rediam.egif_report_number` reads all
    three.

    This is the sharpest contrast with Catalonia, whose code took six forms over forty
    years and is an identifier only from 1997.

962 features are 907 fires
    55 codes are published twice, 2 in 2024 and 53 in 2025. In 54 of the 55 the two rows
    are the same fire with the same footprint, differing only in the case of the names;
    in the remaining one — ``IIFF2025210122`` — they are two different mappings, 363.8 ha
    and 517.4 ha, which dissolve into 527.5 ha. Two pairs also disagree about the
    published burnt areas. The import dissolves on ``(code, date)``, keeps the count in
    :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.part_count` and reports
    the disagreements.

There *is* a burnt area, and it is not the perimeter
    ``SUP_ARBOLA``, ``SUP_MATORR`` and ``SUP_PASTIZ`` — wooded, scrub and grassland
    hectares — on every feature of every year. Over the 907 fires they sum to 152,696 ha
    against 165,582 ha of mapped perimeter, which is what one expects of three vegetation
    classes against an outline that also encloses what is none of them. Both are kept and
    neither is reconciled with the other.

An ignition point, for four years
    ``X_INIC`` and ``Y_INIC`` are published in the yearly layers of 2021-2024 and nowhere
    else — not in the combined layer, not in 2025. 201 fires of 907 have one, and **88 of
    the 201 fall inside their own perimeter**; the rest are outside by a metre to three
    kilometres, one of them by 19.5 km. Two observations, stored as two rows, neither
    corrected.

.. warning::

   **The published ``.prj`` resolves to EPSG:3042, and the geometry is stored as
   EPSG:25830.** They are the same projection — ETRS89 / UTM zone 30N — but 3042 declares
   a *northing-easting* axis order, while the coordinates in the files are
   easting-northing, as GDAL itself reports (``Data axis to CRS axis mapping: 2,1``).

   Storing 3042 would store a declaration the geometry does not obey and invite PROJ to
   swap the axes on the next transform, so the import asserts 25830. The fixture in the
   import's tests writes the published ``.prj`` verbatim, so that this is checked rather
   than assumed.

.. note::

   :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id` is the
   link to the Spanish *parte* for the same fire, and the import **never fills it in** —
   exactly as for Catalonia, and for the same reason: the binding is a later application
   and an ``UPDATE`` rather than a migration.

   ``match_method``, ``match_confidence`` and ``matched_at`` come with it, and
   :doc:`applications/rediam_bind_egif_wildfires` is what writes all four.
   :data:`~src.providers.andalusia_rediam.wildfire.MATCH_METHODS` is the vocabulary, and
   a check constraint enforces it — added in a revision of its own once the rules were
   worked out, rather than guessed at when the table was created.

   **Six methods, not the Catalan eight.** ``date`` and ``date_name`` are the branches
   that cascade takes when a code carries no province, and every Andalusian code carries
   one, so a fire whose code did not decode is left unbound rather than bound on a date
   alone. 759 of the 907 perimeters are bound and 749 of those on the published
   identifier — 98.7%, against Catalonia's 77%.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/rediam_provider
   providers/rediam_wildfire
   providers/rediam_ignition

Greek Fire Service
------------------

The `Hellenic Fire Service <https://www.fireservice.gr>`_ — *Πυροσβεστικό Σώμα Ελλάδας* —
publishes the Greek national fire statistic, *Δασικές Πυρκαγιές*, as a set of Excel
workbooks: one per year from 2013, plus one holding 2000 to 2012 in thirteen sheets.
**260,194 fire records over twenty-six years**, and GisFIRE's first source outside the
Iberian peninsula.

It is the same *kind* of dataset as :doc:`providers/egif_wildfire` and not the same kind
as GWIS, GFA, DARPA or REDIAM. What the service publishes is a record of an
**intervention** — who was called, where, when they arrived and when they left, what
burnt and what was sent to it — and never a shape. Read the EGIF section first: the
argument for why an administrative statistic gets no perimeter column is made there and
is not repeated here.

:doc:`providers/greece_ffa_provider`
    The dataset itself: the fifteen workbooks, the six column arrangements, the header
    that is two rows deep (four in 2025), and the two functions any reader of it needs —
    the header fold and the is-this-a-location test.

:doc:`providers/greece_ffa_wildfire`
    One published record. Adds the year and source sheet, the two identifiers the recent
    years carry, six administrative and locator names, the eight burnt areas, the
    thirteen deployment counts and the link to the published point. Imported by
    :doc:`applications/greece_ffa_import_wildfires`.

:doc:`providers/greece_ffa_ignition`
    Where the service was engaged, for the six years that publish a coordinate.

What makes this dataset unlike the others already in GisFIRE:

Nothing identifies a fire
    ``Α/Α ΕΓΓΡΑΦΗΣ`` and ``Α/Α ENGAGE`` begin in **2020**, so 201,948 of the 260,194
    records carry no identifier of any kind — not a code, not a sequence, not a row
    number. And where the record number exists it is not unique: 512 of its 57,734 values
    are used by more than one row.

    Neither table therefore carries a unique constraint, and an import replaces a
    **year** rather than upserting a row. There is nothing to upsert on.

Three quarters of it has no coordinate
    ``X-ENGAGE`` and ``Y-ENGAGE`` arrive in 2020, in EPSG:4326. 54,491 fires have a
    point; the other 205,703 are locatable only by name — prefecture, municipality,
    forest district, locality. This is the largest wildfire dataset in the project that is
    mostly unmappable, and any spatial analysis over it is an analysis of its last six
    years.

No cause, in any year
    Nothing in any of the twenty-six sheets says why a fire started. There is no
    equivalent of EGIF's ``idcausa``, so there is no catalogue to seed and **no lightning
    question this dataset can answer** — worth stating plainly, since answering it for
    Spain is what :doc:`providers/egif_fire_cause` exists for.

Areas in στρέμματα, stored as hectares
    Eight land-cover columns, and a στρέμμα is 1,000 m² — a tenth of a hectare. The
    conversion is exact and done at import, so a Greek fire and a Spanish one are
    comparable without a per-provider unit. There is no published total and none is
    stored.

A deployment block, which nothing else has
    Thirteen counts from 2011 on: firefighters, ground units, volunteers, soldiers and
    others; four kinds of vehicle; and the aircraft by type, Canadairs and PZLs
    included. The only measurement of a *response* rather than an event anywhere in
    GisFIRE — and a measure of what was sent, which is a function of what was available
    and what was feared as much as of what burnt.

.. warning::

   **The 2025 file is a different dataset wearing the same name.**
   ``agrotodasikes_pyrkaies_2025.xlsx`` is *αγροτοδασικές* — agricultural **and** forest —
   where every earlier file is *δασικές*. It publishes ``Κατηγορία Συμβάντος``, a size
   class the others do not have, and **1,255 of its 9,043 rows are** ``ΨΕΥΔΗΣ
   ΑΝΑΓΓΕΛΙΑ`` — *false alarm*, a call-out that found no fire at all. That is 14% of the
   year.

   They are imported rather than dropped, because a row that says "this was not a fire"
   can be filtered and a discarded one cannot be recovered. Any query that counts or
   measures fires must exclude them::

      WHERE incident_category IS DISTINCT FROM 'ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ'

   ``IS DISTINCT FROM`` and not ``<>``: the column is ``NULL`` for every year before
   2025, where ``<>`` evaluates to ``NULL`` and silently drops the other twenty-five.

.. note::

   Header cells must be matched through
   :func:`~src.providers.greece_ffa.normalise_column`, never by ``==``. The published
   headers wrap long names with a hyphen (``ΒΥΤΙΟ- ΦΟΡΑ`` beside ``ΒΥΤΙΟΦΟΡΑ``,
   ``ΜΗΧΑΝΗ-ΜΑΤΑ`` beside ``ΜΗΧΑΝΗΜΑΤΑ``), spell accents inconsistently, and — in the
   2025 file — write ``Α/Α ENGAGE`` with a **Latin** ``A`` where every other year uses the
   Greek ``Α`` (U+0391). The two render identically and compare unequal, which is the kind
   of mismatch that imports a whole year with an empty column and no error.

   Reading by column *position* is not an option either: the sheets have 16, 17, 31, 32,
   36, 38 and 39 columns depending on the year.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/greece_ffa_provider
   providers/greece_ffa_wildfire
   providers/greece_ffa_ignition

NBAC and NFDB
-------------

`Natural Resources Canada <https://cwfis.cfs.nrcan.gc.ca>`_ publishes two national
wildfire datasets through the Canadian Wildland Fire Information System, and GisFIRE
imports both. They are **one agency and two products** — two
:class:`~src.data_model.data_provider.DataProvider` rows sharing a name, which is exactly
what that table's ``(name, product)`` uniqueness is for — and GisFIRE's first source
outside Europe.

**NBAC**, the *National Burned Area Composite*: 52,276 published polygons over 1973-2025,
dissolving to **51,818 fire events** and 132.7 million hectares of mapped burn, one zipped
shapefile per year. Compiled by the FireMARS system, which picks the best available
polygon for each fire from Natural Resources Canada's own satellite products and the
agencies' own mapping.

**NFDB**, the *Canadian National Fire Database — Agency Fire Data*: **448,602 points**
over 1930-2025 in one 1.1 GB shapefile, as thirteen provincial, territorial and Parks
Canada agencies filed them. The import reads 1973 onwards, to line up with NBAC.

They cover the same country and the same fires and their burnt-area totals differ by 34
million hectares — 166.5 against 132.7 — because one records what an agency reported and
the other measures what a satellite could see afterwards. Neither corrects the other.

:doc:`providers/nbac_provider`
    The composite: its sources, the boundary-split polygons, the two date pairs, the three
    causes and why the CRS has to be asserted.

:doc:`providers/nbac_wildfire`
    One dissolved fire event. Adds the published identifiers, how the burn was mapped and
    by whom, the four published dates, the cause, the two published areas, the
    administrations it burnt in, the polygon in EPSG:3978 and the link to the NFDB report.

:doc:`providers/nfdb_provider`
    The agency archive: the thirteen contributors, the identifiers that do not identify,
    and the dirt.

:doc:`providers/nfdb_wildfire`
    One agency fire report. No perimeter, ever.

:doc:`providers/nfdb_ignition`
    Where the fire was reported, in EPSG:3978 as published and EPSG:4326 on the generic
    model.

.. note::

   **195,240 of the NFDB fires are natural-cause** — by a wide margin the largest
   lightning-attributable set in GisFIRE, and every one of them has a coordinate and a
   date. NBAC classifies 26,311 of its fire events the same way.

   Neither ``Natural`` nor ``N`` is a **lightning** category. The NBAC metadata glosses it
   *"Ignition source by natural cause. Most often lightning."* — the relationship
   :doc:`providers/icnf_fire_cause`'s ``Natural`` has to lightning, and emphatically not
   the one EGIF's ``100 — Rayo`` has. Anything counting lightning fires here is counting
   natural-cause fires and has to say so.

What makes these two unlike the datasets already in GisFIRE:

A fire is a ``GID``, not a polygon
    NBAC cuts its perimeters at provincial, territorial and national park boundaries, so a
    fire that crossed one is published as several features sharing a ``GID``. 458 of the
    52,276 polygons are such pieces. The import dissolves them, sums the published areas,
    counts the parts and joins the administrations with ``"; "`` —
    :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.crosses_admin` being what tells
    a reader to expect a list rather than having to look for a separator.

Two date pairs, and sometimes neither
    NBAC publishes satellite hotspot dates *and* agency-reported dates, independently, and
    for some fires neither: 102 of 1980's 530, 39 of 2023's 2,244. The import resolves the
    start from the agency's date, then the hotspot's, then 1 January of the published year,
    and records both which it used and how much of it is real.

Nothing identifies an NFDB fire
    ``NFDBFIREID`` has 446,918 distinct values over 448,602 rows and ``FIRE_ID`` only
    338,313. Both are indexed, neither is constrained.

Thirteen agencies, thirteen standards
    British Columbia files 156,554 of the NFDB points and Prince Edward Island 55; the
    start years run from 1930 to 2018 and ``FIRE_TYPE`` means something different in each
    agency's hands. The published summary is frank about it: *"Data completeness and
    quality vary among agencies and between years."*

.. warning::

   **The NBAC ``.prj`` does not declare its EPSG code.** It is a bare
   ``Canada_Lambert_Conformal_Conic`` — NAD83, standard parallels at 49° and 77°, false
   origin at 49°N 95°W — which is EPSG:3978 exactly, and the dataset's own metadata names
   ``EPSG:3978`` as its reference system. The NFDB shapefile declares it properly.

   So the import **asserts** 3978 rather than reading it, the guard
   :doc:`providers/rediam_wildfire` needs for the opposite reason. A projection GDAL cannot
   name is one PROJ may later decide to interpret differently.

.. note::

   :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id` is the link
   from a perimeter to the agency report for the same fire, and the import **never fills
   it in** — exactly as for Catalonia and Andalusia, and in the same direction: the shape
   points at the record the fire is filed under. ``match_method``, ``match_confidence``
   and ``matched_at`` come with it.

   **No check constraint lists the methods yet.** Unlike ``CODI_FINAL`` and ``CODIGO``,
   which turn out to be EGIF report numbers, the two Canadian datasets share **no
   published identifier at all** — so a binding will rest on date, place and geometry, and
   a vocabulary invented now would be a guess frozen into the schema.

.. note::

   1972 is not imported. The published NBAC metadata describes a 1972-2025 series of
   52,610 features; the service distributes no 1972 archive, and the 53 yearly files
   available hold 52,276. Nothing depends on the first year, and no lightning data of that
   period exists to attribute it against.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/nbac_provider
   providers/nbac_wildfire
   providers/nfdb_provider
   providers/nfdb_wildfire
   providers/nfdb_ignition

CONAFOR
-------

The `Comisión Nacional Forestal <https://datos.gob.mx/busca/organization/conafor>`_
publishes Mexico's national burnt-area cartography, *Incendios Forestales*, as **one
zipped shapefile per year**. 45,914 polygons over 2010-2023, and GisFIRE's first Latin
American source.

It is a cartography and not a statistic, so it belongs with :doc:`providers/icnf_wildfire`
and :doc:`providers/nbac_wildfire` rather than with EGIF or the Greek Fire Service: every
record is a shape. What sets it apart from those two is that the shape is already in
**EPSG:4326** — all fourteen archives carry a byte-identical ``.prj`` — so there is no
national grid to keep alongside it and this is the one perimeter provider with a single
geometry column and a single QGIS view.

:doc:`providers/conafor_provider`
    The dataset itself: the fourteen archives, the schema that changes every year, and
    the five readers that absorb it.

:doc:`providers/conafor_wildfire`
    One published polygon. Adds the key, the year and source layer, the state and
    municipality, the *predio*, the classification attributes, the total burnt area and
    its six strata, and the link to the cause. Imported by
    :doc:`applications/conafor_import_wildfires`.

:doc:`providers/conafor_fire_cause`
    The 141 cause classifications, reconciled from sixty-four published spellings and
    translated.

What makes this dataset unlike the others already in GisFIRE:

The published key is unique, so a row can be upserted
    ``CLAVEINC`` is ``YY-EE-NNNN`` — year, INEGI state, sequence — in all 45,914 rows, and
    takes 45,909 distinct values. The five repeats are in 2021 and are *exact* duplicate
    features, identical down to the geometry, so dropping the second copy loses nothing.

    Every other perimeter provider here is re-imported a layer at a time because it has to
    be: ICNF publishes no identifier on 48,861 features, GWIS's repeats, the Greek archive
    has none at all. This is the first that can do ``ON CONFLICT (fire_code)``.

    The middle pair of the key is the INEGI state code, and it agrees with the published
    ``ESTADO`` in every single row — which is what makes it worth parsing, since the names
    do not agree with each other: 34 spellings for 32 states, *Distrito Federal* and
    *Ciudad de México* being one state either side of 2016.

No two consecutive years have the same attributes
    Fifty-eight published names across fourteen files. ``TIPVEG`` is also ``TIPVEGE``,
    ``TIP_VEG`` and ``TIPO_DE_VE``. **Two layers are wholly their own**: 2012, with
    ``CLAVE`` for the key and four attributes no other year has, all of them the string
    ``"0"`` in all 224 of its rows; and 2015, which renames almost everything —
    ``CLAVE_DEL`` for the key, ``TIPO_DE_IN``, ``TIPO_DE_VE``, ``TIPO_DE_IM``,
    ``ANP_HECTAR``, and ``ARBADULTO`` / ``RENUEVO`` / ``ARBUSTIVO`` / ``HERBACEO`` /
    ``SUELOORG`` for five of the six strata. ``CAUSAESP`` runs 2010-2019 and stops. The
    six strata run 2010-2021, lose ``SUELORG_HA`` in 2020 and vanish entirely in 2022.

    All of it is absorbed by :data:`~src.providers.mexico_conafor.FIELD_ALIASES` and
    :func:`~src.providers.mexico_conafor.field_value`, so nothing downstream branches on
    the year and a layer that publishes less simply leaves more of the row ``NULL``.

    The *order* of those aliases matters, and 2015 is why: in that layer ``ESTADO`` holds
    the numeric state code and the name is in ``ESTADO_1``, so listing ``ESTADO`` first
    would store ``"32"`` as the name of a Mexican state for 1,105 fires.

``CLAVEMUN`` is not a national code
    It is the municipality's number *within its state*, 1 to 570 — 570 being exactly the
    number of municipalities in Oaxaca — and means nothing without ``state_code`` beside
    it. The national INEGI key is the two composed, two digits and three::

        LPAD(state_code::text, 2, '0') || LPAD(municipality_code::text, 3, '0')

    It is published from 2018 on; the 13,872 fires before that have a name and no code.

The one attribute that says how good a perimeter is, is published once
    ``POLIGONO``, in the 2023 layer and no other: ``IMAGEN`` for a perimeter digitised
    from satellite imagery, ``COORD`` for one surveyed on the ground or from the air,
    ``AQSPPIF`` for the agency's aerial product. It is ``NULL`` on 38,401 of the 45,914
    rows, and it is stored anyway — the year that does publish it shows the mix, 69%
    digitised and 25% surveyed, which is the only quantitative statement about perimeter
    quality anywhere in this dataset.

.. warning::

   **The 2010 areas do not describe the 2010 polygons.** ``AREA_HA`` is the polygon's own
   geodesic area from 2016 on — median ratio 1.000, four rows in five within 1% — and
   agrees to within a few percent for 2011-2014. In 2010 the median ratio is **3.0** and
   the 90th percentile **65**: ``10-01-0001`` reports 20 ha on a polygon of 1.08 ha,
   ``10-01-0004`` reports 2.5 ha on 20.2 ha. Those 311 polygons are five-to-twelve-vertex
   sketches drawn beside a separately reported field figure, and neither number can be
   derived from the other.

   Anything measuring burnt area across the series must either start at
   :data:`~src.providers.mexico_conafor.FIRST_YEAR_WITH_MEASURED_AREA` or measure from the
   geometry — and either way must not average the 2010 column in with the rest.

   The feature counts step by an order of magnitude at the same point (628 in 2014 against
   3,244 in 2016) for a related reason: before 2016 CONAFOR published only the fires it
   had drawn, and from 2016 it publishes the season.

.. warning::

   **Some of the published text is mojibake in the file itself**, not in the reader. The
   archives declare UTF-8 in a ``.cpg``, GDAL honours it, and what comes out is already
   corrupt — ``'BolaÃƒÂ±os'`` for *Bolaños*, ``'CaÃƒÆ’Ã‚Â±ada Verde'`` for *Cañada Verde*,
   worst in 2021 and 2022. The same names are written correctly in the same column in
   other years. There is no encoding that reads these files right.

   2019 and 2022 also carry a find-and-replace accident in ``TIPVEG`` where the letter *i*
   became the word *bosque*: ``'Bosque de Pbosqueno Encbosqueno'`` is *Bosque de Pino
   Encino*. Nine rows.

   Nothing repairs any of it. The strings are stored as published, and the reconciled forms
   on :doc:`providers/conafor_fire_cause` are what a query groups by.

.. note::

   **The 2015 archive is distributed separately from the other thirteen** and is easy to
   miss. A run without it is not silently wrong — the key ``CLAVE_DEL`` that layer uses is
   in :data:`~src.providers.mexico_conafor.FIELD_ALIASES`, and the year simply does not
   appear in any report — but it is a year of 1,105 fires absent from every total.

   Two CSV files sit beside the shapefiles in the published directory and are **not
   imported**: they are CONAFOR's tabular statistic, a different product with no geometry.
   One of them reaches 2025, which the cartography does not; closing that gap means
   importing a 2025 archive when CONAFOR publishes one, not importing a different
   product.

.. note::

   No layer of any year publishes a **time of day**, so every stored instant is local
   midnight and
   :attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.date_time_precision` is
   ``day`` on every row. Mexico spans four time zones and abolished daylight saving outside
   the northern border strip in 2022, which is why the importer resolves the zone from the
   geometry and stores it by *name*: the same published wall clock is UTC-5 in June 2019
   and UTC-6 in January 2023.

   There is **no ignition point**. CONAFOR publishes a perimeter and a *predio* and never a
   coordinate for where the fire started, exactly as the ICNF does — so there is no
   :doc:`../data_model/ignition` for a CONAFOR fire.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/conafor_provider
   providers/conafor_wildfire
   providers/conafor_fire_cause

INAB
----

The `Instituto Nacional de Bosques <https://sig.inab.gob.gt>`_ publishes Guatemala's fire
reports, *Monitoreo de Incendios Forestales*, through the ArcGIS REST server of the
*Sistema Integral de Información para la Gestión del Fuego*. **4,615 reports over
2023-2026**, and GisFIRE's first Central American source.

There is no file to download and no WFS to read: the layer is fetched by
:doc:`applications/inab_download_wildfires`, which is why this is the only provider whose
data arrives through an application of its own.

:doc:`providers/inab_provider`
    The dataset itself: the four published vocabularies, the department codes, the national
    grid that has no EPSG code, and the three readers the models share.

:doc:`providers/inab_wildfire`
    One published report. Adds the identifier, what became of the report, who reported it
    and how, the administrative location, the protected areas and the link to the point.

:doc:`providers/inab_ignition`
    Where the fire was reported to be — on **every** record — plus the coordinates as the
    operator typed them.

What makes this dataset unlike the others already in GisFIRE:

It publishes no size at all
    Not a perimeter, not a hectare figure, not a land-cover split. :doc:`providers/egif_wildfire`
    and :doc:`providers/greece_ffa_wildfire` publish no perimeter but do publish burnt areas;
    this publishes neither, and is the first source here of which that is true.

    So there is no ``area_ha`` on the model, no perimeter on any row, and **nothing any
    report can sum**: :doc:`applications/inab_wildfire_statistics` keeps the three hectare
    columns the other seven burnt-area reports have and leaves every cell of them empty.
    Anything wanting burnt area in Guatemala has to go elsewhere; the burn-scar layers on
    the same server are a single season of polygons rather than an archive.

A row is a report, and one fire can be reported twice
    57 published pairs share an exact coordinate and an exact minute, differing only in
    which institution called it in and — twice — in what they concluded. ``global_id`` is
    unique because a *report* is unique. Deduplicating is an analysis that can state its
    rule, not an import that would have to guess one.

Every record has a point, and the times are real
    All 4,615 carry an EPSG:4326 point, and ``fecha_hora_incendio`` is the minute the
    report came in. In local time the hourly histogram peaks between 13:00 and 16:00 — the
    afternoon fire peak — so these are observations and not a date rounded to midnight.

The national grid has no EPSG code
    ``sistema_proyeccion`` says ``GTM``, Guatemala Transverse Mercator, and the EPSG
    registry has no such system: its Guatemalan entries are the Ocotepeque 1935 Lambert
    zones. :data:`~src.providers.guatemala_inab.GTM_PROJ` is the definition, verified by
    reprojecting the published points onto the published typed coordinates — exact to the
    metre on the best records.

.. warning::

   **140 of the 4,615 records are false alarms** — ``estado_aviso = 'falso'``, meaning
   there was no fire — and 90 more are ``no_verificado``, meaning nobody went to look. They
   are imported rather than dropped, because a record saying *this was not a fire* can be
   filtered and a discarded one cannot be recovered.

   Any query that counts or maps fires must exclude the first group and decide about the
   second::

      WHERE report_status IS DISTINCT FROM 'falso'

   ``IS DISTINCT FROM`` and not ``<>``: the column is ``NULL`` on the four records that
   carry no attributes at all, where ``<>`` evaluates to ``NULL`` and would drop them
   silently.

   The flag earns its keep in an unexpected way: **all three published points that fall
   outside Guatemala are already ``falso``**. Two are longitudes that lost their minus sign
   — ``+90.47`` puts a fire in Jutiapa into Cambodia — and the third is 200 km inside
   Honduras. The provider's own quality flag removes every one of them without this project
   having to invent a coordinate.

.. warning::

   **The published layer carries personal data, and none of it is imported.**

   ``reportado_por`` and ``telefono`` are the name and telephone number of whoever reported
   each fire: 1,786 distinct names, 1,008 numbers, **1,969 distinct pairs**, most of them
   private individuals rather than officials. ``created_user`` and ``last_edited_user`` are
   INAB staff accounts.

   :data:`~src.providers.guatemala_inab.PERSONAL_FIELDS` names all four so the omission is a
   decision on the record rather than an oversight, and a test asserts that no column of
   either model holds one. Nothing analytical is lost — no question about fire is answered
   by a reporter's phone number — and
   :attr:`~src.providers.guatemala_inab.wildfire.InabWildfire.institution` keeps which
   *organisation* reported it, which is the part that has meaning.

.. note::

   **The end times are in a layer that is not modelled.** ``informes`` on the same service,
   5,812 rows, holds when the first ground and air crews arrived and when the fire was
   controlled and extinguished — the only end-time data Guatemala publishes. Until it is
   modelled, :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL`` on every
   INAB fire.

   It is a second model rather than a column: there are more *informes* than fires, one fire
   being reported on several times, so those times are a one-to-many relationship.

.. warning::

   **An unfilled text field is sometimes ``null`` and sometimes ``""``, in the same
   column**, mixed with no pattern:

   .. code-block:: text

                         null    ""    filled
      nombre_ap_1          80   3,080   1,455
      tipo_incendio     2,681   1,445     489
      finca             3,373     203   1,039

   An import that stores what it is handed records 3,080 fires as being inside a protected
   area called ``""`` — which counts as filled in any ``IS NOT NULL`` afterwards and is
   invisible in a spot check. Every text attribute has to go through
   :func:`~src.providers.guatemala_inab.blank_to_none`. The numeric columns are unaffected:
   JSON has no empty number.

.. note::

   ``tipo_incendio`` — inside or outside forest — is the only classification of the fire
   itself, and it is filled on **489 records, 10.6%**. Anything grouping by it is describing
   one record in ten.

   ``municipio`` carries the national INE code inside the slug (``rio_hondo_1903`` is
   department 19, municipality 03), which is what a join to a Guatemalan boundary layer
   needs. Four slugs carry a truncated code naming the wrong department; those 22 records
   get a ``NULL`` code rather than a guessed one, and keep their department name.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/inab_provider
   providers/inab_wildfire
   providers/inab_ignition

CONAF
-----

The `Corporación Nacional Forestal <https://www.conaf.cl>`_ publishes Chile's fire data as
**two products**, both from its own incident record and both organised by *temporada*:

* the seasonal **reports** — 23 shapefiles, **95,868 fires**, 2010-2011 to 2024-2025 —
  each a point, a cause and fourteen burnt-area figures;
* the *incendios de magnitud* **perimeters** — 13 shapefiles, 781 features dissolving to
  **743 fires**, 2013-2014 onwards — the mapped shapes of the fires that reached roughly
  200 hectares.

.. warning::

   **This is Chile's CONAF, not Mexico's CONAFOR.** *Corporación Nacional Forestal* and
   *Comisión Nacional Forestal* differ by two letters and both are real agencies with
   data in GisFIRE. The table prefixes are ``conaf_`` and ``conafor_``, and every module
   in both packages opens by naming its country.

:doc:`providers/conaf_provider`
    The report archive: the fire season, the four date formats, the coordinate triple, the
    two grids, the null tokens and the dirt, plus the readers the models share.

:doc:`providers/conaf_wildfire`
    One seasonal report. Adds the season, the office's number and name, who filed it, the
    administrative location, the cause, the fourteen areas and the link to its point.

:doc:`providers/conaf_ignition`
    Where the fire was reported — on **every** record — on whichever of Chile's two UTM
    grids it was published on, with the published coordinate triple beside it.

:doc:`providers/conaf_fire_cause`
    The cause classification both products share, and the reconciliation of CONAF's **two
    taxonomies**.

:doc:`providers/conaf_magnitud_provider`
    The perimeter product: the threshold, the dissolve key and the binder's vocabulary.

:doc:`providers/conaf_magnitud_wildfire`
    One mapped fire, its two areas, its grid and its link back to the report.

What makes this dataset unlike the others already in GisFIRE:

It is the first provider with **two** projected grids
    Chile has no single national projected CRS. The mainland is EPSG:32719 (UTM 19S) and
    Rapa Nui is EPSG:32712 (UTM 12S), five thousand kilometres and seven zones apart, so
    both the ignition and the perimeter carry two nullable geometry columns and a ``CHECK``
    that exactly one is filled. :doc:`providers/nfdb_ignition` needs one because Canada
    publishes on one grid; this needs two, and a ``COALESCE`` of them would be metres added
    to metres on different planes.

Half of it has no date at all
    Eight of the fifteen mainland seasons publish no start time, so **49,470 fires — 51.6%**
    — are dated to 1 July of their season because that is the only thing known about when
    they burnt. ``date_time_precision`` says so on every row, and every report over this
    provider carries a ``Dated`` count beside its ``Fires`` count.

The cause taxonomy was renumbered **and the numbers reused**
    ``4.1`` is *incendios de causa desconocida* to 2022-2023 and *faenas forestales* from
    2023-2024. Ten more categories were renamed into narrower or broader ones. See the
    danger note in :doc:`providers/conaf_fire_cause`; the short version is *group on the
    name, never on the code*.

Nothing in it is a key
    ``NUMERO_REG`` repeats within a season and within a región — 6,884 fires and 5,975
    distinct ``(CODREG, NUMERO_REG)`` pairs in 2021-2022 — and ``NOM_INCEN`` is a place
    name. Neither model constrains an identifier, which is the same position
    :doc:`providers/nfdb_wildfire` is in.

.. warning::

   **Both products are the same fires, and both are in ``wildfire``.** Every one of the 743
   perimeters is also one of the 95,868 reports. A query filtered only by provider *name*
   counts those 743 twice; filter by ``data_provider_id`` or by the polymorphic ``type``.

.. note::

   The perimeter archive is **not exhaustive**: 2021-2022 has 97 reports of 200 ha or more
   and 62 perimeters. A perimeter is evidence a fire was mapped, and its absence is not
   evidence a fire was small.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/conaf_provider
   providers/conaf_wildfire
   providers/conaf_ignition
   providers/conaf_fire_cause
   providers/conaf_magnitud_provider
   providers/conaf_magnitud_wildfire

OCHA
----

The UN `Office for the Coordination of Humanitarian Affairs
<https://www.unocha.org>`_ publishes *Global International Boundaries (OSM)*, a single
worldwide layer of country outlines built from OpenStreetMap data. GisFIRE imports it as
administrative level 0: the countries.

The dataset, and the GeoPackage the importer reads, come from HDX:

    https://data.humdata.org/dataset/global-international-boundaries-osm

:doc:`providers/ocha_admin_boundary`
    The *Global International Boundaries* product. Its name, geometry and nesting level
    are already the generic model's, so the subclass adds the identifiers and metadata
    around them: the ISO country codes, the UN M49 region, the statehood status and the
    provenance of the geometry.

Six properties of the source layer are worth knowing about before importing it. They
were checked against the 2025-07-29 release, which has 318 features:

``adm0_id``, not ``fid``, identifies a boundary
    ``fid`` is the GeoPackage's own row number and shifts between releases. ``adm0_id``
    — ``"AND-20250729"``, the source code plus the release date — is stable, unique
    across all 318 features, and is what is stored as the generic ``source_id``. Being
    unique, it means the whole layer can be imported as-is: no filtering is needed to
    satisfy the ``(data_provider_id, source_id)`` constraint.

``iso_3`` is **not** unique
    There are 285 distinct ISO alpha-3 codes for 318 features. An ISO entity made of
    scattered landmasses is published as one feature per landmass: ``ATF`` (French
    Southern Territories) is eight rows, and ``ESP`` is three — ``ESP_1`` the mainland
    and the Balearics, ``ESP_2`` the Canary Islands, ``ESP_3`` the *plazas de soberanía*.
    Do not treat ``iso_3`` as a key, and do not expect a query on it to return exactly
    one row.

    This matters when attributing an event to a country. A point-in-polygon lookup
    returns the *landmass* it fell in, so a fire in Tenerife resolves to
    ``name="Canary Islands (Sp.)"``, not to ``"Spain"``. The country is then
    ``iso_3``/``iso_name`` on that row (``ESP`` / ``Spain``), which is the same for all
    three features. Use ``name`` for where it happened and ``iso_name`` for which
    country it counts against.

``adm0_name`` and ``adm0_name1`` are different things
    ``adm0_name`` is the feature's own name, qualified with its sovereign
    (``"Kerguelen Islands (Fr.)"``); ``adm0_name1`` is the name of the ISO entity the
    feature belongs to (``"French Southern Territories"``), shared by all eight ``ATF``
    rows. They agree for most countries and differ for 118 of the 318 features, so
    treating them as interchangeable silently loses data. The first is the generic
    ``name``, the second is ``iso_name``.

``adm0_name`` is empty for every disputed area
    32 features — Aksai Chin, the Spratly Islands, Bi'r Tawīl, Hans Island and the rest,
    all of them ``status_nm`` *Sovereignty unsettled* — have no ``adm0_name`` at all.
    The field is the name qualified with its sovereign (``"Aruba (Neth.)"``), which is
    precisely what is undefined for a disputed area. ``adm0_name1`` is never empty, so
    the import falls back to it; without that fallback these features cannot be stored,
    since the generic ``name`` is NOT NULL.

``iso_2`` is empty for 36 features
    Disputed and jointly administered areas have no ISO alpha-2 code — Abyei, Jammu and
    Kashmir, Akrotiri and Dekelia among them — although every feature in the layer has an
    alpha-3 code. ``iso_2`` is therefore nullable in the model and ``iso_3`` is not.

``adm0_name2`` is empty, and typed as a number
    Not one feature in the release has a value. The layer types it ``Real``, an artefact
    of an all-NULL column surviving a format conversion, so importing it needs an
    explicit cast to text. It is kept as ``name_alt`` for fidelity.

.. note::

   ``wld_view`` is ``"intl"`` for every feature in this release. The field exists to
   distinguish a contested boundary's international rendering from the renderings of the
   parties involved, but this dataset publishes only the first, so importing it needs no
   filter on the field. Should a later release ship several views, the same country would
   appear more than once and the import would need to choose.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/ocha_admin_boundary

CAOP
----

The `DGT <https://www.dgterritorio.gov.pt>`_ (Direção-Geral do Território) publishes the
*Carta Administrativa Oficial de Portugal*, the country's official administrative map.
GisFIRE imports three of its levels — *distritos*, *municípios* and *freguesias* — as
administrative levels 1 to 3 below the country:

    https://www.dgterritorio.gov.pt/dados-abertos

:doc:`providers/caop_provider`
    The dataset itself: its two hierarchies, its four files and why each edition is a
    data provider of its own.

:doc:`providers/caop_admin_boundary`
    The boundary model. The code, the name, the nesting and the polygon are already the
    generic model's, so the subclass adds the edition, which division it is, the parish's
    simplified name and the NUTS region it belongs to.

It is imported for a reason the other boundary datasets do not share: the ICNF says where
a fire started as administrative codes and names, never as a coordinate, so these
polygons are what locates such a fire. See
:doc:`applications/caop_import_admin_boundaries`.

Four properties of the source are worth knowing before importing it:

Each of the four files is in a different CRS
    The mainland is EPSG:3763 (ETRS89 / Portugal TM06), the island groups EPSG:5014,
    5015 and 5016 (PTRA08 / UTM zones 25N, 26N and 28N). All are ETRS89/PTRA08-based, so
    reprojecting to EPSG:4326 is sub-metre, but there is no single source CRS for the
    country.

The codes nest exactly, and are the hierarchy
    ``dt`` (2 characters) is a prefix of ``dtmn`` (4) is a prefix of ``dtmnfr`` (6),
    without one exception in the 3 259 parishes, and the codes are unique across the four
    files. The tree is built from them by prefix rather than by a spatial containment
    test. ``dtmnfr`` is the DICOFRE the ICNF publishes.

NUTS is a second hierarchy, and it does not nest inside the first
    12 of the 26 NUTS 3 regions span more than one *distrito* — *Tâmega e Sousa* spans
    four. Since
    :class:`~src.data_model.geography.admin_boundary.AdminBoundary` has one ``parent_id``,
    only one hierarchy can be the tree. GisFIRE makes the *distrito* one the tree and
    carries the NUTS region as columns, so grouping by it is a ``GROUP BY`` rather than a
    walk.

There is no Portugal
    The ``nuts1`` layers give *Continente*, *R.A. Açores* and *R.A. Madeira*, never the
    country. The *distritos* are parented to the OCHA level 0 boundary instead, which is
    the only country polygon GisFIRE has — the one place where a boundary's parent comes
    from a different provider.

.. warning::

   Parish boundaries and their codes are **not stable across editions**. The 2013 reform
   merged Portugal's parishes from about 4 260 to some 3 092 and reassigned codes, so a
   DICOFRE from a 2010 fire may name nothing in CAOP 2025, or name a differently shaped
   parish. Each edition is imported as its own data provider so that editions can sit
   side by side and a fire can be matched to the boundaries in force when it burnt.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/caop_provider
   providers/caop_admin_boundary

IGN
---

The `IGN <https://www.ign.es>`_ (Instituto Geográfico Nacional) publishes the *Base de
Datos de Divisiones Administrativas de España*, the national administrative map, through
the CNIG download centre. GisFIRE imports its three polygon levels — *comunidades
autónomas*, *provincias* and *municipios* — as administrative levels 1 to 3 below the
country:

    https://centrodedescargas.cnig.es

:doc:`providers/ign_provider`
    The dataset itself: its padded hierarchy, its two datums, its NUTS columns and what
    the import leaves out.

:doc:`providers/ign_admin_boundary`
    The boundary model. The code, the name, the nesting and the polygon are already the
    generic model's, so the subclass adds the edition, which division it is, the INE
    municipal code and the NUTS region.

Five properties of the source are worth knowing before importing it:

The published layers are INSPIRE, not Spanish
    Fields are ``NATCODE``, ``NAMEUNIT`` and ``CODNUT1``/``2``/``3``. The ``recintos_*``
    layers are the areas; the ``ll_*`` layers are the boundary lines and are not
    imported.

``NATCODE`` nests, but it is padded
    Eleven digits at every level — ``34`` + *comunidad* (2) + *provincia* (2) + INE
    municipal code (5) — zero-filled on the right. A child's code begins with its
    parent's, so the tree is built from the codes, but the padding has to be put back:
    ``left(natcode, 6) || '00000'`` rather than a plain prefix.

Both datums transform to WGS84 without moving a coordinate
    ETRS89 (EPSG:4258) for the peninsula and the Balearics, REGCAN95 (EPSG:4081) for the
    Canaries. Both are geographic, both on GRS80, and both declare a null transformation
    — unlike the CAOP's four projected grids, where reprojection is real work.

NUTS refines the administrative tree instead of crossing it
    ``CODNUT2`` maps one-to-one onto the *comunidad autónoma*, and no NUTS 3 region spans
    more than one province — it equals the province except in three island provinces,
    which it splits one region per island. So unlike Portugal, there is no hierarchy to
    choose between and the NUTS codes are simply columns. The IGN fills ``CODNUT3`` on
    *municipios* only.

81 of the *municipios* are not municipalities
    *Condominios*, *comuneros*, *facerías* and *parzonerías* — land shared between
    municipalities, mapped at the same level with a pseudo-province code of ``53``. They
    are imported: they are real ground that can burn. Excluding them would leave holes in
    the coverage, and without them the count is the INE's 8 132.

.. warning::

   The dataset includes **Gibraltar**, the *plazas de soberanía* off the Moroccan coast
   and the Franco-Spanish condominium of the Isla de los Faisanes, as seven areas the IGN
   types ``Territorio`` rather than ``Municipio``. They are **excluded by default**,
   along with the pseudo *comunidad* and *provincia* that exist only to hold them:
   Gibraltar is a separate country in the OCHA boundaries GisFIRE already imports, so
   keeping it here would put one place in the tree twice under two sovereigns.
   ``--include-territories`` brings all nine back, typed ``territorio``.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/ign_provider
   providers/ign_admin_boundary
