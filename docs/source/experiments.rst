Experiments
===========

.. contents::
   :local:
   :depth: 1

Overview
--------

Experiments are analyses run over the data already in the database: they read a
network's strokes, run an algorithm or apply a rule over a period, and write the results
to CSV files for a study. They import nothing, and only the thunderstorm builder they may
drive writes to the database. They live in the top-level ``gisfire_experiments`` package,
one subpackage per kind of study, and are run as modules from the repository root::

   python3 -m gisfire_experiments.<kind>.<experiment> ...

Like the applications, they read the database settings from the environment (``.env``)
and take ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user`` and
``--db-password`` to override them. Each has its tests under ``test/experiments/`` (see
:doc:`testing`).

Network lightning studies
-------------------------

``gisfire_experiments/network_lightning_study/``: what a network detects over the zone of
its nominal region (see :doc:`algorithms/thunderstorm_rules`), before any thunderstorm is
built.

:doc:`experiments/lightning_episodes`
    The episodes of rule 1 over a period, with the flashes and strokes of each, the
    quartiles of the episodes' flashes and the episodes in each quarter: the tool to set
    *G* with and to size the episodes of each network. Read-only.

.. toctree::
   :maxdepth: 1
   :hidden:

   experiments/lightning_episodes

Thunderstorm experiments
------------------------

``gisfire_experiments/thunderstorms/``: the algorithms that group flashes into
thunderstorms (see :doc:`algorithms`), run over a grid of their parameters.

:doc:`experiments/sweep`
    The sensitivity analysis of an algorithm (every combination of its grid stored
    through the thunderstorm builder, and the statistics of its thunderstorms) and its
    time analysis (the computation time of every combination, nothing written to the
    database), for Cellsearch (R, T, I and C) and the time-distance clustering (D and
    T).

:doc:`experiments/sobol_indices`
    The Sobol indices of the sweep's statistics, per episode: how much of each one's
    variation each parameter explains, alone, with its interactions, and two by two,
    exact over the sweep's full grid. Reads the sweep's CSV files only.

:doc:`experiments/sobol_chart`
    The figure of those indices: a panel per KPI, a bar per parameter stacking its
    first-order index and its interactions, a whisker over the episodes' IQR; a PNG,
    16 cm wide at 600 dpi, in English or Catalan, with a Word table of the medians
    (q1–q3).

.. toctree::
   :maxdepth: 1
   :hidden:

   experiments/sweep
   experiments/sobol_indices
   experiments/sobol_chart
