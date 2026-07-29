#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF — Estadística General de Incendios Forestales (Spain).

Data model for the Spanish national fire statistics, published by the MITECO
through the public search service at ``servicio.mapa.gob.es/incendios``. Its unit
of record is the **PIF** (*Parte de Incendio Forestal*), the official fire report
form — one per fire, identified by a ``numeroparte`` such as ``2020080001``.

EGIF is an **administrative record, not a perimeter dataset**. It says where,
when, why, what burnt and what was sent to fight it; it never publishes a burnt
area polygon. What it does publish, and what no other Iberian dataset here does,
is a **coordinate for the point the fire started at** — which is why an EGIF fire
is a :class:`~src.data_model.ignition.Ignition` with a
:class:`~src.data_model.wildfire.Wildfire` attached, and why that wildfire's
:attr:`~src.data_model.wildfire.Wildfire.perimeter` stays ``NULL`` for good.

Two exports, one record
-----------------------

The service exports the same fires in two formats, and GisFIRE reads both. They
are not alternatives: each carries something the other drops, and both key on
``numeroparte``.

**The Excel "resumen"** is one flat row per fire, 31 columns, the whole country in
a single file. Its decisive property is that it prints **codes with their
labels** — ``[213]  Quema de restos agrícolas (viñas,etc)`` — which is the only
public source for the cause and motivation catalogues; the service's own
``Search/getCausasIncendio`` endpoint is behind a login. It drops the numeric INE
codes for municipality and comarca, keeping only names, and it drops everything
outside the fire-level summary.

**The XML** carries the full report — thirteen blocks plus the per-forest-unit
``ParteMonte`` detail — with the numeric identifiers the Excel loses, but every
code is bare: ``<idcausa>231</idcausa>`` and nothing else.

So the import order is fixed: **an Excel export seeds
:class:`~src.providers.egif.fire_cause.EgifFireCause` and
:class:`~src.providers.egif.fire_motivation.EgifFireMotivation`, and the XML
import looks its codes up in them.** An XML-only database has fires whose cause
is an integer nobody can read.

What the XML adds beyond the Excel lands on
:class:`~src.providers.egif.wildfire_report.EgifWildfireReport`, a 1:1 optional
child of the wildfire. Its presence *is* the provenance: a fire with a report row
was seen in the XML, one without was only ever in the Excel. Nothing needs a flag
column to say so.

The published data is never complete
------------------------------------

Every fire the service exports is in state *Cerrado Revisión*, and a region's
fires appear only once that region has closed them. The 2022+2023 export checked
here holds 13,656 fires and is missing Cantabria and Navarra for 2022, and
Cataluña, Extremadura and Canarias for 2023; its 2022 forest total of 243,610 ha
is well below the ~306,000 ha eventually published for that year. Navarra is
absent from both.

A year therefore has to be re-exported and re-imported later, so the import is an
**upsert on ``numeroparte``**, never an append.

Dates are local wall-clock, and not all in the same zone
--------------------------------------------------------

Both exports publish naive local readings — ``29/01/2022 15:22:00`` in the Excel,
``2020-01-01T16:30:00`` in the XML. They are resolved against
:data:`DEFAULT_TIME_ZONE`, except for the Canary Islands, which are an hour behind
the mainland and take :data:`CANARY_TIME_ZONE`. Getting that wrong is a silent
one-hour error on the 47 Canarian fires of the sample, so the zone is chosen from
the fire's *comunidad*, not assumed.

:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **detection**,
not the ignition: ``pif_tiempos/deteccion`` is the earliest instant the report
carries, and nothing in EGIF says when the fire actually started.

The cause code is hierarchical, and the families are not what the form suggests
-------------------------------------------------------------------------------

``idcausa`` is a three-digit code whose first digit is the family. The families
were read off the Excel labels of all 87 codes present in 2022-2023, which
corrects a reading of the paper form that has ``400`` as *unknown*:

``100`` (:data:`CAUSE_LIGHTNING`)
    *Rayo*. The only family in which ``diastormenta`` is ever non-zero.
``2xx``
    Negligence in activities that use fire: agricultural and livestock burns,
    forestry residue, campfires and barbecues, smokers, rubbish, clearing.
``3xx``
    Accidents in activities with no implicit use of fire: railway, power lines,
    machinery, hand tools, vehicles, military.
