Data Model
==========

.. contents::
   :local:
   :depth: 1

Overview
--------

The GisFIRE project needs a way to describe the entities involved in wildfire analysis —
lightning strikes, meteorological data, thunderstorms, wildfire ignitions — and to store
them in a spatial database. This is the **data model**.

The model is built on the general characteristics of each entity and the specifics of
the different data providers, so an object-oriented approach is used: generic domain
models with provider-specific subclasses.

What is a Data Model?
---------------------

A data model describes:

- The entities in the system (for example ``Lightning``, ``WeatherStation``,
  ``Thunderstorm``).
- The relationships between these entities.
- The properties and data types of each entity.
- Any constraints or business rules.

Here it is implemented in code with an ORM,
`SQLAlchemy <https://www.sqlalchemy.org>`_, and its spatial companion
`GeoAlchemy2 <https://geoalchemy-2.readthedocs.io>`_ on top of PostgreSQL/PostGIS.

Building blocks
---------------

Declarative base
^^^^^^^^^^^^^^^^^

Every ORM model inherits from a single :class:`~src.data_model.Base`, a plain
SQLAlchemy 2.0 :class:`~sqlalchemy.orm.DeclarativeBase` subclass (typed
:class:`~sqlalchemy.orm.Mapped` / :func:`~sqlalchemy.orm.mapped_column` columns).
Importing a model module registers its table on
:attr:`Base.metadata <sqlalchemy.orm.DeclarativeBase.metadata>`, from which the
schema is created directly
(:meth:`Base.metadata.create_all() <sqlalchemy.schema.MetaData.create_all>`) — there
are no hand-written SQL DDL files to keep in sync.

Generic and provider-specific models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Generic domain models (:class:`~src.data_model.data_provider.DataProvider`,
``Lightning``, ``Thunderstorm``,
``WeatherStation``, ``Variable``, ...) use polymorphic inheritance; provider-specific
subclasses add the columns particular to each data source.

API reference
-------------

Each model lives in its own module under ``src/data_model/`` and has its own reference
page, generated from the source with autodoc. New models get a page added to the list
below as they are ported.

:doc:`data_model/base`
    The declarative base class every ORM model inherits from. It collects the table
    definitions so the database schema can be created from the models.

:doc:`data_model/data_provider`
    A source of data ingested by GisFIRE (a weather service, a lightning-detection
    network, ...). Provider-specific data tables reference it, so data can only be
    attached to a known provider.

.. toctree::
   :maxdepth: 1
   :hidden:

   data_model/base
   data_model/data_provider
