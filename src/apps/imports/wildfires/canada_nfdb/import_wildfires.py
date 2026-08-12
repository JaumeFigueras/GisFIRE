#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Canadian National Fire Database agency fire points.

One command over the published archive::

    python3 -m src.apps.imports.wildfires.canada_nfdb.import_wildfires \\
        -s /path/to/NFDB_point_shp.zip

One zipped shapefile — 1.1 GB of it, almost all in the ``.dbf`` — holding **448,602
fire points** filed by thirteen provincial, territorial and Parks Canada agencies
over 1930-2025. **195,240 of them are natural-cause**, which makes this the largest
lightning-attributable set in GisFIRE and the reason the archive is worth importing
at all.

Each published row becomes two: a
:class:`~src.providers.canada_nfdb.wildfire.NfdbWildfire` for what the agency filed
and a :class:`~src.providers.canada_nfdb.ignition.NfdbIgnition` for where. That is
the EGIF and Greek shape, and it is what this dataset is — a report with a point,
never a perimeter. The Canadian perimeters are
:mod:`src.apps.imports.wildfires.canada_nbac.import_wildfires`'s to import, into a
provider of their own.

What the import refuses, and why each
--------------------------------------

The published summary is unusually frank — *"the data contained in the CNFDB are not
complete nor are they without error. Locations are approximate."* — and the import
takes it at its word. Four filters, each counted and reported:

**Before 1973.** :data:`~src.providers.canada_nfdb.FIRST_YEAR`, to line the archive
up with NBAC, which the service distributes no earlier year of. About 2% of the
rows, with no perimeter to bind to and no lightning data of that period to attribute
them against. ``--from-year`` moves the cut, and ``--from-year 1930`` takes
everything.

**No year.** 95 rows carry ``YEAR = -999``, the service's sentinel for *not known*.
Kept out by the year cut rather than by a rule of its own, and reported separately so
that the number is visible rather than folded into the cut.

**No report date.** 4,047 rows. ``wildfire.start_date_time`` is ``NOT NULL`` and,
unlike NBAC, this dataset publishes no second date to fall back on — so a row without
one is refused rather than dated to 1 January of its year. Inventing a date here
would put four thousand fires on New Year's Day, which is exactly the artefact that
makes the Portuguese archive hard to reason about.

**A coordinate that is not in Canada.** 244 rows: 154 null or exactly ``(0, 0)`` and
the rest projected metres that have leaked into the published degrees columns — the
published ``LONGITUDE`` minimum is −5,617,700, which is an easting.

The last of these does **not** refuse the fire. A report whose location is unusable
is still a report, so it is stored with a ``NULL`` ``ignition_id`` and no point,
exactly as a Spanish *parte* with no coordinate is. Only the point is dropped.

The published columns are checked against the geometry
--------------------------------------------------------

The shapefile carries ``LATITUDE`` and ``LONGITUDE`` as attributes *and* a projected
geometry, and they can disagree — that is how the 244 bad rows are visible at all.
Neither is stored: the geometry is what becomes the point, and the columns are used
only to test it, which is why :class:`NfdbIgnition` has no coordinate columns of its
own. See :mod:`src.providers.canada_nfdb.ignition`.

The test is :func:`~src.providers.canada_nfdb.is_located` over the published degrees,
plus a bounds check on the reprojected geometry, and a row where the two disagree is
reported: one of them is wrong and the import should not silently prefer either.

A year is the unit, and a year is the step
-------------------------------------------

There is one file rather than 53, but the unit replaced is still a **year**: the
import reads which years the staged data holds and replaces exactly those. So
``--year 2023`` re-imports 2023 alone out of the 1.1 GB archive without touching
anything else, and a re-download of the whole file replaces the whole series.

**And a year is also how much work is done at a time.** The archive is staged once
and then transformed one year per statement, each in a transaction of its own:

.. code-block:: text

   53 year(s) to import: 1973-2025
   [1/53] 1973: imported 4392 fire(s) in 3s
   [2/53] 1974: imported 5203 fire(s) in 3s
   ...

This was one statement over the whole archive, which is the better shape on paper —
one pass, one plan, one transaction — and it does not survive the real data. The
mapping materialises the row set six times over (see :data:`TRANSFORM_SQL`), and at
380,000 rows carrying a geometry each that is enough to take a machine to the OOM
killer, which is where a 1.1 GB import that reports nothing and stores nothing ends
up. **A run that finishes slower is worth any number of runs that do not finish**,
and it is the same trade the burnt-area reports make for the same reason — see
:mod:`src.apps.statistics.wildfires.canada_nbac.wildfire_statistics`.

Per year it is a few thousand rows at a time, released between statements, with a
year count to watch instead of an hour of silence.

.. note::

   The shapefile is still read **once**. It does not have to be read per year: the
   staged table is already in PostgreSQL, indexed on nothing but read year by year,
   and re-running ``ogr2ogr`` 53 times over a 1.1 GB archive would cost far more than
   it saved. What was too big was never the load — it was the transform.

Nothing about the figures changes. Every count in the summary is a count over a
partition of the staged rows, so the totals are what one pass would have reported;
:class:`Audit` adds them up.

What does change is what an interruption leaves behind. **Each year is atomic, and no
longer the whole run**: a run killed at year 31 leaves the first thirty years imported
and the rest untouched, where before it left nothing at all. That is a feature and not
a hazard, because a year is exactly what ``--year`` picks the run back up by — and
because the alternative, on this archive, was a run that never reached a commit.

``--dry-run`` does all the work and rolls back each year in turn, so it still writes
nothing.

One run at a time
^^^^^^^^^^^^^^^^^

The load is the same ``ogr2ogr -overwrite`` it always was, and it drops and recreates
the staged table outside any transaction this application controls. With the run now
lasting minutes rather than being one statement, **two overlapping runs destroy each
other**: the second one's load replaces the table the first is walking, so the first
imports nothing into every year it has not yet reached — having already deleted those
years — and then drops the table out from under the second one's ``COPY``.

So a run takes an advisory lock on the staged table for its whole length and a second
one is refused with a message rather than queued (:func:`exclusive_run`), and no year
is committed if its staged rows have gone missing (:func:`assert_year_survived`). The
first stops the collision; the second means that if one happens anyway, the year keeps
the fires it had instead of being emptied in silence.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import typing
import zlib

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.providers import canada_nfdb

#: Default name of the staging table ``ogr2ogr`` loads the archive into.
DEFAULT_STAGING_TABLE = "nfdb_points"

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: The serial key GDAL puts on the staging table.
STAGING_FID_COLUMN = "ogc_fid"

#: Index built on the staged ``year`` before the per-year loop starts.
#:
#: The loop reads one year per statement, so the column it filters by is worth an
#: index; ogr2ogr builds one on the geometry and nothing else. Unqualified, because
#: an index name is resolved in the schema of the table it is created on.
STAGING_YEAR_INDEX = "ix_staging_nfdb_points_year"

#: Namespace for the advisory lock one run holds against another. Arbitrary, and only
#: has to differ from whatever else in this database takes advisory locks.
STAGING_LOCK_NAMESPACE = 0x4E464442  # "NFDB"

#: Layer creation options passed to ``ogr2ogr`` on top of the shared ones.
#:
#: ``PRECISION=NO`` for the reason the sibling imports need it: ``LATITUDE`` and
#: ``LONGITUDE`` are declared ``Real (19.11)``, and a ``numeric(19,11)`` has eight
#: digits before the point where the leaked easting −5,617,700 has seven. It fits, but
#: only just, and the declared widths are fiction throughout.
STAGING_CREATION_OPTIONS = ["PRECISION=NO"]

#: Every attribute the mapping reads, with the PostgreSQL type it needs, named as
#: ``ogr2ogr`` lands it.
STAGING_COLUMNS = {
    "nfdbfireid": "text",
    "src_agency": "text",
    "nat_park": "text",
    "fire_id": "text",
    "firename": "text",
    "latitude": "double precision",
    "longitude": "double precision",
    "year": "integer",
    "rep_date": "date",
    "attk_date": "date",
    "out_date": "date",
    "size_ha": "double precision",
    "fire_type": "text",
    "response": "text",
    "protzone": "text",
    "prescribed": "text",
    "more_info": "text",
    "cfs_note1": "text",
    "cfs_note2": "text",
    "acq_date": "date",
    "cause": "text",
    "cause2": "text",
}

#: The loaded types each declared type will accept without a conversion.
#:
#: ``integer`` is tight here for the NBAC reason: ``YEAR`` is compared against the
#: year cut and stored in an integer column, and a ``double precision`` that arrived
#: as ``-999.0`` should be converted once here rather than cast in three places.
COMPATIBLE_TYPES = {
    "integer": {"integer", "bigint", "smallint"},
    "double precision": {"double precision", "real", "numeric", "integer", "bigint",
                         "smallint"},
    "date": {"date", "timestamp without time zone", "timestamp with time zone"},
    "text": {"text", "character varying", "character"},
}

#: The characters trimmed off every published text attribute before it is read.
TRIMMED_CHARS = r"E' \t\r\n'"

#: Canada's extent on EPSG:3978, in metres, widened by a margin. The geometry-side
#: half of the location test; :func:`~src.providers.canada_nfdb.is_located` is the
#: degrees-side half.
PLAUSIBLE_EXTENT = (-2_600_000.0, -1_100_000.0, 3_200_000.0, 4_400_000.0)

#: How the published ``PRESCRIBED`` reads as a boolean, as SQL.
#:
#: The Python rule is :func:`~src.providers.canada_nfdb.is_prescribed` and this has
#: to agree with it: anything not a recognised affirmative is **false**, blanks
#: included. See that function for why the conservative direction is the right one.
PRESCRIBED_SQL = (
    "lower(btrim(coalesce(staging.prescribed, ''), {trimmed})) = ANY(:prescribed_true)"
)

#: A published ``PRESCRIBED`` that is neither a recognised yes nor a recognised no.
#:
#: Stored as false either way; counted so that a spelling the agencies start writing
#: is noticed rather than absorbed.
UNRECOGNISED_PRESCRIBED_SQL = """
SELECT count(*) FROM {staging_table} AS staging
WHERE NULLIF(btrim(coalesce(staging.prescribed, ''), {trimmed}), '') IS NOT NULL
  AND lower(btrim(staging.prescribed, {trimmed})) <> ALL(:prescribed_true)
  AND lower(btrim(staging.prescribed, {trimmed})) <> ALL(:prescribed_false)
"""

#: The years the staged archive holds rows in, after the year cut and ``--year``.
#:
#: These are the steps the import walks, one transaction each, so the condition here
#: has to be **exactly** the one :data:`TRANSFORM_SQL`'s ``cleaned`` applies. It
#: deliberately does not ask for a report date, although a row without one cannot
#: become a fire: a year whose rows are all unusable is still a year the staged archive
#: holds, and it has to be walked for two reasons — its rows have to reach the counts
#: that report why they were dropped, and replacing a year has to be able to replace it
#: with nothing. A stricter condition here would make the summary quietly under-count
#: and would leave a year that has become empty upstream still populated here.
STAGED_YEARS_SQL = """
SELECT DISTINCT staging.year AS year
FROM {staging_table} AS staging
WHERE staging.year IS NOT NULL
  AND staging.year >= :from_year
  AND ({year_filter})
ORDER BY year
"""

#: Removes the fires of the years about to be re-imported, and their points.
#:
#: One statement, for the reason the sibling imports give: the fires reference the
#: points and the child tables reference their parents, so no order of separate
#: statements is safe while inside one statement the foreign keys are checked once at
#: the end against a consistent final state.
DELETE_YEARS_SQL = """
WITH doomed AS (
    SELECT id, ignition_id FROM nfdb_wildfire WHERE year = ANY(:years)
),
removed_child AS (
    DELETE FROM nfdb_wildfire WHERE id IN (SELECT id FROM doomed) RETURNING id
),
removed_parent AS (
    DELETE FROM wildfire WHERE id IN (SELECT id FROM removed_child) RETURNING id
),
removed_ignition_child AS (
    DELETE FROM nfdb_ignition
    WHERE id IN (SELECT ignition_id FROM doomed WHERE ignition_id IS NOT NULL)
    RETURNING id
)
DELETE FROM ignition WHERE id IN (SELECT id FROM removed_ignition_child)
"""

#: How many of the fires about to be replaced are linked to by an NBAC perimeter.
#:
#: The link lives on ``nbac_wildfire`` and points this way, so replacing a year here
#: leaves a dangling reference — which the foreign key would refuse. Asked up front so
#: that the run says what the problem is instead of dying on a constraint.
LINKED_SQL = """
SELECT count(*) FROM nbac_wildfire
WHERE nfdb_wildfire_id IN (SELECT id FROM nfdb_wildfire WHERE year = ANY(:years))
"""

#: Maps **one year** of the staged archive onto the three tables of the model.
#:
#: One statement, and one year of rows: it is run once per year rather than once over
#: the archive, and that is not a detail. Six of its CTEs are ``MATERIALIZED``, so the
#: row set — every published attribute plus a geometry — is held in memory several
#: times over at once. Over 380,000 rows that is enough to be killed for; over a year's
#: few thousand it is nothing, and it is released when the statement ends. See the
#: module docstring.
#:
#: ``MATERIALIZED`` is not the problem and is not negotiable: ``numbered`` calls
#: ``nextval`` once per row, and a CTE the planner is free to inline could call it
#: again for every reference, handing the same row two different keys.
#:
#: The CTEs, in order:
#:
#: ``cleaned``
#:     Every text attribute trimmed, an all-whitespace value becoming ``NULL``, the
#:     prescribed flag resolved, and the year cut and ``--year`` applied.
#: ``usable``
#:     The rows that can become a fire: a year, a report date, an agency and a cause.
#:     Counted, so the four filters are visible separately in the summary.
#: ``located``
#:     Adds ``has_point``: whether the published degrees are inside Canada **and**
#:     the geometry is too. Both halves, because they can disagree — that is what the
#:     244 bad rows look like — and a disagreement is reported rather than resolved.
#: ``numbered``
#:     Keys drawn from both sequences up front. The ignition key is drawn only for the
#:     rows that will have one, so the two sequences advance by different amounts.
#: ``zoned``
#:     Zone and country from the point, for the rows that have one. A fire with no
#:     point gets neither and falls back to the provider's default zone — Canada spans
#:     six, so that is a real approximation and not a formality.
#: ``ins_ignition`` / ``ins_nfdb_ignition``
#:     The point, in EPSG:4326 on the generic row and EPSG:3978 as published on the
#:     provider one.
#: ``ins_wildfire`` / ``written``
#:     The fire, linked to its point where there is one.
TRANSFORM_SQL = """
WITH cleaned AS MATERIALIZED (
    SELECT NULLIF(btrim(staging.nfdbfireid, {trimmed}), '') AS nfdb_fire_id,
           NULLIF(btrim(staging.fire_id, {trimmed}), '') AS agency_fire_id,
           NULLIF(btrim(staging.firename, {trimmed}), '') AS fire_name,
           NULLIF(btrim(staging.src_agency, {trimmed}), '') AS src_agency,
           NULLIF(btrim(staging.nat_park, {trimmed}), '') AS nat_park,
           staging.year AS year,
           staging.size_ha AS size_ha,
           upper(NULLIF(btrim(staging.cause, {trimmed}), '')) AS fire_cause,
           upper(NULLIF(btrim(staging.cause2, {trimmed}), '')) AS fire_cause_detail,
           NULLIF(btrim(staging.fire_type, {trimmed}), '') AS fire_type,
           NULLIF(btrim(staging.response, {trimmed}), '') AS response,
           NULLIF(btrim(staging.protzone, {trimmed}), '') AS protection_zone,
           {prescribed} AS prescribed,
           staging.rep_date AS report_date,
           staging.attk_date AS attack_date,
           staging.out_date AS out_date,
           staging.acq_date AS acquisition_date,
           NULLIF(btrim(staging.more_info, {trimmed}), '') AS more_info,
           NULLIF(btrim(staging.cfs_note1, {trimmed}), '') AS cfs_note1,
           NULLIF(btrim(staging.cfs_note2, {trimmed}), '') AS cfs_note2,
           staging.latitude AS latitude,
           staging.longitude AS longitude,
           staging.geom AS geom
    FROM {staging_table} AS staging
    WHERE staging.year IS NOT NULL
      AND staging.year >= :from_year
      AND ({year_filter})
),
usable AS MATERIALIZED (
    SELECT * FROM cleaned
    WHERE cleaned.report_date IS NOT NULL
      AND cleaned.src_agency IS NOT NULL
      AND cleaned.fire_cause = ANY(:fire_causes)
),
located AS MATERIALIZED (
    SELECT usable.*,
           (usable.longitude BETWEEN :min_lon AND :max_lon
            AND usable.latitude BETWEEN :min_lat AND :max_lat) AS degrees_ok,
           (usable.geom IS NOT NULL
            AND ST_X(usable.geom) BETWEEN :min_x AND :max_x
            AND ST_Y(usable.geom) BETWEEN :min_y AND :max_y) AS geometry_ok
    FROM usable
),
flagged AS MATERIALIZED (
    SELECT located.*,
           (located.degrees_ok AND located.geometry_ok) AS has_point
    FROM located
),
numbered AS MATERIALIZED (
    SELECT nextval(pg_get_serial_sequence('wildfire', 'id')) AS wildfire_id,
           CASE WHEN flagged.has_point
                THEN nextval(pg_get_serial_sequence('ignition', 'id'))
                ELSE NULL END AS ignition_id,
           flagged.*
    FROM flagged
),
zoned AS MATERIALIZED (
    SELECT numbered.*,
           ST_Transform(numbered.geom, 4326) AS point_4326,
           zone.name AS time_zone,
           country.id AS admin_boundary_id
    FROM numbered
    LEFT JOIN LATERAL (
        SELECT time_zone.name
        FROM time_zone
        WHERE numbered.has_point
          AND ST_Contains(time_zone.geometry, ST_Transform(numbered.geom, 4326))
        LIMIT 1
    ) AS zone ON TRUE
    LEFT JOIN LATERAL (
        SELECT boundary.id
        FROM admin_boundary AS boundary
        WHERE numbered.has_point
          AND boundary.data_provider_id = :boundary_provider_id
          AND boundary.level = 0
          AND ST_Contains(boundary.geometry, ST_Transform(numbered.geom, 4326))
        LIMIT 1
    ) AS country ON TRUE
),
ins_ignition AS (
    INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                          admin_boundary_id)
    SELECT zoned.ignition_id,
           'nfdb_ignition',
           :provider_id,
           zoned.point_4326,
           (zoned.report_date::timestamp)
               AT TIME ZONE COALESCE(zoned.time_zone, :fallback_time_zone),
           zoned.time_zone,
           zoned.admin_boundary_id
    FROM zoned WHERE zoned.has_point
    RETURNING id
),
ins_nfdb_ignition AS (
    INSERT INTO nfdb_ignition (id, nfdb_fire_id, year, src_agency, geometry_lambert)
    SELECT zoned.ignition_id, zoned.nfdb_fire_id, zoned.year, zoned.src_agency,
           ST_Force2D(zoned.geom)
    FROM zoned
    JOIN ins_ignition ON ins_ignition.id = zoned.ignition_id
    RETURNING id
),
ins_wildfire AS (
    INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                          time_zone, perimeter, admin_boundary_id)
    SELECT zoned.wildfire_id,
           'nfdb_wildfire',
           :provider_id,
           (zoned.report_date::timestamp)
               AT TIME ZONE COALESCE(zoned.time_zone, :fallback_time_zone),
           CASE WHEN zoned.out_date IS NULL THEN NULL
                ELSE (zoned.out_date::timestamp)
                         AT TIME ZONE COALESCE(zoned.time_zone, :fallback_time_zone)
           END,
           zoned.time_zone,
           -- NULL, and always: the agencies publish a location, not a shape. The
           -- Canadian perimeters are NBAC's and belong to a provider of their own.
           NULL,
           zoned.admin_boundary_id
    FROM zoned
    RETURNING id
),
written AS (
    INSERT INTO nfdb_wildfire (id, nfdb_fire_id, agency_fire_id, fire_name, src_agency,
                               nat_park, year, size_ha, fire_cause, fire_cause_detail,
                               fire_type, response, protection_zone, prescribed,
                               report_date, attack_date, out_date, acquisition_date,
                               more_info, cfs_note1, cfs_note2, ignition_id)
    SELECT zoned.wildfire_id, zoned.nfdb_fire_id, zoned.agency_fire_id, zoned.fire_name,
           zoned.src_agency, zoned.nat_park, zoned.year, zoned.size_ha, zoned.fire_cause,
           zoned.fire_cause_detail, zoned.fire_type, zoned.response,
           zoned.protection_zone, zoned.prescribed, zoned.report_date, zoned.attack_date,
           zoned.out_date, zoned.acquisition_date, zoned.more_info, zoned.cfs_note1,
           zoned.cfs_note2, zoned.ignition_id
    FROM zoned
    JOIN ins_wildfire ON ins_wildfire.id = zoned.wildfire_id
    RETURNING id
)
SELECT (SELECT count(*) FROM cleaned) AS in_scope,
       (SELECT count(*) FROM usable) AS usable,
       (SELECT count(*) FROM cleaned WHERE report_date IS NULL) AS no_report_date,
       (SELECT count(*) FROM flagged WHERE has_point) AS with_point,
       (SELECT count(*) FROM flagged WHERE NOT has_point) AS without_point,
       (SELECT count(*) FROM flagged WHERE degrees_ok <> geometry_ok) AS disagreeing,
       (SELECT count(*) FROM flagged WHERE fire_cause = :cause_natural) AS natural_cause,
       (SELECT count(*) FROM written) AS written
"""


# --------------------------------------------------------------------------
# Staging checks
# --------------------------------------------------------------------------

def normalise_staging_columns(session: Session, staging_table: str,
                              columns: dict[str, str],
                              logger: logging.LoggerAdapter) -> None:
    """Make sure the staged table has the attributes the mapping reads, typed usably.

    Raises
    ------
    RuntimeError
        If the staged layer publishes none of an attribute the mapping needs.
    """
    schema, _, table = staging_table.rpartition(".")
    loaded = {
        name: data_type
        for name, data_type in session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table"
        ), {"schema": schema or "public", "table": table}).all()
    }

    missing = [name for name in columns if name not in loaded]
    if missing:
        raise RuntimeError(
            f"the staged layer publishes no {', '.join(missing)}: this is not the NFDB "
            f"point archive, or its attributes have been renamed"
        )

    for name, wanted in columns.items():
        if loaded[name] in COMPATIBLE_TYPES.get(wanted, {wanted}):
            continue
        logger.debug("Converting staged %s from %s to %s", name, loaded[name], wanted)
        session.execute(text(
            f"ALTER TABLE {staging_table} ALTER COLUMN {name} TYPE {wanted} "
            f"USING {name}::{wanted}"
        ))


def check_prescribed(session: Session, staging_table: str,
                     logger: logging.LoggerAdapter) -> int:
    """Report published ``PRESCRIBED`` values that are neither a yes nor a no.

    All of them are stored as ``False`` — see
    :func:`~src.providers.canada_nfdb.is_prescribed` for why the conservative
    direction is right — and this is what stops that being silent. A blank is not
    unrecognised; it is the normal state of the column.
    """
    statement = UNRECOGNISED_PRESCRIBED_SQL.format(staging_table=staging_table,
                                                   trimmed=TRIMMED_CHARS)
    unrecognised = session.scalar(text(statement), {
        "prescribed_true": sorted(canada_nfdb.PRESCRIBED_TRUE),
        "prescribed_false": sorted(canada_nfdb.PRESCRIBED_FALSE),
    }) or 0
    if unrecognised:
        logger.warning(
            "%d row(s) publish a PRESCRIBED value that is neither a recognised yes nor "
            "a recognised no; all are stored as not prescribed. Add the spelling to "
            "src.providers.canada_nfdb.PRESCRIBED_TRUE or PRESCRIBED_FALSE",
            unrecognised,
        )
    return unrecognised


# --------------------------------------------------------------------------
# The years
# --------------------------------------------------------------------------

def year_filter(years: list[int] | None) -> str:
    """The ``WHERE`` fragment applying ``--year``, or one that is always true."""
    if not years:
        return "TRUE"
    return "staging.year = ANY(:years)"


def staged_years(session: Session, staging_table: str, from_year: int,
                 years: list[int] | None) -> list[int]:
    """The years the staged archive holds rows in — the steps the import walks.

    One statement per year follows, so this is the list the whole run is paced by. See
    :data:`STAGED_YEARS_SQL` for why it counts a year whose rows are all unusable.
    """
    statement = STAGED_YEARS_SQL.format(staging_table=staging_table,
                                        year_filter=year_filter(years))
    parameters: dict[str, object] = {"from_year": from_year}
    if years:
        parameters["years"] = years
    return list(session.scalars(text(statement), parameters).all())


def summarise_years(years: list[int]) -> str:
    """``1973-1975, 1980`` — a list of years compressed to its ranges."""
    if not years:
        return "no year"
    ranges: list[tuple[int, int]] = []
    start = previous = years[0]
    for year in years[1:]:
        if year == previous + 1:
            previous = year
        else:
            ranges.append((start, previous))
            start = previous = year
    ranges.append((start, previous))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def check_not_linked(session: Session, years: list[int]) -> None:
    """Refuse the run if an NBAC perimeter is bound to a fire about to be replaced.

    Raises
    ------
    RuntimeError
        If any perimeter links to one of them. The foreign key would refuse the delete
        anyway; this says why, and what to do about it, instead of surfacing a
        constraint violation from inside a 200-line statement.

    Notes
    -----
    Asked **once, for every year in scope, before the first year is written**, and not
    inside the per-year loop. The loop commits each year as it goes, so a check that
    only reached year 31 when year 31 was already being deleted would leave thirty
    years replaced and the run aborted — which is exactly the half-done state the
    up-front check exists to avoid.
    """
    linked = session.scalar(text(LINKED_SQL), {"years": years}) or 0
    if linked:
        raise RuntimeError(
            f"{linked} NBAC perimeter(s) are bound to fires of the year(s) being "
            f"replaced. Re-importing would leave those links dangling. Clear them "
            f"first — the binding application is what wrote them — and run this again."
        )


def delete_years(session: Session, years: list[int]) -> None:
    """Remove the fires of the years about to be re-imported, and their points.

    Runs in the same transaction as the transform that refills the year, so a year is
    never left deleted-but-not-reimported. :func:`check_not_linked` has already
    established that nothing points at these rows from outside.
    """
    session.execute(text(DELETE_YEARS_SQL), {"years": years})


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Audit:
    """What the transform did, for the summary lines.

    Attributes
    ----------
    in_scope : int
        Rows the year cut and ``--year`` let through.
    usable : int
        Of those, the rows that could become a fire: a report date, an agency and a
        recognised cause.
    no_report_date : int
        Rows dropped for publishing no ``REP_DATE``, counted separately from the rest
        of the unusable because it is the one refusal worth a warning of its own.
    with_point, without_point : int
        Fires whose published coordinate was usable, and fires stored without one.
    disagreeing : int
        Rows whose published degrees and own geometry disagree about being in Canada.
    natural_cause : int
        Fires filed as :data:`~src.providers.canada_nfdb.CAUSE_NATURAL`.
    written : int
        Fires actually stored.

    Notes
    -----
    Every field is a **count over a partition of the staged rows**: the transform now
    runs once per year and no row is in two years, so adding the years' audits gives
    exactly what one pass over the whole archive would have reported. That is what
    :meth:`__add__` is for, and it is the same decomposition argument the burnt-area
    reports rely on to measure a year at a time.

    Frozen, so a total is built by addition rather than by mutating a running tally
    that could quietly be added to twice.
    """

    in_scope: int = 0
    usable: int = 0
    no_report_date: int = 0
    with_point: int = 0
    without_point: int = 0
    disagreeing: int = 0
    natural_cause: int = 0
    written: int = 0

    @classmethod
    def from_row(cls, row) -> Audit:
        """The audit the transform's one row reports."""
        return cls(in_scope=row.in_scope, usable=row.usable,
                   no_report_date=row.no_report_date, with_point=row.with_point,
                   without_point=row.without_point, disagreeing=row.disagreeing,
                   natural_cause=row.natural_cause, written=row.written)

    def __add__(self, other: Audit) -> Audit:
        """The two years' counts, summed field by field."""
        return Audit(**{field.name: getattr(self, field.name) + getattr(other, field.name)
                        for field in fields(self)})


def transform(session: Session, provider_id: int, boundary_provider_id: int | None,
              staging_table: str, from_year: int, years: list[int] | None) -> Audit:
    """Map the staged rows of ``years`` onto the model.

    Called once per year by :func:`import_year`. It still accepts a list, and still
    works over the whole archive if given one — which is what the memory it needs to do
    that made unusable, so nothing does.
    """
    statement = TRANSFORM_SQL.format(
        staging_table=staging_table,
        trimmed=TRIMMED_CHARS,
        year_filter=year_filter(years),
        prescribed=PRESCRIBED_SQL.format(trimmed=TRIMMED_CHARS),
    )
    min_x, min_y, max_x, max_y = PLAUSIBLE_EXTENT
    min_lon, max_lon = canada_nfdb.PLAUSIBLE_LONGITUDE
    min_lat, max_lat = canada_nfdb.PLAUSIBLE_LATITUDE
    parameters: dict[str, object] = {
        "provider_id": provider_id,
        "boundary_provider_id": boundary_provider_id,
        "fallback_time_zone": canada_nfdb.DEFAULT_TIME_ZONE,
        "from_year": from_year,
        "fire_causes": list(canada_nfdb.FIRE_CAUSES),
        "cause_natural": canada_nfdb.CAUSE_NATURAL,
        "prescribed_true": sorted(canada_nfdb.PRESCRIBED_TRUE),
        "min_lon": min_lon, "max_lon": max_lon,
        "min_lat": min_lat, "max_lat": max_lat,
        "min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y,
    }
    if years:
        parameters["years"] = years
    return Audit.from_row(session.execute(text(statement), parameters).one())


# --------------------------------------------------------------------------
# Importing the archive
# --------------------------------------------------------------------------

def load_archive(archive: Path, staging_table: str, args: argparse.Namespace,
                 logger: logging.LoggerAdapter) -> None:
    """Stage the published archive, in the CRS it was published in."""
    datasource, layer = common.shapefile_datasource(archive)
    common.load_staging_table(
        datasource, layer, staging_table, args, common.resolve_database_settings(args),
        logger,
        geometry_type="POINT",
        target_srs=f"EPSG:{canada_nfdb.SOURCE_SRID}",
        fid_column=STAGING_FID_COLUMN,
        creation_options=STAGING_CREATION_OPTIONS,
    )


@contextmanager
def exclusive_run(engine: Engine, staging_table: str,
                  log: logging.LoggerAdapter) -> typing.Iterator[None]:
    """Hold the archive's staging table against a second run, for the whole import.

    Raises
    ------
    RuntimeError
        If another import already holds it. The second run is refused outright rather
        than made to wait: it would be waiting minutes on a table the first run is
        about to drop.

    Notes
    -----
    **This is not a nicety, and the reason it exists is worth stating.** The staged
    table is one fixed name in one schema, and ``ogr2ogr -overwrite`` drops and
    recreates it outside any transaction this application controls. Two runs therefore
    destroy each other: the second one's load replaces the table the first is walking
    year by year, so the first silently imports **nothing** for every year it has not
    yet reached — having already deleted those years — and then drops the table out
    from under the second one's ``COPY``.

    That is not hypothetical. It is what happened on 2026-08-05: one run reported
    ``imported 94480 fire(s) over 1973-2025`` while leaving 1986 onwards empty, and the
    other died with ``relation "staging.nfdb_points" does not exist``.

    A single transaction never really protected against this either — the load has
    always been outside it — but the window used to be seconds and is now the length
    of the whole run. :func:`assert_year_survived` is the second half of the guard: this
    stops the collision, that one refuses to commit anything if it happens anyway.

    A PostgreSQL advisory lock, and not a row in a table: it is released when the
    connection closes, so a killed run leaves nothing to clean up by hand.
    """
    key = zlib.crc32(staging_table.encode("utf-8"))
    with engine.connect() as connection:
        held = connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :key)"),
            {"namespace": STAGING_LOCK_NAMESPACE, "key": key % 2**31},
        ).scalar()
        if not held:
            raise RuntimeError(
                f"another import is already running against {staging_table}. Two runs "
                f"share one staging table and would destroy each other's — the second "
                f"one's load replaces the table the first is reading year by year. Wait "
                f"for it to finish, or pass --staging-table to give this run one of its "
                f"own."
            )
        log.debug("Holding the staging lock on %s", staging_table)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": STAGING_LOCK_NAMESPACE, "key": key % 2**31},
            )


def assert_year_survived(year: int, audit: Audit, staging_table: str) -> None:
    """Refuse to commit a year the staged table stopped holding rows for.

    Raises
    ------
    RuntimeError
        If the year the loop was told to import turned out to have no rows in scope.

    Notes
    -----
    :func:`staged_years` listed this year by reading the staged table, and
    :data:`TRANSFORM_SQL`'s ``cleaned`` applies **exactly** the same condition to the
    same table. So ``in_scope`` cannot legitimately be zero here: a year that is on the
    list has rows, by construction.

    Zero therefore means the staged table changed underneath the run — in practice that
    something reloaded it — and it is the one condition under which continuing is
    actively destructive. The transform runs in the same transaction as the delete that
    emptied the year, so raising here rolls both back and the year keeps the rows it
    had. Without this check the run does the opposite: it deletes the year, writes
    nothing, commits, and reports ``imported 0 fire(s)`` as though that were an answer.
    """
    if audit.in_scope:
        return
    raise RuntimeError(
        f"{year} was listed as staged and then had no rows: {staging_table} changed "
        f"while this run was reading it, which means something reloaded it. Nothing has "
        f"been committed for {year} — its existing fires are untouched — but any "
        f"earlier year of this run has already been replaced. Re-run this import, "
        f"alone, once the other one has finished."
    )


def prepare_staging(session: Session, staging_table: str, args: argparse.Namespace,
                    log: logging.LoggerAdapter) -> list[int]:
    """Ready the staged table for the per-year transforms, and say which years it holds.

    Committed by the caller, and worth committing whatever happens next: the column
    conversions and the statistics are properties of the staged table rather than of
    any one year's import, and every year's statement needs them.
    """
    normalise_staging_columns(session, staging_table, STAGING_COLUMNS, log)
    # The column the loop now filters by, once per year. ogr2ogr indexes nothing but
    # the geometry, so without this every one of the 53 statements reads all 448,602
    # staged rows to find its few thousand. One index build pays for itself several
    # times over and is thrown away with the table.
    session.execute(text(
        f"CREATE INDEX IF NOT EXISTS {STAGING_YEAR_INDEX} ON {staging_table} (year)"
    ))
    # ogr2ogr leaves the table with no statistics at all, and this one has 448,602
    # rows: without it the planner picks nested loops over the spatial joins and the
    # transform never finishes. After the index, so the planner knows about it — and
    # the cost is paid once where the plan it produces is reused by every year.
    session.execute(text(f"ANALYZE {staging_table}"))
    check_prescribed(session, staging_table, log)
    return staged_years(session, staging_table, args.from_year, args.year)


def drop_staging(engine: Engine, staging_table: str, args: argparse.Namespace,
                 log: logging.LoggerAdapter) -> None:
    """Drop the staged table once every year has been imported.

    In a transaction of its own, because the years no longer share one — and skipped
    under ``--dry-run``, where the staged table is most of what there is left to look
    at, as it was when the whole run rolled back.
    """
    if args.keep_staging or args.dry_run:
        return
    with Session(engine) as session:
        common.drop_staging_table(session, staging_table, log)
        session.commit()


def import_year(engine: Engine, args: argparse.Namespace, provider_id: int,
                boundary_provider_id: int | None, staging_table: str,
                year: int) -> Audit:
    """Replace one year, in a transaction of its own.

    The delete and the transform are in the same transaction, so the year is never
    left emptied and unfilled; and the transaction is no larger than that, so the row
    set the mapping materialises is one year's and is released when the statement ends.
    That is the whole point of the loop this belongs to — see the module docstring.
    """
    with Session(engine) as session:
        delete_years(session, [year])
        audit = transform(session, provider_id, boundary_provider_id, staging_table,
                          args.from_year, [year])
        # Before the commit, so that a staged table which changed underneath the run
        # takes the delete down with it rather than leaving the year emptied.
        assert_year_survived(year, audit, staging_table)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    return audit


def import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                   provider_id: int, boundary_provider_id: int | None,
                   logger: logging.Logger) -> int:
    """Stage the archive once, then import it a year at a time.

    Returns the fires stored over every year.
    """
    staging_table = f"{args.staging_schema}.{args.staging_table}"
    log = ArchiveLogger(logger, {"archive": archive.name})

    with exclusive_run(engine, staging_table, log):
        return _import_archive(archive, engine, args, provider_id,
                               boundary_provider_id, staging_table, log)


def _import_archive(archive: Path, engine: Engine, args: argparse.Namespace,
                    provider_id: int, boundary_provider_id: int | None,
                    staging_table: str, log: logging.LoggerAdapter) -> int:
    """The body of :func:`import_archive`, with the staging lock already held.

    Split out so that the lock covers the load as well as the loop — ``ogr2ogr``
    overwrites the staged table, so the load is the destructive half — without an
    indent that would bury the whole import in a ``with``.
    """
    started = time.monotonic()
    load_archive(archive, staging_table, args, log)

    with Session(engine) as session:
        years = prepare_staging(session, staging_table, args, log)
        if years:
            # Before the first year is written, not as each is reached: the years
            # commit one by one, so a refusal discovered halfway would leave half the
            # archive replaced.
            check_not_linked(session, years)
        session.commit()

    if not years:
        log.warning("No fire in scope: the archive holds nothing importable for the "
                    "year(s) asked for")
        drop_staging(engine, staging_table, args, log)
        return 0

    log.info("%d year(s) to import: %s", len(years), summarise_years(years))
    audit = Audit()
    for index, year in enumerate(years, start=1):
        year_started = time.monotonic()
        measured = import_year(engine, args, provider_id, boundary_provider_id,
                               staging_table, year)
        audit += measured
        log.info("[%d/%d] %d: %s%d fire(s) in %.0fs", index, len(years), year,
                 "would have imported " if args.dry_run else "imported ",
                 measured.written, time.monotonic() - year_started)

    drop_staging(engine, staging_table, args, log)

    if audit.no_report_date:
        log.warning("%d row(s) in scope publish no report date and were dropped: this "
                    "dataset has no second date to fall back on, and a fire dated 1 "
                    "January of its year would be an invention", audit.no_report_date)
    unusable = audit.in_scope - audit.usable - audit.no_report_date
    if unusable:
        log.warning("%d further row(s) publish no agency or no recognised cause and "
                    "were dropped", unusable)
    if audit.without_point:
        log.warning("%d fire(s) publish no usable coordinate and were stored without a "
                    "point", audit.without_point)
    if audit.disagreeing:
        log.warning("%d row(s) have published LATITUDE/LONGITUDE that disagree with "
                    "their own geometry about being in Canada; neither is preferred and "
                    "the point was dropped", audit.disagreeing)
    if audit.written:
        log.info("%s%d fire(s) over %s in %.0fs: %d with a point, %d natural-cause",
                 "would have imported " if args.dry_run else "imported ",
                 audit.written, summarise_years(years), time.monotonic() - started,
                 audit.with_point, audit.natural_cause)
    return audit.written


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import NFDB agency fire points for Canada into GisFIRE.",
        epilog="Import the OCHA boundaries and the time zone areas first, so that fires "
               "get a country and a local start time. Re-importing replaces the years it "
               "reads. Database settings not given here are read from the environment "
               "(.env).",
    )
    parser.add_argument("-s", "--shapefile", type=Path, required=True,
                        help="the published NFDB_point_shp.zip, or the .shp inside it")

    parser.add_argument("-y", "--year", type=int, action="append", metavar="YEAR",
                        help="import only this year; may be repeated. Re-imports that "
                             "year alone out of the whole archive")
    parser.add_argument("--from-year", type=int, default=canada_nfdb.FIRST_YEAR,
                        metavar="YEAR",
                        help=f"ignore fires published before this year (default "
                             f"{canada_nfdb.FIRST_YEAR}, where the NBAC perimeters "
                             f"start). Pass 1930 to take the whole archive")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would have "
                             "been imported")

    common.add_database_arguments(parser)
    common.add_staging_arguments(parser, DEFAULT_STAGING_TABLE)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Import the archive against ``engine``, returning the fires written."""
    common.require_tables(engine, ["wildfire", "ignition", "nfdb_wildfire",
                                   "nfdb_ignition", "nbac_wildfire", "admin_boundary",
                                   "time_zone", "data_provider"], logger)
    common.create_staging_schema(engine, args.staging_schema)

    with Session(engine) as session:
        common.check_time_zones(session, logger, canada_nfdb.DEFAULT_TIME_ZONE)
        provider = common.get_or_create_data_provider(
            session, canada_nfdb.PROVIDER_NAME, canada_nfdb.PROVIDER_PRODUCT,
            canada_nfdb.PROVIDER_FULL_NAME, canada_nfdb.PROVIDER_URL, logger,
        )
        boundary_provider = common.find_boundary_provider(session, logger)
        session.commit()
        provider_id = provider.id
        boundary_provider_id = None if boundary_provider is None else boundary_provider.id

    return import_archive(args.shapefile, engine, args, provider_id,
                          boundary_provider_id, logger)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("nfdb-import")

    if not args.shapefile.exists():
        logger.error("Not found: %s", args.shapefile)
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
