Korea Forest Service wildfire
=============================

The fire model for the Korea Forest Service's *산불통계데이터* statistic. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, and :doc:`kfs_provider` for
the dataset.

Three things about it are worth knowing before using it. It has **no geometry and no
ignition**: the statistic publishes place names, never a coordinate, so the perimeter and
the country are ``NULL`` and the fire can be placed only by its names. Every name is
stored **as published and romanized** (``*_rr``). And the cause is stored as the three
published columns, an English translation, one of eighteen classes and one of the four
fire causes shared with the New Zealand WOD.

.. automodule:: src.providers.south_korea_kfs.wildfire
   :members:
   :show-inheritance:
