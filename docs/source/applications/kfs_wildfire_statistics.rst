KFS wildfire burnt area (South Korea)
=====================================

Reports the Korea Forest Service wildfire statistics per year: the number of fires, the
smallest and the largest single fire, and the total burnt area in hectares. The six
columns are the ones every burnt-area report shares, so the CSV can be concatenated with
the others.

The hectares are the ones the service **reports** (``피해면적_합계``): the dataset
publishes no perimeter, so there is no ``--area-method``, and one area per fire, so there
is no ``--surface``. Every fire is South Korean and none has a coordinate, so there is no
``--country``; ``--province`` selects one province by its published abbreviation.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.statistics.wildfires.south_korea_kfs.wildfire_statistics \
       --csv burnt.csv --docx burnt.docx

   python3 -m src.apps.statistics.wildfires.south_korea_kfs.wildfire_statistics \
       --province 경북 --min-area 1 --csv gyeongbuk.csv

At least one of ``--csv`` and ``--docx`` is required. ``--year`` restricts to one year,
the year the fire started; ``--min-area`` counts only fires of at least that many
hectares.

For the 2025-09-12 release:

.. code-block:: text

   Country      Year   Fires  Minimum (ha)  Maximum (ha)  Total (ha)
   South Korea  2025   397    0.01          52707.30      105011.38
   South Korea  2024   278    0.01          19.79         131.93
   South Korea  2023   589    0.01          1337.00       4988.02
   South Korea  2022   756    0.01          16301.98      24797.16
   South Korea  Total  2020   0.01          52707.30      134928.49

.. warning::

   **The last year of a release is partial.** A year whose last fire is before December
   is reported as incomplete — in the log and in the Word document — with the date of
   its last fire: 11 September for 2025 above.

.. note::

   Fires are filed where they **started**. The two Uiseong fires of March 2025, three
   quarters of the area above, burnt into four other municipalities and count wholly
   towards Gyeongbuk's Uiseong.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.south_korea_kfs.wildfire_statistics
   :members:
   :show-inheritance:
