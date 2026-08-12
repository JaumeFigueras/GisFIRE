CONAF ignition
==============

Where a Chilean fire was reported, as CONAF's office filed it. See
:doc:`../data_model/ignition` for the columns it inherits, :doc:`conaf_provider` for the
dataset, and :doc:`conaf_wildfire` for the report each point carries.

Three things about it are worth knowing before using it.

**There are two projected geometry columns, and exactly one is filled.** Chile has no
single national projected CRS: the mainland archives are on EPSG:32719 (UTM 19S, 95,625
points) and the Easter Island ones on EPSG:32712 (UTM 12S, 243 points), which are seven
zones and five thousand kilometres apart. So there is
:attr:`~src.providers.chile_conaf.ignition.ConafIgnition.geometry_utm19s`,
:attr:`~src.providers.chile_conaf.ignition.ConafIgnition.geometry_utm12s` and a ``CHECK``
that ``num_nonnulls`` of the two is 1. This is the first provider in GisFIRE with more
than one — :doc:`nfdb_ignition` stores one ``geometry_lambert`` because Canada publishes
on one grid.

.. warning::

   **A ``COALESCE`` of the two is not a geometry.** The values are metres on different
   grids, and adding them is adding apples to kilometres. A query that wants both
   territories at once wants the parent's EPSG:4326 point, which every row carries.

**The published coordinate is provenance, not a second geometry.**
``UTM_E``/``UTM_N``/``HUSO`` are stored as
:attr:`~src.providers.chile_conaf.ignition.ConafIgnition.utm_easting`,
``utm_northing``, ``utm_zone`` and ``utm_band``, and they are absent on more than half
the archive — 43,636 of 95,868 features publish a readable triple. Where both exist they
agree with the shipped geometry exactly, checked over the whole archive, which is what
licenses treating the geometry as the truth and these as the record. The zone is the one
thing the geometry does not carry: a fire the office worked in zone 18 has been
reprojected into zone 19 to sit in its layer, and ``utm_zone`` is the only trace of that.

**Every published feature has a point.** All 95,868, with no exceptions, which is why
:attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.ignition_id` is ``NOT NULL``.
That is unlike Spain, where half the archive has no coordinate, unlike Greece, where four
fires in five have none, and unlike :doc:`nfdb_ignition`, where a handful do not.

.. warning::

   **This is where the fire was reported, not necessarily where it started.** The points
   are filed by CONAF's regional offices and by the forestry companies' own brigades, and
   the most common published ``INICIO_C`` — the place the fire started — is *camino
   principal* or *camino secundario*: a road. Treat the precision as varying by season,
   by región and by who filed it.

.. automodule:: src.providers.chile_conaf.ignition
   :members:
   :show-inheritance:
