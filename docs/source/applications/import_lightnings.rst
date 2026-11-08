Lightning imports
=================

One importer per detection network, each writing the generic
:class:`~src.data_model.lightning.Lightning` row — one per **stroke** — plus its
provider's own table with the network's location-quality measures and flash grouping. See
:doc:`../providers`. They live under ``src/apps/imports/lightnings/<source>/``::

   src/apps/imports/lightnings/catalonia_meteocat/import_lightnings.py

.. note::

   The administrative boundaries and the time zone areas are resolved *at import time*
   and cannot be filled in afterwards without re-importing, so import them first — see
   :doc:`import_boundaries`.

.. contents::
   :local:
   :depth: 1

Europe
------

:doc:`meteocat_import_lightnings`
    Imports MeteoCat's XDDE lightning strokes — fifteen yearly CSV extracts, **6,156,214
    cloud-to-ground strokes over 2006-2020** — as GisFIRE's first lightning source. Read
    in Python and streamed with ``COPY``, no ``ogr2ogr``. A UTC year is replaced
    wholesale, since nothing identifies a stroke; every flash is numbered
    (``multiplicity``, ``stroke_index``) over the whole file; the first network
    generation's ``0`` sensor count and chi-squared are stored as ``NULL``; the published
    ETRS89 point is kept beside its EPSG:4326 reprojection, and the country is resolved
    against subdivided OCHA boundaries. ``--dry-run`` checks the extracts without a
    database.

.. toctree::
   :maxdepth: 1
   :hidden:

   meteocat_import_lightnings
