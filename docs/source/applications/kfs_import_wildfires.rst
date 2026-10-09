Korea Forest Service wildfire import
====================================

Imports the South Korean wildfire statistics, *산불통계데이터*, from the CSV the Korea
Forest Service publishes on data.go.kr (dataset 15121380) — **2,020 fires from January
2022 to September 2025** in the 2025-09-12 release.

The CSV is read as published, in CP949; no English copy is needed or used. It holds no
coordinate, so like :doc:`greece_ffa_import_wildfires` for its early years this needs no
``ogr2ogr`` and no boundaries. See :doc:`../providers` for the dataset and
:doc:`../providers/kfs_wildfire` for what each column means.

Usage
-----

Over the release file, or over the directory it was unpacked into:

.. code-block:: console

   python3 -m src.apps.imports.wildfires.south_korea_kfs.import_wildfires \
       -s "산불통계데이터/산불발생통계(20251110).csv"

   python3 -m src.apps.imports.wildfires.south_korea_kfs.import_wildfires \
       -d 산불통계데이터/

   python3 -m src.apps.imports.wildfires.south_korea_kfs.import_wildfires \
       -d 산불통계데이터/ --year 2025 --dry-run

``-d`` and ``-s`` are mutually exclusive and one is required. With ``-d`` every ``.csv``
in the directory with the statistics header is imported; the data dictionary shipped
beside it is skipped with a warning. ``--year`` imports only the years named.
``--dry-run`` reads, checks and reports without connecting to a database.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``.

What it does
------------

**A year is replaced wholesale.** Nothing in a row identifies a fire, so each year in the
file is deleted and re-inserted in one transaction. A release holds the recent years and
ends part way through the current one; importing the next release revises the years it
holds and leaves older ones alone.

**Every cause text is checked first.** A text not in the cause table
(``src/providers/south_korea_kfs/causes.py``) stops the import, with the list of them,
before any year is deleted. Translate and classify the new texts there, then import
again.

**A bad end is stored as no end.** The twelve fires that end before they start and the
two that end in 2055 and 2223 are stored with ``end_date_time`` ``NULL`` and the reason in
``end_date_problem``. A row is skipped only when it has no valid start, no area, or no
office, province or cause; no row of the 2025 release is.

**Times are Korean local time**, converted to instants in ``Asia/Seoul`` by PostgreSQL.
Place names are romanized and cause texts translated and classified as each row is
written.

The run ends with the fires, area, unstored ends and suspected causes per year, and the
fires per cause class. For the 2025 release:

.. code-block:: text

   2022: 756 fire(s), 24797.16 ha, 10 with no stored end, 156 with a suspected cause
   2023: 589 fire(s), 4988.02 ha, 2 with no stored end, 137 with a suspected cause
   2024: 278 fire(s), 131.93 ha, 0 with no stored end, 43 with a suspected cause
   2025: 397 fire(s), 105011.38 ha, 2 with no stored end, 67 with a suspected cause

In QGIS the fires are the ``v_kfs_wildfire`` view, which has no geometry and loads as a
table.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.south_korea_kfs.import_wildfires
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.wildfires.south_korea_kfs.readers
   :members:
   :show-inheritance:
