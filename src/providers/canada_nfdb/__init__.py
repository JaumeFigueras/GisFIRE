#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NFDB — Canadian National Fire Database, Agency Fire Data.

Data model for the Canadian national fire *reports*: one point per fire, as the
provincial, territorial and Parks Canada fire management agencies filed it,
compiled into one country-wide layer by Natural Resources Canada and published as a
single zipped shapefile.

**448,602 points over 1930-2025**, of which **195,240 are natural-cause** — by a
wide margin the largest set of lightning-attributable fires in GisFIRE, and each
one has a coordinate and a date.

The same agency as :mod:`src.providers.canada_nbac`, and a different product: NBAC
maps burn from imagery, this records what an agency reported. They are two
:class:`~src.data_model.data_provider.DataProvider` rows sharing a
:data:`PROVIDER_NAME`, they cover the same country and the same fires, and their
totals differ by 34 million hectares. Neither corrects the other.

It is a report with a point, not a perimeter with a hole in it
----------------------------------------------------------------

The shape of this model is EGIF's and Greece's, not ICNF's: a
:class:`~src.providers.canada_nfdb.wildfire.NfdbWildfire` carrying what the agency
filed — a reported size in hectares, a cause, dates, a response — and a
:class:`~src.providers.canada_nfdb.ignition.NfdbIgnition` carrying the point it was
filed at. :attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every
one and always will be; the agencies publish a location, not a shape.

Perimeters for Canadian fires come from NBAC, which is a provider of its own, and
**they are not written into these rows**. The two are related instead by
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id`, which a
later binding application will fill in.

The service publishes what it was given
----------------------------------------

The published summary is unusually frank, and it should be believed: *"the data
contained in the CNFDB are not complete nor are they without error. Locations are
approximate. Not all fires have been mapped, and data accuracy varies due to
different mapping techniques. Data completeness and quality vary among agencies and
between years."*

Thirteen agencies contribute, over wildly different periods and at wildly different
volumes — British Columbia alone files 156,554 of the 448,602 points, Prince Edward
Island 55. :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.src_agency` is
therefore not a decoration: a count over this archive is a count of *what thirteen
agencies chose to file*, and any trend across it is partly a trend in reporting.

Nothing identifies a fire uniquely
-----------------------------------

``NFDBFIREID`` looks like a national key and is not one: 446,918 distinct values
over 448,602 rows, so **1,684 are used twice**. ``FIRE_ID`` is the agency's own
number and has only 338,313 distinct values, being unique at best within an agency
and a year.

Both are therefore indexed and neither is constrained, the same decision
:attr:`~src.providers.gwis.wildfire.GwisWildfire.gwis_id` and the Greek record
number get, and for the same reason: a ``UNIQUE`` would reject records the service
really published.

The dirt, and where it is
--------------------------

Three kinds, all of which the import filters and none of which the model pretends
away:

**Coordinates outside Canada.** The published ``LATITUDE`` runs down to −115.667
and ``LONGITUDE`` to −5,617,700 — projected metres that have leaked into the
geographic columns. 244 of the 448,602 rows fall outside Canada's bounding box, 154
of them null or exactly zero. :func:`is_located` is the test.

**A year sentinel.** 95 rows carry ``YEAR = -999``, which means *not known* and
would otherwise be imported as a fire in the year minus nine hundred and ninety
nine. See :data:`UNKNOWN_YEAR`.

**Dates that are not there.** 4,047 rows publish no ``REP_DATE`` and 216,601 — 48%
— publish no ``OUT_DATE``. Nothing is invented for either: the report date is what
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is resolved from, and a
row without one is refused rather than dated to 1 January, because unlike NBAC this
dataset has no second date to fall back on.

The import reads from :data:`FIRST_YEAR` only
----------------------------------------------

1973, to line the archive up with :mod:`src.providers.canada_nbac`, which the
service distributes no earlier year of. The 1930-1972 points are published and are
deliberately left out: they would be 2% of the archive with no perimeter to bind
to, and no lightning dataset of that period exists to attribute them against.

The CRS is EPSG:3978, and this file does say so
-------------------------------------------------

Unlike NBAC's, the NFDB ``.prj`` names ``EPSG:3978`` outright. The point is stored
as published on
:attr:`~src.providers.canada_nfdb.ignition.NfdbIgnition.geometry_lambert` and
reprojected to EPSG:4326 on the generic model.
"""

from __future__ import annotations

#: Name of the provider, shared with :mod:`src.providers.canada_nbac`: one agency,
#: two products.
PROVIDER_NAME = "Canada Government - Natural Resources"

#: The agency, in full.
PROVIDER_FULL_NAME = "Natural Resources Canada, Canadian Forest Service"

#: The published product.
PROVIDER_PRODUCT = "Canadian National Fire Database - Agency Fire Data"

#: Where the point archive is published.
PROVIDER_URL = ("https://cwfis.cfs.nrcan.gc.ca/en/catalogue/results/"
                "7355c08f-1590-41cc-a751-8856afaa5959")

#: The CRS the points are published in: NAD83 / Canada Atlas Lambert, named
#: explicitly in the published ``.prj``.
#:
#: Kept unchanged on
#: :attr:`~src.providers.canada_nfdb.ignition.NfdbIgnition.geometry_lambert`
#: alongside the EPSG:4326 reprojection on the generic model.
SOURCE_SRID = 3978

#: Zone the published dates are resolved against when no time zone areas are
#: imported. Canada spans six, so this is a fallback and not a rule — the importer
#: resolves the zone from each fire's own point.
DEFAULT_TIME_ZONE = "America/Edmonton"

#: First year the import reads. See the module docstring: the archive starts in
#: 1930 and is cut to line up with NBAC.
FIRST_YEAR = 1973

#: What the service writes in ``YEAR`` for a fire whose year it does not know. 95
#: rows. Read as ``None``, never as a year.
UNKNOWN_YEAR = -999

#: ``CAUSE``, the agency's classification of the ignition source.
#:
#: *Natural* — 195,240 fires, 43.5% of the archive. As in
#: :mod:`src.providers.canada_nbac` and :mod:`src.providers.portugal_icnf`, this is
#: the nearest thing to a lightning category and **is not one**: it is dominated by
#: lightning in the Canadian boreal but is not defined as lightning.
CAUSE_NATURAL = "N"

#: *Human* — 242,098 fires, 54.0%.
CAUSE_HUMAN = "H"

#: *Unknown* — 11,264 fires, 2.5%.
CAUSE_UNKNOWN = "U"

#: Every value ``CAUSE`` takes. Constrained on the column: three single letters,
#: stable across thirteen agencies and ninety-five years.
FIRE_CAUSES = (CAUSE_NATURAL, CAUSE_HUMAN, CAUSE_UNKNOWN)

#: ``CAUSE2``, which refines ``CAUSE`` for a few thousand rows and is **not**
#: constrained.
#:
#: It repeats ``CAUSE`` on almost every row and adds two values that ``CAUSE`` has
#: no room for: ``H-PB``, a human-caused prescribed burn (372 rows), and ``RE``, a
#: re-burn (74). It is stored as published and left open because two agencies could
#: add a third refinement tomorrow and a ``CHECK`` would reject the year.
CAUSE2_PRESCRIBED_BURN = "H-PB"

#: A re-burn: fire in an area that has already burnt. 74 rows.
CAUSE2_REBURN = "RE"

#: Bounds a published longitude has to fall in to be a Canadian location. Canada
#: reaches −141° at the Yukon-Alaska border and −52.6° at Cape Spear; the range is
#: widened slightly at both ends rather than trimmed to the coastline, because a
#: fire on an offshore island is a fire and a border test is not this function's
#: job.
PLAUSIBLE_LONGITUDE = (-141.5, -52.0)

#: Bounds a published latitude has to fall in. Canada reaches 41.7°N at Middle
#: Island and 83.1°N at Cape Columbia.
PLAUSIBLE_LATITUDE = (41.0, 84.0)


def is_located(longitude: float | None, latitude: float | None) -> bool:
    """Whether a published coordinate pair is a Canadian location.

    244 of the 448,602 published rows fail this: 154 are null or exactly ``(0, 0)``,
    and the rest are projected metres that have leaked into the geographic columns —
    the published ``LONGITUDE`` minimum is −5,617,700, which is an easting.

    Parameters
    ----------
    longitude, latitude : float or None
        The published pair, as read.

    Returns
    -------
    bool
        ``True`` when the pair can become a
        :class:`~src.providers.canada_nfdb.ignition.NfdbIgnition`.

    Notes
    -----
    Bounds rather than a null test, for the reason
    :func:`src.providers.greece_ffa.is_located` gives: a coordinate outside the
    country is as certainly wrong as a zero, and a transposed pair — a Canadian
    latitude used as a longitude — lands at 41-84°E, which only a bounds test
    catches.

    This tests the *published geographic* columns. The shapefile's own geometry is
    projected and is the thing actually stored; the two are checked against each
    other at import, which is how a row whose columns disagree with its point gets
    noticed rather than silently preferring one.
    """
    if longitude is None or latitude is None:
        return False
    return (PLAUSIBLE_LONGITUDE[0] <= longitude <= PLAUSIBLE_LONGITUDE[1]
            and PLAUSIBLE_LATITUDE[0] <= latitude <= PLAUSIBLE_LATITUDE[1])


#: Published ``PRESCRIBED`` values that mean *yes*, lower-cased.
#:
#: The agencies do not agree on how to write it — some publish ``1``, some ``Yes``,
#: some ``true``, and one publishes ``PB`` — and most publish nothing at all.
#:
#: ``pb`` is *prescribed burn*, and it is by far the commonest affirmative in the
#: archive: **437 rows against a single ``1``**. It is here because the import
#: reported it as an unrecognised spelling on the first real run, and it is
#: unambiguous — 371 of the 437 also carry
#: :data:`CAUSE2_PRESCRIBED_BURN` on ``CAUSE2``, which is 371 of that value's 372
#: occurrences in the whole archive. See :func:`is_prescribed`.
PRESCRIBED_TRUE = frozenset({"1", "y", "yes", "t", "true", "pb"})

#: Published ``PRESCRIBED`` values that mean *no*, lower-cased. Recognised
#: separately from the unrecognised ones so that a value the agencies start writing
#: tomorrow is visible in a log rather than silently folded into ``False``.
PRESCRIBED_FALSE = frozenset({"0", "n", "no", "f", "false"})


def is_prescribed(value: object) -> bool:
    """Whether a published ``PRESCRIBED`` cell means the fire was a prescribed burn.

    Parameters
    ----------
    value : object
        The published cell, as read: text, a number, or nothing.

    Returns
    -------
    bool
        ``True`` only for a recognised affirmative. **Everything else is** ``False``,
        blanks and unrecognised values included.

    Notes
    -----
    The conservative direction is deliberate and is the whole reason this is a
    function rather than a cast. A prescribed burn is rare, and the column is
    unpublished on most rows; reading silence as *not prescribed* is wrong far less
    often than reading it as *prescribed* would be, and the alternative — a nullable
    column — would push the same decision onto every query instead of taking it once.

    What is lost is the difference between *the agency said no* and *the agency did
    not say*. :data:`CAUSE2_PRESCRIBED_BURN` on
    :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.fire_cause_detail` is the
    positive statement where one exists.

    A value that is neither recognised affirmative nor recognised negative is still
    ``False``, and the import counts and reports those separately — see
    :mod:`src.apps.imports.wildfires.canada_nfdb.import_wildfires` — because a new
    spelling appearing in a future publication should be noticed, not absorbed.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in PRESCRIBED_TRUE


def is_unrecognised_prescribed(value: object) -> bool:
    """Whether a published ``PRESCRIBED`` cell is neither a yes nor a no.

    Used by the import to report a spelling the agencies have started writing that
    :data:`PRESCRIBED_TRUE` and :data:`PRESCRIBED_FALSE` do not cover. Such a value
    is stored as ``False`` by :func:`is_prescribed`; this is what stops that being
    silent.

    A blank is *not* unrecognised — it is the normal state of the column.
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value not in (0, 1)
    text = str(value).strip().lower()
    if not text:
        return False
    return text not in PRESCRIBED_TRUE and text not in PRESCRIBED_FALSE


def published_year(year: int | None) -> int | None:
    """The published ``YEAR``, or ``None`` where the service wrote its sentinel.

    Parameters
    ----------
    year : int or None
        ``YEAR`` as read.

    Returns
    -------
    int or None
        The year, or ``None`` for :data:`UNKNOWN_YEAR` and for anything else that
        cannot be a fire year.

    Notes
    -----
    Anything below :data:`FIRST_YEAR` is *not* rejected here — the archive
    legitimately starts in 1930 and the cut to 1973 is the import's policy, not the
    reader's. What this refuses is a value that is not a year at all.
    """
    if year is None or year == UNKNOWN_YEAR or year <= 0:
        return None
    return year
