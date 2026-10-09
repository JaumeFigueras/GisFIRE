KFS wildfires by cause (South Korea)
====================================

Counts the Korea Forest Service wildfires by cause, per year, in two tables. The
companion of :doc:`kfs_wildfire_statistics`, over the same fires and scope: the
``Country``, ``Year`` and ``Fires`` columns agree row for row.

The **shared fire causes** table has the columns of :doc:`wod_wildfire_causes`, so South
Korea and New Zealand can be set side by side: the fires, how many have a determined
cause, lightning, other natural, human and unknown, and lightning's share of the fires
and of the area. The **cause classes** table is this dataset's own: for each year and
each of the eighteen classes, the fires and burnt area with their shares of the year,
and how many give the cause as suspected rather than established.

.. important::

   The causes come from the **free-text** cause, ``발생원인_기타``. The published coded
   cause is *other (free text)* on three rows in four, so the import translates every
   spelling and classifies it — see :doc:`../providers/kfs_provider`. A suspected cause
   is classified by what it suspects; ``Suspected`` says how many. Fires rekindled from
   an earlier one are ``Unknown`` in the shared table.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.south_korea_kfs.wildfire_causes \
       --csv causes.csv --classes-csv classes.csv --docx causes.docx

   python3 -m src.apps.statistics.wildfires.south_korea_kfs.wildfire_causes \
       --year 2025 --province 경북 --classes-csv gyeongbuk-2025.csv

At least one of ``--csv``, ``--classes-csv`` and ``--docx`` is required; the Word
document holds both tables. ``--year`` and ``--province`` select as in
:doc:`kfs_wildfire_statistics`.

In the shared table the percentages are of the fires whose cause is known, as in every
cause report; in the class table they are of all the year's fires and area, so a year's
classes add up to 100%.

For the 2025-09-12 release, every year together:

.. code-block:: text

   Year   Fires  Determined  Lightning  Lightning (%)  Natural  Human  Unknown  Lightning (ha)
   Total  2020   1716        9          0.52           0        1707   304      0.50

   Class                 Fires  Fires (%)  Area (ha)  Area (%)  Suspected
   visitor               516    25.54      2824.32    2.09      258
   unknown               301    14.90      1355.46    1.00      0
   waste_burning         208    10.30      1737.73    1.29      11
   agricultural_burning  157    7.77       53078.65   39.34     4
   grave_visitor         57     2.82       46755.45   34.65     3
   other                 9      0.45       16315.08   12.09     4
   lightning             9      0.45       0.50       0.00      3

Lightning is nine fires and half a hectare: South Korea's fires are started by people.
The area shares are single fires — agricultural burning and grave visitor are the two
Uiseong fires of 2025, *other* the 2022 Uljin fire.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.south_korea_kfs.wildfire_causes
   :members:
   :show-inheritance:
