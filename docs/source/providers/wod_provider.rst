WOD provider package
====================

Constants and rules shared by the WOD models and the import application: the provider
identity — the Bioeconomy Science Institute (formerly Scion), with FENZ and DOC — the
published CRS (NZTM2000, EPSG:2193), the two time zones, the year the import starts from,
the ``-9999``/``NA:NA`` sentinels, the placeholder coordinate, and the published
vocabularies of source, season, area category and ENSO phase.

Two rules live here because the models, the import and its tests all need them:

:func:`~src.providers.new_zealand_wod.fire_cause`
    Classifies a published ``IgnSource`` into **lightning**, **natural** (geothermal or
    volcanic — natural and not lightning), **human** or **unknown**, through
    :data:`~src.providers.new_zealand_wod.CAUSE_MAP`, which lists every one of the 128
    published spellings. A spelling the map does not know raises
    :class:`~src.providers.new_zealand_wod.UnmappedCauseError` instead of quietly becoming
    *unknown*: a new release's new cause has to be classified by a person.

:func:`~src.providers.new_zealand_wod.wod_id`
    Repairs the one identifier the export wrote in scientific notation — ``WOD1e+05`` is
    ``WOD100000``.

The module docstring is where the dataset itself is written down: the four rows each
record becomes, the coverage by period and agency, and every kind of dirt with what is
done about it.

.. automodule:: src.providers.new_zealand_wod
   :members:
   :show-inheritance:
