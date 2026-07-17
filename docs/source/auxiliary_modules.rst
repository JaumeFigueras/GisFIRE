Auxiliary Modules
=================

.. contents::
   :local:
   :depth: 1

Overview
--------

The project relies on several helper modules that provide cross-cutting functionality to
the data models and applications:

- **Geo** — geographic helpers used by the metaclass and data models to build and convert
  geometries between coordinate reference systems (PROJ/pyproj, Shapely).
- **Exceptions** — project-specific exception classes for well-defined error handling
  (for example wrapping non-2xx HTTP responses from remote APIs).
- **JSON Decoders** — extra behaviour for ``json.loads`` (for example stripping ``None``
  entries returned by some provider APIs for retired/voided records).

.. note::

   Per-module API reference pages are generated from the source with autodoc as these
   modules are ported into ``src/``.