``400`` (:data:`CAUSE_INTENTIONAL`)
    *Intencionado*, bare and with no subcodes; the detail is in ``idmotivacion``.
``500`` (:data:`CAUSE_UNKNOWN`)
    *Desconocida*.
``600`` (:data:`CAUSE_REKINDLE`)
    *Reproducido*.

The ``2xx``/``3xx`` boundary is close to "with or without fire use" but not clean
at the edges — ``292`` *Fuegos artificiales* is in the first, ``300`` *Quema de
cables para extraer cobre* in the second — so GisFIRE stores the digit and does
**not** materialise a family column naming the split. Read the label.

``idmotivacion`` is a **different code space** that happens to overlap: ``400``
is *Intencionado* as a cause and *Motivación desconocida* as a motivation. That is
why they are two lookup tables and not one, and why they must never be joined on
code alone. A motivation is published on exactly the fires whose cause is ``400``
— 7,117 of 13,656 in the sample, and on no others.
"""

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: EGIF fire hangs off. The product names the statistic rather than the ministry,
#: which publishes a great deal else on the same servers.
PROVIDER_NAME = "EGIF"
PROVIDER_FULL_NAME = "Ministerio para la Transición Ecológica y el Reto Demográfico"
PROVIDER_PRODUCT = "Estadística General de Incendios Forestales"
PROVIDER_URL = "https://servicio.mapa.gob.es/incendios/Search/Publico"

#: Geodetic datum of the mainland and Balearic coordinates, as the exports spell
#: it. 13,609 of the 13,656 fires checked.
DATUM_ETRS89 = "ETRS89"

#: Geodetic datum of the Canarian coordinates. The remaining 47 fires, and the
#: only ones outside :data:`DATUM_ETRS89`.
DATUM_REGCAN95 = "REGCAN95"

#: Every datum seen in the published exports. Older campaigns may add ED50 — the
#: XML's ``iddatum`` enumeration has more values than the two observed here — in
#: which case this tuple, the ``CHECK`` built from it and
#: :data:`SOURCE_SRIDS` all grow together.
DATUMS = (DATUM_ETRS89, DATUM_REGCAN95)

#: UTM zones the published coordinates fall in. Spain spans 28N to 31N: 30 is
#: most of the peninsula, 29 the west, 31 Catalonia and the east, 28 the Canaries.
UTM_ZONES = (28, 29, 30, 31)

#: The CRS each ``(datum, zone)`` pair means, which is what the importer needs to
#: turn the published easting and northing into the EPSG:4326 point stored on
#: :attr:`~src.data_model.ignition.Ignition.geometry`. Zone 27N is included for
#: REGCAN95 because El Hierro sits on the 18°W meridian, although no fire in the
#: sample uses it.
SOURCE_SRIDS = {
    (DATUM_ETRS89, 28): 25828,
    (DATUM_ETRS89, 29): 25829,
    (DATUM_ETRS89, 30): 25830,
    (DATUM_ETRS89, 31): 25831,
    (DATUM_REGCAN95, 27): 4082,
    (DATUM_REGCAN95, 28): 4083,
}

#: Zone the published wall-clock readings are resolved against for the peninsula,
#: the Balearics, Ceuta and Melilla.
DEFAULT_TIME_ZONE = "Europe/Madrid"

#: Zone for fires in the Canary Islands, an hour behind the mainland all year.
#: Chosen from the *comunidad*, not from the coordinate: see the module docstring.
CANARY_TIME_ZONE = "Atlantic/Canary"

#: Name of the *comunidad autónoma* :data:`CANARY_TIME_ZONE` applies to, as both
#: exports spell it.
CANARY_COMUNIDAD = "CANARIAS"

#: ``idcausa`` of a fire started by lightning. The one family in which
#: :attr:`~src.providers.egif.wildfire_report.EgifWildfireReport.days_since_storm`
#: is ever non-zero, which is what makes EGIF a source of holdover intervals.
CAUSE_LIGHTNING = "100"

#: ``idcausa`` of an intentional fire. The only cause that carries an
#: :class:`~src.providers.egif.fire_motivation.EgifFireMotivation`.
CAUSE_INTENTIONAL = "400"

#: ``idcausa`` of a fire whose cause was never established.
CAUSE_UNKNOWN = "500"

#: ``idcausa`` of a fire that restarted from an earlier one already declared out.
CAUSE_REKINDLE = "600"
