Greek Fire Service wildfire import
==================================

Imports the Greek national fire statistic, *Δασικές Πυρκαγιές*, from the Excel workbooks
the Hellenic Fire Service publishes — **260,194 fire records over 2000-2025**, in fifteen
files, one per year plus one holding 2000 to 2012 in thirteen sheets.

The second importer in GisFIRE that reads a spreadsheet rather than a shapefile, after
:doc:`egif_import_wildfires`, and like that one it needs no ``ogr2ogr``: the source is a
workbook and the only geometry work is a point PostGIS builds from two numbers. See
:doc:`../providers` for the dataset and :doc:`../providers/greece_ffa_wildfire` for what
each column means.

Usage
-----

Over a whole directory, or over named files, or over selected years:

.. code-block:: console

   python3 -m src.apps.imports.wildfires.greece_ffa.import_wildfires -d /path/to/grecia/

   python3 -m src.apps.imports.wildfires.greece_ffa.import_wildfires \
       -s Dasikes_Pyrkagies_2024.xlsx agrotodasikes_pyrkaies_2025.xlsx

   python3 -m src.apps.imports.wildfires.greece_ffa.import_wildfires \
       -s Dasikes_Pyrkagies_2000-2012.xlsx --year 2010 2011 2012

``-d`` and ``-s`` are mutually exclusive and one is required. ``--year`` restricts which
sheets of a multi-year workbook are read, which is what makes re-importing one year of
the thirteen-year file a second-long operation rather than a minute-long one.

Settings are read from the environment (``.env``, see :doc:`../setup/configuration`) and
each can be overridden with ``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``
and ``--db-password``.

Import the :doc:`OCHA boundaries <ocha_import_admin_boundaries>` first, so that the fires
that have a point get a country. The import runs without them and says so; the fires are
worth having either way, and nothing else can be filled in afterwards.

.. note::

   The time zone areas are **not** needed. Greece is one zone for the whole country and
   the whole period, so this importer uses
   :data:`~src.providers.greece_ffa.DEFAULT_TIME_ZONE` outright rather than resolving a
   zone from each fire's location — which it could not do anyway, three quarters of the
   archive having no location. :doc:`inab_import_wildfires` is in the same position for
   the same reason; every other wildfire importer resolves the zone per fire.

A year is the unit, not a file
------------------------------

Every sheet is one year, and a year is **replaced wholesale**: its fires are deleted and
re-inserted in one transaction, so re-importing a revised publication supersedes rather
than doubles.

That is forced by the dataset rather than chosen. This source publishes **nothing that
identifies a fire**: ``Α/Α ΕΓΓΡΑΦΗΣ`` and ``Α/Α ENGAGE`` begin in 2020, so 201,948 of the
260,194 rows have no identifier of any kind, and where the record number does exist 512
of its values are used by more than one row. There is no key to upsert on, so the
:doc:`EGIF import <egif_import_wildfires>`'s trick of writing only the columns one format
publishes has nothing to hang off, and replace-the-year is the only idempotent operation
available.

Importing the 2000-2012 workbook therefore replaces thirteen years and a single-year file
replaces one. Nothing else is touched.

One transaction per year
^^^^^^^^^^^^^^^^^^^^^^^^

A sheet is deleted, read to its end and committed, so an interrupted run keeps the years
it had finished and leaves the year it was in the middle of exactly as it found it.

A *row* that cannot be stored is a different matter: it is logged with its worksheet row
number and the reason, counted, and skipped, and the rest of the year is still committed.
What makes a row unstorable is deliberately short — **no start date**, since
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is ``NOT NULL`` and nothing can
stand in for it. Every row of the twenty-six published sheets passes.

The row number is in the message because for 201,948 rows it is the only way to say which
row was refused.

Reading the workbooks
---------------------

:mod:`~src.apps.imports.wildfires.greece_ffa.readers` does this, and it is most of the
work. The sheets have 16, 17, 31, 32, 36, 38 or 39 columns depending on the year, in six
arrangements, under a header that is two rows deep — four in the 2025 file. So:

Nothing is read by position
    Every field is located by matching its header through
    :func:`~src.providers.greece_ffa.normalise_column`, which folds away the line-break
    hyphens (``ΒΥΤΙΟ- ΦΟΡΑ`` and ``ΒΥΤΙΟΦΟΡΑ`` are one column), the inconsistent accents,
    and the **Latin** ``A`` the 2025 file writes ``A/A ENGAGE`` with where every other
    year uses the Greek ``Α``. The two render identically and compare unequal.

The header is found, not assumed
    The first row naming at least eight known columns — a property of the row, which is
    what lets one rule serve a header on row 1 (2014), row 2 (twenty-four sheets) and row
    4 (2025).

The year is the sheet name, or the cell above the header
    Four digits for every file but one. ``agrotodasikes_pyrkaies_2025.xlsx`` calls its
    sheet ``Sheet0`` and prints ``Για το ΕΤΟΣ:`` ``2025`` above the header. A sheet whose
    year cannot be established is **refused**, because the year is what gets deleted and
    guessing it wrong would destroy a different year.

An unknown column is reported
    and the year is still imported. A new column is a reason to look, not a reason to
    refuse data — but a column that quietly vanished would otherwise import as nulls.

.. note::

   The ``engage``/``engagexy`` helper sheets in the 2022-2024 files are **not** read. The
   coordinate columns there are ``VLOOKUP`` formulas into them, and ``openpyxl``'s
   ``data_only=True`` returns the results Excel cached — so the helper sheets add nothing,
   and reading them would import every coordinate a second time as a fire of its own.

What the import converts
------------------------

Στρέμματα to hectares
    The eight land-cover columns are multiplied by
    :data:`~src.providers.greece_ffa.STREMMA_HA`. A στρέμμα is 1,000 m² by definition, so
    the conversion is exact and the published figure is recoverable by multiplying by ten.
    Every other provider in GisFIRE stores hectares and a report over two countries cannot
    carry a unit per country.

A date and a time to an instant
    Both are published as naive local wall-clock, in two columns, and in two forms — a
    real Excel value for most years, ``dd/mm/yyyy`` and ``HH:MM`` text for others. The
    conversion is done by PostgreSQL with ``AT TIME ZONE``, which resolves daylight saving
    from the date itself.

    27,183 rows publish no usable extinction: 26,597 publish neither an end date nor an
    end time, and 586 publish a time with no date, which cannot name an instant. Those get
    ``NULL``. The 641 that publish a date with no time are read as local midnight, on the
    rule the project follows for any provider publishing a bare date.

A coordinate to a point, sometimes
    ``X-ENGAGE``/``Y-ENGAGE`` are WGS 84 degrees, so the point is ``ST_MakePoint`` and
    **no reprojection**, which only this and :doc:`inab_import_wildfires` can say — every
    other source publishes on some other grid. A pair becomes a point
    only when :func:`~src.providers.greece_ffa.is_located` accepts it: inside Greece's
    bounds, which rejects the ``0``/``0`` that 3,755 rows carry and catches a transposed
    pair. Null island is in the Gulf of Guinea.

The country, per point
    ``admin_boundary_id`` comes from a point-in-polygon test against the OCHA level 0
    boundaries. The 205,703 rows with no point get ``NULL``: there is nothing to test, and
    no Greek administrative boundaries are imported that the published prefecture and
    municipality names could be matched against instead.

.. warning::

   ``Α/Α ENGAGE`` is a ``bigint`` because it has to be. Its values run from 92,687 to
   **911,023,000,013**, and two rows of the 2023 sheet are past what a 32-bit integer
   holds — ``2310230025`` and ``911023000013``, against a median around a million. They
   look like a date and a sequence run together by whatever wrote them, and they are what
   the service published, so they are stored as published. An ``integer`` column failed
   the whole of 2023 on them, which is how they were found.

False alarms are imported
-------------------------

1,255 of the 9,043 rows of 2025 are ``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ`` — a call-out that found no fire.
They are stored, with the category on the row, because a record that says "this was not a
fire" can be filtered afterwards and a discarded one cannot be recovered. The run reports
how many it wrote.

Anything counting or measuring fires has to exclude them, and with an ``IS DISTINCT FROM``
rather than a ``<>``: the column is ``NULL`` for every year before 2025, where ``<>``
evaluates to ``NULL`` and would silently drop the other twenty-five. See
:doc:`../providers/greece_ffa_wildfire`.

Progress
--------

Each sheet gets a bar on a terminal and periodic log lines when redirected. The row count
is known from the worksheet dimensions before reading starts, so the bars carry a
percentage and an estimate:

.. code-block:: text

   2020 (2020): 11,799/11,799 (100%) in 4s

Followed by what the year did, and a summary of the run:

.. code-block:: text

   INFO Dasikes_Pyrkagies_2020.xlsx: 2020: 11799 row(s) read, 11799 written
        (11372 with a point, 0 false alarm(s)), 0 skipped, 0 with problems
   INFO Imported 260194 fire(s) over 26 year(s) from 14 workbook(s) in 49s:
        54491 with a point, 1255 false alarm(s), 0 skipped

The whole archive imports in about fifty seconds.

API reference
-------------

.. automodule:: src.apps.imports.wildfires.greece_ffa.import_wildfires
   :members:
   :show-inheritance:

.. automodule:: src.apps.imports.wildfires.greece_ffa.readers
   :members:
   :show-inheritance:
