#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bind the Andalusian REDIAM perimeters to the Spanish EGIF *partes*.

Fills in :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`
and the three columns that account for it — ``match_method``, ``match_confidence`` and
``matched_at`` — for fires already imported by both
:mod:`~src.apps.imports.wildfires.andalusia_rediam.import_wildfires` and
:mod:`~src.apps.imports.wildfires.spain_egif.import_wildfires`.

It writes nothing else, ever. No row is created, no perimeter is touched, no EGIF
column is written: the whole of this application's effect is four columns on
``rediam_wildfire``, and running it on an empty database is a no-op::

    python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires
    python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires --year 2022
    python3 -m src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires \\
        --dry-run --csv bindings.csv

The Catalan counterpart
-----------------------

:mod:`~src.apps.bindings.wildfires.catalonia_darpa.bind_egif_wildfires` is the same
application over the other regional dataset, and this one is deliberately its twin:
same cascade shape, same confidences for the rules they share, same CSV, same refusal
to guess. Read that module for the argument; what follows is what is *different* here,
which is mostly that this dataset is easier.

Two differences do matter and both are in the same direction: the identifier is an
identifier from the first year rather than from 1997, and the fallback rules are
therefore reached by 25 fires rather than by 177.

The cascade
-----------

Each stage narrows a set of candidates, and a link is written **only when exactly one
candidate is left**. Every stage is a filter, never a ranking — nothing here picks a
best guess.

**Stage 1 — the code.** ``CODIGO`` **is** the EGIF ``report_number``: the same ten
characters, year plus INE province plus four-digit sequence. ``report_number`` is
unique across the whole national archive, so there is nothing to disambiguate. The two
published dates are then compared, which makes the stage self-checking rather than
merely assumed.

**Stage 1b — the code read rather than compared.** Two published shapes are the same
identifier written differently: the ``IIFF`` prefix of a 2025 code, and six 2019 codes
whose four-digit sequence is written with three.
:func:`~src.providers.andalusia_rediam.egif_report_number` reads both.

A decode is a reading of a format rather than string equality, so — exactly as in
Catalonia — it **has to be confirmed by the date**, and one the date contradicts falls
through to the stages below rather than winning.

**Stage 2 — date, province, and then the map.** Only for the fires whose report number
EGIF does not have at all. The province comes from the code and is always there, so the
candidate set starts as *the partes of that province on that date* and is narrowed by
the municipality name and finally by testing which EGIF ignition points fall inside the
perimeter.

**Stage 3 — nothing.** A fire with no candidate, or with several after all of that, is
left unbound and reported.

What actually happens, on the published data
---------------------------------------------

907 Andalusian perimeters against 40,757 Andalusian *partes* of campaigns 1982-2023:

======================  ======  ================================================
``match_method``        Fires   Notes
======================  ======  ================================================
``code``                   702  string equality with the ``report_number``
``code_reformatted``         5  five of the six nine-digit 2019 codes
``code_date_mismatch``      42  the dates differ by 1 day to 5 weeks
``date_province_name``       2  where EGIF has no such report number
``date_province``            8  same, and the only *parte* of that day and province
``geometry``                 0  see below
*(unbound)*                148  **133 of them are 2024 and 2025**
======================  ======  ================================================

**759 of the 907 perimeters are bound — 83.7%** — and **749 of those rest on the
published identifier**, which is 98.7% of the bindings. The Catalan figures are 90.5%
and 77%: fewer bound here, and far more of them certain.

The unbound are almost entirely a coverage gap rather than a matching failure. The EGIF
exports stop at campaign 2023, and REDIAM publishes 2024 and 2025 — 133 fires with no
*parte* to match at all. Of the remaining 15, nine are 2023, where the export is
partial. **The real residue is six fires in fifteen years**: REDIAM publishes a code
whose report number EGIF has never issued, and no *parte* of that date and province can
be singled out.

The geometry rule binds nothing today, and that is not a failure of it: the ten fires
that reach stage 2 at all are settled by the province or the municipality name before
the map is consulted. It stays because it is the strongest evidence available when they
are not — see *The geometry test is evidence, not proof* below.

Why there is no ``date`` or ``date_name`` rule
-----------------------------------------------

The Catalan cascade has two more methods, for the case where a code carries **no
province**: a third of its archive uses formats that encode none. Every Andalusian code
encodes one — all 962 published features decode to one of the eight
:data:`~src.providers.andalusia_rediam.PROVINCE_INE_CODES` — so those branches cannot
be reached.

A fire whose code did **not** decode is therefore left unbound, with a reason of its
own (:data:`UNBOUND_NO_PROVINCE`), rather than bound on a date alone. That is not
timidity: a date alone, against a province with 40,757 *partes*, is not evidence.

The municipality name is weaker here than in Catalonia
-------------------------------------------------------

``Municipio`` is often not a municipality. It is frequently the *paraje* — the site —
and sometimes the site hyphenated with the municipality: ``DEHESA DE LAS YEGUAS`` for a
fire EGIF files in Puerto Real, ``RETIN-BARBATE`` for one it files in Barbate.

Measured on the 749 fires stage 1 has already matched, which is the only ground truth
available: the published names agree on 81.0% of them, and 89.5% after
:func:`normalise_name`. The Catalan pair reaches 94.4%.

.. note::

   Splitting a hyphenated name and accepting either half was tried and **rejected**. It
   raises agreement from 89.5% to 90.0% — four fires — and one of the four is
   ``CULLAR-BAZA`` matching ``Cúllar``, where Cúllar and Baza are two different
   municipalities and the rule is right by accident. A rule that gains 0.5% and can be
   wrong for the reason it is right is not worth having in a cascade whose whole
   discipline is refusing to guess.

The geometry test is evidence, not proof
-----------------------------------------

EGIF publishes an ignition coordinate for 12,378 of the 12,389 Andalusian *partes* of
2008-2023, so unlike in Catalonia — where it publishes none at all before 1998, which is
where the unresolved fires are — the containment test is nearly always available.

It is used to narrow and never to reject. Of the 748 fires bound by identifier that have
a point, **only 417 have that point inside the perimeter**: a published start point and a
perimeter mapped afterwards disagree at this scale routinely, in both directions and in
both datasets (REDIAM's own points are inside their own perimeter 88 times out of 201).

So a candidate whose point is outside is not thereby excluded — the test narrows a set
only when it leaves at least one candidate standing, and a set it would empty is passed
through untouched.

One *parte*, one perimeter
---------------------------

Two perimeters claiming the same *parte* would be a contradiction, and
:func:`resolve_contested` unbinds **both** rather than picking one. Stage 1 cannot
produce a contest — ``report_number`` is unique on the EGIF side and ``(code, date)`` on
the REDIAM side, and the 907 codes decode to 907 distinct report numbers — so a contested
*parte* is always two fuzzy matches, which means neither is trustworthy.

This is enforced here rather than by a unique constraint on ``egif_wildfire_id`` for the
Catalan module's reason: the constraint would make a re-run fail on a conflict instead of
reporting it, and the two datasets are published independently and will disagree again.

Re-running
----------

Every run **recomputes** the bindings in scope: the four columns are cleared first, then
written. A fire that no longer matches loses its link, which is what makes a correction
to either dataset take effect.

``--only-unbound`` restricts it to fires with no link yet, for the case where something
outside this application has bound a fire by hand.

``--csv`` writes one row per fire in scope, **bound and unbound alike**. A report of the
successes says nothing about whether the rules are right; the unbound rows and their
candidate counts are what shows where the cascade ran out of evidence.
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
from src.providers import andalusia_rediam
from src.providers.andalusia_rediam.wildfire import MATCH_CODE
from src.providers.andalusia_rediam.wildfire import MATCH_CODE_DATE_MISMATCH
from src.providers.andalusia_rediam.wildfire import MATCH_CODE_REFORMATTED
from src.providers.andalusia_rediam.wildfire import MATCH_DATE_PROVINCE
from src.providers.andalusia_rediam.wildfire import MATCH_DATE_PROVINCE_NAME
from src.providers.andalusia_rediam.wildfire import MATCH_GEOMETRY
from src.providers.andalusia_rediam.wildfire import MATCH_METHOD_CONFIDENCE

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

#: Why a fire was not bound, for the report. Not stored on the row — the row says only
#: that it has no binding — because these are properties of a run against a particular
#: database and would go stale the moment either side is re-imported.
#:
#: :data:`UNBOUND_NO_PROVINCE` is this application's own: the Catalan cascade falls back
#: to a date alone when a code carries no province, and this one refuses to. See the
#: module docstring.
UNBOUND_NO_CANDIDATE = "no candidate"
UNBOUND_AMBIGUOUS = "several candidates"
UNBOUND_PARTE_CONTESTED = "parte claimed by another perimeter"
UNBOUND_NO_PROVINCE = "code carries no province"
UNBOUND_REASONS = (UNBOUND_NO_CANDIDATE, UNBOUND_AMBIGUOUS, UNBOUND_PARTE_CONTESTED,
                   UNBOUND_NO_PROVINCE)

#: The columns of the ``--csv`` report, in order. The Catalan report's, with
#: ``province_name`` added: this dataset publishes one and it is worth seeing beside the
#: municipality when reading why a name rule did or did not fire.
REPORT_COLUMNS = ("code", "fire_date", "year", "municipality_name", "province_name",
                  "source_layer", "outcome", "method", "confidence",
                  "egif_report_number", "egif_municipality_name", "candidates")

#: The Spanish articles either agency may move to the end of a municipality name.
#:
#: REDIAM writes ``EJIDO (EL)`` and EGIF ``EJIDO, EL``; both mean *El Ejido*. The
#: parentheses and the comma are gone by the time this set is consulted — everything
#: that is not a letter has become a space — so one rule covers both spellings.
ARTICLES = frozenset({"EL", "LA", "LOS", "LAS", "L"})

#: The confidence at or above which a binding rests on the published identifier rather
#: than on a date and a name.
#:
#: The boundary between the two kinds of claim, and the only place the difference is
#: acted on rather than merely recorded: :func:`resolve_contested` lets an identifier
#: match win a contested *parte* and refuses to choose between guesses. Taken from
#: :data:`~src.providers.andalusia_rediam.wildfire.MATCH_CODE_DATE_MISMATCH`, the
#: weakest of the identifier rules, so the two cannot drift apart.
IDENTIFIER_CONFIDENCE = MATCH_METHOD_CONFIDENCE[MATCH_CODE_DATE_MISMATCH]

#: Every Andalusian fire, with the keys the cascade needs.
REDIAM_FIRES_SQL = """
SELECT s.id AS id, s.code AS code, s.fire_date AS fire_date, s.year AS year,
       s.municipality_name AS municipality_name, s.province_name AS province_name,
       s.source_layer AS source_layer,
       s.egif_wildfire_id AS egif_wildfire_id
FROM rediam_wildfire s
WHERE (CAST(:year AS integer) IS NULL OR s.year = CAST(:year AS integer))
  AND (NOT CAST(:only_unbound AS boolean) OR s.egif_wildfire_id IS NULL)
ORDER BY s.year, s.code
"""

#: Every EGIF *parte* filed in an Andalusian province, with its **local** date.
#:
#: ``AT TIME ZONE`` and not the instant: the Andalusian ``fire_date`` is a date somebody
#: wrote on a form, and comparing it against a UTC instant would put a late-evening fire
#: on the wrong day for a third of the year. The zone is the one resolved at import,
#: falling back to the Spanish one where no time zone areas were loaded.
#:
#: The province filter is what keeps the candidate side to the ~40,000 *partes* that
#: could possibly be Andalusian rather than the 586,000 of the national archive.
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

#: Which of a set of candidate *partes* have their published ignition point inside one
#: Andalusian perimeter.
#:
#: ``wildfire`` and not ``rediam_wildfire``: the EPSG:4326 perimeter is the generic
#: model's column, and it is the right one of the two here — the ignition points are
#: stored in 4326 as well, so the containment test needs no reprojection and no
#: assumption about which grid either side is on.
CONTAINED_SQL = """
SELECT e.id
FROM egif_wildfire e
JOIN ignition i ON i.id = e.ignition_id
JOIN wildfire w ON w.id = :rediam_id
WHERE e.id = ANY(CAST(:candidates AS bigint[]))
  AND w.perimeter IS NOT NULL
  AND ST_Contains(w.perimeter, i.geometry)
"""

#: Clears every binding this application owns, for the fires in scope.
#:
#: Run before the cascade so that a re-run is a recomputation rather than an
#: accumulation: a fire that no longer matches has to *lose* its link, or a correction
#: to either dataset could never take effect.
CLEAR_SQL = """
UPDATE rediam_wildfire
SET egif_wildfire_id = NULL, match_method = NULL,
    match_confidence = NULL, matched_at = NULL
WHERE (CAST(:year AS integer) IS NULL OR year = CAST(:year AS integer))
  AND (NOT CAST(:only_unbound AS boolean) OR egif_wildfire_id IS NULL)
"""

#: Writes one binding.
BIND_SQL = """
UPDATE rediam_wildfire
SET egif_wildfire_id = :egif_id, match_method = :method,
    match_confidence = :confidence, matched_at = :matched_at
WHERE id = :rediam_id
"""


def normalise_name(name: str | None) -> str:
    """A municipality name in the one form both agencies can be compared in.

    Folds case and accents, drops everything that is not a letter or a space, and
    removes a leading or trailing Spanish article.

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
    >>> normalise_name("EJIDO (EL)")
    'EJIDO'
    >>> normalise_name("El Ejido") == normalise_name("EJIDO, EL")
    True
    >>> normalise_name("ALMODOVAR DEL RÍO")
    'ALMODOVAR DEL RIO'

    Notes
    -----
    The article rule earns its place on both sides at once: REDIAM writes
    ``EJIDO (EL)`` and EGIF ``EJIDO, EL``, and by the time the words are compared the
    parentheses and the comma have both become spaces, so one rule handles both.

    Accents are folded by decomposing and dropping the combining marks, which handles
    ``á``, ``í`` and ``ñ`` alike without a translation table. Note that this makes
    ``CAÑETE`` and ``CANETE`` the same name, which is what is wanted: the two agencies
    disagree about the tilde far more often than two real places differ only by it.

    Deliberately **not** fuzzy, and deliberately not clever about hyphens — see the
    module docstring. The names that still differ afterwards differ because REDIAM
    named the *paraje* and EGIF the municipality, and no string rule fixes that
    honestly.
    """
    if not name:
        return ""
    folded = unicodedata.normalize("NFKD", name).upper()
    letters = "".join(
        character for character in folded if not unicodedata.combining(character)
    )
    words = "".join(
        character if character.isalpha() else " " for character in letters
    ).split()
    # Only ever strip an article that has something to be an article *of*, so that a
    # municipality whose whole name is the word does not become the empty string and
    # match nothing.
    if len(words) > 1 and words[-1] in ARTICLES:
        words = words[:-1]
    if len(words) > 1 and words[0] in ARTICLES:
        words = words[1:]
    return " ".join(words)


def same_municipality(one: str | None, other: str | None) -> bool:
    """Whether two published municipality names are the same place.

    ``False`` if either is missing: an absent name is not evidence of agreement, and
    treating two blanks as a match would bind on nothing at all.
    """
    left, right = normalise_name(one), normalise_name(other)
    return bool(left) and left == right


@dataclass(frozen=True)
class RediamFire:
    """One Andalusian perimeter, as the cascade needs it."""

    id: int
    code: str
    fire_date: datetime.date
    year: int
    municipality_name: str
    province_name: str
    source_layer: str

    @property
    def egif_report_number(self) -> str | None:
        """The EGIF report number the code is, once its format is read.

        Identical to :attr:`code` for most fires, and a reading of it for the ``IIFF``
        prefix and the nine-digit sequence — see
        :func:`~src.providers.andalusia_rediam.egif_report_number`.
        """
        return andalusia_rediam.egif_report_number(self.code)

    @property
    def province_ine_code(self) -> str | None:
        """The INE province the code carries.

        Never ``None`` on the published archive: all 962 features decode. A fire where
        it is ``None`` is left unbound rather than matched on a date alone — see the
        module docstring.
        """
        report = self.egif_report_number
        return report[4:6] if report else None


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
    """What the cascade concluded about one Andalusian perimeter.

    Attributes
    ----------
    fire : RediamFire
        The perimeter.
    egif : EgifFire or None
        The *parte* it was bound to, or ``None``.
    method : str or None
        Which rule produced the binding, from
        :data:`~src.providers.andalusia_rediam.wildfire.MATCH_METHODS`.
    reason : str or None
        Why there is no binding, from :data:`UNBOUND_REASONS`. Exactly one of this and
        :attr:`method` is set.
    candidates : int
        How many *partes* were still in play when the cascade gave up or decided. ``1``
        for a binding; for an ambiguous fire, the number that made it ambiguous, which
        is the useful thing to look at in the report.
    """

    fire: RediamFire
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
            self.fire.municipality_name, self.fire.province_name,
            self.fire.source_layer,
            "bound" if self.is_bound else "unbound",
            self.method or "", "" if self.confidence is None else f"{self.confidence:.2f}",
            self.egif.report_number if self.egif else "",
            (self.egif.municipality_name or "") if self.egif else "",
            self.candidates,
        )


@dataclass
class Index:
    """The EGIF side, indexed the two ways the cascade looks things up.

    Built once per run rather than queried per fire: 40,000 Andalusian *partes* is a few
    megabytes, and 907 lookups against two dictionaries is immeasurably faster than 907
    round trips. The geometry test is the one thing that stays in the database, because
    the perimeters are there and a handful of fires reach it.
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


def load_rediam_fires(session: Session, year: int | None,
                      only_unbound: bool) -> list[RediamFire]:
    """The Andalusian perimeters in scope."""
    return [
        RediamFire(id=record.id, code=record.code, fire_date=record.fire_date,
                   year=record.year, municipality_name=record.municipality_name,
                   province_name=record.province_name,
                   source_layer=record.source_layer)
        for record in session.execute(
            text(REDIAM_FIRES_SQL), {"year": year, "only_unbound": only_unbound})
    ]


def load_egif_fires(session: Session) -> list[EgifFire]:
    """Every *parte* filed in an Andalusian province, whatever the scope of the run.

    Not narrowed by ``--year``: an Andalusian fire's *parte* is filed under the campaign
    EGIF assigns it, and while the two agree everywhere in the published data,
    restricting the candidate side by a year taken from the other dataset would build
    that agreement into the answer instead of testing it.
    """
    return [
        EgifFire(id=record.id, report_number=record.report_number,
                 campaign=record.campaign,
                 province_ine_code=record.province_ine_code,
                 municipality_name=record.municipality_name,
                 fire_date=record.fire_date, has_point=record.has_point)
        for record in session.execute(text(EGIF_FIRES_SQL), {
            "provinces": list(andalusia_rediam.PROVINCE_INE_CODES),
            "fallback_time_zone": andalusia_rediam.DEFAULT_TIME_ZONE,
        })
    ]


def contained_candidates(session: Session, fire: RediamFire,
                         candidates: list[EgifFire]) -> list[EgifFire]:
    """Those candidates whose ignition point falls inside this perimeter.

    The last narrowing of stage 2. Only the candidates that publish a point can be
    tested at all, and **if the test would leave nothing the set is returned
    unchanged**: a point outside a perimeter is ordinary in this pair of datasets — 331
    of the 748 identifier-matched fires have one — so an empty result means the test had
    nothing to say, not that every candidate is wrong.
    """
    testable = [candidate for candidate in candidates if candidate.has_point]
    if not testable:
        return candidates

    inside = set(session.scalars(text(CONTAINED_SQL), {
        "rediam_id": fire.id,
        "candidates": [candidate.id for candidate in testable],
    }))
    narrowed = [candidate for candidate in candidates if candidate.id in inside]
    return narrowed or candidates


def match(fire: RediamFire, index: Index, session: Session | None = None) -> Binding:
    """Run the cascade for one perimeter.

    Parameters
    ----------
    fire : RediamFire
        The Andalusian perimeter to bind.
    index : Index
        The EGIF side.
    session : Session, optional
        Needed only for the geometry narrowing, which is the one stage that asks the
        database. Without it that stage is skipped, which is what lets the whole cascade
        be tested without a perimeter in sight.

    Returns
    -------
    Binding
        Bound or not, with the rule or the reason.

    Notes
    -----
    Stage 1 first and unconditionally: an identifier match cannot be improved on, and a
    date that disagrees with it is a fact about the two sources rather than a reason to
    doubt the identifier.

    After that every step is the same shape — narrow the candidate set, and stop the
    moment exactly one is left. The method recorded names the criteria that were
    actually applied by then, so a fire that was unique on its date and province alone
    is not recorded as though the municipality had confirmed it.
    """
    matched = index.by_report.get(fire.code)
    if matched is not None:
        return Binding(
            fire=fire, egif=matched, candidates=1,
            method=MATCH_CODE if matched.fire_date == fire.fire_date
            else MATCH_CODE_DATE_MISMATCH,
        )

    # The IIFF prefix and the three-digit sequence are the same identifier written
    # differently. A decode is a reading of a format rather than string equality, so
    # unlike the literal match above it has to be confirmed by the date; a decode the
    # date contradicts falls through to the candidate stages below rather than winning.
    report = fire.egif_report_number
    if report is not None and report != fire.code:
        decoded = index.by_report.get(report)
        if decoded is not None:
            if decoded.fire_date == fire.fire_date:
                return Binding(fire=fire, egif=decoded, candidates=1,
                               method=MATCH_CODE_REFORMATTED)
            # The identifier is still an identifier, and the Catalan cascade binds the
            # undecoded form under the same disagreement. Refusing here would make the
            # IIFF prefix the difference between a link and none.
            return Binding(fire=fire, egif=decoded, candidates=1,
                           method=MATCH_CODE_DATE_MISMATCH)

    province = fire.province_ine_code
    if province is None:
        # Every published code decodes, so this is a format the provider has not used
        # yet. Binding it on a date alone, against a region with 40,757 partes, would
        # not be a weaker answer but a different kind of thing entirely.
        return Binding(fire=fire, reason=UNBOUND_NO_PROVINCE, candidates=0)

    candidates = [candidate for candidate in index.by_date.get(fire.fire_date, ())
                  if candidate.province_ine_code == province]
    if not candidates:
        return Binding(fire=fire, reason=UNBOUND_NO_CANDIDATE, candidates=0)
    if len(candidates) == 1:
        return Binding(fire=fire, egif=candidates[0], method=MATCH_DATE_PROVINCE,
                       candidates=1)

    by_name = [candidate for candidate in candidates
               if same_municipality(fire.municipality_name, candidate.municipality_name)]
    if len(by_name) == 1:
        return Binding(fire=fire, egif=by_name[0], method=MATCH_DATE_PROVINCE_NAME,
                       candidates=1)
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
    """Settle every *parte* that two perimeters both claim, returning how many were dropped.

    Two perimeters cannot be the same fire, so a contested *parte* means at least one of
    the claims is wrong. What happens next depends on **what kind** of claims they are:

    * **An identifier against a guess.** The identifier wins and the guess is dropped.
      ``report_number`` is unique on the EGIF side, so a code match is not a claim that
      can be improved on, and a date-and-province rule that lands on the same *parte* is
      simply wrong about which fire it found.
    * **Guesses only.** All of them are dropped. There is nothing in the data that would
      make the choice, and picking anyway is exactly the silent wrong answer this
      application is built to avoid.

    .. note::

       This is where this cascade parts company with its Catalan twin, which drops every
       claim on a contested *parte* on the grounds that stage 1 cannot produce a contest.
       That is true of the Catalan data and **not** of this one: two real fires here —
       ``2014040066`` and ``2018140034`` — are matched by their published code while the
       *previous* fire in the same province and on the same date reaches the same *parte*
       through the date-and-province rule. Dropping the identifier match because a guess
       collided with it would throw away the best evidence in the dataset.

    Enforced here rather than by a unique constraint on ``egif_wildfire_id`` because a
    constraint would make a re-run *fail* on a conflict instead of reporting it, and the
    two datasets are published independently and will disagree again.
    """
    claims: dict[int, list[Binding]] = defaultdict(list)
    for binding in bindings:
        if binding.is_bound:
            claims[binding.egif.id].append(binding)

    dropped = 0
    for contested in claims.values():
        if len(contested) < 2:
            continue
        strongest = max(binding.confidence for binding in contested)
        winners = [binding for binding in contested if binding.confidence == strongest]
        # One identifier claim beats any number of guesses; anything else is a tie
        # between claims of the same kind, and a tie is not resolved.
        keeper = winners[0] if len(winners) == 1 and strongest >= IDENTIFIER_CONFIDENCE \
            else None
        losers = [binding for binding in contested if binding is not keeper]

        if keeper is not None:
            logger.warning(
                "EGIF parte %s is claimed by %d perimeters (%s); kept %s, which matched "
                "on the published identifier, and dropped the rest",
                keeper.egif.report_number, len(contested),
                ", ".join(binding.fire.code for binding in contested), keeper.fire.code)
        else:
            logger.warning(
                "EGIF parte %s is claimed by %d perimeters (%s); none of them is bound",
                contested[0].egif.report_number, len(contested),
                ", ".join(binding.fire.code for binding in contested))

        for binding in losers:
            binding.egif = None
            binding.method = None
            binding.reason = UNBOUND_PARTE_CONTESTED
            binding.candidates = len(contested)
            dropped += 1
    return dropped


def bind(session: Session, bindings: list[Binding], matched_at: datetime.datetime,
         year: int | None, only_unbound: bool) -> int:
    """Clear the columns in scope and write the bindings, returning how many.

    The clear comes first and covers the whole scope, not just the fires being bound: a
    fire that used to match and no longer does has to lose its link, or a correction to
    either dataset could never take effect.
    """
    session.execute(text(CLEAR_SQL), {"year": year, "only_unbound": only_unbound})
    written = [binding for binding in bindings if binding.is_bound]
    for binding in written:
        session.execute(text(BIND_SQL), {
            "rediam_id": binding.fire.id,
            "egif_id": binding.egif.id,
            "method": binding.method,
            "confidence": binding.confidence,
            "matched_at": matched_at,
        })
    return len(written)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Bind the Andalusian REDIAM perimeters to the Spanish EGIF partes.",
        epilog="Import both datasets first. Only rediam_wildfire's four binding columns "
               "are ever written. A perimeter is bound only when exactly one parte "
               "survives the cascade, so an ambiguous fire is left unbound and reported "
               "rather than guessed at. Database settings not given here are read from "
               "the environment (.env).",
    )
    parser.add_argument("-y", "--year", type=int,
                        help="bind only the Andalusian fires of this year; the candidate "
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

    Both, deliberately. A report of the successes says nothing about whether the rules
    are right; the unbound rows and their candidate counts are what shows where the
    cascade is running out of evidence and what a further rule would have to work with.
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

    logger.info("Bound %d of %d Andalusian fire(s)", len(bound), len(bindings))
    for method, count in sorted(methods.items(),
                                key=lambda item: -MATCH_METHOD_CONFIDENCE[item[0]]):
        logger.info("  %-20s %5d  (confidence %.2f)", method, count,
                    MATCH_METHOD_CONFIDENCE[method])
    for reason in UNBOUND_REASONS:
        if reasons[reason]:
            logger.info("  unbound: %-20s %5d", reason, reasons[reason])

    exact = sum(count for method, count in methods.items()
                if MATCH_METHOD_CONFIDENCE[method] >= 0.9)
    if bound and exact < len(bound):
        logger.warning(
            "%d of the %d bindings rest on a date and a municipality name rather than "
            "on the published identifier: filter on match_confidence >= 0.9 for the "
            "ones that do not", len(bound) - exact, len(bound))


def report_coverage(bindings: list[Binding], index: Index,
                    logger: logging.Logger) -> None:
    """Say how many unbound fires are in campaigns EGIF has not exported at all.

    The distinction that matters when reading the unbound count: a fire of 2025 has no
    *parte* to match because the export stops at 2023, which is a fact about the EGIF
    side rather than a failure of any rule here. On the published data that is 133 of
    the 148 unbound fires.
    """
    covered = {fire.campaign for fire in index.fires if fire.campaign is not None}
    if not covered:
        return
    uncovered = [binding for binding in bindings
                 if not binding.is_bound and binding.fire.year not in covered]
    if uncovered:
        years = sorted({binding.fire.year for binding in uncovered})
        logger.info(
            "%d of the unbound fire(s) are in %s, which the EGIF exports do not reach "
            "at all (campaigns %d-%d are imported)", len(uncovered),
            ", ".join(str(year) for year in years), min(covered), max(covered))


def bind_wildfires(args: argparse.Namespace, engine: Engine,
                   logger: logging.Logger) -> list[Binding]:
    """Run the whole binding against ``engine``, returning what it concluded."""
    common.require_tables(engine, ["rediam_wildfire", "egif_wildfire", "wildfire"], logger)
    matched_at = datetime.datetime.now(datetime.timezone.utc)

    with Session(engine) as session:
        with common.Spinner("Reading the Andalusian perimeters and the Spanish partes",
                            logger):
            fires = load_rediam_fires(session, args.year, args.only_unbound)
            index = Index.build(load_egif_fires(session))

        if not fires and args.only_unbound:
            # Not an error: "bind what is not bound yet" has nothing to do, which is the
            # state a second --only-unbound run is supposed to reach.
            logger.info("Every Andalusian fire in scope is already bound; nothing to do")
            return []
        if not fires:
            raise RuntimeError(
                "No Andalusian wildfires in scope. Check --year, and that the REDIAM "
                "perimeters are imported."
            )
        if not index.fires:
            raise RuntimeError(
                "No EGIF partes are filed in an Andalusian province, so there is nothing "
                "to bind to. Import the EGIF fire statistics first."
            )
        logger.info("%d Andalusian perimeter(s) against %d Andalusian parte(s)",
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
    report_coverage(bindings, index, logger)
    logger.info("%s %d binding(s)", "Would have written" if args.dry_run else "Wrote",
                written)
    return bindings


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    logger = logging.getLogger("rediam-egif-bind")

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
