Algorithms
==========

.. contents::
   :local:
   :depth: 1

Overview
--------

The algorithms are written **once**, in the ``gisfire_algorithms`` package at the root of
the repository, and everything else is an adapter around them: the command-line
applications read their input from the database and store what they return, and the QGIS
plugins will do the same from a layer. Nothing in the package knows where its input came
from::

   gisfire_algorithms/
     __init__.py                       __version__
     thunderstorm/
       flashes.py                      strokes → flashes
       cell_statistics.py              area, lifetime, flash rate, density
       chunking.py                     split a time-ordered sequence at quiet gaps
       cellsearch_tuomi_larjavaara.py  Cellsearch (Tuomi & Larjavaara 2005)

Three rules keep it usable from both sides:

**Pure computation on plain data.** The input and output are numpy arrays and frozen
dataclasses. The package must not import the data model (SQLAlchemy, GeoAlchemy2,
psycopg) nor QGIS; its only dependencies are the standard library, numpy and, for the
algorithms that need it, scikit-learn. Established libraries are preferred to hand-made
code; Cellsearch is sequential and has no library equivalent, so it needs numpy only.

**Relative imports inside the package**, so a plugin can ship it vendored under its own
namespace.

**Units are the caller's.** Times are seconds since the epoch (UTC), coordinates metres
of a projected CRS, location errors metres. An algorithm converts its own thresholds
once, rather than every coordinate, so a boundary given exactly is compared exactly.

``gisfire_algorithms.__version__`` is stored with every run as the experiment's
``software_version`` (see :doc:`data_model/thunderstorm`). **Bump it whenever an
algorithm's output changes**: two runs with the same settings and different versions are
different experiments, and the database lets both be stored.

Tests
-----

``test/algorithms/`` tests the package without a database. QGIS ships its own Python and
an older numpy than the project's virtual environment, so the same tests also run with
the QGIS one:

.. code-block:: bash

   make test                  # with everything else, in .venv
   make test-algorithms-qgis  # test/algorithms only, with the QGIS venv

The second runs pytest with ``--noconftest`` (the root ``test/conftest.py`` needs
pytest-postgresql and SQLAlchemy, which the QGIS environment lacks) and without the
coverage options of ``pytest.ini``. ``make test-all`` runs both.

Thunderstorms
-------------

A thunderstorm is inferred from lightning, by grouping one network's strokes or flashes
in space and time. Each algorithm has a page of its own:

:doc:`algorithms/cellsearch_tuomi_larjavaara`
    Cellsearch (Tuomi & Larjavaara 2005): flashes taken in time order, each one joining
    the open cell with the closest centre within a radius and a waiting time, or opening
    a new one. Flash-based: each flash is represented by its most accurate stroke.

They are run over the database by :doc:`applications/build_thunderstorms`, which stores
each run as a thunderstorm experiment.

.. toctree::
   :maxdepth: 1
   :hidden:

   algorithms/cellsearch_tuomi_larjavaara

What the thunderstorm algorithms share
--------------------------------------

**Strokes and flashes.** A lightning-location network reports strokes and groups them
into flashes. :class:`~gisfire_algorithms.thunderstorm.flashes.Strokes` holds the strokes
as parallel arrays, with the provider's flash identifier folded into one integer key
(for MeteoCat, ``network_version · 10¹⁰ + flash_id``).
:func:`~gisfire_algorithms.thunderstorm.flashes.strokes_to_flashes` represents each
flash by its **most accurate stroke** — the smallest location error, then the earliest,
then the lowest id — which gives the flash its position, its time and its error, and
keeps the map from every stroke to its flash so the adapters can link all of them.

**Cell statistics** (:mod:`gisfire_algorithms.thunderstorm.cell_statistics`). The area
of a group of points is the one of Tuomi & Larjavaara (2005, appendix), built from the
regression of their coordinates:

.. math::

   A = 12\, s_x s_y \sqrt{1 - r^2} = 12 \sqrt{\det \Sigma}

with Σ the **population** covariance matrix of the points (sums divided by *n*). A
uniformly filled square of side *L* comes out as *L*\ ², a stray point barely inflates
it, and it does not depend on the orientation of the axes. It is undefined — ``None``,
never 0 — for fewer than three points or points on a line, so a density is never
infinite. The lifetime (last − first flash, in minutes), the flash rate (flashes per
minute, undefined for a lifetime of 0) and the density (flashes per 100 km², as the
article reports it) complete the set.

**Chunking** (:func:`~gisfire_algorithms.thunderstorm.chunking.split_at_gaps`). A
time-ordered sequence is cut wherever two consecutive elements are more than a gap
apart. For an algorithm whose cells close after that gap — Cellsearch with its waiting
time *T* — the pieces can be clustered one after the other with the same result as the
whole, which is what lets a run over years fit in memory.

API reference
-------------

.. automodule:: gisfire_algorithms
   :members:

.. automodule:: gisfire_algorithms.thunderstorm.flashes
   :members:
   :show-inheritance:

.. automodule:: gisfire_algorithms.thunderstorm.cell_statistics
   :members:
   :show-inheritance:

.. automodule:: gisfire_algorithms.thunderstorm.chunking
   :members:
   :show-inheritance:
