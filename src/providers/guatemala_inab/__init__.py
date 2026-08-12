#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INAB — *Instituto Nacional de Bosques*, Guatemala.

Data model for the Guatemalan fire reports, *Monitoreo de Incendios Forestales*,
published by INAB through the ArcGIS REST server of the *Sistema Integral de
Información para la Gestión del Fuego*. Fetched by
:mod:`src.apps.download.wildfires.guatemala_inab.download_wildfires`, there being
no file to download and no WFS to read.

GisFIRE's first Central American source, and the first from any provider that
publishes **neither a perimeter nor a burnt area**.

One row is a report, not a fire and not an area
------------------------------------------------

``datos_generales`` is the log of fires phoned in to INAB: who called it in, from
where, by what means, and what became of the report. 4,615 records over
2023-01-18 to 2026-08-06 — 187 in 2023, 727 in 2024, 1,789 in 2025 and 1,908 in
2026 to the 6th of August.

Two things follow from *report* rather than *fire*, and both matter:

**There is no size of any kind.** Not a perimeter, not a hectare figure, not a
land-cover split — nothing in the thirty-three published attributes says how big
the fire was. :mod:`src.providers.spain_egif` and
:mod:`src.providers.greece_ffa` publish no perimeter but do publish burnt areas;
this publishes neither. Anything measuring burnt area in Guatemala has to go
somewhere else, and the burn-scar layers on the same server are one season of
polygons rather than an archive.

**One fire can be reported twice.** 57 pairs of records share an exact
coordinate and an exact minute, differing only in which institution called it in:

.. code-block:: text

   same point, same minute, locality "La Nueva"
     particular / no_verificado
     otra       / cierre_operaciones

So :attr:`~src.providers.guatemala_inab.wildfire.InabWildfire.global_id` is
unique because a *report* is unique, and a count of these rows is a count of
reports. Deduplicating them is an analysis, not an import: the two rows disagree
about the outcome, and choosing between them is a judgement this model has no
basis for making.

What is worth reading before using it
--------------------------------------

The times are real
    ``fecha_hora_incendio`` is the minute the report was received, and it behaves
    like a real observation: in local time the hourly histogram peaks between
    13:00 and 16:00, which is the afternoon fire peak. It is not a date rounded to
    midnight, unlike much of :mod:`src.providers.portugal_icnf`.

The geometry is the location; the typed coordinates are not
    Every record carries a point, and it is the answer. The form's own
    ``coordenada_x``/``coordenada_y`` are filled on 440 records and are not
    trustworthy — see :class:`~src.providers.guatemala_inab.ignition.InabIgnition`.

140 records are false alarms
    ``estado_aviso`` is ``falso`` on 140 of the 4,615, and ``no_verificado`` on a
    further 90. They are imported, because a record saying *this was not a fire*
    can be filtered and a discarded one cannot be recovered — the same call
    :mod:`src.providers.greece_ffa` makes for ``ΨΕΥΔΗΣ ΑΝΑΓΓΕΛΙΑ``. Anything
    counting fires must exclude them; see :func:`is_false_alarm`.

Three points are not in Guatemala
    And all three are already ``falso``. Two are **sign-flipped longitudes**
    (``+90.47`` for ``-90.47``, in Cambodia) and the third is 200 km inside
    Honduras. The provider's own quality flag catches every one, which is a better
    argument for keeping ``estado_aviso`` than any amount of coordinate checking.

The classification is mostly absent
    ``tipo_incendio`` — inside or outside forest — is filled on **489 records,
    10.6%**. It is the only thing resembling a fire type in the dataset.

No personal data is imported
    The published layer carries the **name and telephone number of whoever
    reported each fire**: 1,786 distinct names, 1,008 numbers, 1,969 distinct
    pairs, most of them private individuals rather than officials. It also carries
    the INAB user accounts that created and last edited each record.

    **None of it is imported.** :data:`PERSONAL_FIELDS` names the four columns the
    import must never read. Nothing analytical is lost — no question about fire is
    answered by a reporter's phone number — and a research database that can be
    copied, backed up and shared should not carry the contact details of a
    Guatemalan farmer who rang in a fire. :attr:`InabWildfire.institution
    <src.providers.guatemala_inab.wildfire.InabWildfire.institution>` keeps *which
    organisation* reported it, which is the part that has analytical meaning.

The end times are in another layer
    ``informes`` on the same service — 5,812 rows — holds when the first crews
    arrived and when the fire was controlled and extinguished. It is not modelled
    here, so :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL``
    on every INAB fire. That is the only end-time data Guatemala publishes, and
    adding it is a second model rather than a column.

The published vocabularies
---------------------------

Five closed lists, all lower-case slugs, all published cleanly — there is none of
the spelling drift that :mod:`src.providers.mexico_conafor` has to reconcile:

``estado_aviso``
    5 values — see :data:`REPORT_STATUSES`.
``forma_comunicacion``
    5 values — see :data:`REPORT_CHANNELS`.
``tipo_incendio``
    2 values — see :data:`FIRE_LOCATIONS`.
``institucion``
    14 values, led by ``conred`` (2,066) and ``conap`` (756).
``departamento``
    22 values — every department of Guatemala, see :data:`DEPARTMENT_CODES`.

They are **not** given check constraints, on the argument
:mod:`src.providers.greece_ffa` sets out: this is one publication observed once,
and a constraint built from it would reject the first value INAB adds.

.. warning::

   **An unfilled text field is sometimes ``null`` and sometimes ``""``, in the
   same column.** The two are mixed with no pattern:

   .. code-block:: text

                          null   ""     filled
      nombre_ap_1           80   3,080   1,455
      tipo_incendio      2,681   1,445     489
      finca              3,373     203   1,039
      institucion_otra   3,887     261     467
      zona               4,215     316      84

   An import that stores what it is handed therefore records 3,080 fires as being
   inside a protected area called ``""``, and 1,445 as having a fire type of
   ``""`` — both of which count as *filled* in any ``IS NOT NULL`` afterwards, and
   neither of which is visible in a spot check.

   :func:`blank_to_none` is the one-line answer, and every text attribute must go
   through it. The numeric columns are unaffected: JSON has no empty number, so
   ``altitud`` and ``coordenada_x`` use ``null`` alone.

The municipality code is inside the name
-----------------------------------------

``municipio`` is a slug with the INE code on the end — ``rio_hondo_1903`` is Río
Hondo, department 19, municipality 03 — which is the national code a join to any
Guatemalan boundary layer needs. :func:`parse_municipality` takes it apart.

It is valid on 4,589 of the 4,611 records that have a municipality. **Four slugs
carry a three-digit code that is not a valid INE code** and cannot be repaired by
guessing:

===================================  =========  ===============================
Published slug                       Code says  Almost certainly
===================================  =========  ===============================
``san_rafael_la_independencia_131``  0131       1331 (Huehuetenango)
``san_sebastian_huehuetenango_132``  0132       1332 (Huehuetenango)
``fray_bartolome_de_las_casas_161``  0161       1615 (Alta Verapaz)
``san_rafael_pie_de_la_cuesta_121``  0121       1221 (San Marcos)
===================================  =========  ===============================

Each has lost a digit, and *which* digit differs between them, so there is no rule
to apply. :func:`parse_municipality` validates the code's department against
:data:`DEPARTMENT_CODES` and returns ``None`` for a code that disagrees, which
puts those 22 records in the same position as a record with no code at all —
their department is still known, from the department column.
"""

from __future__ import annotations

import re

#: Identity of the :class:`~src.data_model.data_provider.DataProvider` row every
#: INAB fire hangs off. The product names the published layer rather than the
#: agency: INAB's server carries 284 services and this is one of them.
PROVIDER_NAME = "INAB"
PROVIDER_FULL_NAME = "Instituto Nacional de Bosques"
PROVIDER_PRODUCT = "Monitoreo de Incendios Forestales"
PROVIDER_URL = "https://sig.inab.gob.gt/server/rest/services"

#: The CRS the published geometry is in: plain WGS 84 longitude and latitude.
SOURCE_SRID = 4326

#: Zone every published instant is resolved against.
#:
#: A rule here rather than a fallback, unlike Mexico's or Canada's. Guatemala is a
#: single time zone over the whole country, is UTC-6 all year, and has observed no
#: daylight saving since 2006 — so there is nothing for a spatial lookup to decide
#: and nothing a date can change. The importer still stores the name rather than
#: the offset, because that is the project's rule and because a country that has
#: used DST twice in living memory may use it again.
DEFAULT_TIME_ZONE = "America/Guatemala"

#: *Guatemala Transverse Mercator*, the national grid, as a PROJ definition.
#:
#: **It has no EPSG code.** The registry's only Guatemalan projected systems are
#: the Ocotepeque 1935 Lambert zones (EPSG:5459 and EPSG:5559), which this is not:
#: GTM is a transverse Mercator on WGS 84, and what the published
#: ``sistema_proyeccion`` means when it says ``GTM``.
#:
#: Verified rather than assumed. Reprojecting the published EPSG:4326 geometry of
#: the 309 records that carry both a ``GTM`` label and a plausible pair of metres
#: reproduces their typed coordinates to a median of 130 m, with 284 of the 309
#: inside 10 km. A wrong projection would be out by hundreds of kilometres, as the
#: three sign-flipped points elsewhere in this dataset demonstrate. The residual is
#: what it should be: two independent readings of the same fire, one tapped on a
#: map and one typed into a form.
GTM_PROJ = ("+proj=tmerc +lat_0=0 +lon_0=-90.5 +k=0.9998 +x_0=500000 +y_0=0 "
            "+datum=WGS84 +units=m +no_defs")

#: What ``sistema_proyeccion`` says the typed coordinates are in.
CRS_GTM = "GTM"
CRS_UTM = "UTM"
REPORTED_CRS = (CRS_GTM, CRS_UTM)

#: The report was closed: the operation finished. 4,375 of 4,615, and the only
#: outcome that says an actual fire was dealt with.
STATUS_CLOSED = "cierre_operaciones"

#: **The report was false — there was no fire.** 140 records.
#:
#: The single most important value in the dataset to know about. It is imported
#: rather than dropped, on the argument set out in the module docstring, and
#: anything counting or mapping fires has to exclude it. See
#: :func:`is_false_alarm`.
STATUS_FALSE = "falso"

#: Nobody went to look. 90 records — not a fire and not *not* a fire.
STATUS_UNVERIFIED = "no_verificado"

#: Confirmed as a real fire but not closed. 4 records.
STATUS_TRUE = "verdadero"

#: Still burning at the time of publication. 2 records.
STATUS_ACTIVE = "activo"

#: Every value ``estado_aviso`` takes, commonest first.
#:
#: Not a ``CHECK`` on the column: one publication observed once, and a constraint
#: built from it would reject the first outcome INAB adds. See the module
#: docstring.
REPORT_STATUSES = (STATUS_CLOSED, STATUS_FALSE, STATUS_UNVERIFIED, STATUS_TRUE,
                   STATUS_ACTIVE)

#: The statuses that do **not** describe a fire that happened.
#:
#: ``falso`` says there was no fire. ``no_verificado`` says nobody checked, which
#: is not the same claim and is kept separate — 90 records that a strict count
#: should exclude and a permissive one may keep.
NON_FIRE_STATUSES = (STATUS_FALSE,)

#: How the report reached INAB (``forma_comunicacion``), commonest first: by
#: telephone (3,853), in person, through the app, through social media, by radio.
REPORT_CHANNELS = ("telefono", "personal", "app", "redes_sociales", "radio")

#: Whether the fire was inside or outside forest (``tipo_incendio``).
#:
#: The only classification of the fire itself the dataset carries, and it is
#: filled on 489 records — one in ten.
LOCATION_IN_FOREST = "dentro_de_bosque"
LOCATION_OUT_OF_FOREST = "fuera_de_bosque"
FIRE_LOCATIONS = (LOCATION_IN_FOREST, LOCATION_OUT_OF_FOREST)

#: The four published columns that carry personal data, which the import must
#: never read.
#:
#: ``reportado_por`` and ``telefono`` are the name and telephone number of whoever
#: reported the fire — 1,969 distinct pairs, most of them private individuals.
#: ``created_user`` and ``last_edited_user`` are INAB staff accounts.
#:
#: Named here rather than merely omitted from the model so that the omission is a
#: decision on the record instead of an oversight, and so that a test can assert
#: none of them reached a column. See the module docstring.
PERSONAL_FIELDS = ("reportado_por", "telefono", "created_user", "last_edited_user")

#: The INE code of every Guatemalan department, keyed by the slug ``departamento``
#: publishes. All twenty-two appear in the data.
#:
#: This is what makes :func:`parse_municipality` able to reject a malformed
#: municipality code: the first two digits of a municipality code are its
#: department, so a code that disagrees with the department column is wrong.
DEPARTMENT_CODES = {
    "guatemala": 1, "el_progreso": 2, "sacatepequez": 3, "chimaltenango": 4,
    "escuintla": 5, "santa_rosa": 6, "solola": 7, "totonicapan": 8,
    "quetzaltenango": 9, "suchitepequez": 10, "retalhuleu": 11, "san_marcos": 12,
    "huehuetenango": 13, "quiche": 14, "baja_verapaz": 15, "alta_verapaz": 16,
    "peten": 17, "izabal": 18, "zacapa": 19, "chiquimula": 20, "jalapa": 21,
    "jutiapa": 22,
}

#: Bounds a published coordinate has to fall in to be inside Guatemala.
#:
#: Used to report the three points that are not — not to reject them. A point
#: outside the country is the provider's data and is stored as published; what
#: this is for is saying so at import, and noting that all three are already
#: flagged ``falso``.
PLAUSIBLE_LONGITUDE = (-92.5, -88.0)
PLAUSIBLE_LATITUDE = (13.5, 18.0)

#: A ``municipio`` slug: a name, then the INE code. See :func:`parse_municipality`.
_MUNICIPALITY_PATTERN = re.compile(r"^(?P<name>.+)_(?P<code>\d{3,4})$")


def blank_to_none(value: str | None) -> str | None:
    """Turn an unfilled text field into ``None``, whichever way it is unfilled.

    Parameters
    ----------
    value : str or None
        A published text attribute, as read.

    Returns
    -------
    str or None
        The value stripped of surrounding whitespace, or ``None`` if there is
        nothing left.

    Notes
    -----
    Every text attribute of this source has to go through this, because the source
    marks *not filled* two ways in the same column — see the warning in the module
    docstring. ``nombre_ap_1`` alone is ``null`` on 80 records and ``""`` on 3,080,
    and a model that stored the second would report 3,080 fires inside a protected
    area named ``""``.

    Whitespace is stripped as well as tested, the published values including
    trailing spaces — ``'Roger Agustín '``, ``'Josefinos '`` — which would
    otherwise make two spellings of one locality.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def is_false_alarm(status: str | None) -> bool:
    """Whether a report says there was no fire.

    Parameters
    ----------
    status : str or None
        The published ``estado_aviso``.

    Returns
    -------
    bool
        ``True`` for :data:`STATUS_FALSE`, and for nothing else.

    Notes
    -----
    ``no_verificado`` is deliberately **not** a false alarm. It says nobody went to
    check, which is a different claim from *there was no fire*, and folding the two
    together would turn 90 unknowns into 90 non-events. A strict count of fires
    should probably exclude both; this function answers only the question it is
    named for, and the 90 are reachable through
    :data:`~src.providers.guatemala_inab.STATUS_UNVERIFIED`.
    """
    return status == STATUS_FALSE


def is_in_guatemala(longitude: float | None, latitude: float | None) -> bool:
    """Whether a published coordinate falls inside Guatemala.

    Parameters
    ----------
    longitude, latitude : float or None
        The published pair.

    Returns
    -------
    bool
        ``True`` when both are present and inside
        :data:`PLAUSIBLE_LONGITUDE` / :data:`PLAUSIBLE_LATITUDE`.

    Notes
    -----
    Three of the 4,615 published points fail this, and the failure is worth
    reporting rather than fixing. Two are longitudes that lost their minus sign —
    ``+90.47`` for ``-90.47``, which puts a fire in Jutiapa into Cambodia — and
    the third is 200 km inside Honduras.

    They are **not** corrected on the way in. A sign flip is an obvious guess and
    obvious guesses about coordinates are how a dataset acquires plausible wrong
    answers; all three records are already ``estado_aviso = 'falso'``, so the
    provider's own flag removes them from any honest count without this having to
    invent a coordinate.
    """
    if longitude is None or latitude is None:
        return False
    return (PLAUSIBLE_LONGITUDE[0] <= longitude <= PLAUSIBLE_LONGITUDE[1]
            and PLAUSIBLE_LATITUDE[0] <= latitude <= PLAUSIBLE_LATITUDE[1])


def parse_municipality(slug: str | None,
                       department: str | None = None) -> tuple[str | None, int | None]:
    """Split a ``municipio`` slug into its name and its INE code.

    Parameters
    ----------
    slug : str or None
        The published value, ``rio_hondo_1903``.
    department : str or None
        The published ``departamento``. When given, the code's department is
        checked against it and a code that disagrees is rejected — which is the
        only way to catch the four truncated codes described in the module
        docstring.

    Returns
    -------
    tuple of (str or None, int or None)
        The slug as published — code and all — and the INE code where it is
        valid.

    Examples
    --------
    >>> parse_municipality("rio_hondo_1903", "zacapa")
    ('rio_hondo_1903', 1903)
    >>> parse_municipality("amatitlan_114", "guatemala")
    ('amatitlan_114', 114)
    >>> parse_municipality("san_sebastian_huehuetenango_132", "huehuetenango")
    ('san_sebastian_huehuetenango_132', None)

    Notes
    -----
    The slug is returned **whole**, code included, and the code is returned beside
    it rather than instead of any part of it — the project's rule everywhere that
    a provider's text is kept as published and a derived form is added next to it.

    A department code below 10 is published without its leading zero, so Amatitlán
    in department 01 is ``114`` and not ``0114``. Both forms parse; the code is
    returned as an integer, and reading its department means zero-padding to four
    first.

    Without ``department`` the only check is the shape, which the four truncated
    slugs pass — ``0131`` is a perfectly well-formed code, it just is not
    Huehuetenango. Pass the department.
    """
    published = blank_to_none(slug)
    if published is None:
        return None, None
    match = _MUNICIPALITY_PATTERN.match(published)
    if match is None:
        return published, None

    code = int(match.group("code"))
    if department is not None:
        expected = DEPARTMENT_CODES.get(department)
        if expected is not None and int(f"{code:04d}"[:2]) != expected:
            return published, None
    return published, code


def national_municipality_code(code: int | None) -> str | None:
    """The INE municipality code as the four-character string it really is.

    Parameters
    ----------
    code : int or None
        A code from :func:`parse_municipality`.

    Returns
    -------
    str or None
        Zero-padded to four characters, ``'0114'``, or ``None``.

    Notes
    -----
    The integer is what the slug carries and what the column stores; this is what
    a join to a Guatemalan boundary layer needs, because those publish the code as
    text and ``114`` will not match ``'0114'``.
    """
    return None if code is None else f"{code:04d}"
