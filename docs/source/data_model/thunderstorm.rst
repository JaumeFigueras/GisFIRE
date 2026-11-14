Thunderstorm
============

A thunderstorm is not observed: it is **inferred** from lightning strokes, by grouping
one provider's strokes with a clustering algorithm. The same strokes grouped by another
algorithm, or by the same one with other settings, give other thunderstorms. So every
thunderstorm belongs to the *run* that produced it, and the run records exactly how.

.. code-block:: text

   data_provider 1──n thunderstorm_experiment 1──n thunderstorm 1──n thunderstorm_evolution
                              │ 1                    │ 1                 n │
                              └──n thunderstorm_tracking 1──────────────────┘
   lightning 1──n thunderstorm_lightning n──1 thunderstorm
                          1 │                      │ 1
                       0..1 │                      │ n
                          thunderstorm_cellsearch_flash     (Cellsearch only)

Two runs, one after the other
-----------------------------

**An experiment clusters the strokes.**
:class:`~src.data_model.thunderstorm.ThunderstormExperiment` records the provider, the
period of strokes read (half-open), the filter applied to them (for MeteoCat,
``{"network": "newest"}``: the newest network where the two overlap), the algorithm and
its parameters, and the concave-hull settings. The algorithm is free text and the
parameters JSONB, so no method is assumed: a two-step method keeps one block per step.
What the run reports about itself — counts, size classes, whether the period cut a storm
— goes in its ``summary``, an output and so not part of its identity. Each group found is
a :class:`~src.data_model.thunderstorm.Thunderstorm` with its time span, its number of
strokes (and of flashes, for a flash-based algorithm), its area and its **concave hull**;
which strokes make it up is :class:`~src.data_model.thunderstorm.ThunderstormLightning`.
A stroke the algorithm left out has no row. Experiments are built by
:doc:`../applications/build_thunderstorms`.

**A tracking follows each thunderstorm over time.**
:class:`~src.data_model.thunderstorm.ThunderstormTracking` cuts every thunderstorm of an
experiment into time windows, and each window is a
:class:`~src.data_model.thunderstorm.ThunderstormEvolution` with its **gravity centre**
(the plain mean of its strokes) and its concave hull. An experiment can be tracked any
number of times with different windows, without clustering again.

Flash-based algorithms
----------------------

Some algorithms — Cellsearch (:doc:`../algorithms/cellsearch_tuomi_larjavaara`), the
first — group **flashes** rather than strokes, each flash represented by its most
accurate stroke. The generic tables take them without a separate model:

- ``thunderstorm.number_of_flashes`` counts the flashes, between 1 and
  ``number_of_lightnings``; ``NULL`` for a stroke-based algorithm.
- ``thunderstorm.area`` is the area, in km², by the formula of Tuomi & Larjavaara (2005,
  appendix), ``12·√det(Σ)`` over the points clustered; positive, or ``NULL`` when it is
  undefined (fewer than three points, or all on a line), so a density is never a
  division by zero.
- ``thunderstorm_lightning`` links **every stroke** of every flash, so
  ``number_of_lightnings`` and the time span keep their generic meaning: all the linked
  strokes.
- The **concave hull** is drawn over the points the algorithm clustered — each flash's
  representative stroke, the same points as the area — not over all the linked strokes.
  MeteoCat holds merged "flashes" whose strokes lie tens of kilometres apart (3,683 of
  the second network's span 5–60 s, with a median diameter of 19 km), and all the strokes
  would inflate the hull.

An algorithm gets a table of its own only for structured output no other algorithm
produces. Cellsearch's is
:class:`~src.data_model.thunderstorm_cellsearch.ThunderstormCellsearchFlash`
(``thunderstorm_cellsearch_flash``): one row per flash of a kept cell, with its
``sequence`` in the cell (from 1), its representative stroke and the cell's running
**centre** right after it, a ``POINT`` in EPSG:4326 — the trajectory of the article's
Fig. 8. The flash's time and error are not repeated: they are its stroke's. Only the
cells with at least *N*\ :sub:`min` flashes are stored, so only their flashes have rows.

Because of the merged flashes, a storm's ``date_time_end − date_time_start`` (all its
strokes) may exceed the article's **lifetime** (last − first flash) by the span of one
flash. The views give both.

Windows
-------

A window has a **length** *W* — how much time it covers — and a **step** *S* — how far
it moves each time, with ``0 < S <= W``.

- **Sliding, S < W.** The windows overlap and each stroke falls in *W/S* of them: this is
  the window of a moving average. With *W* = 10 min and *S* = 2 min the windows are
  10:00–10:10, 10:02–10:12, 10:04–10:14, …, and each centre is the mean of the last ten
  minutes. The path is smooth — two consecutive windows share (*W* − *S*)/*W* of their
  strokes, so a cell flaring up for a minute moves the centre only a little — but
  consecutive vectors are correlated. Use them to describe a storm; for independent
  samples, take every *W/S*-th window.
- **Fixed, S = W.** The windows sit end to end and each stroke falls in exactly one. The
  path is noisier, with *W/S* times fewer points, and each vector is independent of the
  previous one.

Two more settings make a window fully defined:

- **It stands for its midpoint.** A moving average stamped at the end of its window lags
  the storm by *W*/2; stamped at the midpoint, the speeds come out right.
- **It starts on the clock** (``window_anchor = 'clock'``, the default): windows begin at
  multiples of the step, 10:00, 10:02 …, so they line up across thunderstorms and with
  other data such as radar or reanalysis. ``storm_start`` starts them at each storm's
  first stroke instead.

Only windows with at least ``min_lightnings`` strokes get a row. A window with fewer than
three non-collinear strokes has a centre but no hull (``NULL``).

What is computed, not stored
----------------------------

The views of revisions ``7a1c4e9b2d56`` and ``e7147a41b62b`` compute everything else from
what is stored, so it can never disagree with it (see :ref:`migrations-views`):

- the **direction vector** of each window — the move from the previous centre to its
  own: distance and bearing on the WGS 84 spheroid, elapsed time, speed, and the east and
  north components *u* and *v*. Average the components, never the bearings: the mean of
  350° and 10° is north, not south;
- the **path** — the line through a storm's centres, with its total and net distance,
  mean speed and the bearing of its mean velocity;
- the **convex hull** — ``ST_ConvexHull`` of the concave hull. A concave hull contains
  every point it was drawn from and its vertices are among them, so this *is* the convex
  hull of those points. Storing it as well would have cost about 100 MB per experiment
  and tracking;
- a storm's **density**, 100 · flashes / area, in flashes per 100 km² as the article
  reports it;
- for Cellsearch, each cell's **path** through its centres, with the article's statistics
  computed from the flashes: the **lifetime** (last − first flash), the **flash rate**
  (undefined for a lifetime of zero), the path's length and the distance from its first
  to its last centre.

Integrity
---------

The database enforces what a builder could get wrong:

- a stroke belongs to **at most one thunderstorm per experiment**;
- a link or a window **cannot cross experiments**: they carry ``experiment_id`` and
  reference ``(id, experiment_id)`` through composite foreign keys;
- a Cellsearch flash row likewise carries its cell's ``experiment_id``, and its
  representative stroke must be **one of its cell's linked strokes** (a composite foreign
  key to ``thunderstorm_lightning``); a stroke represents at most one flash per
  experiment, and a position in a cell is taken once;
- ``number_of_flashes`` is between 1 and ``number_of_lightnings``, and ``area`` is
  positive, when they are set;
- the **same configuration cannot be stored twice**, ``software_version`` included.
  ``jsonb`` and ``interval`` compare by value — key order does not matter, and 600 s is
  10 min — so the builder stores complete settings, defaults included;
- ``status`` is ``running``, ``complete`` or ``failed``, and ``completed_at`` is set
  exactly when it is ``complete``; the views show complete runs only;
- deleting an experiment deletes **everything it produced**, the algorithm's own rows
  included; deleting a tracking deletes its windows;
- a stroke in a thunderstorm **cannot be deleted** (``ON DELETE RESTRICT``). A lightning
  import refuses to replace a year an experiment depends on unless told to drop those
  experiments first — see :doc:`../applications/meteocat_import_lightnings`.

What it leaves to the builder: that a run's strokes come from its provider, period and
filter, that a storm's strokes and windows lie within its time span, that a window has
at least ``min_lightnings`` strokes, and that a stored cell has at least the run's
``min_flashes``.

API reference
-------------

.. automodule:: src.data_model.thunderstorm
   :members:
   :show-inheritance:

.. automodule:: src.data_model.thunderstorm_cellsearch
   :members:
   :show-inheritance:
