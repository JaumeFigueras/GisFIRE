#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bind the Catalan DARPA perimeters to the Spanish EGIF *partes*.

Fills in :attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire.egif_wildfire_id`
and the three columns that account for it — ``match_method``, ``match_confidence``
and ``matched_at`` — for fires already imported by both
:mod:`~src.apps.imports.wildfires.catalonia_darpa.import_wildfires` and
:mod:`~src.apps.imports.wildfires.spain_egif.import_wildfires`.

It writes nothing else, ever. No row is created, no perimeter is touched, no EGIF
column is written: the whole of this application's effect is four columns on
``darpa_wildfire``, and running it on an empty database is a no-op::

    python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires
    python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires --year 1994
    python3 -m src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires \\
        --dry-run --csv bindings.csv

Why the two datasets need binding at all
-----------------------------------------

They are complements. EGIF is the national statistic and publishes the cause, the
motivation, the burnt area split five ways and an ignition point — and **no
perimeter, ever**. DARPA publishes the shape and four attributes, with **no burnt
area at all**. Neither can answer the other's question, and a Catalan fire is one
event with its evidence split between two agencies.

What binds them is that the Catalan ``CODI_FINAL`` **is** the EGIF
``report_number``. Not something like it: from 1997 the same ten characters, year
plus INE province plus sequence — and before that the same three fields in a
different order and width, which
:func:`~src.providers.catalonia_darpa.egif_report_number` puts back.

The cascade
-----------

Each stage narrows a set of candidates, and a link is written **only when exactly
one candidate is left**. Every stage is a filter, never a ranking — nothing here
picks a best guess.

**Stage 1 — the code.** If a Catalan ``code`` equals an EGIF ``report_number``,
that is the fire. ``report_number`` is unique across the whole national archive, so
there is nothing to disambiguate. The two published dates are then compared, and
they agree on 471 of the 480 fires this stage matches — which makes the stage
self-checking rather than merely assumed. The nine that disagree are still bound
(the identifier is not a guess) but under
:data:`~src.providers.catalonia_darpa.wildfire.MATCH_CODE_DATE_MISMATCH`, so a fire
whose two sources disagree about *when* it burnt can be found later.

**Stage 1b — the code rearranged.** Four of the six published formats are the same
identifier in a different layout: ``920800034`` of 1992 is ``1992080034``,
``178600064`` of 1986 is ``1986170064``, ``894496`` of 1994 is ``1994080496``. That
is worth 122 more fires, all of them 1986-1996, and it is the difference between
guessing at that era and reading it.

A decode is a reading of a format rather than string equality, so unlike the literal
match it **has to be confirmed by the date**, and one the date contradicts falls
through to the stages below. On the published archive all 122 agree — a cleaner
record than the undecoded form, which disagrees on nine of its 480.

The 1987-1991 letter forms (``G0870016``, ``L89004001``) are **not** decoded: they
carry six digits where a report number has four, and no reading of them matches
EGIF at a rate distinguishable from chance. Those 97 fires go to stage 2 with only
their province, read off the leading letter.

**Stage 2 — the date, narrowed.** For everything stage 1 missed, the candidates are
the EGIF fires whose local start date is the Catalan ``fire_date``. That set is
then narrowed, in order, by whatever is available:

1. the **province**, where :func:`~src.providers.catalonia_darpa.province_ine_code`
   can read one off the code — five of the six formats carry one;
2. the **municipality name**, normalised on both sides (:func:`normalise_name`);
3. the **geometry**, keeping only candidates whose EGIF ignition point falls inside
   the Catalan perimeter.

The method recorded names the criteria that actually did the narrowing, so
``date_province_name`` and ``date`` are different rows in a report rather than the
same one.

**Stage 3 — nothing.** A fire with no candidate, or with several after all of the
above, is left unbound and reported. That is the conservative half of the design
and it is deliberate: a wrong binding silently attaches another fire's cause and
burnt area to a perimeter, and nothing downstream could ever detect it, while a
missing binding is visible in the first report anyone runs.

.. warning::

   **Stage 2's geometry test is almost never available.** EGIF publishes no
   coordinate whatsoever before 1998 — 0 of the 10,010 Catalan fires of 1982-1997 —
   and nearly every fire that reaches stage 2 is pre-1998. So the municipality name
   is doing almost all of the work in the era that needs the most help, and it is a
   name written by two agencies in two conventions thirty years apart.

   That is why those bindings are labelled and scored below
   :data:`~src.providers.catalonia_darpa.wildfire.MATCH_CODE`, and why the useful
   default for an analysis is ``WHERE match_confidence >= 0.9``.

What the numbers look like
--------------------------

Against the published archives — 860 Catalan perimeters, 25,376 Catalan EGIF fires
of campaigns 1982-2022:

* **778 of the 860 are bound**, 90.5%.
* **601 of those rest on an identifier** — 470 on a literal code match, 122 on a
  decoded one, 9 on a code whose dates disagree. That is 77% of the bindings, and it
  is the number that matters: those are identities rather than inferences.
* **177 come from the candidate stages**, nearly all pre-1997 — 123 on date,
  province and municipality, 44 on date and province, 8 on the date alone, 2 on date
  and municipality.
* **82 are left unbound**, and **45 of them are DARPA 2023 and 2024, which the EGIF
  exports do not reach at all**. Of the 37 that remain, 47 fires in total have no
  EGIF fire on their date and 35 have several the cascade could not separate.

So the real residue is small: **37 fires in forty years that both agencies recorded
and the cascade could not pair.** Anyone re-running this after a newer EGIF export
will pick up 2023 and 2024 as well; that gap is coverage, not matching.

Municipality names are not the same string
-------------------------------------------

The two agencies spell a municipality differently often enough that comparing the
published strings would fail on a quarter of them. :func:`normalise_name` folds
case and accents, strips punctuation, and — the one that matters —
**un-inverts the Catalan article**: EGIF writes ``VALL DE BOI, LA`` where DARPA
writes ``La Vall de Boí``. That takes agreement from 76.7% to 94.4% on the fires
stage 1 has already matched, which is what makes it measurable at all.

The residual 5.6% are real and are left alone deliberately: municipal mergers
(``Montagut`` against ``MONTAGUT I OIX``), spelling drift (``Reixach`` /
``Reixac``, ``Gramenet`` / ``Gramanet``), DARPA naming two municipalities at once
(``Albiol i Alcover``), and at least one genuine disagreement between the agencies
about which municipality a boundary-crossing fire belongs to. A fuzzy threshold
would recover perhaps twenty of them and would introduce a number nobody can
validate; a missed binding is the better failure.

One parte, one perimeter
------------------------

Two Catalan perimeters must never end up bound to the same EGIF fire. Stage 1
cannot do it — ``report_number`` is unique — but stage 2 can: two perimeters on the
same date in the same municipality would both find the same single candidate.

Where that happens **neither is bound**, and both are reported. It is the same
conservative rule as everywhere else, applied in the other direction, and it is
enforced here rather than by a unique constraint so that a genuine many-to-one — a
regional perimeter set that splits what EGIF files as one fire — is a data question
to be looked at rather than a crash halfway through a run.

Re-running
----------

The four columns belong to this application and to nothing else, so a run
**recomputes them from scratch** for every fire in scope: it clears them, works out
the bindings again, and writes what it finds, in one transaction. That makes it
idempotent and makes a re-run after a new EGIF import actually correct old
bindings, which is the point of running it again.

``--only-unbound`` restricts it to fires that have no link yet, for the case where
something outside this application has bound a fire by hand and must not be
overwritten. ``--dry-run`` does the whole of the work and rolls it back.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import os
import sys
import unicodedata

from collections import Counter
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
from src.providers import catalonia_darpa
from src.providers.catalonia_darpa.wildfire import MATCH_CODE
from src.providers.catalonia_darpa.wildfire import MATCH_CODE_DATE_MISMATCH
from src.providers.catalonia_darpa.wildfire import MATCH_CODE_REFORMATTED
from src.providers.catalonia_darpa.wildfire import MATCH_DATE
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_NAME
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_PROVINCE
from src.providers.catalonia_darpa.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.catalonia_darpa.wildfire import MATCH_GEOMETRY
from src.providers.catalonia_darpa.wildfire import MATCH_METHOD_CONFIDENCE

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Why a fire was not bound, for the report. Not stored on the row — the row says
#: only that it has no binding — because these are properties of a run against a
#: particular database and would go stale the moment either side is re-imported.
UNBOUND_NO_CANDIDATE = "no candidate"
UNBOUND_AMBIGUOUS = "several candidates"
UNBOUND_PARTE_CONTESTED = "parte claimed by another perimeter"
UNBOUND_REASONS = (UNBOUND_NO_CANDIDATE, UNBOUND_AMBIGUOUS, UNBOUND_PARTE_CONTESTED)

#: The columns of the ``--csv`` report, in order.
REPORT_COLUMNS = ("code", "fire_date", "year", "municipality_name", "source_layer",
                  "outcome", "method", "confidence", "egif_report_number",
                  "egif_municipality_name", "candidates")

#: The Catalan articles EGIF moves to the end of a municipality name and DARPA
#: leaves at the front.
#:
#: ``VALL DE BOI, LA`` and ``La Vall de Boí`` are the same municipality, and there
#: are enough of them that comparing the published strings fails on a quarter of the
#: dataset. ``L`` is here because ``L'ALBIOL`` loses its apostrophe to the
#: punctuation strip and arrives as a bare ``L``.
ARTICLES = frozenset({"LA", "EL", "ELS", "LES", "L", "SA", "ES", "SES"})

#: Every Catalan fire, with the province code and the EGIF-side keys the cascade
#: needs. The province filter is what keeps the candidate side to the ~25,000 fires
#: that could possibly be Catalan rather than the 586,000 of the national archive.
DARPA_FIRES_SQL = """
SELECT d.id AS id, d.code AS code, d.fire_date AS fire_date, d.year AS year,
       d.municipality_name AS municipality_name, d.source_layer AS source_layer,
       d.egif_wildfire_id AS egif_wildfire_id
FROM darpa_wildfire d
WHERE (CAST(:year AS integer) IS NULL OR d.year = CAST(:year AS integer))
  AND (NOT CAST(:only_unbound AS boolean) OR d.egif_wildfire_id IS NULL)
ORDER BY d.year, d.code
"""

#: Every EGIF *parte* filed in a Catalan province, with its **local** date.
#:
#: ``AT TIME ZONE`` and not the instant: the Catalan ``fire_date`` is a date
#: somebody wrote on a form, and comparing it against a UTC instant would put a
#: late-evening fire on the wrong day for a third of the year. The zone is the one
#: resolved at import, falling back to the Spanish one where no time zone areas
#: were loaded.
EGIF_FIRES_SQL = """
SELECT e.id AS id,
       e.report_number AS report_number,
       e.campaign AS campaign,
       e.province_ine_code AS province_ine_code,
       e.municipality_name AS municipality_name,
       (w.start_date_time AT TIME ZONE COALESCE(w.time_zone, :fallback_time_zone))::date
           AS fire_date,
       (e.ignition_id IS NOT NULL) AS has_point
FROM egif_wildfire e
JOIN wildfire w ON w.id = e.id
WHERE e.province_ine_code = ANY(CAST(:provinces AS text[]))
"""

#: Which of a set of candidate *partes* have their published ignition point inside
#: one Catalan perimeter.
#:
#: The last narrowing of stage 2, and the only one that uses the thing that makes
#: this dataset worth having. Asked per fire rather than as one big join because it
#: is reached by a handful of fires — see the module docstring on why EGIF's
#: coordinates are missing exactly where they would help most.
#: ``wildfire`` and not ``darpa_wildfire``: the EPSG:4326 perimeter is the generic
#: model's column, and it is the right one of the two here — the ignition points are
#: stored in 4326 as well, so the containment test needs no reprojection and no
#: assumption about which grid either side is on.
CONTAINED_SQL = """
SELECT e.id
FROM egif_wildfire e
JOIN ignition i ON i.id = e.ignition_id
JOIN wildfire w ON w.id = :darpa_id
WHERE e.id = ANY(CAST(:candidates AS bigint[]))
  AND w.perimeter IS NOT NULL
  AND ST_Contains(w.perimeter, i.geometry)
"""

#: Clears every binding this application owns, for the fires in scope.
#:
#: Run before the cascade so that a re-run is a recomputation rather than an
#: accumulation: a fire that no longer matches has to *lose* its link, or a
#: correction to either dataset could never take effect.
CLEAR_SQL = """
UPDATE darpa_wildfire
SET egif_wildfire_id = NULL, match_method = NULL,
    match_confidence = NULL, matched_at = NULL
WHERE (CAST(:year AS integer) IS NULL OR year = CAST(:year AS integer))
  AND (NOT CAST(:only_unbound AS boolean) OR egif_wildfire_id IS NULL)
"""

#: Writes one binding.
BIND_SQL = """
UPDATE darpa_wildfire
SET egif_wildfire_id = :egif_id, match_method = :method,
    match_confidence = :confidence, matched_at = :matched_at
WHERE id = :darpa_id
"""


def normalise_name(name: str | None) -> str:
    """A municipality name in the one form both agencies can be compared in.

    Folds case and accents, drops everything that is not a letter or a space, and
    removes a leading or trailing Catalan article.

    Parameters
    ----------
    name : str or None
        A published municipality name, from either side.

    Returns
    -------
    str
        The normalised form, or ``""`` for ``None``, which never compares equal to
        anything (:func:`same_municipality` refuses empty names).

    Examples
    --------
    >>> normalise_name("La Vall de Boí")
    'VALL DE BOI'
    >>> normalise_name("VALL DE BOI, LA")
    'VALL DE BOI'
    >>> normalise_name("L'Albiol") == normalise_name("ALBIOL, L'")
    True

    Notes
    -----
    The article rule is the one that earns its place. EGIF writes the article at the
    end after a comma, in INE's inverted style; DARPA writes it at the front, where
    Catalan puts it. Without this, agreement between the two on fires that stage 1
    has already matched is 74%; with it, 94.4%.

    Accents are folded by decomposing and dropping the combining marks, which
    handles ``ò``, ``í`` and ``ç`` alike without a translation table. The interpunct
    of ``Vil·la`` goes with the punctuation.

    Deliberately **not** fuzzy. See the module docstring: the names that still
    differ afterwards differ for real reasons — mergers, renames, two municipalities
    named at once — and a similarity threshold would turn those into quiet wrong
    answers instead of visible misses.
    """
    if not name:
        return ""
    folded = unicodedata.normalize("NFKD", name).upper()
    letters = "".join(
        character for character in folded if not unicodedata.combining(character)
    )
    # The interpunct of a Catalan geminate L joins its two halves — ``Vil·la`` is
    # one word, ``VILLA`` — and so does the dot the exports sometimes use for it.
    # Every other non-letter separates, which is what keeps the apostrophe of
    # ``L'Albiol`` from welding the article on and hiding it from the rule below.
    letters = letters.replace("·", "").replace(".", "")
    words = "".join(
        character if character.isalpha() else " " for character in letters
    ).split()
    # Only ever strip an article that has something to be an article *of*. Les, in
    # the Val d'Aran, is a municipality whose whole name is the word — strip it and
    # the name becomes the empty string, which matches nothing and would lose a
    # real fire to a rule meant to save one.
    if len(words) > 1 and words[-1] in ARTICLES:
        words = words[:-1]
    if len(words) > 1 and words[0] in ARTICLES:
        words = words[1:]
    return " ".join(words)


def same_municipality(one: str | None, other: str | None) -> bool:
    """Whether two published municipality names are the same place.

    ``False`` if either is missing: an absent name is not evidence of agreement,
    and treating two blanks as a match would bind on nothing at all.
    """
    left, right = normalise_name(one), normalise_name(other)
    return bool(left) and left == right


@dataclass(frozen=True)
class DarpaFire:
    """One Catalan perimeter, as the cascade needs it."""

    id: int
    code: str
    fire_date: datetime.date
    year: int
    municipality_name: str
    source_layer: str

    @property
    def province_ine_code(self) -> str | None:
        """The INE province the code carries, where its format carries one."""
        return catalonia_darpa.province_ine_code(self.code, self.year)

    @property
    def egif_report_number(self) -> str | None:
        """The EGIF report number the code is, once its format is read.

        Identical to :attr:`code` for a 1997-or-later fire and a rearrangement of it
        for most of 1986-1996 — see
        :func:`~src.providers.catalonia_darpa.egif_report_number`.
        """
        return catalonia_darpa.egif_report_number(self.code, self.year)


@dataclass(frozen=True)
class EgifFire:
    """One Spanish *parte*, as the cascade needs it."""

    id: int
    report_number: str
    campaign: int | None
    province_ine_code: str | None
    municipality_name: str | None
    fire_date: datetime.date | None
    has_point: bool


@dataclass
class Binding:
    """What the cascade concluded about one Catalan perimeter.

    Attributes
    ----------
    fire : DarpaFire
        The perimeter.
    egif : EgifFire or None
        The *parte* it was bound to, or ``None``.
    method : str or None
        Which rule produced the binding, from
        :data:`~src.providers.catalonia_darpa.wildfire.MATCH_METHODS`.
    reason : str or None
        Why there is no binding, from :data:`UNBOUND_REASONS`. Exactly one of this
        and :attr:`method` is set.
    candidates : int
        How many *partes* were still in play when the cascade gave up or decided.
        ``1`` for a binding; for an ambiguous fire, the number that made it
        ambiguous, which is the useful thing to look at in the report.
    """

    fire: DarpaFire
    egif: EgifFire | None = None
    method: str | None = None
    reason: str | None = None
    candidates: int = 0

    @property
    def is_bound(self) -> bool:
        return self.egif is not None

    @property
    def confidence(self) -> float | None:
        """The confidence for :attr:`method`, or ``None`` where there is no binding."""
        return None if self.method is None else MATCH_METHOD_CONFIDENCE[self.method]

    @property
    def row(self) -> tuple:
        """The binding as the CSV report writes it, in :data:`REPORT_COLUMNS` order."""
        return (
            self.fire.code, self.fire.fire_date.isoformat(), self.fire.year,
            self.fire.municipality_name, self.fire.source_layer,
            "bound" if self.is_bound else "unbound",
            self.method or "", "" if self.confidence is None else f"{self.confidence:.2f}",
            self.egif.report_number if self.egif else "",
            (self.egif.municipality_name or "") if self.egif else "",
            self.candidates,
        )


@dataclass
class Index:
    """The EGIF side, indexed the three ways the cascade looks things up.

    Built once per run rather than queried per fire: 25,000 Catalan *partes* is a
    few megabytes, and 860 lookups against three dictionaries is immeasurably
    faster than 860 round trips. The geometry test is the one thing that stays in
    the database, because the perimeters are there and a handful of fires reach it.
    """

    by_report: dict[str, EgifFire] = field(default_factory=dict)
    by_date: dict[datetime.date, list[EgifFire]] = field(
        default_factory=lambda: defaultdict(list))
    fires: list[EgifFire] = field(default_factory=list)

    @classmethod
    def build(cls, fires: list[EgifFire]) -> Index:
        index = cls(fires=fires)
        for fire in fires:
            index.by_report[fire.report_number] = fire
            if fire.fire_date is not None:
                index.by_date[fire.fire_date].append(fire)
        return index


def load_darpa_fires(session: Session, year: int | None,
                     only_unbound: bool) -> list[DarpaFire]:
    """The Catalan perimeters in scope."""
    return [
        DarpaFire(id=record.id, code=record.code, fire_date=record.fire_date,
                  year=record.year, municipality_name=record.municipality_name,
                  source_layer=record.source_layer)
        for record in session.execute(
            text(DARPA_FIRES_SQL), {"year": year, "only_unbound": only_unbound})
    ]


def load_egif_fires(session: Session) -> list[EgifFire]:
    """Every *parte* filed in a Catalan province, whatever the scope of the run.

    Not narrowed by ``--year``: a Catalan fire's *parte* is filed under the campaign
    EGIF assigns it, and while the two agree everywhere in the published data,
    restricting the candidate side by a year taken from the other dataset would
    build that agreement into the answer instead of testing it.
    """
    return [
        EgifFire(id=record.id, report_number=record.report_number,
                 campaign=record.campaign,
                 province_ine_code=record.province_ine_code,
                 municipality_name=record.municipality_name,
                 fire_date=record.fire_date, has_point=record.has_point)
        for record in session.execute(text(EGIF_FIRES_SQL), {
            "provinces": list(catalonia_darpa.PROVINCE_INE_CODES),
            "fallback_time_zone": catalonia_darpa.DEFAULT_TIME_ZONE,
        })
    ]


def contained_candidates(session: Session, fire: DarpaFire,
                         candidates: list[EgifFire]) -> list[EgifFire]:
    """Those candidates whose ignition point falls inside this perimeter.

    The last narrowing of stage 2. Only the candidates that publish a point can be
    tested at all, and if none does the set is returned unchanged — a test that
    cannot be run must not silently reject everything.
    """
    testable = [candidate for candidate in candidates if candidate.has_point]
    if not testable:
        return candidates

    inside = set(session.scalars(text(CONTAINED_SQL), {
        "darpa_id": fire.id,
        "candidates": [candidate.id for candidate in testable],
    }))
    narrowed = [candidate for candidate in candidates if candidate.id in inside]
    return narrowed or candidates


def match(fire: DarpaFire, index: Index, session: Session | None = None) -> Binding:
    """Run the cascade for one perimeter.

    Parameters
    ----------
    fire : DarpaFire
        The Catalan perimeter to bind.
    index : Index
        The EGIF side.
    session : Session, optional
        Needed only for the geometry narrowing, which is the one stage that asks
        the database. Without it that stage is skipped, which is what lets the whole
        cascade be tested without a perimeter in sight.

    Returns
    -------
    Binding
        Bound or not, with the rule or the reason.

    Notes
    -----
    Stage 1 first and unconditionally: an identifier match cannot be improved on,
    and a date that disagrees with it is a fact about the two sources rather than a
    reason to doubt the identifier.

    After that every step is the same shape — narrow the candidate set, and stop
    the moment exactly one is left. The method recorded names the criteria that
    were actually applied by then, so a fire that was unique on its date alone is
    not recorded as though the municipality had confirmed it.
    """
    matched = index.by_report.get(fire.code)
    if matched is not None:
        return Binding(
            fire=fire, egif=matched, candidates=1,
            method=MATCH_CODE if matched.fire_date == fire.fire_date
            else MATCH_CODE_DATE_MISMATCH,
        )

    # The older formats are the same identifier rearranged. A decode is a reading
    # of a format rather than string equality, so unlike the literal match above it
    # has to be confirmed by the date before it is believed; a decode the date
    # contradicts falls through to the candidate stages below rather than winning.
    reformatted = fire.egif_report_number
    if reformatted is not None and reformatted != fire.code:
        decoded = index.by_report.get(reformatted)
        if decoded is not None and decoded.fire_date == fire.fire_date:
            return Binding(fire=fire, egif=decoded, candidates=1,
                           method=MATCH_CODE_REFORMATTED)

    candidates = list(index.by_date.get(fire.fire_date, ()))
    if not candidates:
        return Binding(fire=fire, reason=UNBOUND_NO_CANDIDATE, candidates=0)
    if len(candidates) == 1:
        return Binding(fire=fire, egif=candidates[0], method=MATCH_DATE, candidates=1)

    province = fire.province_ine_code
    narrowed = ([c for c in candidates if c.province_ine_code == province]
                if province else candidates)
    # A province that excludes every candidate is a disagreement between the code
    # and the parte, not a filter: keep the wider set and let the name decide.
    if province and narrowed:
        candidates, used_province = narrowed, True
    else:
        used_province = False
    if len(candidates) == 1:
        return Binding(fire=fire, egif=candidates[0], candidates=1,
                       method=MATCH_DATE_PROVINCE if used_province else MATCH_DATE)

    by_name = [c for c in candidates
               if same_municipality(fire.municipality_name, c.municipality_name)]
    if len(by_name) == 1:
        return Binding(fire=fire, egif=by_name[0], candidates=1,
                       method=MATCH_DATE_PROVINCE_NAME if used_province
                       else MATCH_DATE_NAME)
    if by_name:
        candidates = by_name

    if session is not None:
        inside = contained_candidates(session, fire, candidates)
        if len(inside) == 1:
            return Binding(fire=fire, egif=inside[0], method=MATCH_GEOMETRY,
                           candidates=1)
        candidates = inside

    return Binding(fire=fire, reason=UNBOUND_AMBIGUOUS, candidates=len(candidates))


def resolve_contested(bindings: list[Binding], logger: logging.Logger) -> int:
    """Unbind every *parte* that two perimeters both claim, returning how many went.

    Stage 1 cannot produce a contest — ``report_number`` is unique — so a contested
    *parte* is always two fuzzy matches, which means neither is trustworthy. Both
    are dropped rather than one picked: there is nothing in the data that would make
    the choice, and picking anyway is exactly the silent wrong answer this
    application is built to avoid.

    See the module docstring for why this is enforced here rather than by a unique
    constraint.
    """
    claims: dict[int, list[Binding]] = defaultdict(list)
    for binding in bindings:
        if binding.is_bound:
            claims[binding.egif.id].append(binding)

    dropped = 0
    for contested in claims.values():
        if len(contested) < 2:
            continue
        logger.warning(
            "EGIF parte %s is claimed by %d perimeters (%s); none of them is bound",
            contested[0].egif.report_number, len(contested),
            ", ".join(binding.fire.code for binding in contested))
        for binding in contested:
            binding.egif = None
            binding.method = None
            binding.reason = UNBOUND_PARTE_CONTESTED
            binding.candidates = len(contested)
            dropped += 1
    return dropped


def bind(session: Session, bindings: list[Binding], matched_at: datetime.datetime,
         year: int | None, only_unbound: bool) -> int:
    """Clear the columns in scope and write the bindings, returning how many.

    The clear comes first and covers the whole scope, not just the fires being
    bound: a fire that used to match and no longer does has to lose its link, or a
    correction to either dataset could never take effect.
    """
    session.execute(text(CLEAR_SQL), {"year": year, "only_unbound": only_unbound})
    written = [binding for binding in bindings if binding.is_bound]
    for binding in written:
        session.execute(text(BIND_SQL), {
            "darpa_id": binding.fire.id,
            "egif_id": binding.egif.id,
            "method": binding.method,
            "confidence": binding.confidence,
            "matched_at": matched_at,
        })
    return len(written)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Bind the Catalan DARPA perimeters to the Spanish EGIF partes.",
        epilog="Import both datasets first. Only darpa_wildfire's four binding "
               "columns are ever written. A perimeter is bound only when exactly one "
               "parte survives the cascade, so an ambiguous fire is left unbound and "
               "reported rather than guessed at. Database settings not given here are "
               "read from the environment (.env).",
    )
    parser.add_argument("-y", "--year", type=int,
                        help="bind only the Catalan fires of this year; the candidate "
                             "partes are never restricted by it")
    parser.add_argument("--only-unbound", action="store_true",
                        help="leave fires that already have a link alone, instead of "
                             "recomputing every binding in scope. Use it when something "
                             "outside this application has bound a fire by hand")
    parser.add_argument("--dry-run", action="store_true",
                        help="do all the work and roll it back, reporting what would "
                             "have been bound")
    parser.add_argument("--csv", type=Path,
                        help="write the outcome for every fire in scope to this .csv, "
                             "bound and unbound alike — which is the file to read when "
                             "deciding whether a rule is doing what it should")

    common.add_database_arguments(parser)
    parser.add_argument("--log-level", default=os.getenv("GISFIRE_LOG_LEVEL", "INFO"),
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="verbosity (env: GISFIRE_LOG_LEVEL, default INFO)")
    return parser.parse_args(argv)


def write_csv(bindings: list[Binding], path: Path, logger: logging.Logger) -> None:
    """Write the outcome for every fire in scope, bound and unbound alike.

    Both, deliberately. A report of the successes says nothing about whether the
    rules are right; the unbound rows and their candidate counts are what shows
    where the cascade is running out of evidence and what a further rule would have
    to work with.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for binding in bindings:
            writer.writerow(binding.row)
    logger.info("Wrote %s", path)


def report(bindings: list[Binding], logger: logging.Logger) -> None:
    """Log what the run concluded, by method and by reason."""
    bound = [binding for binding in bindings if binding.is_bound]
    methods = Counter(binding.method for binding in bound)
    reasons = Counter(binding.reason for binding in bindings if not binding.is_bound)

    logger.info("Bound %d of %d Catalan fire(s)", len(bound), len(bindings))
    for method, count in sorted(methods.items(),
                                key=lambda item: -MATCH_METHOD_CONFIDENCE[item[0]]):
        logger.info("  %-20s %5d  (confidence %.2f)", method, count,
                    MATCH_METHOD_CONFIDENCE[method])
    for reason in UNBOUND_REASONS:
        if reasons[reason]:
            logger.info("  unbound: %-11s %5d", reason, reasons[reason])

    exact = sum(count for method, count in methods.items()
                if MATCH_METHOD_CONFIDENCE[method] >= 0.9)
    if bound and exact < len(bound):
        logger.warning(
            "%d of the %d bindings rest on a date and a municipality name rather than "
            "on the published identifier: filter on match_confidence >= 0.9 for the "
            "ones that do not", len(bound) - exact, len(bound))


def bind_wildfires(args: argparse.Namespace, engine: Engine,
                   logger: logging.Logger) -> list[Binding]:
    """Run the whole binding against ``engine``, returning what it concluded."""
    common.require_tables(engine, ["darpa_wildfire", "egif_wildfire", "wildfire"], logger)
    matched_at = datetime.datetime.now(datetime.timezone.utc)

    with Session(engine) as session:
        with common.Spinner("Reading the Catalan perimeters and the Spanish partes",
                            logger):
            fires = load_darpa_fires(session, args.year, args.only_unbound)
            index = Index.build(load_egif_fires(session))

        if not fires and args.only_unbound:
            # Not an error: "bind what is not bound yet" has nothing to do, which is
            # the state a second --only-unbound run is supposed to reach.
            logger.info("Every Catalan fire in scope is already bound; nothing to do")
            return []
        if not fires:
            raise RuntimeError(
                "No Catalan wildfires in scope. Check --year, and that the DARPA "
                "perimeters are imported."
            )
        if not index.fires:
            raise RuntimeError(
                "No EGIF partes are filed in a Catalan province, so there is nothing to "
                "bind to. Import the EGIF fire statistics first."
            )
        logger.info("%d Catalan perimeter(s) against %d Catalan parte(s)",
                    len(fires), len(index.fires))

        with common.Spinner("Matching", logger):
            bindings = [match(fire, index, session) for fire in fires]
        resolve_contested(bindings, logger)

        written = bind(session, bindings, matched_at, args.year, args.only_unbound)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    report(bindings, logger)
    logger.info("%s %d binding(s)", "Would have written" if args.dry_run else "Wrote",
                written)
    return bindings


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("darpa-egif-bind")

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
