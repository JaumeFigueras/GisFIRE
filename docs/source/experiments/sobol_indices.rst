Sobol indices of the sweep
==========================

How much of each statistic's variation each parameter of an algorithm explains, alone
(first-order index), with its interactions (total index), and two by two (interaction),
computed per episode from a CSV file of :doc:`sweep`'s ``--sensitivity``. The sweep runs a
full factorial grid, so the indices are exact: a decomposition of the variance over the
grid, with no sampling. It reads nothing from the database.

The time-distance clustering over FMI's first quarter of Finland's episodes (30 episodes
of at least 100 zone flashes, D × T = 36 combinations) gives, as medians over the
episodes, a first-order index of D of 0.46 for the number of thunderstorms, 0.87 for
their density and 0.61 for their median diameter, against 0.25, 0.06 and 0.22 for T; for
their duration T leads, 0.47 against 0.29. Density, diameters and duration had a value
for every combination in 14 of the 30 episodes only (a combination with no thunderstorm
has none), and only those 14 are used. ``flashes_isolated`` and ``isolated_pct`` give the
same indices: within an episode one is the other times a constant.

.. contents::
   :local:
   :depth: 1

.. automodule:: gisfire_experiments.thunderstorms.sobol_indices
   :members:
