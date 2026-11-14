#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FMI — the lightning-location data of the Finnish Meteorological Institute.

Data model for the lightning strokes published by the *Ilmatieteen laitos*
(Finnish Meteorological Institute, FMI) through its open-data WFS, listed as
"Lightning strikes" on https://en.ilmatieteenlaitos.fi/open-data-sets-available.

Everything below was established by querying the service (November 2026); the
FMI pages document none of it — not the fields, not their units, not the
period covered.

The service
-----------

Two stored queries of https://opendata.fmi.fi/wfs return the same records:

* ``fmi::observations::lightning::simple`` — one ``BsWfsElement`` per stroke
  *and parameter*: verbose, a stroke is four (or sixteen) elements.
* ``fmi::observations::lightning::multipointcoverage`` — one coverage: a list of
  ``lat lon unixtime`` positions and a parallel list of value tuples. A small
  fraction of the size (430 strokes: 45 KB with all sixteen fields, against
  800 KB for ``simple`` with four); this is the one to download
  (:data:`STORED_QUERY`).

Both take ``starttime``/``endtime`` (UTC), ``bbox``, ``crs`` and ``parameters``.
The interval is **half-open**, ``[starttime, endtime)``, and may be **at most
168 hours** long (:data:`MAX_REQUEST_HOURS`); a longer one is refused with HTTP
400, ``Too long time interval requested!``. A week of a busy summer
(1-8 August 2018) is 507,923 strokes, 42 MB of XML, returned whole in about
twenty seconds. The service limits are 20,000 requests a day and 600 every five
minutes; there is no API key.

Fields: four by default, sixteen on request
-------------------------------------------

Without ``parameters`` the service returns ``multiplicity``, ``peak_current``,
``cloud_indicator`` and ``ellipse_major``. Twelve more are served when named
(:data:`PARAMETERS`); ``created`` and ``altitude`` are accepted too but always
``NaN``. Per stroke:

* the position, **ETRS89** geographic (:data:`SOURCE_SRID`), to 1e-4 degree;
* the instant, **UTC, whole seconds** — no fraction is published;
* ``flash_id``: the **flash** the stroke belongs to, a single sequence since
  1998 (172,850 in July 1998, 35.9 million in July 2025), never reset;
* ``multiplicity``: the number of strokes of the flash **on the flash's first
  stroke and 0 on every other one**;
* ``peak_current``: signed, whole kiloamperes;
* ``cloud_indicator``: 0 cloud-to-ground, 1 intra-cloud. An intra-cloud stroke
  is always a flash of its own;
* ``ellipse_major``/``ellipse_minor``/``ellipse_angle``: the location confidence
  ellipse. The axes are in **kilometres** (0 to 50) although the service's
  metadata says ``m``; the angle is in degrees, 0 to 180;
* ``chi_square``, ``sensors``, ``freedom_degree``: the location fit;
* ``rise_time``, ``ptz_time``: waveform rise and peak-to-zero times, by their
  values in microseconds (unit not published). 30.4 (rise) and 30.2
  (peak-to-zero) are the most frequent single values, although larger ones
  occur;
* ``angle_indicator``, ``signal_indicator``, ``timing_indicator``:
  undocumented. From 2005 always 1, 0 and 1; in 1998-2004, 0.2 to 1.5 % of the
  strokes, mostly two-sensor locations, have an angle and/or timing indicator
  of 0. ``signal_indicator`` is 0 in every sample;
* ``stroke_status``: 0 until 2010, 101 in 2011-2012, 0 again, 17 from 2017.

Strokes, not flashes, since 1998
--------------------------------

The archive starts on **8 January 1998** and every year down to the current
one is stroke-level data: a flash of *n* strokes is *n* records sharing a
``flash_id``, the first with ``multiplicity = n``. One July day per year from
1998 to 2025 was checked, and every one has this structure. What changes, as
the network and its processing evolved, is visible in the values (one July day
per year, so the years of each change are approximate):

* 1998-2004: cloud-to-ground only (``cloud_indicator`` always 0), and the only
  years with indicators other than 1, 0, 1;
* 1998-2005: ellipse up to 50 km, chi-squared up to 16;
* 2005-2008: some intra-cloud strokes; **a peak current of 0** on 10 to 23 %
  of the strokes — not recorded, stored as ``NULL``;
* 2006-2012: ellipse up to 25 km, chi-squared up to 10;
* 2013-2024: ellipse up to 15 km;
* 2025: ellipse up to 10 km;
* the intra-cloud share grows from 2 % (2005) to about half or more in most
  years from 2015 (24 % on the 2016 sample day).

The ellipse ceilings are a filter, not a clipping: the distribution runs at
full density up to the ceiling and stops, with no pile-up at it. FMI drops the
strokes located worse than the threshold, and that is also why about 0.01 % of
the flashes are inconsistent (33 of 411,529 in
1-8 August 2018, none of them at the edge of the request): a lone stroke with
``multiplicity`` 0, or a first stroke announcing more strokes than the flash
has. The published value is FMI's count before the filter; it is kept, beside
the count of strokes actually published.

Nothing in a record identifies a stroke
---------------------------------------

There is no stroke id, and no combination of fields is unique: within one
week, 26 pairs of strokes share flash, second and position, and two of them the
peak current too. The order of strokes within the same second is **not stable**
between requests (the response is sorted by the whole second only). An import
therefore replaces a period rather than updating rows in place.

Licence
-------

FMI open data is licensed **CC BY 4.0** (:data:`LICENCE`): attribution
required, redistribution allowed — unlike MeteoCat's, these strokes may be
committed as test fixtures, with attribution.
"""

from __future__ import annotations

#: Short name of the provider.
PROVIDER_NAME = "FMI"

#: The provider in full.
PROVIDER_FULL_NAME = "Ilmatieteen laitos (Finnish Meteorological Institute)"

#: The product, as the open-data catalogue names it.
PROVIDER_PRODUCT = "Lightning strikes"

#: The provider's website.
PROVIDER_URL = "https://en.ilmatieteenlaitos.fi/"

#: What goes in ``data_provider.description``.
PROVIDER_DESCRIPTION = (
    "Lightning strokes located by the lightning-location network of the Finnish "
    "Meteorological Institute (FMI), from 1998, covering Northern Europe. Downloaded "
    "from the FMI open-data WFS (https://opendata.fmi.fi/wfs), stored query "
    "fmi::observations::lightning::multipointcoverage. Licensed CC BY 4.0."
)

#: The licence of FMI open data.
LICENCE = "CC BY 4.0 (https://en.ilmatieteenlaitos.fi/open-data-licence)"

#: How to credit the data, wherever it is redistributed (test fixtures included).
ATTRIBUTION = "Finnish Meteorological Institute (FMI), open data, CC BY 4.0"

#: The WFS endpoint.
WFS_URL = "https://opendata.fmi.fi/wfs"

#: The stored query downloaded: the compact coverage encoding of the strokes.
STORED_QUERY = "fmi::observations::lightning::multipointcoverage"

#: The longest interval one request may cover, in hours.
MAX_REQUEST_HOURS = 168

#: The area the service serves, ``(west, south, east, north)`` in degrees: the
#: polygon every response declares as its sampled feature. No stroke falls outside.
SERVED_AREA = (2.3, 49.7, 35.7, 73.1)

#: The parameters requested, in the order they are asked for and written.
PARAMETERS = ("flash_id", "multiplicity", "peak_current", "cloud_indicator", "sensors",
              "freedom_degree", "ellipse_angle", "ellipse_major", "ellipse_minor",
              "chi_square", "rise_time", "ptz_time", "angle_indicator", "signal_indicator",
              "timing_indicator", "stroke_status")

#: The name every monthly file of the downloader starts with:
#: ``fmi_lightning_YYYY-MM.csv.gz`` and its ``fmi_lightning_YYYY-MM.meta.json``.
FILE_STEM = "fmi_lightning"

#: The header of a monthly file: the Unix time and the position as served
#: (latitude first), then every parameter in :data:`PARAMETERS` order.
FILE_COLUMNS = ("unixtime", "latitude", "longitude") + PARAMETERS

#: The CRS the coordinates are published in: ETRS89 geographic. Kept unchanged on
#: :attr:`~src.providers.finland_fmi.lightning.FmiLightning.geometry_etrs89`.
SOURCE_SRID = 4258

#: The projected CRS of Finland, ETRS89 / TM35FIN(E,N). Never a column: the
#: reprojection of the ETRS89 point is kept only in the GiST expression index
#: ``idx_fmi_lightning_geometry_3067``, and used by the ``v_fmi_lightning_3067``
#: view and by the thunderstorm reader (distances and hulls in metres). Its scale
#: error is at most 0.2 % over Finland, about 1 % at Oslo and Copenhagen, and
#: 3.8 % at the south-western corner of the served area (49.7 N 2.3 E); a fifth
#: of the served area is above 1 %.
PROJECTED_SRID = 3067

#: The ellipse axes are published in kilometres and stored in metres.
ELLIPSE_AXIS_FACTOR = 1000.0
