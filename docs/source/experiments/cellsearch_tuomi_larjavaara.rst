Cellsearch: sensitivity and time analyses
=========================================

Runs :doc:`../algorithms/cellsearch_tuomi_larjavaara` over one network's strokes for
every combination of its four parameters — the radius of attraction R, the maximum
waiting time T, the inertia I and the time-distance limit C — over a period:
5 × 5 × 6 × 6 = 900 combinations, the lists being :data:`ATTRACTION_RADII_KM
<gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara.ATTRACTION_RADII_KM>`,
:data:`MAX_WAITING_TIMES_MIN
<gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara.MAX_WAITING_TIMES_MIN>`,
:data:`INERTIAS <gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara.INERTIAS>`
and :data:`TIME_DISTANCE_LIMITS_MIN_KM
<gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara.TIME_DISTANCE_LIMITS_MIN_KM>`.

It is one script with two analyses, and one of them is chosen on every run:

- ``--sensitivity`` stores every combination as a thunderstorm experiment, through
  :doc:`../applications/build_thunderstorms`, and writes the statistics of each one's
  thunderstorms, so the parameters can be chosen by what they make of a network's storms;
- ``--time`` writes nothing to the database: it times ``cellsearch()`` on every
  combination, several times each, so the cost of each choice can be weighed.

.. note::

   ``--country`` restricts the sensitivity statistics to the thunderstorms with more
   than half their flashes in a level-0 country, and takes them over all their flashes.
   That is not yet the rule of :doc:`../algorithms/thunderstorm_rules`, which keeps a
   storm with any zone flash and takes its statistics from its zone flashes.

.. contents::
   :local:
   :depth: 1

.. automodule:: gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara
   :members:
