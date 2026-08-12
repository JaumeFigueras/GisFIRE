INAB fire data download (Guatemala)
====================================

Fetches the fire layers of Guatemala's *Sistema Integral de Información para la Gestión
del Fuego* — the data behind INAB's *Monitoreo de Incendios* viewer — to GeoJSON files on
disk.

The first application in the project that only **downloads**: it writes files, touches no
database, and needs no ``ogr2ogr``. Loading what it fetches is a separate job, and for the
fire reports it is :doc:`inab_import_wildfires`.

Usage
-----

.. code-block:: console

   # what is there, and how much of it, per year — run this first
   python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires years

   # one year
   python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires year \
       --year 2025 --output-dir ~/data/guatemala

   # the whole dataset in one file, undated records included
   python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires all \
       --output-dir ~/data/guatemala

   # the other layers
   python3 -m src.apps.download.wildfires.guatemala_inab.download_wildfires --list-datasets

``--delay`` sets the seconds between requests and is the setting to raise if anything
about a run looks unwelcome. ``--iso-dates`` rewrites the date fields from epoch
milliseconds to ISO 8601.

There is no WFS
---------------

The platform is ArcGIS Enterprise 11.3 and **none of the fire services has the OGC WFS
interface enabled** — one unrelated cloud-forest service on the whole server does. What
the fire layers do have is the ArcGIS REST API, readable without a token, which is what
this speaks.

If INAB ever enables the OGC extension, ``ogr2ogr`` against the WFS would replace this
program entirely. Until then, a paged REST client is what a complete copy takes.

What is actually published
--------------------------

Five fire datasets, measured on 2026-08-07, and they are not what their names suggest:

=======================  =======  ==========  ===================================
Key                      Records  Geometry    Span
=======================  =======  ==========  ===================================
``fire-reports``           4,615  point       2023-2026, dated to the minute
``fire-report-updates``    5,812  point       2023-2026, dated to the minute
``burn-scars``             1,217  polygon     **2025 only**
``burn-scars-table``       1,337  none        **2025 only**
``burn-scars-2024``        1,405  polygon     no year field at all
=======================  =======  ==========  ===================================

.. warning::

   **The burn-scar layers are not a historical archive.** ``burn-scars`` carries a
   ``fecha_ano`` and every one of its 1,217 rows says 2025; ``burn-scars-2024`` has no
   date field of any kind. Anything wanting a multi-year Guatemalan burnt-area series
   will not find one here — which is exactly what the ``years`` mode is for finding out
   before a download rather than after.

``fire-reports`` (``datos_generales``) is the interesting one and the default: one row per
fire reported to INAB, with who called it in and how, the department, municipality,
*aldea* and *finca*, the coordinates as given, the altitude, whether it is inside a
protected area, and ``fecha_hora_incendio`` — **the date and time the report came in**,
which the burn scars lack entirely.

``fire-report-updates`` (``informes``) is the follow-up: when the first ground and air
crews arrived, when the fire was controlled and when it was extinguished. More rows than
there are fires, one fire being reportable several times. A fire's start comes from the
first layer and its end from this one.

Being a polite client
---------------------

The server's limits are undocumented, so the program assumes they are tight.

**No bulk download.** The two monitoring layers advertise ``maxRecordCount`` 50,000 — the
whole dataset in one request — and this deliberately does not ask for it. ``--page-size``
defaults to a per-dataset value, and ``--page-size`` above the layer's own limit is
*refused* rather than silently clamped by the server, which would leave the run's paging
arithmetic disagreeing with what it received. The ``Extract`` capability some of these
services expose, which hands over a whole file at once, is never touched.

**A delay between requests**, enforced between the *start* of one and the next, so a slow
response does not shorten the gap. One second by default.

**Retries with exponential backoff**, honouring ``Retry-After`` up to two minutes. A 400
or a 404 is not retried: the server will refuse it just as fast the second time.

**A ``User-Agent`` that says who is calling**, so an administrator reading a log can tell
this apart from a scraper.

The fire reports come down in about ten requests and ten seconds; the burn scars take
twenty-seven and three minutes, being **312 MB** of polygon — they are traced around
raster cells, so a scar of half a hectare carries thousands of vertices.

.. warning::

   **This server truncates an over-large response instead of refusing it.** Asking for
   500 burn-scar polygons produces a body of well over 100 MB that arrives cut off in the
   middle of a JSON string — not an error, not a 500, just a body that will not parse. It
   was measured doing exactly that, 32 MB in.

   That is why the page size is **per dataset**: 500 for the point layers, **50** for the
   polygon ones, whose features run to about 260 kB each. A body that fails to parse is
   reported as *"the response was cut off, retry with a smaller --page-size"* rather than
   as corruption, and is not retried — the same request would be cut off in the same
   place.

How a run knows it got everything
----------------------------------

Two mechanisms, because neither is sufficient alone.

ArcGIS reports "there is more" in a flag whose **position moves**: absent from the GeoJSON
of a feature layer, nested under ``properties`` in the GeoJSON of a table. Trusting it
would work on four of these five datasets and silently truncate the fifth. So paging ends
on a **short page**, which is true of every ArcGIS version and both response shapes.

But a short page is also what a truncated response looks like. So the expected count is
fetched **first**, with ``returnCountOnly``, and compared against what arrived. A mismatch
raises and **no file is written** — a quietly incomplete GeoJSON being the worst outcome
available here.

Ordering is explicit (``orderByFields=objectid ASC``): paging without a sort is undefined,
and two pages of an unordered result can overlap or skip.

.. note::

   An existing file is **skipped** rather than refetched, so a run interrupted half way
   through resumes by being run again. ``--overwrite`` forces a refetch, which is what to
   use when INAB republishes.

Provenance, which the source does not supply
---------------------------------------------

.. warning::

   These layers are hosted **views**, published with no metadata, no lineage and no
   licence statement. INAB can republish or reindex them, and ``objectid`` is a view
   artefact rather than a stable identifier — it is not safe to treat as a key across two
   downloads.

Every run therefore writes a ``.meta.json`` beside its data recording the exact URL, the
query, the server's own field list, the expected and written record counts, and the
download timestamp. That sidecar is the provenance the source does not give, and it is
what makes a figure in a thesis reproducible.

Ask INAB's SIG unit for a citation and use statement in writing before publishing anything
derived from these layers.

.. note::

   ArcGIS serialises a date as **milliseconds since 1970-01-01 UTC**, in GeoJSON as in its
   own format. That is what the server said, so by default it is what gets written.

   ``--iso-dates`` rewrites those fields to ISO 8601 UTC on the way out. The fields to
   convert are read from the layer's own metadata rather than named in the code, so a
   field INAB adds is handled without an edit, and a value that is not a number is left
   exactly as it is.

API reference
-------------

.. automodule:: src.apps.download.wildfires.guatemala_inab.download_wildfires
   :members:
   :show-inheritance:
