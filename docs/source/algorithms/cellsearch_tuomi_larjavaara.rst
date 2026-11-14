Cellsearch (Tuomi & Larjavaara 2005)
====================================

.. contents::
   :local:
   :depth: 1

Groups lightning **flashes** into **flash cells**, following T. J. Tuomi and
M. Larjavaara, *Identification and analysis of flash cells in thunderstorms*, Q. J. R.
Meteorol. Soc. **131** (2005) 1191–1214, `doi:10.1256/qj.04.64
<https://doi.org/10.1256/qj.04.64>`_, section 4(a). It lives in
:mod:`gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara` and is stored as
``thunderstorm_experiment.algorithm = 'CELLSEARCH_TUOMI_LARJAVAARA_2005'``.

The rules
---------

The flashes are read in time order, and each new flash is tested against the cells that
are still open:

(i) **Radius of attraction.** Its distance to the cell's current centre is at most *R*.

(ii) **Delay time.** Its delay from the cell's latest flash is at most *T*. A cell beyond
     this limit is **closed** and never tested again.

(iii) **Time–distance limit** (optional). The product of that delay, in minutes, and its
      distance to the cell's **latest flash**, in km, is at most *C*. The article's
      reason for this, the most artificial rule: stray flashes tend to bridge adjacent
      cells, and as a decaying cell's flash rate drops, the product grows even for nearby
      strays, which stops them joining it.

(iv) **Closest cell.** Of the cells passing (i)–(iii), the flash joins the one with the
     closest centre.

(v) **New cell.** With no candidate, the flash opens a new cell.

(vi) **Centre and inertia.** A cell's centre is the mean position of its last
     ``min(I, n)`` flashes, recomputed after each flash.

Before the search, flashes with a location error of *E*\ :sub:`max` or more are
**discarded** (the article accepts "only flashes with location error below 10 km"). After
it, only cells with at least *N*\ :sub:`min` flashes are **kept**; the smaller ones are
the article's stray flashes and small cells, and are counted in the summary but not
stored.

Each flash is represented by its **most accurate stroke**, "or its only stroke", as in
the article; that stroke gives the flash its position, its time and its location error
(see :doc:`../algorithms`).

Parameters
----------

They are :class:`~gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara.CellsearchParameters`,
a frozen dataclass that validates itself, and each one is a flag of
:doc:`../applications/build_thunderstorms`:

==================================  ====================================  ==========  ===========  ======================
Article                             Field and flag                        Unit        Default      Valid values
==================================  ====================================  ==========  ===========  ======================
*R*, radius of attraction           ``attraction_radius_km``              km          15           > 0
                                    ``--attraction-radius``
*T*, maximum waiting (delay) time   ``max_waiting_time_min``              min         15           > 0
                                    ``--max-waiting-time``
*C*, time–distance limit            ``time_distance_limit_min_km``        min·km      ``None``     ``None`` (off) or > 0
                                    ``--time-distance-limit``
*I*, cell inertia                   ``inertia``                           flashes     20           integer ≥ 1
                                    ``--inertia``
*E*\ :sub:`max`, location error     ``max_location_error_km``             km          10           > 0
                                    ``--max-location-error``
*N*\ :sub:`min`, smallest cell      ``min_flashes``                       flashes     5            integer ≥ 3
                                    ``--min-flashes``
(projection)                        ``srid``                              EPSG        25831        projected, in metres
                                    ``--srid``
==================================  ====================================  ==========  ===========  ======================

*R*, *T*, *I* and *E*\ :sub:`max` default to the article's values. Its discussion of them
(section 4b): *R* should be no smaller than 10 km, or a moving cell splits into a string
of small ones, and no larger than about 20 km, or close simultaneous cells merge; *T*
has an upper limit of 20–30 minutes, beyond which a dying cell captures the flashes of a
young neighbour, while a very short one (5 minutes) lets flashes be captured by too
distant a cell. *N*\ :sub:`min` is this implementation's: three is the least an area
needs.

:meth:`~gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara.CellsearchParameters.to_dict`
returns **every** field, the defaults and ``None`` included. It is what the experiment
stores, and the database refuses the same configuration twice by comparing it as
``jsonb``, so a run with ``--inertia 20`` given explicitly is the same run as one with the
default.

.. warning::

   **C = None is not the article's basic run.** Table 1, Table 2 and Figs. 8 and 13 all
   use condition (iii), with a value of *C* the article does not publish; only the run of
   its Fig. 14 leaves it out. There is therefore no default value: leaving *C* out turns
   the condition off, and each run chooses its own. Finnish and Catalan storms differ, so
   the article's tables are a sanity reference, not a target.

A sweep over *C* on 2020-07-13 (all other parameters at their defaults; 2,209 flashes
searched), against Table 1 and the text of the article:

======  =====  ====  ==========================  =========================  ============  ==============
*C*     Cells  Kept  One-flash cells / flashes   Flashes in cells ≥10/≥30   Mean area     Longest life
======  =====  ====  ==========================  =========================  ============  ==============
10      512    99    44.5 % / 10.3 %             53 % / 26 %                101 km²       58 min
15      361    85    43.2 % / 7.1 %              69 % / 38 %                120 km²       100 min
25      231    77    37.7 % / 3.9 %              78 % / 56 %                138 km²       111 min
50      148    56    34.5 % / 2.3 %              89 % / 72 %                179 km²       132 min
100     105    46    33.3 % / 1.6 %              93 % / 77 %                225 km²       213 min
200     92     46    28.3 % / 1.2 %              93 % / 81 %                237 km²       239 min
off     92     46    28.3 % / 1.2 %              93 % / 81 %                234 km²       239 min
Art.                 47.1 % / 7.7 %              ~70 % / >40 %              150 → >400    202 min
======  =====  ====  ==========================  =========================  ============  ==============

The mean area is over the kept cells; the article's runs from about 150 km² in its
smallest classes of Table 2 to over 400 km² for the most abundant cells, and its longest
lifetime is over a whole season. *C* = 15 min·km gives the shape of Table 1 most
closely; from about 100 min·km the condition hardly acts, and the longest cells, longer in
a day than the article's longest in a season, suggest merged cells — what condition (iii)
is there to prevent. All seven runs are frozen in a regression test, run where the day's
data is available locally (see :doc:`../testing`).

Choices the article leaves open
-------------------------------

The article describes the rules in words; these are the readings this implementation
makes, and the tests pin each one down:

- **Boundaries are inclusive** where the article says "at most": a flash at exactly *R*
  from the centre, exactly *T* after the latest flash or exactly at *C* is accepted. A
  flash with an error of exactly *E*\ :sub:`max` is discarded (the article: "below 10
  km"). The thresholds are converted once to metres and seconds (*R*·1000, *T*·60,
  *C*·60·1000), never the coordinates to km, so a boundary given exactly is compared
  exactly.
- **A tie in (iv) goes to the lowest label**, the oldest cell. The article does not say.
- **The most accurate stroke** is the one with the smallest error; a tie goes to the
  earliest stroke, then to the lowest id.
- **Labels are running numbers in order of creation**, with gaps where small cells were
  dropped. The article: the numbering "is unique for a given set of parameters".
- **The location error is MeteoCat's** ``ellipse_major_axis`` **as published**, not
  halved. Inside Catalonia the second network's median is 0.8 km, matching the article's
  error "of the order of 1 km".

The area and the other statistics
---------------------------------

A kept cell's area is the one of the article's appendix, ``12·√det(Σ)`` over its flashes'
positions (see :doc:`../algorithms`), in km². The views add the article's other per-cell
statistics: the **lifetime** (last − first flash), the **flash rate** and the **density**
(flashes per 100 km²) — see :doc:`../data_model/thunderstorm`.

The centre after each flash is kept as well: it is the trajectory of the article's Fig. 8,
stored one point per flash in ``thunderstorm_cellsearch_flash``.

The summary
-----------

Besides the labels, the run returns a summary, stored in the experiment's ``summary``:

``size_classes``
    For each cell-size class, the number of cells and of their flashes, **every cell
    included**, kept or not. The classes are Table 1's — 1, 2–4, 5–9, 10–19, 20–29,
    30–49, 50–99 — with its "100–" split into Table 2's 100–199 and 200+, so both tables
    can be rebuilt.
``flashes_total``, ``flashes_discarded_error``, ``flashes_kept``
    The input flashes, those discarded by *E*\ :sub:`max` and those in kept cells. The
    flashes in kept cells, those in smaller cells and the discarded ones add up to the
    total.
``cells_total``, ``cells_kept``
    Every cell found, and those with at least *N*\ :sub:`min` flashes.

:doc:`../applications/build_thunderstorms` adds ``strokes_total`` and the two
window-boundary flags, ``cells_open_at_end`` and ``activity_before_start``.

Running over a long period
--------------------------

A gap of more than *T* between two consecutive flashes closes every open cell, so the
flashes can be cut there into pieces and searched one after the other, passing on the
label counter (``first_label`` / ``next_label``), with exactly the result of one search
over everything. That is how a run over years fits in memory; a test checks that a run
in pieces equals the whole.

For a caller that wants to show progress or stop a long search — the QGIS plugin —
:func:`~gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara.cellsearch` takes a
``progress(done, total)`` callback and an ``is_cancelled()`` one, both checked every
1,000 flashes; a cancelled search raises
:class:`~gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara.CellsearchCancelled`.

Using it from Python
--------------------

.. code-block:: python

   import numpy as np

   from gisfire_algorithms.thunderstorm import CellsearchParameters
   from gisfire_algorithms.thunderstorm import Strokes
   from gisfire_algorithms.thunderstorm import cell_area_km2
   from gisfire_algorithms.thunderstorm import cellsearch
   from gisfire_algorithms.thunderstorm import strokes_to_flashes

   # Six flashes, one stroke each, a minute apart and within 3 km of each other:
   # times in seconds, coordinates in metres of EPSG:25831, errors in metres.
   strokes = Strokes(
       ids=np.arange(1, 7),
       flash_keys=np.arange(1, 7),
       t=1_594_600_000 + 60.0 * np.arange(6),
       x=400_000 + np.array([0, 1000, 2000, 0, 1000, 2000]),
       y=4_600_000 + np.array([0, 0, 0, 1000, 1000, 3000]),
       error=np.full(6, 500.0),
   )
   flashes = strokes_to_flashes(strokes)
   result = cellsearch(flashes, CellsearchParameters(time_distance_limit_min_km=50))

   result.label                       # array([1, 1, 1, 1, 1, 1])
   result.kept_labels                 # array([1])
   result.summary["flashes_kept"]     # 6
   kept = result.label == 1
   cell_area_km2(flashes.x[kept] / 1000, flashes.y[kept] / 1000)   # 9.7…

Not implemented
---------------

The article considers and sets aside two variants of the rules, and so does this
implementation:

- **Joining the most abundant cell** rather than the closest, in (iv), to reduce the
  effect of stray flashes. The article: some cells then "behave like a 'cancer'" and grow
  too large and long-lived at their neighbours' expense — 'cells' 300 km long in its
  Fig. 1 case.
- **An R that grows with the spread of the latest flashes** of a cell, possibly more in
  its direction of movement. The article finds no essential gain in the quality of the
  results and favours the basic rules "because of its clarity".

Also left out, as outside the algorithm: a polarity filter (the database holds only
cloud-to-ground strokes, and all of them are used) and an incremental search state that
would let a run be resumed or extended.

API reference
-------------

.. automodule:: gisfire_algorithms.thunderstorm.cellsearch_tuomi_larjavaara
   :members:
   :show-inheritance:
