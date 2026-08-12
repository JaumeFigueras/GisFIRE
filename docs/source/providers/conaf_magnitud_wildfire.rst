CONAF *incendios de magnitud* wildfire
======================================

One mapped perimeter of a large Chilean fire. See :doc:`../data_model/wildfire` for the
columns it inherits, :doc:`conaf_magnitud_provider` for the dataset, and
:doc:`conaf_wildfire` for the report of the same fire.

Four things about it are worth knowing before using it.

**A fire is several published features.** There is no ``GID``: a fire mapped in pieces is
published as several features sharing a season and a name, and ``668 - CANIHUAL VII`` of
2018-2019 is thirteen of them. The import dissolves on the season, the folded name **and
the office's number** — the number matters, because ``120_LOS MAITENES`` and
``388_LOS MAITENES`` of 2016-2017 are two fires three weeks apart, and dissolving without
it turned 743 fires into 739.
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.part_count`
records how many pieces a row came from; 19 of the 743 are more than one.

**There are two areas, and they are two measurements.** ``SUPERFICIE`` is the *feature's
own polygon area* — the median ratio of computed to declared area is 1.000 in every one
of the thirteen archives — so summing it over overlapping pieces double-counts.
``37_TIL TIL`` of 2016-2017 is six features each declaring 327.50 ha of one 327.8 ha fire.
So :attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.area_ha_mapped`
is computed from the union and
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.area_ha_published`
keeps the sum of the parts beside it, so the disagreement stays visible.

.. note::

   ``area_ha_mapped`` is deliberately not called ``area_ha``: it is the *mapped* area, and
   the reported burnt area of the same fire is
   :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_ha_total`, a different
   number from a different measurement.

**Exactly one of the two grids is filled**, as on :doc:`conaf_ignition`:
``perimeter_utm19s`` on EPSG:32719 for the mainland, ``perimeter_utm12s`` on EPSG:32712
for the one Rapa Nui perimeter, and a ``CHECK`` that says one and not both.

**The link to the report is written by the binder, and never without its reason.**
``conaf_wildfire_id``, ``match_method``, ``match_confidence`` and ``matched_at`` are
filled by :doc:`../applications/conaf_magnitud_bind_wildfires`, and a ``CHECK`` enforces
that the link and the method arrive together: a row claiming which fire it is without
saying how it knows is not evidence of anything. **No method scores 1.00** — the office's
``NUMERO_REG`` is a shared identifier but not a unique one, so every binding is an
inference.

.. automodule:: src.providers.chile_conaf_magnitud.wildfire
   :members:
   :show-inheritance:
