#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bind CONAF's *incendio de magnitud* perimeters to the seasonal fire reports.

Fills
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.conaf_wildfire_id`
and the three columns beside it, so that the 743 mapped perimeters and the 95,865
fire reports become one view of the same fires.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires
   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires \\
         -y 2016 --csv /tmp/conaf-2016.csv
   $ python3 -m src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires \\
         --max-distance 0 --only-unbound

Import both datasets first. **Only the four binding columns are ever written**;
nothing else in either table is touched.

Unlike Canada, these are the same fires
-----------------------------------------

:mod:`src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires` binds two
agencies' independent accounts of Canadian fire, and a binding there is a claim that
two organisations were looking at the same event. Here both archives are **CONAF's
own record of its own incidents**, published twice, so a binding is a claim about
which two rows of one office's books describe one fire. That is a much easier thing
to be right about, and it is why this cascade can lean on a published running number
where the Canadian one has nothing but a distance and an agency code.

It is still not certain. There is no key: ``NUMERO_REG`` repeats within a season and
is unpublished for two of them, names repeat, and eleven of the thirteen perimeter
archives carry the number only as a prefix on the name.

The cascade
------------

Every report of the perimeter's season is a possible candidate. Each is labelled with
the **strongest** rule it satisfies, the best-labelled group is taken, and the binding
is written only if that group holds exactly one:

=============================================================================  ==========
Rule                                                                           Confidence
=============================================================================  ==========
:data:`~src.providers.chile_conaf_magnitud.MATCH_NUMBER_REGION_NAME_SEASON`    0.98
:data:`~src.providers.chile_conaf_magnitud.MATCH_NUMBER_REGION_INSIDE_SEASON`  0.96
:data:`~src.providers.chile_conaf_magnitud.MATCH_NUMBER_REGION_SEASON`         0.95
:data:`~src.providers.chile_conaf_magnitud.MATCH_NUMBER_NAME_SEASON`           0.93
:data:`~src.providers.chile_conaf_magnitud.MATCH_NAME_SEASON_INSIDE`           0.90
:data:`~src.providers.chile_conaf_magnitud.MATCH_NAME_SEASON`                  0.80
:data:`~src.providers.chile_conaf_magnitud.MATCH_INSIDE_SINGLE`                0.70
:data:`~src.providers.chile_conaf_magnitud.MATCH_NEAR_SINGLE`                  0.60
=============================================================================  ==========

A group of two or more ends the cascade rather than falling through to the next: the
labels are ordered by strength and every later group is a *weaker* kind of claim, not
a narrower set, so there is nothing below that could separate what the best evidence
could not.

A candidate that satisfies no rule is not a candidate. Being of the same season is
not evidence of anything.

.. note::

   The first two rules exist because **the número is not unique inside a región**,
   which is easy to assume it is. Binding on the pair alone leaves 93 perimeters
   ambiguous because each matches two reports; adding the name settles 83 of them and
   adding containment settles 77, and between them the two recover almost all.

   They are two rules rather than one because they are independent evidence: one is
   the text and the other the geometry, and a fire whose two candidates are named
   alike is settled by the second where the first cannot help.

The number is the strongest signal, and it is usually in the name
-------------------------------------------------------------------

Only 2022-2023 and 2023-2024 publish ``NUMERO_REG`` as a column. Six other archives
write it as a prefix on ``NOM_INCEN`` — ``'402 - SAN GUILLERMO'``,
``'944-LA AGUADA'``, ``'320_LAS MAQUINAS'`` — and
:func:`~src.providers.chile_conaf_magnitud.published_number` splits it off at import,
so by the time this runs 569 of the 743 perimeters carry a number in a column of
their own.

Names are compared :func:`~src.providers.chile_conaf.normalise` d, in Python, using
the same fold the imports used. Doing it here rather than in SQL is what lets the two
sides agree without an ``unaccent`` extension and a second copy of the rule — and the
archive needs it: the reports write ``'CHUFQUÉN'`` and the perimeters ``'Chufquen'``.

No report is bound twice
-------------------------

Nothing in the schema prevents two perimeters claiming one report — see
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.conaf_wildfire_id`
for why there is no unique constraint — so :func:`resolve_contested` enforces it here,
and drops **both** claims rather than picking one. Nothing in the data would make the
choice, and picking anyway is the silent wrong answer this application exists to
avoid.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import os
import sys

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports import common
from src.providers import chile_conaf
from src.providers.chile_conaf_magnitud import DEFAULT_MATCH_DISTANCE_M
from src.providers.chile_conaf_magnitud import MATCH_INSIDE_SINGLE
from src.providers.chile_conaf_magnitud import MATCH_METHOD_CONFIDENCE
from src.providers.chile_conaf_magnitud import MATCH_METHODS
from src.providers.chile_conaf_magnitud import MATCH_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NAME_SEASON_INSIDE
from src.providers.chile_conaf_magnitud import MATCH_NEAR_SINGLE
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_INSIDE_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_NAME_SEASON
from src.providers.chile_conaf_magnitud import MATCH_NUMBER_REGION_SEASON

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"

#: No report of the season satisfied any rule.
UNBOUND_NO_CANDIDATE = "no candidate"

#: Several reports satisfied the same strongest rule, and nothing separates them.
UNBOUND_AMBIGUOUS = "several candidates"

#: The report this perimeter would have taken is claimed by another perimeter too.
UNBOUND_REPORT_CONTESTED = "report claimed by another perimeter"

#: Every reason a perimeter can be left unbound.
UNBOUND_REASONS = (UNBOUND_NO_CANDIDATE, UNBOUND_AMBIGUOUS, UNBOUND_REPORT_CONTESTED)

#: The cascade's rules, strongest first. The same tuple as
#: :data:`~src.providers.chile_conaf_magnitud.MATCH_METHODS`, named here so that
#: :func:`rank_of` reads as the cascade rather than as an index into a constant.
RANKED_METHODS = MATCH_METHODS

#: Columns of the ``--csv`` report.
REPORT_COLUMNS = ("season", "perimeter_id", "number", "name", "region_code",
                  "area_ha_mapped", "outcome", "method", "confidence", "metres",
                  "report_id", "report_number", "report_name", "report_region_code",
                  "report_area_ha_total", "report_start", "candidates")

#: The seasons that have perimeters to bind.
SEASONS_SQL = """
SELECT DISTINCT season_start_year
FROM conaf_magnitud_wildfire
WHERE (NOT CAST(:only_unbound AS boolean) OR conaf_wildfire_id IS NULL)
  AND (CAST(:season AS integer) IS NULL OR season_start_year = CAST(:season AS integer))
ORDER BY season_start_year
"""

#: The perimeters of one season, with what the cascade compares.
PERIMETERS_SQL = """
SELECT m.id AS id,
       m.season_start_year AS season_start_year,
       m.number AS number,
       m.name AS name,
       m.region_code AS region_code,
       m.area_ha_mapped AS area_ha_mapped
FROM conaf_magnitud_wildfire m
WHERE m.season_start_year = :season
  AND (NOT CAST(:only_unbound AS boolean) OR m.conaf_wildfire_id IS NULL)
ORDER BY m.id
"""

#: Every report of one season, with what the cascade compares.
#:
#: All of them, not only the ones near a perimeter: the number and the name rules are
#: not spatial, and a report whose point was filed at the office rather than at the
#: fire is exactly the case they exist to catch. A season is a few thousand rows.
REPORTS_SQL = """
SELECT f.id AS id,
       f.number AS number,
       f.name AS name,
       f.region_code AS region_code,
       f.area_ha_total AS area_ha_total,
       w.start_date_time AS start_date_time
FROM conaf_wildfire f
JOIN wildfire w ON w.id = f.id
WHERE f.season_start_year = :season
"""

#: Which reports of the season lie inside, or near, each perimeter of it.
#:
#: The comparison is made on the published grid, in metres, and on **whichever of the
#: two grids** the pair is on: a mainland perimeter against a mainland point, an
#: Easter Island perimeter against an Easter Island point. A cross-territory pair
#: matches neither branch and is not a candidate, which is right — Rapa Nui is 3,500
#: km off the coast.
#:
#: ``ST_DWithin`` is what uses the GiST indexes, so the distance filter runs before
#: the exact ``ST_Distance``. When ``--max-distance`` is 0 it degenerates to
#: containment, which is the intended reading of that setting.
SPATIAL_SQL = """
SELECT m.id AS perimeter_id,
       f.id AS report_id,
       CASE WHEN m.perimeter_utm19s IS NOT NULL
            THEN ST_Distance(m.perimeter_utm19s, p.geometry_utm19s)
            ELSE ST_Distance(m.perimeter_utm12s, p.geometry_utm12s)
       END AS metres,
       CASE WHEN m.perimeter_utm19s IS NOT NULL
            THEN ST_Contains(m.perimeter_utm19s, p.geometry_utm19s)
            ELSE ST_Contains(m.perimeter_utm12s, p.geometry_utm12s)
       END AS inside
FROM conaf_magnitud_wildfire m
JOIN conaf_wildfire f ON f.season_start_year = m.season_start_year
JOIN conaf_ignition p ON p.id = f.ignition_id
WHERE m.season_start_year = :season
  AND (NOT CAST(:only_unbound AS boolean) OR m.conaf_wildfire_id IS NULL)
  AND ((m.perimeter_utm19s IS NOT NULL AND p.geometry_utm19s IS NOT NULL
        AND ST_DWithin(m.perimeter_utm19s, p.geometry_utm19s, :max_distance))
    OR (m.perimeter_utm12s IS NOT NULL AND p.geometry_utm12s IS NOT NULL
        AND ST_DWithin(m.perimeter_utm12s, p.geometry_utm12s, :max_distance)))
"""

#: Clears the bindings of the perimeters in scope, so the cascade starts from nothing.
CLEAR_SQL = """
UPDATE conaf_magnitud_wildfire
SET conaf_wildfire_id = NULL, match_method = NULL,
    match_confidence = NULL, matched_at = NULL
WHERE season_start_year = :season
  AND (NOT CAST(:only_unbound AS boolean) OR conaf_wildfire_id IS NULL)
"""

#: Writes one binding.
BIND_SQL = """
UPDATE conaf_magnitud_wildfire
SET conaf_wildfire_id = :report_id, match_method = :method,
    match_confidence = :confidence, matched_at = :matched_at
WHERE id = :perimeter_id
"""


# --------------------------------------------------------------------------
# The two sides
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Perimeter:
    """One mapped perimeter, as the cascade needs it."""

    id: int
    season_start_year: int
    number: int | None
    name: str | None
    region_code: str | None
    area_ha_mapped: float | None

    @property
    def name_key(self) -> str:
        """The name folded the way the imports folded it."""
        return chile_conaf.normalise(self.name)


@dataclass(frozen=True)
class Report:
    """One seasonal fire report, as the cascade needs it."""

    id: int
    number: int | None
    name: str | None
    region_code: str | None
    area_ha_total: float | None
    start_date_time: datetime.datetime | None

    @property
    def name_key(self) -> str:
        """The name folded the way the imports folded it."""
        return chile_conaf.normalise(self.name)


@dataclass(frozen=True)
class Candidate:
    """One report considered for one perimeter, with the spatial tests applied.

    Attributes
    ----------
    report : Report
        The report.
    metres : float or None
        Distance from the perimeter to its point, or ``None`` when the pair was never
        compared spatially — which happens when the report matched on its number or
        name alone and its point is further away than ``--max-distance``.
    inside : bool
        Whether the point falls inside the perimeter.
    """

    report: Report
    metres: float | None = None
    inside: bool = False


def rank_of(method: str) -> int:
    """Where a method sits in the cascade: lower is stronger."""
    return RANKED_METHODS.index(method)


def label(perimeter: Perimeter, candidate: Candidate,
          unique_names: set[str]) -> str | None:
    """The strongest rule this candidate satisfies, or ``None`` for no rule at all.

    Parameters
    ----------
    perimeter : Perimeter
        The perimeter being bound.
    candidate : Candidate
        One report of the same season.
    unique_names : set of str
        The folded names that exactly one report of the season carries.
        :data:`~src.providers.chile_conaf_magnitud.MATCH_NAME_SEASON` needs it: a name
        two reports share is not an identification, and testing it here rather than by
        counting the resulting group is what keeps the *reason* a fire went unbound
        honest — it is "the name is not unique", not "two candidates tied".

    Returns
    -------
    str or None
        One of :data:`RANKED_METHODS`, or ``None``.

    Notes
    -----
    Order matters and is the cascade's: the number with the región is checked before
    the number with the name, which is checked before either of the name rules, which
    are checked before the two purely spatial ones.

    A number of ``None`` on either side never matches. ``NUMERO_REG`` is unpublished
    on two whole seasons of reports, and treating "neither has one" as agreement would
    bind every perimeter of 2013-2014 to whichever report happened to be nearest.
    """
    report = candidate.report
    names_agree = bool(perimeter.name_key) and perimeter.name_key == report.name_key
    numbers_agree = (perimeter.number is not None
                     and perimeter.number == report.number)
    regions_agree = (perimeter.region_code is not None
                     and perimeter.region_code == report.region_code)

    if numbers_agree and regions_agree and names_agree:
        return MATCH_NUMBER_REGION_NAME_SEASON
    if numbers_agree and regions_agree and candidate.inside:
        return MATCH_NUMBER_REGION_INSIDE_SEASON
    if numbers_agree and regions_agree:
        return MATCH_NUMBER_REGION_SEASON
    if numbers_agree and names_agree:
        return MATCH_NUMBER_NAME_SEASON
    if names_agree and candidate.inside:
        return MATCH_NAME_SEASON_INSIDE
    if names_agree and perimeter.name_key in unique_names:
        return MATCH_NAME_SEASON
    if candidate.inside:
        return MATCH_INSIDE_SINGLE
    if candidate.metres is not None:
        return MATCH_NEAR_SINGLE
    return None


@dataclass
class Binding:
    """What the cascade concluded about one perimeter.

    Attributes
    ----------
    perimeter : Perimeter
        The mapped fire.
    candidate : Candidate or None
        The report it was bound to, or ``None``.
    method : str or None
        Which rule produced the binding. Exactly one of this and :attr:`reason` is set.
    reason : str or None
        Why there is no binding, from :data:`UNBOUND_REASONS`.
    candidates : int
        How many reports were still in play when the cascade decided or gave up.
    """

    perimeter: Perimeter
    candidate: Candidate | None = None
    method: str | None = None
    reason: str | None = None
    candidates: int = 0

    @property
    def is_bound(self) -> bool:
        return self.candidate is not None

    @property
    def confidence(self) -> float | None:
        """The confidence for :attr:`method`, or ``None`` where there is no binding."""
        return None if self.method is None else MATCH_METHOD_CONFIDENCE[self.method]

    @property
    def row(self) -> tuple:
        """The binding as the CSV report writes it, in :data:`REPORT_COLUMNS` order."""
        perimeter, candidate = self.perimeter, self.candidate
        report = None if candidate is None else candidate.report
        season = perimeter.season_start_year
        return (
            f"{season}-{season + 1}",
            perimeter.id,
            "" if perimeter.number is None else perimeter.number,
            perimeter.name or "",
            perimeter.region_code or "",
            "" if perimeter.area_ha_mapped is None else f"{perimeter.area_ha_mapped:.2f}",
            "bound" if self.is_bound else "unbound",
            self.method or self.reason or "",
            "" if self.confidence is None else f"{self.confidence:.2f}",
            "" if candidate is None or candidate.metres is None
            else f"{candidate.metres:.0f}",
            "" if report is None else report.id,
            "" if report is None or report.number is None else report.number,
            "" if report is None else (report.name or ""),
            "" if report is None else (report.region_code or ""),
            "" if report is None or report.area_ha_total is None
            else f"{report.area_ha_total:.2f}",
            "" if report is None or report.start_date_time is None
            else report.start_date_time.isoformat(),
            self.candidates,
        )


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

def match(perimeter: Perimeter, candidates: list[Candidate],
          unique_names: set[str]) -> Binding:
    """Run the cascade for one perimeter.

    Every candidate is labelled with the strongest rule it satisfies, the
    best-labelled group is taken, and the binding is written only if that group holds
    exactly one. See the module docstring.
    """
    eligible = [(label(perimeter, candidate, unique_names), candidate)
                for candidate in candidates]
    eligible = [(method, candidate) for method, candidate in eligible if method]
    if not eligible:
        return Binding(perimeter=perimeter, reason=UNBOUND_NO_CANDIDATE, candidates=0)

    best = min(rank_of(method) for method, _ in eligible)
    group = [candidate for method, candidate in eligible if rank_of(method) == best]
    if len(group) > 1:
        return Binding(perimeter=perimeter, reason=UNBOUND_AMBIGUOUS,
                       candidates=len(group))
    return Binding(perimeter=perimeter, candidate=group[0],
                   method=RANKED_METHODS[best], candidates=1)


def resolve_contested(bindings: list[Binding], logger: logging.Logger) -> int:
    """Unbind every report that two perimeters both claim, returning how many went.

    Both are dropped rather than one picked: nothing in the data would make the
    choice. A contest here usually means one report covers a fire CONAF mapped in two
    separately-named pieces, in which case the right answer is a dissolve the import
    did not make — and that is worth looking at rather than papering over.
    """
    claims: dict[int, list[Binding]] = defaultdict(list)
    for binding in bindings:
        if binding.is_bound:
            claims[binding.candidate.report.id].append(binding)

    dropped = 0
    for contested in claims.values():
        if len(contested) < 2:
            continue
        logger.warning(
            "Report %d (%r) is claimed by %d perimeters (%s); none of them is bound",
            contested[0].candidate.report.id,
            contested[0].candidate.report.name,
            len(contested),
            ", ".join(str(binding.perimeter.id) for binding in contested),
        )
        for binding in contested:
            binding.candidate = None
            binding.method = None
            binding.reason = UNBOUND_REPORT_CONTESTED
            dropped += 1
    return dropped


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_seasons(session: Session, season: int | None, only_unbound: bool) -> list[int]:
    """The seasons with perimeters in scope, in order."""
    return list(session.scalars(text(SEASONS_SQL),
                                {"season": season, "only_unbound": only_unbound}).all())


def load_perimeters(session: Session, season: int, only_unbound: bool) -> list[Perimeter]:
    """The perimeters of one season, in scope."""
    rows = session.execute(text(PERIMETERS_SQL),
                           {"season": season, "only_unbound": only_unbound}).all()
    return [Perimeter(id=row.id, season_start_year=row.season_start_year,
                      number=row.number, name=row.name, region_code=row.region_code,
                      area_ha_mapped=None if row.area_ha_mapped is None
                      else float(row.area_ha_mapped))
            for row in rows]


def load_reports(session: Session, season: int) -> dict[int, Report]:
    """Every report of one season, by id."""
    rows = session.execute(text(REPORTS_SQL), {"season": season}).all()
    return {row.id: Report(id=row.id, number=row.number, name=row.name,
                           region_code=row.region_code,
                           area_ha_total=None if row.area_ha_total is None
                           else float(row.area_ha_total),
                           start_date_time=row.start_date_time)
            for row in rows}


def load_candidates(session: Session, season: int, perimeters: list[Perimeter],
                    reports: dict[int, Report], max_distance: float,
                    only_unbound: bool) -> dict[int, list[Candidate]]:
    """Every report worth considering for each perimeter of the season.

    Notes
    -----
    Two sources, unioned per perimeter:

    * **Spatial.** Reports inside the perimeter or within ``--max-distance`` of it,
      from :data:`SPATIAL_SQL`, which is where the two geometry indexes earn their
      keep.
    * **Attribute.** Reports of the season whose ``(region_code, number)`` or whose
      folded name matches the perimeter's, found in Python from the season's reports.

    The second is not a refinement of the first. A report's point is where the office
    filed it, and for a 200-hectare fire that can be a road junction kilometres away —
    or, in the older seasons, the comuna's centre. Gating the number rule on distance
    would throw away the strongest evidence in the archive because of the weakest.
    """
    spatial = session.execute(text(SPATIAL_SQL), {
        "season": season, "max_distance": max_distance, "only_unbound": only_unbound,
    }).all()

    by_perimeter: dict[int, dict[int, Candidate]] = defaultdict(dict)
    for row in spatial:
        report = reports.get(row.report_id)
        if report is None:
            continue
        by_perimeter[row.perimeter_id][row.report_id] = Candidate(
            report=report, metres=float(row.metres), inside=bool(row.inside))

    by_number: dict[tuple[str, int], list[Report]] = defaultdict(list)
    by_name: dict[str, list[Report]] = defaultdict(list)
    for report in reports.values():
        if report.region_code is not None and report.number is not None:
            by_number[(report.region_code, report.number)].append(report)
        if report.name_key:
            by_name[report.name_key].append(report)

    for perimeter in perimeters:
        found = by_perimeter[perimeter.id]
        matches: list[Report] = []
        if perimeter.region_code is not None and perimeter.number is not None:
            matches += by_number.get((perimeter.region_code, perimeter.number), [])
        if perimeter.name_key:
            matches += by_name.get(perimeter.name_key, [])
        for report in matches:
            found.setdefault(report.id, Candidate(report=report))

    return {perimeter_id: list(found.values())
            for perimeter_id, found in by_perimeter.items()}


def unique_name_keys(reports: dict[int, Report]) -> set[str]:
    """The folded names exactly one report of the season carries."""
    counts: dict[str, int] = defaultdict(int)
    for report in reports.values():
        if report.name_key:
            counts[report.name_key] += 1
    return {name for name, count in counts.items() if count == 1}


# --------------------------------------------------------------------------
# Binding a season
# --------------------------------------------------------------------------

def bind_season(session: Session, season: int, max_distance: float,
                only_unbound: bool, dry_run: bool,
                logger: logging.Logger) -> list[Binding]:
    """Run the cascade over one season and write what it concluded."""
    perimeters = load_perimeters(session, season, only_unbound)
    if not perimeters:
        return []
    reports = load_reports(session, season)
    if not reports:
        logger.warning("%d-%d: %d perimeter(s) and no reports of that season; import "
                       "the seasonal reports first", season, season + 1, len(perimeters))
        return [Binding(perimeter=perimeter, reason=UNBOUND_NO_CANDIDATE)
                for perimeter in perimeters]

    candidates = load_candidates(session, season, perimeters, reports, max_distance,
                                 only_unbound)
    unique = unique_name_keys(reports)
    bindings = [match(perimeter, candidates.get(perimeter.id, []), unique)
                for perimeter in perimeters]
    resolve_contested(bindings, logger)

    session.execute(text(CLEAR_SQL), {"season": season, "only_unbound": only_unbound})
    matched_at = datetime.datetime.now(datetime.timezone.utc)
    for binding in bindings:
        if not binding.is_bound:
            continue
        session.execute(text(BIND_SQL), {
            "perimeter_id": binding.perimeter.id,
            "report_id": binding.candidate.report.id,
            "method": binding.method,
            "confidence": binding.confidence,
            "matched_at": matched_at,
        })

    bound = sum(1 for binding in bindings if binding.is_bound)
    if dry_run:
        session.rollback()
        logger.info("%d-%d: would bind %d of %d perimeter(s) (dry run)",
                    season, season + 1, bound, len(bindings))
    else:
        session.commit()
        logger.info("%d-%d: bound %d of %d perimeter(s)",
                    season, season + 1, bound, len(bindings))
    return bindings


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def write_csv(bindings: list[Binding], path: Path, logger: logging.Logger) -> None:
    """Write every perimeter in scope, bound or not.

    The unbound rows are the point of the report: a binding that happened needs no
    looking at, and one that did not is either a fire to check or a gap in coverage.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for binding in bindings:
            writer.writerow(binding.row)
    logger.info("Wrote %s", path)


def report(bindings: list[Binding], logger: logging.Logger) -> None:
    """Log what the cascade concluded, by rule and by reason."""
    if not bindings:
        logger.info("No perimeter in scope")
        return

    bound = [binding for binding in bindings if binding.is_bound]
    logger.info("Bound %d of %d perimeter(s), %.1f%%",
                len(bound), len(bindings), 100.0 * len(bound) / len(bindings))

    by_method: dict[str, int] = defaultdict(int)
    for binding in bound:
        by_method[binding.method] += 1
    for method in RANKED_METHODS:
        if by_method.get(method):
            logger.info("  %-22s %5d  (confidence %.2f)",
                        method, by_method[method], MATCH_METHOD_CONFIDENCE[method])

    by_reason: dict[str, int] = defaultdict(int)
    for binding in bindings:
        if not binding.is_bound:
            by_reason[binding.reason] += 1
    for reason in UNBOUND_REASONS:
        if by_reason.get(reason):
            logger.info("  unbound: %-13s %5d", reason, by_reason[reason])


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def metres(text_value: str) -> float:
    """Argparse type for ``--max-distance``: a finite, non-negative number of metres.

    Zero is meaningful and is accepted: it turns the tolerance rule off and leaves the
    number, name and containment rules, which is the right setting for an analysis
    that will not accept a point outside the burnt area.
    """
    try:
        distance = float(text_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text_value!r} is not a number of metres")
    if distance != distance or distance in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError(
            f"{text_value!r} is not a finite number of metres")
    if distance < 0:
        raise argparse.ArgumentTypeError(
            f"a distance cannot be negative, and {distance:g} m is: pass 0 to consider "
            f"only the points inside a perimeter")
    return distance


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Bind CONAF's Chilean perimeters to the seasonal fire reports.",
        epilog="Import both datasets first. Only conaf_magnitud_wildfire's four binding "
               "columns are ever written. A perimeter is bound only when exactly one "
               "report survives the cascade, so an ambiguous fire is left unbound and "
               "reported rather than guessed at. Database settings not given here are "
               "read from the environment (.env).",
    )
    parser.add_argument("-y", "--season", type=int, metavar="YEAR",
                        help="bind only the perimeters of this season, named by its "
                             "first year (2016 for 2016-2017); the candidates are the "
                             "reports of the same season")
    parser.add_argument("--max-distance", type=metres,
                        default=DEFAULT_MATCH_DISTANCE_M, metavar="METRES",
                        help=f"how far outside a perimeter a report's point may be and "
                             f"still be considered by the weakest rule (default "
                             f"{DEFAULT_MATCH_DISTANCE_M:g}). 0 keeps only the points "
                             f"inside a perimeter. The number and name rules are not "
                             f"spatial and are unaffected")
    parser.add_argument("--only-unbound", action="store_true",
                        help="leave the perimeters that already have a link alone, and "
                             "try only the ones that do not. By default every perimeter "
                             "in scope is recomputed from scratch")
    parser.add_argument("--dry-run", action="store_true",
                        help="run the cascade and report, writing nothing")
    parser.add_argument("--csv", type=Path,
                        help="write every perimeter in scope, bound or not, to this .csv")

    common.add_database_arguments(parser)
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def bind_wildfires(args: argparse.Namespace, engine: Engine,
                   logger: logging.Logger) -> list[Binding]:
    """Bind every season in scope, returning every binding decision."""
    common.require_tables(engine, ["conaf_magnitud_wildfire", "conaf_wildfire",
                                   "conaf_ignition", "wildfire"], logger)

    with Session(engine) as session:
        seasons = load_seasons(session, args.season, args.only_unbound)
    if not seasons:
        logger.warning("No perimeter to bind. Import them with "
                       "src.apps.imports.wildfires.chile_conaf_magnitud.import_wildfires")
        return []
    logger.info("Binding %d season(s)", len(seasons))

    bindings: list[Binding] = []
    for season in seasons:
        with Session(engine) as session:
            bindings += bind_season(session, season, args.max_distance,
                                    args.only_unbound, args.dry_run, logger)

    report(bindings, logger)
    if args.csv:
        write_csv(bindings, args.csv, logger)
    return bindings


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("conaf-bind")

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        bind_wildfires(args, engine, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Binding failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
