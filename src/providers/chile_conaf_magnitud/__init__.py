#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF *incendios de magnitud* — mapped perimeters of Chile's large fires.

Data model for CONAF's second published product: the burnt-area polygons of the
fires that reached roughly 200 hectares, one shapefile per *temporada* from
2013-2014 on, with Easter Island in its own archive.

**781 published features over the thirteen archives, which dissolve to 743 fires.**

.. important::

   This is **Chile's CONAF**, not Mexico's CONAFOR
   (:mod:`src.providers.mexico_conafor`). See the note in
   :mod:`src.providers.chile_conaf`.

The same fires as :mod:`src.providers.chile_conaf`
----------------------------------------------------

Unlike NBAC and NFDB, which are two agencies' independent accounts of Canadian
fire, these two archives are **one agency's one incident record published twice**.
Every one of the 743 fires here is also a report in
:mod:`src.providers.chile_conaf`, and the link is filled in by
:mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires`.

They are still two :class:`~src.data_model.data_provider.DataProvider` rows
sharing a :data:`~src.providers.chile_conaf.PROVIDER_NAME`, because they are two
published products with different attributes, different geometry and independent
release cadences, and because a row has to be checkable against the file it came
from.

.. warning::

   A query over ``wildfire`` filtered only by provider *name* therefore counts 743
   Chilean fires twice. Filter by ``data_provider_id``, or by the polymorphic
   ``type``.

The threshold is 200 hectares, and the archive is not exhaustive
-----------------------------------------------------------------

The published minimum area sits at 200–215 ha in every season from 2015-2016 on
(200.51, 200.00, 226.51, 209.45, 202.89, 203.18, 201.63, 215.34, 204.68), which is
what fixes the threshold; three earlier archives carry a handful of smaller
polygons and 2018-2019 carries pieces down to 0.05 ha that are parts of larger
fires rather than fires.

It does **not** contain every fire over the threshold. 2021-2022 has 97 reports of
200 ha or more in :mod:`src.providers.chile_conaf` and 62 perimeters here;
2019-2020 has 86 and 62; 2024-2025 has 81 and 55. A perimeter is evidence a fire
was mapped, and its absence is not evidence a fire was small.

A fire is several features
---------------------------

There is no ``GID``. A fire that was mapped in pieces is published as several
features sharing ``TEMPORADA`` and ``NOM_INCEN``, and the pieces are unmistakable:
same season, same date, same comuna, tens to a few thousand metres apart.
``668 - CANIHUAL VII`` of 2018-2019 is **thirteen** features of one fire.

So the import dissolves on :data:`DISSOLVE_KEY` — the season and the normalised
name — taking 781 features to 743 fires, and records
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.part_count`.

The area comes from the dissolved geometry, not from the column
-----------------------------------------------------------------

``SUPERFICIE`` is the *feature's own polygon area* in hectares, not the burnt area
the office reported: the ratio of computed area to declared area has median 1.000
in every one of the thirteen archives. That makes it a derived attribute, and it
makes summing it over the parts wrong wherever the parts overlap — ``37_TIL TIL``
of 2016-2017 is six features each declaring 327.50 ha of what is one 327.8 ha
fire, and ``QUEBRADILLA`` of 2015-2016 is the same polygon published twice.

:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.area_ha_mapped`
is therefore computed from the union, and
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.area_ha_published`
keeps the sum of the parts' ``SUPERFICIE`` beside it so the disagreement stays
visible. Only 19 of the 743 fires are published in more than one feature, so for
724 of them the two are the same number.

Neither is the fire's reported burnt area. That is
:attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_ha_total`, on the
report this perimeter binds to, and it is a different measurement — it counts
affected vegetation by type and is filed by the office, not traced from imagery.

.. warning::

   77 of the 781 published polygons are **invalid** — 31 in 2016-2017 and 27 in
   2021-2022 alone — and one 2014-2015 polygon covers 14,560 ha while declaring
   2,402. The import repairs with ``ST_MakeValid`` before it measures anything,
   which is why :attr:`area_ha_mapped` and ``SUPERFICIE`` can disagree by a factor
   of six on that one fire. The repaired geometry is the one stored.

   273 features are already ``MULTIPOLYGON`` as published, and 2021-2022 and
   2022-2023 publish 3D polygons. Both are flattened at import.

Dates are thinner here than on the reports
-------------------------------------------

Three archives — 2015-2016, 2017-2018 and 2019-2020, 116 features — publish no
``FECHA_INI`` at all, and 313 features publish no end date. The same
:data:`~src.providers.chile_conaf.PRECISION_SEASON` fallback applies: a fire with
no published start is dated to the first instant of its season.

The published dates use the same four formats
:func:`~src.providers.chile_conaf.parse_published_datetime` reads, and 2022-2023
and 2023-2024 switched to the ``18-ene-2023 15:50`` shape with hours, which the
report archive had been using since 2017-2018.

``CAUSA`` here is not the reports' cause vocabulary
-----------------------------------------------------

One column where the reports have two, and it is used inconsistently: sometimes a
specific cause with its code (``'2.1.11. Otros intencionales no clasificados'``),
sometimes a general one in prose (``'Incendio Intencional'``), sometimes the null
token ``'0'``. 180 distinct strings over 781 features.

It is stored as published on
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.cause_published`
and resolved against :class:`~src.providers.chile_conaf.fire_cause.ConafFireCause`
where the string matches one the reports use. Where it does not,
:attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.cause_id`
stays ``NULL`` and the bound report's cause is the one to use.

Binding: the number is in the name
------------------------------------

Six of the thirteen archives write the report's ``NUMERO_REG`` into ``NOM_INCEN``
as a prefix — ``'402 - SAN GUILLERMO'``, ``'944-LA AGUADA'``, ``'320_LAS
MAQUINAS'`` — and two publish it as a column. Matching on it against
:mod:`src.providers.chile_conaf` finds the report for 137 of 144 fires in
2016-2017, 66 of 67 in 2018-2019, and every one of 2019-2020, 2020-2021,
2021-2022 and 2023-2024. Where there is no number, the name alone matches every
fire of 2015-2016, 2017-2018, 2022-2023 and 2024-2025.

:data:`MATCH_METHODS` is that ladder, and :func:`published_number` is what reads
the prefix.
"""

from __future__ import annotations

import re

from src.providers.chile_conaf import PROVIDER_FULL_NAME  # noqa: F401  (re-exported)
from src.providers.chile_conaf import PROVIDER_NAME  # noqa: F401  (re-exported)

#: The published product. Shares
#: :data:`~src.providers.chile_conaf.PROVIDER_NAME` with the report archive: one
#: agency, two products, two
#: :class:`~src.data_model.data_provider.DataProvider` rows.
PROVIDER_PRODUCT = "Incendios forestales de magnitud"

#: Where the archive is published.
PROVIDER_URL = "https://www.conaf.cl/incendios-forestales/incendios-forestales-en-chile/"

#: First season a perimeter archive exists for. The report archive starts three
#: seasons earlier, in :data:`~src.providers.chile_conaf.FIRST_SEASON`.
FIRST_SEASON = 2013

#: Area, in hectares, at which CONAF calls a fire an *incendio de magnitud* and
#: maps it.
#:
#: Not a filter the import applies — every published feature is imported, the
#: handful below the threshold included. It is here because it is the answer to
#: "why are there only 743 of these", and because a statistic comparing this
#: archive with :mod:`src.providers.chile_conaf` has to know what the archive is a
#: sample *of*. See the module docstring on exhaustiveness.
MAGNITUD_THRESHOLD_HA = 200.0

#: What the import dissolves published features on: the season, the
#: :func:`~src.providers.chile_conaf.normalise` d ``NOM_INCEN`` with any number
#: prefix removed, and the number itself.
#:
#: Not a published key — there is no ``GID`` here — but a sound one for this archive:
#: the features that share a key all share a date and a comuna too, and none of the
#: 743 resulting groups mixes two dates.
#:
#: **The number is in the key and has to be.** Four groups in the archive share a
#: name within a season and are different fires: *120_LOS MAITENES* and *388_LOS
#: MAITENES* of 2016-2017 are eighteen days apart, and *558 - SAN RAMON* and *1037 -
#: SAN RAMON* of 2024-2025 are seven weeks apart. Dissolving on the name alone gives
#: 739 fires instead of 743 and merges those four pairs into one polygon each.
#:
#: Where no number is published, the name alone is the key, and features with no
#: number group together — which is right for the eleven archives that publish none,
#: because in those the name is all there is.
#:
#: The import reports every group of more than one, so that a future archive naming
#: two real unnumbered fires the same in one season is visible rather than silent.
DISSOLVE_KEY = ("season_start_year", "name_normalised", "number")

#: The región, the running number **and** the name all agree.
#:
#: The strongest rule there is, and the one that does most of the work of separating
#: reports that the número alone cannot. ``NUMERO_REG`` is not unique inside a región
#: — 2016-2017 has 93 perimeters whose ``(CODREG, NUMERO_REG)`` matches two reports —
#: and in 83 of those 93 exactly one of the two also carries the perimeter's name.
MATCH_NUMBER_REGION_NAME_SEASON = "number_region_name_season"

#: The región and the running number agree, and the report's point falls **inside**
#: the perimeter.
#:
#: The other tie-break for a repeated número, and independent of the first: it uses
#: the geometry rather than the text, so it settles the fires whose two candidates
#: are named alike or unnamed.
MATCH_NUMBER_REGION_INSIDE_SEASON = "number_region_inside_season"

#: The perimeter was matched to a report of the same season whose ``CODREG`` and
#: ``NUMERO_REG`` both agree — the number coming either from the published column
#: or from the ``'402 - '`` prefix on ``NOM_INCEN`` — and nothing further was needed
#: to separate it from another report with the same pair.
#:
#: This is the rule 2023-2024's 49 perimeters match on exactly.
MATCH_NUMBER_REGION_SEASON = "number_region_season"

#: The number agrees and the normalised names agree, but the región does not — or
#: is unpublished, as it is on every feature of three archives.
MATCH_NUMBER_NAME_SEASON = "number_name_season"

#: The normalised names agree and the perimeter contains that report's point.
#: Two independent signals, neither of which is the number.
MATCH_NAME_SEASON_INSIDE = "name_season_inside"

#: The normalised names agree and the name is unique among the season's reports.
#: The only rule available for the four archives that publish no number at all.
MATCH_NAME_SEASON = "name_season"

#: The perimeter contains exactly one of the season's reports, and nothing else
#: agrees. Roughly half of all perimeters satisfy this on its own.
MATCH_INSIDE_SINGLE = "inside_single"

#: Exactly one of the season's reports lies within
#: :data:`DEFAULT_MATCH_DISTANCE_M` of the perimeter, and none lies inside it.
#: The tolerance rule, for a report whose point was filed just outside the mapped
#: burn.
MATCH_NEAR_SINGLE = "near_single"

#: Every method
#: :attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.match_method`
#: takes, strongest first. Constrained on the column by a migration of its own —
#: see :mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires`.
MATCH_METHODS = (
    MATCH_NUMBER_REGION_NAME_SEASON,
    MATCH_NUMBER_REGION_INSIDE_SEASON,
    MATCH_NUMBER_REGION_SEASON,
    MATCH_NUMBER_NAME_SEASON,
    MATCH_NAME_SEASON_INSIDE,
    MATCH_NAME_SEASON,
    MATCH_INSIDE_SINGLE,
    MATCH_NEAR_SINGLE,
)

#: How much of a claim each method is, as a number between 0 and 1, stored on
#: :attr:`~src.providers.chile_conaf_magnitud.wildfire.ConafMagnitudWildfire.match_confidence`.
#:
#: These are ordinal and are not probabilities. They exist so that a query can say
#: "only bindings I would defend" without having to know the ladder, and so that a
#: later method inserted in the middle does not renumber the ones around it.
MATCH_METHOD_CONFIDENCE = {
    MATCH_NUMBER_REGION_NAME_SEASON: 0.98,
    MATCH_NUMBER_REGION_INSIDE_SEASON: 0.96,
    MATCH_NUMBER_REGION_SEASON: 0.95,
    MATCH_NUMBER_NAME_SEASON: 0.93,
    MATCH_NAME_SEASON_INSIDE: 0.90,
    MATCH_NAME_SEASON: 0.80,
    MATCH_INSIDE_SINGLE: 0.70,
    MATCH_NEAR_SINGLE: 0.60,
}

#: How far outside a perimeter a report's point may lie and still be matched by
#: :data:`MATCH_NEAR_SINGLE`, in metres on the published grid.
#:
#: Two kilometres, the same tolerance
#: :data:`src.providers.canada_nbac.DEFAULT_MATCH_DISTANCE_M` uses, and for the
#: same reason: a report's point is where the fire was *reported*, which for a
#: 200-hectare fire can be the road it was seen from. The binder's
#: ``--max-distance`` overrides it and ``0`` disables the stage.
DEFAULT_MATCH_DISTANCE_M = 2000.0

#: The ``'402 - SAN GUILLERMO'`` prefix: a running number, a separator, a name.
#:
#: The separator is written ``' - '``, ``'-'``, ``'_'`` and ``' '`` in different
#: seasons. The number is bounded to five digits so that a fire genuinely named
#: after a year — and there are none, but there could be — is not read as a
#: number with the year stripped off.
_NUMBER_PREFIX = re.compile(r"^\s*(\d{1,5})\s*[-_ ]\s*(\S.*)$")


def published_number(
        name: str | None,
        number: object = None,
) -> tuple[int | None, str | None]:
    """Split a published ``NOM_INCEN`` into the report number and the name.

    Parameters
    ----------
    name : str or None
        The published ``NOM_INCEN``, which in six of the thirteen archives is
        ``'402 - SAN GUILLERMO'`` and in the rest is ``'CERRO VIEJO'``.
    number : object, optional
        The published ``NUMERO_REG``, where the archive has that column — 2022-2023
        and 2023-2024 do. It wins over the prefix when both are present.

    Returns
    -------
    tuple
        ``(number, name)``. *number* is ``None`` when neither the column nor a
        prefix gives one; *name* is the remainder, stripped, or ``None`` for a
        blank.

    Notes
    -----
    The name that comes back is the name **without** the prefix, and that is what
    gets stored and what the binder compares. The prefix is not part of what the
    fire is called: ``'402 - SAN GUILLERMO'`` here and ``'SAN GUILLERMO'`` in the
    report archive are one fire, and keeping the prefix would defeat every
    name-based match in the six archives that use it.

    A name that is only a number — no separator, no remainder — is left alone and
    returns ``(None, name)``. There are none in the archive as published; reading
    one as a number with an empty name would lose the only label the fire has.
    """
    text = None if name is None else str(name).strip()
    if not text:
        text = None

    parsed_number: int | None = None
    if number is not None:
        raw = str(number).strip()
        match = re.match(r"^(\d+)(?:\.0+)?$", raw)
        if match is not None and int(match.group(1)) != 0:
            parsed_number = int(match.group(1))

    if text is not None:
        prefix = _NUMBER_PREFIX.match(text)
        if prefix is not None:
            if parsed_number is None:
                parsed_number = int(prefix.group(1))
            text = prefix.group(2).strip() or None

    return (parsed_number, text)
