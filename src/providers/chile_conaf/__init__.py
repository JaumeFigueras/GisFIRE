#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF — Corporación Nacional Forestal, Chile. Fire reports by season.

Data model for the Chilean national fire *reports*: one point per fire as CONAF's
regional offices and the forestry companies filed it, published one shapefile per
*temporada* — the fire season — with the mainland and Easter Island in separate
archives.

**95,868 points over the fifteen seasons 2010-2011 to 2024-2025**, of which 95,625
are mainland and 243 Easter Island.

.. important::

   This is **Chile's CONAF**. :mod:`src.providers.mexico_conafor` is **Mexico's
   CONAFOR**, a different agency in a different country, and the two table
   prefixes differ by two letters: ``conaf_`` here, ``conafor_`` there. Both are
   the agencies' own names and neither can be renamed without lying about the
   source, so the distinction has to be read rather than inferred.

One agency, two products
-------------------------

CONAF publishes the fires twice. This module is the *seasonal report* archive —
every fire, with a point, a cause, a set of burnt areas by vegetation type and
(for the more recent seasons) the times it started and was put out.
:mod:`src.providers.chile_conaf_magnitud` is the *incendios de magnitud* archive —
mapped perimeters for the 781 large fires, from 2013-2014 on.

They are two :class:`~src.data_model.data_provider.DataProvider` rows sharing a
:data:`PROVIDER_NAME`, exactly as :mod:`src.providers.canada_nbac` and
:mod:`src.providers.canada_nfdb` are, and for the same reason: a row belongs to
the product it was published in, and writing a *magnitud* polygon onto a report
row would make its ``data_provider_id`` a lie.

Unlike Canada, though, the two Chilean archives describe **the same incidents** —
they come from one agency's one incident record, and the perimeter archive is the
subset of fires that reached 200 hectares. Every perimeter binds to a report, and
:mod:`src.apps.bindings.wildfires.chile_conaf_magnitud.bind_conaf_wildfires` is
what fills the link in. A count over both products together therefore
double-counts 781 fires; count over one.

It is a report with a point, not a perimeter
---------------------------------------------

The shape of this model is EGIF's, Greece's and NFDB's:
:class:`~src.providers.chile_conaf.wildfire.ConafWildfire` carries what the office
filed and :class:`~src.providers.chile_conaf.ignition.ConafIgnition` carries the
point it was filed at. :attr:`~src.data_model.wildfire.Wildfire.perimeter` is
``NULL`` on every one of them and always will be.

The season is 1 July to 30 June
--------------------------------

``TEMPORADA`` is published as ``"2010-2011"`` and names the austral fire year. The
window is not a convention this project has imposed: every dated feature in every
one of the thirty-six archives falls inside 1 July of the first year and 30 June
of the second, checked across all 95,868 of them — 2017-07-02 to 2018-06-27 for
2017-2018, 2019-07-01 to 2020-06-21 for 2019-2020, 2022-07-07 to 2023-06-30 for
2022-2023, and so on for every other dated season.

:func:`season_window` is that window and :data:`SEASON_START_MONTH` is where it
starts. The season is the unit everything here is organised by: the archives, the
importer's transactions, the statistics, and — for half the archive — the only
date there is.

Half the archive has no date
-----------------------------

``INICIO_IN`` / ``FH_INICIO`` is **entirely empty in eight of the fifteen mainland
seasons** — 2010-2011 through 2016-2017 and 2018-2019 — which is 49,379 fires,
51.6% of the archive. For those there is no day, no hour and no month: there is a
season, and that is all CONAF published.

So :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.date_time_precision`
has three values rather than NBAC's two, and the third is
:data:`PRECISION_SEASON`: the fire's
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is 1 July of the season
at local midnight and means *some time in this season*.

.. warning::

   Any statistic over month of year, time of day or duration is computable on the
   2017-2018-and-later half of the archive only. Computing one over the whole
   archive silently puts half the fires on 1 July at midnight. Filter on
   :data:`PRECISION_MINUTE` — see
   :mod:`src.apps.statistics.wildfires.chile_conaf.wildfire_statistics`, which
   reports the split rather than hiding it.

2017-2018 publishes starts but no ends: 6,048 fires with a
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` and no
:attr:`~src.data_model.wildfire.Wildfire.end_date_time`. A handful of rows across
the later seasons publish an end before their start; the import reports them and
stores both as published rather than swapping them.

Four date formats, and one of them is ambiguous
------------------------------------------------

.. code-block:: text

   18-ene-2023 15:50     Spanish month abbreviation — the dominant format
   2023/07/07            date only, no time
   08-09-2019 12:10      day-month-year
   6-abr-2023  11:51     as the first, with a doubled space

:func:`parse_published_datetime` reads all four and returns the precision it
achieved with them, which is how a bare ``2023/07/07`` becomes
:data:`PRECISION_DAY` rather than midnight pretending to be a time.

The third is read as **day-month-year**, which is the Chilean convention and what
the surrounding rows agree with, but it is genuinely ambiguous for the first
twelve days of a month and only two layers use it — ``if_isla_pascua_2019_2020``
and one row each of ``if_temporada_2020_2021`` and ``if_magnitud_2023_2024``.

The published coordinate is a UTM pair plus a zone
---------------------------------------------------

CONAF publishes ``UTM_E``, ``UTM_N`` and ``HUSO``, and the pair is read in the
zone ``HUSO`` names: 18 or 19 for the mainland, 12 for Easter Island. This was
checked against the shipped geometry of all 95,868 features and they agree
exactly — zero mismatches, one row with a seven-digit easting that is a typing
error rather than a zone problem.

That makes the shapefile geometry a *reprojection* of the published pair, and it
is the reprojection that is reliable: ``UTM_E``/``UTM_N`` are **zero on every row
of 2013-2014** and on 2,813 rows of 2019-2020, are stored as the text
``'317709 E'`` and ``'6350587 S'`` in 2023-2024 and ``if_isla_pascua_2023_2024``,
and ``HUSO`` itself is written ``NULL``, ``'18'``, ``'19'``, ``'12'``, ``'12.0'``
and MGRS-style ``'18F'`` … ``'19K'`` depending on the year.

So the geometry is what is stored and the published triple is kept beside it as
provenance. :func:`published_utm` is what reads it.

Chile has no single national projected CRS
-------------------------------------------

The mainland archives are published on :data:`SOURCE_SRID_MAINLAND` and the Easter
Island ones on :data:`SOURCE_SRID_EASTER`, which are 5,000 kilometres and seven
UTM zones apart. There is no grid that covers both, so
:class:`~src.providers.chile_conaf.ignition.ConafIgnition` carries **two** nullable
projected geometry columns with a ``CHECK`` that exactly one is filled, rather
than the single ``geometry_lambert`` :mod:`src.providers.canada_nfdb` gets.

One mainland layer, ``if_temporada_2024_2025``, is published in bare geographic
WGS 84 instead of UTM 19S. It is the same 6,262 mainland fires as any other season
and is reprojected onto the mainland grid at import like the rest; the importer
reads the layer's own SRS rather than trusting the filename.

Two cause classifications, and the codes are reused
-----------------------------------------------------

``CAUSA_GENE`` and ``CAUSA_ESPE`` carry 110 and 500 distinct published strings
across the archive, and behind them are **two different numbering systems**:

.. code-block:: text

   to 2022-2023     1.x  negligence      2.1  intentional
                    3.1  natural         4.1  unknown / undetermined

   from 2023-2024   1.x  negligence      2.x  intentional
                    3.x  natural         4.x  negligence (renumbered)
                                         5.1  indeterminate

.. danger::

   ``4.1`` is *incendios de causa desconocida* before the break and *faenas
   forestales* after it. The 2023-2024 and 2024-2025 layers contain **both**
   numberings, so the year does not settle it either.

   Group on
   :attr:`~src.providers.chile_conaf.fire_cause.ConafFireCause.cause_normalised`,
   never on the raw code, and if you must use the code then use it together with
   :attr:`~src.providers.chile_conaf.fire_cause.ConafFireCause.scheme`.

2016-2017 writes bare ``01``/``02``/``03``/``04`` in ``CAUSA_GENE`` with the
old-scheme ``1.7.1.``-style code still in ``CAUSA_ESPE``, and 6,888 fires publish
no ``CAUSA_GENE`` at all. The reconciliation lives in
:mod:`src.providers.chile_conaf.fire_cause`, on the same argument as
:mod:`src.providers.mexico_conafor.fire_cause`.

The dirt, and where it is
--------------------------

**Three corrupt records.** Rows 4810, 4811 and 4812 of
``if_temporada_2010_2011`` have binary garbage where ``COMUNA``, ``AMBITO``,
``TEMPORADA`` and the cause columns should be — a DBF that has come apart. Their
geometry is fine. :func:`is_corrupt` is the test; the import drops them and says
so, rather than letting the garbage become three rows of the cause table.

**Encoding damage.** ``if_temporada_2015_2016`` and ``if_temporada_2018_2019``
write ``'vehí\\xadculos'`` — the letter, then a soft hyphen — 3,226 and 3,583 times
between them, and the archives are littered with the usual mis-decoded accents
(``TRANSEONTES``, ``CALDA DE RAYO``, ``ELACTRICO``). Only seven of the thirty-six
layers ship a ``.cpg``. :func:`normalise` removes the soft hyphen so that the
damaged spelling groups with the intact one; it does **not** repair the rest, for
the reason :func:`src.providers.mexico_conafor.normalise` gives.

**Missing administrative names.** ``REGION`` and ``PROVINCIA`` are empty on every
row of six of the fifteen mainland seasons. The codes are there; the names are
not, and nothing is invented for them.

**Administrative codes in three shapes.** Zero-padded strings in most seasons
(``'08'``, ``'081'``, ``'08111'``), unpadded in 2022-2023 (``'5'``, ``'58'``,
``'5801'``), and floats in 2024-2025 (``'6.00000000000'``), which also publishes
no ``CODPROV`` or ``CODCOM`` at all. :func:`admin_code` normalises them to the
padded form.

Nothing identifies a fire
--------------------------

``NUMERO_REG`` is the office's own running number and is **not unique within a
season**, not even together with ``CODREG``: 2021-2022 has 5,975 distinct
``(CODREG, NUMERO_REG)`` pairs for 6,884 fires. It is all zeros in 2010-2011 and
2013-2014. Only 2023-2024 happens to be unique on the pair.

So there is no ``UNIQUE`` constraint anywhere in this provider — the
:mod:`src.providers.canada_nfdb` decision, for the same reason: a constraint here
would be a claim the published data does not support.
"""

from __future__ import annotations

import datetime
import re
import unicodedata

#: Name of the provider, shared with :mod:`src.providers.chile_conaf_magnitud`:
#: one agency, two products.
PROVIDER_NAME = "Chile - Corporación Nacional Forestal"

#: The agency, in full.
PROVIDER_FULL_NAME = ("Corporación Nacional Forestal (CONAF), Gerencia de "
                      "Protección contra Incendios Forestales")

#: The published product: the per-season fire report layers.
PROVIDER_PRODUCT = "Incendios forestales por temporada"

#: Where the archive is published.
PROVIDER_URL = "https://www.conaf.cl/incendios-forestales/incendios-forestales-en-chile/"

#: The CRS the mainland archives are published on: WGS 84 / UTM zone 19S.
#:
#: Every mainland layer but one carries a ``.prj`` naming
#: ``WGS_1984_UTM_Zone_19S``; ``if_temporada_2024_2025`` carries a bare geographic
#: WGS 84 one instead and is reprojected onto this grid at import. Kept unchanged
#: on :attr:`~src.providers.chile_conaf.ignition.ConafIgnition.geometry_utm19s`
#: alongside the EPSG:4326 reprojection on the generic model.
SOURCE_SRID_MAINLAND = 32719

#: The CRS the Easter Island archives are published on: WGS 84 / UTM zone 12S.
#:
#: Rapa Nui sits at 109°W, seven zones west of the mainland, and CONAF publishes
#: it as its own layer for exactly that reason. 243 points and one perimeter.
SOURCE_SRID_EASTER = 32712

#: Zone numbers ``HUSO`` names: 12 for Easter Island, 18 and 19 for the mainland.
#: Constrained on
#: :attr:`~src.providers.chile_conaf.ignition.ConafIgnition.utm_zone`.
UTM_ZONES = (12, 18, 19)

#: Character set the published shapefiles are read as.
#:
#: Only seven of the thirty-six layers ship a ``.cpg``, and those seven declare
#: UTF-8. The rest are read the same way, which is right for most of them and is
#: why the archive carries the mis-decoded accents the module docstring lists —
#: the damage is in the published bytes, not in the reading of them.
SOURCE_ENCODING = "UTF-8"

#: Season start year of the first published archive, ``"2010-2011"``.
FIRST_SEASON = 2010

#: Month the austral fire season starts in. 1 July to 30 June, verified against
#: every dated feature of every archive. See :func:`season_window`.
SEASON_START_MONTH = 7

#: Zone the published times are resolved against when no time zone areas are
#: imported.
#:
#: A fallback and not a rule. Chile spans three: ``America/Santiago`` for most of
#: the country, ``America/Punta_Arenas`` for Magallanes (región 12), which has
#: stayed on UTC−3 all year since 2016, and ``Pacific/Easter`` for Rapa Nui, which
#: is two hours behind the mainland. Every fire has a point, so the importer
#: resolves the zone spatially against
#: :class:`~src.data_model.geography.time_zone.TimeZone`; this is only what it uses
#: when no zone areas have been imported.
DEFAULT_TIME_ZONE = "America/Santiago"

#: Zone Easter Island fires fall in, named here because it is two hours from the
#: national default and a fallback that got it wrong would be wrong by two hours
#: on 243 fires.
EASTER_TIME_ZONE = "Pacific/Easter"

#: The published start carried a date and a time, so
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the instant CONAF
#: printed. 41,274 mainland fires and 130 Easter Island ones: 2017-2018, and
#: 2019-2020 onwards except 2023-2024.
PRECISION_MINUTE = "minute"

#: The published start carried a date and no time, so
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is local midnight of
#: that day. 4,972 mainland fires and 22 Easter Island ones: 2023-2024 and
#: ``if_isla_pascua_2023_2024`` are the two layers publishing ``YYYY/MM/DD``.
PRECISION_DAY = "day"

#: There was no published start at all, so
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the first instant
#: of :func:`season_window` and means *some time in this season*.
#:
#: 49,379 mainland fires — 51.6% of the mainland archive — and 91 Easter Island
#: ones: every fire of 2010-2011 through 2016-2017 and of 2018-2019. See the
#: warning in the module docstring.
PRECISION_SEASON = "season"

#: Every value
#: :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.date_time_precision`
#: takes. Constrained on the column.
DATE_TIME_PRECISIONS = (PRECISION_MINUTE, PRECISION_DAY, PRECISION_SEASON)

#: ``AMBITO``: the fire was reported and fought by CONAF. 66,715 fires.
REPORTER_CONAF = "Conaf"

#: ``AMBITO``: the fire was reported by a forestry company — the private
#: plantation owners run their own brigades and file their own reports. 29,145
#: fires.
#:
#: This is who reported the fire, not who owned the land and not who caused it. A
#: count by :data:`REPORTER_CONAF` is a count of *what CONAF's own offices filed*,
#: which is not the same as a count of fires on public land.
REPORTER_COMPANY = "Empresa"

#: Every value ``AMBITO`` takes once case is folded. Constrained on
#: :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.reporter`.
#:
#: The published spellings are ``Conaf``, ``CONAF``, ``Empresa`` and ``EMPRESA``,
#: plus six blanks and the two corrupt rows; the import folds them onto these two
#: and leaves the blanks ``NULL``.
REPORTERS = (REPORTER_CONAF, REPORTER_COMPANY)

#: Bounds a point on :data:`SOURCE_SRID_MAINLAND` has to fall in to be a mainland
#: Chilean location, as ``(min_easting, min_northing, max_easting, max_northing)``.
#:
#: Chile is a long way off zone 19's central meridian in the far south and west,
#: so the eastings run well below the 166,000 a textbook UTM zone is clipped at —
#: the published minimum is 69,786, at 74.5°W and 47°S, and it is a real fire.
#: The bounds are the published extent widened rather than a nominal zone extent,
#: which is the only way this test catches a layer published on the wrong grid
#: without rejecting Aysén and Magallanes.
PLAUSIBLE_EXTENT_MAINLAND = (40_000.0, 3_800_000.0, 700_000.0, 8_100_000.0)

#: Bounds a point on :data:`SOURCE_SRID_EASTER` has to fall in. Rapa Nui is 24 km
#: across, so this is tight on purpose: a mainland coordinate landing in an Easter
#: Island layer is an error worth failing on.
PLAUSIBLE_EXTENT_EASTER = (640_000.0, 6_980_000.0, 685_000.0, 7_015_000.0)

#: Spanish month abbreviations as the published date strings write them, mapped to
#: month numbers.
#:
#: ``set`` is in here beside ``sep`` because Chilean administrative writing uses
#: both for September; the archive as published today uses only ``sep``, and a
#: reader that fell over the day it changed would be a poor one.
MONTH_ABBREVIATIONS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}

#: Values that mean *nothing here* rather than a value, :func:`normalise` d.
#:
#: The archive has no single null token: ``'0'``, ``'N/A'``, ``'S/I'``,
#: ``'Sin informacion'``, ``'Sin Informacion'`` and ``'(en blanco)'`` all appear,
#: sometimes in the same column in different seasons.
MISSING_VALUES = frozenset({
    "", "0", "n/a", "na", "s/i", "sin informacion", "sin dato", "sin datos",
    "(en blanco)", "no aplica", "-",
})

#: Widths the three administrative codes are padded to: región, provincia, comuna.
#: The published codes nest — comuna ``08111`` is in provincia ``081`` in región
#: ``08`` — which is what makes the padding matter rather than being cosmetic.
ADMIN_CODE_WIDTHS = {"region": 2, "province": 3, "commune": 5}

#: Pattern a season is published as: ``"2010-2011"``.
_SEASON_PATTERN = re.compile(r"^\s*(\d{4})\s*[-/]\s*(\d{4})\s*$")

#: Control characters that mark a record as a corrupt DBF read. See
#: :func:`is_corrupt`.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

#: The four published datetime shapes, in the order :func:`parse_published_datetime`
#: tries them. See the module docstring for what each of them is.
_DATE_PATTERNS = (
    # 18-ene-2023 15:50 — and 6-abr-2023  11:51, with the doubled space.
    (re.compile(r"^(\d{1,2})-([a-zA-Z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})$"), "month_name_time"),
    # 18-ene-2023
    (re.compile(r"^(\d{1,2})-([a-zA-Z]{3})-(\d{4})$"), "month_name_day"),
    # 2023/07/07 and 2023-07-07
    (re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$"), "iso_day"),
    # 08-09-2019 12:10 — day-month-year. See the module docstring.
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})\s+(\d{1,2}):(\d{2})$"), "day_month_time"),
)


def normalise(value: str | None) -> str:
    """Fold a published string to the form the vocabularies are compared on.

    Strips, removes the soft hyphens the damaged layers carry, collapses internal
    whitespace, lower-cases and removes accents. ``'Tránsito de personas'``,
    ``'TRANSITO DE PERSONAS'``, ``'Tránsito De Personas'`` and the
    ``'Tránsi\\xadto de personas'`` of 2015-2016 all come back as
    ``'transito de personas'``.

    Parameters
    ----------
    value : str or None
        A published attribute value, as read. ``None`` normalises to ``""``.

    Returns
    -------
    str
        The normalised form, suitable as a dictionary key.

    Notes
    -----
    The soft-hyphen removal is the one thing this does that
    :func:`src.providers.mexico_conafor.normalise` does not. ``U+00AD`` is
    invisible, it appears 6,809 times across two seasons in the middle of words
    that are otherwise intact, and leaving it in would split every one of those
    strings off from its own spelling in every other season — which is a
    reconciliation failure, not a faithful reading.

    What it does **not** repair is the rest of the mojibake. ``'TRANSEONTES'`` and
    ``'CALDA DE RAYO'`` fold to themselves and stay distinct from the intact
    spellings, which is correct: they are different strings in the published files,
    and guessing which letter was lost would be a guess. Those are reconciled by
    name in :mod:`src.providers.chile_conaf.fire_cause`, where the guess can be
    read and argued with.
    """
    if value is None:
        return ""
    text = str(value).replace("­", "")
    folded = unicodedata.normalize("NFD", text.strip().lower())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


def is_missing(value: str | None) -> bool:
    """Whether a published value means *nothing here* rather than a value.

    Tests the :func:`normalise` d string against :data:`MISSING_VALUES`.

    Parameters
    ----------
    value : str or None
        The published cell, as read.

    Returns
    -------
    bool
        ``True`` when the cell should become ``NULL``.

    Notes
    -----
    ``'0'`` is in :data:`MISSING_VALUES` and that is a judgement rather than an
    obvious reading. It appears as a ``CAUSA`` on thirteen perimeters and as a
    ``CAUSA_GENE`` on fifty-four fires, in every case beside a blank
    ``CAUSA_ESPE``; it is a spreadsheet's idea of an empty cell, not a cause coded
    zero. It is **not** applied to the numeric area columns, where zero hectares of
    eucalyptus is a measurement.
    """
    return normalise(value) in MISSING_VALUES


def season_start_year(temporada: str | None) -> int | None:
    """The first year of a published ``TEMPORADA``.

    Parameters
    ----------
    temporada : str or None
        The published season, ``"2010-2011"``.

    Returns
    -------
    int or None
        ``2010`` for ``"2010-2011"``. ``None`` for anything that is not a pair of
        consecutive four-digit years — which is what the three corrupt rows of
        ``if_temporada_2010_2011`` and the blanks look like.

    Notes
    -----
    The two years have to be consecutive. ``"2010-2011"`` is a season;
    ``"2023-2025"`` — which one feature of ``if_magnitud_2023_2024`` really
    publishes — is a typing error, and reading its first half as a season would
    hide the fact that the cell is wrong.

    Seven features of the archive return ``None`` here: that one, and six blank
    cells in ``if_temporada_2010_2011``. The import falls back to the season the
    archive as a whole is for, and counts the fallbacks.
    """
    if temporada is None:
        return None
    match = _SEASON_PATTERN.match(str(temporada))
    if match is None:
        return None
    first, second = int(match.group(1)), int(match.group(2))
    if second != first + 1:
        return None
    return first


def season_window(year: int) -> tuple[datetime.datetime, datetime.datetime]:
    """The local window a season covers: 1 July ``year`` to 30 June ``year + 1``.

    Parameters
    ----------
    year : int
        The season start year, as :func:`season_start_year` returns it.

    Returns
    -------
    tuple of datetime.datetime
        Naive local ``(start, end)``, the start inclusive at midnight and the end
        exclusive at midnight on 1 July of the following year.

    Notes
    -----
    Naive rather than aware because the zone is resolved per fire from its own
    point — Chile has three — and this function does not know which one a fire
    is in. The importer applies ``AT TIME ZONE`` to the result.

    The window is measured, not conventional: every dated feature of every archive
    falls inside it. See the module docstring.
    """
    return (
        datetime.datetime(year, SEASON_START_MONTH, 1),
        datetime.datetime(year + 1, SEASON_START_MONTH, 1),
    )


def parse_published_datetime(
        value: str | None,
) -> tuple[datetime.datetime | None, str | None]:
    """Read a published date cell, and say how much of it was real.

    Parameters
    ----------
    value : str or None
        The published ``FH_INICIO``, ``INICIO_IN``, ``FECHA_INI``, ``FH_EXTINCI``,
        ``EXTINCION`` or ``FECHA_TER`` cell, as read.

    Returns
    -------
    tuple
        ``(datetime, precision)`` where *precision* is :data:`PRECISION_MINUTE` or
        :data:`PRECISION_DAY`, or ``(None, None)`` for a blank or an unreadable
        cell. The datetime is **naive local**: the zone is the caller's business.

    Notes
    -----
    :data:`PRECISION_SEASON` is never returned. It is not a reading of a cell — it
    is what the importer records when there is no cell to read — so the reader has
    no business inventing it.

    An unreadable cell returns ``(None, None)`` rather than raising, and the
    importer counts those. Across the archive as published today there are none
    beyond the blanks, which is what makes a new one worth noticing.
    """
    if value is None:
        return (None, None)
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text:
        return (None, None)

    for pattern, shape in _DATE_PATTERNS:
        match = pattern.match(text)
        if match is None:
            continue
        try:
            if shape == "month_name_time":
                day, name, year, hour, minute = match.groups()
                month = MONTH_ABBREVIATIONS.get(name.lower())
                if month is None:
                    return (None, None)
                return (datetime.datetime(int(year), month, int(day),
                                          int(hour), int(minute)), PRECISION_MINUTE)
            if shape == "month_name_day":
                day, name, year = match.groups()
                month = MONTH_ABBREVIATIONS.get(name.lower())
                if month is None:
                    return (None, None)
                return (datetime.datetime(int(year), month, int(day)), PRECISION_DAY)
            if shape == "iso_day":
                year, month, day = match.groups()
                return (datetime.datetime(int(year), int(month), int(day)),
                        PRECISION_DAY)
            day, month, year, hour, minute = match.groups()
            return (datetime.datetime(int(year), int(month), int(day),
                                      int(hour), int(minute)), PRECISION_MINUTE)
        except ValueError:
            # A shape that matched but is not a date — 31 February, hour 25.
            return (None, None)
    return (None, None)


def published_utm(
        easting: object,
        northing: object,
        huso: object,
) -> tuple[float, float, int, str | None] | None:
    """Read the published coordinate triple.

    Parameters
    ----------
    easting, northing : object
        ``UTM_E`` and ``UTM_N`` as read: a number, or the text ``'317709 E'`` /
        ``'6350587 S'`` that 2023-2024 and ``if_isla_pascua_2023_2024`` publish.
    huso : object
        ``HUSO`` as read: ``None``, ``'19'``, ``'12.0'`` or the MGRS-style
        ``'19K'``.

    Returns
    -------
    tuple or None
        ``(easting, northing, zone, band)`` with *zone* one of :data:`UTM_ZONES`
        and *band* the MGRS latitude letter or ``None``. ``None`` when the triple
        cannot be read.

        It reads on 43,636 of the 95,868 published features. The other 52,232 are
        mostly rows publishing no ``HUSO`` at all — eight mainland seasons leave the
        column empty — plus the 9,119 publishing ``(0, 0)`` for the pair.

    Notes
    -----
    This is **provenance, not geometry**. The point that gets stored comes from the
    shapefile's own geometry, which exists on all 95,868 features; this triple is
    absent, zeroed or unzoned on more than half of them. Wherever both are present
    they were checked against each other over the whole archive and agree, which is
    what licenses keeping the geometry and treating this as a record of what was
    printed.

    A zero easting is read as *unpublished* rather than as a coordinate. Easting
    zero is 500 km west of the zone's central meridian and 2013-2014 publishes it
    on every one of its 6,297 rows, so it is a blank written as a number.
    """
    def number(value: object) -> float | None:
        if value is None:
            return None
        text = str(value).strip().rstrip("ENSWensw").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    east, north = number(easting), number(northing)
    if east is None or north is None or east == 0 or north == 0:
        return None

    if huso is None:
        return None
    zone_text = str(huso).strip().upper()
    match = re.match(r"^(\d{1,2})(?:\.0+)?\s*([A-Z])?$", zone_text)
    if match is None:
        return None
    zone = int(match.group(1))
    if zone not in UTM_ZONES:
        return None
    return (east, north, zone, match.group(2))


def admin_code(value: object, kind: str) -> str | None:
    """The published administrative code, zero-padded to its width.

    Parameters
    ----------
    value : object
        ``CODREG``, ``CODPROV`` or ``CODCOM`` as read: ``'08'``, ``'5'`` or the
        ``'6.00000000000'`` that 2024-2025 publishes.
    kind : str
        One of the keys of :data:`ADMIN_CODE_WIDTHS` — ``"region"``,
        ``"province"`` or ``"commune"``.

    Returns
    -------
    str or None
        The padded code, or ``None`` for a blank or an unreadable one.

    Raises
    ------
    KeyError
        If *kind* is not one of :data:`ADMIN_CODE_WIDTHS`.

    Notes
    -----
    Padding rather than storing an integer, because these are codes and not
    quantities: región 08 is Biobío and there is no región 8 to add it to. Storing
    them unpadded would make ``'5801'`` and ``'05801'`` two comunas.

    A code longer than its width is returned unchanged rather than truncated. It
    means the published cell is not the code it claims to be, and losing digits
    would turn that into a plausible-looking wrong comuna.
    """
    width = ADMIN_CODE_WIDTHS[kind]
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # '6.00000000000' and '6.0' are how 2024-2025 writes región 06.
    match = re.match(r"^(\d+)(?:\.0+)?$", text)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) > width:
        return digits
    return digits.zfill(width)


def is_corrupt(*values: object) -> bool:
    """Whether a published record is a corrupt DBF read.

    Parameters
    ----------
    *values : object
        The record's text cells, as read.

    Returns
    -------
    bool
        ``True`` when any of them contains a control character.

    Notes
    -----
    Three records of ``if_temporada_2010_2011`` are like this — binary in
    ``COMUNA``, ``AMBITO``, ``TEMPORADA`` and the cause columns, and a run of
    plausible-looking text in others (``'0-2011 CONAF   484  BD0510C 309320.00'``
    turns up as a ``CAUSA_GENE``) that is one field's bytes read as another's. The
    file has come apart at those rows; nothing in them can be trusted, including
    the parts that look readable.

    The import drops them and reports the count. Three rows of 95,868 is a
    rounding error in any statistic; three rows of garbage in
    :class:`~src.providers.chile_conaf.fire_cause.ConafFireCause` would be three
    permanent entries in a classification.

    Tabs, carriage returns and newlines are **not** control characters for this
    purpose: they are whitespace, they appear in legitimately typed cells, and
    :func:`normalise` collapses them.
    """
    return any(_CONTROL_CHARACTERS.search(str(value))
               for value in values if value is not None)
