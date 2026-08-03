#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REDIAM — Red de Información Ambiental de Andalucía.

Data model for the Andalusian burnt area cartography: *Perímetros de incendios
forestales en Andalucía*, published by the Junta de Andalucía through the REDIAM
download service as one shapefile per year **and** one shapefile holding the whole
series.

The second **regional** perimeter source in GisFIRE, after
:mod:`src.providers.catalonia_darpa`, and it exists for the same reason: EGIF is an
administrative statistic and publishes a burnt *area* in hectares, never a polygon,
while what the autonomous regions publish is the shape. The relation between the
two is modelled on
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`;
what fills it in is not this import. See *The EGIF relation* below.

Where the shape of this dataset differs from Catalonia's is worth having in mind
throughout: it starts in 2008 rather than 1986, it publishes a burnt area of its
own (three of them), it publishes an ignition coordinate for four of its years, and
its code is an EGIF ``report_number`` from the first year onwards rather than from
1997.

One combined file, and one file per year
-----------------------------------------

The published set is ``PERIMETROS_COR_2008`` … ``PERIMETROS_COR_2025``, one
shapefile per year, plus ``PERIMETROS_COR_2008_2025``, which holds the whole series
in one layer. They are not two datasets: the combined file is the eighteen yearly
ones together, fire for fire.

The combined file is what the perimeter import reads
(:func:`is_combined_layer`), because it is the one the service republishes as the
archive grows and because reading one layer cannot half-import a series. The yearly
files are read for one thing the combined file does not carry — see *The ignition
point* below.

.. note::

   The name carries the range, so the next publication will be
   ``PERIMETROS_COR_2008_2026`` and not a new edition of this file name. Nothing
   here keys on the name: the import replaces **the years it finds inside the
   layer**, so a re-import under any name replaces rather than doubles. See
   :mod:`src.apps.imports.wildfires.andalusia_rediam.import_wildfires`.

Seven attributes, and only one of them identifies the fire
-----------------------------------------------------------

Every layer publishes ``Municipio``, ``Provincia``, ``CODIGO``, ``FECHA_INC``,
``SUP_ARBOLA``, ``SUP_MATORR`` and ``SUP_PASTIZ``. The yearly layers of 2021-2024
add ``X_INIC`` and ``Y_INIC``; 2021 also publishes an ``fid``, which is a row number
and not an identifier of the fire.

The names are not quite stable across the yearly files — 2015 upper-cases
``MUNICIPIO`` and ``PROVINCIA``, and 2020 and 2021 truncate ``SUP_PASTIZ`` to
``SUP_PASTI`` — which is one more reason the perimeters are read from the combined
layer, where they are spelled one way.

``CODIGO`` **is** the EGIF report number
-----------------------------------------

Unlike Catalonia's ``CODI_FINAL``, which took six forms over forty years, this code
is one thing in two dresses:

``2008410097``
    Ten digits — year, INE province, four-digit sequence — which is exactly
    :attr:`~src.providers.spain_egif.wildfire.EgifWildfire.report_number`. 2008-2024,
    and 812 of the 907 fires.
``IIFF2025040059``
    The same ten digits behind an ``IIFF`` prefix (*incendios forestales*). The whole
    of 2025, 97 fires. The prefix is a label, not part of the number.

Six 2019 codes are nine digits — ``201918023`` — a sequence written with three
digits instead of four rather than a different format; zero-padding it back yields
a report number like every other.

Every one of the 962 published features decodes, always to a **Andalusian** INE
province (:data:`PROVINCE_INE_CODES`), and always to the year of its own
``FECHA_INC``. :func:`egif_report_number` is that decode.

The code is nevertheless stored **exactly as published**, prefix and all, on
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.code`. Normalising it
at import would bake a matching rule into the import, and the matching rule is what
has not been agreed yet — the same rule the Catalan provider follows, and for the
same reason.

The natural key is the code **and the date**
---------------------------------------------

``(CODIGO, FECHA_INC)`` — 907 pairs in the combined file. The date is part of it for
the Catalan reason (a code that names two fires) held as a precaution rather than as
an observation: no Andalusian code names two dates today. What the pair does do here
is make the key comparable with
:attr:`~src.providers.catalonia_darpa.wildfire.DarpaWildfire`'s, so a query over both
regional datasets is one query.

962 features are 907 fires
---------------------------

55 codes are published **twice** — 2 in 2024 and 53 in 2025 — always with the same
date, and almost always with the same everything else. In 54 of the 55 the two rows
carry the same areas and the same footprint and differ only in the case of the names
(``LUBRIN`` beside ``Lubrín``, ``ALMERÍA`` beside ``Almería``): duplicate records
rather than two parts of a fire.

The exceptions are worth knowing, because they are the reason the import reports
rather than assumes:

* ``IIFF2025210122`` (Huelva) is published as **two different polygons**, 363.8 ha and
  517.4 ha of mapped area, which dissolve into 527.5 ha.
* it and ``IIFF2025230060`` are also published with **different burnt areas** — 82.83
  against 83.72 ha of scrub for the first, 10.0 against 10.8 ha of grassland for the
  second.

The import groups on the natural key and dissolves, exactly as the Catalan one does
with its shattered years, keeping the count in
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.part_count`. For 54 of
the 55 the union is the shape either row already had, so nothing is merged that was
not already the same polygon; for ``IIFF2025210122`` it is genuinely the union of two
mappings. Either way no fire is counted or summed twice, which is what would happen to
every 2025 total if the rows were stored as published.

Three burnt areas, and they are not the perimeter
--------------------------------------------------

``SUP_ARBOLA``, ``SUP_MATORR`` and ``SUP_PASTIZ`` are the burnt **wooded**, **scrub**
and **grassland** areas in hectares, published on every feature of every year with no
nulls at all.

They are kept as published and are **not** what a burnt area computed from the
polygon would give: over the 907 fires they sum to 152,696 ha against 165,582 ha of
mapped perimeter. The two disagree for the ordinary reason — the three
classes are vegetation types and a perimeter also encloses what is neither wooded,
scrub nor grassland — and both are worth having. GisFIRE keeps published numbers
rather than replacing them with measured ones.

There is no total column; the sum of the three is the closest thing the source
publishes to one.

The ignition point, for four years
-----------------------------------

``X_INIC`` and ``Y_INIC`` are the coordinates of the point the fire started at, on
the same grid as the perimeter, and they exist in the **yearly** layers of 2021,
2022, 2023 and 2024 — 201 fires — and nowhere else. The combined layer does not carry
them, and neither does the 2025 yearly layer.

So the import reads them from those four files and builds a
:class:`~src.providers.andalusia_rediam.ignition.RediamIgnition` for each, which is
what makes an Andalusian fire comparable with a
:class:`~src.providers.gfa.ignition.GfaIgnition` or an
:class:`~src.providers.spain_egif.ignition.EgifIgnition`.

.. warning::

   **The published point is not guaranteed to be inside the published perimeter.**
   Only 88 of the 201 are: the rest lie outside, by 1 m to 3 km, and one 2022 fire's
   point is 19.5 km away.

   That is not a projection error — the coordinates are unmistakably on the same
   grid — and it is not something to correct. A start point reported by the service
   and a perimeter mapped afterwards are two observations, and where they disagree
   the disagreement is the information. Both are stored as published.

Dates
-----

``FECHA_INC`` is a real DBF date field rather than text, so there is no format to
parse and no century to resolve — the whole of the Catalan date machinery is absent
here. It is published on every feature, it always falls in the year its code names,
and it carries no time of day: a fire's
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is local midnight on that
date and
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.fire_date` keeps the
date itself.

The CRS, and the axis order in the ``.prj``
--------------------------------------------

Every layer is published on **ETRS89 / UTM zone 30N**, the grid of peninsular Spain
west of 0°, and stored as :data:`SOURCE_SRID` — EPSG:25830.

The published ``.prj`` says so in an ESRI dialect that carries no EPSG code
(``PROJCS["ETRS_1989_ETRS-TM30", ...]``), and GDAL matches it to **EPSG:3042**, which
is the same projection declared with a *northing-easting* axis order. The
coordinates in the files are easting-northing, as every shapefile's are, and GDAL
says as much (``Data axis to CRS axis mapping: 2,1``).

Storing 3042 would therefore be storing a declaration the data does not follow, and
would invite PROJ to swap the axes on the next transform. The import asserts
EPSG:25830 — the same projection, the conventional order, and the code QGIS and
PostGIS use for the Spanish peninsular grid.

The EGIF relation
-----------------

:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.egif_wildfire_id`
exists and the import **never fills it in**. It is left ``NULL`` on every row, with
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.match_method`,
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.match_confidence` and
:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.matched_at` beside it.

The column is here so that the binding application is an ``UPDATE`` rather than a
migration. What is deliberately *not* here is a matching rule, or even the
vocabulary of one: unlike
:data:`~src.providers.catalonia_darpa.wildfire.MATCH_METHODS`, no set of method names
is fixed, because the rules for this dataset have not been agreed. The code being an
identifier from 2008 onwards makes it likely that most of them will be one rule; that
is not the same as having checked.
"""

import re

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: Andalusian wildfire hangs off. The product names the cartography rather than the
#: network, which publishes a great deal else.
PROVIDER_NAME = "REDIAM"
PROVIDER_FULL_NAME = "Red de Información Ambiental de Andalucía"
PROVIDER_PRODUCT = "Perímetros de incendios forestales en Andalucía"
PROVIDER_URL = "https://portalrediam.cica.es"

#: The projected CRS the perimeters are stored in — ETRS89 / UTM zone 30N.
#:
#: **Not** EPSG:3042, which is what GDAL reads off the published ``.prj``: that is
#: the same projection declared northing-easting, and the coordinates in the files
#: are easting-northing. See the module docstring.
#:
#: The published geometry is kept in it unchanged
#: (:attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.perimeter_etrs89_utm30n`)
#: alongside the EPSG:4326 reprojection on the generic model, for the reason set out
#: in :mod:`src.providers.portugal_icnf.wildfire`: a national grid in metres is what
#: an area or a distance means something in, and reprojecting is neither free nor
#: lossless.
SOURCE_SRID = 25830

#: The CRS the published ``.prj`` resolves to, recorded so that the difference is
#: documented rather than rediscovered. Never stored; see :data:`SOURCE_SRID`.
DECLARED_SRID = 3042

#: Zone the published dates are resolved against. Andalusia is one zone.
#:
#: Like every other importer's, a fallback rather than a rule: the zone is resolved
#: from the geometry, and this is what is used if no time zone areas are imported.
DEFAULT_TIME_ZONE = "Europe/Madrid"

#: INE province codes of the eight Andalusian provinces, in numerical order:
#: Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla.
#:
#: What makes a published ``CODIGO`` recognisable as an EGIF ``report_number``, and
#: what will restrict the EGIF side of a binding to the fires that could be
#: Andalusian at all. Every code in the archive decodes to one of these.
PROVINCE_INE_CODES = ("04", "11", "14", "18", "21", "23", "29", "41")

#: Prefix every published layer name carries.
LAYER_PREFIX = "PERIMETROS_COR"

#: The prefix the 2025 codes carry — *incendios forestales*.
#:
#: A label rather than part of the number: ``IIFF2025040059`` is report number
#: ``2025040059``. Stripped by :func:`egif_report_number` and by nothing else — the
#: code is stored as published.
CODE_PREFIX = "IIFF"

#: A yearly layer: the prefix and four digits.
YEARLY_LAYER_PATTERN = re.compile(rf"^{LAYER_PREFIX}_(\d{{4}})$", re.IGNORECASE)

#: The combined layer: the prefix and the two years of the range it covers.
#:
#: Matched as a shape rather than by name because the range moves — today's
#: ``PERIMETROS_COR_2008_2025`` becomes ``PERIMETROS_COR_2008_2026`` at the next
#: publication, and an import keyed on the name would treat that as a new dataset.
COMBINED_LAYER_PATTERN = re.compile(rf"^{LAYER_PREFIX}_(\d{{4}})_(\d{{4}})$", re.IGNORECASE)

#: The attributes the yearly layers publish for the ignition point, as ``ogr2ogr``
#: lands them (lower-cased). Present in 2021-2024 and in no other layer, the combined
#: one included. See the module docstring.
IGNITION_COLUMNS = ("x_inic", "y_inic")

#: Length of a report number: four digits of year, two of province, four of sequence.
REPORT_NUMBER_LENGTH = 10


def layer_year(layer: str) -> int | None:
    """The year a yearly layer covers, or ``None`` if it is not one.

    Parameters
    ----------
    layer : str
        A published layer or file name, without extension.

    Returns
    -------
    int or None
        The four-digit year, or ``None`` for the combined layer and for anything
        that is not a published layer name at all.

    Examples
    --------
    >>> layer_year("PERIMETROS_COR_2022")
    2022
    >>> layer_year("PERIMETROS_COR_2008_2025") is None
    True
    >>> layer_year("something_else") is None
    True

    Notes
    -----
    ``None`` rather than an exception, unlike its Catalan counterpart: here the
    caller is sorting a directory that legitimately holds both kinds of layer, so
    "this is not a yearly file" is an ordinary answer rather than a fault. What is
    *not* a published layer at all is
    :func:`~src.apps.imports.wildfires.andalusia_rediam.import_wildfires.skipped_archives`'s
    to report.
    """
    match = YEARLY_LAYER_PATTERN.match(layer)
    return int(match.group(1)) if match else None


def is_combined_layer(layer: str) -> bool:
    """Whether a layer name is the one holding the whole series.

    Examples
    --------
    >>> is_combined_layer("PERIMETROS_COR_2008_2025")
    True
    >>> is_combined_layer("PERIMETROS_COR_2025")
    False

    Notes
    -----
    By shape and not by name: the range in the name moves with every publication,
    and an import that recognised only ``PERIMETROS_COR_2008_2025`` would stop
    finding the file the year it grows.
    """
    return COMBINED_LAYER_PATTERN.match(layer) is not None


def combined_layer_years(layer: str) -> tuple[int, int] | None:
    """The range a combined layer's name claims, as ``(first, last)``.

    Returns ``None`` if the name is not a combined layer's.

    Examples
    --------
    >>> combined_layer_years("PERIMETROS_COR_2008_2025")
    (2008, 2025)

    Notes
    -----
    Used for reporting only. What the import actually replaces is the years it finds
    **inside** the layer, never the ones the file name claims — a name is not
    evidence about content, and this dataset's name has to change every year.
    """
    match = COMBINED_LAYER_PATTERN.match(layer)
    return (int(match.group(1)), int(match.group(2))) if match else None


def source_layer_name(layer: str) -> str:
    """The canonical form of a published layer name, as stored on every row.

    Upper-cased, which is how the service spells it and how every file on disk is
    named. Canonical rather than as-found so that a copy renamed in the download
    directory still records the same provenance.

    Examples
    --------
    >>> source_layer_name("perimetros_cor_2008_2025")
    'PERIMETROS_COR_2008_2025'
    """
    return layer.upper()


def egif_report_number(code: str) -> str | None:
    """The EGIF ``report_number`` a published ``CODIGO`` is, if it is one.

    Parameters
    ----------
    code : str
        A published code, with or without the :data:`CODE_PREFIX`.

    Returns
    -------
    str or None
        The ten-character report number, or ``None`` where the code is not one.

    Examples
    --------
    >>> egif_report_number("2008410097")
    '2008410097'
    >>> egif_report_number("IIFF2025040059")
    '2025040059'
    >>> egif_report_number("201918023")
    '2019180023'
    >>> egif_report_number("303/22N") is None
    True

    Notes
    -----
    Three published shapes, one number. The ``IIFF`` prefix of the 2025 codes is a
    label and comes off; a nine-digit code is a four-digit sequence written with
    three digits and is zero-padded back; everything else is already the number.

    The decode is accepted only when the province is one of the eight Andalusian
    ones (:data:`PROVINCE_INE_CODES`), so a code of some other kind that happens to
    have ten digits is refused rather than turned into a plausible-looking report
    number. The year is **not** checked against anything here — the caller has the
    published date and can compare the two, which is a stronger test than any this
    function could make on its own, and it is what the binding application will do.

    This is **derived, not stored**: the code is kept exactly as published (see the
    module docstring), and a function that reads it is a rule that can be corrected,
    where a column would be a decision frozen at import time.
    """
    if not code:
        return None
    digits = code[len(CODE_PREFIX):] if code.upper().startswith(CODE_PREFIX) else code
    if not digits.isdigit():
        return None
    if len(digits) == REPORT_NUMBER_LENGTH - 1:
        # A three-digit sequence: six 2019 codes are written this way.
        digits = f"{digits[:6]}0{digits[6:]}"
    if len(digits) != REPORT_NUMBER_LENGTH:
        return None
    if digits[4:6] not in PROVINCE_INE_CODES:
        return None
    return digits
