CONAFOR wildfire statistics (Mexico)
====================================

Burnt area per year over Mexico's national cartography: how many fires, the smallest, the
largest and the total, in hectares. The CONAFOR member of the same family as
:doc:`gwis_wildfire_statistics`, :doc:`gfa_wildfire_statistics` and
:doc:`icnf_wildfire_statistics` — same columns, same shape, so the CSVs can be
concatenated and read as a difference between the datasets rather than between two ways of
counting.

See :doc:`../providers` for the dataset and :doc:`../providers/conafor_wildfire` for what
each column means.

Usage
-----

.. code-block:: console

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_statistics --csv burnt.csv

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_statistics \
       --year 2023 --csv 2023.csv --docx 2023.docx

   python3 -m src.apps.statistics.wildfires.mexico_conafor.wildfire_statistics \
       --area-method reported --csv as-published.csv

At least one of ``--csv`` and ``--docx`` is required. The application only reads.

No ``--country``, no ``--country-source``, and no boundaries needed
--------------------------------------------------------------------

CONAFOR publishes one country's fires, so there is nothing to select between — the same as
:doc:`icnf_wildfire_statistics`. Unlike that one there is **no containment test either**.

The ICNF report offers a ``geometry`` mode because its perimeters can and do fall outside
Portugal, into the sea or across the Spanish border, and a fire that is not in the country
should not be in the country's total. CONAFOR's do not: the published extent of all
fourteen archives is inside Mexico. A point-in-polygon per fire would cost something to
confirm what is already known.

So the ``Country`` column is a **label, not a computed answer**, and this is the one report
in the family that runs against a database with **no OCHA boundaries imported at all**.
Both options are still accepted by the parser, purely so they can be refused with a message
that says why — anyone reaching for them has copied a GWIS or ICNF command line, which is a
reasonable thing to have done.

Three ways to get a hectare, one of them unique to this report
---------------------------------------------------------------

======================  ==================================================================
``geodesic``            Measures the perimeter on the WGS84 ellipsoid. The default, and
                        what the sibling reports mean by an area.
``equal-area``          Projects to EPSG:6933 and measures there. Agrees with the above to
                        within thousandths of a percent.
``reported``            Uses CONAFOR's published ``AREA_HA`` and measures nothing.
======================  ==================================================================

The third exists because this dataset is the one that makes it interesting. CONAFOR
publishes **both** a perimeter and a burnt area, and from 2016 the second *is* the first's
own area — the median ratio between them is 1.000 and four rows in five agree to within 1%.
The two are a check on each other, and running the report twice is how the 2010 warning
below becomes a number rather than a claim.

Mexico's own projected CRS, ITRF2008 / LCC (EPSG:6362), is **not** offered: it is a Lambert
conformal conic, so its ``ST_Area`` is not a burnt area, for the same reason the ICNF report
declines EPSG:3763. Nothing is lost — unlike Portugal, CONAFOR publishes in EPSG:4326 and
nothing is stored in a national grid to reproduce.

.. warning::

   **The counts are not comparable across 2016, and 2010's areas are not comparable with
   anything.**

   The feature count steps by an order of magnitude at 2016 — 628 polygons in 2014 against
   3,244 in 2016 — because before then CONAFOR published only the fires it had drawn and
   from 2016 it publishes the season. That is a change in what was mapped, not in what
   burnt.

   And the areas the 2010 layer publishes do not describe its polygons: the median ratio
   between them is 3.0 and the 90th percentile 65. Under ``--area-method reported`` that
   year's figures are a different measurement from every other year's.

.. note::

   **The ``Fires`` column can differ by a handful between two runs**, and that is the truth
   about the dataset rather than an inconsistency.

   A measured method needs a polygon, so the nine 2012 features that publish attributes and
   an empty shape are not counted. ``reported`` needs a published area, so the one fire
   that leaves ``AREA_HA`` empty — ``21-24-0078``, which publishes everything else — is not
   counted, and the nine shapeless ones are.

   Forcing the two to agree would mean making three columns wrong for nine fires in order
   to make one column consistent.

.. note::

   **The years come from a ``DISTINCT`` over the data and not from a range**, so a year
   the database does not hold is a gap in the report rather than a row reading zero —
   which would say that nothing burnt in Mexico that year, when what it means is that the
   archive was not imported.

   That is not hypothetical for this dataset. The 2015 archive is distributed separately
   from the others and is easy to miss; a report run without it should leave 2015 out, not
   invent it.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.mexico_conafor.wildfire_statistics
   :members:
   :show-inheritance:
