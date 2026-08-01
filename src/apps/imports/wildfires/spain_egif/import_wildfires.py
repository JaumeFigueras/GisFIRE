#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Spanish EGIF fire statistics, Excel first and then XML.

One application, two steps, in that order::

    python3 -m src.apps.imports.wildfires.spain_egif.import_wildfires -d /path/to/egif/

**Step 1 reads every ``.xlsx``.** The Excel "resumen" is the only public source
that prints a code *with its label* — ``[213]  Quema de restos agrícolas`` — so it
is what seeds :class:`~src.providers.spain_egif.fire_cause.EgifFireCause` and
:class:`~src.providers.spain_egif.fire_motivation.EgifFireMotivation`. It also carries
the administrative names, which the XML publishes only as numbers.

**Step 2 reads every ``.xml``.** The XML carries what the Excel drops: the INE
municipality code, the *paraje*, the control and response times, the weather, the
cause certainty, the fuel and fire-type codes and — the field the whole exercise
is for — ``diastormenta``, the holdover interval.

The order is not a preference. An XML import into a database whose catalogues
have never been seeded can only store a cause as an integer nobody can read, so
the causes have to come from an Excel export first. Running the steps together,
in one command, is what makes that automatic.

Both steps **upsert on ``numeroparte``**, so the same fire read from both formats
lands on one row, and a re-import of a revised year updates rather than
duplicates. What stops the second step undoing the first is that **each step
writes only the columns its own format publishes** — see
:data:`EXCEL_WILDFIRE_COLUMNS` and :data:`XML_WILDFIRE_COLUMNS`. An Excel
re-import cannot blank the ``municipality_ine_code`` an XML import filled in,
because it never names that column.

One transaction per file
------------------------

A file is read to its end and then committed, so a run interrupted half way
through a 285 MB export leaves the database exactly as it found it. A *fire* that
cannot be stored is a different matter: it is logged with its report number and
the reason, counted, and skipped, and the rest of the file is still committed.
Losing 30,000 good fires to one bad one would be the wrong trade at every scale
this dataset comes in.

What makes a fire unstorable is deliberately short — no report number, no
detection instant (``wildfire.start_date_time`` is ``NOT NULL`` and nothing else
can stand in for it). Everything else is degraded rather than refused: a fire
whose coordinate will not reproject is stored **without an ignition**, which is
the normal state of half the archive, and a fire whose cause
code is not in the catalogue is stored with a null cause.

Progress
--------

Each file gets a :class:`~src.apps.imports.common.ProgressReporter` — a bar on a
terminal, periodic log lines when redirected. The Excel row count is known in
advance (a cheap second pass over the same zip), so those bars carry a percentage
and an estimate; an XML export cannot be counted without parsing it, so its bar
shows the running count and rate instead.

Database settings come from the environment (``.env``, see :mod:`src.settings`);
every one of them can be overridden with a command-line argument. Unlike the
other wildfire importers this one needs no ``ogr2ogr``: both formats are read in
Python and the only geometry work — turning the published easting and northing
into the stored EPSG:4326 point — is done by PostGIS with ``ST_Transform``.
"""

from __future__ import annotations

import argparse
import collections
import logging
import sys
import time

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.imports.common import ArchiveLogger
from src.apps.imports.common import ProgressReporter
from src.apps.imports.wildfires.spain_egif import readers
from src.apps.imports.wildfires.spain_egif.readers import PifRecord
from src.providers import spain_egif
from src.providers import spain_ign

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Fires converted and written per round trip. Large enough that the per-batch
#: statements dominate their own overhead, small enough that the parameter lists
#: stay well inside what psycopg will bind in one executemany.
BATCH_SIZE = 2000

#: How many individually bad fires are logged per file before the rest are only
#: counted. A file that is wrong in some systematic way — the wrong export, a
#: format change — would otherwise write one line per fire and bury the summary
#: that says so.
MAX_REPORTED_PROBLEMS = 20

#: Columns of ``egif_wildfire`` the **Excel** step is responsible for.
#:
#: The administrative names live here and nowhere else: the XML publishes
#: ``idcomunidad``, ``idprovincia`` and ``idmunicipio`` as bare integers and no
#: names at all. ``status`` likewise — the XML has ``idestadopif``, a code this
#: import does not store.
EXCEL_WILDFIRE_COLUMNS = (
    "campaign", "status", "ccaa_name", "province_name", "province_ine_code",
    "municipality_name", "comarca_name", "minor_entity_name",
    "affected_municipality_count", "cause_id", "motivation_id",
    "area_ha_wooded", "area_ha_non_wooded", "area_ha_forest_total",
    "area_ha_agricultural", "area_ha_other_non_forest",
    "wui_affected", "wui_compact", "wui_scattered", "wui_isolated",
    "protected_space_affected", "agricultural_land_affected", "zar_affected",
    "pss_report_number", "ignition_id",
)

#: Columns of ``egif_wildfire`` the **XML** step is responsible for.
#:
#: Deliberately not a superset. It omits every ``*_name`` column and ``status``
#: and ``pss_report_number``, because the XML does not publish them and writing
#: them would mean writing nulls over what step 1 stored. It adds ``egif_id`` and
#: ``municipality_ine_code``, which only the XML has.
XML_WILDFIRE_COLUMNS = (
    "egif_id", "campaign", "province_ine_code", "municipality_ine_code",
    "affected_municipality_count", "cause_id", "motivation_id",
    "area_ha_wooded", "area_ha_non_wooded", "area_ha_forest_total",
    "area_ha_agricultural", "area_ha_other_non_forest",
    "wui_affected", "wui_compact", "wui_scattered", "wui_isolated",
    "protected_space_affected", "agricultural_land_affected", "zar_affected",
    "ignition_id",
)

#: Columns of ``egif_ignition`` each step is responsible for, same rule.
#: ``place_name`` (the *paraje*) and ``datum_code`` are XML-only.
EXCEL_IGNITION_COLUMNS = ("utm_zone", "utm_x", "utm_y", "datum",
                          "start_point_count", "mtn_sheet", "mtn_grid")
XML_IGNITION_COLUMNS = EXCEL_IGNITION_COLUMNS + ("datum_code", "place_name")

#: Everything on ``egif_wildfire_report``. Written by the XML step only — the
#: table exists precisely because the Excel publishes none of it.
REPORT_COLUMNS = (
    "control_date_time", "first_ground_response_date_time",
    "first_aerial_response_date_time", "first_helitransported_response_date_time",
    "first_coordination_response_date_time", "first_notification_from_112",
    "detected_by_code", "started_next_to_other", "responsibility_grade_code",
    "days_since_storm", "cause_investigated_code", "cause_certainty_code",
    "offender_identified_code", "activity_authorisation_code", "day_class_code",
    "weather_station_code", "weather_observation_time", "days_since_rain",
    "max_temperature_celsius", "relative_humidity_percent", "wind_speed_km_h",
    "wind_direction_degrees", "max_severity_level", "fuel_model_codes",
    "fire_type_codes", "start_area_type_codes", "started_next_to_codes",
)

#: The instants that are published as naive local wall-clock and stored as
#: absolute time, resolved against the fire's own zone.
LOCAL_DATETIME_COLUMNS = frozenset({
    "control_date_time", "first_ground_response_date_time",
    "first_aerial_response_date_time", "first_helitransported_response_date_time",
    "first_coordination_response_date_time",
})

#: The keys already stored for a batch of report numbers, from both tables.
#:
#: The ignition is looked up in ``egif_ignition`` by its own report number rather
#: than followed from ``egif_wildfire.ignition_id``, because the two can disagree
#: in a way that matters: a fire imported from an Excel export that published no
#: coordinate has a null ``ignition_id``, and if a later XML import allocated a
#: *new* ignition for it the insert would collide with the unique
#: ``egif_ignition.report_number`` rather than update the row that is already
#: there. Reading both sides independently means an existing row of either kind is
#: always reused.
EXISTING_SQL = """
SELECT report_number, max(wildfire_id) AS wildfire_id, max(ignition_id) AS ignition_id
FROM (
    SELECT report_number, id AS wildfire_id, NULL::integer AS ignition_id
    FROM egif_wildfire WHERE report_number = ANY(:report_numbers)
    UNION ALL
    SELECT report_number, NULL::integer, id
    FROM egif_ignition WHERE report_number = ANY(:report_numbers)
) AS stored
GROUP BY report_number
"""

#: Draws ``:count`` identifiers from a table's own sequence in one round trip.
#: The parent row's key has to be known before the child insert, so ``RETURNING``
#: would come too late — the same reason the ICNF import takes its ids up front.
ALLOCATE_SQL = "SELECT nextval(pg_get_serial_sequence(:table, 'id')) FROM generate_series(1, :count)"

#: The stored point, built from the published easting and northing.
#:
#: ``ST_SetSRID`` tags the pair with the CRS resolved from its own datum and zone
#: — which varies per row, so this cannot be a column type — and ``ST_Transform``
#: reprojects to the EPSG:4326 the model stores. Done in PostGIS rather than in
#: Python so that the transformation is the same one every spatial query in the
#: database will use.
GEOMETRY_SQL = "ST_Transform(ST_SetSRID(ST_MakePoint(:utm_x, :utm_y), :srid), 4326)"

def _local(column: str) -> str:
    """The SQL that resolves a naive published reading against the fire's zone.

    Both exports publish wall-clock local time with no offset, so the instant a
    reading names depends on where the fire was — an hour's difference for the
    Canarian fires. ``AT TIME ZONE`` applied to a ``timestamp`` yields the
    ``timestamptz`` the column stores.

    The ``CAST`` is not decoration. Most of these readings are optional and
    frequently null — only 1,089 fires of 29,926 have a coordination-resource
    arrival — and PostgreSQL cannot infer a bound parameter's type from
    ``AT TIME ZONE`` alone, so an untyped null is rejected outright with
    *could not determine data type of parameter*. Naming the type is also why no
    ``CASE`` is needed around it: ``NULL::timestamp AT TIME ZONE`` is null, which
    is exactly the wanted answer for a fire that was never extinguished.
    """
    return f"CAST(:{column} AS timestamp) AT TIME ZONE :time_zone"


UPSERT_IGNITION_SQL = f"""
INSERT INTO ignition (id, type, data_provider_id, geometry, date_time, time_zone,
                      admin_boundary_id)
VALUES (:ignition_id, 'egif_ignition', :provider_id, {GEOMETRY_SQL},
        {_local('start_date_time')}, :time_zone, :admin_boundary_id)
ON CONFLICT (id) DO UPDATE SET
    geometry = EXCLUDED.geometry,
    date_time = EXCLUDED.date_time,
    time_zone = EXCLUDED.time_zone,
    admin_boundary_id = EXCLUDED.admin_boundary_id,
    updated_at = now()
"""

UPSERT_WILDFIRE_SQL = f"""
INSERT INTO wildfire (id, type, data_provider_id, start_date_time, end_date_time,
                      time_zone, admin_boundary_id)
VALUES (:wildfire_id, 'egif_wildfire', :provider_id,
        {_local('start_date_time')},
        {_local('end_date_time')},
        :time_zone, :admin_boundary_id)
ON CONFLICT (id) DO UPDATE SET
    start_date_time = EXCLUDED.start_date_time,
    end_date_time = EXCLUDED.end_date_time,
    time_zone = EXCLUDED.time_zone,
    admin_boundary_id = EXCLUDED.admin_boundary_id,
    updated_at = now()
"""


def _upsert_sql(table: str, key: str, columns: tuple[str, ...],
                extra: dict[str, str] | None = None,
                touch_updated_at: bool = False) -> str:
    """Build an ``INSERT ... ON CONFLICT (id) DO UPDATE`` over ``columns``.

    ``extra`` maps a column to the SQL expression that produces it, for the ones
    that are not a plain bound parameter — the local datetimes, which need the
    fire's zone applied. Everything else binds by name.

    Only ``columns`` appear in the ``SET``, which is the mechanism behind "each
    step writes only what its format publishes": a column this step does not name
    is not merely left unbound, it is not mentioned, so an existing value survives
    untouched.

    ``touch_updated_at`` adds ``updated_at = now()``, which raw SQL has to do for
    itself — SQLAlchemy's ``onupdate`` is applied by the ORM, and these statements
    go straight to the database. Only ``egif_wildfire_report`` needs it; neither
    ``egif_wildfire`` nor ``egif_ignition`` has the column, their timestamps
    living on the parent rows instead.
    """
    extra = extra or {}
    names = (key, *columns)
    values = ", ".join(extra.get(name, f":{name}") for name in names)
    updates = [f"{name} = EXCLUDED.{name}" for name in columns]
    if touch_updated_at:
        updates.append("updated_at = now()")
    return (
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({values}) "
        f"ON CONFLICT (id) DO UPDATE SET {', '.join(updates)}"
    )


# --------------------------------------------------------------------------
# Converting a record into the parameters the statements bind
# --------------------------------------------------------------------------

def time_zone_for(record: PifRecord) -> str:
    """The zone a fire's published wall-clock readings are in.

    Chosen from the **province**, which both exports agree on and neither can
    garble; see :data:`~src.providers.spain_egif.CANARY_PROVINCE_INE_CODES` for why not
    from the *comunidad*.
    """
    if record.province_ine_code in spain_egif.CANARY_PROVINCE_INE_CODES:
        return spain_egif.CANARY_TIME_ZONE
    return spain_egif.DEFAULT_TIME_ZONE


def resolve_srid(record: PifRecord) -> int | None:
    """The CRS the published easting and northing are in, or ``None``.

    Two published values are repaired here, and only when they have to be:

    **A missing datum becomes ETRS89.** ``iddatum`` does not exist in the XML
    before the 2014-2016 campaigns and the Excel's ``Datum`` column is blank over
    the same span, so most of the archive says nothing. ETRS89 is what every fire
    that *does* say something says, bar the Canarian ones, and those are caught by
    the zone: ``(ETRS89, 28)`` is EPSG:25828, a metre-level difference from
    REGCAN95 rather than a wrong place.

    **A zone outside 28-31 is replaced from the province.** Only then — a
    published zone Spain lies in is always used as published, because
    :data:`~src.providers.spain_egif.PROVINCE_UTM_ZONES` is modal and would move a
    quarter of a million points if it were allowed to override a good value.

    A coordinate that is not where a Spanish fire can be is refused outright — see
    :data:`~src.providers.spain_egif.PLAUSIBLE_UTM_EASTING`. That is a third repair, and
    the only one that declines to place the point rather than guessing at it.

    Returns ``None`` when there is no coordinate to place, which is not an error:
    293,710 fires in the archive publish none.
    """
    if record.utm_x is None or record.utm_y is None:
        return None

    low_x, high_x = spain_egif.PLAUSIBLE_UTM_EASTING
    low_y, high_y = spain_egif.PLAUSIBLE_UTM_NORTHING
    if not (low_x <= record.utm_x <= high_x and low_y <= record.utm_y <= high_y):
        record.problems.append(
            f"coordinate ({record.utm_x:.0f}, {record.utm_y:.0f}) is not where a "
            f"Spanish fire can be; stored without a point"
        )
        return None

    zone = record.utm_zone
    if zone not in spain_egif.UTM_ZONES:
        zone = spain_egif.PROVINCE_UTM_ZONES.get(record.province_ine_code or "")
        if zone is None:
            record.problems.append(
                f"huso {record.utm_zone!r} is not a zone Spain lies in and province "
                f"{record.province_ine_code!r} gives no fallback; stored without a point"
            )
            return None
        record.problems.append(
            f"huso {record.utm_zone!r} is not a zone Spain lies in; reprojected as "
            f"zone {zone}, the usual one for province {record.province_ine_code}"
        )

    datum = record.datum or spain_egif.DATUM_ETRS89
    srid = spain_egif.SOURCE_SRIDS.get((datum, zone))
    if srid is None:
        record.problems.append(
            f"no CRS known for datum {datum!r} in zone {zone}; stored without a point"
        )
    return srid


def base_parameters(record: PifRecord, provider_id: int,
                    admin_boundaries: dict[str, int]) -> dict[str, object]:
    """The parameters both steps bind, whichever tables they go on to write."""
    return {
        "provider_id": provider_id,
        "report_number": record.report_number,
        "time_zone": time_zone_for(record),
        "start_date_time": record.start_date_time,
        "end_date_time": record.end_date_time,
        "admin_boundary_id": admin_boundaries.get(record.municipality_ine_code or ""),
    }


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------

def load_admin_boundaries(session: Session, logger: logging.Logger) -> dict[str, int]:
    """Map INE municipal code to ``admin_boundary.id``, for the fires to hang off.

    Resolved by code rather than by point-in-polygon, which is what
    :mod:`src.providers.spain_egif.wildfire` calls for: EGIF states where a fire is
    *filed*, and where it is filed is the answer the statistic is compiled on even
    when the coordinate falls elsewhere. It also works for the 22,855 fires that
    have no coordinate to test.

    Only the XML publishes the municipal code, so in practice this resolves during
    step 2. Returning an empty map rather than raising is deliberate: the fires
    are worth having without their boundaries, and the boundaries can be imported
    afterwards.
    """
    rows = session.execute(text(
        "SELECT ign_admin_boundary.ine_code, ign_admin_boundary.id "
        "FROM ign_admin_boundary WHERE ign_admin_boundary.ine_code IS NOT NULL"
    )).all()
    boundaries = {code: identifier for code, identifier in rows}
    if not boundaries:
        logger.warning(
            "No %s municipal boundaries imported: fires will have no admin_boundary_id. "
            "Import them with src.apps.imports.admin_boundaries.ign.import_admin_boundaries",
            spain_ign.PROVIDER_NAME,
        )
    else:
        logger.debug("%d municipal boundaries available for matching", len(boundaries))
    return boundaries


class Catalogue:
    """The cause or motivation lookup, seeded from the Excel and read by both steps.

    The Excel prints ``[213]  Quema de restos agrícolas``; the XML prints ``213``
    and nothing else. So step 1 stores the pairs it sees and step 2 resolves bare
    codes through what step 1 stored — and a code the catalogue has never seen
    leaves the fire's ``cause_id`` null and is reported.

    The table is unique on ``(code, label)`` rather than on the code, so a code
    whose official wording changes between editions keeps both meanings. That
    makes ``code -> id`` potentially ambiguous, which is resolved by preferring the
    label seen on the most fires, and saying so. No code in the 1982-2023 archive
    is actually ambiguous; the rule exists so that a future edition that renames
    one degrades to "the common meaning, with a warning" instead of to chance.
    """

    def __init__(self, table: str, logger: logging.Logger) -> None:
        self.table = table
        self.logger = logger
        self.by_code: dict[str, int] = {}
        self._counts: collections.Counter[tuple[str, str]] = collections.Counter()
        self._unknown: collections.Counter[str] = collections.Counter()

    def load(self, session: Session) -> None:
        """Read what is already stored, so step 2 can run without step 1 re-reading."""
        rows = session.execute(text(
            f"SELECT code, label, id FROM {self.table} ORDER BY id"
        )).all()
        for code, label, identifier in rows:
            self._counts[(code, label)] += 0
            self.by_code.setdefault(code, identifier)
        self.logger.debug("%d %s entries known", len(rows), self.table)

    def seed(self, session: Session, seen: collections.Counter[tuple[str, str]]) -> None:
        """Store any ``(code, label)`` pair not already there, then refresh the map.

        ``ON CONFLICT DO NOTHING`` on the pair, so re-importing a file is a no-op
        and an English translation added to a row by hand is never overwritten.
        """
        if not seen:
            return
        self._counts.update(seen)
        session.execute(
            text(f"INSERT INTO {self.table} (code, label) VALUES (:code, :label) "
                 f"ON CONFLICT ON CONSTRAINT uq_{self.table}_code_label DO NOTHING"),
            [{"code": code, "label": label} for code, label in seen],
        )
        rows = session.execute(text(
            f"SELECT code, label, id FROM {self.table} WHERE code = ANY(:codes)"
        ), {"codes": sorted({code for code, _ in seen})}).all()

        best: dict[str, tuple[int, int]] = {}
        for code, label, identifier in rows:
            weight = self._counts[(code, label)]
            if code not in best or weight > best[code][0]:
                best[code] = (weight, identifier)
        for code, (_, identifier) in best.items():
            self.by_code[code] = identifier

    def resolve(self, code: str | None) -> int | None:
        """The id for a bare code, counting the ones that cannot be resolved."""
        if code is None:
            return None
        identifier = self.by_code.get(code)
        if identifier is None:
            self._unknown[code] += 1
        return identifier

    def report_unknown(self) -> None:
        """Warn once per file about codes no Excel export has ever labelled."""
        if not self._unknown:
            return
        listed = ", ".join(f"{code} x{count}"
                           for code, count in sorted(self._unknown.most_common(10)))
        self.logger.warning(
            "%d %s code(s) are not in the catalogue, so those fires have no %s: %s. "
            "Import an Excel export covering them — it is the only source of the labels.",
            len(self._unknown), self.table, self.table.replace("egif_fire_", ""), listed,
        )
        self._unknown.clear()

    def check_ambiguous(self) -> None:
        """Report any code the catalogue now holds under more than one label."""
        labels: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
        for (code, label), count in self._counts.items():
            labels[code].append((label, count))
        ambiguous = {code: sorted(entries, key=lambda item: -item[1])
                     for code, entries in labels.items() if len(entries) > 1}
        for code, entries in sorted(ambiguous.items()):
            self.logger.warning(
                "%s code %s is published under %d labels; fires are linked to the "
                "commonest (%r, on %d fires) and the others are stored unused: %s",
                self.table, code, len(entries), entries[0][0], entries[0][1],
                ", ".join(f"{label!r} x{count}" for label, count in entries[1:]),
            )


# --------------------------------------------------------------------------
# Writing a batch
# --------------------------------------------------------------------------

class FileOutcome:
    """What one file did, for the summary line and the exit status."""

    def __init__(self) -> None:
        self.read = 0
        self.written = 0
        self.skipped = 0
        self.without_point = 0
        self.problems = 0


def write_batch(session: Session, batch: list[PifRecord], provider_id: int,
                admin_boundaries: dict[str, int], causes: Catalogue,
                motivations: Catalogue, from_excel: bool,
                outcome: FileOutcome, log: logging.LoggerAdapter) -> None:
    """Upsert one batch of fires, parents before children.

    Five statements at most, each an ``executemany`` over the whole batch:
    ``ignition`` and ``egif_ignition`` for the fires that have a point,
    ``wildfire`` and ``egif_wildfire`` for all of them, and
    ``egif_wildfire_report`` for the XML step.
    """
    if not batch:
        return

    existing = {
        row.report_number: (row.wildfire_id, row.ignition_id)
        for row in session.execute(
            text(EXISTING_SQL),
            {"report_numbers": [record.report_number for record in batch]},
        ).all()
    }

    ignitions: list[dict[str, object]] = []
    egif_ignitions: list[dict[str, object]] = []
    wildfires: list[dict[str, object]] = []
    egif_wildfires: list[dict[str, object]] = []
    reports: list[dict[str, object]] = []

    # Everything that needs a freshly allocated key is worked out first, so the
    # two sequences are each drawn from once for the whole batch.
    prepared: list[tuple[PifRecord, dict[str, object], int | None]] = []
    new_wildfires = 0
    new_ignitions = 0
    for record in batch:
        parameters = base_parameters(record, provider_id, admin_boundaries)
        srid = resolve_srid(record)
        wildfire_id, ignition_id = existing.get(record.report_number, (None, None))
        if wildfire_id is None:
            new_wildfires += 1
        if srid is not None and ignition_id is None:
            new_ignitions += 1
        prepared.append((record, parameters, srid))

    wildfire_ids = allocate(session, "wildfire", new_wildfires)
    ignition_ids = allocate(session, "ignition", new_ignitions)

    for record, parameters, srid in prepared:
        wildfire_id, ignition_id = existing.get(record.report_number, (None, None))
        if wildfire_id is None:
            wildfire_id = wildfire_ids.pop()
        if srid is not None and ignition_id is None:
            ignition_id = ignition_ids.pop()
        if srid is None:
            outcome.without_point += 1

        # Kept even when this import has no point to store: an earlier import may
        # have had one, and a later export dropping the coordinate is no reason to
        # unlink the ignition that is already there.
        parameters["wildfire_id"] = wildfire_id
        parameters["ignition_id"] = ignition_id
        parameters["cause_id"] = causes.resolve(record.cause_code)
        parameters["motivation_id"] = motivations.resolve(record.motivation_code)
        report_problems(record, outcome, log)

        if srid is not None:
            point = dict(parameters, ignition_id=ignition_id, srid=srid,
                         utm_x=record.utm_x, utm_y=record.utm_y)
            ignitions.append(point)
            columns = EXCEL_IGNITION_COLUMNS if from_excel else XML_IGNITION_COLUMNS
            egif_ignitions.append(
                {"id": ignition_id, "report_number": record.report_number,
                 **{name: getattr(record, name) for name in columns}}
            )

        wildfires.append(parameters)
        columns = EXCEL_WILDFIRE_COLUMNS if from_excel else XML_WILDFIRE_COLUMNS
        egif_wildfires.append(
            {"id": wildfire_id, "report_number": record.report_number,
             **{name: parameters[name] if name in parameters else getattr(record, name)
                for name in columns}}
        )

        if not from_excel:
            report = {"id": wildfire_id, "time_zone": parameters["time_zone"]}
            report.update({name: getattr(record, name) for name in REPORT_COLUMNS})
            reports.append(report)

        outcome.written += 1

    if ignitions:
        session.execute(text(UPSERT_IGNITION_SQL), ignitions)
        session.execute(
            text(_upsert_sql("egif_ignition", "id",
                             ("report_number",) + (EXCEL_IGNITION_COLUMNS if from_excel
                                                   else XML_IGNITION_COLUMNS))),
            egif_ignitions,
        )
    session.execute(text(UPSERT_WILDFIRE_SQL), wildfires)
    session.execute(
        text(_upsert_sql("egif_wildfire", "id",
                         ("report_number",) + (EXCEL_WILDFIRE_COLUMNS if from_excel
                                               else XML_WILDFIRE_COLUMNS))),
        egif_wildfires,
    )
    if reports:
        session.execute(
            text(_upsert_sql(
                "egif_wildfire_report", "id", REPORT_COLUMNS,
                extra={name: _local(name) for name in LOCAL_DATETIME_COLUMNS},
                touch_updated_at=True,
            )),
            reports,
        )


def allocate(session: Session, table: str, count: int) -> list[int]:
    """Draw ``count`` primary keys from a table's own sequence."""
    if count <= 0:
        return []
    return list(session.scalars(text(ALLOCATE_SQL),
                                {"table": table, "count": count}).all())


# --------------------------------------------------------------------------
# Importing one file
# --------------------------------------------------------------------------

def report_problems(record: PifRecord, outcome: FileOutcome,
                    log: logging.LoggerAdapter) -> None:
    """Log everything wrong with one fire, then forget it.

    Called from :func:`write_batch` rather than from the read loop, and that is
    not arbitrary: :func:`resolve_srid` adds problems of its own — a zone it had
    to replace, a datum it could not resolve — and it does not run until the fire
    is being written. Logging at read time would report the file's problems and
    silently drop the importer's.
    """
    for problem in record.problems:
        outcome.problems += 1
        if outcome.problems <= MAX_REPORTED_PROBLEMS:
            log.warning("%s: %s", record.report_number, problem)
    record.problems.clear()


def usable(record: PifRecord, outcome: FileOutcome, log: logging.LoggerAdapter) -> bool:
    """Whether a fire can be stored at all, logging it if not.

    The bar is low on purpose. Only the detection instant is indispensable —
    ``wildfire.start_date_time`` is ``NOT NULL`` and EGIF publishes nothing else
    that could stand for it. A fire missing anything else is stored in a reduced
    form rather than dropped.
    """
    if record.start_date_time is None:
        report_problems(record, outcome, log)
        outcome.skipped += 1
        if outcome.skipped <= MAX_REPORTED_PROBLEMS:
            log.error("%s has no detection instant, so it cannot be stored",
                      record.report_number)
        return False
    return True


def import_file(path: Path, engine: Engine, provider_id: int,
                admin_boundaries: dict[str, int], causes: Catalogue,
                motivations: Catalogue, from_excel: bool,
                logger: logging.Logger) -> FileOutcome:
    """Read one export and commit it, all of it, in a single transaction."""
    log = ArchiveLogger(logger, {"archive": path.name})
    outcome = FileOutcome()
    started = time.monotonic()

    total = readers.count_excel_rows(path) if from_excel else None
    progress = ProgressReporter(total, path.name, logger)
    records = readers.read_excel(path) if from_excel else readers.read_xml(path)

    with Session(engine) as session:
        batch: list[PifRecord] = []
        seen_causes: collections.Counter[tuple[str, str]] = collections.Counter()
        seen_motivations: collections.Counter[tuple[str, str]] = collections.Counter()

        def flush() -> None:
            if from_excel:
                causes.seed(session, seen_causes)
                motivations.seed(session, seen_motivations)
                seen_causes.clear()
                seen_motivations.clear()
            write_batch(session, batch, provider_id, admin_boundaries, causes,
                        motivations, from_excel, outcome, log)
            batch.clear()

        # A report number is the key both formats share and both upserts conflict
        # on, so the same one twice in one file would mean two rows racing for one
        # key inside a single statement. No export in the archive does it; the
        # guard is here because the failure would otherwise be an opaque unique
        # violation on a 30,000-fire file rather than a named duplicate.
        seen_reports: set[str] = set()

        for record in records:
            outcome.read += 1
            progress.advance()
            if record.report_number in seen_reports:
                outcome.skipped += 1
                if outcome.skipped <= MAX_REPORTED_PROBLEMS:
                    log.error("%s appears more than once in this file; keeping the first",
                              record.report_number)
                continue
            if not usable(record, outcome, log):
                continue
            seen_reports.add(record.report_number)
            if from_excel:
                if record.cause_code and record.cause_label:
                    seen_causes[(record.cause_code, record.cause_label)] += 1
                if record.motivation_code and record.motivation_label:
                    seen_motivations[(record.motivation_code, record.motivation_label)] += 1
            batch.append(record)
            if len(batch) >= BATCH_SIZE:
                flush()
        flush()
        session.commit()

    progress.finish()
    causes.report_unknown()
    motivations.report_unknown()

    elapsed = time.monotonic() - started
    log.info("imported %d of %d fire(s) in %.0fs (%d without a point)",
             outcome.written, outcome.read, elapsed, outcome.without_point)
    if outcome.skipped:
        log.warning("%d fire(s) could not be stored and were skipped", outcome.skipped)
    if outcome.problems > MAX_REPORTED_PROBLEMS:
        log.warning("%d problem(s) reported in total, of which %d were logged above",
                    outcome.problems, MAX_REPORTED_PROBLEMS)
    return outcome


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Import the Spanish EGIF fire statistics: Excel exports first, "
                    "then XML exports.",
        epilog="Import the IGN municipal boundaries first, so that fires get an "
               "admin_boundary_id. Database settings not given here are read from "
               "the environment (.env).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-d", "--directory", type=Path,
                        help="directory holding the exports; every .xlsx is imported "
                             "before every .xml")
    source.add_argument("-s", "--source", type=Path, nargs="+",
                        help="one or more export files to import instead of a whole "
                             "directory, still Excel before XML")

    parser.add_argument("--skip-excel", action="store_true",
                        help="do not run step 1. The cause and motivation catalogues "
                             "must already be seeded, or every fire will be stored "
                             "with no cause")
    parser.add_argument("--skip-xml", action="store_true",
                        help="do not run step 2, importing only the fire-level summary")

    common.add_database_arguments(parser)
    common.add_common_arguments(parser)
    return parser.parse_args(argv)


def find_exports(args: argparse.Namespace) -> tuple[list[Path], list[Path]]:
    """List the Excel and the XML exports to read, each sorted chronologically.

    Sorting matters for more than tidiness: the file names begin with the campaign
    span, so sorting them puts the archive in order and a fire revised in a later
    export is written after the version it supersedes.

    Raises
    ------
    RuntimeError
        If nothing was found — far more likely a wrong path than an empty
        download, and importing nothing without saying so would hide it.
    """
    if args.directory is not None:
        excel = sorted(args.directory.glob("*.xlsx"))
        xml = sorted(args.directory.glob("*.xml"))
        if not excel and not xml:
            raise RuntimeError(f"{args.directory} holds no .xlsx or .xml export")
    else:
        excel = sorted(path for path in args.source if path.suffix.lower() == ".xlsx")
        xml = sorted(path for path in args.source if path.suffix.lower() == ".xml")
        unknown = [path for path in args.source
                   if path.suffix.lower() not in (".xlsx", ".xml")]
        if unknown:
            raise RuntimeError(
                f"not an EGIF export: {', '.join(str(path) for path in unknown)}"
            )
    return excel, xml


def import_wildfires(args: argparse.Namespace, engine: Engine,
                     logger: logging.Logger) -> int:
    """Run both steps against ``engine``, returning the fires written."""
    excel, xml = find_exports(args)
    if args.skip_excel:
        excel = []
    if args.skip_xml:
        xml = []

    common.require_tables(engine, ["wildfire", "ignition", "egif_wildfire",
                                   "egif_ignition", "egif_wildfire_report",
                                   "egif_fire_cause", "egif_fire_motivation",
                                   "ign_admin_boundary", "data_provider"], logger)

    causes = Catalogue("egif_fire_cause", logger)
    motivations = Catalogue("egif_fire_motivation", logger)

    with Session(engine) as session:
        provider = common.get_or_create_data_provider(
            session, spain_egif.PROVIDER_NAME, spain_egif.PROVIDER_PRODUCT,
            spain_egif.PROVIDER_FULL_NAME, spain_egif.PROVIDER_URL, logger,
        )
        admin_boundaries = load_admin_boundaries(session, logger)
        causes.load(session)
        motivations.load(session)
        session.commit()
        provider_id = provider.id

    if not excel and not causes.by_code:
        logger.warning(
            "No Excel export will be read and no cause catalogue is stored, so every "
            "fire will be imported with no cause. The Excel export is the only public "
            "source of the cause and motivation labels."
        )

    started = time.monotonic()
    written = 0
    logger.info("Step 1: %d Excel export(s); step 2: %d XML export(s)", len(excel), len(xml))
    for step, (paths, from_excel) in enumerate(((excel, True), (xml, False)), start=1):
        for index, path in enumerate(paths, start=1):
            logger.info("[step %d: %d/%d] %s", step, index, len(paths), path.name)
            written += import_file(path, engine, provider_id, admin_boundaries,
                                   causes, motivations, from_excel, logger).written

    causes.check_ambiguous()
    motivations.check_ambiguous()
    logger.info("Imported %d fire(s) from %d file(s) in %.0fs", written,
                len(excel) + len(xml), time.monotonic() - started)
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("egif-import")

    if args.directory is not None and not args.directory.exists():
        logger.error("Not found: %s", args.directory)
        return 1
    for path in args.source or []:
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
