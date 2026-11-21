Episodes and thunderstorms: the rules
=====================================

.. contents::
   :local:
   :depth: 1

Every thunderstorm analysis of a network follows two rules: one says what an **episode**
is, the other which **thunderstorms** count and from which flashes their statistics come.
They apply to every thunderstorm run, whatever the algorithm, and not only to the
sensitivity analysis. They were agreed on 2026-11-21; the code does not apply all of them
yet (see `Status`_).

Definitions
-----------

**Networks and nominal regions.** Each network is analysed over the region it is meant to
cover, its *nominal region*, taken as the region's **land** boundary. Every distance, the
buffer included, is measured in the network's projected CRS.

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Network
     - Nominal region (boundary)
     - Projected CRS
   * - FMI
     - Finland (the country)
     - EPSG:3067 (ETRS89 / TM35FIN)
   * - Alaska Lightning Detection Network (USWFS)
     - Alaska (the state, from the Census Bureau's cartographic boundary files)
     - EPSG:3338 (NAD83 / Alaska Albers)
   * - MeteoCat XDDE
     - Catalonia (IGN's boundary of the autonomous community)
     - EPSG:25831 (ETRS89 / UTM 31N)

**Zone** (the area of interest): the nominal region plus a **50 km buffer**. Along a
coast, the buffer adds the sea.

**Lightning**: only **cloud-to-ground** strokes, in both rules.

**Flash**:

- FMI and MeteoCat: the flash as the network publishes it, unless it lasts **more than
  2 s** from its first stroke to its last. No real flash lasts that long, so such a flash
  is an error of the network's grouping: its strokes are regrouped with the NLDN rule
  (:doc:`flash_grouping_nldn`) **among themselves only**, never joined to the strokes of
  another flash. A flash of up to 2 s (1.3 s, say) stays as published.
- The Alaska network publishes no flashes; its strokes are grouped with the NLDN rule.

**Zone flash**: a ground flash with **any** of its strokes inside the zone. The whole
flash counts.

**A flash's time and position** are those of its **representative stroke**, the most
accurate one, which is the point the algorithm clusters (see :doc:`../algorithms`), even
when that stroke lies outside the zone and another of its strokes is inside.

Rule 1: episodes
----------------

- Only zone flashes count, whatever their location error. Flashes outside the zone are
  ignored.
- An episode **starts** at a zone flash with no zone flash in the *G* before it, and
  **ends** at its last zone flash: the first one followed by *G* with no zone flash.
  *G* is only the silence test; it is not added to the episode.
- *G* is always longer than the algorithm's waiting time (Cellsearch: *T*). Its value
  will come from a study of its own.
- E\ :sub:`max` is not part of the rule: it is a parameter of the algorithms.

Example: with *G* = 5 h, zone flashes at 12:00, 13:30 and 21:00 make two episodes,
12:00–13:30 and one starting at 21:00, because 13:30 to 21:00 is longer than 5 h.

Rule 2: thunderstorms
---------------------

- Thunderstorms are built from the **whole network's** ground strokes, not only the
  zone's.
- **No storm is cut.** A run's ``--from`` and ``--to`` lie where the whole network has
  been silent for longer than *T*. A run may hold one episode or many; a whole season,
  with both ends in a quiet time, is the simplest choice.
- A thunderstorm is **kept** only when at least one of its flashes is a zone flash.
  Otherwise the thunderstorm and its hull are discarded. A kept storm's hull therefore
  always intersects the zone, and a storm with no hull (fewer than three distinct points,
  or all on a line) can be kept too.
- For a kept thunderstorm:

  - its **time** (start, end, duration) comes from **all** its flashes, the whole storm;
  - **everything else** (its flashes, area, density, diameter, …) comes only from its
    **zone flashes**.

- Because *G* is longer than *T*, a kept thunderstorm's zone flashes all fall within one
  episode, and that is its episode.
- **Isolated flashes**: an episode's zone flashes that the algorithm clustered and that
  belong to no kept thunderstorm (stray flashes, or cells smaller than *N*\ :sub:`min`).
- **Discarded flashes**: flashes the algorithm discards (by E\ :sub:`max`, for
  Cellsearch) are neither in a thunderstorm nor isolated.

Example: a storm is born in Sweden at 10:00 and enters Finland's zone at 13:00, so
Finland's episode starts at 13:00. The storm is kept, its duration runs from 10:00, and
its area and flash count come from its flashes in the zone only.

Status
------

What the code already does as the rules say:

- Ground strokes only: the default of :doc:`../applications/build_thunderstorms`.
- A flash's time and position from its representative stroke
  (:func:`~gisfire_algorithms.thunderstorm.flashes.strokes_to_flashes`).
- The Alaska strokes grouped into flashes with the NLDN rule, by the Alaska import.
- A storm cut at ``--from`` or ``--to`` is detected: the run's summary records
  ``activity_before_start`` and ``cells_open_at_end``, and the builder warns.
- The zones and rule 1, in the episodes study
  (:doc:`../experiments/lightning_episodes`): for a given *G*, it
  writes each episode's span and its zone flashes and strokes, and the quartiles of the
  episodes' flashes. Its regions are OCHA's Finland, IGN's Catalonia and the Census
  Bureau's Alaska (:doc:`../applications/census_import_admin_boundaries`); a stroke is in
  the zone when it is at most 50 km from the region, tested with shapely. The episodes
  are cut with :func:`~gisfire_algorithms.thunderstorm.chunking.split_at_gaps`. It takes
  the flashes as published, without the 2 s regrouping below.

What is still to do:

- Regrouping the published flashes that last more than 2 s.
- *G*: still to be set; the episodes study is the tool to study it with.
- The zones and the episodes in the builder, which so far uses neither.
- Keeping only the storms with a zone flash, and taking their statistics from their
  zone flashes. The sensitivity analysis's ``--country`` follows another rule today: a
  storm counts when more than half of its flashes have their representative stroke in a
  level-0 country, and the statistics use all of its flashes.
