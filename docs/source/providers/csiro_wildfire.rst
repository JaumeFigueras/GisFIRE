CSIRO wildfire
==============

The burnt area model for the Australian historical bushfire extents. See
:doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, and :doc:`csiro_provider` for
the dataset itself.

Four things about it are worth knowing before using it. **Half of what it holds is not a
wildfire**: 166,048 of the published features are prescribed burns and 93,960 more are
published as ``Unknown``, so ``fire_type`` is the column every count has to apply and
``v_csiro_bushfire`` is that filter already applied. **One row is one published polygon**, and
nothing is merged: grouping on ``(source_layer, state_code, fire_id, ignition_date)``
turned out to join features up to 2,403 km apart, Western Australia's small fire numbers
being district sequences reused across the state. **Every published value is kept beside its
normalised form**, because the two feature classes spell the same state, type and cause
differently. And **the perimeter is stored once**, in EPSG:4326 on the generic model: the
published EPSG:4283 is geographic degrees 1.8 m away from it, so unlike the Portuguese,
Canadian, Catalan and Andalusian models there is no second geometry worth keeping.

.. automodule:: src.providers.australia_csiro.wildfire
   :members:
   :show-inheritance:
