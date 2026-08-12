#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import CONAF's Chilean seasonal fire reports.

Reads the published *incendios forestales por temporada* shapefiles — 23 archives,
95,868 points, the fifteen seasons 2010-2011 to 2024-2025 — and writes four tables:
:class:`~src.data_model.ignition.Ignition` and
:class:`~src.providers.chile_conaf.ignition.ConafIgnition` for the point,
:class:`~src.data_model.wildfire.Wildfire` and
:class:`~src.providers.chile_conaf.wildfire.ConafWildfire` for the report, plus
whatever :class:`~src.providers.chile_conaf.fire_cause.ConafFireCause` rows the
season's causes need.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires \\
         -d /data/incendis-forestals/america/xile/punts
   $ python3 -m src.apps.imports.wildfires.chile_conaf.import_wildfires \\
         -s if_temporada_2022_2023.rar -y 2022 --dry-run

Import the OCHA boundaries and the time zone areas first, so fires get a country and
a local start time. Re-importing replaces the seasons it reads.

One transaction per season, and per territory
-----------------------------------------------

Each archive is staged, its seasons found from the data's own ``TEMPORADA``, and
each season deleted and rewritten inside its own transaction — so a season that
fails rolls back alone and a run over all 23 archives never holds one lock for its
whole length.

.. important::

   The unit that gets replaced is a season **of one territory**, not a season. CONAF
   publishes the mainland and Easter Island as separate archives for the same
   ``TEMPORADA`` — ``if_temporada_2024_2025`` and
   ``if_temporada_islapascua_2024_2025`` are both 2024-2025 — so a delete scoped to
   the season alone destroys whichever half was imported first. Importing all 23
   archives in name order with a season-only delete loses 6,496 fires: the 234 Rapa
   Nui ones the mainland archives overwrite, and the 6,262 mainland ones the last
   archive in the directory overwrites.

   :func:`grid_filter` is what scopes it. The grid is the territory, which is what
   makes that the right test and not merely a convenient one: CONAF splits the
   archives by territory precisely because the two are on different UTM zones.

Deleting a season refuses if an *incendio de magnitud* perimeter points at any of
its fires. See :data:`LINKED_SQL`: the link lives on
:class:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire` and
points this way, so replacing a season underneath it would leave a dangling
reference the foreign key would refuse anyway — asked up front so the run says what
the problem is instead of dying on a constraint.

The published attributes are named 34 different ways
------------------------------------------------------

Twenty-three layers, and almost no two agree on their column names. ``NOM_INCEN``
is also ``NOMBRE`` and ``Nombre_inc``; ``NUMERO_REG`` is also ``NUMERO``,
``NUMERO_RE`` and ``N_MERO_RE``; ``AMBITO`` is ``N_MBITO`` in 2024-2025;
``TOTAL_OTRA`` is ``TOTAL_O`` and ``SUBTOTAL_O``; the start and end are
``INICIO_IN``/``EXTINCION`` up to 2020-2021 and ``FH_INICIO``/``FH_EXTINCI`` after.
Case varies freely, and 2024-2025 mangles its accented names into ``AGR_COLA`` and
``N_MBITO``.

:data:`COLUMN_ALIASES` is the whole map, and :func:`normalise_staging_columns`
renames the staged table's columns to one canonical set before any SQL reads them,
so the transform below can be written once.

Dates and causes are resolved in Python, not in SQL
-----------------------------------------------------

Two of the four published date formats need a Spanish month table and one is
day-month-year, and the cause needs the two-taxonomy reconciliation in
:mod:`src.providers.chile_conaf.fire_cause`. Neither is something to write twice.

So both are resolved by the tested Python functions and written back into the
staging table — :func:`resolve_dates` fills ``start_at``, ``end_at`` and
``start_precision``, :func:`upsert_causes` fills ``cause_id`` — and the transform
reads columns rather than parsing strings. It is the pattern
:mod:`src.apps.imports.wildfires.mexico_conafor.import_wildfires` uses for its
vegetation codes, applied to the two attributes here that are worth it.

The simpler folds stay in SQL, and each names the Python function it has to agree
with: see :data:`REPORTER_SQL`, :data:`REGION_CODE_SQL` and :data:`UTM_ZONE_SQL`.

Half the archive has no start date
------------------------------------

Eight of the fifteen mainland seasons publish none at all. Those fires are stored
with ``start_date_time`` at the first instant of their season and
``date_time_precision`` = :data:`~src.providers.chile_conaf.PRECISION_SEASON`, and
the summary says how many. Nothing is invented and nothing is dropped: a fire with
no date is still a fire, and the precision column is what stops the placeholder
being mistaken for an observation.

.. warning::

   The three corrupt records of ``if_temporada_2010_2011`` are dropped, not stored.
   Their text fields are binary — see
   :func:`~src.providers.chile_conaf.is_corrupt` — and one of them carries a
   fragment of another row's bytes in ``CAUSA_GENE``, which would otherwise become a
   permanent entry in the cause classification. The count is reported.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import typing
import zlib

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.apps.imports import common
from src.apps.imports.wildfires.chile_conaf import archives
from src.providers import chile_conaf
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.fire_cause import resolve_cause

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"

#: The season an archive's file name carries: two consecutive years. See
#: :func:`archive_season`.
_ARCHIVE_SEASON = re.compile(r"(\d{4})[_-](\d{4})")

#: Where the published rows are staged before being mapped onto the model.
DEFAULT_STAGING_TABLE = "conaf_reports"

#: First half of the advisory lock key :func:`exclusive_run` takes, so that this
#: import's locks cannot collide with another application's. ``"CONF"``, which is as
#: close to CONAF as four bytes get; :mod:`src.apps.imports.wildfires.canada_nfdb`
#: uses ``"NFDB"`` the same way.
STAGING_LOCK_NAMESPACE = 0x434F4E46

#: Name of the serial key ``ogr2ogr`` puts on the staging table.
#:
#: Not ``fid``, the default, because several published layers carry an ``id``
#: attribute of their own and one carries ``gid``; giving the key a name of its own
#: keeps every published column loading as an ordinary column.
STAGING_FID_COLUMN = "staging_fid"

#: ``PRECISION=NO``, for the reason the Andalusian import gives: several layers
#: declare their numeric fields as ``Real (24.15)``, and the PostgreSQL driver would
#: turn that into ``numeric(24,15)``, which cannot hold the seven-digit northing the
#: field actually contains.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]

#: Every published spelling of each attribute this import reads, keyed by the
#: canonical name the transform uses.
#:
#: Twenty-three layers over fifteen seasons, and the naming drifts in four different
#: ways: case (``temporada`` / ``TEMPORADA``), abbreviation (``NUMERO_REG`` /
#: ``NUMERO_RE``), renaming (``TOTAL_PLAN`` / ``SUBTOTAL_P``) and accent-mangling
#: (``AGRICOLA`` / ``AGR_COLA``, ``AMBITO`` / ``N_MBITO``).
#:
#: The spellings are compared **lower-cased**, which is what ``ogr2ogr`` gives the
#: staged columns anyway, so only the genuinely different names are listed. Order
#: matters: the first spelling present in the staged table wins, so the canonical
#: name comes first and the odder variants after it.
#:
#: ``pino_total`` is in the list for ``pino18_mas`` and that is a judgement worth
#: stating: ``if_isla_pascua_2013_2014`` publishes ``Pino_total`` where every other
#: layer publishes ``PINO18_MAS``, on a layer that also publishes ``Pino_0010`` and
#: ``Pino_11_17``, so the third band is what it must be. 39 fires.
COLUMN_ALIASES = {
    "temporada": ("temporada",),
    "numero_reg": ("numero_reg", "numero_re", "n_mero_re", "numero"),
    "nom_incen": ("nom_incen", "nombre", "nombre_inc"),
    "ambito": ("ambito", "n_mbito"),
    "region": ("region",),
    "provincia": ("provincia",),
    "comuna": ("comuna",),
    "codreg": ("codreg",),
    "codprov": ("codprov",),
    "codcom": ("codcom",),
    "utm_e": ("utm_e", "utm_este"),
    "utm_n": ("utm_n", "utm_norte"),
    "huso": ("huso", "huso_op_"),
    "inicio_c": ("inicio_c", "inicio_cer"),
    "combus_i": ("combus_i", "combustibl"),
    "causa_gene": ("causa_gene",),
    "causa_espe": ("causa_espe",),
    "fh_inicio": ("fh_inicio", "inicio_in"),
    "fh_extinci": ("fh_extinci", "extincion"),
    "pino_00_10": ("pino_00_10", "pino_0_a_1", "pino_0010", "pino_0_10"),
    "pino_11_17": ("pino_11_17", "pino_11_a"),
    "pino18_mas": ("pino18_mas", "pino_18_o", "pino_total"),
    "eucalipto": ("eucalipto",),
    "otras_plan": ("otras_plan",),
    "total_plan": ("total_plan", "subtotal_p"),
    "arbolado": ("arbolado",),
    "matorral": ("matorral",),
    "pastizal": ("pastizal",),
    "total_veg": ("total_veg", "subtotal_v"),
    "agricola": ("agricola", "agr_cola"),
    "desechos": ("desechos",),
    "total_otra": ("total_otra", "total_o", "subtotal_o"),
    "superficie": ("superficie", "sup_t_a"),
}

#: The attributes every one of the 23 published layers carries, under one spelling
#: or another.
#:
#: A layer missing any of these is not a CONAF seasonal report layer, and the import
#: stops rather than writing a season of nulls. Everything else in
#: :data:`COLUMN_ALIASES` is genuinely optional — see :func:`normalise_staging_columns`
#: — because CONAF really does publish layers without it:
#:
#: * ``if_isla_pascua_2013_2014`` publishes no ``REGION``, ``PROVINCIA``, ``COMUNA``,
#:   ``HUSO`` or start and end date. It has 39 fires, a season and a cause.
#: * ``if_temporada_2024_2025`` and ``if_temporada_islapascua_2024_2025`` publish no
#:   ``CODPROV`` or ``CODCOM``, only the región code.
#:
#: The seven below are the layer's signature: they are what every published season
#: has in common, and a shapefile carrying all seven is a CONAF report layer whatever
#: else it is missing.
REQUIRED_COLUMNS = ("temporada", "causa_gene", "causa_espe", "superficie",
                    "arbolado", "matorral", "pastizal")

#: The type each canonical column is read as, after the aliases are resolved.
#:
#: Everything textual stays ``text``, the two coordinates included: 2023-2024
#: publishes ``UTM_E`` as ``'317709 E'``, which is not a number until the suffix is
#: off it, and casting the column would lose the row rather than the suffix.
STAGING_COLUMNS = {
    "temporada": "text",
    "numero_reg": "text",
    "nom_incen": "text",
    "ambito": "text",
    "region": "text",
    "provincia": "text",
    "comuna": "text",
    "codreg": "text",
    "codprov": "text",
    "codcom": "text",
    "utm_e": "text",
    "utm_n": "text",
    "huso": "text",
    "inicio_c": "text",
    "combus_i": "text",
    "causa_gene": "text",
    "causa_espe": "text",
    "fh_inicio": "text",
    "fh_extinci": "text",
    "pino_00_10": "double precision",
    "pino_11_17": "double precision",
    "pino18_mas": "double precision",
    "eucalipto": "double precision",
    "otras_plan": "double precision",
    "total_plan": "double precision",
    "arbolado": "double precision",
    "matorral": "double precision",
    "pastizal": "double precision",
    "total_veg": "double precision",
    "agricola": "double precision",
    "desechos": "double precision",
    "total_otra": "double precision",
    "superficie": "double precision",
}

#: Columns the import adds to the staging table and fills itself.
#:
#: ``season_start_year`` because ``TEMPORADA`` is text and seven rows publish
#: something that is not a season; the three date columns because the four published
#: formats are read in Python; ``cause_id`` because the cause needs the two-taxonomy
#: reconciliation; ``corrupt`` because three rows have to be excluded from
#: everything, including the cause catalogue, and marking them once is cheaper and
#: clearer than repeating the test.
RESOLVED_COLUMNS = {
    "season_start_year": "integer",
    "start_at": "timestamp without time zone",
    "end_at": "timestamp without time zone",
    "start_precision": "text",
    "cause_id": "integer",
    "corrupt": "boolean",
}

#: The loaded types each declared type will accept without a conversion.
COMPATIBLE_TYPES = {
    "integer": {"integer", "bigint", "smallint"},
    "double precision": {"double precision", "real", "numeric", "integer", "bigint",
                         "smallint"},
    "text": {"text", "character varying", "character"},
}

#: The characters trimmed off every published text attribute before it is read.
TRIMMED_CHARS = r"E' \t\r\n'"

#: How the published ``AMBITO`` reads as a reporter, as SQL.
#:
#: Four published spellings — ``Conaf``, ``CONAF``, ``Empresa``, ``EMPRESA`` — onto
#: the two constants in :data:`~src.providers.chile_conaf.REPORTERS`, which are
#: written in exactly this capitalisation. Anything else, blanks included, is
#: ``NULL``: the column is constrained to the two, and a third spelling should stop
#: the import rather than be folded into one of them by accident.
REPORTER_SQL = """
    CASE lower(NULLIF(btrim(staging.ambito, {trimmed}), ''))
         WHEN 'conaf' THEN 'Conaf'
         WHEN 'empresa' THEN 'Empresa'
         ELSE NULL
    END"""

#: How an administrative code is zero-padded, as SQL.
#:
#: This has to agree with :func:`~src.providers.chile_conaf.admin_code`: take the
#: digits before any decimal point, and left-pad to the code's width. ``'6.00000'``
#: becomes ``'06'``, ``'5801'`` becomes ``'05801'``, and a value that is not digits
#: becomes ``NULL``.
#:
#: A code already longer than its width is returned unpadded, which ``lpad`` does by
#: itself — it truncates from the *left* when the string is too long, so the
#: ``length()`` guard is what stops ``lpad`` silently losing the leading digits of a
#: malformed code.
ADMIN_CODE_SQL = """
    CASE WHEN btrim(coalesce(staging.{column}, ''), {trimmed}) ~ '^[0-9]+(\\.0+)?$'
         THEN CASE WHEN length(split_part(btrim(staging.{column}, {trimmed}), '.', 1)) > {width}
                   THEN split_part(btrim(staging.{column}, {trimmed}), '.', 1)
                   ELSE lpad(split_part(btrim(staging.{column}, {trimmed}), '.', 1),
                             {width}, '0')
              END
         ELSE NULL
    END"""

#: How the published ``UTM_E`` / ``UTM_N`` read as numbers, as SQL.
#:
#: Has to agree with :func:`~src.providers.chile_conaf.published_utm`: strip the
#: ``' E'`` / ``' S'`` suffix 2023-2024 writes, and read a zero as *unpublished*
#: rather than as a coordinate 500 km west of the central meridian.
UTM_COORDINATE_SQL = """
    NULLIF(CASE WHEN btrim(coalesce(staging.{column}, ''), {trimmed} || 'ENSWensw')
                     ~ '^-?[0-9]+(\\.[0-9]+)?$'
                THEN btrim(staging.{column}, {trimmed} || 'ENSWensw')::double precision
                ELSE NULL
           END, 0)"""

#: How the published ``HUSO`` reads as a zone number, as SQL. ``'19K'``, ``'19'``
#: and ``'12.0'`` all give the number; anything else gives ``NULL``.
UTM_ZONE_SQL = """
    NULLIF(substring(btrim(coalesce(staging.huso, ''), {trimmed})
                     from '^([0-9]{{1,2}})'), '')::integer"""

#: How the published ``HUSO`` reads as an MGRS latitude band, as SQL. Only the
#: seasons that write ``'19K'`` have one.
UTM_BAND_SQL = """
    substring(upper(btrim(coalesce(staging.huso, ''), {trimmed}))
              from '^[0-9]{{1,2}}(?:\\.0+)?([A-Z])$')"""

#: The distinct published start and end strings of the staged archive, for
#: :func:`resolve_dates`.
#:
#: Distinct rather than every row because 95,868 rows carry far fewer distinct date
#: strings — a season's 6,000 fires share a few thousand — and the parse is a Python
#: round trip per distinct value rather than per fire.
#:
#: The two column names are parameters because the perimeter import shares this
#: function and calls them ``FECHA_INI`` and ``FECHA_TER``.
DATE_STRINGS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce({start_column}, ''), {trimmed}), '') AS start_text,
                NULLIF(btrim(coalesce({end_column}, ''), {trimmed}), '') AS end_text
FROM {staging_table}
"""

#: The distinct seasons the staged archive publishes, for :func:`resolve_seasons`.
SEASON_STRINGS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce(temporada, ''), {trimmed}), '') AS season_text
FROM {staging_table}
"""

#: The distinct ``(CAUSA_GENE, CAUSA_ESPE)`` pairs of the staged archive, for
#: :func:`upsert_causes`. Corrupt rows are excluded, which is the point of resolving
#: :data:`RESOLVED_COLUMNS`' ``corrupt`` before this runs.
CAUSE_PAIRS_SQL = """
SELECT DISTINCT NULLIF(btrim(coalesce(causa_gene, ''), {trimmed}), '') AS cause,
                NULLIF(btrim(coalesce(causa_espe, ''), {trimmed}), '') AS specific_cause
FROM {staging_table}
WHERE NOT corrupt
"""

#: Published causes in the catalogue that no canonical form was found for.
#:
#: Checked against the whole table rather than this season's rows, for the reason
#: :mod:`src.apps.imports.wildfires.mexico_conafor.import_wildfires` gives: a cause
#: that appears in only one season is still a hole in a fifteen-season series, and
#: this is the one place the whole catalogue is in view.
UNRECONCILED_CAUSES_SQL = """
SELECT cause, count(*) AS fires
FROM conaf_fire_cause
JOIN conaf_wildfire ON conaf_wildfire.cause_id = conaf_fire_cause.id
WHERE conaf_fire_cause.cause IS NOT NULL
  AND conaf_fire_cause.cause_normalised IS NULL
GROUP BY cause ORDER BY fires DESC
"""

#: How many rows the archive marks as corrupt, for the summary.
CORRUPT_SQL = "SELECT count(*) FROM {staging_table} WHERE corrupt"

#: The seasons the staged archive holds rows in, after ``--season``.
#:
#: These are the steps the import walks, one transaction each, so the condition has
#: to be **exactly** the one :data:`TRANSFORM_SQL`'s ``cleaned`` applies — corrupt
#: rows excluded, because a season whose only rows are corrupt is not a season this
#: import can write, and walking it would delete a good season and replace it with
#: nothing.
STAGED_SEASONS_SQL = """
SELECT DISTINCT season_start_year
FROM {staging_table}
WHERE NOT corrupt
  AND season_start_year IS NOT NULL
  AND ({season_filter})
ORDER BY season_start_year
"""

#: How finely :data:`BOUNDARY_PARTS_SQL` and :data:`TIME_ZONE_PARTS_SQL` cut the
#: polygons they copy. The PostGIS recipe's own figure; anything of this order works,
#: because what matters is that a piece is small, not how small.
SUBDIVIDE_VERTICES = 256

#: The countries the staged points could be in, cut into pieces small enough to test
#: a point against.
#:
#: **This is what makes the import take minutes rather than hours.** The lookup it
#: replaces — ``ST_Contains`` straight against ``admin_boundary`` — is indexed and
#: still costs about 100 ms per fire, because Chile's OCHA level 0 boundary is
#: 8.7 million vertices and 134 MB: the GiST index finds the country, and then every
#: single row detoasts and tests against the whole of it. Cut into ≤256-vertex
#: pieces, the same lookup costs 0.03 ms — three thousand times less — and answers
#: identically, because the pieces tile the country they came from.
#:
#: Restricted to the staged extent, so an archive pays only for the countries its own
#: fires could be in: Chile and its neighbours, not all 318 of them. A country whose
#: polygon contains one of the points necessarily has a bounding box meeting their
#: extent, so nothing that could match is left out.
#:
#: Built during the run and dropped when it ends. A permanent table of pieces would
#: serve every import rather than only this one — ``canada_nbac`` and ``canada_nfdb``
#: pay the same toll on Canada's 8.5 million vertices — but it would have to be kept
#: in step with the boundary imports that fill ``admin_boundary``, and this import
#: does not have to wait for that to be built.
BOUNDARY_PARTS_SQL = """
CREATE TABLE {parts_table} AS
SELECT boundary.id AS admin_boundary_id,
       ST_Subdivide(boundary.geometry, {max_vertices}) AS geometry
FROM admin_boundary AS boundary
WHERE boundary.level = 0
  AND boundary.data_provider_id = :boundary_provider_id
  AND boundary.geometry && ST_GeomFromText(:extent, 4326)
"""

#: The time zone areas the staged points could be in, cut the same way.
#:
#: Cheaper to begin with than the countries — no zone is a Chile — but the same 3 ms
#: per fire is a quarter of an hour over the whole archive, and it goes the same way
#: for the same reason.
TIME_ZONE_PARTS_SQL = """
CREATE TABLE {parts_table} AS
SELECT time_zone.name AS name,
       ST_Subdivide(time_zone.geometry, {max_vertices}) AS geometry
FROM time_zone
WHERE time_zone.geometry && ST_GeomFromText(:extent, 4326)
"""

#: The index that is the whole point of the two tables above.
PARTS_INDEX_SQL = "CREATE INDEX ON {parts_table} USING gist (geometry)"

#: The grid the staged extent is rounded out to, in degrees.
#:
#: Coarse on purpose, and this is the number that decides how often a run stops to
#: cut polygons up. Rounded to the degree, every season is a slightly different box —
#: one fire further north than last year's is enough — so each archive would find the
#: pieces a hair too small and cut Chile again, 23 times over a full run. Rounded to
#: ten, every mainland season is the same box and Rapa Nui is one other: two builds
#: for the whole directory, and the second only because Rapa Nui is 3,500 km out.
#:
#: The price is the neighbours a wider box takes in — Peru, Bolivia, Argentina and
#: the rest of the Southern Cone are cut up as well as Chile. They are small: Chile
#: alone is 8.7 million of the vertices involved, and the whole of the rest of the
#: box is a fraction of it.
EXTENT_SNAP_DEGREES = 10

#: The box the staged points cover, in EPSG:4326, or ``NULL`` for an empty archive,
#: rounded out to :data:`EXTENT_SNAP_DEGREES` so the next archive can reuse it.
STAGED_EXTENT_SQL = """
SELECT ST_AsText(ST_MakeEnvelope(
           GREATEST(floor(ST_XMin(box) / {snap}) * {snap}, -180),
           GREATEST(floor(ST_YMin(box) / {snap}) * {snap}, -90),
           LEAST(ceil(ST_XMax(box) / {snap}) * {snap}, 180),
           LEAST(ceil(ST_YMax(box) / {snap}) * {snap}, 90),
           4326)) AS extent
FROM (
    SELECT ST_Extent(ST_Transform(staging.geom, 4326))::geometry AS box
    FROM {staging_table} AS staging
    WHERE NOT staging.corrupt AND staging.geom IS NOT NULL
) AS staged
WHERE box IS NOT NULL
"""

#: Whether pieces cut for ``:covered`` can answer for points inside ``:extent``.
#:
#: They can when the one box holds the other, and only then: a country selected for
#: the first box is not necessarily one that would have been selected for a box
#: reaching further, and the pieces of the country that was missed do not exist to
#: be found. Boundary cases are answered ``false`` and cost a rebuild, which is the
#: harmless way round.
EXTENT_COVERED_SQL = """
SELECT ST_Contains(ST_GeomFromText(:covered, 4326), ST_GeomFromText(:extent, 4326))
"""

#: The box holding both, for a rebuild that will not have to be done again for either.
EXTENT_UNION_SQL = """
SELECT ST_AsText(ST_Envelope(ST_Collect(ST_GeomFromText(:covered, 4326),
                                        ST_GeomFromText(:extent, 4326))))
"""

#: Which of ``conaf_ignition``'s two grid columns a fire has to be on to belong to
#: the territory the archive being imported covers.
#:
#: **The unit that gets replaced is a season *of one territory*, not a season.** The
#: mainland and Easter Island are published as separate archives for the same
#: ``TEMPORADA`` — ``if_temporada_2024_2025`` and
#: ``if_temporada_islapascua_2024_2025`` are both season 2024-2025 — so a delete
#: scoped to the season alone destroys the half of it the other archive wrote.
#:
#: The grid *is* the territory here, which is what makes this test the right one and
#: not merely a convenient one: CONAF splits the archives by territory precisely
#: because the two are on different UTM zones.
GRID_FILTER_SQL = ("point.geometry_utm19s IS NOT NULL" ,
                   "point.geometry_utm12s IS NOT NULL")

#: Removes the reports of one season *of one territory*, and their points.
#:
#: One statement, for the reason the sibling imports give: the reports reference the
#: points and the child tables reference their parents, so no order of separate
#: statements is safe, while inside one statement the foreign keys are checked once
#: at the end against a consistent final state.
DELETE_SEASONS_SQL = """
WITH doomed AS (
    SELECT conaf_wildfire.id, conaf_wildfire.ignition_id
    FROM conaf_wildfire
    JOIN conaf_ignition AS point ON point.id = conaf_wildfire.ignition_id
    WHERE conaf_wildfire.season_start_year = ANY(:seasons)
      AND {grid_filter}
),
removed_child AS (
    DELETE FROM conaf_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM conaf_ignition WHERE id IN (SELECT ignition_id FROM doomed) RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: How many of the reports about to be replaced an *incendio de magnitud* perimeter
#: points at.
#:
#: Asked up front so the run says what the problem is instead of dying on the
#: foreign key half way through.
LINKED_SQL = """
SELECT count(*) FROM conaf_magnitud_wildfire
WHERE conaf_wildfire_id IN (
    SELECT conaf_wildfire.id
    FROM conaf_wildfire
    JOIN conaf_ignition AS point ON point.id = conaf_wildfire.ignition_id
    WHERE conaf_wildfire.season_start_year = ANY(:seasons)
      AND {grid_filter}
)
"""

#: Maps **one season** of the staged archive onto the four tables of the model.
#:
#: One statement and one season's rows, run once per season. ``MATERIALIZED`` is not
#: negotiable on ``numbered``: it calls ``nextval`` twice per row, and a CTE the
#: planner is free to inline could call them again for every reference, handing one
#: fire two different keys.
#:
#: The CTEs, in order:
#:
#: ``cleaned``
#:     Every text attribute trimmed, an all-whitespace value becoming ``NULL``, the
#:     reporter folded, the codes padded, the coordinate triple read, and the season
#:     filter applied. Corrupt rows are already excluded.
#: ``dated``
#:     ``start_date_time`` resolved: the parsed instant where there is one, the first
#:     instant of the season where there is not, with the precision that says which.
#: ``numbered``
#:     Keys drawn from both sequences up front, one of each per row — every published
#:     feature has a geometry, so unlike the Canadian import there is no row here
#:     without a point.
#: ``zoned``
#:     Zone and country from the point. Chile spans three zones, so this is a real
#:     lookup and not a formality: ``Pacific/Easter`` is two hours from the mainland
#:     and ``America/Punta_Arenas`` one. Both lookups go to the subdivided copies
#:     :func:`build_lookup_parts` leaves in the staging schema rather than to
#:     ``admin_boundary`` and ``time_zone`` themselves — see :data:`BOUNDARY_PARTS_SQL`
#:     for why, and for the three orders of magnitude it is worth.
#:
#:     ``ST_Intersects`` and not ``ST_Contains``, which is forced by the subdivision:
#:     cutting a country into pieces creates internal edges that were never part of
#:     its boundary, and ``ST_Contains`` rejects a point lying exactly on one, so a
#:     fire could fall down the crack between two pieces of the same country. The
#:     difference elsewhere is confined to a point exactly on a real border, which
#:     now matches one of the two sides instead of neither.
#: ``ins_ignition`` / ``ins_conaf_ignition``
#:     The point, in EPSG:4326 on the generic row and on its published grid on the
#:     provider one — whichever of the two columns this archive's grid is.
#: ``ins_wildfire`` / ``written``
#:     The report, with ``perimeter`` NULL and always.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT staging.season_start_year AS season_start_year,
           NULLIF(btrim(staging.temporada, {trimmed}), '') AS season,
           NULLIF(btrim(staging.numero_reg, {trimmed}), '') AS number_text,
           NULLIF(btrim(staging.nom_incen, {trimmed}), '') AS name,
           {reporter} AS reporter,
           NULLIF(btrim(staging.region, {trimmed}), '') AS region,
           NULLIF(btrim(staging.provincia, {trimmed}), '') AS province,
           NULLIF(btrim(staging.comuna, {trimmed}), '') AS commune,
           {region_code} AS region_code,
           {province_code} AS province_code,
           {commune_code} AS commune_code,
           NULLIF(btrim(staging.inicio_c, {trimmed}), '') AS start_place,
           NULLIF(btrim(staging.combus_i, {trimmed}), '') AS fuel,
           staging.cause_id AS cause_id,
           staging.start_at AS start_at,
           staging.end_at AS end_at,
           staging.start_precision AS start_precision,
           {utm_easting} AS utm_easting,
           {utm_northing} AS utm_northing,
           {utm_zone} AS utm_zone,
           {utm_band} AS utm_band,
           staging.pino_00_10 AS area_ha_pine_0_10,
           staging.pino_11_17 AS area_ha_pine_11_17,
           staging.pino18_mas AS area_ha_pine_18_plus,
           staging.eucalipto AS area_ha_eucalyptus,
           staging.otras_plan AS area_ha_other_plantation,
           staging.total_plan AS area_ha_plantation,
           staging.arbolado AS area_ha_native_forest,
           staging.matorral AS area_ha_scrub,
           staging.pastizal AS area_ha_grassland,
           staging.total_veg AS area_ha_vegetation,
           staging.agricola AS area_ha_agricultural,
           staging.desechos AS area_ha_debris,
           staging.total_otra AS area_ha_other,
           staging.superficie AS area_ha_total,
           ST_Force2D(ST_GeometryN(staging.geom, 1)) AS geom
    FROM {staging_table} AS staging
    WHERE NOT staging.corrupt
      AND staging.season_start_year IS NOT NULL
      AND staging.geom IS NOT NULL
      AND ({season_filter})
),
dated AS MATERIALIZED (
    SELECT cleaned.*,
           CASE WHEN cleaned.number_text ~ '^[0-9]+(\\.0+)?$'
                     AND split_part(cleaned.number_text, '.', 1)::bigint
                         BETWEEN 1 AND 2147483647
                THEN split_part(cleaned.number_text, '.', 1)::integer
                ELSE NULL
           END AS number,
           COALESCE(cleaned.start_at,
                    make_timestamp(cleaned.season_start_year, :season_start_month,
                                   1, 0, 0, 0)) AS resolved_start,
           COALESCE(cleaned.start_precision, :precision_season) AS date_time_precision,
           -- The office's own subtotals against its own total. Three NULL subtotals
           -- and a NULL total agree trivially and are reported as agreeing, which is
           -- right: there is nothing to disagree about.
           (abs(COALESCE(cleaned.area_ha_plantation, 0)
                + COALESCE(cleaned.area_ha_vegetation, 0)
                + COALESCE(cleaned.area_ha_other, 0)
                - COALESCE(cleaned.area_ha_total, 0)) < 0.02) AS area_totals_agree
    FROM cleaned
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           nextval(pg_get_serial_sequence('ignition', 'id')) AS ignition_id,
           dated.*
    FROM dated
),
zoned AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(numbered.geom, 4326) AS point_4326,
           zone.name AS time_zone,
           country.id AS admin_boundary_id
    FROM numbered
    LEFT JOIN LATERAL (
        SELECT part.name
        FROM {time_zone_parts} AS part
        WHERE ST_Intersects(part.geometry, ST_Transform(numbered.geom, 4326))
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT part.admin_boundary_id AS id
        FROM {boundary_parts} AS part
        WHERE ST_Intersects(part.geometry, ST_Transform(numbered.geom, 4326))
        LIMIT 1
    ) AS country ON TRUE
),
ins_ignition AS (
    INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                          admin_boundary_id)
    SELECT zoned.ignition_id,
           'conaf_ignition',
           :provider_id,
           zoned.point_4326,
           zoned.resolved_start AT TIME ZONE COALESCE(zoned.time_zone,
                                                      :fallback_time_zone),
           zoned.time_zone,
           zoned.admin_boundary_id
    FROM zoned
    RETURNING id
),
ins_conaf_ignition AS (
    INSERT INTO conaf_ignition (id, season_start_year, number, region_code,
                                utm_easting, utm_northing, utm_zone, utm_band,
                                geometry_utm19s, geometry_utm12s)
    SELECT zoned.ignition_id, zoned.season_start_year, zoned.number, zoned.region_code,
           zoned.utm_easting, zoned.utm_northing, zoned.utm_zone, zoned.utm_band,
           CASE WHEN :source_srid = {mainland_srid} THEN zoned.geom ELSE NULL END,
           CASE WHEN :source_srid = {easter_srid} THEN zoned.geom ELSE NULL END
    FROM zoned
    JOIN ins_ignition ON ins_ignition.id = zoned.ignition_id
    RETURNING id
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT zoned.wildfire_id,
           'conaf_wildfire',
           :provider_id,
           zoned.resolved_start AT TIME ZONE COALESCE(zoned.time_zone,
                                                      :fallback_time_zone),
           CASE WHEN zoned.end_at IS NULL THEN NULL
                ELSE zoned.end_at AT TIME ZONE COALESCE(zoned.time_zone,
                                                        :fallback_time_zone)
           END,
           zoned.time_zone,
           -- NULL, and always: CONAF publishes the report as a point. The Chilean
           -- perimeters are the incendios de magnitud product's and belong to a
           -- provider row of their own.
           NULL,
           zoned.admin_boundary_id
    FROM zoned
    JOIN ins_conaf_ignition ON ins_conaf_ignition.id = zoned.ignition_id
    RETURNING id
),
written AS (
    INSERT INTO conaf_wildfire (id, ignition_id, season, season_start_year, number,
                                name, reporter, region, province, commune, region_code,
                                province_code, commune_code, start_place, fuel, cause_id,
                                date_time_precision, area_ha_pine_0_10,
                                area_ha_pine_11_17, area_ha_pine_18_plus,
                                area_ha_eucalyptus, area_ha_other_plantation,
                                area_ha_plantation, area_ha_native_forest, area_ha_scrub,
                                area_ha_grassland, area_ha_vegetation,
                                area_ha_agricultural, area_ha_debris, area_ha_other,
                                area_ha_total, area_totals_agree)
    SELECT zoned.wildfire_id, zoned.ignition_id,
           COALESCE(zoned.season, :season_label), zoned.season_start_year, zoned.number,
           zoned.name, zoned.reporter, zoned.region, zoned.province, zoned.commune,
           zoned.region_code, zoned.province_code, zoned.commune_code,
           zoned.start_place, zoned.fuel, zoned.cause_id, zoned.date_time_precision,
           zoned.area_ha_pine_0_10, zoned.area_ha_pine_11_17, zoned.area_ha_pine_18_plus,
           zoned.area_ha_eucalyptus, zoned.area_ha_other_plantation,
           zoned.area_ha_plantation, zoned.area_ha_native_forest, zoned.area_ha_scrub,
           zoned.area_ha_grassland, zoned.area_ha_vegetation, zoned.area_ha_agricultural,
           zoned.area_ha_debris, zoned.area_ha_other,
           GREATEST(zoned.area_ha_total, 0), zoned.area_totals_agree
    FROM zoned
    JOIN ins_wildfire ON ins_wildfire.id = zoned.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS in_scope,
       (SELECT count(*) FROM dated WHERE date_time_precision = :precision_minute)
           AS with_time,
       (SELECT count(*) FROM dated WHERE date_time_precision = :precision_day)
           AS with_day,
       (SELECT count(*) FROM dated WHERE date_time_precision = :precision_season)
           AS season_only,
       (SELECT count(*) FROM dated WHERE end_at IS NOT NULL) AS with_end,
       (SELECT count(*) FROM dated WHERE end_at IS NOT NULL
                                     AND end_at < resolved_start) AS end_before_start,
       (SELECT count(*) FROM dated WHERE NOT area_totals_agree) AS area_mismatch,
       (SELECT count(*) FROM dated WHERE cause_id IS NULL) AS no_cause,
       (SELECT count(*) FROM zoned WHERE time_zone IS NULL) AS no_time_zone,
       (SELECT count(*) FROM written) AS written
"""


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def normalise_staging_columns(session: Session, staging_table: str,
                              logger: logging.LoggerAdapter) -> None:
    """Rename the staged columns to one canonical set, and type them usably.

    Raises
    ------
    RuntimeError
        If the staged layer publishes none of the spellings of one of
        :data:`REQUIRED_COLUMNS`.

    Notes
    -----
    Renaming rather than reading through an alias in the SQL, because the SQL is one
    statement of some length and threading 33 alternative column names through it
    would make it unreadable and unreviewable. After this runs, every staged table
    looks the same whichever of the 23 layers it came from.

    A column that is already canonically named is left alone; a canonical name that
    is *also* present alongside an alias wins, which is why the canonical spelling is
    first in each :data:`COLUMN_ALIASES` entry.

    An attribute this layer does not publish at all — and there are several, see
    :data:`REQUIRED_COLUMNS` — is **added as an empty column** rather than treated as
    an error. That is what makes one transform work over all 23 layers: the SQL reads
    the same column names every time and gets ``NULL`` where the season published
    nothing, which is exactly what those fires should store. The absences are logged,
    because a layer that stops publishing something it used to is worth seeing in a
    run.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = {
        name: data_type
        for name, data_type in session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table"
        ), {"schema": schema or "public", "table": table}).all()
    }

    absent = []
    for canonical, spellings in COLUMN_ALIASES.items():
        present = next((name for name in spellings if name in loaded), None)
        if present is None:
            absent.append(canonical)
            continue
        if present != canonical:
            logger.debug("Renaming staged %s to %s", present, canonical)
            session.execute(text(
                f"ALTER TABLE {staging_table} RENAME COLUMN {present} TO {canonical}"
            ))
            loaded[canonical] = loaded.pop(present)

    unusable = sorted(set(absent) & set(REQUIRED_COLUMNS))
    if unusable:
        raise RuntimeError(
            f"the staged layer publishes no {', '.join(unusable)}: this is not a CONAF "
            f"seasonal report layer, or its attributes have been renamed again"
        )
    if absent:
        logger.info("This layer publishes no %s; those columns are stored empty",
                    ", ".join(sorted(absent)))
        for name in absent:
            session.execute(text(
                f"ALTER TABLE {staging_table} ADD COLUMN {name} {STAGING_COLUMNS[name]}"
            ))
            loaded[name] = STAGING_COLUMNS[name]

    for name, wanted in STAGING_COLUMNS.items():
        if loaded[name] in COMPATIBLE_TYPES.get(wanted, {wanted}):
            continue
        logger.debug("Converting staged %s from %s to %s", name, loaded[name], wanted)
        session.execute(text(
            f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {wanted} "
            f"USING NULLIF(btrim({name}::text), '')::{wanted}"
        ))

    for name, data_type in RESOLVED_COLUMNS.items():
        session.execute(text(
            f"ALTER TABLE {staging_table} ADD COLUMN IF NOT EXISTS {name} {data_type}"
        ))


def mark_corrupt(session: Session, staging_table: str,
                 logger: logging.LoggerAdapter) -> int:
    """Mark the records whose text fields are binary, returning how many.

    Notes
    -----
    The test is :func:`~src.providers.chile_conaf.is_corrupt`, applied here in SQL
    over the columns that carry the damage in the archive as published — the
    administrative names, the reporter, the season and the two causes.

    It is a marker column rather than a filter in the transform because three
    different things have to skip these rows: the cause catalogue, the season list
    and the transform itself. Marking once is cheaper than testing three times, and
    it means the count in the summary is the same rows every consumer skipped.

    Three rows of ``if_temporada_2010_2011``, and none anywhere else.
    """
    marked = session.execute(text(
        f"UPDATE {staging_table} SET corrupt = ("
        f"    coalesce(temporada, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(comuna, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(region, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(provincia, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(ambito, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(nom_incen, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(causa_gene, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'"
        f" OR coalesce(causa_espe, '') ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]')"
    )).rowcount
    corrupt = session.scalar(text(CORRUPT_SQL.format(staging_table=staging_table)))
    if corrupt:
        logger.warning("%d of %d staged record(s) have binary in their text fields and "
                       "are dropped: the published DBF has come apart at those rows",
                       corrupt, marked)
    return corrupt or 0


def resolve_seasons(session: Session, staging_table: str, fallback: int | None,
                    logger: logging.LoggerAdapter) -> int:
    """Fill ``season_start_year`` from the published ``TEMPORADA``, returning fallbacks.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        The session the archive was staged through.
    staging_table : str
        The staging table, schema-qualified.
    fallback : int or None
        The season the archive as a whole is for, used for a row whose ``TEMPORADA``
        is unreadable. ``None`` leaves those rows unresolved, and the transform then
        skips them.
    logger : logging.LoggerAdapter
        Where the fallbacks are reported.

    Returns
    -------
    int
        How many rows needed the fallback.

    Notes
    -----
    Seven features of the whole archive need it: six blank cells in
    ``if_temporada_2010_2011`` and one ``'2023-2025'`` in
    ``if_magnitud_2023_2024``. Both are reported rather than absorbed —
    :func:`~src.providers.chile_conaf.season_start_year` refuses a non-consecutive
    pair on purpose, and a run where that number grows is a run worth looking at.
    """
    rows = session.execute(text(SEASON_STRINGS_SQL.format(
        staging_table=staging_table, trimmed=TRIMMED_CHARS))).all()
    published = [row.season_text for row in rows]
    resolved = {value: chile_conaf.season_start_year(value) for value in published}

    known = {value: year for value, year in resolved.items() if year is not None}
    if known:
        session.execute(text(
            f"UPDATE {staging_table} AS staging SET season_start_year = mapping.year "
            f"FROM (SELECT * FROM unnest(:published ::text[], :years ::integer[])) "
            f"AS mapping(published, year) "
            f"WHERE btrim(coalesce(staging.temporada, ''), {TRIMMED_CHARS}) "
            f"      = mapping.published"),
            {"published": list(known), "years": list(known.values())},
        )

    unresolved = session.scalar(text(
        f"SELECT count(*) FROM {staging_table} WHERE season_start_year IS NULL"))
    if unresolved and fallback is not None:
        session.execute(text(
            f"UPDATE {staging_table} SET season_start_year = :fallback "
            f"WHERE season_start_year IS NULL"), {"fallback": fallback})
        logger.warning("%d staged record(s) publish no readable TEMPORADA (%s); read as "
                       "season %d-%d, the one this archive is for", unresolved,
                       ", ".join(repr(value) for value, year in resolved.items()
                                 if year is None) or "blank",
                       fallback, fallback + 1)
    elif unresolved:
        logger.warning("%d staged record(s) publish no readable TEMPORADA and this "
                       "archive's season could not be guessed; they are skipped",
                       unresolved)
    return unresolved or 0


def resolve_dates(session: Session, staging_table: str,
                  logger: logging.LoggerAdapter,
                  start_column: str = "fh_inicio",
                  end_column: str = "fh_extinci") -> int:
    """Fill ``start_at``, ``end_at`` and ``start_precision``, returning unreadable cells.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        The session the archive was staged through.
    staging_table : str
        The staging table, schema-qualified.
    logger : logging.LoggerAdapter
        Where an unreadable cell is reported.
    start_column, end_column : str, optional
        The staged columns to read. The defaults are the report archive's;
        :mod:`src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires` passes
        ``fecha_ini`` and ``fecha_ter``, which is what the perimeter archive calls
        them.

    Notes
    -----
    :func:`~src.providers.chile_conaf.parse_published_datetime` is the reader, and it
    is called once per **distinct** published string rather than once per fire: the
    four formats need a Spanish month table and one is day-month-year, so the parse
    is Python, and 95,868 round trips would be paid for nothing when a season's fires
    share a few thousand distinct instants.

    ``start_precision`` is left ``NULL`` where there is no start to read. The
    transform reads that as
    :data:`~src.providers.chile_conaf.PRECISION_SEASON` and dates the fire to the
    first instant of its season; doing it there rather than here keeps the
    season-window arithmetic in one place.

    A cell that is neither blank nor readable is counted and reported. There are none
    in the archive as published, which is exactly what makes a new one worth
    noticing.
    """
    rows = session.execute(text(DATE_STRINGS_SQL.format(
        staging_table=staging_table, trimmed=TRIMMED_CHARS,
        start_column=start_column, end_column=end_column))).all()

    starts: dict[str, tuple[object, str]] = {}
    ends: dict[str, object] = {}
    unreadable: set[str] = set()
    for row in rows:
        for value, target in ((row.start_text, starts), (row.end_text, ends)):
            if value is None or value in target:
                continue
            parsed, precision = chile_conaf.parse_published_datetime(value)
            if parsed is None:
                unreadable.add(value)
                continue
            target[value] = (parsed, precision) if target is starts else parsed

    if starts:
        session.execute(text(
            f"UPDATE {staging_table} AS staging "
            f"SET start_at = mapping.parsed, start_precision = mapping.precision "
            f"FROM (SELECT * FROM unnest(:published ::text[], "
            f"                           :parsed ::timestamp[], "
            f"                           :precision ::text[])) "
            f"AS mapping(published, parsed, precision) "
            f"WHERE NULLIF(btrim(coalesce(staging.{start_column}, ''), {TRIMMED_CHARS}), '') "
            f"      = mapping.published"),
            {"published": list(starts),
             "parsed": [value[0] for value in starts.values()],
             "precision": [value[1] for value in starts.values()]},
        )
    if ends:
        session.execute(text(
            f"UPDATE {staging_table} AS staging SET end_at = mapping.parsed "
            f"FROM (SELECT * FROM unnest(:published ::text[], :parsed ::timestamp[])) "
            f"AS mapping(published, parsed) "
            f"WHERE NULLIF(btrim(coalesce(staging.{end_column}, ''), {TRIMMED_CHARS}), '') "
            f"      = mapping.published"),
            {"published": list(ends), "parsed": list(ends.values())},
        )

    if unreadable:
        logger.warning("%d published date string(s) could not be read and are stored as "
                       "no date: %s. Add the format to "
                       "src.providers.chile_conaf.parse_published_datetime",
                       len(unreadable),
                       ", ".join(repr(value) for value in sorted(unreadable)[:5]))
    logger.debug("Read %d distinct start(s) and %d distinct end(s)", len(starts), len(ends))
    return len(unreadable)


def upsert_causes(session: Session, staging_table: str,
                  logger: logging.LoggerAdapter) -> int:
    """Store the cause classifications this archive uses and link the staged rows.

    Returns
    -------
    int
        How many distinct classifications the archive publishes.

    Notes
    -----
    The catalogue is not seeded from a fixed list — it is whatever the archive
    actually contains — so a cause CONAF types for the first time arrives with the
    first fire that uses it. :func:`~src.providers.chile_conaf.fire_cause.resolve_cause`
    is what turns the published pair into a row: it splits the code off, decides which
    of the two numberings the code belongs to, and only then names the cause. Doing
    those in that order is what stops 2016-2017's bare ``'04.01'`` being read as
    *faenas forestales* instead of *incendios de causa desconocida*.

    ``ON CONFLICT DO NOTHING``, in **three statements**, because uniqueness is
    enforced by three partial indexes rather than one constraint: either half of the
    pair can be ``NULL`` and in SQL two ``NULL``\\ s are not equal, so each
    combination needs its own conflict target. Doing nothing on conflict also means
    an existing row is left alone rather than rewritten, so a reconciliation
    corrected by hand in the database survives the next import.

    The pair with both halves ``NULL`` is not a row at all — 840 fires publish
    neither — and those fires keep ``cause_id IS NULL``.
    """
    rows = session.execute(text(CAUSE_PAIRS_SQL.format(
        staging_table=staging_table, trimmed=TRIMMED_CHARS))).all()
    resolved = [resolve_cause(row.cause, row.specific_cause) for row in rows]
    values = [entry for entry in resolved
              if entry["cause"] is not None or entry["specific_cause"] is not None]
    if not values:
        return 0

    unreconciled = sorted({entry["cause"] for entry in values
                           if entry["cause"] is not None
                           and entry["cause_normalised"] is None})
    if unreconciled:
        logger.warning("No canonical form for %d published cause(s), stored "
                       "unreconciled: %s. Add them to "
                       "src.providers.chile_conaf.fire_cause.CAUSE_NORMALISATIONS",
                       len(unreconciled),
                       ", ".join(repr(term[:60]) for term in unreconciled))

    both = [entry for entry in values
            if entry["cause"] is not None and entry["specific_cause"] is not None]
    cause_only = [entry for entry in values
                  if entry["cause"] is not None and entry["specific_cause"] is None]
    specific_only = [entry for entry in values
                     if entry["cause"] is None and entry["specific_cause"] is not None]
    for batch, elements, where in (
            (both, ["cause", "specific_cause"],
             "cause IS NOT NULL AND specific_cause IS NOT NULL"),
            (cause_only, ["cause"], "cause IS NOT NULL AND specific_cause IS NULL"),
            (specific_only, ["specific_cause"],
             "cause IS NULL AND specific_cause IS NOT NULL"),
    ):
        if batch:
            session.execute(
                pg_insert(ConafFireCause.__table__).values(batch)
                .on_conflict_do_nothing(index_elements=elements,
                                        index_where=text(where))
            )

    # Link the staged rows to the catalogue. Matched on the published pair with the
    # same trim the catalogue was built with, and NULL-safe on both halves because
    # either can be absent.
    session.execute(text(
        f"UPDATE {staging_table} AS staging SET cause_id = fire_cause.id "
        f"FROM conaf_fire_cause AS fire_cause "
        f"WHERE NOT staging.corrupt "
        f"  AND fire_cause.cause IS NOT DISTINCT FROM "
        f"      NULLIF(btrim(coalesce(staging.causa_gene, ''), {TRIMMED_CHARS}), '') "
        f"  AND fire_cause.specific_cause IS NOT DISTINCT FROM "
        f"      NULLIF(btrim(coalesce(staging.causa_espe, ''), {TRIMMED_CHARS}), '')"
    ))
    logger.debug("Catalogued %d cause classification(s) for this archive", len(values))
    return len(values)


def report_unreconciled_causes(session: Session, logger: logging.Logger) -> None:
    """Warn about catalogued causes with no canonical form, over the whole table."""
    stranded = session.execute(text(UNRECONCILED_CAUSES_SQL)).all()
    if stranded:
        logger.warning("%d published cause(s) in the catalogue have no canonical form "
                       "(%s). Their fires are stored, but a series grouped by "
                       "cause_normalised drops them into a NULL bucket",
                       len(stranded),
                       ", ".join(f"{cause[:40]!r} x{fires}" for cause, fires in stranded))


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------

def season_filter(seasons: list[int] | None) -> str:
    """The ``WHERE`` fragment restricting to ``--season``, or one that lets all through."""
    return "staging.season_start_year = ANY(:seasons)" if seasons else "TRUE"


def staged_seasons(session: Session, staging_table: str,
                   seasons: list[int] | None) -> list[int]:
    """The seasons the staged archive holds usable rows in, in order."""
    statement = STAGED_SEASONS_SQL.format(
        staging_table=staging_table,
        season_filter=season_filter(seasons).replace("staging.", ""),
    )
    parameters = {"seasons": seasons} if seasons else {}
    return list(session.scalars(text(statement), parameters).all())


def summarise_seasons(seasons: list[int]) -> str:
    """``2010-2011, 2011-2012, …`` for a log line, contracted when there are many."""
    if not seasons:
        return "none"
    if len(seasons) <= 3:
        return ", ".join(f"{year}-{year + 1}" for year in seasons)
    return (f"{seasons[0]}-{seasons[0] + 1} to {seasons[-1]}-{seasons[-1] + 1} "
            f"({len(seasons)} seasons)")


def grid_filter(source_srid: int) -> str:
    """The ``WHERE`` fragment picking out the territory ``source_srid`` is the grid of.

    See :data:`GRID_FILTER_SQL`: a season is replaced one territory at a time,
    because the mainland and Easter Island are published as separate archives for the
    same season and each must leave the other alone.
    """
    mainland, easter = GRID_FILTER_SQL
    return mainland if source_srid == chile_conaf.SOURCE_SRID_MAINLAND else easter


def check_not_linked(session: Session, seasons: list[int], source_srid: int) -> None:
    """Refuse to replace a season whose reports a perimeter points at.

    Raises
    ------
    RuntimeError
        If any *incendio de magnitud* perimeter is bound to a report of these seasons
        on this grid.
    """
    linked = session.scalar(
        text(LINKED_SQL.format(grid_filter=grid_filter(source_srid))),
        {"seasons": seasons},
    )
    if linked:
        raise RuntimeError(
            f"{linked} incendio de magnitud perimeter(s) are bound to reports of "
            f"{summarise_seasons(seasons)}. Re-importing would leave them pointing at "
            f"rows that no longer exist. Clear the bindings first with "
            f"src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires, "
            f"or re-import the perimeters afterwards"
        )


def delete_seasons(session: Session, seasons: list[int], source_srid: int) -> None:
    """Remove one territory's reports and points for these seasons.

    Checks first that no perimeter points at any of them; see
    :func:`check_not_linked`.
    """
    check_not_linked(session, seasons, source_srid)
    session.execute(
        text(DELETE_SEASONS_SQL.format(grid_filter=grid_filter(source_srid))),
        {"seasons": seasons},
    )


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Audit:
    """What the transform did, for the summary lines.

    Attributes
    ----------
    in_scope : int
        Rows the season filter let through, corrupt and geometry-less rows already
        excluded.
    with_time, with_day, season_only : int
        Fires by how much of their start is real:
        :data:`~src.providers.chile_conaf.PRECISION_MINUTE`,
        :data:`~src.providers.chile_conaf.PRECISION_DAY` and
        :data:`~src.providers.chile_conaf.PRECISION_SEASON`.
    with_end : int
        Fires with a published extinction time.
    end_before_start : int
        Fires whose published end precedes their start. Stored as published; see the
        notes.
    area_mismatch : int
        Fires whose three published subtotals do not sum to their published total.
    no_cause : int
        Fires publishing neither a *causa general* nor a *causa específica*.
    no_time_zone : int
        Fires whose point matched no time zone area, and which are therefore dated
        against :data:`~src.providers.chile_conaf.DEFAULT_TIME_ZONE`.
    written : int
        Fires actually stored.

    Notes
    -----
    Every field is a **count over a partition of the staged rows**: the transform
    runs once per season and no row is in two seasons, so adding the seasons' audits
    gives exactly what one pass over the archive would have reported. That is what
    :meth:`__add__` is for.

    ``end_before_start`` is counted and not corrected. Swapping the two would be
    inventing a fire that ran the other way; the pair is stored as published and the
    count is how a reader learns to distrust the handful that are like that.

    Frozen, so a total is built by addition rather than by mutating a running tally
    that could quietly be added to twice.
    """

    in_scope: int = 0
    with_time: int = 0
    with_day: int = 0
    season_only: int = 0
    with_end: int = 0
    end_before_start: int = 0
    area_mismatch: int = 0
    no_cause: int = 0
    no_time_zone: int = 0
    written: int = 0

    @classmethod
    def from_row(cls, row) -> Audit:
        """The audit the transform's one row reports."""
        return cls(**{field.name: getattr(row, field.name) for field in fields(cls)})

    def __add__(self, other: Audit) -> Audit:
        """The two seasons' counts, summed field by field."""
        return Audit(**{field.name: getattr(self, field.name) + getattr(other, field.name)
                        for field in fields(self)})


@dataclass
class LookupParts:
    """The two subdivided lookup tables, and the box they were cut for.

    Named after the staging table and living in the staging schema beside it, so
    that ``--staging-table`` keeps two runs apart exactly as it already does, and
    ``--keep-staging`` keeps these to be looked at too.

    One of these is made per run and handed to every archive, because ``covered`` is
    what lets the second archive use the first one's pieces: cutting Chile up costs
    about half a minute, and a run over all 23 archives that did it again each time
    would spend ten minutes cutting the same country into the same pieces.
    """

    boundary: str
    time_zone: str
    #: The box the pieces answer for, as WKT in EPSG:4326, or ``None`` before the
    #: first build. Grows to hold each archive that does not fit it — the mainland
    #: and Rapa Nui together, after which nothing in this dataset is outside it.
    covered: str | None = None

    @classmethod
    def beside(cls, staging_table: str) -> LookupParts:
        """The names to use next to ``staging_table``."""
        return cls(boundary=f"{staging_table}_boundary_parts",
                   time_zone=f"{staging_table}_time_zone_parts")

    def __iter__(self) -> typing.Iterator[str]:
        """The two table names, for dropping them."""
        return iter((self.boundary, self.time_zone))


def build_lookup_parts(session: Session, staging_table: str, parts: LookupParts,
                       boundary_provider_id: int | None,
                       logger: logging.Logger) -> None:
    """Cut the countries and zones the staged points could be in into small pieces.

    Called once per archive, before any of its seasons is written; it does the work
    only when the pieces it already has cannot answer for the points just staged.
    The tables it builds are what :data:`TRANSFORM_SQL` looks points up in — see
    :data:`BOUNDARY_PARTS_SQL` for what they are worth.

    An empty ``boundary_provider_id`` — the boundaries were never imported — builds
    the table empty rather than skipping it, so the transform has something to join
    to and fires simply come out with no country, which is what happened before.
    """
    extent = session.scalar(text(STAGED_EXTENT_SQL.format(staging_table=staging_table,
                                                          snap=EXTENT_SNAP_DEGREES)))
    if extent is None:
        logger.debug("Nothing staged to look up; leaving the lookup tables alone")
        if parts.covered is not None:
            return
        extent = "POLYGON EMPTY"

    if parts.covered is not None:
        if session.scalar(text(EXTENT_COVERED_SQL),
                          {"covered": parts.covered, "extent": extent}):
            logger.debug("Reusing the lookup pieces already cut for %s", parts.covered)
            return
        extent = session.scalar(text(EXTENT_UNION_SQL),
                                {"covered": parts.covered, "extent": extent})

    for name in parts:
        session.execute(text(f"DROP TABLE IF EXISTS {name}"))
    session.execute(text(BOUNDARY_PARTS_SQL.format(
        parts_table=parts.boundary, max_vertices=SUBDIVIDE_VERTICES,
    )), {"boundary_provider_id": boundary_provider_id, "extent": extent})
    session.execute(text(TIME_ZONE_PARTS_SQL.format(
        parts_table=parts.time_zone, max_vertices=SUBDIVIDE_VERTICES,
    )), {"extent": extent})
    for name in parts:
        session.execute(text(PARTS_INDEX_SQL.format(parts_table=name)))
        session.execute(text(f"ANALYZE {name}"))
    parts.covered = extent

    logger.debug("Cut %d boundary piece(s) and %d time zone piece(s) to look points up in",
                 session.scalar(text(f"SELECT count(*) FROM {parts.boundary}")),
                 session.scalar(text(f"SELECT count(*) FROM {parts.time_zone}")))


def transform(session: Session, provider_id: int, parts: LookupParts,
              staging_table: str, source_srid: int, season: int) -> Audit:
    """Map the staged rows of one season onto the model."""
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        boundary_parts=parts.boundary,
        time_zone_parts=parts.time_zone,
        trimmed=TRIMMED_CHARS,
        season_filter=season_filter([season]),
        reporter=REPORTER_SQL.format(trimmed=TRIMMED_CHARS),
        region_code=ADMIN_CODE_SQL.format(column="codreg", width=2, trimmed=TRIMMED_CHARS),
        province_code=ADMIN_CODE_SQL.format(column="codprov", width=3,
                                            trimmed=TRIMMED_CHARS),
        commune_code=ADMIN_CODE_SQL.format(column="codcom", width=5,
                                           trimmed=TRIMMED_CHARS),
        utm_easting=UTM_COORDINATE_SQL.format(column="utm_e", trimmed=TRIMMED_CHARS),
        utm_northing=UTM_COORDINATE_SQL.format(column="utm_n", trimmed=TRIMMED_CHARS),
        utm_zone=UTM_ZONE_SQL.format(trimmed=TRIMMED_CHARS),
        utm_band=UTM_BAND_SQL.format(trimmed=TRIMMED_CHARS),
        mainland_srid=chile_conaf.SOURCE_SRID_MAINLAND,
        easter_srid=chile_conaf.SOURCE_SRID_EASTER,
    )
    parameters = {
        "provider_id": provider_id,
        "fallback_time_zone": chile_conaf.DEFAULT_TIME_ZONE,
        "seasons": [season],
        "season_label": f"{season}-{season + 1}",
        "season_start_month": chile_conaf.SEASON_START_MONTH,
        "source_srid": source_srid,
        "precision_minute": chile_conaf.PRECISION_MINUTE,
        "precision_day": chile_conaf.PRECISION_DAY,
        "precision_season": chile_conaf.PRECISION_SEASON,
    }
    return Audit.from_row(session.execute(text(statement), parameters).one())


# --------------------------------------------------------------------------
# Importing an archive
# --------------------------------------------------------------------------

def archive_season(archive: Path) -> int | None:
    """The season an archive's name says it is for, for use when a row's is unreadable.

    ``if_temporada_2010_2011.rar`` and ``if_magnitud_islapascua_2024_2025.rar`` both
    give 2010 and 2024 respectively. ``None`` when the name carries no such pair,
    in which case a row with an unreadable ``TEMPORADA`` is skipped rather than
    guessed at.
    """
    match = _ARCHIVE_SEASON.search(archive.stem)
    if match is None:
        return None
    first, second = int(match.group(1)), int(match.group(2))
    return first if second == first + 1 else None


@contextmanager
def exclusive_run(engine: Engine, staging_table: str,
                  logger: logging.LoggerAdapter) -> typing.Iterator[None]:
    """Hold the staging table against a second run, for one archive.

    Raises
    ------
    RuntimeError
        If another import already holds it. The second run is refused outright
        rather than made to wait: it would be waiting on a table the first run is
        about to drop.

    Notes
    -----
    The same guard, and the same reasoning, as
    :func:`src.apps.imports.wildfires.canada_nfdb.import_wildfires.exclusive_run`.
    The staged table is one fixed name in one schema and ``ogr2ogr -overwrite``
    drops and recreates it outside any transaction this application controls, so
    two runs destroy each other: the second one's load replaces the table the first
    is walking season by season, and the first then writes one archive's fires under
    another archive's season — after having deleted the season it was replacing.

    The lock is keyed on the table's name, so two runs given different
    ``--staging-table`` values proceed in parallel quite happily. That is what a user
    importing the mainland and the Easter Island archives at once should do, and
    with 23 archives to get through it is worth doing.

    The connection is held open for the whole block rather than committed and
    returned to the pool. A session-level advisory lock belongs to the *connection*
    that took it, and a ``Session`` releases its connection on commit — so a version
    of this that committed would unlock from whichever connection the pool happened
    to hand back, leaving the real lock held until the process exited.
    """
    key = zlib.crc32(staging_table.encode("utf-8")) % 2**31
    with engine.connect() as connection:
        held = connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :key)"),
            {"namespace": STAGING_LOCK_NAMESPACE, "key": key},
        ).scalar()
        if not held:
            raise RuntimeError(
                f"another import is already running against {staging_table}. Two runs "
                f"share one staging table and would destroy each other's — the second "
                f"one's load replaces the table the first is reading season by season. "
                f"Wait for it to finish, or pass --staging-table to give this run one of "
                f"its own"
            )
        logger.debug("Holding the staging lock on %s", staging_table)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": STAGING_LOCK_NAMESPACE, "key": key},
            )


def assert_season_survived(season: int, audit: Audit, staging_table: str) -> None:
    """Refuse to commit a season the staged table stopped holding rows for.

    Raises
    ------
    RuntimeError
        If the season was staged with rows and the transform found none.

    Notes
    -----
    The second half of the guard :func:`exclusive_run` is the first half of, and the
    reason it is worth having anyway: this season's rows were counted while the lock
    was held, and if they have vanished by the time the transform runs then something
    replaced the staging table underneath it — a second run, or a hand-run
    ``ogr2ogr``. Having already deleted the season it was about to rewrite, this
    transaction must not commit.

    Raising inside the season's transaction rolls back its ``DELETE`` too, so a run
    that hits this leaves the season exactly as it found it.
    """
    if audit.in_scope == 0 and audit.written == 0:
        raise RuntimeError(
            f"season {season}-{season + 1} was staged but {staging_table} held no rows "
            f"for it by the time it was read. Something replaced the staging table "
            f"during the run; nothing has been committed for this season"
        )


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   parts: LookupParts, logger: logging.Logger) -> Audit:
    """Stage one published archive and write the seasons it holds.

    Notes
    -----
    Staging happens once, then each season is deleted and rewritten in its own
    transaction. A season that fails rolls back alone: the seasons before it stay
    written and the run reports which one stopped it, rather than losing an hour's
    work to one bad row.
    """
    log = common.ArchiveLogger(logger, {"archive": archive.name})
    settings = common.resolve_database_settings(args)
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    total = Audit()

    with archives.archive_datasource(archive, log) as (datasource, layer, shapefile):
        source_srid = archives.archive_grid(shapefile, log)
        with exclusive_run(engine, staging_table, log):
            common.load_staging_table(
                datasource, layer, staging_table, args, settings, log,
                geometry_type="POINT",
                target_srs=f"EPSG:{source_srid}",
                fid_column=STAGING_FID_COLUMN,
                creation_options=STAGING_CREATION_OPTIONS,
            )

            with Session(engine) as session:
                normalise_staging_columns(session, staging_table, log)
                session.execute(text(f"ANALYZE {staging_table}"))
                mark_corrupt(session, staging_table, log)
                resolve_seasons(session, staging_table, archive_season(archive), log)
                resolve_dates(session, staging_table, log)
                upsert_causes(session, staging_table, log)
                archives.check_extent(session, staging_table, source_srid, log)
                build_lookup_parts(session, staging_table, parts,
                                   boundary_provider_id, log)
                seasons = staged_seasons(session, staging_table, args.season)
                session.commit()

            if not seasons:
                log.warning("No season in this archive matches the filter; nothing to do")
            else:
                log.info("Staged %s", summarise_seasons(seasons))

            for season in seasons:
                with Session(engine) as session:
                    delete_seasons(session, [season], source_srid)
                    audit = transform(session, provider_id, parts,
                                      staging_table, source_srid, season)
                    assert_season_survived(season, audit, staging_table)
                    if args.dry_run:
                        session.rollback()
                        log.info("%d-%d: would write %d fire(s) (dry run)",
                                 season, season + 1, audit.written)
                    else:
                        session.commit()
                        log.info("%d-%d: wrote %d fire(s)",
                                 season, season + 1, audit.written)
                    total = total + audit

            with Session(engine) as session:
                if not args.keep_staging:
                    common.drop_staging_table(session, staging_table, log)
                session.commit()

    return total


def report(total: Audit, logger: logging.Logger) -> None:
    """Log what the run did, in the order a reader wants to know it."""
    logger.info("Read %d published record(s), wrote %d fire(s)",
                total.in_scope, total.written)
    logger.info("Start dates: %d to the minute, %d to the day, %d to the season only",
                total.with_time, total.with_day, total.season_only)
    if total.season_only:
        logger.warning("%d fire(s) (%.1f%%) have no published start and are dated to "
                       "1 July of their season. Filter on date_time_precision before "
                       "computing anything about months, hours or durations",
                       total.season_only,
                       100.0 * total.season_only / max(total.written, 1))
    logger.info("End dates: %d published", total.with_end)
    if total.end_before_start:
        logger.warning("%d fire(s) publish an end before their start; both are stored "
                       "as published", total.end_before_start)
    if total.area_mismatch:
        logger.warning("%d fire(s) have subtotals that do not sum to their published "
                       "total; area_totals_agree is false on those rows",
                       total.area_mismatch)
    if total.no_cause:
        logger.info("%d fire(s) publish no cause at all", total.no_cause)
    if total.no_time_zone:
        logger.warning("%d fire(s) matched no time zone area and are dated in %s",
                       total.no_time_zone, chile_conaf.DEFAULT_TIME_ZONE)


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import CONAF Chilean seasonal fire reports into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Re-importing replaces the seasons "
               "it reads. Database settings not given here are read from the environment "
               "(.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path, metavar="DIR",
                        help="import every archive in this directory, in name order")
    source.add_argument("-s", "--shapefile", type=Path, nargs="+", metavar="PATH",
                        help="import these archives: a .rar, a .zip, a directory or a .shp")

    parser.add_argument("-y", "--season", type=int, action="append", metavar="YEAR",
                        help="import only this season, named by its first year (2022 for "
                             "2022-2023); may be repeated. Read from the data's own "
                             "TEMPORADA, not from the file name")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would "
                             "have been imported")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def find_archives(directory: Path) -> list[Path]:
    """Every published archive in ``directory``, in name order.

    Name order is season order for this archive — ``if_temporada_2010_2011`` sorts
    before ``if_temporada_2011_2012`` — which is what makes a partial run easy to
    resume and a log easy to read.
    """
    found = sorted(path for path in directory.iterdir()
                   if path.suffix.lower() in (".rar", ".zip", ".shp"))
    if not found:
        found = sorted(path for path in directory.iterdir() if path.is_dir())
    return found


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> Audit:
    """Import the archives against ``engine``, returning the totals."""
    common.require_tables(engine, ["wildfire", "ignition", "conaf_wildfire",
                                   "conaf_ignition", "conaf_fire_cause",
                                   "conaf_magnitud_wildfire", "admin_boundary",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, chile_conaf.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, chile_conaf.PROVIDER_NAME, chile_conaf.PROVIDER_PRODUCT,
            chile_conaf.PROVIDER_FULL_NAME, chile_conaf.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    archive_paths = (find_archives(args.directory) if args.directory
                     else list(args.shapefile))
    if not archive_paths:
        raise RuntimeError(f"no archive found in {args.directory}")
    logger.info("Importing %d archive(s)", len(archive_paths))

    total = Audit()
    # Cut for the first archive that needs them, reused by every archive after it,
    # and dropped however the run ends — see :class:`LookupParts`.
    parts = LookupParts.beside(f"{args.staging_schema}.{args.staging_table}")
    try:
        for archive in archive_paths:
            total = total + import_archive(archive, engine, args, provider_id,
                                           boundary_provider_id, parts, logger)
    finally:
        if not args.keep_staging:
            with Session(engine) as session:
                for name in parts:
                    common.drop_staging_table(session, name, logger)
                session.commit()

    with Session(engine) as session:
        if not args.dry_run:
            report_unreconciled_causes(session, logger)
    report(total, logger)
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("conaf-import")

    for path in ([args.directory] if args.directory else args.shapefile):
        if not path.exists():
            logger.error("Not found: %s", path)
            return 1

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        import_wildfires(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Import failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
