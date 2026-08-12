INAB fire report import (Guatemala)
===================================

Imports Guatemala's *Monitoreo de Incendios Forestales* — the ``datos_generales`` layer,
**4,615 fire reports over 2023-2026**, one row per fire phoned in to INAB — from the
GeoJSON files :doc:`inab_download_wildfires` writes.

The first importer in the project whose source is an API download rather than a published
archive, and the third to need no ``ogr2ogr`` after :doc:`egif_import_wildfires` and
:doc:`greece_ffa_import_wildfires` — the source is JSON, and the only geometry work is a
point PostGIS builds from two numbers. See :doc:`../providers` for the dataset and
:doc:`../providers/inab_wildfire` for what each column means.

Only the ``fire-reports`` layer is imported. The other four the downloader can fetch have
no model behind them: ``informes`` is a second, one-to-many model rather than more columns
on this one, and the burn-scar layers are a single season rather than an archive.

Usage
-----

Over a whole download directory, or over named files, or over selected years:

.. code-block:: console

   python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \
       -d ~/data/guatemala

   python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \
       -s guatemala_inab_fire-reports_2025.geojson

   python3 -m src.apps.imports.wildfires.guatemala_inab.import_wildfires \
       -s guatemala_inab_fire-reports_all.geojson --year 2025 2026

``-d`` and ``-s`` are mutually exclusive and one is required. ``-d`` reads every
``*.geojson`` in the directory and leaves the downloader's ``*.meta.json`` provenance
sidecars alone. ``--dry-run`` does the whole job — the deletes included — and rolls it
back.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``.

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` first, so that the fires
get a country. The import runs without them and says so.

.. note::

   The time zone areas are **not** needed, as for :doc:`greece_ffa_import_wildfires`.
   Guatemala is one zone for the whole country, is UTC-6 all year and has observed no
   daylight saving since 2006, so
   :data:`~src.providers.guatemala_inab.DEFAULT_TIME_ZONE` is a rule rather than
   something resolved from each fire's location.

   What the import does check is that PostgreSQL itself knows the zone name, because the
   ``v_inab_*`` views resolve ``AT TIME ZONE`` with it — a failure that would otherwise
   surface months later, in whatever query first selected from the view.

A year is the unit of work
--------------------------

This dataset is small: 4,615 records, 0.9 MB, the whole of it fetchable in one request the
downloader deliberately does not make. Importing it in a single transaction would work.

It is imported **a year at a time anyway**, one transaction per year, as every other
importer in the project does — because the size of a source is the least durable thing
about it. This one has grown from 187 records in 2023 to 727, then 1,789, then 1,908 in
the first seven months of 2026, and an import whose shape depends on the data staying
small has to be rewritten the year it stops being small.

What that buys today rather than later: a run interrupted half way keeps the years it
finished, ``--year`` makes re-importing one year a fraction of a second, and the log says
what each year did rather than what the run did.

Every file is read before any year is written. That is what makes the year buckets
complete: a run given both the ``all`` file and a per-year file would otherwise import the
same records twice, the second copy failing on ``inab_wildfire.global_id`` half way
through, having already replaced some years. Reading first also means the duplicate is
found and reported rather than hit.

Replacing a year, and why the delete also keys on the identifier
-----------------------------------------------------------------

A year is **replaced wholesale**: the stored fires whose start instant falls in it are
deleted and the file's records inserted, so re-importing a revised publication supersedes
rather than doubles, and a report INAB has withdrawn goes.

The delete removes one more thing than that — every stored row whose ``global_id`` is in
the batch, whatever year it is currently filed under — and that clause is worth
understanding, because it guards against a disagreement that would otherwise be silent.

A year here is the **Guatemalan calendar year**, resolved through the zone above: that is
the year the fire happened in, and what ``v_inab_wildfire.start_date_time_local`` shows.
The downloader's ``--year``, by contrast, asks the ArcGIS server for
``EXTRACT(YEAR FROM fecha_hora_incendio)``, which the server evaluates itself. If it does
so in UTC, then a fire reported in the last six hours of 31 December is in the server's
*next* year and in this program's *current* one — and a year-only delete would remove the
row that the other file had stored and not put it back. With the identifier clause the row
moves between years instead of vanishing. It costs one ``OR``, and it removes the whole
class of problem.

The instant is published as UTC
--------------------------------

``fecha_hora_incendio`` arrives as milliseconds since the Unix epoch — ArcGIS's own
serialisation, UTC by definition — or as ISO 8601 if the file was fetched with the
downloader's ``--iso-dates``. Both are read, so a file can be imported however it was
fetched.

There is therefore **no local-to-instant conversion** here, unlike the Greek and Spanish
imports: what the source publishes is already an instant, and what this import adds is the
zone name it should be read back in. The times are worth trusting — in local time the
hourly histogram peaks between 13:00 and 16:00, the afternoon fire peak, rather than
clustering at midnight the way three quarters of the Portuguese archive does.

No personal data is read
------------------------

The published layer carries the **name and telephone number of whoever reported each
fire** — 1,969 distinct pairs, most of them private individuals — and the INAB accounts
that created and last edited each record.
:data:`~src.providers.guatemala_inab.PERSONAL_FIELDS` names all four, and neither model
has a column for them.

They are dropped **here**, by never being read out of the feature, rather than by being
left unmapped after a staging load. That is the reason this importer parses the GeoJSON in
Python instead of handing it to ``ogr2ogr``, which would land all thirty-three published
attributes in a real table in the database before the mapping got a say. Nothing outside
``IMPORTED_FIELDS`` reaches a bind parameter, and a test asserts that no published
personal value is anywhere in either table afterwards.

The traps this source sets
--------------------------

.. warning::

   **An unfilled text field is sometimes ``null`` and sometimes ``""``, in the same
   column.** ``nombre_ap_1`` is ``null`` on 80 records and ``""`` on 3,080 of them, so an
   import that stores what it is handed reports 3,080 fires as being inside a protected
   area called ``""`` — which counts as *filled* in any ``IS NOT NULL`` afterwards and is
   invisible in a spot check. It happened during the model's validation.

   Every text attribute goes through
   :func:`~src.providers.guatemala_inab.blank_to_none`, and ``read_text`` is the only way
   this application reads one.

**The municipality code is inside the name.** ``rio_hondo_1903`` is Río Hondo, department
19, municipality 03. :func:`~src.providers.guatemala_inab.parse_municipality` takes it
apart and validates the code's department against the published one, which is what rejects
the four truncated slugs that name the wrong department; the slug itself is stored whole
either way, and the 22 affected records keep their department.

**The typed coordinates are not the location.** ``coordenada_x``/``coordenada_y`` are
filled on 440 records, a dozen of them with the axes swapped and fifteen out of range
entirely. They are stored as published and never reprojected or used to place a fire — the
geometry is the answer, and it is EPSG:4326 already.

**Three points are not in Guatemala.** Two are longitudes that lost their minus sign and
the third is 200 km into Honduras; all three are already flagged ``falso`` by INAB. They
are stored as published and counted in the run's report. A coordinate this import invented
would be worse than one the provider got wrong.

What is refused, and what is only degraded
-------------------------------------------

Two things make a record unstorable, and both are refusals to invent a value for a
``NOT NULL`` column:

* **no ``fecha_hora_incendio``** — four of the 4,615 records, which carry nothing but an
  identifier and a map tap. There is no second date in this layer to fall back on, and the
  year would date them to 1 January, which is an invention;
* **no ``globalid``** — no record published today lacks one, and one that did could not be
  re-imported or matched to anything.

Everything else is degraded rather than refused. A record with no geometry is stored
**without a point**, which the model allows and ``v_inab_wildfire`` left-joins for. A
false alarm is stored, with its ``estado_aviso`` on the row, because a record saying *this
was not a fire* can be filtered afterwards and a discarded one cannot be recovered — the
same call :doc:`greece_ffa_import_wildfires` makes. Anything counting fires has to exclude
the 140 ``falso`` records; see :func:`~src.providers.guatemala_inab.is_false_alarm`.

.. note::

   **No report over this data can sum a burnt area.** INAB publishes thirty-three
   attributes and not one of them is a size — no perimeter, no hectares, no land-cover
   split. This dataset answers *where and when*, not *how much*.

   What can be reported is counts, and two applications do:
   :doc:`inab_wildfire_statistics`, whose three hectare columns are present and empty on
   every row, and :doc:`inab_wildfire_classification`, which counts the four published
   vocabularies — and which is not a causes report, there being no cause here either.

What the run reports
--------------------

One line per year as it is committed, then a summary: fires written, years, files, how
many have a point, how many are false alarms, how many unverified, how many records were
skipped, how many duplicates were found across the files, how many had a per-record
problem, and how many stored fires the run replaced. Points outside Guatemala get a
warning of their own.

Per-record problems — an unreadable date, a coordinate that is not a number, a geometry
that is not a point — are logged with the record's position in its file and its
identifier, and capped at twenty per run so that a systematically wrong file cannot bury
the summary that says so.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.guatemala_inab.import_wildfires
   :members:
   :show-inheritance:
