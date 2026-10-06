#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WOD — the New Zealand Wildfire Occurrence Database.

Data model for the national record of New Zealand wildfires compiled by the
Bioeconomy Science Institute (formerly Scion) from the incident records of Fire and
Emergency New Zealand (FENZ) and the Department of Conservation (DOC), and described
in Kiely et al., *A spatial database of wildfire occurrence and associated fire
environment conditions in New Zealand*, Scientific Data (2026),
doi:10.1038/s41597-026-07859-z.

The release this package was written against is figshare version 3
(doi:10.6084/m9.figshare.30854057.v3, published 2026-09-18, **CC BY 4.0**): two
shapefiles in NZTM2000, ``WOD_points`` and ``WOD_polygons``, holding **128,020
records over 1931-2025** between them — 125,931 points and 2,089 perimeters, no
record in both.

One record, four rows
---------------------

Every published record becomes:

* a :class:`~src.providers.new_zealand_wod.wildfire.WodWildfire` — what the agency
  reported: when, how large, the cause, and the perimeter where there is one;
* a :class:`~src.providers.new_zealand_wod.ignition.WodIgnition` — the published
  ``X``/``Y``, **always**, untouched;
* a :class:`~src.providers.new_zealand_wod.terrain.WodTerrain` — the topography and
  fuel the compilers attached;
* a :class:`~src.providers.new_zealand_wod.weather.WodWeather` — the weather, fire
  danger and climate they attached.

The last two are not observations of the fire. They are the dataset's own
*enrichment*, derived from national rasters and the nearest suitable weather
station, and they live on tables of their own so that the boundary between what an
agency recorded and what a compiler computed stays visible. They are kept whole:
nothing of the hundred-odd published columns is dropped except what is exactly
derivable from another (``Lat``/``Lon``, ``Hour``/``Minute``, ``EndFY``/``FY``).

Coverage is not uniform
-----------------------

* **1931-1997**: DOC only, and sparse. The paper itself says that before 1998 the
  WOD "does not provide good overall coverage of wildfire occurrence, rather
  information on specific wildfires". :data:`FIRST_YEAR` is the import's default cut
  for that reason.
* **1998-2011**: FENZ and DOC. Where both recorded the same fire (same day, within
  600 m) the DOC record was kept and the FENZ one dropped — 862 of them, whose CAD
  numbers survive in ``OrgIDDrop``.
* **2012 onwards**: FENZ only.

FENZ records only *vegetation* fires: no planned burns, no false alarms needing no
action. Most of them are tiny — the median FENZ ``AreaHa`` is 0.0005 ha.

The dirt, and what is done with it
-----------------------------------

**-9999 means nothing**, in every column, numeric or text; ``NA:NA`` means no time;
``Null`` (five DOC rows) means no cause. All are read as ``NULL``. See
:data:`NO_DATA`, :data:`NO_TIME` and :func:`published_ignition_source`.

**One identifier was written in scientific notation**: ``WOD1e+05`` is
``WOD100000``, the only number missing from the sequence. See :func:`wod_id`.

**Points in the sea are kept.** 92 records have no FENZ district because their point
is off the coast, and 15 FENZ points sit on the same placeholder coordinate,
:data:`PLACEHOLDER_X`/:data:`PLACEHOLDER_Y`, off North Cape. They are reports of real
fires whose location was recorded wrongly, and they are stored as published.

**One area is negative** (−0.0001 ha), a recording error carried from the source. The
import clamps it to 0.

**A polygon's** ``X``/``Y`` **is neither its centroid nor its origin.** It is the
location the original record carried; only 21% fall inside their own polygon. It is
stored untouched, as every other point is.

Times
-----

``Time`` is when the fire was **reported**, not when it ignited — the paper takes it
as the best available proxy. It is New Zealand local time: the compilers' code
localises it with ``pytz.timezone("NZ")``. The import reads it in
:data:`DEFAULT_TIME_ZONE`, or :data:`CHATHAM_TIME_ZONE` for the Chatham Islands.

Every DOC record lacks a time. Those fires are dated to **local midnight**, the
project's convention for a bare date, with
:attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.time` left ``NULL`` to say
so. Note that the compilers assumed **12:00** for them when they attached weather,
so for those rows the "at detection" weather values refer to noon.

Causes
------

``IgnSource`` comes in two vocabularies — FENZ's and DOC's — and 128 spellings. It is
stored as published and classified by :data:`CAUSE_MAP` into one of
:data:`FIRE_CAUSES`: lightning, natural (geothermal or volcanic, anything natural that
is not lightning), human, or unknown. A spelling the map does not know is an error,
not an *unknown*: see :func:`fire_cause`.
"""

from __future__ import annotations

import re

#: Short name of the provider: the institute that compiled and publishes the WOD.
#: Scion merged into it in 2025; the paper's corresponding address is still Scion's.
PROVIDER_NAME = "Bioeconomy Science Institute"

#: The provider in full, with the two agencies whose records the WOD is made of.
PROVIDER_FULL_NAME = ("Bioeconomy Science Institute (formerly Scion), Fire and Emergency "
                      "New Zealand and Department of Conservation")

#: The published product.
PROVIDER_PRODUCT = "Wildfire Occurrence Database (WOD)"

#: Where the dataset is published: its figshare DOI.
PROVIDER_URL = "https://doi.org/10.6084/m9.figshare.30854057"

#: What goes in ``data_provider.description``: the paper and the licence, which has
#: no column of its own.
PROVIDER_DESCRIPTION = (
    "Kiely, L. et al. A spatial database of wildfire occurrence and associated fire "
    "environment conditions in New Zealand. Sci Data (2026), "
    "doi:10.1038/s41597-026-07859-z. Dataset licensed CC BY 4.0."
)

#: The CRS both shapefiles are published in: NZGD2000 / New Zealand Transverse
#: Mercator 2000. Kept unchanged on
#: :attr:`~src.providers.new_zealand_wod.wildfire.WodWildfire.perimeter_nztm` and
#: :attr:`~src.providers.new_zealand_wod.ignition.WodIgnition.geometry_nztm`.
SOURCE_SRID = 2193

#: Zone the published local times are read in.
DEFAULT_TIME_ZONE = "Pacific/Auckland"

#: Zone for the Chatham Islands, 45 minutes ahead of the mainland. The compilers
#: used New Zealand time everywhere; the import does not, for these 18 records.
CHATHAM_TIME_ZONE = "Pacific/Chatham"

#: The published ``FENZDist`` of the Chatham Islands.
CHATHAM_DISTRICT = "Chatham Islands"

#: First year the import reads by default: when the FENZ records start, and before
#: which the paper says coverage is poor.
FIRST_YEAR = 1998

#: First year the archive publishes. ``--all-years`` imports from here.
PUBLISHED_FIRST_YEAR = 1931

#: The published *no value*, in every column.
NO_DATA = -9999

#: Spellings of :data:`NO_DATA` in the text columns. The ``.0`` one is what a
#: numeric value written as text looks like (``FDC`` is declared as text).
NO_DATA_TEXTS = frozenset({"-9999", "-9999.0"})

#: The published ``Time`` of a record without one: every DOC record.
NO_TIME = "NA:NA"

#: Placeholder coordinate 15 FENZ points carry, in the sea off North Cape. Kept as
#: published; named so that the import can count them.
PLACEHOLDER_X = 2147484.0

#: See :data:`PLACEHOLDER_X`.
PLACEHOLDER_Y = 6147484.0

#: ``Source`` for Fire and Emergency New Zealand.
SOURCE_FENZ = "FENZ"

#: ``Source`` for the Department of Conservation.
SOURCE_DOC = "DOC"

#: Every value ``Source`` takes. Constrained on the column.
SOURCES = (SOURCE_FENZ, SOURCE_DOC)

#: Every value ``Season`` takes: December-February is summer.
SEASONS = ("Summer", "Autumn", "Winter", "Spring")

#: Every value ``AreaCat`` takes, smallest first.
AREA_CATEGORIES = ("< 1", "1 to 5", "5 to 10", "10 to 50", "50 to 100", "> 100")

#: Every value ``ENSO`` takes.
ENSO_PHASES = ("El Nino", "La Nina", "Neutral")

#: The range of a fire danger class (``FDC*``), 1 (low) to 5 (extreme).
FIRE_DANGER_CLASS_RANGE = (1, 5)

#: Struck by lightning. 538 records: 467 FENZ ``Lightning discharge`` and 71 DOC
#: ``Lightning`` or ``Lightening Strike``.
CAUSE_LIGHTNING = "lightning"

#: Natural, and not lightning: geothermal or volcanic. Five records, all
#: ``Geothermal Activity``.
CAUSE_NATURAL = "natural"

#: Started by people, deliberately or not.
CAUSE_HUMAN = "human"

#: Not recorded, not determined, or not classifiable from what was published.
CAUSE_UNKNOWN = "unknown"

#: Every class :func:`fire_cause` returns. Constrained on the column.
FIRE_CAUSES = (CAUSE_LIGHTNING, CAUSE_NATURAL, CAUSE_HUMAN, CAUSE_UNKNOWN)

#: Published ``IgnSource`` values with no information in them: read as ``NULL``.
IGNITION_SOURCE_NO_DATA = frozenset({"-9999", "null"})

#: Every published ``IgnSource`` value, as spelt in the 2025 release, and its class.
#:
#: Matched through :func:`normalise_cause`, so the two spellings that differ only in
#: case (``Burn Breakaway - authorised``/``Authorised``) or trailing space
#: (``Electrical Fence``) are one entry. Some calls that could go either way:
#:
#: * ``Spontaneous ignition, chemical reaction`` and ``Solar heat`` are *human*:
#:   stored material, and glass, are objects somebody put there.
#: * ``Trees``, ``Animals``, ``Birds nest`` and ``Static electrical discharge`` are
#:   *unknown*: in an incident system they usually mean contact with power lines or
#:   equipment, but the record does not say so.
#: * ``Exposure Fire - unable to classify`` and ``Re-ignition`` are *unknown*: the
#:   fire came from another fire whose cause is not given. The specific exposure
#:   kinds (radiated heat, embers…) are *human*, being spread from a structure or
#:   vehicle fire.
#: * ``False alarm`` and ``Smoke report only`` are *unknown* — the DOC record says the
#:   record is doubtful, not what started it.
CAUSE_MAP: dict[str, str] = {
    # Lightning.
    "Lightning discharge": CAUSE_LIGHTNING,
    "Lightning": CAUSE_LIGHTNING,
    "Lightening Strike": CAUSE_LIGHTNING,
    # Natural, not lightning.
    "Geothermal Activity": CAUSE_NATURAL,
    # Unknown.
    "Information not recorded/Unknown": CAUSE_UNKNOWN,
    "Unknown": CAUSE_UNKNOWN,
    "Unable to classify": CAUSE_UNKNOWN,
    "Exposure Fire - unable to classify": CAUSE_UNKNOWN,
    "Re-ignition, Rekindle from previous fire": CAUSE_UNKNOWN,
    "Other": CAUSE_UNKNOWN,
    "False alarm": CAUSE_UNKNOWN,
    "Smoke report only": CAUSE_UNKNOWN,
    "Trees": CAUSE_UNKNOWN,
    "Animals": CAUSE_UNKNOWN,
    "Birds nest": CAUSE_UNKNOWN,
    "Static electrical discharge": CAUSE_UNKNOWN,
    # Human: burning.
    "Agricultural fire or burn off": CAUSE_HUMAN,
    "Broadcast slash burn": CAUSE_HUMAN,
    "Burn Breakaway - Authorisation not recorded": CAUSE_HUMAN,
    "Burn Breakaway - Authorised": CAUSE_HUMAN,
    "Burn Breakaway - Unauthorised": CAUSE_HUMAN,
    "Controlled Burn": CAUSE_HUMAN,
    "Crop burn": CAUSE_HUMAN,
    "Debris burning": CAUSE_HUMAN,
    "Refuse burning": CAUSE_HUMAN,
    "Scrub and tussock burn": CAUSE_HUMAN,
    "Windrow / slash pile": CAUSE_HUMAN,
    "Outside bonfire": CAUSE_HUMAN,
    "Outside fire - unable to classify": CAUSE_HUMAN,
    "Outside fire for cooking": CAUSE_HUMAN,
    "Outside fire for warmth / Campfire": CAUSE_HUMAN,
    "Campfire": CAUSE_HUMAN,
    "Picnickers/ Campfires": CAUSE_HUMAN,
    "Hunters": CAUSE_HUMAN,
    "BBQ": CAUSE_HUMAN,
    "Umu / Hangi": CAUSE_HUMAN,
    "Wood-fired pizza ovens": CAUSE_HUMAN,
    "Embers, Ashes": CAUSE_HUMAN,
    "Frost pots": CAUSE_HUMAN,
    # Human: arson, smoking, matches, fireworks, explosives.
    "Arson/ Incendiarism": CAUSE_HUMAN,
    "Arson/Incendiarism": CAUSE_HUMAN,
    "Incendiary devices, Molotov cocktail": CAUSE_HUMAN,
    "Torched Car": CAUSE_HUMAN,
    "Matchers or Lighters(Suspicious)": CAUSE_HUMAN,
    "Matches": CAUSE_HUMAN,
    "Lighters": CAUSE_HUMAN,
    "Lighter/Match/Candle - POSSIBLE combination of": CAUSE_HUMAN,
    "Candle": CAUSE_HUMAN,
    "Lantern": CAUSE_HUMAN,
    "Sky / Chinese lanterns": CAUSE_HUMAN,
    "Cigarette, Cigar or Smoking materials": CAUSE_HUMAN,
    "Cigarettes, matches and candles - Other": CAUSE_HUMAN,
    "Heat from smoking material": CAUSE_HUMAN,
    "Pipe,": CAUSE_HUMAN,
    "Smoking/ Matches": CAUSE_HUMAN,
    "Smoking/Matches": CAUSE_HUMAN,
    "Fireworks": CAUSE_HUMAN,
    "Fireworks / Pyrotechnics": CAUSE_HUMAN,
    "Flare: Warning, Safety, Boat": CAUSE_HUMAN,
    "Explosives, Fire works - not classified above": CAUSE_HUMAN,
    "Explosives, fuses, and associated equipment": CAUSE_HUMAN,
    "Bomb, Military rocket, Ammunition": CAUSE_HUMAN,
    "Tracer ammunition": CAUSE_HUMAN,
    "Rockets: Commercial, model or amateur": CAUSE_HUMAN,
    # Human: electrical.
    "Arc from fault, Loose or broken conductor": CAUSE_HUMAN,
    "Arc from switch, electric fence or operating equip": CAUSE_HUMAN,
    "Arcing or overloaded electrical equipment - Other": CAUSE_HUMAN,
    "Clashing / Arching power lines": CAUSE_HUMAN,
    "Powerlines": CAUSE_HUMAN,
    "Powerlines/Electrical Fault": CAUSE_HUMAN,
    "Electrical Fence": CAUSE_HUMAN,
    "Electric lamp": CAUSE_HUMAN,
    "Fluorescent light ballast": CAUSE_HUMAN,
    "Heat from electrical equip: Defective or faulty": CAUSE_HUMAN,
    "Heat from electrical equipment: Incorrectly used": CAUSE_HUMAN,
    "Heat from electrical equipment: Properly operating": CAUSE_HUMAN,
    "Heat from overloaded equipment": CAUSE_HUMAN,
    "Short circuit arc: Defective or worn insulation": CAUSE_HUMAN,
    "Short circuit arc: Mechanical damage": CAUSE_HUMAN,
    "Short circuit arc: Unspecified": CAUSE_HUMAN,
    "Short circuit arc: Water cause": CAUSE_HUMAN,
    # Human: machinery, vehicles and equipment.
    "Chainsaws": CAUSE_HUMAN,
    "Earthwork or forestry machinery": CAUSE_HUMAN,
    "Farm machinery": CAUSE_HUMAN,
    "Mowers and slashers": CAUSE_HUMAN,
    "Tractors/ Other Machinery": CAUSE_HUMAN,
    "Tractors/Other Machinery": CAUSE_HUMAN,
    "Maintenance crews": CAUSE_HUMAN,
    "Malfunction": CAUSE_HUMAN,
    "Motor Vehicles": CAUSE_HUMAN,
    "Motorbike, Truck or Car": CAUSE_HUMAN,
    "Railways": CAUSE_HUMAN,
    "Exhaust heat / Spark": CAUSE_HUMAN,
    "Friction heat, Overheated tyres": CAUSE_HUMAN,
    "Molten material: Hot glass, Brake shoes, Slag": CAUSE_HUMAN,
    "Welding, grinding, cutting": CAUSE_HUMAN,
    "Gas or liquid cutting torch: Spark, Ember, Flame": CAUSE_HUMAN,
    "Gas or liquid welding torch: Spark, Ember, Flame": CAUSE_HUMAN,
    "Gas or liquid fuel powered equipment - Other": CAUSE_HUMAN,
    "Other gas or liquid powered sources: Furnace, Torch": CAUSE_HUMAN,
    "Flame escaping from liquid fueled equip, Backfire": CAUSE_HUMAN,
    "Flame from gas equipment other than a torch": CAUSE_HUMAN,
    "Heat from gas fueled equipment": CAUSE_HUMAN,
    "Heat from liquid fuelled equipment": CAUSE_HUMAN,
    "Coal fuelled equipment: Spark, Ember, Flame": CAUSE_HUMAN,
    "Heat from coal or coke fuelled equipment": CAUSE_HUMAN,
    "Heat from other solid fuelled equipment": CAUSE_HUMAN,
    "Heat from paper-fuelled equipment": CAUSE_HUMAN,
    "Solid fuelled powered equipment - Other": CAUSE_HUMAN,
    "Wood/paper fuelled equipment: Spark, Ember, Flame": CAUSE_HUMAN,
    "Bee-Keeping smoking tool": CAUSE_HUMAN,
    "Oil and gas exploration": CAUSE_HUMAN,
    "Ropes / binding": CAUSE_HUMAN,
    "Hot object - not classified above": CAUSE_HUMAN,
    # Human: spontaneous ignition of stored material, and the sun through glass.
    "Bark or sawdust spontaneous ignition": CAUSE_HUMAN,
    "Hay/silage spontaneous ignition": CAUSE_HUMAN,
    "Skid site spontaneous ignition": CAUSE_HUMAN,
    "Spontaneous ignition, chemical reaction": CAUSE_HUMAN,
    "Spontaneous ignition; organic- hay, linseed oil etc": CAUSE_HUMAN,
    "Solar heat: Sun (magnified through glass etc)": CAUSE_HUMAN,
    # Human: spread from another fire of known kind.
    "Exposure fire: Conducted heat": CAUSE_HUMAN,
    "Exposure fire: Direct burning (convection currents)": CAUSE_HUMAN,
    "Exposure fire: Ember, Spark, Flying brand": CAUSE_HUMAN,
    "Exposure fire: Radiated heat": CAUSE_HUMAN,
    "Structure": CAUSE_HUMAN,
}

#: Published ``ID`` written in scientific notation: ``WOD1e+05``.
_SCIENTIFIC_WOD_ID = re.compile(r"WOD(\d+(?:\.\d+)?[eE][+-]?\d+)")

#: A well-formed ``ID``.
_WOD_ID = re.compile(r"WOD\d+")


class UnmappedCauseError(ValueError):
    """An ``IgnSource`` value that :data:`CAUSE_MAP` does not classify."""


def normalise_cause(value: str) -> str:
    """The key a published ``IgnSource`` is looked up by in :data:`CAUSE_MAP`.

    Case-folded, with runs of whitespace collapsed and the ends stripped: the
    published spellings differ in exactly those ways (``Burn Breakaway -
    authorised``/``Authorised``, a trailing space on ``Electrical Fence``) and in no
    other. Spellings that differ in anything else — ``Arson/ Incendiarism`` and
    ``Arson/Incendiarism`` — are listed separately rather than guessed together.
    """
    return " ".join(value.split()).casefold()


#: :data:`CAUSE_MAP` keyed by :func:`normalise_cause`.
NORMALISED_CAUSE_MAP: dict[str, str] = {normalise_cause(key): value
                                        for key, value in CAUSE_MAP.items()}


def published_ignition_source(value: str | None) -> str | None:
    """A published ``IgnSource`` as stored: stripped, or ``None`` for no value.

    ``-9999`` (8 DOC rows) and ``Null`` (5) carry no information and are read as
    ``None``; everything else is kept as published, trailing spaces excepted.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.casefold() in IGNITION_SOURCE_NO_DATA:
        return None
    return stripped


def fire_cause(value: str | None) -> str:
    """Classify a published ``IgnSource`` into one of :data:`FIRE_CAUSES`.

    Parameters
    ----------
    value : str or None
        The published cell, as read.

    Returns
    -------
    str
        The class. :data:`CAUSE_UNKNOWN` where nothing was published (see
        :func:`published_ignition_source`).

    Raises
    ------
    UnmappedCauseError
        For a value :data:`CAUSE_MAP` does not list. Deliberately an error rather
        than *unknown*: a new release that adds a cause must have it classified by a
        person, because quietly counting a new lightning category as unknown is
        exactly the mistake this class exists to prevent.
    """
    published = published_ignition_source(value)
    if published is None:
        return CAUSE_UNKNOWN
    try:
        return NORMALISED_CAUSE_MAP[normalise_cause(published)]
    except KeyError:
        raise UnmappedCauseError(f"unmapped WOD ignition source: {published!r}") from None


def wod_id(value: str) -> str:
    """The WOD identifier a published ``ID`` stands for.

    The published sequence runs ``WOD1``…``WOD128036`` and is stable across releases.
    One value was written by the export in scientific notation — ``WOD1e+05``, which
    is ``WOD100000``, the only number otherwise missing. This repairs that, and any
    other like it.

    Raises
    ------
    ValueError
        For anything that is not a WOD identifier, or a scientific value that is not
        a whole number.
    """
    stripped = value.strip()
    if _WOD_ID.fullmatch(stripped):
        return stripped
    match = _SCIENTIFIC_WOD_ID.fullmatch(stripped)
    if match:
        number = float(match.group(1))
        if number.is_integer() and number > 0:
            return f"WOD{int(number)}"
    raise ValueError(f"not a WOD identifier: {value!r}")
