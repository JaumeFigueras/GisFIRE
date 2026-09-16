#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSIRO — Australian historical bushfire extents.

Data model for the Australian national burnt-area cartography, distributed through
the Digital Atlas of Australia as a single ESRI file geodatabase holding two
feature classes.

**347,834 published polygons over 1898-2025**, stored one row per polygon —
GisFIRE's first Oceanian source and, per feature, its heaviest: one polygon carries
2,125,741 vertices and another 52,426 separate parts.

Two feature classes, one dataset
---------------------------------

``National_Historical_Bushfire_Extents_v4``
    345,345 features covering Western Australia, Victoria, New South Wales,
    Queensland, Tasmania, South Australia and the Australian Capital Territory —
    **and not the Northern Territory**, which has no row in it at all.
``NT_Historical_Bushfire_Extents_v1``
    2,489 features, almost all Northern Territory, published at its own version
    number and covering 2020-2025 only.

They are complements, not duplicates: no ``(fire_id, ignition_date)`` pair appears
in both. One :class:`~src.data_model.data_provider.DataProvider` row therefore
covers both, and :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
source_layer` records which class a row came from — the same reasoning as
``source_sheet`` on :mod:`src.providers.greece_ffa`: provenance within one
publication, not a second product.

.. warning::

   The layers do **not** share a vocabulary. ``state`` is ``WA (Western
   Australia)`` in the national class and ``WA``, ``NT``, ``Qld`` in the Northern
   Territory one; ``capture_date`` is ``YYYYMMDD`` text in the first and a real
   date column in the second. Every published value is kept verbatim in a
   ``*_published`` column and normalised beside it, so neither layer's spelling is
   lost and neither has to be remembered by a query.

Half of it is deliberate burning
---------------------------------

166,048 features (48.1%) are prescribed burns, 85,336 (24.7%) are bushfires and
93,960 (27.2%) are ``Unknown``. By area: 84.8 million hectares prescribed against
175.8 million bushfire. Victoria is 88% prescribed burning, New South Wales 78%
bushfire.

All of it is imported and all of it becomes a
:class:`~src.data_model.wildfire.Wildfire`, because dropping rows at import is
irreversible and no rule would honestly assign the 27% published as ``Unknown``.
:attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.fire_type` is what
separates them afterwards, and ``v_csiro_bushfire`` is the view that has already
applied the filter.

.. warning::

   **Any count over more than one provider must say so.** A query that sums
   :class:`~src.data_model.wildfire.Wildfire` across GisFIRE and does not filter
   ``fire_type`` is adding a fuel-reduction programme to a wildfire total. This is
   the first provider in the project for which that is true;
   :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.prescribed` marks 19
   such fires in Canada, against 166,048 here.

One row is one published polygon, and nothing is merged
--------------------------------------------------------

The published feature is a *mapped patch*, not a fire. Victoria's fire 705270 is
3,566 separate features, all ignited on 2018-05-26, all named *Murray Sunset -
Cowra Wilderness* and spread over 9 km. All 3,566 are stored, as 3,566 rows.

**The import does not dissolve them, and this was measured before it was decided.**
Grouping the archive on ``(source_layer, state, fire_id, ignition_date)`` — the
tightest key the published attributes offer — produces 4,078 merged groups in the
national class, and:

* **23.4% of them span more than 10 km**, 15.8% more than 25 km, 6.6% more than
  100 km;
* the widest joins two Western Australian features **2,403 km apart**, both
  publishing ``fire_id`` ``23`` on 2010-11-24;
* the next widest are the same shape — ``21``, ``001``, ``1``, ``4``, ``032`` — all
  Western Australian, all small numbers that the state's districts reuse.

A fire has several fronts; it does not have one on each side of Western Australia.
Those small numbers are placeholders exactly as ``'999'`` is, without saying so, and
nothing published distinguishes them from a real fire number. So the archive is
stored at the only unit that is certainly true — **the published feature** — and
reassembling fires is left to an application that can bring a rule to it. An import
that merged them could not be undone.

What is unique is ``(source_layer, object_id)``, the feature's own ``OBJECTID``.
:attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.fire_id` is **not
unique, not a key and not a grouping** —
:attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.fire_id_is_sentinel`
marks the placeholders that announce themselves, and the paragraph above is about
the ones that do not.

.. warning::

   A row count is a count of **mapped polygons**, not of fires: 347,834 rows for an
   archive whose real fire count nobody here knows. 186,632 of the national
   features have no usable identifier at all — 145,694 published as ``'999'``,
   4,592 as ``'0'``, every one of Queensland's 15,444 with nothing — so there is no
   honest way to derive that number from what is stored.

Every date is a day, and some are not dates
--------------------------------------------

All 347,503 published timestamps are at 00:00:00. There is no time of day anywhere
in this dataset, so :data:`PRECISION_DAY` is the best it ever gets and there is no
``minute`` here, exactly as in :mod:`src.providers.canada_nbac`.

:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is ``NOT NULL``, so the
start is resolved in the order :data:`DATE_SOURCES` gives — the ignition date, then
the extinguish date, then the capture date — and
:attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.date_source` records
which was used. 331 features publish no ignition date; 209 of them publish an
extinguish date and 2 a capture date, leaving **120 features with no date of any
kind**, which cannot be stored and are counted by the import instead.

What :func:`dates_are_plausible` flags — **514 features, 0.15%** — and why it flags
rather than fixes:

* 127 sit on the ArcGIS epoch sentinels, see :data:`EPOCH_DATES`;
* 14 are dated before 1900 at all, the earliest 1898-01-01;
* 241 extinguish dates fall outside :data:`EARLIEST_PLAUSIBLE_DATE` to
  :data:`LATEST_PLAUSIBLE_DATE` — the earliest is in the year **200** and two of the
  Northern Territory's are in **2525**;
* 365 fires are extinguished before they ignite.

They are stored as published and flagged, on the same argument
:mod:`src.providers.chile_conaf` makes about ``end_before_start``: correcting them
would be inventing data, and a flag is how a reader learns to distrust the handful
that need distrusting.

Being old is **not** implausible and is not flagged. 12,817 features predate 1950
and they are the archive doing its job — the national class reaches back to 1898 on
purpose. What the flag catches is a date that cannot be a date.

.. warning::

   **67,552 features — one in five — ignite on 1 January**, and 25,027 more on
   1 July, against a median day of a few hundred. Those are a fire season written
   as a date, not 92,579 fires that started at midnight on New Year's Day.

   No rule can separate them from the real 1 January fires, which in Australia are
   the peak of the season, so nothing here tries: they carry :data:`PRECISION_DAY`
   like every other row and :attr:`~src.providers.australia_csiro.wildfire.
   CsiroWildfire.dates_plausible` stays true. Anything computing a distribution
   over months or days of the year has to know this or it will find a spike it
   then has to explain.

The geometry is published in GDA94, and stored once
----------------------------------------------------

:data:`SOURCE_SRID` is EPSG:4283, which is geographic degrees and lies about 1.8 m
from EPSG:4326. Unlike :mod:`src.providers.portugal_icnf`,
:mod:`src.providers.canada_nbac`, :mod:`src.providers.catalonia_darpa` and
:mod:`src.providers.andalusia_rediam`, this model therefore stores **no second
geometry**: those four keep a projected national grid because an area or a distance
computed on it means something, and a second copy in degrees would mean nothing at
a cost of gigabytes — 155.8 million vertices are involved.

Anything needing metres has :attr:`~src.providers.australia_csiro.wildfire.
CsiroWildfire.area_ha` and :attr:`~src.providers.australia_csiro.wildfire.
CsiroWildfire.perim_km`, which were checked against the equal-area figure for the
published polygons (EPSG:3577, GDA94 / Australian Albers) and agree to the
rounding.
"""

from __future__ import annotations

import datetime

#: Name of the provider.
#:
#: The Digital Atlas distributes the geodatabase with no publisher, licence or
#: lineage recorded inside it — the embedded ESRI metadata carries nothing but an
#: ArcGIS Pro schema edit dated 2025-11-07 — so this name comes from the
#: distribution page, not from the data.
PROVIDER_NAME = "CSIRO"

#: The organisation, in full.
PROVIDER_FULL_NAME = "Commonwealth Scientific and Industrial Research Organisation"

#: The published product, covering both feature classes of the geodatabase.
PROVIDER_PRODUCT = "Historical Bushfire Extents"

#: Where the geodatabase is distributed.
PROVIDER_URL = ("https://digital.atlas.gov.au/pages/"
                "8b124790a8f54ccd9b3288288e21cfd2#datasets")

#: The CRS the polygons are published in: GDA94, geographic degrees.
#:
#: Recorded here and **not** stored as a second geometry column, for the reason set
#: out in the module docstring: it is degrees, like the EPSG:4326 the generic model
#: holds, and 1.8 m away from it.
SOURCE_SRID = 4283

#: The national feature class, and the value
#: :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.source_layer` takes
#: for a row that came from it. Seven states and territories, 1898-2025, no NT.
LAYER_NATIONAL = "national"

#: The Northern Territory feature class, published at its own version number and
#: covering 2020-2025. Fills the hole the national class leaves.
LAYER_NT = "nt"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: source_layer` takes. Constrained on the column: the geodatabase has two feature
#: classes and a row that came from neither is an import bug.
SOURCE_LAYERS = (LAYER_NATIONAL, LAYER_NT)

#: The feature class each :data:`SOURCE_LAYERS` value names in the geodatabase.
#:
#: The version numbers are part of the published names and are kept as published:
#: the national class is at v4 and the Northern Territory one at v1, which is the
#: only version information the file carries anywhere.
LAYER_FEATURE_CLASSES = {
    LAYER_NATIONAL: "National_Historical_Bushfire_Extents_v4",
    LAYER_NT: "NT_Historical_Bushfire_Extents_v1",
}

# --------------------------------------------------------------------------
# States and territories
# --------------------------------------------------------------------------

#: Western Australia — 167,937 features and 125.9 of the 155.8 million vertices.
STATE_WA = "WA"

#: Victoria, 87,771 features, seven eighths of them prescribed burns.
STATE_VIC = "VIC"

#: New South Wales, 55,199 features and the only state whose ``fire_id`` is nearly
#: unique on its own: 52,844 distinct values over 54,934 rows.
STATE_NSW = "NSW"

#: Queensland, 15,444 features, **none of which publishes a fire_id**.
STATE_QLD = "QLD"

#: Tasmania, 9,901 features, and the one state whose ``fire_id`` is unique
#: outright.
STATE_TAS = "TAS"

#: South Australia, 6,787 features.
STATE_SA = "SA"

#: The Australian Capital Territory, 2,306 features. Shares fourteen
#: ``(fire_id, ignition_date)`` pairs with New South Wales — one of several reasons
#: those columns do not identify a fire.
STATE_ACT = "ACT"

#: The Northern Territory, 2,451 features — every one of them from
#: :data:`LAYER_NT`, the national class having none.
STATE_NT = "NT"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: state_code` takes: the six states and two territories, constrained on the column.
#: A closed set defined by the Australian constitution rather than by this dataset,
#: which is what makes it worth stating in the schema.
STATE_CODES = (STATE_WA, STATE_VIC, STATE_NSW, STATE_QLD, STATE_TAS, STATE_SA,
               STATE_ACT, STATE_NT)

#: Published ``state`` spelling to :data:`STATE_CODES`, over both feature classes.
#:
#: Keys are lower-cased and stripped; look up with
#: ``STATE_NORMALISATIONS[value.strip().lower()]``. Both vocabularies are here
#: because both are published: the national class writes ``WA (Western
#: Australia)``, the Northern Territory one writes ``WA``, and the eight-value
#: normalised column is what a query uses.
STATE_NORMALISATIONS = {
    "wa (western australia)": STATE_WA,
    "wa": STATE_WA,
    "vic (victoria)": STATE_VIC,
    "vic": STATE_VIC,
    "nsw (new south wales)": STATE_NSW,
    "nsw": STATE_NSW,
    "qld (queensland)": STATE_QLD,
    "qld": STATE_QLD,
    "tas (tasmania)": STATE_TAS,
    "tas": STATE_TAS,
    "sa (south australia)": STATE_SA,
    "sa": STATE_SA,
    "act (australian capital territory)": STATE_ACT,
    "act": STATE_ACT,
    "nt (northern territory)": STATE_NT,
    "nt": STATE_NT,
}

#: The zone each state's fires are dated in when the geometry cannot be placed.
#:
#: **A fallback, not the rule.** The importer resolves the zone from the fire's own
#: perimeter against ``time_zone``, as the Canadian and Chilean ones do, and uses
#: this only where no time zone areas are imported. The lookup has to lead because
#: state borders are not zone borders: Broken Hill runs on Adelaide time inside New
#: South Wales, and Eucla on UTC+8:45 inside Western Australia — neither has a row
#: here that could be right.
STATE_TIME_ZONES = {
    STATE_WA: "Australia/Perth",
    STATE_VIC: "Australia/Melbourne",
    STATE_NSW: "Australia/Sydney",
    STATE_QLD: "Australia/Brisbane",
    STATE_TAS: "Australia/Hobart",
    STATE_SA: "Australia/Adelaide",
    STATE_ACT: "Australia/Sydney",
    STATE_NT: "Australia/Darwin",
}

#: Zone of last resort, when a fire has neither a resolved zone nor a usable state.
#:
#: Every published date is a bare date, so the zone decides which instant local
#: midnight is and nothing more — but Australia spans five of them, from UTC+8 in
#: Perth to UTC+11 in a Sydney summer, so it decides it by up to three hours.
DEFAULT_TIME_ZONE = "Australia/Sydney"

# --------------------------------------------------------------------------
# Fire type
# --------------------------------------------------------------------------

#: An unplanned fire. 85,336 features, 175.8 million hectares.
FIRE_TYPE_BUSHFIRE = "bushfire"

#: A deliberate fuel-reduction or land-management burn. 166,048 features and 84.8
#: million hectares — **half this dataset**, and not a wildfire. See the module
#: docstring before counting anything.
FIRE_TYPE_PRESCRIBED_BURN = "prescribed_burn"

#: Published as ``Unknown``: 93,960 features and 85.9 million hectares, a quarter of
#: the archive that says nothing either way. Kept as its own value rather than
#: folded into :data:`FIRE_TYPE_BUSHFIRE`, which would be inventing 93,960
#: wildfires, or excluded, which would be throwing away a quarter of Australia.
FIRE_TYPE_UNKNOWN = "unknown"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: fire_type` takes. Constrained, and ``NOT NULL``: exactly one national feature
#: publishes no type at all and it becomes :data:`FIRE_TYPE_UNKNOWN`, which is what
#: it is.
FIRE_TYPES = (FIRE_TYPE_BUSHFIRE, FIRE_TYPE_PRESCRIBED_BURN, FIRE_TYPE_UNKNOWN)

#: Published ``fire_type`` spelling to :data:`FIRE_TYPES`, keys lower-cased and
#: stripped.
#:
#: The case variants are the whole reason this map exists: the national class
#: publishes ``Prescribed Burn`` 154,891 times and ``Prescribed burn`` 11,157
#: times, and the Northern Territory one uses the second spelling throughout. They
#: are one category.
FIRE_TYPE_NORMALISATIONS = {
    "bushfire": FIRE_TYPE_BUSHFIRE,
    "prescribed burn": FIRE_TYPE_PRESCRIBED_BURN,
    "unknown": FIRE_TYPE_UNKNOWN,
}

# --------------------------------------------------------------------------
# Cause
# --------------------------------------------------------------------------

#: Lightning and other natural ignition. 8,961 features.
#:
#: The same proxy for lightning that :data:`~src.providers.canada_nbac.CAUSE_NATURAL`
#: and :data:`~src.providers.portugal_icnf.CAUSE_NATURAL` are, and **not** the named
#: ``Rayo`` of :data:`~src.providers.spain_egif.CAUSE_LIGHTNING`. Anything counting
#: lightning fires from this column is counting natural-cause fires and should say
#: so.
CAUSE_NATURAL = "natural"

#: Human ignition without intent — escapes, machinery, campfires. 9,144 features.
CAUSE_ACCIDENTAL = "accidental"

#: Deliberate ignition. 11,872 features, and the second most common published cause
#: in the Northern Territory class, where it is one row in five.
CAUSE_INCENDIARY = "incendiary"

#: Investigated and not established, or simply not recorded. 47,694 features, three
#: quarters of every cause this dataset publishes.
CAUSE_UNDETERMINED = "undetermined"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.cause`
#: takes. Constrained, and nullable: **78.2% of the national class publishes no
#: cause at all**, against none of the Northern Territory one.
FIRE_CAUSES = (CAUSE_NATURAL, CAUSE_ACCIDENTAL, CAUSE_INCENDIARY, CAUSE_UNDETERMINED)

#: Published ``ignition_cause`` spelling to :data:`FIRE_CAUSES`, keys lower-cased
#: and stripped.
#:
#: Four categories arrive in seven spellings. ``NOT DETERMINED`` (274 features) and
#: ``WF - unknown`` (1) are :data:`CAUSE_UNDETERMINED` written by a different hand;
#: ``OTHER`` (57) is **not** — it is a fifth category with no canonical form here,
#: so it maps to nothing, the row keeps it in ``cause_published`` and ``cause``
#: stays ``NULL``. The same treatment
#: :func:`src.providers.chile_conaf.fire_cause.resolve_cause` gives a cause it
#: cannot reconcile.
CAUSE_NORMALISATIONS = {
    "natural": CAUSE_NATURAL,
    "accidental": CAUSE_ACCIDENTAL,
    "incendiary": CAUSE_INCENDIARY,
    "undetermined": CAUSE_UNDETERMINED,
    "not determined": CAUSE_UNDETERMINED,
    "wf - unknown": CAUSE_UNDETERMINED,
}

# --------------------------------------------------------------------------
# How the burn was mapped
# --------------------------------------------------------------------------

#: ``capt_method``, normalised. The analogue of
#: :attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.ba_source`: what the
#: polygon was drawn from, and therefore what its edge is worth.
#:
#: Eleven published values over both classes, 48.4% of the national class publishing
#: none. Keys are lower-cased and stripped.
#:
#: The spread matters when comparing perimeters: 79,581 features are Landsat, whose
#: pixel is 30 m, and 181 are MODIS, whose pixel is 250 m and whose smallest
#: honest polygon is therefore several hectares. The Northern Territory class is
#: nothing but Sentinel (1,264) and MODIS (1,225).
CAPTURE_METHOD_NORMALISATIONS = {
    "landsat": "landsat",
    "sentinel": "sentinel",
    "modis": "modis",
    "noaa avhrr": "noaa_avhrr",
    "aerial photography": "aerial_photography",
    "linescanner": "linescanner",
    "air intelligence gps": "air_intelligence_gps",
    "ground intelligence": "ground_intelligence",
    "ground intelligence gps": "ground_intelligence_gps",
    "multiple": "multiple",
    "unknown": "unknown",
}

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: capture_method` takes.
#:
#: **Not constrained on the column**, unlike the causes and the types. The published
#: list is instruments and working practices, not a defined vocabulary: it gained
#: Sentinel when Sentinel launched and will gain whatever comes next, and a
#: ``CHECK`` here would reject the next publication rather than describe this one —
#: the argument :data:`~src.providers.canada_nbac.BA_SOURCES` makes.
CAPTURE_METHODS = tuple(sorted(set(CAPTURE_METHOD_NORMALISATIONS.values())))

# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

#: The start came from ``ignition_date``, which is what 99.9% of features publish.
SOURCE_IGNITION = "ignition"

#: No ignition date was published and the start is ``extinguish_date`` — the fire is
#: dated to the day it was declared out, which is the only day it has. 209
#: features.
SOURCE_EXTINGUISH = "extinguish"

#: Neither was published and the start is ``capture_date``, the day the imagery or
#: the survey was taken. Provenance of the mapping standing in for the fire. 2
#: features.
SOURCE_CAPTURE = "capture"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: date_source` takes, **in the order the import prefers them**. A feature with
#: none of the three cannot have a ``NOT NULL`` start and is not stored; there are
#: 120 of them.
DATE_SOURCES = (SOURCE_IGNITION, SOURCE_EXTINGUISH, SOURCE_CAPTURE)

#: The published date is a day. Every timestamp in both feature classes is at
#: 00:00:00, so this is the only precision this dataset has — no ``minute`` as in
#: :mod:`src.providers.portugal_icnf`, and no ``year`` as in
#: :mod:`src.providers.canada_nbac`, there being no year column to fall back to.
PRECISION_DAY = "day"

#: Every value :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.
#: date_time_precision` takes. One value, and the column is kept anyway so that a
#: query joining this archive to the Portuguese, Canadian or Chilean one is one
#: query over one column name.
DATE_TIME_PRECISIONS = (PRECISION_DAY,)

#: The dates that mean *no date*.
#:
#: 1899-12-30 is the ArcGIS and Excel epoch — day zero written out — and
#: 1900-01-01 is what a zero year becomes. 127 features publish one of them, and
#: they are stored as published with
#: :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.dates_plausible`
#: false rather than nulled, so that the published value stays visible.
EPOCH_DATES = (
    datetime.date(1899, 12, 30),
    datetime.date(1899, 12, 31),
    datetime.date(1900, 1, 1),
)

#: Earliest date this archive can be believed at.
#:
#: The national class runs back to 1898-01-01 and 12,817 features predate 1950. The
#: old ones are not impossible — Australia has fire records that old — but they are
#: not mapped burns either, and 1900-01-01 is an epoch artefact rather than a
#: summer. Anything before this is flagged, not dropped.
EARLIEST_PLAUSIBLE_DATE = datetime.date(1900, 1, 2)

#: Latest date this archive can be believed at.
#:
#: There to catch the transposed years: the earliest published extinguish date is in
#: the year **200** and the Northern Territory class has two in **2525**. 221
#: features are outside the range in one direction or the other.
LATEST_PLAUSIBLE_DATE = datetime.date(2100, 1, 1)

#: What ``fire_id`` says when it means *no identifier*.
#:
#: ``'999'`` is 145,694 Western Australian features and 3 South Australian ones;
#: ``'0'`` is 4,592 more. They are placeholders, not fires, and grouping by them
#: would merge a third of the continent into two rows — which is what
#: :attr:`~src.providers.australia_csiro.wildfire.CsiroWildfire.fire_id_is_sentinel`
#: exists to prevent. A blank or whitespace-only value counts as a sentinel too.
FIRE_ID_SENTINELS = ("999", "0", "-1")


def normalise_state(published: str | None) -> str | None:
    """The :data:`STATE_CODES` value ``published`` names, or ``None``.

    Parameters
    ----------
    published : str or None
        The ``state`` attribute as published, in either feature class's spelling.

    Returns
    -------
    str or None
        The normalised code, or ``None`` if the value is not one this dataset has
        been seen to publish — which the import treats as a row it cannot place,
        rather than guessing.
    """
    if published is None:
        return None
    return STATE_NORMALISATIONS.get(published.strip().lower())


def normalise_fire_type(published: str | None) -> str:
    """The :data:`FIRE_TYPES` value ``published`` names.

    Parameters
    ----------
    published : str or None
        The ``fire_type`` attribute as published, in either spelling.

    Returns
    -------
    str
        The normalised type, defaulting to :data:`FIRE_TYPE_UNKNOWN` — for the null
        one national feature publishes, and for any spelling not yet seen, which is
        what ``Unknown`` already means.
    """
    if published is None:
        return FIRE_TYPE_UNKNOWN
    return FIRE_TYPE_NORMALISATIONS.get(published.strip().lower(), FIRE_TYPE_UNKNOWN)


def normalise_cause(published: str | None) -> str | None:
    """The :data:`FIRE_CAUSES` value ``published`` names, or ``None``.

    Parameters
    ----------
    published : str or None
        The ``ignition_cause`` attribute as published.

    Returns
    -------
    str or None
        The normalised cause, or ``None`` where none was published or where the
        published one has no canonical form here — ``OTHER``, for which see
        :data:`CAUSE_NORMALISATIONS`.
    """
    if published is None:
        return None
    return CAUSE_NORMALISATIONS.get(published.strip().lower())


def normalise_capture_method(published: str | None) -> str | None:
    """The :data:`CAPTURE_METHODS` value ``published`` names, or ``None``.

    Parameters
    ----------
    published : str or None
        The ``capt_method`` attribute as published.

    Returns
    -------
    str or None
        The normalised method, or ``None`` where none was published or the spelling
        is new. Unconstrained on the column, so a new instrument is stored
        unnormalised in ``capture_method_published`` and read from there until this
        map learns it.
    """
    if published is None:
        return None
    return CAPTURE_METHOD_NORMALISATIONS.get(published.strip().lower())


def is_sentinel_fire_id(published: str | None) -> bool:
    """Whether ``published`` is a placeholder rather than an identifier.

    Parameters
    ----------
    published : str or None
        The ``fire_id`` attribute as published.

    Returns
    -------
    bool
        True for ``None``, for a blank or whitespace-only value and for every member
        of :data:`FIRE_ID_SENTINELS`. It marks the placeholders that announce
        themselves; the module docstring is about the ones that do not, and a false
        here is **not** a promise that the number identifies a fire.
    """
    if published is None:
        return True
    stripped = published.strip()
    return stripped == "" or stripped in FIRE_ID_SENTINELS


def dates_are_plausible(ignition: datetime.date | None,
                        extinguish: datetime.date | None) -> bool:
    """Whether a fire's published dates can be believed.

    Parameters
    ----------
    ignition : datetime.date or None
        The published ``ignition_date``.
    extinguish : datetime.date or None
        The published ``extinguish_date``.

    Returns
    -------
    bool
        False if either date is an :data:`EPOCH_DATES` sentinel, if either falls
        outside :data:`EARLIEST_PLAUSIBLE_DATE` to :data:`LATEST_PLAUSIBLE_DATE`, or
        if the fire is extinguished before it ignites. True otherwise, the missing
        dates of a fire that publishes none being nothing to disbelieve.

    Notes
    -----
    This is a *statement about the published dates*, not about the resolved instant:
    a fire flagged here still has a
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time`, stored as published.
    See the module docstring for what it excludes and how much of it there is.
    """
    for value in (ignition, extinguish):
        if value is None:
            continue
        if value in EPOCH_DATES:
            return False
        if value < EARLIEST_PLAUSIBLE_DATE or value > LATEST_PLAUSIBLE_DATE:
            return False
    if ignition is not None and extinguish is not None and extinguish < ignition:
        return False
    return True
