Greek Fire Service ignition
===========================

Where a Greek fire was reported, as published from 2020 on — ``X-ENGAGE`` and
``Y-ENGAGE``, a longitude and a latitude in decimal degrees. See
:doc:`../data_model/ignition` for the columns it inherits and why an ignition is a model
of its own, and :doc:`greece_ffa_wildfire` for the fire it belongs to.

Two things about it are worth knowing before using it. It exists for **54,491 of the
260,194 fires**: no year before 2020 publishes a coordinate at all, and 3,755 of the
later rows carry the ``0``/``0`` the service writes for a fire it did not locate. And it
is the one ignition in GisFIRE that stores **no coordinate columns of its own** — the
published pair is already EPSG:4326, so the inherited geometry *is* it, where the
:doc:`Spanish <egif_ignition>` and :doc:`Andalusian <rediam_ignition>` points keep the
published easting and northing because their geometry is a reprojection.

.. warning::

   The point is where the service was **engaged**, not necessarily where the fire began.
   ``ENGAGE`` is the dispatch system and the coordinate is the incident location it
   recorded — the same thing for a fire reported from beside it, not the same thing for
   one reported from the next village, and nothing published says which.

.. automodule:: src.providers.greece_ffa.ignition
   :members:
   :show-inheritance:
