#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USWFS — the lightning strokes of the Alaska Lightning Detection Network.

Data model for the strokes located by the **Alaska Lightning Detection Network
(ALDN)**, owned and run by the U.S. Department of the Interior's **U.S. Wildland
Fire Service (USWFS), Alaska Geographic Area**, at Fort Wainwright (until 2026 the
BLM Alaska Fire Service, the name the README still uses). The network supports
the day-to-day work of wildland fire managers.

Everything below was established by reading the release of 2026-11-06 row by row
(November 2026): the metadata documents the columns in a sentence each, and two of
those sentences are wrong.

The release
-----------

One zip, ``Historical_Lightning_2012_forward_as_txt.zip`` (72 MB), downloaded by
hand from the publisher's page (:data:`SOURCE_URL`) and **re-published every
year**, cumulative from 2012. It holds:

* ``Historical_Lightning_2012_2026_TOA_WGS84.txt`` — the strokes: CSV, UTF-8 **with
  a byte-order mark**, one header line (:data:`FILE_COLUMNS`), 2,226,185 rows;
* ``TOALightning_2012_2026_FGDC_metadata.xml`` — FGDC metadata, whose
  ``ptvctcnt`` is the number of rows;
* ``README_BLM_Alaska_Historical_Lightning.pdf`` — the network's history since 1986.

Since 2012 the network is a **Time Of Arrival (TOA)** system, which reports
strokes, cloud strokes included; the older Impact network, which reported flashes
with a multiplicity, ran alongside it in 2012 and is not in this file. The
README warns that the sensors, their number and positions, and the processing
changed many times, so the data "may not be suitable for trend analysis".

The strokes fall within 250 km of Alaska, Yukon, British Columbia and the
Northwest Territories: from 46.1 to 79.4 N, and from 168.8 E across the
antimeridian to 97.0 W (535 strokes east of 180°). 83 % of them fall in June and
July. The release of 2026-11-06 runs from 2012-03-07 to 2026-09-28.

The columns, and what they turned out to be
-------------------------------------------

* ``STROKETYPE``: ``GROUND_STROKE`` or ``CLOUD_STROKE`` — "derived from amplitude
  values": a cloud stroke is exactly a stroke of amplitude 0.
* ``NETWORKCODE``: ``0`` on every row.
* ``UTCDATETIME``: ``M/D/YYYY H:MM:SS``, UTC, whole seconds. The file is sorted
  by it.
* ``MILLISECONDS``: described as the "duration of stroke, in milliseconds". **It
  is not**: it is the fraction of the second of ``UTCDATETIME``. Its values are
  uniform over 0-999, and within a second the sequence number follows them. The
  instant is therefore published to the millisecond. Within a second the file is
  not in millisecond order.
* ``LOCALDATETIME``: **unusable**. UTC-9 all year until 2014-05-28; Alaska's
  daylight saving time from then until 2020-03-05; UTC-9 again until 2020-05-30,
  then UTC-8 all year. 12.6 % of the rows disagree with America/Anchorage.
* ``STRIKETIME``: ``LOCALDATETIME`` cut to the minute, as text, on every row.
* ``LATITUDE``, ``LONGITUDE``: WGS 84 degrees (:data:`SOURCE_SRID`), 7 decimals.
* ``AMPLITUDE``: the peak current in **amperes**, signed, in steps of 100 A, and
  **saturating at ±500 kA** (230 strokes sit exactly there). 0 on every cloud
  stroke, which is how a cloud stroke is told apart, not a measurement.
* ``GDOP``: the geometric dilution of precision, an integer from 1 to 255 (255,
  on 68 strokes, is the ceiling of an 8-bit field).
* ``ERRSEMIMAJOR``, ``ERRSEMIMINOR``, ``ERRELIPSEANGLE``: the location error
  ellipse, documented only as "error ellipse parameter". The semi-axes are whole
  **kilometres**: the semi-major from 0 to 255 (the 8-bit ceiling again, on 81
  strokes), the semi-minor from 1 to 9; the angle is in whole degrees from -89 to
  89, its reference direction unstated, and so is the confidence level of the
  ellipse. The unit was checked two ways. Strokes 0 to 0.1 s apart — mostly
  strokes of one flash — lie a median 1.35 km apart when the semi-major is 1, and
  15 km apart when it is 13 to 20: in units of 100 m the distance could not grow
  that way. And the semi-major grows with the distance to the network, from 1 km
  in interior Alaska to 24 km 1,500-2,000 km away.
* ``STRIKESEQNUMBER``: a 16-bit counter of the processor, 0 to 65535. It wraps,
  has gaps (strokes clipped out of the release, presumably) and repeats, so it
  identifies nothing; empty on the first eight rows.
* ``POLARITY``: ``Negative``, ``Positive`` or ``Cloud To Cloud`` — the sign of
  the amplitude. Missing on 25,355 strokes (2018-12-11 to 2019-09-03) and wrong
  on 22 (2019-06-06, ``Positive`` with a negative amplitude).

Oddities
--------

* **24 strokes are published twice** (all on 2012-06-15): every value identical
  but the sequence number.
* **599 strokes have a semi-major axis of 0** and a semi-minor of 1, which no
  ellipse has: 31 from 2014-04-26 to 2014-05-27 and 568 from 2019-05-08 to
  2019-07-30, both spells next to a change in the processing (the local time
  changes regime on 2014-05-28; the polarity is missing around 2019). Stored as
  "not known".
* **40,740 strokes share their millisecond** with another: mostly a ground stroke
  and a cloud stroke a few kilometres apart, some coincidences hundreds of
  kilometres apart. The order of the strokes of one millisecond is therefore
  arbitrary.

No flashes
----------

A TOA network reports strokes, and nothing in a row groups them into flashes:
there is no flash id and no multiplicity. Cellsearch counts flashes, so GisFIRE
groups the strokes itself, at import, with the rule of the U.S. National
Lightning Detection Network (Cummins et al., 1998): a stroke joins a flash when it
is within :data:`FLASH_MAX_DURATION_S` of the flash's first stroke,
:data:`FLASH_MAX_INTERVAL_S` of its previous stroke and
:data:`FLASH_MAX_DISTANCE_KM` of its first stroke; ground and cloud strokes are
grouped apart, as FMI's flashes are. Over the release that gives 1.28 strokes per
ground flash (82 % single-stroke) and 1.10 per cloud flash.

Licence
-------

"None, these data are considered public domain" (:data:`LICENCE`); the USWFS asks
to be cited as the source and that any modification be described
(:data:`ATTRIBUTION`). Real strokes may therefore be committed as test fixtures,
with the citation beside them.
"""

from __future__ import annotations

#: Short name of the provider.
PROVIDER_NAME = "USWFS"

#: The provider in full.
PROVIDER_FULL_NAME = "U.S. Wildland Fire Service, Alaska Geographic Area"

#: The product: the network, as MeteoCat's product is its XDDE network.
PROVIDER_PRODUCT = "ALDN"

#: The provider's website.
PROVIDER_URL = "https://fire.ak.blm.gov/"

#: The page the release is downloaded from, as the metadata gives it.
SOURCE_URL = "https://fire.ak.blm.gov/predsvcs/maps.php"

#: What goes in ``data_provider.description``.
PROVIDER_DESCRIPTION = (
    "Lightning strokes located by the Alaska Lightning Detection Network (ALDN), the "
    "time-of-arrival network of the U.S. Wildland Fire Service, Alaska Geographic Area, "
    "from 2012, within 250 km of Alaska, Yukon, British Columbia and the Northwest "
    "Territories. Imported from the yearly cumulative release "
    "Historical_Lightning_2012_forward_as_txt.zip. Public domain. Flashes grouped by "
    "GisFIRE (the network publishes strokes only)."
)

#: The licence, as the metadata states it.
LICENCE = "Public domain (\"None, these data are considered public domain\")"

#: How to credit the data, wherever it is redistributed (test fixtures included).
ATTRIBUTION = ("U.S. Wildland Fire Service (USWFS), Alaska Geographic Area: Alaska "
               "Lightning Detection Network (ALDN), public domain")

#: The header of the strokes file, in order.
FILE_COLUMNS = ("STROKETYPE", "NETWORKCODE", "UTCDATETIME", "LOCALDATETIME", "MILLISECONDS",
                "LATITUDE", "LONGITUDE", "AMPLITUDE", "GDOP", "ERRSEMIMAJOR", "ERRSEMIMINOR",
                "ERRELIPSEANGLE", "STRIKETIME", "STRIKESEQNUMBER", "POLARITY")

#: The CRS the coordinates are published in: WGS 84. Stored as published on the
#: parent's ``geometry``; there is no second point to keep.
SOURCE_SRID = 4326

#: NAD83 / Alaska Albers, the usual projected CRS for Alaska. Never a column: kept
#: only in the partial GiST expression index ``idx_lightning_alaska_uswfs_geometry_3338``
#: on ``lightning``, and used by the ``v_alaska_uswfs_lightning_3338`` view and by the
#: thunderstorm reader (distances and hulls in metres). Its scale error over the
#: release's strokes is 0.25 % at the median, 1.4 % at the 99th percentile, and 17 %
#: at 79 N, where there are few.
PROJECTED_SRID = 3338

#: The amplitude is published in amperes and stored, as every peak current, in
#: kiloamperes: divided by this.
AMPERES_PER_KILOAMPERE = 1000.0

#: The ellipse semi-axes are published in kilometres and stored in metres.
ELLIPSE_AXIS_FACTOR = 1000.0

#: The box of every stroke of the 2026 release, rounded outward, ``(west, south,
#: east, north)`` in degrees. It crosses the antimeridian, so it is written in a
#: longitude frame that runs past 180: 263.1 is 96.9 W.
NETWORK_AREA = (168.8, 46.1, 263.1, 79.4)

#: A stroke joins a flash only within this many seconds of the flash's first stroke.
FLASH_MAX_DURATION_S = 1.0

#: ... and within this many seconds of the flash's previous stroke.
FLASH_MAX_INTERVAL_S = 0.5

#: ... and within this many kilometres of the flash's first stroke.
FLASH_MAX_DISTANCE_KM = 10.0
