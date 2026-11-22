Time-distance clustering (Galanaki et al. 2018)
===============================================

.. contents::
   :local:
   :depth: 1

Groups lightning **flashes** into thunderstorms by how close they are in time and space,
following E. Galanaki, K. Lagouvardos, V. Kotroni, E. Flaounas and A. Argiriou,
*Thunderstorm climatology in the Mediterranean using cloud-to-ground lightning
observations*, Atmospheric Research **207** (2018) 136–144,
`doi:10.1016/j.atmosres.2018.03.004 <https://doi.org/10.1016/j.atmosres.2018.03.004>`_,
section 2.2. It lives in :mod:`gisfire_algorithms.thunderstorm.time_distance_galanaki`
and is stored as ``thunderstorm_experiment.algorithm = 'TIME_DISTANCE_GALANAKI_2018'``.

The rule
--------

The article clusters in three steps:

1. A flash not yet in a cluster is the **lightning core** of a new cluster.
2. Every flash within a distance *D* **and** a time difference *T* of it joins the
   cluster. This is repeated for every flash that joins, until no flash is left to join.
3. The cluster takes the next sequential number.

Both limits are inclusive. The distance is Euclidean, in the network's projected CRS; the
time difference goes both ways, so a flash can bring in an earlier one, and a flash
between two clusters joins them into one. The clusters do not depend on which flash
step 1 takes: they are the groups of flashes linked by chains of pairs within *D* and
*T*. The flashes are taken in time order, so the labels follow each cluster's first
flash.

Parameters
----------

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Field (flag)
     - Default
     - Meaning
   * - ``max_distance_km`` (``--max-distance``)
     - 10
     - *D*. The article's 0.1° ("about 10 km"), taken as 10 km in the projected CRS.
   * - ``max_time_difference_min`` (``--max-time-difference``)
     - 16
     - *T*, in minutes.
   * - ``min_flashes`` (``--min-flashes``)
     - 1
     - *N*\ :sub:`min`: smaller clusters are not stored. 1 keeps every cluster, as the
       article does.
   * - ``srid`` (``--srid``)
     - the provider's
     - The projected CRS the algorithm works in.

As in Cellsearch, each flash is represented by its most accurate stroke
(:func:`~gisfire_algorithms.thunderstorm.flashes.strokes_to_flashes`), and the builder
reads cloud-to-ground strokes only, the article's data. No flash is filtered by its
location error, as in the article.

What is stored
--------------

The builder (:doc:`../applications/build_thunderstorms`) stores every kept cluster in the
generic tables and nothing of its own:

- every stroke of the cluster's flashes is linked;
- the concave hull is drawn over the flashes' representative strokes;
- the **area** is the concave hull's, in km², in the projected CRS. A cluster of one or
  two flashes (or with every flash on a line) has no hull and no area, and is stored all
  the same.

A quiet gap longer than *T* links no flash across it, so a run is cut there into pieces
with the same result as one run over everything.

Differences from the article
----------------------------

- The article clusters strokes from ZEUS, a network that detects about a quarter of the
  strokes. GisFIRE clusters flashes, as for Cellsearch.
- The article measures *D* in degrees; here it is metres of the network's projected CRS,
  so it does not shrink with latitude.
- The article says its thresholds "are adapted to the ZEUS observational network
  detection efficiency". On networks that detect far more, the same *D* and *T* chain
  more: on FMI's busiest day of 2018 (2018-08-03), the largest cluster had 15,317 flashes
  over 21.9 h and 524 × 609 km.
- The article's other properties (size on a 0.05° grid, intensity, speed and direction,
  rainfall) are not computed.

API reference
-------------

.. automodule:: gisfire_algorithms.thunderstorm.time_distance_galanaki
   :members:
   :show-inheritance:
