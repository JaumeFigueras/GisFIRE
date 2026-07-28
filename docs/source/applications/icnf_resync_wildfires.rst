Resync ICNF wildfires from the WFS
==================================

Goes back to the ICNF's WFS to recover the times the shapefile export truncated,
and refreshes every other published attribute while it is there. Run it after
:doc:`icnf_import_wildfires`.

.. contents::
   :local:
   :depth: 2

Why it exists
-------------

The bulk import reads ``SHAPE-ZIP`` archives, and a shapefile's DBF has no
datetime type. ``DH_Inicio``, ``DH_1Interv``, ``DH_Fim`` and ``Edicao`` are
``xsd:dateTime`` at the source and arrive **truncated to dates**:

.. code-block:: text

   WFS       2024-01-31T20:03:00Z
   archive   2024-01-31              -> stored as local midnight, marked "day"

Twenty hours out, and honestly labelled as such — which is what
:attr:`~src.providers.icnf.wildfire.IcnfWildfire.date_time_precision` is for. This
application replaces those dates with the instants the source actually holds and
marks the rows :data:`~src.providers.icnf.PRECISION_MINUTE`.

Usage
-----

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.portugal_icnf.resync_wildfires

   # see what would change, change nothing
   python3 -m src.apps.imports.wildfires.portugal_icnf.resync_wildfires --dry-run

   # one layer, or a few
   python3 -m src.apps.imports.wildfires.portugal_icnf.resync_wildfires -l ardida_2024

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line.
Unlike the import applications this one needs no GDAL: it speaks HTTP and SQL.

The times really are UTC
------------------------

The WFS returns ``2025-01-02T20:16:00Z``, and a ``Z`` cannot be taken on trust —
GeoServer will happily stamp one onto a local wall-clock reading, and storing that
as UTC would be an hour out for every summer fire.

It was checked against the dates the archives published, using the 55 fires of
2025 whose two possible readings fall on **different calendar days** — the ones
starting between 23:00 and midnight UTC in summer, when Lisbon is UTC+1:

=============================================================  ==========
Reading                                                        Agreement
=============================================================  ==========
published date == local date, treating ``Z`` as real UTC       2084/2084
published date == the date of the ``Z`` string as written      2029/2084
=============================================================  ==========

So the values are genuine instants and are stored **unchanged**. This is the only
place in the project where a published datetime needs no conversion — every
importer has to read a naive local reading and convert it, and this one must not.

:attr:`~src.data_model.wildfire.Wildfire.time_zone` is left alone. Nothing is
derived from it any more, but it is still what turns a stored instant back into
the wall-clock time the ICNF would print.

What gets resynced
------------------

Everything the WFS publishes except the geometry:

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Column
     - From
   * - ``start_date_time``, ``end_date_time``
     - ``DH_Inicio``, ``DH_Fim`` — on the parent ``wildfire`` row
   * - ``first_response_date_time``, ``edition_date_time``
     - ``DH_1Interv``, ``Edicao``
   * - ``date_time_precision``
     - becomes ``minute`` wherever a start actually arrived
   * - ``anepc_code``, ``year``, ``duration_minutes``
     - ``Cod_ANEPC``, ``Ano``, ``Duracao_m``
   * - the location columns
     - ``PI_DICOFRE``, ``PI_NUTS3``, ``PI_Distrit``, ``PI_Conc``, ``PI_Freg``, ``PI_Local``
   * - ``cause_id``
     - ``Causa_Cod`` / ``Causa_Tipo`` / ``Causa_Desc``, matched on the whole triple
   * - the five area columns
     - ``AreaHaSIG``, ``AreaHaSGIF``, ``AreaHaPov``, ``AreaHaMato``, ``AreaHaAgri``

The archives are a snapshot and the ICNF revises records after publishing them, so
re-reading the lot costs nothing — it all arrives in the same response.

The **geometry is deliberately not re-read**. It would multiply the payload many
times over to rewrite perimeters that nothing here depends on; the archives'
geometry is what the import stored and it stays.

.. note::

   The cause classification is upserted exactly as the import does it, by reusing
   :func:`~src.apps.imports.wildfires.portugal_icnf.import_wildfires.upsert_causes`.
   A classification the ICNF has added since the archive was exported therefore
   arrives with the resync rather than needing a re-import.

One request per layer
---------------------

The server is GeoServer with ``ImplementsResultPaging``, ``CQL_FILTER`` and
``application/json``, and naming the properties drops the geometry from the
response. A whole year then fits in a single request — 2025 is 2 084 features in
350 KB — so the twelve layers that carry dates cost about a dozen requests:

.. code-block:: text

   ardida_2025: 2084 fetched, 2084 date(s) corrected, ...
   ardida_2018:  495 fetched,  495 date(s) corrected, ...
   DRY RUN: 2 layer(s), 2579 fetched, 2579 date(s) corrected, 2 request(s) made

Layers are walked **newest first**, and within a layer features come back sorted
by start date descending, so the most recent data is corrected first and a run
stopped early has done the most useful part.

Fires with no identifier are not asked for
------------------------------------------

901 of the 20 475 fires in the dated layers are polygons the ICNF could not match
to a record in its fire database. They carry no ``Cod_SGIF`` and no ``Cod_ANEPC``,
so nothing could be matched to them — and there is nothing to match. Asking the
server for the 42 such fires of 2018 returns three populated fields and no others:

.. code-block:: text

   Ano          42/42
   AreaHaSIG    42/42
   DH_Inicio     7/42     <- and all seven are already local midnight

That is exactly what the database holds for them. They are excluded at the server
with ``CQL_FILTER=Cod_SGIF IS NOT NULL`` rather than fetched and discarded, which
is why ``ardida_2018`` fetches 495 features rather than its full 537.

Being polite to the server
--------------------------

Nothing is known about the ICNF's rate limits, so:

- requests are spaced by ``--delay`` seconds (default 2) and never overlap, the
  wait being enforced inside the client so a caller cannot forget it;
- a failed request is retried with exponential backoff, honouring ``Retry-After``
  when the server sends one, capped at
  :data:`~src.apps.imports.wildfires.portugal_icnf.resync_wildfires.MAX_RETRY_AFTER`;
- a 400 or a 404 is **not** retried — it would fail identically however often it
  is sent;
- a 200 whose body is not JSON is treated as a refusal, because that is how
  GeoServer reports a rejected request (an XML ``ows:ExceptionReport``);
- a layer that still fails is reported and the run moves on, so one bad layer does
  not cost the other eleven. The process exits non-zero if any layer failed.

Restartable, and safe to re-run
-------------------------------

Each layer is committed on its own, so a run that dies half way leaves whole
layers done. Re-running is harmless: every write is conditional on the row
actually differing (``IS DISTINCT FROM`` over the whole row), so a fire already
carrying the WFS's values is not written again and its ``updated_at`` does not
move. The second run of a layer reports ``0 date(s) corrected``.

What the report tells you
-------------------------

Per layer, and then as a total:

``date(s) corrected`` / ``attribute row(s) changed``
    Rows actually written, not rows examined.

``moved to another day``
    Fires whose **date** the ICNF has changed, as opposed to a time the export had
    truncated. The WFS value is taken, and the count is logged as a warning
    because it means the archive and the source now disagree about when a fire
    happened. Compared as local dates — every stored start is local midnight, so
    comparing instants would report all of them.

``start(s) at local midnight``
    The WFS publishes a ``dateTime``, so the row is marked ``minute`` — but
    midnight is also what a record with no time of day looks like, and the two
    cannot be told apart. The count makes the claim visible rather than implied.

``not returned``
    Stored fires the WFS did not return: withdrawn or renumbered at the source.
    Left untouched, never deleted.

``unknown``
    Fires the WFS has and the database does not — added since the archive was
    exported. Reported, not inserted: this application corrects what the import
    stored, and a new fire has no geometry here to attach itself to. Re-import the
    layer to pick them up.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.portugal_icnf.resync_wildfires
   :members:
