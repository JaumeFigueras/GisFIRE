#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Greek Fire Service — *Πυροσβεστικό Σώμα Ελλάδας*.

Data model for the Greek national wildfire statistics, *Δασικές Πυρκαγιές*,
published by the Hellenic Fire Service as a set of Excel workbooks — one per
year, plus one holding 2000 to 2012 in thirteen sheets.

The first source in GisFIRE outside the Iberian peninsula, and the second
**administrative** wildfire statistic after :mod:`src.providers.spain_egif`. It
is the same kind of dataset as EGIF and not the same kind as
:mod:`src.providers.gwis` or :mod:`src.providers.andalusia_rediam`: what the
service publishes is a *record of an intervention* — who was called, where, when
they arrived and left, what burnt and what was sent — and never a shape.

Twenty-six years, 260,194 fires
--------------------------------

2000 to 2025, every year present, between 6,834 (2014) and 15,303 (2001) fires a
year. The whole archive is in fifteen workbooks::

   Dasikes_Pyrkagies_2000-2012.xlsx      13 sheets, one per year
   Dasikes_Pyrkagies_2013.xlsx           … one sheet per file from here
   Dasikes_Pyrkagies_2015_v1.1.xlsx      the version suffix is the publication,
   Dasikes_Pyrkagies_2022_v1.7a.xlsx     not the data
   agrotodasikes_pyrkaies_2025.xlsx      the outlier; see below

There is no combined file. Unlike the Andalusian service, which republishes the
whole series every year, the Greek one publishes a year and leaves it — so a
re-publication is a *new file for that year*, and the unit an import replaces is
the year rather than the file.

The header is two rows, and the columns move
---------------------------------------------

Every sheet carries a **two-row header**: a banner row grouping the columns
(``ΚΑΜΜΕΝΗ ΕΚΤΑΣΗ``, ``ΠΡΟΣΩΠΙΚΟ``, ``ΟΧΗΜΑΤΑ``, ``ΕΝΑΕΡΙΑ``) over a row of
actual names. The 2025 file adds two more above them, a title and the year — so
where the header ends is a per-sheet fact rather than a constant, and nothing may
be read by position: the sheets have 16, 17, 31, 32, 36, 38 and 39 columns
depending on the year, in six different arrangements.

What arrives when:

2000-2008
    16 columns: the service, the forest district, the locality, the prefecture,
    the two dates and the two times, and eight burnt areas.
2009
    ``Δήμος``, the municipality.
2011
    the deployment block — five personnel counts, four vehicle counts and five
    aircraft counts.
2012
    ``Περιοχή - Τοποθεσία`` splits into ``Περιοχή`` and ``Διεύθυνση``.
2020
    ``Α/Α ΕΓΓΡΑΦΗΣ``, ``Α/Α ENGAGE`` and the first **coordinates** the dataset
    has ever carried.
2021
    the two leased-aircraft counts.
2022
    ``ΟΧΗΜ. ΟΤΑ`` is renamed ``ΟΧΗΜ. ΥΠΗΡΕΣΙΑΚΑ``.
2025
    ``Κατηγορία Συμβάντος`` and ``ΑΛΛΩΝ ΦΟΡΕΩΝ`` arrive, and ``Α/Φ GRU.`` is gone.

Several names are one field in different dress and must be read as one:
``Σκουπιδότοποι``/``Σκουπι-δότοποι``, ``ΜΗΧΑΝΗΜΑΤΑ``/``ΜΗΧΑΝΗ-ΜΑΤΑ``,
``ΕΘΕΛΟΝΤΕΣ``/``ΕΘΕΛΟ-ΝΤΕΣ``, ``ΒΥΤΙΟΦΟΡΑ``/``ΒΥΤΙΟ- ΦΟΡΑ``,
``ΕΛΙΚΟΠΤΕΡΑ``/``ΕΛΙΚΟ- ΠΤΕΡΑ`` — the hyphen is a line break in the published
spreadsheet, not part of the name.

.. warning::

   ``Α/Α ENGAGE`` is spelled with a **Latin** ``A`` in the 2025 file and with a
   Greek ``Α`` (U+0391) everywhere else. The two are different characters that
   render identically. Match the column by
   :func:`~src.providers.greece_ffa.normalise_column`, never by ``==``.

There are no coordinates before 2020
-------------------------------------

This is the single most important fact about the dataset, and the reason
:attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.ignition_id` is
nullable.

``X-ENGAGE`` and ``Y-ENGAGE`` appear in 2020 and are longitude and latitude in
**EPSG:4326** — decimal degrees, within Greece's bounds
(:data:`PLAUSIBLE_LONGITUDE`, :data:`PLAUSIBLE_LATITUDE`). 54,491 of the 58,246
fires from 2020 on carry one, 93.6%; the other 3,755 publish a pair of zeros,
which is the service's way of writing *no location* and must not be imported as a
point off the coast of Ghana.

**The 201,948 fires of 2000-2019 carry no coordinate whatsoever.** They are
locatable only by name — prefecture, municipality, forest district, locality —
and 77.6% of the archive is therefore mappable only as an administrative area.

In 2022-2024 the coordinate columns hold a ``VLOOKUP`` into a helper sheet
(``engage``/``engagexy``) keyed on ``Α/Α ENGAGE``. The cached results are stored
in the workbook, so reading with ``data_only=True`` gives the numbers and the
helper sheet does not have to be read at all.

There is no cause, in any year
-------------------------------

Nothing in any of the twenty-six sheets says why a fire started. There is no
equivalent of EGIF's ``idcausa``, so there is no
``greece_ffa_fire_cause`` catalogue and no lightning question that can be put to
this dataset — which is worth stating explicitly, since answering it for Spain is
what :mod:`src.providers.spain_egif`'s catalogues exist for.

What 2025 is, and why it is kept anyway
----------------------------------------

``agrotodasikes_pyrkaies_2025.xlsx`` is *αγροτοδασικές* — agricultural **and**
forest — where every earlier file is *δασικές*, forest. It is a wider net, and
it publishes ``Κατηγορία Συμβάντος``, a size class the others do not have:

======================  =====  ==============================================
Value                   Rows   Meaning
======================  =====  ==============================================
``ΜΙΚΡΗ``               6,290  small
``ΜΕΣΑΙΑ``              1,225  medium
``ΜΕΓΑΛΗ``                273  large
``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ``    1,255  **false alarm** — a call-out to no fire at all
======================  =====  ==============================================

The false alarms are 14% of the year. They are records of a *dispatch*, not of a
wildfire, and nothing that counts fires should count them — which is why the
category is stored on
:attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.incident_category`
rather than discarded at import: a column that says "this row is not a fire" can
be filtered, and a row silently dropped cannot be recovered.

For every year before 2025 the column is ``NULL``, which means *not published* —
not *not a false alarm*. Those years presumably contain false alarms too, and
there is no way to tell which.

Nothing identifies a fire before 2020
--------------------------------------

``Α/Α ΕΓΓΡΑΦΗΣ`` (the record number) and ``Α/Α ENGAGE`` (the incident number in
the service's dispatch system) begin in 2020. Before that a row has no
identifier of any kind — not a code, not a sequence, not even a row number.

And the record number is not unique where it exists: 57,734 distinct values over
58,246 rows, **512 of them used more than once**. So
:attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.record_number` is
indexed and *not* constrained, exactly as
:attr:`~src.providers.gwis.wildfire.GwisWildfire.gwis_id` is and for the same
reason: a ``UNIQUE`` here would reject records the service really published.

What identifies a row instead is
:attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.year` plus
:attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.source_sheet`, which
is provenance rather than identity — and it is why an import must replace a
**year** wholesale rather than upsert row by row. There is nothing to upsert on.

Times, and the one time zone
-----------------------------

Greece is one zone, :data:`DEFAULT_TIME_ZONE`, for the whole country and the
whole period. The dates arrive as Excel datetimes (as ``dd/mm/yyyy`` strings in
the 2025 file) and the times as a mixture of ``datetime.time`` and ``HH:MM``
strings depending on the year; the two are combined and resolved to an instant at
import, following :mod:`src.data_model.wildfire`.

27,183 fires — 10.4% — publish **no extinction date**, so
:attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL`` on one row in
ten.

Areas are published in στρέμματα
---------------------------------

Eight land-cover columns, and a *στρέμμα* is 1,000 m², a tenth of a hectare
(:data:`STREMMA_HA`). They are converted at import and stored as hectares, like
every other provider in GisFIRE, so that a Greek fire and a Spanish one are
comparable without a per-provider unit — see
:mod:`src.providers.greece_ffa.wildfire`.

There is no published total, and none is stored. The eight are the parts, and a
stored sum is a value that can disagree with them after an edit.
"""

from __future__ import annotations

import re
import unicodedata

#: Name of the provider, as it goes into
#: :attr:`~src.data_model.data_provider.DataProvider.name`.
PROVIDER_NAME = "GreeceFFA"

#: The agency, in full.
PROVIDER_FULL_NAME = "Πυροσβεστικό Σώμα Ελλάδας (Hellenic Fire Service)"

#: The published product.
PROVIDER_PRODUCT = "Δασικές Πυρκαγιές"

#: Where the workbooks are published.
PROVIDER_URL = "https://www.fireservice.gr/el_GR/synola-dedomenon"

#: Zone the published dates and times are resolved against.
#:
#: Unlike the Spanish and Portuguese importers, this one is not a fallback: Greece
#: has a single time zone over the whole country and the whole 2000-2025 period,
#: mainland and islands alike, so there is nothing for a spatial lookup to decide.
#: A row with no coordinate — three quarters of the archive — could not be resolved
#: spatially anyway.
DEFAULT_TIME_ZONE = "Europe/Athens"

#: The CRS ``X-ENGAGE`` and ``Y-ENGAGE`` are published in: plain WGS 84 longitude
#: and latitude in decimal degrees.
#:
#: There is no national grid to keep alongside it, which is why
#: :class:`~src.providers.greece_ffa.ignition.GreeceFfaIgnition` stores no
#: coordinate columns of its own — see that module. Greece's own grid, GGRS87 /
#: Greek Grid (EPSG:2100), does not appear anywhere in the published data.
SOURCE_SRID = 4326

#: One στρέμμα in hectares. The published areas are multiplied by this on the way
#: in; the conversion is exact in decimal and defined, not measured.
STREMMA_HA = 0.1

#: Bounds a published longitude has to fall in to be a location rather than the
#: ``0`` the service writes for *not known*. The archive's real values run
#: 19.39 to 29.57.
PLAUSIBLE_LONGITUDE = (19.0, 30.0)

#: Bounds a published latitude has to fall in, on the same argument. The archive's
#: real values run 34.93 to 41.74.
PLAUSIBLE_LATITUDE = (34.0, 42.0)

#: First year of the archive.
FIRST_YEAR = 2000

#: First year that publishes a coordinate — and therefore the first year any fire
#: can get a :class:`~src.providers.greece_ffa.ignition.GreeceFfaIgnition`. See the
#: module docstring.
FIRST_YEAR_WITH_COORDINATES = 2020

#: First year that publishes ``Α/Α ΕΓΓΡΑΦΗΣ`` and ``Α/Α ENGAGE``. The same year,
#: as it happens, but a different fact: one is about location and this one is
#: about identity.
FIRST_YEAR_WITH_IDENTIFIERS = 2020

#: The 2025 ``Κατηγορία Συμβάντος`` value that means the call-out found no fire.
#:
#: 1,255 of the 9,043 rows of 2025. Records of a dispatch rather than of a
#: wildfire: anything counting or measuring fires has to exclude them, and can,
#: because the value is stored. See the module docstring.
CATEGORY_FALSE_ALARM = "ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ"

#: The three real size classes of ``Κατηγορία Συμβάντος`` — small, medium, large —
#: in ascending order. Published in 2025 and in no earlier year.
CATEGORY_SMALL = "ΜΙΚΡΗ"
CATEGORY_MEDIUM = "ΜΕΣΑΙΑ"
CATEGORY_LARGE = "ΜΕΓΑΛΗ"

#: Every value ``Κατηγορία Συμβάντος`` takes in the published data.
#:
#: Not a ``CHECK`` on the column: this is one year's vocabulary observed once, and
#: a constraint built from it would reject the first new class the service adds.
#: See :mod:`src.providers.greece_ffa.wildfire`.
INCIDENT_CATEGORIES = (
    CATEGORY_SMALL,
    CATEGORY_MEDIUM,
    CATEGORY_LARGE,
    CATEGORY_FALSE_ALARM,
)

#: Characters the published headers break lines with, removed before matching.
#:
#: ``ΒΥΤΙΟ- ΦΟΡΑ`` and ``ΒΥΤΙΟΦΟΡΑ`` are one column in two spreadsheets, and so are
#: ``ΜΗΧΑΝΗ-ΜΑΤΑ``/``ΜΗΧΑΝΗΜΑΤΑ``, ``ΕΘΕΛΟ-ΝΤΕΣ``/``ΕΘΕΛΟΝΤΕΣ`` and
#: ``ΕΛΙΚΟ- ΠΤΕΡΑ``/``ΕΛΙΚΟΠΤΕΡΑ``. See :func:`normalise_column`.
_HEADER_NOISE = re.compile(r"[\s\-‐-―]+")

#: Latin letters that appear in the headers where the Greek ones are meant, and
#: what they stand in for. ``Α/Α ENGAGE`` is written with a Latin ``A`` in the
#: 2025 file and a Greek ``Α`` in every other; the two render identically and
#: compare unequal.
_LATIN_TO_GREEK = str.maketrans({"A": "Α", "B": "Β", "E": "Ε", "H": "Η", "I": "Ι",
                                 "K": "Κ", "M": "Μ", "N": "Ν", "O": "Ο", "P": "Ρ",
                                 "T": "Τ", "X": "Χ", "Y": "Υ", "Z": "Ζ"})


def normalise_column(name: str | None) -> str:
    """Reduce a published column header to the form the readers match on.

    Upper-cases, strips accents, removes the whitespace and hyphens the published
    headers wrap lines with, and folds the Latin homoglyphs onto their Greek
    letters. ``"ΒΥΤΙΟ- ΦΟΡΑ"``, ``"ΒΥΤΙΟΦΟΡΑ"`` and ``"βυτιοφορα"`` all come back
    as ``"ΒΥΤΙΟΦΟΡΑ"``; the Latin-``A`` ``"A/A ENGAGE"`` of the 2025 file and the
    Greek-``Α`` one of every other year both come back as ``"Α/ΑENGAGE"``.

    Parameters
    ----------
    name : str or None
        A header cell, as read. ``None`` — an empty cell — normalises to ``""``.

    Returns
    -------
    str
        The normalised form, suitable as a dictionary key.

    Notes
    -----
    Accents are stripped because the final sigma and the tonos are not written
    consistently across the twenty-six sheets. Nothing in the vocabulary is
    distinguished by an accent alone, so the fold loses nothing and spares the
    readers a per-year spelling table.
    """
    if name is None:
        return ""
    folded = unicodedata.normalize("NFD", str(name).strip().upper())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return _HEADER_NOISE.sub("", stripped).translate(_LATIN_TO_GREEK)


def is_located(longitude: float | None, latitude: float | None) -> bool:
    """Whether a published ``X-ENGAGE``/``Y-ENGAGE`` pair is a real location.

    The service writes ``0``/``0`` for a fire it did not locate — 3,755 of the
    58,246 rows from 2020 on — and null island is off the coast of Ghana. A pair
    is a location when both numbers are present and both fall inside Greece
    (:data:`PLAUSIBLE_LONGITUDE`, :data:`PLAUSIBLE_LATITUDE`).

    Parameters
    ----------
    longitude, latitude : float or None
        The published pair, as read.

    Returns
    -------
    bool
        ``True`` when the pair should become a
        :class:`~src.providers.greece_ffa.ignition.GreeceFfaIgnition`.

    Notes
    -----
    Bounds rather than ``!= 0``: a coordinate outside Greece is as wrong as a zero
    and just as certainly not a Greek fire, and this catches a transposed pair —
    a Greek latitude used as a longitude lands at 35-42°E, outside the longitude
    bounds, which a zero test would let through.
    """
    if longitude is None or latitude is None:
        return False
    return (PLAUSIBLE_LONGITUDE[0] <= longitude <= PLAUSIBLE_LONGITUDE[1]
            and PLAUSIBLE_LATITUDE[0] <= latitude <= PLAUSIBLE_LATITUDE[1])
