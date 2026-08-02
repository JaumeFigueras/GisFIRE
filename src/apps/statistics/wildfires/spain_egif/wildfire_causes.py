#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wildfire counts by cause for the Spanish EGIF fire statistics.

Reports, per campaign, how many fires there were, how many carry a cause at all,
how many of those were started by **lightning**, and then the same three counts
again over the fires whose published ignition point really falls inside Spain::

    Country  Year   Fires  Classified  Lightning  Lightning %  Fires inside  ...
    Spain    2023    6294        6294        271         4.31          6290  ...
    Spain    2022    7362        7362        198         2.69          7358  ...
    Spain    Total  13656       13656        469         3.43         13648  ...

Run it over everything, or narrow it to one campaign, or count a different
family of causes::

    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes --csv causes.csv
    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \\
        --year 2023 --csv 2023.csv --docx 2023.docx
    python3 -m src.apps.statistics.wildfires.spain_egif.wildfire_causes \\
        --cause-family intentional --csv arson.csv

At least one of ``--csv`` and ``--docx`` is required.

The companion of
:mod:`~src.apps.statistics.wildfires.spain_egif.wildfire_statistics`, over the
same archive and the same campaigns. What that one measures in hectares, this one
counts by cause.

EGIF does publish lightning
---------------------------

Unlike the ICNF — whose
:mod:`counterpart <src.apps.statistics.wildfires.portugal_icnf.wildfire_causes>`
has to fall back on ``Natural`` and say at length that it is a proxy — **EGIF names
lightning outright**. ``idcausa`` is a three-digit code whose first digit is the
family, and the ``1`` family is :data:`~src.providers.spain_egif.CAUSE_LIGHTNING`,
*Rayo*. So the default column of this report is ``Lightning`` and it means
lightning; there is no proxy to apologise for.

Matching is on the **family digit** and not on the exact code. ``100`` is today the
whole of the family, but the catalogue is versioned — the *Instrucciones para
cumplimentar el parte de incendio forestal* are at v3.6, *9ª actualización*, and
every revision so far has added subcodes — so a future ``101`` *Rayo seco* is
counted the day it appears rather than the day someone notices this file.

``--cause-family`` counts one of the other five instead; see
:data:`CAUSE_FAMILIES`. The digits of the four families the provider module names
are taken from its constants rather than written out again here.

Which fires are counted, and why it is not the companion's rule
---------------------------------------------------------------

**Every EGIF fire of the campaign.** There is no ``--surface`` and no
``--min-area``: this report counts fires, and a fire whose report form leaves the
burnt area blank is still a fire.

That is a deliberate divergence from the ICNF pair, whose two reports are built to
agree row for row. They can here, because the companion report **excludes any fire
that does not report the surface asked for** — it has to, or its ``Fires`` column
would stop counting the fires its three area figures were computed from. So:

.. warning::

   Do not expect this report's ``Fires`` column to match
   :mod:`~src.apps.statistics.wildfires.spain_egif.wildfire_statistics`'s. That one
   counts the fires that reported a burnt area; this one counts the fires. The
   difference is exactly the fires with a blank surface on the form, and it is a
   real property of the archive rather than a disagreement.

The points outside the border
-----------------------------

EGIF has no perimeter, but it does have a **point** — the published ignition
coordinate on :class:`~src.providers.spain_egif.ignition.EgifIgnition` — and that
point can be somewhere a Spanish fire is not. The importer's only geometric guard
is a plausibility box on the published easting and northing
(:data:`~src.providers.spain_egif.PLAUSIBLE_UTM_EASTING`), which is a rectangle
containing a great deal of Atlantic and Mediterranean; and where the published
*huso* is not a zone Spain lies in, the zone is replaced with the modal one for the
province, which can walk a coastal point out to sea or over a border.

So the report gives the counts **twice**. The first three columns are every fire
EGIF filed. The ``... inside`` columns are the fires whose point the database finds
inside the real Spanish polygon, tested against the OCHA country outlines at report
time. The gap between the two blocks is the answer to "how much of this can be
placed on the ground", and ``Fires inside (%)`` is that gap as a number.

Unlike the companion report this is **not an option**, because nothing is dropped
by it: a fire that is not inside still counts in the first block. The companion has
a ``--country-source`` precisely because there the test *removes* fires, and
switching it on silently halves the archive; here both answers are in the same row
and neither hides the other.

A fire is *outside* for three quite different reasons, and the log separates them
rather than adding them up:

*no point published*
    An ordinary property of the archive, and the big number: **293,710 of the
    586,157 fires of 1982-2023 publish no coordinate at all**, every fire before
    1998 among them. It says nothing whatsoever about the fires that do have one.
*a point in no country*
    A coordinate in the sea — the data fault the plausibility box lets through.
    This is the number to watch.
*a point in another country*
    A coordinate over the French or Portuguese border. Reported by name in the log,
    because a handful is a rounding error and a systematic drift is a bug in a
    province's zone fallback.

The fire is still Spanish in every case: it is a Spanish *parte*, so the
``Country`` column is the constant :data:`~...wildfire_statistics.COUNTRY_NAME` on
every row and a fire is never moved into France's total. This report is about one
country's statistic, and "which country contains the point" is a question about the
coordinate rather than about the fire.

.. note::

   If the OCHA country boundaries are not imported there is no Spanish polygon to
   be inside, every ``... inside`` column is zero, and the report says so at
   ``WARNING`` rather than letting a table of zeros pass for an answer.

Which year a fire counts towards
--------------------------------

:attr:`~src.providers.spain_egif.wildfire.EgifWildfire.campaign`, the filed
``Campania``, exactly as in the companion report and for the same reasons: it is
what a published yearly total is a total of, it is ``NOT NULL`` and indexed, and it
needs no timezone applied to it.

One statement
-------------

One, for the whole report, exactly as the companion. The grouping is by campaign
**and placement**, so the two blocks of counts, the ``Total`` row and the whole
outside-the-border audit all come out of a single pass — which means the
point-in-polygon test is paid once per fire rather than once per number.

Shared with the companion report
--------------------------------

The country name, the country level, the campaign column, the ``Total`` label and
the country ordering are **imported from**
:mod:`~src.apps.statistics.wildfires.spain_egif.wildfire_statistics` rather than
copied. Two reports over one dataset that disagreed about which campaign a fire is
filed under would be worse than one report, and a copy is a thing that drifts.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import Select
from sqlalchemy import Subquery
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import literal
from sqlalchemy import select
from sqlalchemy import true
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.apps.statistics.wildfires.spain_egif.wildfire_statistics import CAMPAIGN
from src.apps.statistics.wildfires.spain_egif.wildfire_statistics import COUNTRY_LEVEL
from src.apps.statistics.wildfires.spain_egif.wildfire_statistics import COUNTRY_NAME
from src.apps.statistics.wildfires.spain_egif.wildfire_statistics import TOTAL_LABEL
from src.apps.statistics.wildfires.spain_egif.wildfire_statistics import ordered_countries
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.ignition import Ignition
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.spain_egif import CAUSE_INTENTIONAL
from src.providers.spain_egif import CAUSE_LIGHTNING
from src.providers.spain_egif import CAUSE_REKINDLE
from src.providers.spain_egif import CAUSE_UNKNOWN
from src.providers.spain_egif.fire_cause import EgifFireCause
from src.providers.spain_egif.wildfire import EgifWildfire


@dataclass(frozen=True)
class Family:
    """One family of EGIF causes: the leading digit of ``idcausa``, and its names.

    Attributes
    ----------
    digit : str
        The first character of every ``idcausa`` in the family, which is what the
        report matches on. See the module docstring for why the family and not the
        exact code.
    label : str
        English name, used for the report's column headings.
    spanish : str
        The family as the EGIF classification names it, for the prose that has to
        be checkable against the source.
    """

    digit: str
    label: str
    spanish: str


#: The six families of ``idcausa``, keyed by what ``--cause-family`` accepts.
#:
#: The digits of the four families :mod:`src.providers.spain_egif` names are taken
#: from its constants rather than written out again, so a renumbering there cannot
#: leave this report counting the old digit. ``2`` and ``3`` have no constant —
#: they are families of subcodes with no bare parent — and are spelled out.
#:
#: The ``2``/``3`` boundary is close to "with or without an implicit use of fire"
#: but is not clean at the edges: ``292`` *Fuegos artificiales* is in the first and
#: ``300`` *Quema de cables para extraer cobre* in the second.
CAUSE_FAMILIES = {
    "lightning": Family(CAUSE_LIGHTNING[0], "Lightning", "Rayo"),
    "negligence": Family("2", "Negligence", "Negligencias (uso del fuego)"),
    "accident": Family("3", "Accident", "Causas accidentales (sin uso del fuego)"),
    "intentional": Family(CAUSE_INTENTIONAL[0], "Intentional", "Intencionado"),
    "unknown": Family(CAUSE_UNKNOWN[0], "Unknown", "Desconocida"),
    "rekindle": Family(CAUSE_REKINDLE[0], "Rekindle", "Reproducido"),
}

#: The family counted unless ``--cause-family`` says otherwise. EGIF names it
#: outright, so this column is lightning and not a proxy for it — see the module
#: docstring, and contrast the ICNF report, which has no such category to count.
DEFAULT_FAMILY = "lightning"

#: Index of the first column that holds a number, and so is right-aligned in the
#: Word table.
FIRST_NUMERIC_COLUMN = 2


def columns(family: str = DEFAULT_FAMILY) -> tuple[str, ...]:
    """The report's columns, in order, for a given cause family.

    Notes
    -----
    A function rather than a constant, for the ICNF companion's reason: three of the
    headings name the family being counted, and a file of intentional fires counted
    under a heading saying ``Lightning`` would be a trap.

    Both output formats read them from here, so a change to one cannot silently
    leave the other behind. The first three are the companion report's first three,
    unchanged.
    """
    label = cause_family(family).label
    return (
        "Country", "Year", "Fires", "Classified", label,
        f"{label} (% of classified)",
        "Fires inside", "Fires inside (%)", "Classified inside",
        f"{label} inside", f"{label} inside (% of classified inside)",
    )


def cause_family(family: str) -> Family:
    """Look a family up by the name ``--cause-family`` accepts.

    Raises
    ------
    ValueError
        If ``family`` is not one of :data:`CAUSE_FAMILIES`.
    """
    try:
        return CAUSE_FAMILIES[family]
    except KeyError:
        raise ValueError(
            f"unknown cause family {family!r}; expected one of "
            f"{', '.join(CAUSE_FAMILIES)}"
        ) from None


def fire_details(year: int | None = None) -> Subquery:
    """One row per EGIF fire: its campaign, its cause and where its point is.

    Parameters
    ----------
    year : int, optional
        Restrict to one campaign. ``None``, the default, covers every campaign.

    Returns
    -------
    Subquery
        Columns ``country, year, cause_id, code, has_point, placement``. The
        counting is :func:`counts_query`'s work; this is only the per-fire fact
        table both blocks of the report are aggregated from.

    Notes
    -----
    **Every join here is outer, and each of the three has to be.** The join to
    ``egif_fire_cause`` would otherwise drop the unclassified fires, the join to
    ``ignition`` the fires that publish no coordinate — half the archive — and the
    lateral the fires whose coordinate is inside no country. All three belong in the
    first block of counts; what they are missing is exactly what the second block
    and the log audit are for.

    ``placement`` is the name of the country whose polygon contains the point, or
    ``NULL`` where there is no point or no such country. It is a name and not a
    boolean because the three ways of being outside mean entirely different things —
    see the module docstring — and a boolean would flatten them into one.

    ``ORDER BY (name = COUNTRY_NAME) DESC LIMIT 1`` inside the lateral: a point on a
    shared border can satisfy ``ST_Contains`` for two countries, and one fire must
    not become two rows. Sorting Spain first means such a point is called *inside*
    rather than reported as a border crossing, which is the reading that does not
    invent a foreign fire out of a rounding error in a polygon.

    The join to ``ocha_admin_boundary`` keeps the test against the OCHA country
    outlines rather than against every level-0 boundary any provider has loaded.
    """
    egif = EgifWildfire.__table__
    cause = EgifFireCause.__table__
    ignition = Ignition.__table__
    ocha_boundary = OchaAdminBoundary.__table__

    containing = (
        select(AdminBoundary.name.label("name"))
        .select_from(AdminBoundary)
        .join(ocha_boundary, ocha_boundary.c.id == AdminBoundary.id)
        .where(AdminBoundary.level == COUNTRY_LEVEL)
        .where(func.ST_Contains(AdminBoundary.geometry, ignition.c.geometry))
        .order_by((AdminBoundary.name == COUNTRY_NAME).desc())
        .limit(1)
        .lateral("containing")
    )

    fires = (
        select(
            literal(COUNTRY_NAME).label("country"),
            CAMPAIGN.label("year"),
            egif.c.cause_id.label("cause_id"),
            cause.c.code.label("code"),
            egif.c.ignition_id.is_not(None).label("has_point"),
            containing.c.name.label("placement"),
        )
        .select_from(egif)
        .outerjoin(cause, cause.c.id == egif.c.cause_id)
        .outerjoin(ignition, ignition.c.id == egif.c.ignition_id)
        .outerjoin(containing, true())
    )
    if year is not None:
        fires = fires.where(CAMPAIGN == year)
    return fires.subquery("fire")


def counts_query(year: int | None = None, family: str = DEFAULT_FAMILY) -> Select:
    """Build the counting query: three counts per campaign and placement.

    Parameters
    ----------
    year : int, optional
        Restrict to one campaign.
    family : str
        One of :data:`CAUSE_FAMILIES`.

    Returns
    -------
    Select
        A query yielding ``country, year, has_point, placement, fires, classified,
        matching``, newest campaign first. Both blocks of the report, the ``Total``
        row and the audit are folded out of this by :func:`summarise` and
        :func:`placements`.

    Notes
    -----
    Grouping by the placement as well as the campaign is what makes this **one
    statement**. The ``... inside`` columns are the group whose placement is Spain,
    the audit is the groups that are not, and neither needs a second pass — which
    matters because the point-in-polygon test is the only expensive thing here and
    is thereby paid once per fire rather than once per number.

    ``count(cause_id)`` and not ``count(*)`` for the classified column: counting a
    nullable column counts the rows where it is filled in, which is the definition
    of classified. EGIF's Excel export classifies every fire, so the two are usually
    equal — but an XML import into a database whose cause catalogue was never
    seeded cannot resolve one, and that is a case worth being able to see.

    The family is matched on the first character of the published ``idcausa``. See
    the module docstring: the code is hierarchical and the catalogue is versioned,
    so a subcode a later edition adds is counted without a second edit here.
    """
    fire = fire_details(year)
    matches = func.substr(fire.c.code, 1, 1) == cause_family(family).digit

    return (
        select(
            fire.c.country,
            fire.c.year,
            fire.c.has_point,
            fire.c.placement,
            func.count().label("fires"),
            func.count(fire.c.cause_id).label("classified"),
            func.count().filter(matches).label("matching"),
        )
        .group_by(fire.c.country, fire.c.year, fire.c.has_point, fire.c.placement)
        .order_by(fire.c.year.desc())
    )


def country_geometry_query() -> Select:
    """Count the OCHA country polygons a fire could be found inside of.

    Returns
    -------
    Select
        A query yielding a single number: how many level-0 OCHA boundaries are named
        :data:`~...wildfire_statistics.COUNTRY_NAME`.

    Notes
    -----
    Asked only when the report found no fire inside the country at all, which has
    two possible meanings: every published coordinate really is outside — which
    would be extraordinary — or the boundaries were never imported. The second is
    overwhelmingly likelier and produces a table of zeros that looks exactly like an
    answer, so it is worth one cheap statement to tell them apart.
    """
    ocha_boundary = OchaAdminBoundary.__table__
    return (
        select(func.count())
        .select_from(AdminBoundary)
        .join(ocha_boundary, ocha_boundary.c.id == AdminBoundary.id)
        .where(AdminBoundary.level == COUNTRY_LEVEL)
        .where(AdminBoundary.name == COUNTRY_NAME)
    )


@dataclass(frozen=True)
class Group:
    """The fires of one campaign that share a placement, as the statement grouped them.

    Attributes
    ----------
    country : str
        The country the fires are filed in, always
        :data:`~...wildfire_statistics.COUNTRY_NAME`.
    year : int
        The filed campaign.
    has_point : bool
        Whether these fires publish an ignition coordinate at all.
    placement : str or None
        Name of the country whose polygon contains that coordinate, or ``None``
        where there is no coordinate or no such country.
    fires, classified, matching : int
        How many fires, how many of them carry a cause, and how many of those are
        of the family asked for.

    Notes
    -----
    An intermediate rather than a line of the report: :func:`summarise` folds these
    into :class:`Row`\\ s and :func:`placements` reads the audit off the same list.
    The pair ``(has_point, placement)`` takes exactly four values in practice —
    ``(False, None)``, ``(True, None)``, ``(True, 'Spain')`` and ``(True, <a
    neighbour>)`` — which is why grouping on it is cheap.
    """

    country: str
    year: int
    has_point: bool
    placement: str | None
    fires: int
    classified: int
    matching: int

    @property
    def is_inside(self) -> bool:
        """Whether these fires' points fall inside the country they are filed in."""
        return self.placement == COUNTRY_NAME


def share(part: int, whole: int) -> float | None:
    """``part`` as a percentage of ``whole``, or ``None`` where there is no whole.

    ``None`` and not zero: a percentage of nothing is not zero percent, it is no
    answer, and the writers turn it into an empty cell. A campaign in which no fire
    was classified has no lightning share to report, and a zero there would be a
    claim that none of its fires was a lightning fire.
    """
    if not whole:
        return None
    return 100.0 * part / whole


def share_label(part: int, whole: int) -> str:
    """A percentage as it is written out, empty where there is none."""
    value = share(part, whole)
    return "" if value is None else f"{value:.2f}"


@dataclass(frozen=True)
class Row:
    """One line of the report: the three counts, and the three counts inside.

    Attributes
    ----------
    country : str
        The country the fires are filed in. Always
        :data:`~...wildfire_statistics.COUNTRY_NAME` — see the module docstring on
        why a point over a border does not move the fire.
    year : int or None
        The filed campaign, or ``None`` for the summary row.
    fires : int
        Every fire EGIF filed under this campaign, whatever its form says and
        wherever its coordinate is.
    classified : int
        How many of them carry a cause at all.
    matching : int
        How many carry a cause of the family asked for.
    inside_fires : int
        How many of ``fires`` publish a coordinate that really is inside the
        country's polygon.
    inside_classified, inside_matching : int
        ``classified`` and ``matching`` over those fires alone.

    Notes
    -----
    ``matching <= classified <= fires``, and each ``inside_*`` is at most its
    counterpart. Both of the first two can be zero for entirely different reasons —
    nothing of that cause, or nothing classified — which is why they are separate
    columns and why the percentage names its denominator.
    """

    country: str
    year: int | None
    fires: int
    classified: int
    matching: int
    inside_fires: int
    inside_classified: int
    inside_matching: int

    @property
    def is_total(self) -> bool:
        """Whether this is the summary row rather than one of the campaigns."""
        return self.year is None

    @property
    def year_label(self) -> str:
        return TOTAL_LABEL if self.is_total else str(self.year)

    @property
    def share(self) -> float | None:
        """``matching`` as a percentage of ``classified``."""
        return share(self.matching, self.classified)

    @property
    def inside_share(self) -> float | None:
        """``inside_matching`` as a percentage of ``inside_classified``."""
        return share(self.inside_matching, self.inside_classified)

    @property
    def located_share(self) -> float | None:
        """``inside_fires`` as a percentage of ``fires``.

        How much of the campaign can be placed on the ground at all — the number
        that says how much weight the second block of counts will bear.
        """
        return share(self.inside_fires, self.fires)

    @property
    def values(self) -> tuple[str, ...]:
        """The row as the CSV writes it, in :func:`columns` order."""
        return (
            self.country, self.year_label, str(self.fires), str(self.classified),
            str(self.matching), share_label(self.matching, self.classified),
            str(self.inside_fires), share_label(self.inside_fires, self.fires),
            str(self.inside_classified), str(self.inside_matching),
            share_label(self.inside_matching, self.inside_classified),
        )

    @property
    def readable_values(self) -> tuple[str, ...]:
        """The row as the Word document writes it: the counts with separators."""
        return (
            self.country, self.year_label, f"{self.fires:,}", f"{self.classified:,}",
            f"{self.matching:,}", share_label(self.matching, self.classified),
            f"{self.inside_fires:,}", share_label(self.inside_fires, self.fires),
            f"{self.inside_classified:,}", f"{self.inside_matching:,}",
            share_label(self.inside_matching, self.inside_classified),
        )


def fold(groups: list[Group], country: str, year: int | None) -> Row:
    """One row from the groups it is made of: the counts added up.

    Notes
    -----
    Counts decompose over a partition of the fires, so a ``Total`` row folded from
    every campaign's groups is what a single pass over the same fires would have
    returned, and no fire is counted twice or left out.

    The percentages are deliberately **not** folded: they are recomputed by
    :class:`Row` from the summed counts, which is the ratio of the totals rather
    than the mean of the ratios. A campaign with eleven classified fires and one
    with eleven thousand must not weigh the same in the answer.
    """
    inside = [group for group in groups if group.is_inside]
    return Row(
        country=country,
        year=year,
        fires=sum(group.fires for group in groups),
        classified=sum(group.classified for group in groups),
        matching=sum(group.matching for group in groups),
        inside_fires=sum(group.fires for group in inside),
        inside_classified=sum(group.classified for group in inside),
        inside_matching=sum(group.matching for group in inside),
    )


def summarise(groups: list[Group], countries: list[str]) -> list[Row]:
    """Build the report from the groups counted: the summary rows, in order.

    Returns
    -------
    list of Row
        Each country, its campaigns newest first and its summary row last. Empty if
        nothing was counted — a report of no fires has no total either.
    """
    report: list[Row] = []
    for name in countries:
        mine = [group for group in groups if group.country == name]
        if not mine:
            continue
        for year in sorted({group.year for group in mine}, reverse=True):
            report.append(fold([group for group in mine if group.year == year], name, year))
        report.append(fold(mine, name, None))
    return report


@dataclass(frozen=True)
class Placement:
    """Where the fires' published coordinates turned out to be.

    Attributes
    ----------
    inside : int
        Points inside the country the fires are filed in.
    no_point : int
        Fires publishing no coordinate at all. Half the 1982-2023 archive, and an
        ordinary property of it rather than a fault.
    no_country : int
        Points inside no country's polygon — a coordinate in the sea, which is what
        the import's plausibility box on the UTM easting and northing lets through.
    elsewhere : tuple
        ``(country, fires)`` pairs for the points that landed over a border, sorted
        by name.

    Notes
    -----
    The four are counted apart and **never added up into a single "excluded"**,
    because they mean entirely different things about the data: the first is the
    answer, the second is the archive, the third is a data fault and the fourth is
    either a rounding error at the border or a systematically wrong UTM zone.
    """

    inside: int
    no_point: int
    no_country: int
    elsewhere: tuple[tuple[str, int], ...]

    @property
    def outside(self) -> int:
        """Every fire not found inside the country, however it failed to be."""
        return self.no_point + self.no_country + sum(count for _, count in self.elsewhere)


def placements(groups: list[Group]) -> Placement:
    """Read the placement audit off the groups the report was folded from.

    Notes
    -----
    No query of its own: the grouping :func:`counts_query` already does carries
    every distinction this needs, so the audit costs nothing beyond the arithmetic
    and cannot disagree with the table it accompanies.
    """
    elsewhere: Counter[str] = Counter()
    for group in groups:
        if group.placement is not None and not group.is_inside:
            elsewhere[group.placement] += group.fires

    return Placement(
        inside=sum(group.fires for group in groups if group.is_inside),
        no_point=sum(group.fires for group in groups if not group.has_point),
        no_country=sum(group.fires for group in groups
                       if group.has_point and group.placement is None),
        elsewhere=tuple(sorted(elsewhere.items())),
    )


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Wildfire counts by cause for the Spanish EGIF fire statistics.",
        epilog="EGIF names lightning outright — the 100 family, Rayo — so the default "
               "column is a count of lightning fires and not a proxy for one. Every fire "
               "is counted, and the '... inside' columns repeat the counts over the fires "
               "whose published ignition point really falls inside Spain. Spain is the "
               "only country, so there is no --country. Database settings not given here "
               "are read from the environment (.env).",
    )
    parser.add_argument("-y", "--year", type=int,
                        help="restrict to one campaign, e.g. 2023; this is the filed "
                             "Campania, not the year of the detection date")
    parser.add_argument("--cause-family", default=DEFAULT_FAMILY, choices=list(CAUSE_FAMILIES),
                        help="which family of idcausa to count, by the leading digit of "
                             "the code: 'lightning' (default) is the 100 family, Rayo. The "
                             "family and not the exact code, so a subcode a later edition "
                             "of the classification adds is counted as soon as it appears")

    # Accepted only so that they can be refused clearly. Anyone reaching for one has
    # copied a command line from the EGIF or ICNF statistics report, which is a
    # reasonable thing to have done, and argparse's own "unrecognized arguments"
    # would not say why this report is different.
    parser.add_argument("--country", help=argparse.SUPPRESS)
    parser.add_argument("--country-source", help=argparse.SUPPRESS)
    parser.add_argument("--cause-type", help=argparse.SUPPRESS)
    parser.add_argument("--surface", help=argparse.SUPPRESS)

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
            "between."
        )
    if arguments.country_source is not None:
        parser.error(
            "there is no --country-source here: this report gives both answers at once. "
            "The Fires, Classified and cause columns count every filed fire, and the "
            "'... inside' columns repeat them over the fires whose published point really "
            "falls inside the country. Nothing is dropped, so there is nothing to choose."
        )
    if arguments.cause_type is not None:
        parser.error(
            "there is no --cause-type here: that is the ICNF report's option, and EGIF "
            "publishes no Causa_Tipo. Its causes are a hierarchical three-digit idcausa — "
            "use --cause-family, whose choices are "
            f"{', '.join(CAUSE_FAMILIES)}."
        )
    if arguments.surface is not None:
        parser.error(
            "there is no --surface here: this report counts fires, not hectares, and a "
            "fire whose report form leaves the burnt area blank is still a fire. Use the "
            "companion wildfire_statistics report for the areas."
        )
    if arguments.csv is None and arguments.docx is None:
        parser.error("nothing to write: pass --csv, --docx, or both")
    return arguments


def compute(session: Session, year: int | None, logger: logging.Logger,
            family: str = DEFAULT_FAMILY) -> list[Row]:
    """Run the statement and return the report's rows in order.

    Notes
    -----
    One statement, under one spinner — see the module docstring. The ``Total`` row,
    the ``... inside`` columns and the placement audit are all arithmetic over its
    result rather than further queries.

    The one thing that can need a second, tiny statement is the case of nothing
    being found inside the country at all: :func:`country_geometry_query` tells a
    genuinely extraordinary archive apart from the far likelier missing import.
    """
    label = cause_family(family).label
    with common.Spinner("Counting the EGIF fires by cause and placing their points",
                        logger):
        groups = [
            Group(country=record.country, year=record.year,
                  has_point=record.has_point, placement=record.placement,
                  fires=record.fires, classified=record.classified,
                  matching=record.matching)
            for record in session.execute(counts_query(year, family))
        ]

    rows = summarise(groups, ordered_countries(session, {group.country for group in groups}))
    where = placements(groups)
    counted = sum(group.fires for group in groups)
    classified = sum(group.classified for group in groups)

    if groups and not classified:
        # An XML import into a database whose cause catalogue was never seeded,
        # almost always. A table of zeros with no explanation would look like an
        # answer rather than an absence.
        logger.warning(
            "No fire in scope carries a cause at all, so every %s count is zero and no "
            "percentage can be given: an XML import cannot resolve idcausa unless the "
            "cause catalogue has been seeded first", label)

    if counted:
        logger.info(
            "Of %d fire(s), %d have a point inside %s (%.2f%%): %d publish no point, "
            "%d publish a point in no country, %d publish a point in another country",
            counted, where.inside, COUNTRY_NAME,
            100.0 * where.inside / counted, where.no_point, where.no_country,
            sum(count for _, count in where.elsewhere))
    if where.no_country:
        logger.warning(
            "%d fire(s) have a published coordinate that is inside no country — a point "
            "in the sea survives import, whose only geometric guard is a plausibility box "
            "on the UTM easting and northing", where.no_country)
    for name, count in where.elsewhere:
        logger.warning(
            "%d fire(s) filed in %s have a published coordinate inside %s — a border "
            "rounding error at this scale, a wrong UTM zone at a larger one",
            count, COUNTRY_NAME, name)
    if counted and not where.inside:
        if not session.scalar(country_geometry_query()):
            logger.warning(
                "No OCHA level-0 boundary named %s is imported, so no fire can be found "
                "inside one and every '... inside' column is zero: import the OCHA "
                "country boundaries before reading them", COUNTRY_NAME)

    logger.info("Counted %d rows over %d campaign(s) (%s fires)",
                len(rows), len({row.year for row in rows if not row.is_total}), label)
    return rows


def write_csv(rows: list[Row], path: Path, logger: logging.Logger,
              family: str = DEFAULT_FAMILY) -> None:
    """Write the report as CSV.

    The counts go out bare and the percentages rounded to two decimals, with no
    thousands separators, because a CSV is read by another program far more often
    than by a person and a separator would make every figure a string.

    A percentage with no denominator is written **empty** — an empty field reads as
    no answer to whatever parses this, which is what it is, while a zero would read
    as an answer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns(family))
        for row in rows:
            writer.writerow(row.values)
    logger.info("Wrote %s", path)


def write_docx(rows: list[Row], path: Path, year: int | None,
               logger: logging.Logger, family: str = DEFAULT_FAMILY) -> None:
    """Write the report as a Word document.

    One table, with the summary row in bold, on a **landscape** page: eleven
    columns do not fit across a portrait one, and a table that wraps is a table
    nobody reads.

    Counts get thousands separators here — the opposite of the CSV, and for the
    opposite reason: this one is for reading.

    The opening paragraphs say what the two blocks of counts are and why they
    differ. Both belong in the document and not only in the manual: a reader who
    took the ``... inside`` columns for the whole archive would conclude that half
    of Spain's fires never happened.
    """
    # Imported here rather than at module scope so that --csv keeps working if
    # python-docx is not installed, which matters because it is the only
    # dependency this application adds.
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    kind = cause_family(family)
    headings = columns(family)

    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width

    document.add_heading(
        f"EGIF wildfire counts — {kind.label} causes ({COUNTRY_NAME})", level=1)

    scope = f"campaign: {year}" if year is not None else "all campaigns"
    document.add_paragraph(
        f"Counts of EGIF wildfires whose idcausa is of the {kind.digit} family "
        f"({kind.spanish} — {kind.label}). Every filed fire is counted, whether or not "
        f"its report form gives a burnt area and wherever its coordinate is. Years are "
        f"the filed Campania. Scope: {scope}."
    )
    document.add_paragraph(
        "The percentage is of the classified fires and not of all of them, and is left "
        "blank where nothing was classified."
    )
    document.add_paragraph(
        f"The four '... inside' columns repeat the counts over the fires whose published "
        f"ignition point the database finds inside the real {COUNTRY_NAME} polygon. They "
        f"are not the archive: EGIF publishes no coordinate at all for about half of the "
        f"1982-2023 fires, including every fire before 1998, and a published coordinate "
        f"can land in the sea or over a border. 'Fires inside (%)' is how much of each "
        f"campaign can be placed on the ground."
    )

    table = document.add_table(rows=1, cols=len(headings))
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, headings):
        cell.text = title
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(8)

    for row in rows:
        cells = table.add_row().cells
        for index, (cell, value) in enumerate(zip(cells, row.readable_values)):
            cell.text = value
            paragraph = cell.paragraphs[0]
            if index >= FIRST_NUMERIC_COLUMN:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for run in paragraph.runs:
                run.bold = row.is_total
                run.font.size = Pt(8)

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    logger.info("Wrote %s", path)


def report(args: argparse.Namespace, engine: Engine, logger: logging.Logger) -> list[Row]:
    """Count the fires and write whichever outputs were asked for."""
    with Session(engine) as session:
        rows = compute(session, args.year, logger, args.cause_family)

    if not rows:
        # An empty report is almost always a campaign with no data, and writing an
        # empty file would hide that. Note that a campaign with no fire of the
        # family asked for is not empty — it is a row of zeros, which is a
        # different thing and is reported as one.
        raise RuntimeError(
            "No wildfires matched. Check --year, and that the EGIF fires are imported — "
            "every filed fire is counted here, so an empty report means there are none "
            "in scope at all."
        )

    if args.csv is not None:
        write_csv(rows, args.csv, logger, args.cause_family)
    if args.docx is not None:
        write_docx(rows, args.docx, args.year, logger, args.cause_family)
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("egif-causes")

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
