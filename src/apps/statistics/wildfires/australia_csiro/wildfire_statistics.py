#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Burnt-area statistics for the CSIRO Historical Bushfire Extents (Australia).

Reports the archive per **fire season** — July to June, the Australian bushfire
season — with three figures for every group of fires: how many there were, the
hectares the agencies report and the hectares this application measures::

    Season  Fires  Reported (ha)  Measured (ha)  | Bushfire ... | Prescribed burn ... |
            Unknown type ... | Natural cause ...

The first triplet is every fire in the season. The next three repeat it for each
published fire type, and add up to the first. The last repeats it for the fires
whose published cause is natural, and is **not** a fourth part of the first: it cuts
across the types (see below).

One national file and one file per state are written in the same format, as CSV and
Word::

    python3 -m src.apps.statistics.wildfires.australia_csiro.wildfire_statistics \\
        --csv australia.csv --docx australia.docx

writes ``australia.csv`` and ``australia.docx`` for the whole archive, then
``australia_NSW.csv``, ``australia_NSW.docx``, … for every state that has fires in
the seasons reported. A state with none is skipped rather than written as a table of
zeros.

The application only reads. Database settings come from the environment (``.env``,
see :mod:`src.settings`); every one of them can be overridden with a command-line
argument.

Seasons, and why 1970-71 is the default first one
-------------------------------------------------

A fire belongs to the season its resolved start date falls in — the published
ignition date, or the extinction or capture date where there is none, exactly the
date :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.year` is taken
from. A start from July onwards opens a season, one before July closes the previous
one: 2020-01-04 is in 2019-20, the Black Summer, and so is 2019-11-08. A season is
named and selected by the year it starts in.

The archive runs from 1898, but its early decades are not a national record. The
year from which each state reports **every** year without a gap is WA 1925, QLD
1937, VIC 1942, NSW 1944, SA 1950, ACT 1964 and TAS 1969 — so before 1970 a national
total cannot tell a season without fires from a season without data. 1970-71 is
therefore the default first season (:data:`DEFAULT_FIRST_SEASON`). The Northern
Territory is the exception for good: it publishes 2020, 2021 and 2025 only.

What the columns count
----------------------

``Fires`` counts **published features**. The import merges nothing — one row per
polygon the agency published — so a burn mapped as several patches is several
fires here. See :mod:`src.providers.australia_csiro`.

``Reported (ha)`` sums the published ``area_ha``, which is whole hectares: 77,069
features publish 0. ``Measured (ha)`` sums the geodesic area of the perimeter on the
WGS84 ellipsoid, the method every burnt-area report in GisFIRE uses. Over a season
they agree to a few hundredths of a percent; per feature they do not, which is why
both are reported.

The three type triplets are the published fire type normalised —
``bushfire``, ``prescribed_burn`` and ``unknown`` for the 27% of features that do
not say. Every feature has exactly one, so they partition the season.

The natural triplet counts the features whose published cause is natural. Cause is
published for some states only — all of NSW and NT, part of WA, TAS and ACT, almost
none of VIC and none of QLD and SA — so **a zero is only an answer where causes were
published**. Where no feature of a season in the file's scope publishes any cause,
the three natural cells are left empty instead.

Fires whose published dates cannot be believed (an epoch placeholder, a year outside
1900-2100, an extinction before the ignition — 514 features) are left out by
default, because their season is unknown; ``--include-implausible`` counts them.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from geoalchemy2 import Geography
from sqlalchemy import Engine
from sqlalchemy import Integer
from sqlalchemy import Select
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import create_engine
from sqlalchemy import extract
from sqlalchemy import false
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.data_model.wildfire import Wildfire
from src.providers import australia_csiro
from src.providers.australia_csiro.wildfire import CsiroWildfire

#: Written in the season column of the summary row.
TOTAL_LABEL = "Total"

#: How the report names the whole archive, in the Word heading.
COUNTRY_NAME = "Australia"

#: Square metres in a hectare.
SQUARE_METRES_PER_HECTARE = 10_000.0

#: The month a fire season starts in. July: the Australian bushfire season is
#: reported July to June, so that one summer is one season.
SEASON_FIRST_MONTH = 7

#: The first season reported unless ``--from-season`` says otherwise: 1970-71, the
#: first in which every state but the Northern Territory reports every year. See the
#: module docstring.
DEFAULT_FIRST_SEASON = 1970

#: The fire types, in the order their triplets appear, with the label each is given.
TYPE_LABELS = {
    australia_csiro.FIRE_TYPE_BUSHFIRE: "Bushfire",
    australia_csiro.FIRE_TYPE_PRESCRIBED_BURN: "Prescribed burn",
    australia_csiro.FIRE_TYPE_UNKNOWN: "Unknown type",
}

#: The label of the natural-cause triplet.
NATURAL_LABEL = "Natural cause"

#: The label of the first triplet, every fire in the season.
ALL_LABEL = "All fires"

#: The three figures of a triplet, as their headings read.
TRIPLET = ("Fires", "Reported (ha)", "Measured (ha)")

#: Every group the report has a triplet for, in column order.
GROUPS = (ALL_LABEL, *TYPE_LABELS.values(), NATURAL_LABEL)

#: The last column: how many of the season's fires publish a cause this project can
#: read. See :attr:`Row.with_cause`.
WITH_CAUSE_LABEL = "Fires with cause"

#: The CSV header: the season, then a triplet per group, then
#: :data:`WITH_CAUSE_LABEL`. The first triplet is unprefixed so that its three headings
#: read like every other burnt-area report's.
COLUMNS = ("Season", *TRIPLET,
           *(f"{group} {heading[0].lower()}{heading[1:]}"
             for group in GROUPS[1:] for heading in TRIPLET),
           WITH_CAUSE_LABEL)

#: States in the order their files are written: the ``STATE_CODES`` order, which is
#: the provider's.
STATES = australia_csiro.STATE_CODES

#: Notes the Word document of a scope carries, beyond the ones every file has.
#: Keyed by state code, with ``None`` for the national file.
SCOPE_NOTES = {
    None: "The national figures are the sum of the states. Coverage is not even: the "
          "Northern Territory publishes 2020, 2021 and 2025 only, and Queensland "
          "publishes almost nothing after 2023.",
    australia_csiro.STATE_QLD: "Queensland publishes 8 features in 2024 and 6 in 2025, "
                               "against several hundred a year before: the last "
                               "seasons are incomplete, not quiet.",
    australia_csiro.STATE_NT: "The Northern Territory publishes 2020, 2021 and 2025 "
                              "only. Every other season is empty for lack of data.",
}


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------

def season_label(season: int) -> str:
    """``2019`` → ``2019-20``: the season that starts in July of that year."""
    return f"{season}-{(season + 1) % 100:02d}"


def season_argument(text: str) -> int:
    """Argparse type for a season: ``2019`` or ``2019-20``, both meaning July 2019.

    Raises
    ------
    argparse.ArgumentTypeError
        If the text is neither, or names a pair of years that are not consecutive.
    """
    match = re.fullmatch(r"\s*(\d{4})(?:\s*[-/]\s*(\d{2}|\d{4}))?\s*", text)
    if match is None:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a season: write the year it starts in, e.g. 2019, or "
            f"the pair, e.g. 2019-20")
    start = int(match.group(1))
    if match.group(2) is not None:
        end = match.group(2)
        expected = str(start + 1)
        if end != expected and end != expected[-2:]:
            raise argparse.ArgumentTypeError(
                f"{text!r} is not a season: a season runs July to June, so the second "
                f"year has to be {season_label(start).split('-')[1]}")
    return start


def resolved_start() -> object:
    """The date a fire's season is taken from: ignition, else extinction, else capture.

    The same fallback the import resolves ``start_date_time`` and ``year`` with.
    """
    fire = CsiroWildfire.__table__.c
    return func.coalesce(fire.ignition_date, fire.extinguish_date, fire.capture_date)


def season_of() -> object:
    """The season a fire belongs to, as the year it starts in."""
    start = resolved_start()
    return cast(
        extract("year", start)
        - case((extract("month", start) < SEASON_FIRST_MONTH, 1), else_=0),
        Integer,
    )


# --------------------------------------------------------------------------
# The query
# --------------------------------------------------------------------------

def statistics_query(first: int | None, last: int | None,
                     include_implausible: bool = False) -> Select:
    """Everything the report needs, in one statement.

    One row per state, season, fire type and natural-or-not, with the count, the
    number of those that publish any cause, and both areas summed. Every file the
    run writes is a sum of these rows, so the perimeters — 155.8 million vertices —
    are measured once, not once per file, and only a few thousand summary rows leave
    the server.
    """
    fire = CsiroWildfire.__table__.c
    season = season_of()
    natural = func.coalesce(fire.cause == australia_csiro.CAUSE_NATURAL, false())
    measured = func.ST_Area(
        cast(Wildfire.perimeter, Geography(geometry_type="MULTIPOLYGON", srid=4326))
    ) / SQUARE_METRES_PER_HECTARE

    statement = (
        select(fire.state_code.label("state"),
               season.label("season"),
               fire.fire_type.label("fire_type"),
               natural.label("natural"),
               func.count().label("fires"),
               func.count(fire.cause).label("with_cause"),
               func.coalesce(func.sum(fire.area_ha), 0.0).label("reported"),
               func.coalesce(func.sum(measured), 0.0).label("measured"))
        .select_from(CsiroWildfire.__table__)
        .join(Wildfire.__table__, Wildfire.id == fire.id)
        .where(resolved_start().is_not(None))
        .group_by(fire.state_code, season, fire.fire_type, natural)
    )
    if not include_implausible:
        statement = statement.where(fire.dates_plausible)
    if first is not None:
        statement = statement.where(season >= first)
    if last is not None:
        statement = statement.where(season <= last)
    return statement


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Triplet:
    """The three figures of one group of fires."""

    fires: int = 0
    reported: float = 0.0
    measured: float = 0.0

    def __add__(self, other: Triplet) -> Triplet:
        return Triplet(self.fires + other.fires, self.reported + other.reported,
                       self.measured + other.measured)

    @property
    def values(self) -> tuple[str, str, str]:
        """As the CSV writes it: bare numbers."""
        return str(self.fires), f"{self.reported:.2f}", f"{self.measured:.2f}"

    @property
    def readable_values(self) -> tuple[str, str, str]:
        """As the Word document writes it: with thousands separators."""
        return f"{self.fires:,}", f"{self.reported:,.2f}", f"{self.measured:,.2f}"


#: Three empty cells, for a natural triplet that has no answer.
NO_ANSWER = ("", "", "")


@dataclass(frozen=True)
class Row:
    """One line of a report: a season, or the summary.

    Attributes
    ----------
    season : int or None
        The year the season starts in, or ``None`` for the summary row.
    total : Triplet
        Every fire in the season.
    by_type : dict
        One triplet per fire type, keyed by the normalised type; they add up to
        ``total``.
    natural : Triplet or None
        The fires whose published cause is natural, or ``None`` where no fire in the
        season publishes any cause — a zero there would claim an answer the data does
        not give.
    with_cause : int
        How many of ``total.fires`` publish a cause in the provider's vocabulary
        (natural, accidental, incendiary or undetermined, in any of the spellings
        :data:`~src.providers.australia_csiro.CAUSE_NORMALISATIONS` reads). A blank
        cause, or one it does not recognise such as ``OTHER``, is not counted.
    """

    season: int | None
    total: Triplet
    by_type: dict[str, Triplet] = field(default_factory=dict)
    natural: Triplet | None = None
    with_cause: int = 0

    @property
    def is_total(self) -> bool:
        return self.season is None

    @property
    def season_label(self) -> str:
        return TOTAL_LABEL if self.is_total else season_label(self.season)

    def _triplets(self) -> list[Triplet | None]:
        return [self.total,
                *(self.by_type.get(fire_type, Triplet()) for fire_type in TYPE_LABELS),
                self.natural]

    @property
    def values(self) -> tuple[str, ...]:
        """The row as the CSV writes it, in :data:`COLUMNS` order."""
        cells = [self.season_label]
        for triplet in self._triplets():
            cells += NO_ANSWER if triplet is None else triplet.values
        cells.append(str(self.with_cause))
        return tuple(cells)

    @property
    def readable_values(self) -> tuple[str, ...]:
        """The row as the Word document writes it."""
        cells = [self.season_label]
        for triplet in self._triplets():
            cells += NO_ANSWER if triplet is None else triplet.readable_values
        cells.append(f"{self.with_cause:,}")
        return tuple(cells)


@dataclass(frozen=True)
class Report:
    """One file's worth of rows, and whose fires they are.

    ``state`` is ``None`` for the national report.
    """

    state: str | None
    rows: list[Row]

    @property
    def label(self) -> str:
        return COUNTRY_NAME if self.state is None else f"{self.state}, {COUNTRY_NAME}"


def build_rows(records: list, seasons: list[int]) -> list[Row]:
    """Turn the query's rows for one scope into the report's: newest season first,
    then the summary.

    Parameters
    ----------
    records : list
        Rows of :func:`statistics_query` already restricted to the scope.
    seasons : list of int
        Every season the file has a line for, whether it has fires or not, so that
        the national file and every state's line up.
    """
    totals: dict[int, Triplet] = {season: Triplet() for season in seasons}
    by_type: dict[int, dict[str, Triplet]] = {season: {} for season in seasons}
    natural: dict[int, Triplet] = {season: Triplet() for season in seasons}
    with_cause: dict[int, int] = {season: 0 for season in seasons}

    for record in records:
        if record.season not in totals:
            continue
        triplet = Triplet(record.fires, float(record.reported), float(record.measured))
        totals[record.season] += triplet
        types = by_type[record.season]
        types[record.fire_type] = types.get(record.fire_type, Triplet()) + triplet
        if record.natural:
            natural[record.season] += triplet
        with_cause[record.season] += record.with_cause

    rows = [Row(season=season, total=totals[season], by_type=by_type[season],
                natural=natural[season] if with_cause[season] else None,
                with_cause=with_cause[season])
            for season in sorted(seasons, reverse=True)]
    return rows + [summarise(rows)] if rows else []


def summarise(rows: list[Row]) -> Row:
    """The summary row: every triplet summed over the seasons.

    The natural triplet sums the seasons that have one, and is empty only if none
    does.
    """
    total = Triplet()
    types: dict[str, Triplet] = {}
    natural: Triplet | None = None
    with_cause = 0
    for row in rows:
        total += row.total
        with_cause += row.with_cause
        for fire_type, triplet in row.by_type.items():
            types[fire_type] = types.get(fire_type, Triplet()) + triplet
        if row.natural is not None:
            natural = row.natural if natural is None else natural + row.natural
    return Row(season=None, total=total, by_type=types, natural=natural,
               with_cause=with_cause)


def compute(session: Session, logger: logging.Logger, first: int | None = None,
            last: int | None = None,
            include_implausible: bool = False) -> list[Report]:
    """Measure the archive once and split it into the national and state reports.

    Returns
    -------
    list of Report
        The national report first, then one per state that has fires in the seasons
        reported. Empty if nothing matched.
    """
    with common.Spinner(f"Measuring the burnt area of the {COUNTRY_NAME} perimeters",
                        logger):
        records = list(session.execute(
            statistics_query(first, last, include_implausible)))
    if not records:
        return []

    found = [record.season for record in records]
    lowest = min(found) if first is None else first
    highest = max(found) if last is None else min(last, max(found))
    seasons = list(range(lowest, highest + 1))

    reports = [Report(None, build_rows(records, seasons))]
    for state in STATES:
        mine = [record for record in records if record.state == state]
        if not any(record.fires for record in mine):
            logger.info("%s has no fires in the seasons reported; no file for it", state)
            continue
        reports.append(Report(state, build_rows(mine, seasons)))

    national = reports[0].rows[-1].total
    logger.info("Computed %d season(s), %s to %s: %d fire(s), %.2f ha reported, "
                "%.2f ha measured, %d state file(s)",
                len(seasons), season_label(lowest), season_label(highest),
                national.fires, national.reported, national.measured, len(reports) - 1)
    return reports


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def output_path(path: Path, state: str | None) -> Path:
    """``australia.csv`` for the nation, ``australia_NSW.csv`` for a state."""
    if state is None:
        return path
    return path.with_name(f"{path.stem}_{state}{path.suffix}")


def write_csv(report_: Report, path: Path, logger: logging.Logger) -> None:
    """Write one report as CSV: bare numbers, no separators, for another program."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in report_.rows:
            writer.writerow(row.values)
    logger.info("Wrote %s", path)


def write_docx(report_: Report, path: Path, logger: logging.Logger,
               include_implausible: bool = False) -> None:
    """Write one report as a Word document.

    One table on a **landscape** page — seventeen columns do not fit across a portrait
    one — under a two-row heading: the group over its three figures. The summary row
    is in bold.
    """
    # Imported here so that --csv keeps working without python-docx.
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width

    document.add_heading(f"CSIRO bushfire extents — burnt area by fire season "
                         f"({report_.label})", level=1)
    seasons = [row for row in report_.rows if not row.is_total]
    span = (f"{season_label(seasons[-1].season)} to {season_label(seasons[0].season)}"
            if seasons else "no season")
    document.add_paragraph(
        f"Fire seasons run July to June; a fire belongs to the season its published "
        f"ignition date falls in (its extinction or capture date where there is none). "
        f"Seasons: {span}. Fires are published features: nothing is merged, so a burn "
        f"mapped as several patches counts several times. Reported is the published "
        f"area_ha, in whole hectares; Measured is the geodesic area of the perimeter "
        f"on the WGS84 ellipsoid."
    )
    document.add_paragraph(
        "The three fire types add up to All fires. Natural cause counts the fires whose "
        "published cause is natural, of any type. Causes are published for some states "
        "only, so its cells are left empty for a season in which no fire publishes a "
        "cause at all; a zero means causes were published and none was natural."
    )
    document.add_paragraph(
        f"{WITH_CAUSE_LABEL} counts the fires whose published cause is one this report "
        f"can read — natural, accidental, incendiary or undetermined. A blank cause, or "
        f"an unrecognised one such as OTHER, is not counted. Compare it with Fires to "
        f"see how much of a season the Natural cause triplet can speak for."
    )
    if not include_implausible:
        document.add_paragraph(
            "Fires whose published dates cannot be believed are left out: their season "
            "is unknown.")
    note = SCOPE_NOTES.get(report_.state)
    if note:
        document.add_paragraph(note)

    columns = 1 + len(GROUPS) * len(TRIPLET) + 1
    table = document.add_table(rows=2, cols=columns)
    table.style = "Table Grid"
    figures = table.rows[1].cells
    season_cell = table.cell(0, 0).merge(table.cell(1, 0))
    season_cell.text = "Season"
    cause_cell = table.cell(0, columns - 1).merge(table.cell(1, columns - 1))
    cause_cell.text = WITH_CAUSE_LABEL
    for index, group in enumerate(GROUPS):
        first = 1 + index * len(TRIPLET)
        merged = table.cell(0, first).merge(table.cell(0, first + len(TRIPLET) - 1))
        merged.text = group
        merged.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for offset, title in enumerate(TRIPLET):
            figures[first + offset].text = title
    for row in table.rows[:2]:
        for cell in row.cells:
            for run in cell.paragraphs[0].runs:
                run.bold = True
                run.font.size = Pt(7)

    for row in report_.rows:
        cells = table.add_row().cells
        for index, (cell, value) in enumerate(zip(cells, row.readable_values)):
            cell.text = value
            paragraph = cell.paragraphs[0]
            if index >= 1:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for run in paragraph.runs:
                run.bold = row.is_total
                run.font.size = Pt(7)

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    logger.info("Wrote %s", path)


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Burnt-area statistics for the CSIRO Historical Bushfire Extents, "
                    "per fire season (July to June): every fire, each fire type and the "
                    "natural-cause fires, as a national file and one file per state.",
        epilog="Fires are published features, nothing merged. Measured areas are "
               "geodesic on the WGS84 ellipsoid. Database settings not given here are "
               "read from the environment (.env).",
    )
    parser.add_argument("--from-season", type=season_argument,
                        default=DEFAULT_FIRST_SEASON, metavar="SEASON",
                        help=f"first season, as 2019 or 2019-20 (default "
                             f"{season_label(DEFAULT_FIRST_SEASON)}, the first in which "
                             f"every state but NT reports every year)")
    parser.add_argument("--to-season", type=season_argument, default=None,
                        metavar="SEASON",
                        help="last season, as 2019 or 2019-20 (default: the latest "
                             "with fires)")
    parser.add_argument("-s", "--season", type=season_argument, default=None,
                        metavar="SEASON",
                        help="report this one season only, as 2019 or 2019-20")
    parser.add_argument("--all-seasons", action="store_true",
                        help="start from the first season in the archive (1898-99) "
                             "instead of the default")
    parser.add_argument("--include-implausible", action="store_true",
                        help="count the fires whose published dates cannot be "
                             "believed (514 features); left out by default because "
                             "their season is unknown")

    output = parser.add_argument_group(
        "output", "at least one is required; a file per state is written beside each")
    output.add_argument("--csv", type=Path, help="write the national report to this .csv")
    output.add_argument("--docx", type=Path,
                        help="write the national report to this .docx (MS Word)")

    common.add_database_arguments(parser)
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")

    arguments = parser.parse_args(argv)
    if arguments.csv is None and arguments.docx is None:
        parser.error("nothing to write: pass --csv, --docx, or both")
    if arguments.season is not None:
        arguments.from_season = arguments.to_season = arguments.season
    elif arguments.all_seasons:
        arguments.from_season = None
    if (arguments.from_season is not None and arguments.to_season is not None
            and arguments.to_season < arguments.from_season):
        parser.error(f"--to-season {season_label(arguments.to_season)} is before "
                     f"--from-season {season_label(arguments.from_season)}")
    return arguments


def report(args: argparse.Namespace, engine: Engine,
           logger: logging.Logger) -> list[Report]:
    """Compute the reports and write whichever outputs were asked for."""
    with Session(engine) as session:
        reports = compute(session, logger, args.from_season, args.to_season,
                          args.include_implausible)
    if not reports:
        raise RuntimeError(
            "No fires matched. Check the seasons asked for, and that the CSIRO bushfire "
            "extents are imported.")

    for report_ in reports:
        if args.csv is not None:
            write_csv(report_, output_path(args.csv, report_.state), logger)
        if args.docx is not None:
            write_docx(report_, output_path(args.docx, report_.state), logger,
                       args.include_implausible)
    return reports


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("csiro-statistics")

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        report(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("%s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":  # pragma nocover
    sys.exit(main())
