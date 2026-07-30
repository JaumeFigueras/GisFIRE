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

Usually. **Half** the 1982-2023 archive is a *parte* with no coordinate at all —
the exports before 1998 publish none — so
:attr:`~src.providers.egif.wildfire.EgifWildfire.ignition_id` is nullable.

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

How much of the XML is modelled, and why that much
--------------------------------------------------

Not all of it. The XSD carries 13 ``pif_*`` blocks, a per-forest-unit
``ParteMonte`` block and **25 ``Rel*`` relations**, all of which are populated in
the real exports — none of it is dead schema. Modelling the lot is of the order
of fifteen extra tables.

What is kept is **the fire**: where, when, why, how certain the why is, what
burnt, the weather at the time, and the fuel and behaviour codes. That is the
subset a study of lightning-caused fires reads, and on the lightning subset of
2004-2023 it is populated at 94-100% for everything except the weather block
(49-94%, worse the further back you go).

What is left out is the response and the accounting: ``pif_medios`` (personnel,
aircraft, machinery), ``pif_tecnicas``, the casualty and by-ownership breakdowns,
``pif_anexo``'s regeneration and erosion indices, and the whole ``ParteMonte``
tree with its species detail and timber valuations.

Adding any of it later is additive and does not disturb what is here: the report
is 1:1 on the wildfire's primary key, and ``numeroparte`` is a stable unique key
present in both export formats, so a re-import backfills new columns by upsert.
Do get the *types* right first time, though — the ``v_egif_*`` views block
``ALTER COLUMN ... TYPE`` on every column they select.

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

#: Every datum the exports name. Checked against all seven XML exports covering
#: 2004-2023: ED50 never appears, and no third label does either. What older
#: campaigns do instead is publish no datum at all — see :data:`DATUM_CODES`.
DATUMS = (DATUM_ETRS89, DATUM_REGCAN95)

#: What the XML's ``iddatum`` means, for the two codes that can be resolved.
#:
#: The element is **absent before the 2014-2016 campaigns** — 2004-2013 publish
#: coordinates with no datum whatsoever, and 2014-2016 carries it on 6,401 of its
#: 30,365 fires — which is why
#: :attr:`~src.providers.egif.ignition.EgifIgnition.datum` is nullable. From 2017
#: on it is universal.
#:
#: Three values occur in the whole 2004-2023 archive: ``2`` on 67,462 fires, ``5``
#: on 443 (tracking the Canarian huso-28 fires, hence REGCAN95), and ``3`` on three
#: records, which nothing published maps to anything. Those three keep their raw
#: code in :attr:`~src.providers.egif.ignition.EgifIgnition.datum_code` and a
#: ``NULL`` datum, rather than being silently called ETRS89.
DATUM_CODES = {
    "2": DATUM_ETRS89,
    "5": DATUM_REGCAN95,
}

#: UTM zones the published coordinates fall in. Spain spans 28N to 31N: 30 is
#: most of the peninsula, 29 the west, 31 Catalonia and the east, 28 the Canaries.
#:
#: This is what the coordinates *should* be in, and what
#: :data:`SOURCE_SRIDS` is keyed on — it is **not** a constraint on
#: :attr:`~src.providers.egif.ignition.EgifIgnition.utm_zone`, which stores the
#: published number whatever it is. See that attribute for why.
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

#: The UTM zone to fall back on when a fire's published ``huso`` is not a zone
#: Spain lies in, keyed by INE province code.
#:
#: **A fallback, never an override.** A published zone in :data:`UTM_ZONES` is
#: always used as published; this is consulted only for the handful of records
#: whose zone is unusable — 7 in the XML archive, a few more in the Excel, with
#: values like ``3``, ``63`` and ``71``.
#:
#: The distinction matters because these are *modal* zones, not authoritative
#: ones: eleven provinces genuinely straddle two, and Badajoz, Cáceres, Asturias,
#: Zamora and Barcelona are close to evenly split. Taken across the whole archive
#: the modal zone agrees with the published one on only 92.7% of fires, so using
#: it in place of a good published value would move a quarter of a million points.
#: Derived from the published ``Huso`` of 298,266 fires in the eight Excel
#: exports; the comment on each line is the province and the modal zone's share.
PROVINCE_UTM_ZONES = {
    "01": 30,  # Álava 862/863
    "02": 30,  # Albacete 1976/1976
    "03": 30,  # Alicante 1737/1766
    "04": 30,  # Almería 1877/1878
    "05": 30,  # Ávila 3008/3008
    "06": 29,  # Badajoz 4435/7583 — straddles 29/30
    "07": 31,  # Illes Balears 2728/2730
    "08": 31,  # Barcelona 4884/5816 — straddles 30/31
    "09": 30,  # Burgos 3099/3099
    "10": 30,  # Cáceres 7904/13761 — straddles 29/30
    "11": 30,  # Cádiz 2033/2071
    "12": 30,  # Castellón 1616/1739
    "13": 30,  # Ciudad Real 1871/1871
    "14": 30,  # Córdoba 2012/2012
    "15": 29,  # A Coruña 28143/28143
    "16": 30,  # Cuenca 3212/3212
    "17": 31,  # Girona 3054/3054
    "18": 30,  # Granada 2722/2723
    "19": 30,  # Guadalajara 2913/2913
    "20": 30,  # Guipúzcoa 614/614
    "21": 30,  # Huelva 3181/3423
    "22": 30,  # Huesca 2203/2663
    "23": 30,  # Jaén 3020/3023
    "24": 30,  # León 7300/7620
    "25": 31,  # Lleida 2652/2652
    "26": 30,  # La Rioja 1570/1571
    "27": 29,  # Lugo 16576/16581
    "28": 30,  # Madrid 5522/5522
    "29": 30,  # Málaga 1941/1941
    "30": 30,  # Murcia 2229/2229
    "31": 30,  # Navarra 5254/5255
    "32": 29,  # Ourense 46024/46026
    "33": 30,  # Asturias 18946/26672 — straddles 29/30
    "34": 30,  # Palencia 1770/1770
    "35": 28,  # Las Palmas 662/662
    "36": 29,  # Pontevedra 33674/33674
    "37": 30,  # Salamanca 4247/4458
    "38": 28,  # Santa Cruz de Tenerife 820/822
    "39": 30,  # Cantabria 8400/8400
    "40": 30,  # Segovia 1421/1421
    "41": 30,  # Sevilla 2673/2788
    "42": 30,  # Soria 1589/1589
    "43": 31,  # Tarragona 2875/2875
    "44": 30,  # Teruel 2441/2665
    "45": 30,  # Toledo 4240/4240
    "46": 30,  # Valencia 3975/3976
    "47": 30,  # Valladolid 1589/1590
    "48": 30,  # Vizcaya 607/607
    "49": 30,  # Zamora 4070/6330 — straddles 29/30
    "50": 30,  # Zaragoza 4371/4381
    "51": 30,  # Ceuta 8/8
    "52": 30,  # Melilla — no fire in the archive, included for completeness
}

#: The easting and northing a published coordinate has to fall between for the
#: point to be worth placing, in metres.
#:
#: A UTM easting is meaningful over roughly 100-900 km from the zone's western
#: edge, and Spain's northings run from about 3,060,000 (El Hierro, 27.6°N) to
#: 4,850,000 (the Pyrenees, 43.8°N). The bounds are set wide of both.
#:
#: This is a **plausibility check, not a tidy-up**: 339 fires of the 292,447 that
#: publish a coordinate — 0.12%, nearly all before 2011 — publish one that cannot
#: be where the fire was. The failures are ordinary data entry, and they are
#: obvious once reprojected: a northing with three digits missing
#: (``2022320419``, Ourense, ``y = 4655``, which lands in the Gulf of Guinea), the
#: easting typed into both fields (``2005230258``, Jaén, ``434047, 434047``), an
#: extra digit (``2006490039``, Zamora, ``y = 46648500``).
#:
#: A fire that fails it is stored **without an ignition**, exactly like the 293,710
#: that publish no coordinate at all, rather than with a point in the ocean that
#: every spatial query would then have to exclude by hand. The published numbers
#: are still kept, on the fire's own row, so nothing is lost.
PLAUSIBLE_UTM_EASTING = (100_000.0, 900_000.0)
PLAUSIBLE_UTM_NORTHING = (2_800_000.0, 4_900_000.0)

#: Zone the published wall-clock readings are resolved against for the peninsula,
#: the Balearics, Ceuta and Melilla.
DEFAULT_TIME_ZONE = "Europe/Madrid"

#: Zone for fires in the Canary Islands, an hour behind the mainland all year.
CANARY_TIME_ZONE = "Atlantic/Canary"

#: Name of the *comunidad autónoma* :data:`CANARY_TIME_ZONE` applies to, as both
#: exports spell it.
CANARY_COMUNIDAD = "CANARIAS"

#: INE province codes of the Canary Islands — Las Palmas and Santa Cruz de
#: Tenerife — which is how a Canarian fire is recognised for
#: :data:`CANARY_TIME_ZONE`.
#:
#: The province rather than the *comunidad*, because the province code is the one
#: identifier both exports agree on and neither can garble: it is characters 5-6
#: of ``numeroparte`` and equals ``idprovincia`` on all 29,926 fires checked. The
#: XML's ``idcomunidad`` is **not** the INE autonomous-community code — EGIF
#: numbers them its own way, with Cataluña as ``2`` — so reading Canarias off it
#: would need a second undocumented catalogue to be right.
CANARY_PROVINCE_INE_CODES = ("35", "38")

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
