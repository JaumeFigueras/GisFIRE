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

Metaclass
^^^^^^^^^

A dedicated metaclass generates coordinate columns, validated properties and PostGIS
geometry columns from a class-level ``__location__`` declaration, and keeps coordinate
sets in different EPSG systems in sync automatically. It also generates timezone-aware
datetime properties.

Mixins
^^^^^^

Mixins provide reusable functionality across models:

- **Location** — geospatial coordinates (X, Y) for one or more EPSG codes.
- **Date/Time** — timezone-aware date/time fields with comparison support.
- **Timestamp** — an automatic UTC record-creation timestamp.

Generic and provider-specific models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Generic domain models (``DataProvider``, ``Lightning``, ``Thunderstorm``,
``WeatherStation``, ``Variable``, ...) use polymorphic inheritance; provider-specific
subclasses add the columns particular to each data source.

.. note::

   Per-module API reference pages are generated from the source with autodoc as the
   models are ported from GisFIRE2 into ``src/data_model/``.
