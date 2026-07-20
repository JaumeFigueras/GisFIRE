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
   type          'gwis_wildfire'     gwis_id
   data_provider_id
   start_date_time
   end_date_time
   perimeter
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
and is — ``NOT NULL`` and ``UNIQUE``, which is what makes re-importing the same GWIS
record idempotent instead of duplicating it.

The cost is a join on read and two inserts on write. For the volumes here that is a
good trade.

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
    already the generic model's, so the subclass adds only the identifier.

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

Three fields of the source layer are worth knowing about before importing it:

``adm0_id``, not ``fid``, identifies a boundary
    ``fid`` is the GeoPackage's own row number and shifts between releases. ``adm0_id``
    — ``"AND-20250729"``, the source code plus the release date — is stable, and is what
    is stored as the generic ``source_id``.

``wld_view`` can put the same country in the layer twice
    Contested boundaries are published once per *view*: the international one
    (``"intl"``) and those of the parties involved. An import that ignores ``wld_view``
    will either duplicate countries or trip the ``(data_provider_id, source_id)``
    uniqueness constraint. Pick a view.

``adm0_name2`` is usually NULL
    The layer types it as a real number, which is an artefact of an all-NULL column
    surviving a format conversion. It holds an alternative name where there is one and
    is stored as text, in ``name_alt``.

.. toctree::
   :maxdepth: 1
   :hidden:

   providers/gwis_wildfire
   providers/ocha_admin_boundary
