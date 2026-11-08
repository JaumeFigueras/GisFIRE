#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MeteoCat — the lightning-detection network of Catalonia.

Data model for the strokes located by the *Xarxa de Detecció de Descàrregues
Elèctriques* (XDDE) of the Servei Meteorològic de Catalunya (MeteoCat).

The data this package was written against is a delivery of yearly CSV extracts,
``DATMET-12706_cg_cm_<year>.csv``, **2006 to 2020, 6,156,214 cloud-to-ground
strokes**. The same data is served by the XDDE endpoint of the MeteoCat API
(https://apidocs.meteocat.gencat.cat/), which was not available when this was
written; a future API import shares the provider row and the model.

What a file holds
-----------------

One row per stroke, ``;``-separated, eleven columns::

    secidx; data; correntpic; chi2; eixmajor; eixmenor; numsensors;
    nuvolterra; idmunicipi; longitud; latitud

* ``secidx`` is the identifier of the **flash** the stroke belongs to, not of
  the stroke: 2014 has 291,306 single-stroke flashes, 54,383 with two strokes,
  and so on up to a few dozen. It is stored as
  :attr:`~src.providers.catalonia_meteocat.lightning.MeteocatLightning.flash_id`.
* ``data`` is the instant, **in UTC**, to the microsecond. Each file is one UTC
  calendar year: the 2010 file starts at ``2010-01-01 00:00:00.000022``.
* ``correntpic`` is the signed peak current, in kA.
* ``chi2``, ``eixmajor``/``eixmenor`` (metres) and ``numsensors`` describe how
  well the stroke was located. There is **no ellipse angle** in the files; the
  API publishes one.
* ``nuvolterra`` is always ``t``: the delivery is cloud-to-ground only (``cg``
  in the file name). The API returns intra-cloud strokes as well.
* ``idmunicipi`` is the six-digit INE code of the Catalan municipality the
  stroke fell in, empty outside Catalonia — which is most of them: the network
  covers from about 6.5 W to 9.4 E and 35.6 to 47.1 N, and only about 40 % of
  the strokes fall inside Catalonia's bounding box. Every stroke is kept.
* ``longitud``/``latitud`` are ETRS89 geographic coordinates
  (:data:`SOURCE_SRID`).

Nothing in a row identifies a stroke
------------------------------------

Not even ``(secidx, data)``: it repeats 81 times over the delivery, with two
different positions and currents (2014, flash 9926356: +22.4 kA and −22.9 kA at
the same microsecond, five kilometres apart). No row repeats whole. An import
therefore replaces a year rather than updating rows in place.

Two networks
------------

The delivery spans two generations of the network, told apart by the data
itself and recorded in
:attr:`~src.providers.catalonia_meteocat.lightning.MeteocatLightning.network_version`
(see :data:`NETWORK_VERSIONS`):

* **Version 1, 2006 to 29 September 2009.** ``numsensors`` and ``chi2`` are
  always ``0`` — not recorded, not zero. The current is clipped to ±30 kA, the
  ellipse is a circle (major = minor axis, 260 to 7,000 m), and the instant has
  a resolution of one second: the fraction is always ``.00xxxx``, the
  sub-millisecond digits being a sequence number within the second rather than a
  time. They do increase along a flash, so ordering by the published instant
  still orders the strokes.
* **Version 2, from 1 September 2009.** Two to five sensors, chi² from 0 to 50,
  currents up to about ±940 kA, a real ellipse and microsecond times.

**September 2009 is reported by both** (88,694 version-1 strokes and 46,767
version-2 ones), so the same discharges may be in the database twice, once per
network. Both are kept; filter on ``network_version`` to choose.

The flash identifiers of the two networks are independent: 6,286 values of
``secidx`` are used by both in 2009 for unrelated flashes. A flash is therefore
identified by ``(network_version, flash_id)`` — and that pair is never shared
by two files, so a flash never crosses a year.
"""

from __future__ import annotations

#: Short name of the provider.
PROVIDER_NAME = "MeteoCat"

#: The provider in full.
PROVIDER_FULL_NAME = "Servei Meteorològic de Catalunya"

#: The product: the lightning-detection network, *Xarxa de Detecció de
#: Descàrregues Elèctriques*. Shared by the CSV delivery and the API.
PROVIDER_PRODUCT = "XDDE"

#: The provider's website.
PROVIDER_URL = "https://www.meteo.cat/"

#: What goes in ``data_provider.description``.
PROVIDER_DESCRIPTION = (
    "Xarxa de Detecció de Descàrregues Elèctriques (XDDE), the lightning-detection "
    "network of the Servei Meteorològic de Catalunya. Strokes obtained as yearly CSV "
    "extracts (request DATMET-12706, 2006-2020) and through the MeteoCat API "
    "(https://apidocs.meteocat.gencat.cat/)."
)

#: The CRS the coordinates are published in: ETRS89 geographic. Kept unchanged on
#: :attr:`~src.providers.catalonia_meteocat.lightning.MeteocatLightning.geometry_etrs89`.
SOURCE_SRID = 4258

#: The projected CRS of Catalonia, ETRS89 / UTM zone 31N. Not stored: exposed by
#: the ``v_meteocat_lightning_25831`` view as a reprojection of the ETRS89 point.
PROJECTED_SRID = 25831

#: The header of a CSV extract, in order.
COLUMNS = ("secidx", "data", "correntpic", "chi2", "eixmajor", "eixmenor", "numsensors",
           "nuvolterra", "idmunicipi", "longitud", "latitud")

#: The generations of the network, by the number stored in
#: :attr:`~src.providers.catalonia_meteocat.lightning.MeteocatLightning.network_version`.
#: A new generation gets the next number; the numbers are never reused.
NETWORK_VERSIONS = {
    1: "2006 to September 2009: no sensor count or chi-squared, current clipped to "
       "±30 kA, circular ellipse, one-second time resolution",
    2: "From September 2009: sensor count, chi-squared, elliptical confidence region, "
       "microsecond time resolution",
}


def network_version(published_sensors: int) -> int:
    """The generation of the network that located a stroke of the CSV delivery.

    The first generation did not record the number of sensors and published ``0``;
    the second always records at least one. Nothing else tells them apart reliably —
    the second generation's chi-squared can be ``0`` too — so the sensor count is
    the rule.

    It describes the 2006-2020 delivery. A third generation will not be told apart
    by its data and will need a rule of its own (a date, or a field of the API).

    Raises
    ------
    ValueError
        If the count is negative.
    """
    if published_sensors < 0:
        raise ValueError(f"A negative number of sensors: {published_sensors}")
    return 1 if published_sensors == 0 else 2
