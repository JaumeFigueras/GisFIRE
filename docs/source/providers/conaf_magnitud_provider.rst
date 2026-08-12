CONAF *incendios de magnitud* provider package
==============================================

Constants shared by the perimeter model, its import and its binder: the product identity,
the 200-hectare threshold, the first season the perimeters exist for, the key the import
dissolves a fire's pieces on, the eight match methods with their confidences, the default
match tolerance, and the reader that splits the ``'402 - SAN GUILLERMO'`` prefix into a
number and a name.

.. important::

   This is **Chile's CONAF**, not Mexico's CONAFOR (:doc:`conafor_provider`). See the note
   in :doc:`conaf_provider`.

This is CONAF's second published product: the burnt-area polygons of the fires that
reached roughly 200 hectares, one shapefile per *temporada* from 2013-2014 on, with Easter
Island in its own archive. **781 published features over thirteen archives, dissolving to
743 fires.**

Unlike NBAC and NFDB, which are two agencies' independent accounts of Canadian fire, these
two archives are **one agency's one incident record published twice**: every one of the
743 fires here is also a report in :doc:`conaf_provider`. They are still two
:class:`~src.data_model.data_provider.DataProvider` rows sharing a name, because they are
two published products with different attributes, different geometry and independent
release cadences, and because a row has to be checkable against the file it came from.

.. warning::

   A query over ``wildfire`` filtered only by provider **name** therefore counts 743
   Chilean fires twice. Filter by ``data_provider_id``, or by the polymorphic ``type``.

.. note::

   **The archive is not exhaustive.** 2021-2022 has 97 reports of 200 ha or more in
   :doc:`conaf_provider` and 62 perimeters here; 2019-2020 has 86 and 62; 2024-2025 has 81
   and 55. A perimeter is evidence a fire was mapped, and its absence is not evidence a
   fire was small.

.. automodule:: src.providers.chile_conaf_magnitud
   :members:
   :show-inheritance:
