Thunderstorm algorithms: sensitivity and time analyses
======================================================

Runs one thunderstorm algorithm over one network's strokes for every combination of a
grid of its parameters, over a period. ``--algorithm`` chooses it:

- ``cellsearch_tuomi_larjavaara`` (the default), :doc:`../algorithms/cellsearch_tuomi_larjavaara`:
  the radius of attraction R, the maximum waiting time T, the inertia I and the
  time-distance limit C, 6 × 6 × 5 × 6 = 1,080 combinations, the lists being
  :data:`ATTRACTION_RADII_KM <gisfire_experiments.thunderstorms.sweep.ATTRACTION_RADII_KM>`,
  :data:`MAX_WAITING_TIMES_MIN <gisfire_experiments.thunderstorms.sweep.MAX_WAITING_TIMES_MIN>`,
  :data:`INERTIAS <gisfire_experiments.thunderstorms.sweep.INERTIAS>` and
  :data:`TIME_DISTANCE_LIMITS_MIN_KM
  <gisfire_experiments.thunderstorms.sweep.TIME_DISTANCE_LIMITS_MIN_KM>`;
- ``time_distance_galanaki``, :doc:`../algorithms/time_distance_galanaki`: the distance
  D and the time difference T, 6 × 6 = 36 combinations, the lists being
  :data:`MAX_DISTANCES_KM <gisfire_experiments.thunderstorms.sweep.MAX_DISTANCES_KM>` and
  :data:`MAX_TIME_DIFFERENCES_MIN
  <gisfire_experiments.thunderstorms.sweep.MAX_TIME_DIFFERENCES_MIN>`, with N\ :sub:`min`
  fixed at 10, as Cellsearch's, so that the statistics of the two mean the same.

It is one script with two analyses, and one of them is chosen on every run:

- ``--sensitivity`` stores every combination as a thunderstorm experiment, through
  :doc:`../applications/build_thunderstorms`, and writes the statistics of each one's
  thunderstorms, so the parameters can be chosen by what they make of a network's storms;
- ``--time`` writes nothing to the database: it times the algorithm (``cellsearch()``
  or ``time_distance()``) on every combination, several times each, so the cost of each
  choice can be weighed.

``--sensitivity`` runs over one period (``--from``, ``--to``) or, with ``--periods``,
over every episode of an episodes study's file (:doc:`lightning_episodes`), each widened
by an hour on both sides, writing one CSV file for all of them. ``--defaults`` runs the
algorithm's recommended values alone instead of its grid, into files of their own.

The runs and the statistics follow rule 2 of :doc:`../algorithms/thunderstorm_rules`:
the runs cluster the whole network and store only the thunderstorms with a flash in the
network's zone (its nominal region plus 50 km), and each one's statistics come from its
zone flashes, but for its duration, which comes from all its flashes.

.. contents::
   :local:
   :depth: 1

.. automodule:: gisfire_experiments.thunderstorms.sweep
   :members:
