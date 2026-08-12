INAB wildfire
=============

One fire report from Guatemala's *Monitoreo de Incendios Forestales*. See :doc:`../providers`
for how provider models relate to the generic ones, :doc:`../data_model/wildfire` for the
columns it inherits, :doc:`inab_provider` for the dataset, and :doc:`inab_ignition` for the
point each report carries.

Three things about it are worth knowing before using it.

**There is no burnt area and no perimeter.** This is the first provider in GisFIRE that
publishes neither: :doc:`egif_wildfire` and :doc:`greece_ffa_wildfire` publish no shape but
do publish hectares, five figures and eight. INAB publishes thirty-three attributes and not
one is a size. What this dataset answers is *where and when*, not *how much*.

**A row is a report, not a fire.** 57 published pairs share an exact coordinate and an exact
minute — the same fire called in by two institutions, sometimes reaching two different
outcomes. ``global_id`` is unique because a report is unique, and a ``count(*)`` here counts
reports.

**140 records say there was no fire.** ``report_status`` is the column every honest query
filters on; see :func:`~src.providers.guatemala_inab.is_false_alarm`.

.. automodule:: src.providers.guatemala_inab.wildfire
   :members:
   :show-inheritance:
