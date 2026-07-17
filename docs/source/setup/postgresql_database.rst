PostgreSQL Database
===================

.. contents::
   :local:
   :depth: 1

Overview
--------

GisFIRE stores its data in a **PostgreSQL 15+** database with the **PostGIS** extension
enabled for spatial types. The models are mapped with SQLAlchemy and GeoAlchemy2, and
the geometry columns use PostGIS ``Geometry`` types.

An independent PostgreSQL cluster is recommended for improved isolation from other
services on the development machine.

Requirements
------------

- PostgreSQL 15 or above.
- The PostGIS extension available to the target database.

.. note::

   Detailed cluster creation, role and extension setup steps will be documented here as
   the schema is ported. The test suite does not need a permanent database: it spins up
   an ephemeral PostgreSQL instance per run (see :doc:`../testing`).
