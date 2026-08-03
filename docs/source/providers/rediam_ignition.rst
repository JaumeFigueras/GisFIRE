REDIAM ignition
===============

Where an Andalusian fire started, as published in the yearly layers of 2021-2024 —
``X_INIC`` and ``Y_INIC``, a point on the same grid as the perimeter. See
:doc:`../data_model/ignition` for the columns it inherits and why an ignition is a model
of its own, and :doc:`rediam_wildfire` for the fire it belongs to.

Two things about it are worth knowing before using it: it exists for **201 of the 907
fires**, because those four years are the only ones that publish a coordinate at all; and
the published point is often **not inside the published perimeter** — 88 of the 201 are —
which is a disagreement between two observations rather than an error to repair.

.. automodule:: src.providers.andalusia_rediam.ignition
   :members:
   :show-inheritance:
