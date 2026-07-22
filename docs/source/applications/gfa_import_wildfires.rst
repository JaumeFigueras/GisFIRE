Import GFA wildfire perimeters
==============================

Imports the *Global Fire Atlas* fire perimeters into
:class:`~src.providers.gfa.wildfire.GfaWildfire` rows — one per fire, with the generic
columns in ``wildfire`` and the Atlas measurements in ``gfa_wildfire``.

.. contents::
   :local:
   :depth: 2

Usage
-----

Migrate the database first — ``gfa_wildfire`` is created by a migration, not by the
importer — then point it at the directory the shapefiles were unpacked into:

.. code-block:: bash

   make migrate
   python3 -m src.apps.imports.wildfires.gfa.import_wildfires -d /path/to/SHP_perimeters/

or import a single year with ``-s``:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gfa.import_wildfires \
       -s GFA_v20260408_perimeters_2021.shp

Unlike the GWIS download, the Atlas ships **loose shapefiles**, one per year, rather than
one archive each — so ``-d`` globs ``*.shp`` in the directory. A ``.zip`` is accepted too,
and read in place without unpacking.

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import these first
------------------

Neither is required, and the fires import without them, but both are resolved *at import
time* and cannot be filled in afterwards without re-importing:

:doc:`time_zone_import_time_zones`
    Without the time zone areas every fire is dated in UTC rather than in local time.

:doc:`ocha_import_admin_boundaries`
    Without the boundaries no fire gets a country.

Three properties of this dataset shape the mapping
--------------------------------------------------

One fire is several features
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The shapefiles have geometry type ``Polygon``, not ``MultiPolygon``. A fire whose burnt
area is in several pieces is therefore published as **several features sharing one**
``fire_ID``, repeating every attribute — the same ignition point, the same ``size``, the
same dates — and differing only in geometry.

The import groups by ``fire_ID`` and collects the parts into one ``MULTIPOLYGON``, so one
fire is one row. This matters beyond tidiness: ``size`` is the size of the *whole* fire
repeated on each part, so ``SUM(size)`` over ungrouped features silently over-counts.

The attributes are aggregated with ``min()``, which is not a choice about which value to
keep — the parts carry identical values, so every aggregate returns the same answer and
``min()`` is simply the cheapest way to write "the value they all share".

``fire_ID`` is a real key, and is used as one
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It encodes the year — ``2xxxxxxx`` for 2002 through ``26xxxxxxx`` for 2026 — so it does
not collide between files, and once the multipart features are grouped it does not repeat
within one either. ``gfa_wildfire.gfa_id`` is therefore ``UNIQUE``, and the import
**skips fires it already holds**:

* re-running it is a no-op that reports ``0 imported``, not a second copy;
* adding a newly published year to a database holding the earlier ones is the normal way
  to use it, and needs no special flag.

This is the opposite of :doc:`gwis_import_wildfires`, whose identifier names genuinely
different fires when it repeats and which consequently cannot skip anything and warns
instead.

About one perimeter in six is invalid
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The polygons are traced around MODIS pixels and self-intersect where the trace doubles
back on itself — 12,357 of the 84,496 features in the 2026 file, 15%. They are repaired
with ``ST_MakeValid`` on the way in, so that the country join here and everything
downstream is safe against ``TopologyException``.

.. note::

   The repair can split a bowtie into two polygons, so its result goes through
   ``ST_CollectionExtract(..., 3)`` for the same reason as in
   :doc:`time_zone_import_time_zones`: what comes back may be a ``GEOMETRYCOLLECTION``,
   which the column rejects. A trace degenerate enough to be repaired away to nothing
   stores ``NULL`` rather than an empty multipolygon.

   The stored geometry is therefore not byte-identical to the published one for those
   15%.

Dates and country
-----------------

``start_date`` and ``end_date`` are bare ``yyyy-mm-dd`` strings meaning local midnight,
exactly as GWIS publishes them, so the same rule applies — they are resolved to instants
and the zone is kept alongside as provenance (see :mod:`src.data_model.wildfire`). The end
of a fire is the last second of its end date, ``23:59:59`` local.

Both the zone and the country come from the **ignition point**, built from the published
``lat``/``lon`` and stored on :attr:`~src.providers.gfa.wildfire.GfaWildfire.ignition_point`:

.. code-block:: sql

   ST_Contains(boundary.geometry, ignition_point)

That is cheaper than intersecting the perimeter, never ambiguous for a fire that straddles
a border, and is the fire's own reported origin rather than something derived from its
shape.

.. warning::

   This differs from :doc:`gwis_import_wildfires`, which attributes a fire to the country
   holding the **largest share of its perimeter**. The two providers therefore answer
   "which country" by different rules, which matters when comparing per-country totals
   between them: a large fire that ignites just inside one country and burns mostly into
   its neighbour is counted differently by each.

What is stored as published
---------------------------

The measurements keep the Atlas's own units and are named for them — ``size_km2``,
``perimeter_km``, ``speed_km_day``, ``spread_km2_day``, ``fire_line_km``,
``duration_days`` — so a row can be checked against the published file without arithmetic.
Note that ``size_km2`` is what GFA published and is *not* the geodesic area of the stored
perimeter.

The two sentinels are kept verbatim rather than translated to ``NULL``:

``direction = 'none'``
    No direction dominated; ``direc_frac`` is 0. Common — 46% of the 2026 file.

``landcover = 'Unclassified'``
    The Atlas classifies land cover for 2002-2023 only, so *every* fire in a later file
    carries this. It is also a genuine class within the classified years, and translating
    it away would conflate "not provided" with "provided as unclassified".

API reference
-------------

.. automodule:: src.apps.imports.wildfires.gfa.import_wildfires
   :members:
   :show-inheritance:
