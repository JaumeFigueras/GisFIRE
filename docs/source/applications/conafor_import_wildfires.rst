CONAFOR wildfire import (Mexico)
================================

Imports Mexico's national burnt-area cartography, CONAFOR's *Incendios Forestales*: 13
zipped shapefiles, one per year from 2010 to 2023, holding **45,914 published polygons**.
GisFIRE's first Latin American source.

See :doc:`../providers` for the dataset and :doc:`../providers/conafor_wildfire` for what
each column means. The zips are read without ever being unpacked, through GDAL's
``/vsizip/``.

Usage
-----

.. code-block:: console

   python3 -m src.apps.imports.wildfires.mexico_conafor.import_wildfires -d /path/to/mexico/

   python3 -m src.apps.imports.wildfires.mexico_conafor.import_wildfires \
       -s incendios_2023_shp.zip

   python3 -m src.apps.imports.wildfires.mexico_conafor.import_wildfires \
       -d /path/to/mexico/ --replace

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` and the
:doc:`time zone areas <time_zone_import_time_zones>` first, so that fires get a country and
a local start time. Mexico spans four zones, so unlike Greece the zone really is resolved
per fire — and it matters more here than almost anywhere, daylight saving having been
abolished outside the northern border strip in 2022.

The two CSV files that sit beside the archives in the published directory are **not**
imported and are not looked at: they are CONAFOR's tabular statistic, a different product
with no geometry. ``find_archives`` only ever picks up ``.zip`` and ``.shp``.

The attributes change every single year
----------------------------------------

This is the whole difficulty of the source, and it is handled in one place. Forty-six
published names appear across the fourteen archives and **no two consecutive years have
the same schema**:

``TIPVEG`` / ``TIPVEGE`` / ``TIP_VEG``
    One attribute, three spellings.
``CLAVEINC`` / ``CLAVE``
    The key, renamed in 2012 — and ``AREA_HA`` / ``TOTAL``, the burnt area,
    likewise.
``CAUSAESP`` / ``CAUSA_ESPE``
    Published in 2010 and 2012-2019, then gone.
The six burnt-area strata
    2010-2021, five of the six from 2020, none at all from 2022.
``CLAVEMUN``
    2018 onwards only. ``POLIGONO``, 2023 only.

Rather than write fourteen mappings, or branch on the year,
:func:`~src.apps.imports.wildfires.mexico_conafor.import_wildfires.normalise_staging_columns`
**normalises the staging table**: it renames every alias in
:data:`~src.providers.mexico_conafor.FIELD_ALIASES` onto one name, adds every attribute the
file did not have as an empty column, and converts every one that landed in a type the
mapping cannot read. One mapping then covers all fourteen years, and a layer that publishes
less simply leaves more of the row ``NULL``.

The aliases live in the *provider* module rather than in the importer, so that anything
else reading these archives folds them the same way.

Dates are parsed in Python, on purpose
---------------------------------------

``FECHAINIC`` and ``FECHALIQ`` arrive in four written formats — ``YYYY-MM-DD``,
``YYYY/MM/DD``, ``DD/MM/YYYY`` and ``DD-MM-YYYY`` — and the 2022 layer uses **all four
within one column**. They also land as a ``date`` in six layers and as a string in seven.

They are not parsed in SQL, and the reason is specific:

.. code-block:: text

   to_date('22/20/2021', 'DD/MM/YYYY')  ->  2022-08-22

PostgreSQL's ``to_date`` is lenient. It does not refuse a twentieth month, it rolls it over
and returns a date that looks perfectly reasonable — and that exact string is in the
published 2021 archive. So
:func:`~src.apps.imports.wildfires.mexico_conafor.import_wildfires.normalise_staging_dates`
reads the **distinct** published strings, a few hundred per layer whatever the row count,
parses each with :func:`~src.providers.mexico_conafor.parse_date`, and writes the results
back into two real ``date`` columns.

The parser is then one tested function shared by the model tests and the import, rather
than a regular expression in SQL that could drift away from it.
:func:`~src.apps.imports.wildfires.mexico_conafor.import_wildfires.normalise_staging_vegetation`
does the same for the INEGI code in ``TIPVEG``, for the same reason: telling ``BPQ`` from
the *Pino* of ``'Bosque de Encino - Pino'`` needs the fixed set of real codes, and that
lives in Python beside the model.

Three published values in the whole archive cannot be read, and all three are end dates on
rows whose start reads fine. They become ``NULL``. A row with no readable *start* is dated
to the 1st of January of its year and marked ``year`` — no row of the archive as published
needs that, and the next release might.

No layer publishes a time of day, so every stored instant is local midnight and every
imported row is marked ``day``.

The year comes from the file name, and is checked against the data
-------------------------------------------------------------------

Only three layers publish ``ANO``, so the year is taken from the archive:
``incendios_2021`` is 2021. That is a file name, which is a weaker thing to trust than
data — so
:func:`~src.apps.imports.wildfires.mexico_conafor.import_wildfires.check_layer_year`
verifies it. Every published ``CLAVEINC`` is ``YY-EE-NNNN``, and if the majority of a
layer's keys disagree with the year its name claims, the run **stops before anything is
written**.

A mis-named or mis-downloaded archive is caught at import rather than in a query three
months later — and it matters here more than in the sibling imports, because the year is
the unit an import replaces, so a wrong one would replace another year's fires.

.. warning::

   **Five published features are exact duplicates of five others.** All are in the 2021
   archive: identical attributes and byte-identical geometry, except that the second copy
   of the four Guerrero rows (``21-12-0195`` … ``21-12-0198``) has both its date fields
   blanked.

   The mapping de-duplicates on ``CLAVEINC``, keeping the copy that has a start date. This
   is not a tidiness measure — ``conafor_wildfire.fire_code`` is ``UNIQUE``, so **without
   it the 2021 archive fails to import at all**.

   Being able to have that constraint is worth the de-duplication: this is the only
   perimeter provider in GisFIRE whose published key identifies a fire, and so the only one
   where a row could be upserted rather than a whole layer replaced.

.. note::

   A feature with **no geometry** is imported, with a ``NULL`` perimeter. Nine of the 2012
   layer's 224 features carry attributes and an empty shape, and a fire with a key, a date
   and an area is still a fire — which is what the model's nullable geometry is for. It
   simply resolves no zone and no country. The same goes for a polygon that ``ST_MakeValid``
   reduces to nothing.

   What *is* dropped: a feature whose key is not of the published form, one that publishes
   no area, and the duplicate copies above. The run reports the difference between features
   staged and fires imported.

.. note::

   ``-lco PRECISION=NO`` is passed to ``ogr2ogr``, as in the Andalusian import and for the
   same reason. Every numeric column of these shapefiles declares ``Real (24.15)``, and
   GDAL's PostgreSQL driver renders a declared width as ``NUMERIC(width, scale)`` — a
   ``numeric(24,15)`` cannot hold a five-digit hectare figure, and the 2021 layer has fires
   of 19,102 ha, so the ``COPY`` fails outright without it.

   No ``-oo ENCODING`` is passed, unlike the ICNF import: these archives carry a ``.cpg``
   and GDAL reads it. That does not make the text clean — see the mojibake warning in
   :doc:`../providers` — but the corruption is in the published file and no encoding
   recovers it.

One transaction per year
------------------------

A layer is loaded, deleted and re-inserted in one transaction, so an interrupted run leaves
the years it finished and the year it was in the middle of exactly as it found them.

A layer already in the database is **skipped**, and ``--replace`` deletes what it loaded
before importing it again. Unlike the ICNF import this is a convenience rather than a
necessity — the key is unique, so an upsert would be possible — but replacing a year is the
simpler operation, and it is the only one that removes a fire CONAFOR has withdrawn from a
revised publication.

The cause catalogue is not replaced with it. Classifications are inserted
``ON CONFLICT DO NOTHING``, in two statements rather than one, because uniqueness on
``conafor_fire_cause`` is enforced by two partial indexes: three fires in five have no
specific cause, and in SQL two ``NULL``\ s are not equal. Doing nothing on conflict also
means a reconciliation corrected by hand in the database survives the next import.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.mexico_conafor.import_wildfires
   :members:
   :show-inheritance:
