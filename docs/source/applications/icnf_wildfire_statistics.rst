ICNF wildfire statistics (Portugal)
====================================

Reports the Portuguese ICNF burnt area cartography per year: how many fires there were,
and the smallest single fire, the largest single fire and the total burnt area, in
hectares.

The third of the three burnt-area reports, alongside :doc:`gwis_wildfire_statistics` and
:doc:`gfa_wildfire_statistics`, and deliberately the same shape: same columns, same
grouping, same two output formats, so the three CSVs can be concatenated and compared.

Usage
-----

Over everything, or narrowed to one year:

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.portugal_icnf.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.portugal_icnf.wildfire_statistics \
       --year 2024 --csv 2024.csv --docx 2024.docx

At least one of ``--csv`` and ``--docx`` is required.

The application only reads; it never modifies the database. Settings are read from the
environment (``.env``, see :doc:`../setup/configuration`) and each can be overridden with
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   **There is no** ``--country``. The ICNF publishes one country's fires, so there is
   nothing to select between, and passing it is refused with a message that says so
   rather than argparse silently resolving the prefix to ``--country-source``.

   The **column** stays, for two reasons: it keeps this report's CSV the same shape as
   the other two, and under ``--country-source geometry`` it is not always ``Portugal``
   — which is the point of that option here.

Output
------

=============  ======  =======  ============  ============  ============
Country        Year      Fires  Minimum (ha)  Maximum (ha)  Total (ha)
=============  ======  =======  ============  ============  ============
Portugal       2024       6820          0.51      11485.32     135872.44
Portugal       2023       7541          0.50       8802.11      88214.06
Portugal       Total     68435          0.50      97462.10    4218774.51
=============  ======  =======  ============  ============  ============

.. important::

   The ``Total`` row is **not** a total of every column above it. ``Fires`` and
   ``Total (ha)`` are sums; ``Minimum`` and ``Maximum`` are the smallest and largest fire
   of *any* year in scope.

The ``.csv`` writes bare numbers because it is read by another program more often than by
a person; the ``.docx`` writes them with thousands separators and right-aligned, with the
summary row in bold, because it is not.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.icnf.wildfire.IcnfWildfire.year` — the ``Ano`` the ICNF published,
which is also the layer the fire came from — and **not** the year of ``start_date_time``
as in the other two reports.

That is the same rule reached more directly, and here it matters. **48,860 of the 68,435
fires publish no date at all.** Those rows carry ``date_time_precision = 'year'`` and a
``start_date_time`` of the 1st of January of their year, which is a placeholder
satisfying a ``NOT NULL`` column rather than a claim about the fire. Grouping on it would
in fact work — the year inside the placeholder is the right year — but it would mean
routing 71% of the dataset through a value that exists only because the column could not
be null. ``Ano`` is the published answer, is ``NOT NULL``, and needs no timezone applied.

.. warning::

   The consequence is worth stating plainly: **this report is sound, but a report grouped
   by month or day over the same data would not be.** 71% of these fires would all land
   on the 1st of January. Anything finer than a year has to filter on
   :attr:`~src.providers.icnf.wildfire.IcnfWildfire.date_time_precision` first — see
   :doc:`icnf_resync_wildfires` for the application that puts the real times back.

Where the two disagree — a fire filed under 2022 whose start date falls in 2023 — the
report follows the provider, because a published yearly total is a total of what the
provider filed that year.

.. warning::

   **Fire counts are not comparable across 1999.** The 1975-1999 layers only map fires of
   5 ha or more; from 2000 on the small ones are mapped too. So is the minimum: a 0.50 ha
   minimum in 2024 and a 5.0 ha minimum in 1995 describe the mapping rule, not the fires.
   The totals are much less affected, small fires being small.

How the area is measured
------------------------

The same two ways as the other reports, chosen with ``--area-method``: ``geodesic`` on
the WGS84 ellipsoid (the default) or ``equal-area`` in EPSG:6933. They agree to within
0.003%. See :doc:`gfa_wildfire_statistics` for the measurements behind that.

Why not the CRS the ICNF publishes in
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Tempting, and wrong — which is worth recording, because this is the one dataset of the
three that *has* a published projected geometry to reach for.

The perimeters are stored as published in EPSG:3763 (ETRS89 / Portugal TM06) on
:attr:`~src.providers.icnf.wildfire.IcnfWildfire.perimeter_etrs89_tm06`, a projected
national grid in metres whose ``ST_Area`` reproduces the ICNF's own ``AreaHaSIG``. It is
**not** offered as an area method, because PT-TM06 is a *transverse Mercator* — conformal,
not equal-area — and its distortion away from the central meridian is not negligible for
this dataset:

.. code-block:: text

   the same polygon, geodesic vs EPSG:3763
     Lisbon      (-9.1, 38.7)     +0.017%
     Bragança    (-6.8, 41.8)     +0.030%
     Faro        (-7.9, 37.0)     +0.001%
     Madeira    (-17.0, 32.7)     +1.717%
     Azores     (-28.0, 38.5)     +7.631%

On the mainland it is fine. On the islands it is not, and a report cannot know in advance
that no island fire will ever appear in it. A test asserts the omission stays deliberate.

To reproduce the ICNF's published figures, read them rather than recompute them:

.. code-block:: sql

   -- the published areas beside the measured one
   SELECT year,
          sum(area_ha_gis)                             AS published_sig_ha,
          sum(area_ha_sgif)                            AS published_sgif_ha,
          sum(ST_Area(perimeter::geography) / 10000.0) AS measured_ha
   FROM icnf_wildfire JOIN wildfire USING (id)
   GROUP BY year ORDER BY year DESC;

The published areas are not used
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:attr:`~src.providers.icnf.wildfire.IcnfWildfire.area_ha_gis` (``AreaHaSIG``, measured
from the polygon) and :attr:`~src.providers.icnf.wildfire.IcnfWildfire.area_ha_sgif`
(``AreaHaSGIF``, what the fire database recorded) are kept as published and are **not**
what this reports. They are two independent measurements of the same fire and are worth
having as a check on this one, but a report that mixed them with a measured area would be
comparing three different things in one column.

Which country a fire counts towards
-----------------------------------

Chosen with ``--country-source``, exactly as in the other two reports: ``geometry``
(default) tests an interior point of the perimeter against the real country polygons at
report time; ``reported`` trusts the ``admin_boundary_id`` the import stored.

For a single-country dataset its job is not to choose between countries but to **catch
the fires that are in none of them**. A perimeter digitised into the Atlantic keeps its
Portuguese ``admin_boundary_id`` and is silently in the total under ``reported``; under
``geometry`` it is in nobody's. A perimeter that reaches over the Spanish border shows up
as a ``Spain`` row, which is what the Country column is there to say.

Here the two agree on well-formed data — the ICNF import resolves the country by
containment from a point on the perimeter — so ``reported`` is simply the faster path, an
index lookup on a foreign key instead of a point-in-polygon test per fire.

.. tip::

   Running the same report both ways is a cheap consistency check: any figure that moves
   is a fire whose perimeter and whose attribution disagree.

Which fires are counted
-----------------------

Fires with **no country are excluded**, and so is any fire with no perimeter. A report
therefore does not necessarily account for every hectare in the database; the totals are
totals of *attributable* burnt area.

.. note::

   The ``Fires`` column counts exactly the fires that survived these rules, so it never
   disagrees with the areas beside it — but it is therefore a count of *attributable*
   fires, not of every fire in the database.


Progress
--------

The report is one ``SELECT``, so there is no n-of-m to show: PostgreSQL does not report
partial progress on an aggregate, and inventing a percentage would be a fiction. What is
shown instead is that the process is alive and how long it has been going.

On a terminal, one line rewritten in place:

.. code-block:: text

   \ Measuring the burnt area of the ICNF fires (every year)... 0:02:47

Redirected to a file, or below ``INFO``, the same thing as two ordinary log records and
no control characters at all:

.. code-block:: text

   14:22:01 INFO Measuring the burnt area of the ICNF fires (every year)...
   14:24:48 INFO Measuring the burnt area of the ICNF fires (every year): done in 167s

A run that fails says ``failed after 167s`` rather than ``done in``: knowing it worked
for three minutes before falling over is worth as much as knowing it finished.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.portugal_icnf.wildfire_statistics
   :members:
   :show-inheritance:
