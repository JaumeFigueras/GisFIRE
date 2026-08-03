#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REDIAM wildfire model.

A burnt area polygon from the Andalusian cartography. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start instant and the
perimeter; this model adds the published code, the published date, where the fire is
filed municipally and provincially, the three burnt areas the service publishes, how
many features it was published as, the polygon in the CRS it was published in, the
link to the published ignition point, and the link to the EGIF *parte* for the same
fire.

See :mod:`src.providers.andalusia_rediam` for the dataset itself — the combined
layer, the two forms of the code, the 55 duplicate records and why the axis order in
the ``.prj`` is not the one the geometry is stored under.

The perimeter is stored twice, on purpose
-----------------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the reprojection to
EPSG:4326, which is what makes an Andalusian fire comparable with a GWIS, GFA, ICNF
or Catalan one and what every cross-provider query uses.
:attr:`RediamWildfire.perimeter_etrs89_utm30n` is the polygon in EPSG:25830, the grid
it was published on.

The argument is the ICNF and DARPA one exactly: a projected grid in metres is what an
area or a distance computed on it means something in, and the same computation on
EPSG:4326 is on degrees and means nothing without a geodesic function. Reprojecting
is neither free nor lossless, so a query that needs the grid needs it stored.

The two are the same geometry: the import dissolves and repairs the published
polygons, stores the result, and derives the 4326 one from what it stored with
``ST_Transform``.

There *is* a burnt area, and it is not the perimeter
-----------------------------------------------------

Unlike Catalonia's, this dataset publishes hectares:
:attr:`RediamWildfire.area_ha_wooded`, :attr:`RediamWildfire.area_ha_scrub` and
:attr:`RediamWildfire.area_ha_grassland`, on every feature of every year.

They are kept exactly as published and are not reconciled with the polygon. Over the
907 fires they sum to 152,696 ha against 165,582 ha of mapped perimeter, measured on
the published grid — which is what one expects of three vegetation classes against an
outline
that also encloses everything that is none of them. Both numbers are real and they
answer different questions; a report that mixed them would be comparing two things in
one column.

There is no published total. The sum of the three is the nearest thing to one, and
the model does not store it: a stored sum is a value that can disagree with its parts
after an edit, and adding three columns is not expensive.

The ignition point is a row of its own
---------------------------------------

For 2021-2024 the yearly layers publish ``X_INIC`` and ``Y_INIC``, and the import
turns each into a :class:`~src.providers.andalusia_rediam.ignition.RediamIgnition`
with :attr:`RediamWildfire.ignition_id` pointing at it. For every other year the
column is ``NULL``, because no point was published — not because it was dropped.

An ignition is a row and not two columns here for the reason set out in
:mod:`src.data_model.ignition`: it is a separate observation, with its own instant,
its own country and its own zone, and the published point is often **not inside the
published perimeter** — 88 of the 201 are. Storing it as an attribute of the polygon
would suggest the two agree.

The code is stored as published
--------------------------------

:attr:`RediamWildfire.code` is ``CODIGO`` verbatim, ``IIFF`` prefix and all. See
:mod:`src.providers.andalusia_rediam`: the code *is* an EGIF ``report_number`` and
:func:`~src.providers.andalusia_rediam.egif_report_number` is the decode, but
normalising it at import would bake the matching rule into the model. The rule lives
where it belongs instead:
:mod:`~src.apps.bindings.wildfires.andalusia_rediam.bind_egif_wildfires` reads the code
and records *how* it read it, on :attr:`RediamWildfire.match_method`.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers.andalusia_rediam import SOURCE_SRID
from src.providers.andalusia_rediam.ignition import RediamIgnition
from src.providers.spain_egif.wildfire import EgifWildfire

#: The published ``CODIGO`` **is** the EGIF ``report_number``, character for
#: character, and the two agree on the date as well. 702 of the 907 fires. Certain.
MATCH_CODE = "code"

#: The code *is* the report number once it is read rather than compared: the ``IIFF``
#: prefix of a 2025 code comes off, or a nine-digit code's three-digit sequence is
#: zero-padded back. The two published dates also agree.
#:
#: Five fires: the 2019 codes written with three digits, less the one whose dates
#: disagree, which is :data:`MATCH_CODE_DATE_MISMATCH` instead. The ``IIFF`` codes are
#: all 2025, which the EGIF exports do not reach, so none of them matches anything yet.
#:
#: Below :data:`MATCH_CODE` because it rests on a reading of the format rather than on
#: string equality — the same distinction the Catalan
#: :data:`~src.providers.catalonia_darpa.wildfire.MATCH_CODE_REFORMATTED` draws, and
#: for the same reason — and above everything else because it is still an identifier.
MATCH_CODE_REFORMATTED = "code_reformatted"

#: The code is the ``report_number`` but the two published dates disagree — 42 of the
#: 749 fires whose number EGIF has, by anything from a day to five weeks. Still a
#: match, because the report number is a national identifier and not a guess; kept
#: apart because a fire whose two sources disagree about *when* it burnt is worth
#: being able to find.
MATCH_CODE_DATE_MISMATCH = "code_date_mismatch"

#: Exactly one candidate left after testing which EGIF ignition points fall inside the
#: Andalusian perimeter.
#:
#: Reached only by the fires whose report number EGIF does not have at all. Available
#: far more often than in Catalonia — EGIF publishes a coordinate for 12,378 of the
#: 12,389 Andalusian *partes* of 2008-2023, where it publishes none at all before 1998
#: — but **evidence rather than proof**: of the 748 fires bound by identifier that have
#: a point, only 417 have it inside the perimeter. A point outside is normal here, so
#: the test is used to *narrow* candidates and never to reject them all.
MATCH_GEOMETRY = "geometry"

#: Exactly one *parte* on that date, in that province, in that municipality.
MATCH_DATE_PROVINCE_NAME = "date_province_name"

#: Exactly one *parte* on that date in that province, whatever the municipality says.
MATCH_DATE_PROVINCE = "date_province"

#: Every value :attr:`RediamWildfire.match_method` may take, strongest first.
#:
#: Shorter than the Catalan list by the two rules that cannot arise here.
#: :data:`~src.providers.catalonia_darpa.wildfire.MATCH_DATE` and
#: :data:`~src.providers.catalonia_darpa.wildfire.MATCH_DATE_NAME` are the branches
#: taken when a code carries **no province**, and every Andalusian code does — all 962
#: published features decode to one of the eight
#: :data:`~src.providers.andalusia_rediam.PROVINCE_INE_CODES`. A fire whose code did
#: not decode is left unbound and reported rather than bound on a date alone, which in
#: a province with 40,757 *partes* would be a coin toss.
MATCH_METHODS = (
    MATCH_CODE,
    MATCH_CODE_REFORMATTED,
    MATCH_CODE_DATE_MISMATCH,
    MATCH_GEOMETRY,
    MATCH_DATE_PROVINCE_NAME,
    MATCH_DATE_PROVINCE,
)

#: The confidence stored for each method.
#:
#: Fixed per method rather than computed per fire, and **an ordering rather than a
#: probability** — see :attr:`RediamWildfire.match_confidence`. The numbers are the
#: Catalan ones for the methods the two datasets share, so that
#: ``WHERE match_confidence >= 0.9`` means the same thing on both: an identifier
#: match, not a name match.
MATCH_METHOD_CONFIDENCE = {
    MATCH_CODE: 1.00,
    MATCH_CODE_REFORMATTED: 0.95,
    MATCH_CODE_DATE_MISMATCH: 0.90,
    MATCH_GEOMETRY: 0.85,
    MATCH_DATE_PROVINCE_NAME: 0.75,
    MATCH_DATE_PROVINCE: 0.60,
}


class RediamWildfire(Wildfire):
    """An Andalusian forest fire perimeter.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Andalusian ones are stored here, in
    ``rediam_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE identifier,
        shared with the parent row.
    source_layer : str
        The published layer the fire was read from, upper-cased —
        ``PERIMETROS_COR_2008_2025`` for a fire from the combined file, or
        ``PERIMETROS_COR_2022`` for one imported from a single year.

        Provenance, and only that. **It is not what a re-import replaces**: the name
        of the combined file carries the range it covers and therefore changes every
        year, so the import replaces the years it finds inside a layer instead. See
        :mod:`~src.apps.imports.wildfires.andalusia_rediam.import_wildfires`.
    code : str
        The published ``CODIGO``, **exactly as published** — ``2008410097``,
        ``IIFF2025040059``, ``201918023``. Never parsed or normalised;
        :func:`~src.providers.andalusia_rediam.egif_report_number` reads it when
        something needs the report number.

        Indexed through :attr:`fire_date`'s unique constraint rather than on its own.
    fire_date : datetime.date
        The published ``FECHA_INC``, which is a real DBF date field rather than text
        and is published on every feature. ``NOT NULL``.

        Stored beside :attr:`~src.data_model.wildfire.Wildfire.start_date_time`
        rather than derived from it because the two are different kinds of thing: the
        parent holds an *instant*, local midnight in
        :attr:`~src.data_model.wildfire.Wildfire.time_zone`, and this holds the *date*
        the service wrote down. The dataset publishes no time of day anywhere.

        It is also half the natural key.
    year : int
        The year of :attr:`fire_date`, which is also the year the code names —
        checked at import on every fire rather than assumed, and true of all 962
        published features. Indexed, because grouping by year is what every
        statistics report over this dataset does, an expression on :attr:`fire_date`
        could not use an index, and **it is what a re-import replaces**.
    municipality_name : str
        ``Municipio``, as published: the municipality the fire is filed under. The
        case is the source's and varies within a single layer — ``LUBRIN`` beside
        ``Lubrín`` — and is not normalised, for the same reason the code is not.

        A fire that burnt in several municipalities is filed under one of them: this
        is where the fire is *recorded*, not the whole of where it burnt. The
        perimeter is the answer to the second question.
    province_name : str
        ``Provincia``, as published, with the same variation in case and accents
        (``Cordoba``, ``CÓRDOBA``, ``Córdoba`` all occur).

        The province is also the fifth and sixth digits of the code, as an INE code,
        and that is the one to join on — see
        :func:`~src.providers.andalusia_rediam.egif_report_number`. This column is
        what the service wrote.
    part_count : int
        How many published features were dissolved into this fire's perimeter.

        ``1`` for 852 of the 907 fires and ``2`` for the other 55, which are the
        duplicate records described in :mod:`src.providers.andalusia_rediam` — the
        same fire published twice, with the same footprint in 54 of the 55 and with
        two different mappings in the remaining one. Stored so that the duplication
        stays visible rather than silently smoothed over.
    area_ha_wooded, area_ha_scrub, area_ha_grassland : float or None
        ``SUP_ARBOLA``, ``SUP_MATORR`` and ``SUP_PASTIZ``: the burnt wooded, scrub
        and grassland areas in hectares, as published. Nullable because a later
        publication may leave one out; nothing in the 2008-2025 archive does.

        Not reconciled with the perimeter and not summed into a total — see the
        module docstring.
    ignition_id : int or None
        Foreign key to the
        :class:`~src.providers.andalusia_rediam.ignition.RediamIgnition` built from
        the published ``X_INIC`` / ``Y_INIC``.

        ``NULL`` except for 2021-2024, the only years that publish a point. A null
        here means the service published no coordinate, never that one was dropped.
    ignition : RediamIgnition or None
        Where the fire started, as published.
    egif_wildfire_id : int or None
        Foreign key to the :class:`~src.providers.spain_egif.wildfire.EgifWildfire`
        *parte* for the same fire.

        **Always ``None`` as imported**: the import does not attempt the match, and
        neither does anything else today. The column exists so that the binding
        application is an ``UPDATE`` rather than a migration.
    egif_wildfire : EgifWildfire or None
        The Spanish *parte* for the same fire, once something has bound them.
    match_method : str or None
        **How** the binding was arrived at. ``None`` exactly when
        :attr:`egif_wildfire_id` is, which a check constraint enforces.

        One of :data:`MATCH_METHODS`, which a check constraint enforces as well. This
        column is what makes the binding usable: 98.7% of the links rest on the
        published identifier — ``CODIGO`` *is* the EGIF ``report_number`` — and the
        rest on a date, a province and a municipality name, which is a good rule and
        not a certainty. An analysis that treated the two alike would be claiming a
        precision the second kind does not have.

        The list is shorter than the Catalan one and deliberately so; see
        :data:`MATCH_METHODS`.
    match_confidence : float or None
        A number between 0 and 1, fixed per method by
        :data:`MATCH_METHOD_CONFIDENCE`, and an **ordering rather than a
        probability**: nothing here is calibrated against ground truth, so it says
        "trust this more than that" and nothing arithmetical.
    matched_at : datetime.datetime or None
        When the binding was computed. Not
        :attr:`~src.data_model.wildfire.Wildfire.updated_at`, which moves for any
        edit: a binding older than the last EGIF import was computed against data
        that has since changed, and this is what says so.
    perimeter_etrs89_utm30n : str or None
        The burnt area polygon in EPSG:25830, the grid the service publishes on. See
        the module docstring on why it is kept as well as the EPSG:4326 one on the
        parent row.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL`` on every row
    and will stay so: the dataset publishes one date per fire and does not say
    whether it is the detection, the ignition or the day the perimeter was flown.
    Storing it as an end as well would be an invention.
    """

    __tablename__ = "rediam_wildfire"

    __table_args__ = (
        # The published natural key. The date is in it as a precaution rather than
        # from observation — no Andalusian code names two dates — and because it
        # makes this key the same shape as darpa_wildfire's, so a query over both
        # regional datasets is one query.
        UniqueConstraint("code", "fire_date", name="uq_rediam_wildfire_code_fire_date"),
        # A binding is the link *and* the account of how it was made. Either both are
        # there or neither is: a link with no method would be unattributable, and a
        # method with no link would be a claim about nothing.
        CheckConstraint(
            "(egif_wildfire_id IS NULL) = (match_method IS NULL)",
            name="ck_rediam_wildfire_match_method_with_link",
        ),
        CheckConstraint(
            "match_method IN ("
            + ", ".join(f"'{method}'" for method in MATCH_METHODS)
            + ")",
            name="ck_rediam_wildfire_match_method",
        ),
        Index("ix_rediam_wildfire_source_layer", "source_layer"),
        Index("ix_rediam_wildfire_year", "year"),
        Index("ix_rediam_wildfire_ignition_id", "ignition_id"),
        Index("ix_rediam_wildfire_egif_wildfire_id", "egif_wildfire_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    fire_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    municipality_name: Mapped[str] = mapped_column(String, nullable=False)
    province_name: Mapped[str] = mapped_column(String, nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)
    area_ha_wooded: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_scrub: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_grassland: Mapped[float | None] = mapped_column(Float, nullable=True)
    ignition_id: Mapped[int | None] = mapped_column(ForeignKey(Ignition.id), nullable=True)
    egif_wildfire_id: Mapped[int | None] = mapped_column(
        ForeignKey(EgifWildfire.id), nullable=True
    )
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    perimeter_etrs89_utm30n: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID), nullable=True
    )

    ignition: Mapped[RediamIgnition | None] = relationship(foreign_keys=[ignition_id])
    egif_wildfire: Mapped[EgifWildfire | None] = relationship(
        foreign_keys=[egif_wildfire_id]
    )

    __mapper_args__ = {
        "polymorphic_identity": "rediam_wildfire",
    }

    def __repr__(self) -> str:
        return (f"RediamWildfire(id={self.id!r}, code={self.code!r}, "
                f"fire_date={self.fire_date!r})")
