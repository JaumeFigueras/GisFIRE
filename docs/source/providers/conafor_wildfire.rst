CONAFOR wildfire
================

The burnt area model for Mexico's national cartography, CONAFOR's *Incendios Forestales*.
See :doc:`../providers` for how provider models relate to the generic ones,
:doc:`../data_model/wildfire` for the columns it inherits, :doc:`conafor_provider` for the
dataset, :doc:`conafor_fire_cause` for the classification it links to, and
:doc:`../applications/conafor_import_wildfires` for the import that fills it.

Three things about it are worth knowing before using it. **There is one perimeter and only
one**, unlike :doc:`icnf_wildfire` and :doc:`nbac_wildfire`, because CONAFOR publishes in
EPSG:4326 already and there is no national grid to keep beside it. **The published key is
unique**, which no other perimeter provider in GisFIRE can say, so this dataset can be
re-imported row by row rather than layer by layer. And **the 2010 areas do not describe
the 2010 polygons** — the median ratio between them is 3.0 and the 90th percentile is 65 —
so anything measuring burnt area across the series has to filter on
:attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.year` or measure from the
geometry.

.. automodule:: src.providers.mexico_conafor.wildfire
   :members:
   :show-inheritance:
