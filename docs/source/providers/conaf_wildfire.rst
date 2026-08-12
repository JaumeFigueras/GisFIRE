CONAF wildfire
==============

One fire report from CONAF's seasonal archive (Chile). See :doc:`../providers` for how
provider models relate to the generic ones, :doc:`../data_model/wildfire` for the columns
it inherits, :doc:`conaf_provider` for the dataset, :doc:`conaf_ignition` for the point
every report carries, and :doc:`conaf_magnitud_wildfire` for the polygons of the large
fires.

Four things about it are worth knowing before using it.

**The perimeter is always NULL and always will be.** CONAF publishes the report as a
point; the polygons are a different published product with a different
``data_provider_id``, and writing one onto a report row would make the provenance a lie.
The two are related by
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.conaf_wildfire_id`,
which :doc:`../applications/conaf_magnitud_bind_wildfires` fills in — perimeter to
report, the direction :doc:`nbac_wildfire` and :doc:`rediam_wildfire` also point in.

**Half the archive has no date.**

.. warning::

   49,470 of the 95,868 fires carry
   :data:`~src.providers.chile_conaf.PRECISION_SEASON`, which means their start is a
   placeholder: ``start_date_time`` is 1 July at midnight because that is where the
   import put it. Eight of the fifteen mainland seasons publish no start at all.

   Filtering on the instant, grouping by month or hour, or subtracting it from an end
   date gives an answer for the other half of the archive and nonsense for this one.
   :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.date_time_precision` is the
   only column that says which is which, and it is indexed for exactly that.

**There are fourteen published areas, in three groups and a total.** CONAF reports burnt
area by what burnt, and the columns nest::

   pine_0_10 + pine_11_17 + pine_18_plus + eucalyptus + other_plantation = plantation
   native_forest + scrub + grassland                                     = vegetation
   agricultural + debris                                                 = other
   plantation + vegetation + other                                       = total

The pine bands are **stand ages in years** — 0-10, 11-17, 18 or more — not tree sizes: a
young *Pinus radiata* plantation and a mature one are different fuels and different
money, and CONAF has reported them apart since the archive begins.

Every column is stored as published, drift included. The arithmetic holds on 90,128 of
the 95,831 readable rows and fails on the rest, almost all of them in 2010-2011,
2011-2012 and 2015-2016;
:attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_totals_agree` records which
is which, so a report can say how much of its total it is standing on rather than
discovering the gap by subtraction.

**Nothing here is a key.** ``NUMERO_REG`` repeats within a season and even within a
región — 2021-2022 has 6,884 fires and 5,975 distinct ``(CODREG, NUMERO_REG)`` pairs — and
``NOM_INCEN`` is a place name that repeats freely. Neither is constrained, and neither
should be joined on outside the binder, which uses them together with the season and
corroborates them spatially.

.. automodule:: src.providers.chile_conaf.wildfire
   :members:
   :show-inheritance:
