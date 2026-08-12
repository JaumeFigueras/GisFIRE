#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAFOR — *Comisión Nacional Forestal*, Mexico.

Data model for the Mexican national burnt-area cartography, *Incendios
Forestales*, published by CONAFOR as **one zipped shapefile per year**. GisFIRE's
first Latin American source, and the third national perimeter dataset after
:mod:`src.providers.portugal_icnf` and :mod:`src.providers.canada_nbac`.

Unlike the Greek and Spanish statistics, this is a *cartography*: every record is
a polygon. Unlike ICNF and NBAC, the polygon is published in **EPSG:4326**
already, so there is no national grid to keep alongside it and
:class:`~src.providers.mexico_conafor.wildfire.ConaforWildfire` stores no
geometry of its own — the generic
:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the whole of it.

Fourteen files, fourteen years, 45,914 polygons
-----------------------------------------------

============  =========  ============  =========
Layer         Features   Layer         Features
============  =========  ============  =========
2010                311  2018              3,416
2011                343  2019              4,265
2012                224  2020              5,778
2013                552  2021              7,272
2014                628  2022              6,718
2015              1,105  2023              7,513
2016              3,244
2017              4,545
============  =========  ============  =========

The count steps up by an order of magnitude at 2016 — 628 polygons in 2014, 1,105
in 2015, 3,244 in 2016 — which is a change in *what was mapped*, not in what
burnt. Before 2016 CONAFOR published only the fires it had drawn; from 2016 it
publishes the whole season.

Every layer is EPSG:4326 (identical ``.prj`` in all fourteen archives) and every
one declares ``UTF-8`` in its ``.cpg``.

The attributes change every single year
----------------------------------------

This is the difficulty of the source. Fifty-eight distinct attribute names appear
across fourteen files and **no two consecutive years have the same schema**. The
same field is written five ways — ``TIPVEG``, ``TIPVEGE``, ``TIP_VEG``,
``TIPO_DE_VE`` and, in 2012, nothing at all.

Two layers are wholly their own. **2012** uses ``CLAVE`` for the key and
``TOTAL`` for the area, and adds ``PARAJE``, ``TIP_PRO``, ``HR_LIQ`` and
``RELEVANTE`` that no other year has and that are the string ``"0"`` in all 224
of its rows. **2015** renames almost everything — ``CLAVE_DEL`` for the key,
``TIPO_DE_IN``, ``TIPO_DE_VE``, ``TIPO_DE_IM``, ``ANP_HECTAR``, and
``ARBADULTO`` / ``RENUEVO`` / ``ARBUSTIVO`` / ``HERBACEO`` / ``SUELOORG`` for
five of the six strata — and it is the layer that makes the *order* of
:data:`FIELD_ALIASES` matter rather than merely tidy. See the warning there.

:data:`FIELD_ALIASES` is the whole of the mapping: one model attribute, every
published spelling of it, in the order they should be tried. An importer reads
through :func:`field_value` and never touches a published name directly.

What survives the variation, and what does not:

``CLAVEINC`` / ``CLAVE_DEL`` / ``CLAVE``
    In all fourteen files, and the only usable identifier. See below. The key is
    the one thing every layer publishes and the one thing every layer spells
    differently enough to break a naive reader: 2015's ``CLAVE_DEL`` is *clave
    del incendio* cut off at the shapefile's ten-character field-name limit.
``MUNICIPIO``, ``CAUSA``, ``FECHAINIC``, ``FECHALIQ``, ``AREA_HA``
    In all fourteen too (``AREA_HA`` as ``TOTAL`` in 2012). Published for every
    fire but **one**: ``21-24-0078`` leaves the area empty and fills in everything
    else, polygon included.
The state name
    In all fourteen, but not always under that name and not always a name — see
    the warning on :data:`FIELD_ALIASES`.
``CAUSAESP``
    2010, 2012-2015 and 2016-2019 — 18,290 rows. Gone from 2020 on.
``TIPVEG``, ``TIPOINC``, ``TIPIMPAC``, ``ANP``
    All fourteen except 2012, which publishes none of them.
The six burnt-area strata
    2010-2021, and only five of them from 2020 (``SUELORG_HA`` is dropped).
    **Gone entirely in 2022 and 2023**, 14,231 rows with a total and no split.
``CLAVEMUN``
    2018 on. ``CLAVEEDO`` in 2016-2017 only, and the numeric ``ESTADO`` of 2015,
    both redundant with the key — see below.
``POLIGONO``
    2023 only, and the single most useful thing in the dataset: it says how each
    polygon was drawn. See :data:`PERIMETER_SOURCES`.

``ID`` is a row number, not an identifier
------------------------------------------

It is present in all fourteen files — as ``OBJECTID`` in 2015 — and it is
worthless: 1 to *n* within the file up to 2020, and from 2021 restarting **per
state**, so 2021's 7,272 features carry 1,965 distinct values. 2015's runs to
1,074 and up on a layer of 1,105 rows, so it is not even file-local. It is not
imported.

``CLAVEINC`` is, and it carries the state code
-----------------------------------------------

The published key is ``YY-EE-NNNN`` — two digits of year, two of *entidad
federativa*, four of sequence within that state and year — and it holds that
shape in **all 45,914 rows** of all fourteen files. The middle pair is the INEGI
state code, and it agrees with the published state name in every row but one,
which is what makes it worth parsing rather than trusting the name: the names are
spelled 34 ways for 32 states, and 2015's ``ESTADO_1`` says *Distrito Federal*
for ``15-17-0054``, whose key and whose ``ESTADO_DE`` both say Morelos.

The year prefix is two digits, so the key is unique across this series but would
collide with 1910-1923 or 2110-2123. Nothing in the archive reaches either.

``CLAVEINC`` is **unique after de-duplication**: 45,909 distinct values in 45,914
rows. The five repeats are all in 2021 and all *exact* duplicate features —
identical attributes and byte-identical geometry — except that the second copy of
the four Guerrero ones (``21-12-0195`` … ``21-12-0198``) has its two date fields
blanked. Dropping the second copy loses nothing, which is why
:attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.fire_code` can
carry a ``UNIQUE`` constraint.

Two administrative codes, only one of them national
----------------------------------------------------

:attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.state_code` comes
from the key and is INEGI's national state code, 1 to 32.

``CLAVEMUN`` is **not** a national municipality code. Its values run 1 to 570 —
570 being exactly the number of municipalities in Oaxaca — so it is the
municipality's number *within its state* and means nothing without the state
beside it. The national INEGI key is the two composed::

    LPAD(state_code::text, 2, '0') || LPAD(municipality_code::text, 3, '0')

which is what a join to an INEGI boundary layer needs. It is published from 2018
on; the 13,872 fires before that have a municipality name and no code, and one
2020 row publishes ``0``.

``CLAVEEDO`` (2016-2017) is the state code again, written as a float in 2016
(``1.000000000000000``) and as a zero-padded string in 2017 (``"01"``); 2015's
numeric ``ESTADO`` is the same thing a third way. All three are redundant with
the key — they agree with it in every row of every layer — and none is imported.

Dates: a day, never a time, in four formats
--------------------------------------------

``FECHAINIC`` and ``FECHALIQ`` are the day the fire started and the day it was
*liquidado* — declared out. **No year publishes a time of day**, so every stored
instant is local midnight and
:attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.date_time_precision`
is :data:`PRECISION_DAY` for every row imported today. See
:class:`~src.data_model.wildfire.Wildfire` for the instant-plus-zone rule.

The written format changes by year and, in 2022, *within* the year:

``YYYY/MM/DD``
    2010, 2013, 2014, 2015, 2016, 2017 and 2020.
``YYYY-MM-DD``
    2011, 2012, 2018, 2019, 2021 and 2023.
All four at once
    2022 — 3,336 rows ISO, 2,304 ``DD/MM/YYYY``, 886 ``DD-MM-YYYY`` and 192
    ``YYYY/MM/DD``.

The day-first forms are unambiguously day-first — the first component reaches 31
and the second stops at 12 — so :data:`DATE_FORMATS` puts ``%d/%m/%Y`` ahead of
any month-first reading and :func:`parse_date` walks the tuple in order.

Four rows in 45,914 defeat it, and they are worth knowing by name because they
are what the nullable end date and the precision column exist for:

``21-19-0051``
    ``FECHALIQ = '22/12/202'``, a truncated year.
``21-21-0082``
    ``FECHALIQ = '22/20/2021'``, month 20.
``22-29-0003``
    both fields ``'01/15/2022'``: the one month-first date in the archive,
    recovered by the last entry of :data:`DATE_FORMATS`.
``21-12-0195`` … ``21-12-0198``
    both fields empty — the duplicate features above, which the import drops.

Dates otherwise hold up well. 1.27 days is the mean duration, 13 days the 99th
percentile, and only two fires in the archive run past a year. Sixteen rows have
an end before their start and nine have a start in the wrong calendar year
(five 2016 dates in the 2017 layer, and so on) — those are the provider's, and
are stored as published.

Areas: measured from the polygon, except in 2010
-------------------------------------------------

``AREA_HA`` is not an independent field observation. Compared against the
geodesic area of the polygon it sits on, the median ratio is **1.000** from 2016
onwards and within 1% for four rows in five — it *is* the polygon's area, to the
precision the file prints.

**2010 is the exception and its areas must not be used.** The median ratio there
is 3.0 and the 90th percentile is 65: ``10-01-0001`` reports 20 ha on a polygon
of 1.08 ha, ``10-01-0004`` reports 2.5 ha on 20.2 ha. The 2010 polygons are
sketches of five to twelve vertices drawn beside a separately reported area, and
neither number can be derived from the other. 2011-2014 agree to within a few
percent; 2016 on are exact.

Where the six strata are published they sum to the total almost perfectly —
44,215 of the 44,222 rows that have both agree to within 1%, most of them
exactly. That holds in 2020-2021 too, where ``SUELORG_HA`` is gone and five
columns still add up, which says the organic-soil hectares were folded in rather
than lost.

Vocabularies: free text that nobody normalised
-----------------------------------------------

``CAUSA``, ``CAUSAESP``, ``TIPVEG``, ``TIPOINC`` and ``TIPIMPAC`` are typed
strings with no code beside them and no controlled list behind them. Over
fourteen years they drift:

=============  =====  ==================================================
``CAUSA``         64  ``'Fogatas'``, ``'fogatas'``, ``'Fogata'``,
                      ``'Fogatas\\n'``, ``'Fogatas De Paseantes'``
``CAUSAESP``      54  and 179 distinct ``(CAUSA, CAUSAESP)`` pairs
``TIPVEG``       156  including 50 that append the INEGI code —
                      ``'Bosque de Pino-Encino - BPQ'``
``TIPOINC``       10  four spellings of *superficial*
``TIPIMPAC``      14  ``'Impacto Minimo'``, ``'Impacto minimo'``,
                      ``'Minimo'``, ``'Impacto MÃ­nimo\\n'``
=============  =====  ==================================================

Case- and accent-folding (:func:`normalise`) takes ``CAUSA`` from 64 to 43 and
``TIPIMPAC`` from 14 to 8; the rest is genuine synonymy that only a table can
resolve. That table is
:class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause`, and the
argument for it being a table is in that module.

.. warning::

   **Some of the text is mojibake in the published file**, not in the reader. The
   archives declare UTF-8 and decode cleanly as UTF-8; what comes out is already
   corrupt in a handful of rows, and doubly so in 2021 and 2022 —
   ``'BolaÃƒÂ±os'`` for *Bolaños*, ``'CaÃƒÆ’Ã‚Â±ada Verde'`` for *Cañada Verde*.
   The same names are written correctly in the same column in other years. There
   is no encoding that reads these files right; the damage predates publication.

   2019 and 2022 also carry a find-and-replace accident in ``TIPVEG``, where the
   letter *i* was substituted with the word *bosque*:
   ``'Bosque de Pbosqueno Encbosqueno'`` is *Bosque de Pino Encino*, and
   ``'matorral desertbosqueco rosetofbosquelo'`` is *Matorral Desértico
   Rosetófilo*. Nine rows.

   Nothing here repairs any of it. The strings are stored as published and the
   normalised forms on
   :class:`~src.providers.mexico_conafor.fire_cause.ConaforFireCause` are what a
   query groups by.

Geometry
--------

Polygons, 6,661 of them multipart, so the storage type is ``MULTIPOLYGON`` as
everywhere else in the project. 145 are invalid as published — self-intersecting
rings, 45 of them in 2017 alone, none at all in 2015 — and go through
``ST_MakeValid`` before storing.
Nine features in 2012 have **no geometry at all**; they carry attributes and an
empty shape, which is why
:attr:`~src.data_model.wildfire.Wildfire.perimeter` stays nullable for this
provider as for every other.

Vertex counts run to 154,977 on a single ring (a 2021 fire in Oaxaca), so nothing
here should be read into memory a whole year at a time.

There is no ignition point
---------------------------

CONAFOR publishes a perimeter and a *predio* — the estate or landholding the fire
was on — and no coordinate for where it started. There is therefore no
:class:`~src.data_model.ignition.Ignition` for a CONAFOR fire, for exactly the
reason there is none for an ICNF one: there is no point to put in it.

The statistics CSVs are not imported
-------------------------------------

Two CSV files sit beside the shapefiles in the published directory —
``2025_Incendios_forestales.csv`` and
``estadisticasincendiosforestales2015-2024.csv``. They are CONAFOR's tabular
statistic, a different product with no geometry, and they are deliberately out of
scope for this model: mixing a statistic into a cartography is not what this
provider is. Note in passing that the first covers 2025, which the cartography
does not reach — a gap to close by importing a 2025 archive when CONAFOR
publishes one, not by importing a different product.
"""

from __future__ import annotations

import datetime
import re
import unicodedata

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: CONAFOR wildfire hangs off. The product names the published layer family
#: rather than the agency: CONAFOR publishes a great deal else on the same portal
#: — the statistics CSVs above among it — and each would be its own provider row.
PROVIDER_NAME = "CONAFOR"
PROVIDER_FULL_NAME = "Comisión Nacional Forestal"
PROVIDER_PRODUCT = "Incendios Forestales"
PROVIDER_URL = "https://datos.gob.mx/busca/organization/conafor"

#: The CRS every layer is published in: plain WGS 84 longitude and latitude.
#:
#: All fourteen archives carry a byte-identical ``.prj``. Mexico's own grids —
#: ITRF2008 / UTM zones 11N to 16N, and the ITRF92 Mexico LCC (EPSG:6362) — appear
#: nowhere in the published data, which is why
#: :class:`~src.providers.mexico_conafor.wildfire.ConaforWildfire` stores no
#: second geometry the way ICNF, DARPA, REDIAM and NBAC do. There is nothing to
#: keep: the published polygon *is* the EPSG:4326 one.
SOURCE_SRID = 4326

#: Character set of the published shapefiles, as declared by their ``.cpg``.
#:
#: Unlike the ICNF archives this one does not have to be forced — GDAL reads the
#: ``.cpg`` and gets it right. It is stated here because getting it right is not
#: enough: see the mojibake warning in the module docstring.
SOURCE_ENCODING = "UTF-8"

#: Zone the published dates are resolved against when nothing better is available.
#:
#: A fallback and not a rule, and a weaker one than Portugal's or Greece's:
#: Mexico spans four zones (``America/Mexico_City``, ``America/Chihuahua``,
#: ``America/Mazatlan``, ``America/Tijuana``, plus ``America/Hermosillo`` and
#: ``America/Cancun``), so a national default is wrong by one to three hours for
#: the northern and Pacific states. Every polygon has a geometry, so the importer
#: resolves the zone spatially against
#: :class:`~src.data_model.geography.time_zone.TimeZone` like every other
#: importer; this is only what it uses when no zone areas have been imported.
#:
#: The 2022 abolition of daylight saving outside the northern border strip is
#: another reason to store the zone *name* rather than an offset — see
#: :class:`~src.data_model.wildfire.Wildfire`.
DEFAULT_TIME_ZONE = "America/Mexico_City"

#: The fire's start date could not be read at all, so
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the 1st of January
#: of :attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.year` at local
#: midnight and means "some time in this year".
#:
#: No row in the archive as published today needs it: the only four with an empty
#: ``FECHAINIC`` are the duplicate features the import drops, and the one
#: month-first date is recovered by :data:`DATE_FORMATS`. The value exists so that
#: the next release can be loaded without a migration, and so that
#: :attr:`~src.data_model.wildfire.Wildfire.start_date_time` can stay ``NOT NULL``
#: honestly.
PRECISION_YEAR = "year"

#: The fire was dated but not timed, which is every CONAFOR row. No layer of any
#: year publishes a time of day, so the stored instants are local midnight on the
#: right day. The date is the provider's; the time of day is not.
PRECISION_DAY = "day"

#: Every value
#: :attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.date_time_precision`
#: may take, in increasing order of precision.
DATE_TIME_PRECISIONS = (PRECISION_YEAR, PRECISION_DAY)

#: The date formats ``FECHAINIC`` and ``FECHALIQ`` are written in, **in the order
#: they must be tried**.
#:
#: The order is the point. The day-first forms are unambiguously day-first in this
#: archive — their first component reaches 31 and their second stops at 12 — so
#: reading ``12/05/2022`` as December 5th would be wrong. Putting ``%d/%m/%Y``
#: before any month-first reading makes that impossible.
#:
#: ``%m/%d/%Y`` is last and is a deliberate last resort. It fires on exactly one
#: row of the archive, ``22-29-0003``'s ``01/15/2022``, which no day-first format
#: can read because 15 is not a month — and which the month-first reading resolves
#: to the 15th of January with no ambiguity at all, since a day-first reading of
#: it does not exist. Anything a day-first format *can* read never reaches it.
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")

#: Shape of the published key, ``YY-EE-NNNN``. See the module docstring.
FIRE_CODE_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")

#: Strings the archives write where they mean *nothing here*.
#:
#: There is no single one: ``ANP`` is ``'0'`` in 14,332 rows and ``'N/A'`` in
#: 16,832, ``TIPIMPAC`` is ``'Sin dato'`` in the 654 rows of 2010-2011, and 2011
#: writes ``'0'`` into ``TIPOINC``, ``TIPVEGE`` and ``CAUSA`` alike. All of them
#: mean ``NULL`` and none of them is a value. Compared through
#: :func:`is_missing`, which folds case and accents first.
MISSING_VALUES = frozenset({"", "0", "n/a", "n/d", "no", "ninguna", "sin dato", "no aplica",
                            "ninguna / no aplica", "sin anp", "desconocido"})

#: How the 2023 layer says each polygon was produced — ``POLIGONO``, published in
#: that year and no other.
#:
#: ``IMAGEN`` (5,157 rows) is a perimeter digitised from a satellite image,
#: ``COORD`` (1,893) one walked or flown as GPS coordinates, and ``AQSPPIF`` (309)
#: one taken from the agency's own *Adquisición de Servicios* aerial product. 154
#: rows say nothing.
#:
#: Not a ``CHECK`` on the column, on the same argument as the Greek incident
#: categories: this is one year of one file observed once, and a constraint built
#: from it would reject the first source CONAFOR adds.
PERIMETER_SOURCE_IMAGE = "IMAGEN"
PERIMETER_SOURCE_COORDINATES = "COORD"
PERIMETER_SOURCE_AERIAL = "AQSPPIF"
PERIMETER_SOURCES = (PERIMETER_SOURCE_IMAGE, PERIMETER_SOURCE_COORDINATES,
                     PERIMETER_SOURCE_AERIAL)

#: Years the cartography is published for: 2010 to 2023, complete.
PUBLISHED_YEARS = (2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019,
                   2020, 2021, 2022, 2023)

#: The first year whose ``AREA_HA`` may be trusted against the polygon it sits on.
#:
#: From 2016 the published area is the polygon's own area to three decimal places;
#: 2011-2014 agree to a few percent; **2010 does not agree at all** and its areas
#: and polygons are two unrelated measurements of the same fire. See the module
#: docstring.
FIRST_YEAR_WITH_MEASURED_AREA = 2016

#: The last year that publishes the burnt area split by stratum. 2022 and 2023
#: publish ``AREA_HA`` and nothing else, so 14,231 rows have a total with no
#: breakdown; 2020-2021 publish five of the six, ``SUELORG_HA`` having gone.
LAST_YEAR_WITH_AREA_STRATA = 2021

#: The first year that publishes ``CLAVEMUN``. Before it, a fire has a
#: municipality name and no code — 12,767 rows.
FIRST_YEAR_WITH_MUNICIPALITY_CODE = 2018

#: Every published spelling of every attribute this model reads, keyed by the
#: model attribute, **in the order they should be tried**.
#:
#: This is the whole of the year-to-year mapping and the reason nothing downstream
#: branches on the year. Fifty-eight distinct names appear across the fourteen
#: files and no two consecutive years agree; an importer resolves a value through
#: :func:`field_value` and a layer that publishes less simply leaves more of the
#: row ``NULL``.
#:
#: .. warning::
#:
#:    **Order matters, because one published name is reused for a different
#:    thing.** In the 2015 layer ``ESTADO`` is a ``Real`` holding the numeric
#:    INEGI state code (``32.0``), and the state *name* is in ``ESTADO_1`` — with
#:    a third field, ``ESTADO_DE``, holding the formal name (*Veracruz de Ignacio
#:    de la Llave* against *Veracruz*). In the other thirteen layers ``ESTADO`` is
#:    the name.
#:
#:    So ``state_name`` lists ``ESTADO_1`` and ``ESTADO_DE`` **before** ``ESTADO``:
#:    the first alias a layer actually has wins, which gives 2015 the name and
#:    every other year the same name it always had. Reversing those three entries
#:    would silently store ``"32"`` as the name of a Mexican state for 1,105 fires.
#:
#: Everywhere else the aliases name the same thing wherever they appear, and the
#: tuples are ordered most-common-spelling-first.
FIELD_ALIASES = {
    "fire_code": ("CLAVEINC", "CLAVE_DEL", "CLAVE"),
    # ``ESTADO_1`` and ``ESTADO_DE`` come first because of 2015, where ``ESTADO``
    # is a **number** — see the warning below. ``ESTADO_1`` before ``ESTADO_DE``
    # because it holds the short common name the other thirteen layers publish
    # (``Veracruz``, not ``Veracruz de Ignacio de la Llave``).
    "state_name": ("ESTADO_1", "ESTADO_DE", "ESTADO"),
    "municipality_code": ("CLAVEMUN",),
    "municipality_name": ("MUNICIPIO",),
    "property_name": ("PREDIO", "PREDIO_O_P"),
    "cause": ("CAUSA",),
    "specific_cause": ("CAUSAESP", "CAUSA_ESPE"),
    "start_date": ("FECHAINIC",),
    "end_date": ("FECHALIQ",),
    "fire_type": ("TIPOINC", "TIPO_INC", "TIPO_DE_IN"),
    "vegetation_type": ("TIPVEG", "TIP_VEG", "TIPVEGE", "TIPO_DE_VE"),
    "impact_level": ("TIPIMPAC", "TIPO_DE_IM"),
    "protected_area_name": ("ANP",),
    "area_ha_protected": ("ANP_HA", "SUPAFECANP", "ANP_HECTAR"),
    "area_ha": ("AREA_HA", "TOTAL"),
    "area_ha_tree": ("ARBOR_HA", "ARB_ADUL", "ARBADULTO"),
    "area_ha_regeneration": ("RENUEV_HA", "RENUEV", "RENUEVO"),
    "area_ha_shrub": ("ARBUSTI_HA", "ARBUST", "ARBUSTIVO"),
    "area_ha_herbaceous": ("HERBAC_HA", "PASTO", "HERBACEO"),
    "area_ha_litter": ("HOJAR_HA", "HOJARASCA"),
    "area_ha_organic_soil": ("SUELORG_HA", "SUELO_ORG_", "SUELO_ORG", "SUELOORG"),
    "perimeter_source": ("POLIGONO",),
}

#: Every INEGI vegetation code that appears in the published ``TIPVEG`` values.
#:
#: 5,366 of the 45,914 rows write the code after the name —
#: ``'Bosque de Pino-Encino - BPQ'``, ``'Selva Baja Caducifolia - SBC'`` — almost
#: all of them in 2015 and 2019, and the mapping is consistent wherever it
#: appears: these 50 codes, each on exactly one name.
#:
#: Eight of them appear in the 2015 layer and nowhere else — ``BG`` (*Bosque de
#: Galería*), ``MJ``, ``MK``, ``MKE``, ``MSCC``, ``MSN``, ``PT`` (*Petén*) and
#: ``VM`` (*Manglar*) — which is what a fixed set costs: a layer arriving with a
#: code that is not in it stores no code until it is added. That is the same
#: trade :mod:`src.providers.portugal_icnf` makes for an untranslated cause, and
#: the alternative — believing any two-to-four-letter word after a dash — is what
#: turns the *Pino* of ``'Bosque de Encino - Pino'`` into a code.
#:
#: A fixed set rather than "whatever follows the dash", because what follows the
#: dash is not always a code. Twenty-two rows spell the *encino-pino* mixture as
#: ``'Bosque de Encino - Pino'``, where *Pino* is the other half of the name. A
#: pattern alone would read it as the code ``PINO``; membership of this set is
#: what tells the two apart. A code CONAFOR adds later is not in here and is
#: stored as ``None`` until it is — which is the same choice
#: :mod:`src.providers.portugal_icnf` makes for an untranslated cause.
VEGETATION_CODES = frozenset({
    "BA", "BB", "BC", "BG", "BI", "BJ", "BM", "BP", "BPQ", "BQ", "BQP",
    "MC", "MDM", "MDR", "MJ", "MK", "MKE", "MKX", "ML", "MRC", "MSC",
    "MSCC", "MSM", "MSN", "MST", "PH", "PN", "PT", "SAP", "SBC", "SBK",
    "SBP", "SBQ", "SBS", "SMC", "SMP", "SMQ", "SMS", "VA", "VG", "VH",
    "VHH", "VM", "VPI", "VPN", "VS", "VSI", "VT", "VU", "VW",
})

#: How a ``TIPVEG`` value writes the code, when it writes one. Matched against
#: :data:`VEGETATION_CODES` before being believed — see
#: :func:`split_vegetation_type`.
_VEGETATION_CODE_PATTERN = re.compile(r"^(?P<name>.+?)\s+-\s+(?P<code>[A-Za-z]{2,4})$")


def normalise(value: str | None) -> str:
    """Fold a published string to the form the vocabularies are compared on.

    Strips, collapses internal whitespace (the published values include trailing
    newlines — ``'Fogatas\\n'``, ``'Desconocidas\\n'``), lower-cases and removes
    accents. ``'Impacto Minimo'``, ``'impacto minimo'``, ``'Impacto Mínimo'`` and
    ``'Impacto Minimo\\n'`` all come back as ``'impacto minimo'``.

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
    This gets ``CAUSA`` from 64 spellings to 43 and ``TIPIMPAC`` from 13 to 7. It
    does **not** finish the job — ``'Fogatas'`` and ``'Fogata'`` are still two —
    and it is not meant to: what is left is synonymy, which needs the table in
    :mod:`src.providers.mexico_conafor.fire_cause` rather than a string function.

    It does not repair the mojibake either. ``'BolaÃƒÂ±os'`` folds to
    ``'bolaãƒâ±os'`` and stays distinct from ``'bolanos'``, which is correct: the
    two are different strings in the published file and pretending otherwise would
    be a guess.
    """
    if value is None:
        return ""
    folded = unicodedata.normalize("NFD", str(value).strip().lower())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


def is_missing(value: str | None) -> bool:
    """Whether a published value means *nothing here* rather than a value.

    Tests the :func:`normalise` d string against :data:`MISSING_VALUES`. The
    archives have no single null token — ``'0'``, ``'N/A'``, ``'Sin dato'``,
    ``'Ninguna / No aplica'`` and the empty string all appear, sometimes in the
    same column in different years — and every one of them has to become ``NULL``
    rather than be stored as text that looks like data.

    Parameters
    ----------
    value : str or None
        A published attribute value, as read.

    Returns
    -------
    bool
        ``True`` when the value should be stored as ``NULL``.

    Notes
    -----
    Deliberately not applied to :attr:`ConaforWildfire.fire_code
    <src.providers.mexico_conafor.wildfire.ConaforWildfire.fire_code>` or to any
    numeric column. ``'0'`` is a legitimate reading of ``ANP_HA`` — the fire
    touched no protected area — and turning it into ``NULL`` would confuse *no
    protected area* with *not measured*.
    """
    return normalise(value) in MISSING_VALUES


def field_value(row: dict, attribute: str) -> str | None:
    """Read one model attribute out of a published feature, whatever the year.

    Walks :data:`FIELD_ALIASES` for ``attribute`` and returns the first alias the
    row actually has. A layer that does not publish the attribute at all — 2012
    has no ``TIPVEG`` in any spelling, 2022 and 2023 have none of the six strata —
    yields ``None``.

    Parameters
    ----------
    row : dict
        One feature's attributes, keyed by published field name.
    attribute : str
        A key of :data:`FIELD_ALIASES`.

    Returns
    -------
    str or None
        The published value, unmodified, or ``None`` if this layer has no field
        for it.

    Raises
    ------
    KeyError
        If ``attribute`` is not in :data:`FIELD_ALIASES`, which is a typo rather
        than a missing field and should not be swallowed.

    Notes
    -----
    A present-but-empty field returns its empty value rather than ``None``, so
    that *this layer does not publish it* and *this row leaves it blank* stay
    distinguishable. Deciding what an empty value means is :func:`is_missing`'s
    job, not this one's.
    """
    for name in FIELD_ALIASES[attribute]:
        if name in row:
            return row[name]
    return None


def parse_fire_code(fire_code: str | None) -> tuple[int, int, int] | None:
    """Split a published ``CLAVEINC`` into its year, state and sequence.

    Parameters
    ----------
    fire_code : str or None
        The published key, ``YY-EE-NNNN``.

    Returns
    -------
    tuple of (int, int, int) or None
        Two-digit year, INEGI state code and sequence number, or ``None`` if the
        string is not of that shape.

    Notes
    -----
    The two-digit year is returned as published — 10 for 2010 — because that is
    what the key says. Widening it to a calendar year is the caller's decision and
    needs a century the key does not carry; the importer takes the year from the
    layer it is reading instead, which cannot be wrong.

    All 45,914 rows of all fourteen layers match, and in all but one of them the
    state code agrees with the published state name. That is what makes this
    parse worth doing rather than trusting the name, which is spelled 34 ways for
    32 states — *Distrito Federal* and *Ciudad de México* being the same state
    before and after 2016, and *México* and *Estado de México* the same one
    throughout — and which is simply wrong for ``15-17-0054``, filed under
    *Distrito Federal* in a layer whose own key and formal-name column both say
    Morelos.
    """
    if fire_code is None:
        return None
    match = FIRE_CODE_PATTERN.match(fire_code.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_date(value: str | None) -> datetime.date | None:
    """Read a published ``FECHAINIC`` / ``FECHALIQ`` in whichever format it is in.

    Tries :data:`DATE_FORMATS` in order and returns the first that parses.

    Parameters
    ----------
    value : str or None
        The published date, as read.

    Returns
    -------
    datetime.date or None
        The date, or ``None`` for an empty or unreadable value.

    Notes
    -----
    Returns a :class:`datetime.date` and not a datetime, because a date is all
    the archive has: no layer of any year publishes a time of day. Turning it into
    the instant GisFIRE stores — local midnight against the zone the polygon falls
    in — is the importer's job, and the row records that it did so through
    :attr:`ConaforWildfire.date_time_precision
    <src.providers.mexico_conafor.wildfire.ConaforWildfire.date_time_precision>`.

    Three published values in the whole archive return ``None``: ``'22/12/202'``
    (a year of three digits), ``'22/20/2021'`` (month 20) and the empty strings of
    the four duplicate 2021 features. All three are end dates on rows whose start
    date reads fine, except the empty ones, which are on rows the import drops.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def split_vegetation_type(value: str | None) -> tuple[str | None, str | None]:
    """Separate a ``TIPVEG`` value from the INEGI code some years append to it.

    Parameters
    ----------
    value : str or None
        The published vegetation type, as read.

    Returns
    -------
    tuple of (str or None, str or None)
        The value as published — code and all — and the upper-cased code alone
        where there is one. ``(None, None)`` for a missing value.

    Examples
    --------
    >>> split_vegetation_type("Bosque de Pino-Encino - BPQ")
    ('Bosque de Pino-Encino - BPQ', 'BPQ')
    >>> split_vegetation_type("Bosque de Pino-Encino")
    ('Bosque de Pino-Encino', None)
    >>> split_vegetation_type("0")
    (None, None)

    Notes
    -----
    The name is returned **whole**, with the suffix still on it, and the code is
    returned *beside* it rather than instead of any part of it. Stripping the
    suffix would make the stored string differ from the published one for 4,290
    rows, and the project's rule everywhere else is that a provider's text is kept
    byte for byte and any derived form is added next to it.

    A trailing word is only believed to be a code if it is in
    :data:`VEGETATION_CODES`. ``'Bosque de Encino - Pino'`` matches the pattern
    perfectly — *Pino* is four letters, like ``BPQ`` is three — and is not a code
    at all but the second half of the name, as twenty-two rows spell that mixture.
    Nothing in the string distinguishes the two cases, so the fixed set does.
    """
    if value is None or is_missing(value):
        return None, None
    text = value.strip()
    match = _VEGETATION_CODE_PATTERN.match(text)
    if match is None:
        return text, None
    code = match.group("code").upper()
    return text, code if code in VEGETATION_CODES else None
