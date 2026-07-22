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
    perimeter it adds the ignition point and the Atlas's measurements of how the fire
    spread — size, duration, speed, dominant direction, land cover, GFED region — each
    kept in the units it was published in. Imported by
    :doc:`applications/gfa_import_wildfires`.

.. note::

   The GFA ``fire_ID`` **is** unique, unlike the GWIS one: it carries the year, and within
   a year it repeats only across the parts of one multipart fire, which the import
   collects into a single row. It is therefore constrained ``UNIQUE``, and the GFA import
   *is* idempotent — a second run of the same file imports nothing.

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

   providers/gfa_wildfire
   providers/gwis_wildfire
   providers/ocha_admin_boundary
