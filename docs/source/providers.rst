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
    :attr:`~src.providers.icnf.wildfire.IcnfWildfire.date_time_precision` does.

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
   providers/gfa_ignition
   providers/gfa_wildfire
   providers/gwis_wildfire
   providers/icnf_provider
   providers/icnf_wildfire
   providers/icnf_fire_cause
   providers/ocha_admin_boundary
