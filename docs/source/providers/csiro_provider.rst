CSIRO provider
==============

The dataset behind :doc:`csiro_wildfire`: the two feature classes of the Australian
historical bushfire extents, the identifiers that are mostly placeholders, the half of the
archive that is deliberate burning, the dates that are days and the ones that are not
dates at all.

Read this before the model. The columns make sense only against what the geodatabase
publishes — in particular why the archive is stored one row per published polygon and
nothing is merged, why ``fire_id`` is indexed but not constrained, and why every count
over more than one provider has to mention ``fire_type``.

.. automodule:: src.providers.australia_csiro
   :members:
   :show-inheritance:
