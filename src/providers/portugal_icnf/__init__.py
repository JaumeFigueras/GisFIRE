#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICNF — Instituto da Conservação da Natureza e das Florestas (Portugal).

Data model for the Portuguese national burnt area cartography, published by the
ICNF as the *áreas ardidas* (burnt areas) layers of its ``BDG`` GeoServer: one
layer per year from 2009 on, plus three multi-year layers covering 1975-2008.
Every layer is a set of burnt-area polygons in EPSG:3763.

The dataset spans fifty years, and what it publishes about a fire changed
completely half way through — which is the one thing to know before reading
:class:`~src.providers.portugal_icnf.wildfire.IcnfWildfire`.

Two eras, one model
-------------------

**1975-2013** publishes two attributes and no more: the year the polygon burnt in
and its area in hectares. There is no identifier, no date, no cause and no
locality — not in the shapefile export and not in the WFS layer behind it. The
1975-1999 layers only map fires of 5 ha or more; from 2000 on the small ones are
mapped too.

**2014-2025** publishes twenty-two attributes: the fire's identifier in each of
the two national systems, its start, first-response and end times, its duration,
where it started down to the parish, its cause, and its burnt area split by land
type. Not every fire has them — a polygon the ICNF could not match to a record in
the fire database keeps the old two attributes and nothing else, 901 of the
20,475 features across those twelve years, nearly all before 2019.

Both eras are the same model. An importer fills what a layer publishes and leaves
the rest ``NULL``, and
:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.date_time_precision` records
which of the two a row came from without anyone having to know the years by
heart.

Times are lost in the shapefile export
--------------------------------------

The archives are ``SHAPE-ZIP`` exports of a WFS layer, and a shapefile's DBF has
no datetime type: ``DH_Inicio``, ``DH_1Interv``, ``DH_Fim`` and ``Edicao`` are
``xsd:dateTime`` at the source and arrive **truncated to dates**. A fire the WFS
reports as starting at ``2024-01-31T20:03:00`` is in the archive as
``2024-01-31``, and importing that as local midnight is twenty hours out.

The import from the archives therefore stores what it can — the date, at local
midnight — and marks the row ``day``. Recovering the real times means asking the
WFS, which is a separate application against a separate source and is deliberately
not done during a bulk import of fifty years.

Provenance is on the row, not in a comment
------------------------------------------

Because the two eras and the two date resolutions all live in one table, every
row says where it came from and how good its dates are:
:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.source_layer` names the
published layer, and
:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.date_time_precision` is one of
:data:`PRECISION_YEAR`, :data:`PRECISION_DAY` or :data:`PRECISION_MINUTE`.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: ICNF wildfire hangs off, kept beside the model for the same reason as OCHA's
#: (see :mod:`src.providers.ocha`). The product names the layer family rather
#: than the agency, because the ICNF publishes a great many other layers on the
#: same server and each would be its own provider row.
PROVIDER_NAME = "ICNF"
PROVIDER_FULL_NAME = "Instituto da Conservação da Natureza e das Florestas"
PROVIDER_PRODUCT = "Áreas Ardidas"
PROVIDER_URL = "https://si.icnf.pt/geoserverplinia/BDG/ows"

#: The projected CRS the ICNF publishes in — ETRS89 / Portugal TM06, the national
#: grid. Every layer, both eras. The published geometry is kept in it unchanged
#: (:attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.perimeter_etrs89_tm06`)
#: alongside the EPSG:4326 reprojection on the generic model.
SOURCE_SRID = 3763

#: Character set of the published shapefiles. GDAL cannot work this out on its
#: own: the archives carry a ``.cst`` file, which is a GeoServer convention it
#: does not read, and no ``.cpg``, which is the one it does. Read without it,
#: every accented name comes back mangled — ``Viseu Dão Lafões`` arrives with a
#: replacement character in place of each accented letter — and the damage is
#: silent, since what is stored is still a perfectly valid string.
SOURCE_ENCODING = "ISO-8859-1"

#: Zone the published wall-clock readings are resolved against. Every layer covers
#: mainland Portugal only — the extent of all twenty is within the mainland grid,
#: with no feature in the Azores or Madeira — so one zone covers the dataset. It
#: is a fallback rather than a rule: the importer resolves the zone from the
#: geometry like every other importer, and this is what it uses if no time zone
#: areas have been imported.
DEFAULT_TIME_ZONE = "Europe/Lisbon"

#: The fire was never dated: the layer publishes only a year, so
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the 1st of January
#: of :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.year` at local midnight and
#: means "some time in this year", not "on New Year's Day".
PRECISION_YEAR = "year"

#: The fire was dated but not timed: the shapefile export truncated the published
#: instants to dates, so the stored ones are local midnight on the right day. The
#: date is the provider's; the time of day is not.
PRECISION_DAY = "day"

#: The stored instants are the ones the provider published, to the minute. Only
#: reachable by reading them from the WFS, which the archive import does not do.
PRECISION_MINUTE = "minute"

#: Every value :attr:`~src.providers.portugal_icnf.wildfire.IcnfWildfire.date_time_precision`
#: may take, in increasing order of precision.
DATE_TIME_PRECISIONS = (PRECISION_YEAR, PRECISION_DAY, PRECISION_MINUTE)
