Auxiliary Applications
======================

.. contents::
   :local:
   :depth: 1

Overview
--------

Auxiliary applications are command-line helper tools for database and schema
maintenance rather than domain analysis. Typical examples:

- **Get SQL** — prints the ``CREATE TABLE`` DDL generated from the ORM models for a given
  target, useful to regenerate or verify the hand-written ``.sql`` files against the
  models.
- **Create Data Providers** — seeds the database with the initial set of data providers.

They are argparse-based scripts run as modules::

   python3 -m src.apps.auxiliar.<...>

.. note::

   Individual tool pages are added as these helpers are ported into
   ``src/apps/auxiliar/``.
