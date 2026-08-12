#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bind the Canadian NBAC perimeters to the NFDB agency fire reports.

Fills in :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id`
and the three columns that account for it — ``match_method``, ``match_confidence``
and ``matched_at`` — for fires already imported by both
:mod:`~src.apps.imports.wildfires.canada_nbac.import_wildfires` and
:mod:`~src.apps.imports.wildfires.canada_nfdb.import_wildfires`.

It writes nothing else, ever. No row is created, no perimeter is touched, no NFDB
column is written: the whole of this application's effect is four columns on
``nbac_wildfire``, and running it on an empty database is a no-op::

    python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires
    python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires --year 2023
    python3 -m src.apps.bindings.wildfires.canada_nbac.bind_nfdb_wildfires \\
        --dry-run --csv bindings.csv

Why the two datasets need binding at all
-----------------------------------------

They are complements, and they are the same fires. NBAC maps the burn from imagery
and publishes a **shape** with no report behind it; NFDB is what the agency filed —
a cause, a response, a protection zone, a reported size — with **no shape**. Neither
can answer the other's question, and a Canadian fire is one event whose evidence is
split between two products of the same agency.

The lightning work is the reason it matters. NFDB's 195,240 natural-cause fires are
the largest such set in GisFIRE and every one of them has a point and a date; NBAC
is where the area actually burnt is. Binding them is what makes *how much burnt, by
what cause* a question this project can ask of Canada at all.

There is no identifier, and that is not an oversight
------------------------------------------------------

The Catalan binder opens on ``CODI_FINAL`` being the EGIF ``report_number``, and the
Andalusian one on ``CODIGO`` being it — 749 of its 759 bindings. **This one has
nothing of the kind.**

NBAC publishes nineteen fields, and the same nineteen in every one of its fifty-three
yearly archives::

    YEAR NFIREID BASRC FIREMAPS FIREMAPM FIRECAUS HS_SDATE HS_EDATE AG_SDATE
    AG_EDATE CAPDATE POLY_HA ADJ_HA ADJ_FLAG ADMIN_NAME ADMIN_DIV PRESCRIBED
    VERSION GID

Not one of them is an agency fire number. ``NFIREID`` is NBAC's own within-year
sequence and ``GID`` is the year and that sequence run together; neither has any
relationship to NFDB's ``NFDBFIREID`` or ``FIRE_ID``. So there is no code stage in
this cascade, no stage can be certain, and **no method here scores 1.00** — see
:data:`~src.providers.canada_nbac.wildfire.MATCH_METHOD_CONFIDENCE`.

What there is instead
---------------------

Three things the two datasets share, measured rather than assumed:

**The geometry.** Both are published on EPSG:3978 and both store the published
geometry unchanged, so the containment test is metres on a common national grid with
no reprojection and no assumption about whose CRS is authoritative. That is a better
position than the Spanish binder is in.

**The date.** NBAC's ``AG_SDATE`` is *the agency's* start date, which means it comes
from the same records NFDB publishes as ``REP_DATE`` — and it shows: on the
perimeters that contain a point, the two agree exactly on 157 of 1985's 177 dated
pairs. **The exactness is the signal.** Widening the comparison to ±3 days makes the
binding *worse*, not better, because it re-admits the neighbours it was
discriminating against.

**The agency.** NBAC's ``ADMIN_NAME`` and NFDB's ``SRC_AGENCY`` are the same
vocabulary of provincial, territorial and Parks Canada codes — 178 agreements in 181
in 1985, 128 in 128 in 1986. A perimeter cut across a boundary carries several,
joined by :data:`~src.providers.canada_nbac.ADMIN_SEPARATOR`, so the test is
membership and not equality.

Together, ``(agency, exact day)`` is the pseudo-identifier this pair of datasets does
not otherwise have.

The cascade
-----------

Every candidate is labelled with the **strongest rule it satisfies**, the best-labelled
group is taken, and a link is written **only when that group holds exactly one
candidate**. The labels are disjoint, so nothing is ever resolved by widening a set
that was already ambiguous.

===  ===================================================  ===============================
#    The candidate…                                       Method
===  ===================================================  ===============================
1    is inside the perimeter, same agency, same day       ``inside_agency_day``
2    is inside, same agency, NBAC publishes no date       ``inside_agency_undated``
3    is inside, same agency, the dates disagree           ``inside_agency_date_mismatch``
4    is inside, and the agency does not match             ``inside``
5    is within ``--max-distance``, same agency, same day  ``near_agency_day``
===  ===================================================  ===============================

Anything else is not a candidate. A perimeter whose best group holds two or more is
left **unbound and reported**, which is the conservative half of the design and is
deliberate: a wrong binding silently attaches another fire's cause and reported size
to a perimeter and nothing downstream could ever detect it, while a missing binding
is visible in the first report anyone runs.

Stage 5 is half the work, and the weakest thing here
------------------------------------------------------

On the 1985-1995 archive stage 5 produces about as many bindings as all four
containment stages together — 143 of 1985's 279, 118 of 1986's 225. It has to exist:
an agency point is *where somebody said the fire was*, the published summary says
outright that *"locations are approximate"*, and a point a kilometre outside a burnt
polygon is the normal case rather than a fault.

But it is a claim about proximity and not about containment, so how far is *too* far
was measured rather than chosen. Taking the 1,359 perimeters of 1985-1995 that have a
known-good contained partner and asking how often a **wrong** point is also nearby
with the same agency and the same day:

====================  ===================  ===============
``--max-distance``    stage 5 bindings     decoy density
====================  ===================  ===============
500 m                 1,034                3.7%
1 km                  1,478                5.7%
**2 km** (default)    **1,685**            **7.5%**
5 km                  1,730                13.0%
====================  ===================  ===============

There is a knee at 2 km. Going on to 5 km buys 45 more bindings — 2.7% — and nearly
doubles the chance that the single candidate a fire is bound to is somebody else's
fire. That is the whole argument for the default, and ``--max-distance 0`` turns the
stage off altogether for an analysis that wants containment or nothing.

.. warning::

   The decoy density is a property of the neighbourhood, not a false-positive rate:
   stage 5 fires only where exactly one candidate exists, so a crowded neighbourhood
   is refused rather than guessed at. What it measures is the risk in the case that
   cannot be checked — the true partner missing from NFDB and one wrong point present.
   Filter on ``match_confidence >= 0.7`` for an analysis that will not tolerate it.

One report, one perimeter
-------------------------

Two perimeters must never end up bound to the same NFDB report. Nothing prevents it —
there is no identifier to be unique — and it happens a couple of times a year, when
one agency report sits between two mapped polygons.

Where it happens **neither is bound**, and both are reported. It is the same
conservative rule applied in the other direction, and it is enforced here rather than
by a unique constraint so that a genuine many-to-one — NBAC splitting what an agency
filed as one fire — is a data question to be looked at rather than a crash halfway
through a run.

A year at a time
----------------

The candidates are generated one year per statement, as everywhere else in this
project. It is not optional here: 51,818 perimeters against 380,000 points is a
spatial join that has no business being asked in one piece, and a year of it is a few
thousand rows either side. The cascade itself then runs in Python over that year's
candidates.

Every year is committed as it goes, so an interrupted run keeps the years it
finished. ``--dry-run`` does all the work and rolls it back.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import os
import sys
import time

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

import src.settings  # noqa: F401  (imported for the side effect of loading .env)

from src.apps.imports import common
from src.providers import canada_nbac
from src.providers.canada_nbac.wildfire import DEFAULT_MATCH_DISTANCE_M
from src.providers.canada_nbac.wildfire import MATCH_INSIDE
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_DATE_MISMATCH
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_DAY
from src.providers.canada_nbac.wildfire import MATCH_INSIDE_AGENCY_UNDATED
from src.providers.canada_nbac.wildfire import MATCH_METHOD_CONFIDENCE
from src.providers.canada_nbac.wildfire import MATCH_NEAR_AGENCY_DAY

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Why a fire was not bound, for the report. Not stored on the row — the row says
#: only that it has no binding — because these are properties of a run against a
#: particular database and would go stale the moment either side is re-imported.
UNBOUND_NO_CANDIDATE = "no candidate"
UNBOUND_AMBIGUOUS = "several candidates"
UNBOUND_REPORT_CONTESTED = "report claimed by another perimeter"
UNBOUND_REASONS = (UNBOUND_NO_CANDIDATE, UNBOUND_AMBIGUOUS, UNBOUND_REPORT_CONTESTED)

#: The columns of the ``--csv`` report, in order.
REPORT_COLUMNS = ("gid", "year", "admin_name", "agency_start_date", "area_ha_polygon",
                  "outcome", "method", "confidence", "distance_m",
                  "nfdb_fire_id", "agency_fire_id", "src_agency", "report_date",
                  "size_ha", "candidates")

#: The methods in the order the cascade prefers them. The rank of a candidate is its
#: index here, so a lower number is a stronger claim; see :func:`rank_of`.
RANKED_METHODS = (
    MATCH_INSIDE_AGENCY_DAY,
    MATCH_INSIDE_AGENCY_UNDATED,
    MATCH_INSIDE_AGENCY_DATE_MISMATCH,
    MATCH_INSIDE,
    MATCH_NEAR_AGENCY_DAY,
)

#: The years both datasets hold fires in, newest first.
#:
#: The intersection, and not NBAC's years: a year NFDB does not cover has no candidate
#: for any of its perimeters, and there is no point opening a spatial statement to
#: discover that. NBAC drives the run because it is the side being written.
YEARS_SQL = """
SELECT DISTINCT b.year AS year
FROM nbac_wildfire b
WHERE b.perimeter_lambert IS NOT NULL
  AND (CAST(:year AS integer) IS NULL OR b.year = CAST(:year AS integer))
  AND (NOT CAST(:only_unbound AS boolean) OR b.nfdb_wildfire_id IS NULL)
  AND EXISTS (SELECT 1 FROM nfdb_wildfire f
              WHERE f.year = b.year AND f.ignition_id IS NOT NULL)
ORDER BY year DESC
"""

#: Every perimeter of one year that the run may write to.
#:
#: Read separately from the candidates so that a perimeter with **no** candidate is
#: still a row in the report. A spatial join alone cannot report an absence.
PERIMETERS_SQL = """
SELECT b.id AS id, b.gid AS gid, b.year AS year, b.admin_name AS admin_name,
       b.agency_start_date AS agency_start_date,
       b.area_ha_polygon AS area_ha_polygon
FROM nbac_wildfire b
WHERE b.year = :year
  AND b.perimeter_lambert IS NOT NULL
  AND (NOT CAST(:only_unbound AS boolean) OR b.nfdb_wildfire_id IS NULL)
ORDER BY b.gid
"""

#: Every (perimeter, report) pair of one year close enough to be considered.
#:
#: The whole geometric half of the application, and the only expensive statement in
#: it. Notes on three choices:
#:
#: **The Lambert grid, not EPSG:4326.** Both datasets are published on EPSG:3978 and
#: both keep the published geometry, so this is metres on a common national grid with
#: no reprojection either way. ``ST_DWithin`` on a geography would be the alternative
#: and would be slower, less exact and dependent on a reprojection neither source
#: asked for.
#:
#: **The agency test is membership, not equality.** A perimeter cut at a provincial
#: boundary carries several administrations joined by ``'; '`` — ``'AB; SK'`` is one
#: fire in two provinces — and comparing that to a single ``SRC_AGENCY`` with ``=``
#: would score every one of those 450 fires as a disagreement.
#:
#: **``ST_DWithin`` and then ``ST_Distance``.** The first is what the GiST index can
#: answer; the second is only computed for the pairs that survive it, and is kept
#: because the distance is worth reporting even when the rule that used it does not
#: care how far.
CANDIDATES_SQL = """
SELECT b.id AS nbac_id,
       f.id AS nfdb_id,
       ST_Distance(b.perimeter_lambert, ni.geometry_lambert) AS metres,
       COALESCE(f.src_agency = ANY(string_to_array(b.admin_name, :separator)), FALSE)
           AS same_agency,
       COALESCE(b.agency_start_date = f.report_date, FALSE) AS same_day,
       (b.agency_start_date IS NULL) AS nbac_undated,
       f.nfdb_fire_id AS nfdb_fire_id,
       f.agency_fire_id AS agency_fire_id,
       f.src_agency AS src_agency,
       f.report_date AS report_date,
       f.size_ha AS size_ha
FROM nbac_wildfire b
JOIN nfdb_wildfire f ON f.year = b.year
JOIN nfdb_ignition ni ON ni.id = f.ignition_id
WHERE b.year = :year
  AND b.perimeter_lambert IS NOT NULL
  AND (NOT CAST(:only_unbound AS boolean) OR b.nfdb_wildfire_id IS NULL)
  AND ST_DWithin(b.perimeter_lambert, ni.geometry_lambert, :max_distance)
"""

#: Clears every binding this application owns, for the perimeters in scope.
#:
#: Run before the cascade so that a re-run is a recomputation rather than an
#: accumulation: a fire that no longer matches has to *lose* its link, or a correction
#: to either dataset could never take effect.
CLEAR_SQL = """
UPDATE nbac_wildfire
SET nfdb_wildfire_id = NULL, match_method = NULL,
    match_confidence = NULL, matched_at = NULL
WHERE year = :year
  AND (NOT CAST(:only_unbound AS boolean) OR nfdb_wildfire_id IS NULL)
"""

#: Writes one binding.
BIND_SQL = """
UPDATE nbac_wildfire
SET nfdb_wildfire_id = :nfdb_id, match_method = :method,
    match_confidence = :confidence, matched_at = :matched_at
WHERE id = :nbac_id
"""


# --------------------------------------------------------------------------
# The two sides
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Perimeter:
    """One NBAC perimeter, as the cascade needs it."""

    id: int
    gid: str
    year: int
    admin_name: str | None
    agency_start_date: datetime.date | None
    area_ha_polygon: float | None


@dataclass(frozen=True)
class Candidate:
    """One NFDB report near one perimeter, with the three tests already applied.

    The tests are computed in SQL rather than here because two of the three are
    comparisons the database is better at — a distance against an indexed geometry,
    and an array membership — and doing them there keeps this a pure function of what
    came back.

    Attributes
    ----------
    metres : float
        Distance from the perimeter, ``0.0`` for a point inside it.
    same_agency : bool
        Whether ``SRC_AGENCY`` is one of the administrations the perimeter was mapped
        in. Membership, not equality — see :data:`CANDIDATES_SQL`.
    same_day : bool
        Whether ``REP_DATE`` is the perimeter's ``AG_SDATE``. ``False`` when the
        perimeter publishes no date, which :attr:`nbac_undated` tells apart.
    nbac_undated : bool
        Whether the perimeter publishes no agency start date at all, so the date test
        is a silence rather than a disagreement.
    """

    nfdb_id: int
    metres: float
    same_agency: bool
    same_day: bool
    nbac_undated: bool
    nfdb_fire_id: str | None
    agency_fire_id: str | None
    src_agency: str | None
    report_date: datetime.date | None
    size_ha: float | None

    @property
    def inside(self) -> bool:
        """Whether the point falls within the burnt perimeter."""
        return self.metres == 0.0

    @property
    def method(self) -> str | None:
        """The strongest rule this candidate satisfies, or ``None`` for none of them.

        The labels are **disjoint and ordered**: a candidate gets exactly one, the
        best one available to it. That is what lets :func:`match` take the best group
        and stop, rather than widening a set that was already ambiguous — widening can
        only ever add candidates, so a set that was ambiguous stays ambiguous.
        """
        if self.inside:
            if self.same_agency:
                if self.same_day:
                    return MATCH_INSIDE_AGENCY_DAY
                if self.nbac_undated:
                    return MATCH_INSIDE_AGENCY_UNDATED
                return MATCH_INSIDE_AGENCY_DATE_MISMATCH
            return MATCH_INSIDE
        if self.same_agency and self.same_day:
            return MATCH_NEAR_AGENCY_DAY
        return None


def rank_of(method: str) -> int:
    """Where a method sits in the cascade: lower is stronger."""
    return RANKED_METHODS.index(method)


@dataclass
class Binding:
    """What the cascade concluded about one perimeter.

    Attributes
    ----------
    perimeter : Perimeter
        The NBAC fire.
    candidate : Candidate or None
        The NFDB report it was bound to, or ``None``.
    method : str or None
        Which rule produced the binding. Exactly one of this and :attr:`reason` is set.
    reason : str or None
        Why there is no binding, from :data:`UNBOUND_REASONS`.
    candidates : int
        How many reports were still in play when the cascade decided or gave up. ``1``
        for a binding; for an ambiguous fire, the number that made it ambiguous, which
        is the useful thing to look at in the report.
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
        return (
            perimeter.gid, perimeter.year, perimeter.admin_name or "",
            perimeter.agency_start_date.isoformat() if perimeter.agency_start_date else "",
            "" if perimeter.area_ha_polygon is None else f"{perimeter.area_ha_polygon:.2f}",
            "bound" if self.is_bound else "unbound",
            self.method or "",
            "" if self.confidence is None else f"{self.confidence:.2f}",
            "" if candidate is None else f"{candidate.metres:.0f}",
            (candidate.nfdb_fire_id or "") if candidate else "",
            (candidate.agency_fire_id or "") if candidate else "",
            (candidate.src_agency or "") if candidate else "",
            candidate.report_date.isoformat() if candidate and candidate.report_date else "",
            "" if candidate is None or candidate.size_ha is None
            else f"{candidate.size_ha:.2f}",
            self.candidates,
        )


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

def match(perimeter: Perimeter, candidates: list[Candidate]) -> Binding:
    """Run the cascade for one perimeter.

    Parameters
    ----------
    perimeter : Perimeter
        The NBAC fire to bind.
    candidates : list of Candidate
        Every NFDB report of the same year within ``--max-distance`` of it.

    Returns
    -------
    Binding
        Bound or not, with the rule or the reason.

    Notes
    -----
    Every candidate is labelled with the strongest rule it satisfies
    (:attr:`Candidate.method`), the best-labelled group is taken, and the binding is
    written only if that group holds exactly one.

    A candidate that satisfies no rule is not a candidate: being within two kilometres
    of a burnt area, from another agency, on another day, is not evidence of anything
    and admitting it would only make well-determined fires ambiguous.

    A group of two or more ends the cascade rather than falling through to the next.
    The labels are ordered by strength and every later group is a *weaker* kind of
    claim, not a narrower set, so there is nothing below that could separate what the
    best evidence could not.
    """
    labelled = [(candidate.method, candidate) for candidate in candidates]
    eligible = [(method, candidate) for method, candidate in labelled if method]
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
    """Unbind every NFDB report that two perimeters both claim, returning how many went.

    Nothing prevents a contest here — there is no identifier to be unique, unlike the
    Catalan cascade where stage 1 could not produce one — so it happens a couple of
    times a year, where one agency report sits between two mapped polygons.

    Both are dropped rather than one picked: nothing in the data would make the
    choice, and picking anyway is exactly the silent wrong answer this application is
    built to avoid. See the module docstring for why this is enforced here rather than
    by a unique constraint.
    """
    claims: dict[int, list[Binding]] = defaultdict(list)
    for binding in bindings:
        if binding.is_bound:
            claims[binding.candidate.nfdb_id].append(binding)

    dropped = 0
    for contested in claims.values():
        if len(contested) < 2:
            continue
        logger.warning(
            "NFDB report %s is claimed by %d perimeters (%s); none of them is bound",
            contested[0].candidate.nfdb_fire_id or contested[0].candidate.nfdb_id,
            len(contested),
            ", ".join(binding.perimeter.gid for binding in contested))
        for binding in contested:
            binding.candidate = None
            binding.method = None
            binding.reason = UNBOUND_REPORT_CONTESTED
            binding.candidates = len(contested)
            dropped += 1
    return dropped


# --------------------------------------------------------------------------
# One year
# --------------------------------------------------------------------------

def load_years(session: Session, year: int | None, only_unbound: bool) -> list[int]:
    """The years in scope, newest first."""
    return list(session.scalars(text(YEARS_SQL),
                                {"year": year, "only_unbound": only_unbound}))


def load_perimeters(session: Session, year: int, only_unbound: bool) -> list[Perimeter]:
    """The NBAC perimeters of one year."""
    return [
        Perimeter(id=record.id, gid=record.gid, year=record.year,
                  admin_name=record.admin_name,
                  agency_start_date=record.agency_start_date,
                  area_ha_polygon=record.area_ha_polygon)
        for record in session.execute(text(PERIMETERS_SQL),
                                      {"year": year, "only_unbound": only_unbound})
    ]


def load_candidates(session: Session, year: int, max_distance: float,
                    only_unbound: bool) -> dict[int, list[Candidate]]:
    """Every candidate of one year, grouped by the perimeter it belongs to.

    One statement per year, for the reason the module docstring gives. An empty
    ``max_distance`` still runs it: ``ST_DWithin(..., 0)`` is containment, which is
    exactly what ``--max-distance 0`` is asked for.
    """
    candidates: dict[int, list[Candidate]] = defaultdict(list)
    for record in session.execute(text(CANDIDATES_SQL), {
        "year": year,
        "max_distance": max_distance,
        "only_unbound": only_unbound,
        "separator": canada_nbac.ADMIN_SEPARATOR,
    }):
        candidates[record.nbac_id].append(Candidate(
            nfdb_id=record.nfdb_id,
            metres=float(record.metres),
            same_agency=record.same_agency,
            same_day=record.same_day,
            nbac_undated=record.nbac_undated,
            nfdb_fire_id=record.nfdb_fire_id,
            agency_fire_id=record.agency_fire_id,
            src_agency=record.src_agency,
            report_date=record.report_date,
            size_ha=record.size_ha,
        ))
    return candidates


def bind_year(session: Session, year: int, max_distance: float, only_unbound: bool,
              matched_at: datetime.datetime, logger: logging.Logger,
              write: bool = True) -> list[Binding]:
    """Run the cascade over one year and write its bindings.

    The clear comes first and covers the whole year in scope, not just the perimeters
    being bound: a fire that used to match and no longer does has to lose its link, or
    a correction to either dataset could never take effect.
    """
    perimeters = load_perimeters(session, year, only_unbound)
    candidates = load_candidates(session, year, max_distance, only_unbound)

    bindings = [match(perimeter, candidates.get(perimeter.id, []))
                for perimeter in perimeters]
    resolve_contested(bindings, logger)

    if write:
        session.execute(text(CLEAR_SQL), {"year": year, "only_unbound": only_unbound})
        for binding in bindings:
            if not binding.is_bound:
                continue
            session.execute(text(BIND_SQL), {
                "nbac_id": binding.perimeter.id,
                "nfdb_id": binding.candidate.nfdb_id,
                "method": binding.method,
                "confidence": binding.confidence,
                "matched_at": matched_at,
            })
    return bindings


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

def metres(text_value: str) -> float:
    """Argparse type for ``--max-distance``: a finite, non-negative number of metres.

    Zero is meaningful and is accepted: it turns stage 5 off and leaves the four
    containment rules, which is the right setting for an analysis that will not accept
    a point outside the burnt area.
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
            f"a distance cannot be negative, and {distance:g} m is: pass 0 to bind only "
            f"the points inside a perimeter")
    return distance


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Bind the Canadian NBAC perimeters to the NFDB agency fire reports.",
        epilog="Import both datasets first. Only nbac_wildfire's four binding columns "
               "are ever written. A perimeter is bound only when exactly one report "
               "survives the cascade, so an ambiguous fire is left unbound and reported "
               "rather than guessed at. The two datasets share no published identifier, "
               "so no binding here is certain. Database settings not given here are read "
               "from the environment (.env).",
    )
    parser.add_argument("-y", "--year", type=int,
                        help="bind only the perimeters of this year; the candidates are "
                             "the NFDB reports of the same year")
    parser.add_argument("--max-distance", type=metres,
                        default=DEFAULT_MATCH_DISTANCE_M, metavar="METRES",
                        help=f"how far outside a perimeter an NFDB point may be and "
                             f"still be considered, with its agency and day agreeing "
                             f"(default {DEFAULT_MATCH_DISTANCE_M:g}, measured: 5 km "
                             f"buys 2.7%% more bindings and nearly doubles the chance "
                             f"of binding the wrong fire). 0 keeps only the points "
                             f"inside a perimeter")
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
    """Log what the run concluded: how many bound, by which rule, and why not."""
    bound = [binding for binding in bindings if binding.is_bound]
    logger.info("Bound %d of %d perimeter(s) (%.1f%%)",
                len(bound), len(bindings),
                100.0 * len(bound) / len(bindings) if bindings else 0.0)

    by_method: dict[str, int] = defaultdict(int)
    for binding in bound:
        by_method[binding.method] += 1
    for method in RANKED_METHODS:
        if by_method[method]:
            logger.info("  %-28s %6d  (confidence %.2f)", method, by_method[method],
                        MATCH_METHOD_CONFIDENCE[method])

    by_reason: dict[str, int] = defaultdict(int)
    for binding in bindings:
        if binding.reason:
            by_reason[binding.reason] += 1
    for reason in UNBOUND_REASONS:
        if by_reason[reason]:
            logger.info("  unbound: %-19s %6d", reason, by_reason[reason])

    contained = sum(1 for binding in bound if binding.method != MATCH_NEAR_AGENCY_DAY)
    if bound:
        logger.info("%d of the %d binding(s) rest on the point being inside the "
                    "perimeter (%.1f%%); the rest are near it, on the same day, from "
                    "the same agency", contained, len(bound),
                    100.0 * contained / len(bound))


def bind_wildfires(args: argparse.Namespace, engine: Engine,
                   logger: logging.Logger) -> list[Binding]:
    """Bind every year in scope, one transaction each, returning every binding."""
    common.require_tables(engine, ["nbac_wildfire", "nfdb_wildfire", "nfdb_ignition"],
                          logger)
    matched_at = datetime.datetime.now(datetime.timezone.utc)
    started = time.monotonic()

    with Session(engine) as session:
        years = load_years(session, args.year, args.only_unbound)

    if not years:
        raise RuntimeError(
            "No year has both perimeters and located NFDB reports. Check --year, and "
            "that both Canadian datasets are imported — the binding needs the NFDB "
            "points, not only the fires."
        )

    logger.info("%d year(s) to bind, %s, within %g m",
                len(years), "unbound perimeters only" if args.only_unbound
                else "every perimeter", args.max_distance)

    bindings: list[Binding] = []
    for index, year in enumerate(years, start=1):
        year_started = time.monotonic()
        with Session(engine) as session:
            measured = bind_year(session, year, args.max_distance, args.only_unbound,
                                 matched_at, logger, write=not args.dry_run)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        bindings += measured
        bound = sum(1 for binding in measured if binding.is_bound)
        logger.info("[%d/%d] %d: %s%d of %d perimeter(s) in %.0fs",
                    index, len(years), year,
                    "would have bound " if args.dry_run else "bound ",
                    bound, len(measured), time.monotonic() - year_started)

    report(bindings, logger)
    logger.info("%s in %.0fs", "Dry run" if args.dry_run else "Done",
                time.monotonic() - started)
    return bindings


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("nbac-nfdb-binding")

    try:
        settings = common.resolve_database_settings(args)
    except RuntimeError as error:
        logger.error("%s", error)
        return 1

    engine = create_engine(common.database_url(settings))
    try:
        bindings = bind_wildfires(args, engine, logger)
        if args.csv is not None:
            write_csv(bindings, args.csv, logger)
    except Exception as error:  # noqa: BLE001  (the CLI boundary: report, do not traceback)
        logger.error("Binding failed: %s", error)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
