#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Burnt-area statistics for the Spanish EGIF fire statistics.

Reports, per campaign, how many fires there were and the smallest, largest and
total area burnt, in hectares::

    Country          Year    Fires     Minimum      Maximum        Total
    Spain            2023      6294        0.00      9520.00      75236.41
    Spain            2022      7362        0.00     31500.00     243610.28
    Spain            Total    13656        0.00     31500.00     318846.69

Run it over everything, or narrow it to one campaign, or to the fires above a
size::

    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics --csv burnt.csv
    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics \\
        --year 2023 --csv 2023.csv --docx 2023.docx
    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_statistics \\
        --surface burnt --min-area 5 --csv over-5-ha.csv

At least one of ``--csv`` and ``--docx`` is required: an application that
computed a report and then printed nothing would be a strange thing.

The application only reads. Database settings come from the environment
(``.env``, see :mod:`src.settings`); every one of them can be overridden with a
command-line argument.

The area is reported, not measured
----------------------------------

This is the one thing that makes this report different from its
:mod:`GWIS <src.apps.statistics.wildfires.gwis.wildfire_statistics>`,
:mod:`GFA <src.apps.statistics.wildfires.gfa.wildfire_statistics>` and
:mod:`ICNF <src.apps.statistics.wildfires.portugal_icnf.wildfire_statistics>`
counterparts, and it is not a detail of implementation. Those three measure a
polygon. **EGIF publishes no polygon, in any of its exports, and never will** —
:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every EGIF
fire by design, see :mod:`src.providers.spain_egif.wildfire`. What EGIF publishes
is a burnt *area*, in hectares, as filled in on the report form.

So there is no ``--area-method`` here: nothing is being projected or measured on
an ellipsoid, and the figures cannot be made to agree with a perimeter dataset by
choosing a better CRS. They are a different kind of number, and the difference
between them and a measured area is a real quantity about the archive rather than
an error in either.

Which surface
-------------

EGIF does not publish *one* burnt area. It publishes five, and ``--surface``
picks which one the report is of:

``forest`` (default)
    ``SuperficieTotalForestal`` — total burnt forest area, and the figure the
    national statistic is quoted in. Summing it over fires reproduces the
    published national total, which is why it is the default.
``wooded``, ``non-wooded``
    ``SuperficieArbolada`` and ``SuperficieNoArbolada``, the two parts ``forest``
    is the sum of — exactly, checked on every row of the 2022-2023 sample.
``agricultural``, ``other-non-forest``
    ``SuperficieAgricola`` and ``OtrasSuperficiesNoforestales``. Both are
    **outside** the forest total: EGIF counts forest and non-forest separately.
``burnt``
    Everything that burnt: ``forest`` plus ``agricultural`` plus
    ``other-non-forest``. Not a figure EGIF publishes, and deliberately not the
    default — quoting it as *the* burnt area of a Spanish fire year would not
    match the national statistic. It is the right one to ask for when the
    question is about land burnt rather than about forest lost.

Never add two runs of this report together. ``wooded`` and ``non-wooded`` sum to
``forest``, and ``forest``, ``agricultural`` and ``other-non-forest`` sum to
``burnt``, but only in the ``Total (ha)`` column: a minimum of minima over two
different columns is not the minimum of their sum, because the two ends need not
belong to the same fire. Ask for ``burnt`` and let the database add the rows up.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.spain_egif.wildfire.EgifWildfire.campaign` — the campaign
the *parte* is filed under, which is also the first four characters of its report
number — and **not** the year of ``start_date_time``, exactly as the ICNF report
uses the published ``Ano``.

The two are normally the same year and can disagree at a New Year's Eve fire.
Where they do, the report follows the filing, because a published yearly total is
a total of what the service filed that year. ``campaign`` is also ``NOT NULL``
and indexed, and needs no timezone applied to it — which
``start_date_time`` would, EGIF's instants being local wall-clock readings in two
different zones.

Which fires are counted
-----------------------

Those whose chosen surface **is reported**. A fire whose
``SuperficieTotalForestal`` is ``NULL`` is not a fire that burnt no forest; it is
a fire whose form does not say, and it is left out of the count as well as out of
the areas — so the ``Fires`` column always counts exactly the fires the three
figures beside it were computed from.

A reported **zero is counted**, and is a real answer: a fire that burnt only
agricultural land has a forest total of 0.00 ha. That is why a minimum of
``0.00`` is normal in this report and not a sign of a missing value. Under
``--surface burnt`` a fire counts if *any* of the three components is reported,
the unreported ones contributing nothing.

``--min-area`` narrows it further, to the fires of at least that many hectares.
By default there is no threshold.

.. warning::

   **A campaign's total is a floor, not the year's burnt area.** Every fire the
   service exports is in state *Cerrado Revisión*, and a region appears only once
   it has closed its fires, so a freshly exported year is missing whole regions —
   the 2022 sample here totals 243,610 ha against the ~306,000 ha eventually
   published. A year has to be re-exported and re-imported later. Comparing two
   campaigns of different vintages compares two different degrees of completeness,
   not two fire seasons.

One statement, and no country test
----------------------------------

The other three reports measure one year per statement, because a point-in-polygon
test against a country polygon holds its memory until the statement ends and a
single pass over twenty million perimeters took a 30 GB machine to the OOM killer.
**This report does no geometry at all** — it is an indexed aggregate over one
column of one table — so there is nothing to spread over several statements, and
it runs as one ``GROUP BY campaign``. The ``Total`` row is still arithmetic over
the years, by :func:`combine`, so the output is the same shape as the other three.

For the same reason there is no ``--country-source``: with no perimeter there is
nothing to test against a boundary, and EGIF's own answer to where a fire is —
*comunidad*, province, municipality — is administrative and never in doubt about
the country. The ``Country`` column is therefore the constant
:data:`COUNTRY_NAME`. It is kept so that this report's CSV has the same shape as
the other three and the four can be concatenated and compared, which is the whole
reason for reporting a national statistic in the same table as three perimeter
datasets.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
import sys

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import ColumnElement
from sqlalchemy import Engine
from sqlalchemy import Select
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers.spain_egif.wildfire import EgifWildfire

#: Label used in the ``Year`` column for the summary row.
TOTAL_LABEL = "Total"

#: The report's columns, in order, shared by both output formats so that a change
#: to one cannot silently leave the other behind. Deliberately identical to the
#: GWIS, GFA and ICNF reports' columns, so the four CSVs can be concatenated.
COLUMNS = ("Country", "Year", "Fires", "Minimum (ha)", "Maximum (ha)", "Total (ha)")

#: Index of the first column that holds a number, and so is right-aligned in the
#: Word table.
FIRST_NUMERIC_COLUMN = 2

#: The only country EGIF reports on. A constant and not a query: see the module
#: docstring for why there is nothing to resolve here. Spelled as the OCHA
#: boundaries spell it, so a row of this report sorts and groups with the rows of
#: the other three.
COUNTRY_NAME = "Spain"

#: The burnt areas EGIF publishes, as ``--surface`` accepts them.
SURFACE_FOREST = "forest"
SURFACE_WOODED = "wooded"
SURFACE_NON_WOODED = "non-wooded"
SURFACE_AGRICULTURAL = "agricultural"
SURFACE_OTHER_NON_FOREST = "other-non-forest"
SURFACE_BURNT = "burnt"
SURFACES = (SURFACE_FOREST, SURFACE_WOODED, SURFACE_NON_WOODED,
            SURFACE_AGRICULTURAL, SURFACE_OTHER_NON_FOREST, SURFACE_BURNT)

#: How each surface reads in prose, for the Word document's opening paragraph. A
#: report of agricultural hectares that said only "areas in hectares" would be
#: indistinguishable from a report of forest ones.
SURFACE_PROSE = {
    SURFACE_FOREST: "total burnt forest area (SuperficieTotalForestal)",
    SURFACE_WOODED: "burnt wooded forest area (SuperficieArbolada)",
    SURFACE_NON_WOODED: "burnt non-wooded forest area (SuperficieNoArbolada)",
    SURFACE_AGRICULTURAL: "burnt agricultural area (SuperficieAgricola)",
    SURFACE_OTHER_NON_FOREST: "other burnt non-forest area (OtrasSuperficiesNoforestales)",
    SURFACE_BURNT: "all burnt area: forest plus agricultural plus other non-forest",
}

#: The campaign a fire counts towards. See the module docstring: the filing, not
#: the clock.
CAMPAIGN = EgifWildfire.__table__.c.campaign


def reported_surface(surface: str) -> tuple[ColumnElement, ColumnElement]:
    """The burnt area of one fire in hectares, as ``(hectares, is_reported)``.

    Parameters
    ----------
    surface : str
        One of :data:`SURFACES`.

    Returns
    -------
    tuple
        The SQL expression yielding hectares, and the condition a fire has to
        satisfy for that expression to be an answer rather than a silence.

    Raises
    ------
    ValueError
        If ``surface`` is not one of :data:`SURFACES`.

    Notes
    -----
    The second element is what keeps the ``Fires`` column honest. Every one of
    these columns is nullable, ``sum`` and ``min`` skip nulls and ``count`` does
    not, so a report that did not filter would count fires whose area it had not
    included. ``NULL`` here means the form does not say — not zero hectares.

    ``burnt`` is the one composite: a fire counts if any of the three components
    is reported, and the ones that are not contribute nothing. Requiring all three
    would discard most of the archive over an unreported column that is zero on
    the overwhelming majority of fires anyway.
    """
    fire = EgifWildfire.__table__.c

    simple = {
        SURFACE_FOREST: fire.area_ha_forest_total,
        SURFACE_WOODED: fire.area_ha_wooded,
        SURFACE_NON_WOODED: fire.area_ha_non_wooded,
        SURFACE_AGRICULTURAL: fire.area_ha_agricultural,
        SURFACE_OTHER_NON_FOREST: fire.area_ha_other_non_forest,
    }
    if surface in simple:
        column = simple[surface]
        return column, column.is_not(None)

    if surface == SURFACE_BURNT:
        components = (fire.area_ha_forest_total, fire.area_ha_agricultural,
                      fire.area_ha_other_non_forest)
        hectares = (func.coalesce(components[0], 0.0)
                    + func.coalesce(components[1], 0.0)
                    + func.coalesce(components[2], 0.0))
        return hectares, or_(*[component.is_not(None) for component in components])

    raise ValueError(
        f"unknown surface {surface!r}; expected one of {', '.join(SURFACES)}"
    )


def statistics_query(surface: str = SURFACE_FOREST,
                     year: int | None = None,
                     min_area: float | None = None) -> Select:
    """Build the statistics query: one row per campaign, newest first.

    Parameters
    ----------
    surface : str
        One of :data:`SURFACES`.
    year : int, optional
        Restrict to one campaign. ``None``, the default, reports every campaign.
    min_area : float, optional
        Count only fires of at least this many hectares of the chosen surface.
        ``None``, the default, counts every fire.

    Returns
    -------
    Select
        A query yielding ``year, minimum, maximum, total, fires``. The summary row
        is :func:`summarise`'s work.

    Notes
    -----
    Built against the mapped class rather than written as SQL text, so a column
    renamed on the model breaks this at import time rather than in front of a user.

    Selected from ``egif_wildfire`` alone: everything this report reads —
    the campaign and the five reported areas — is on that table, so the parent
    ``wildfire`` row is not joined at all. By table and not through the mapped
    class, to keep SQLAlchemy from adding a polymorphic join of its own.

    The inner query computes each area exactly once. Folded into the outer
    aggregate instead, the ``burnt`` expression would be evaluated three times per
    row, for the minimum, the maximum and the sum.

    ``min_area`` filters that subquery's column rather than repeating the
    expression, and is applied before the aggregates rather than as a ``HAVING``:
    the threshold selects the fires the figures are computed from, it does not
    discard years whose total came out small.
    """
    hectares, is_reported = reported_surface(surface)

    fires = (
        select(CAMPAIGN.label("year"), hectares.label("hectares"))
        .select_from(EgifWildfire.__table__)
        .where(is_reported)
    )
    if year is not None:
        fires = fires.where(CAMPAIGN == year)

    fire = fires.subquery("fire")
    statistics = (
        select(
            fire.c.year,
            func.min(fire.c.hectares).label("minimum"),
            func.max(fire.c.hectares).label("maximum"),
            func.sum(fire.c.hectares).label("total"),
            func.count().label("fires"),
        )
        .group_by(fire.c.year)
        .order_by(fire.c.year.desc())
    )
    if min_area is not None:
        statistics = statistics.where(fire.c.hectares >= min_area)
    return statistics


@dataclass(frozen=True)
class Row:
    """One line of the report.

    Attributes
    ----------
    country : str
        Always :data:`COUNTRY_NAME`; kept as a field so that this report's rows
        are the same shape as the other three's.
    year : int or None
        The campaign, or ``None`` for the summary row.
    minimum, maximum, total : float
        Smallest single fire, largest single fire and sum of every fire, in
        hectares of the surface asked for.
    fires : int
        How many fires the three area figures were computed from — the fires of
        this campaign that report that surface, or of the whole period for the
        summary row.
    """

    country: str
    year: int | None
    minimum: float
    maximum: float
    total: float
    fires: int

    @property
    def is_total(self) -> bool:
        """Whether this is the summary row rather than one of the campaigns."""
        return self.year is None

    @property
    def year_label(self) -> str:
        return TOTAL_LABEL if self.is_total else str(self.year)


def combine(rows: list[Row], year: int | None = None) -> Row:
    """One row summarising several: the four figures taken over all of them.

    Notes
    -----
    All four decompose over a partition of the fires — a minimum of minima is a
    minimum, a sum of sums is a sum — so the ``Total`` row is the number a second
    aggregate over the same rows would have returned, and no fire is counted twice
    or left out.

    ``fsum`` rather than ``sum``: an exact accumulation over a handful of partial
    totals costs nothing and cannot drift from what one pass would have returned.
    """
    return Row(
        country=COUNTRY_NAME,
        year=year,
        minimum=min(row.minimum for row in rows),
        maximum=max(row.maximum for row in rows),
        total=math.fsum(row.total for row in rows),
        fires=sum(row.fires for row in rows),
    )


def summarise(measured: list[Row]) -> list[Row]:
    """The report: the campaigns newest first, then the summary row.

    Parameters
    ----------
    measured : list of Row
        One row per campaign, as the statement returned them.

    Returns
    -------
    list of Row
        Empty if nothing was measured — a report of no fires has no total either.
    """
    if not measured:
        return []
    return sorted(measured, key=lambda row: row.year, reverse=True) + [combine(measured)]


def hectares(text: str) -> float:
    """Argparse type for ``--min-area``: a finite, non-negative number of hectares.

    Raises
    ------
    argparse.ArgumentTypeError
        If the text is not a number, or is negative, or is a non-finite float.

    Notes
    -----
    A bare ``type=float`` would accept ``-5``, ``nan`` and ``inf``. The first two
    are almost certainly a typo and would silently produce the unfiltered report —
    ``nan`` compares false against every area, so it would produce an empty one —
    and none of the three is a size a fire can have.
    """
    try:
        area = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of hectares")
    if not math.isfinite(area):
        raise argparse.ArgumentTypeError(f"{text!r} is not a finite number of hectares")
    if area < 0:
        raise argparse.ArgumentTypeError(
            f"a burnt area cannot be negative, and {area:g} ha is: pass 0 or more, or "
            f"leave --min-area out to count every fire"
        )
    return area


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Burnt-area statistics for the Spanish EGIF fire statistics.",
        epilog="Areas are the hectares EGIF reports, not a measured perimeter: EGIF "
               "publishes no polygon, so there is no --area-method. Spain is the only "
               "country, so there is no --country. Database settings not given here are "
               "read from the environment (.env).",
    )
    parser.add_argument("-y", "--year", type=int,
                        help="restrict to one campaign, e.g. 2023; this is the filed "
                             "Campania, not the year of the detection date")
    parser.add_argument("--surface", default=SURFACE_FOREST, choices=SURFACES,
                        help="which reported burnt area to report: 'forest' (default) is "
                             "SuperficieTotalForestal, the figure the national statistic "
                             "is quoted in; 'wooded' and 'non-wooded' are the two parts it "
                             "is the sum of; 'agricultural' and 'other-non-forest' are "
                             "outside it; 'burnt' adds all three together, which EGIF does "
                             "not publish")
    parser.add_argument("--min-area", type=hectares, default=None, metavar="HECTARES",
                        help="count only fires that burnt at least this many hectares of "
                             "the chosen surface; by default every fire that reports one "
                             "counts, including a reported zero")

    # Accepted only so that they can be refused clearly. Anyone reaching for either
    # has copied a command line from the GWIS, GFA or ICNF report, which is a
    # reasonable thing to have done, and argparse's own "unrecognized arguments"
    # would not say why this report is different.
    parser.add_argument("--country", help=argparse.SUPPRESS)
    parser.add_argument("--area-method", help=argparse.SUPPRESS)

    output = parser.add_argument_group("output", "at least one is required")
    output.add_argument("--csv", type=Path, help="write the report to this .csv")
    output.add_argument("--docx", type=Path, help="write the report to this .docx (MS Word)")

    common.add_database_arguments(parser)
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")

    arguments = parser.parse_args(argv)
    if arguments.country is not None:
        parser.error(
            "there is no --country here: EGIF is the Spanish national statistic, so "
            f"every fire in it is filed in {COUNTRY_NAME} and there is nothing to select "
            "between. The Country column says so on every row."
        )
    if arguments.area_method is not None:
        parser.error(
            "there is no --area-method here: EGIF publishes no perimeter, so nothing is "
            "measured and no CRS is involved. The hectares are the ones on the report "
            "form — use --surface to choose which of them."
        )
    if arguments.csv is None and arguments.docx is None:
        parser.error("nothing to write: pass --csv, --docx, or both")
    return arguments


def compute(session: Session, year: int | None, logger: logging.Logger,
            surface: str = SURFACE_FOREST,
            min_area: float | None = None) -> list[Row]:
    """Run the statement and return the report's rows in order.

    Notes
    -----
    One statement, under one spinner — see the module docstring for why this
    report does not need the year-at-a-time machinery the other three are built
    on. The ``Total`` row is arithmetic over its result, not a second query.
    """
    with common.Spinner(f"Measuring the reported {surface} area of the EGIF fires", logger):
        measured = [
            Row(country=COUNTRY_NAME, year=record.year,
                minimum=float(record.minimum),
                maximum=float(record.maximum),
                total=float(record.total),
                fires=record.fires)
            for record in session.execute(statistics_query(surface, year, min_area))
        ]

    rows = summarise(measured)
    logger.info("Computed %d rows over %d campaign(s) (%s area, %s)",
                len(rows), len(measured), surface,
                "every fire" if min_area is None else f"fires of {min_area:g} ha or more")
    return rows


def write_csv(rows: list[Row], path: Path, logger: logging.Logger) -> None:
    """Write the report as CSV.

    The numbers go out unformatted apart from being rounded to two decimals — no
    thousands separators — because a CSV is read by another program far more often
    than by a person, and a separator would make every figure a string.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([row.country, row.year_label, row.fires,
                             f"{row.minimum:.2f}", f"{row.maximum:.2f}", f"{row.total:.2f}"])
    logger.info("Wrote %s", path)


def write_docx(rows: list[Row], path: Path, year: int | None,
               logger: logging.Logger,
               surface: str = SURFACE_FOREST,
               min_area: float | None = None) -> None:
    """Write the report as a Word document.

    One table, with the summary row in bold. Numbers get thousands separators here
    — the opposite of the CSV, and for the opposite reason: this one is for
    reading.

    The opening paragraph names the surface, the scope and the incompleteness of a
    freshly exported campaign, because a table of agricultural hectares and a
    table of forest ones look exactly alike, and a total that is a floor rather
    than a year's burnt area should not have to be remembered by the reader.
    """
    # Imported here rather than at module scope so that --csv keeps working if
    # python-docx is not installed, which matters because it is the only
    # dependency this application adds.
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    document.add_heading(f"EGIF wildfire burnt area ({COUNTRY_NAME})", level=1)

    scope = [f"campaign: {year}" if year is not None else "all campaigns"]
    if min_area is not None:
        scope.append(f"only fires of {min_area:g} ha or more")
    document.add_paragraph(
        f"Areas in hectares as reported by EGIF — {SURFACE_PROSE[surface]} — and not "
        f"measured from a perimeter, which EGIF does not publish. Fires that do not "
        f"report this area are excluded; a reported zero is counted. Years are the filed "
        f"Campania. Scope: {'; '.join(scope)}."
    )
    document.add_paragraph(
        "A campaign's total is a floor: the service exports only fires it has closed and "
        "reviewed, so a recently exported year is missing whole regions and will grow "
        "when it is re-imported."
    )

    table = document.add_table(rows=1, cols=len(COLUMNS))
    table.style = "Table Grid"
    for cell, heading in zip(table.rows[0].cells, COLUMNS):
        cell.text = heading
        cell.paragraphs[0].runs[0].bold = True

    for row in rows:
        cells = table.add_row().cells
        values = [row.country, row.year_label, f"{row.fires:,}",
                  f"{row.minimum:,.2f}", f"{row.maximum:,.2f}", f"{row.total:,.2f}"]
        for index, (cell, value) in enumerate(zip(cells, values)):
            cell.text = value
            paragraph = cell.paragraphs[0]
            if index >= FIRST_NUMERIC_COLUMN:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for run in paragraph.runs:
                run.bold = row.is_total
                run.font.size = Pt(9)

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    logger.info("Wrote %s", path)


def report(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> list[Row]:
    """Compute the statistics and write whichever outputs were asked for."""
    with Session(engine) as session:
        rows = compute(session, args.year, logger, args.surface, args.min_area)

    if not rows:
        # An empty report is almost always a campaign with no data, and writing an
        # empty file would hide that. The surface is named because asking for one
        # the export does not fill in is the other likely reason, and so is the
        # threshold when there is one.
        threshold = "" if args.min_area is None else \
            f" No fire reached the --min-area of {args.min_area:g} ha."
        raise RuntimeError(
            f"No wildfires matched. Check --year, and that the EGIF fires are imported "
            f"and report a {args.surface} area — fires that do not report the surface "
            f"asked for are not counted." + threshold
        )

    if args.csv is not None:
        write_csv(rows, args.csv, logger)
    if args.docx is not None:
        write_docx(rows, args.docx, args.year, logger, args.surface, args.min_area)
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("egif-statistics")

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
