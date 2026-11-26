Gap statistic of the sweep
==========================

For each combination of an algorithm's parameters, how far the real data's share of
isolated flashes falls below its share in copies of the same periods with the flashes'
times shuffled: the combinations where the parameters find storms that chance does not
make. Computed per episode from a gap file of the sweep's ``--sensitivity --gap`` (see
:doc:`sweep`), of any algorithm and provider, with the summary over the episodes, the combination where
each episode's gap is largest, and a bootstrap of the episodes for the combination of the
largest median gap. It reads nothing from the database.

.. contents::
   :local:
   :depth: 1

.. automodule:: gisfire_experiments.thunderstorms.gap_statistic
   :members:
