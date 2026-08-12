INAB ignition
=============

Where a Guatemalan fire was reported to be. See :doc:`inab_wildfire` for the report it
belongs to and :doc:`inab_provider` for the dataset.

**Every published record has a point**, which makes this the best-located administrative
fire statistic in the project — :doc:`greece_ffa_ignition` has one for a fifth of its
records and :doc:`egif_ignition` has one that must be rebuilt from a UTM zone and a datum
code. Here it arrives as EPSG:4326 longitude and latitude.

The form's own typed coordinates are kept beside it and are **not** a location to use: they
are filled on 440 records of 4,615, twelve have the axes swapped, fifteen more are out of
range, and where usable they disagree with the point by a median of 130 m — an independent
reading rather than a copy. See the module docstring.

.. automodule:: src.providers.guatemala_inab.ignition
   :members:
   :show-inheritance:
