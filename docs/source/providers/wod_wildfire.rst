WOD wildfire
============

The fire record of the New Zealand *Wildfire Occurrence Database*. See :doc:`../providers`
for how provider models relate to the generic ones, :doc:`../data_model/wildfire` for the
columns it inherits, :doc:`wod_provider` for the dataset, :doc:`wod_ignition` for the point
every record has, and :doc:`wod_terrain` and :doc:`wod_weather` for the fire environment
attached to it.

Three things about it are worth knowing before using it. **The identifier is a key**:
``wod_id`` is unique and stable across releases, unlike most identifiers in GisFIRE, and it
is what a re-import matches on. **Most records have no perimeter** — 2,089 of 128,020 do,
kept in NZTM2000 beside the EPSG:4326 copy, and there are none for 2012-2016. And the
**cause is stored twice**: verbatim, as the agency recorded it, and classified into four
classes, lightning kept apart from every other natural cause.

``start_date_time`` is when the fire was **reported**, the paper's proxy for ignition. A
DOC record has no time and starts at local midnight; its ``report_time`` is ``NULL``, which
is what tells it from a fire really reported at 00:00.

.. automodule:: src.providers.new_zealand_wod.wildfire
   :members:
   :show-inheritance:
