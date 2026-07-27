#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICNF wildfire model.

A burnt area polygon from the Portuguese national cartography. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start, the end and
the perimeter; this model adds the identifiers, the administrative location of
the ignition, the areas by land type, the link to the cause and the perimeter as
the ICNF published it.

See :mod:`src.providers.icnf` for the two eras of the dataset and why a row has
to say how good its own dates are.

The perimeter is stored twice, on purpose
-----------------------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is the reprojection to
EPSG:4326, which is what makes an ICNF fire comparable with a GWIS or GFA one and
what every cross-provider query and spatial join uses.
:attr:`IcnfWildfire.perimeter_etrs89_tm06` is the polygon exactly as published, in
EPSG:3763.

Keeping both is not redundancy. ETRS89 / Portugal TM06 is a projected national
grid in metres, so an area or a distance computed on it is the number Portuguese
forestry works in and matches what ``AreaHaSIG`` says; the same computation on
EPSG:4326 is on degrees and has to go through a geodesic function to mean
anything. Reprojecting is also not free and not lossless — going to 4326 and back
does not return the published coordinates — so a query that needs the national
grid needs it stored, not derived.

The two are the same geometry: the import repairs the published polygon, stores
it, and derives the 4326 one from what it stored with ``ST_Transform``.

The location is administrative, not a coordinate
------------------------------------------------

The ``PI_`` attributes (*Ponto de Início*, point of origin) name where the fire
started — district, municipality, parish, place — but the ICNF publishes **no
ignition coordinate** in these layers. There is therefore no
:class:`~src.data_model.ignition.Ignition` for an ICNF fire, unlike a GFA one:
there is no point to put in it. The names are stored as text, as published.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.icnf import DATE_TIME_PRECISIONS
from src.providers.icnf import SOURCE_SRID
from src.providers.icnf.fire_cause import IcnfFireCause


class IcnfWildfire(Wildfire):
    """A burnt area as published by the ICNF.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the ICNF-specific ones are stored here, in
    ``icnf_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. This is the local GisFIRE
        identifier, shared with the parent row.
    source_layer : str
        Name of the published layer this row was read from — ``"ardida_2024"``,
        ``"ardida_1975_1989"``. Provenance, and the only thing that identifies a
        fire from the years that publish no identifier, which is what the import
        uses to recognise a layer it has already loaded. Indexed.
    sgif_code : str or None
        The fire's identifier in SGIF, the national forest fire information
        system (``Cod_SGIF``). **Unique** where present, over all twelve years
        that publish it. ``None`` for every fire before 2014 and for the 901
        later polygons the ICNF could not match to a record.

        Text, and never parsed: the format has changed three times —
        ``"AT114103"`` up to 2021, ``"2022_01_0004987"`` in 2022, ``"20240125102"``
        from 2023 — and nothing but the ICNF's own systems can read meaning out
        of it.
    anepc_code : str or None
        The same fire's occurrence number at ANEPC, the national emergency and
        civil protection authority (``Cod_ANEPC``). Thirteen digits through 2022
        and eleven from 2023, when it became equal to :attr:`sgif_code`. Not
        unique-constrained: it is the other agency's key, not this dataset's.
    year : int
        The year the polygon burnt in (``Ano``). The **only** attribute besides
        the geometry and the area that every layer of every era publishes, which
        is why it is ``NOT NULL`` here while the dates on the parent may be
        derived. Indexed.
    date_time_precision : str
        How much of :attr:`~src.data_model.wildfire.Wildfire.start_date_time` the
        provider actually published — :data:`~src.providers.icnf.PRECISION_YEAR`,
        :data:`~src.providers.icnf.PRECISION_DAY` or
        :data:`~src.providers.icnf.PRECISION_MINUTE`. Constrained to those three.

        This is the column that keeps the model honest. A ``year`` row's start is
        the 1st of January because that is the only instant the year supports,
        not because anything happened that day, and an average or a histogram
        that does not filter on this column will be wrong by up to twelve months
        for 71% of the dataset. See :mod:`src.providers.icnf`.
    first_response_date_time : datetime.datetime or None
        When the first crew reached the fire (``DH_1Interv``), never earlier than
        the parent's ``start_date_time``. Same instant-plus-zone rule and the same
        precision caveat as the parent's dates.
    duration_minutes : int or None
        Duration in minutes (``Duracao_m``), as published.

        Worth knowing: this is the **only** surviving trace of the times the
        shapefile export threw away. It is consistent with the published instants
        to the minute, so on a ``day`` row it is strictly better information than
        the difference between the stored dates — a fire with
        ``duration_minutes = 97`` whose stored start and end are a day apart
        burnt for an hour and a half across midnight, not for a day.
    dicofre_code : str or None
        The INE administrative code of the parish the fire started in
        (``PI_DICOFRE``): two digits of *distrito*, two of *concelho*, two of
        *freguesia*. Text, always six characters — several are written
        ``"030415"`` and would lose their leading zero as a number.
    nuts3_name : str or None
        NUTS 3 statistical region (``PI_NUTS3``).
    district_name : str or None
        *Distrito* (``PI_Distrit``). Beware when grouping: 2014-2016 spell Viana
        do Castelo two ways, ``"Viana Do Castelo"`` and ``"Viana do Castelo"``, so
        eighteen districts come back as nineteen names. Kept as published rather
        than corrected; :attr:`dicofre_code` is the reliable key.
    municipality_name : str or None
        *Concelho* (``PI_Conc``).
    parish_name : str or None
        *Freguesia* (``PI_Freg``).
    place_name : str or None
        Locality or place the fire started at (``PI_Local``), free text.
    cause_id : int or None
        Foreign key to the :class:`~src.providers.icnf.fire_cause.IcnfFireCause`
        the fire was classified as. ``None`` for an unclassified fire and for
        every fire before 2014.
    cause : IcnfFireCause or None
        The fire's cause. Its ``type``/``description`` are the published
        Portuguese and its ``type_en``/``description_en`` the English.
    area_ha_gis : float
        Burnt area in hectares measured from the polygon (``AreaHaSIG``).
        Published for every fire in every era, and the only area the pre-2014
        layers have. ``NOT NULL``.
    area_ha_sgif : float or None
        Burnt area in hectares as recorded in SGIF (``AreaHaSGIF``). A different
        measurement of the same fire, not a copy of :attr:`area_ha_gis`, and the
        one the three areas below add up to.
    area_ha_forest_stand : float or None
        Of :attr:`area_ha_sgif`, the hectares that were *povoamento*, forest
        stand (``AreaHaPov``).
    area_ha_shrubland : float or None
        Of :attr:`area_ha_sgif`, the hectares that were *mato*, shrubland
        (``AreaHaMato``).
    area_ha_agricultural : float or None
        Of :attr:`area_ha_sgif`, the hectares that were agricultural land
        (``AreaHaAgri``). These three sum to :attr:`area_ha_sgif` exactly, in all
        19,568 fires that publish them.
    edition_date_time : datetime.datetime or None
        When the ICNF last revised the record (``Edicao``). Not an event time:
        it is the provider's own bookkeeping, and it runs well past the fire —
        fires of 2024 carry editions into March 2025. It is what tells you a
        published year is still being corrected, and so whether re-importing it
        is worth doing.
    perimeter_etrs89_tm06 : geoalchemy2.elements.WKBElement or None
        The burnt area as published: a ``MULTIPOLYGON`` in EPSG:3763, ETRS89 /
        Portugal TM06. ``None`` only if repairing the published polygon reduced it
        to nothing. See the module docstring for why this is kept as well as the
        parent's EPSG:4326 perimeter.

    Notes
    -----
    There is no unique constraint spanning the whole table. :attr:`sgif_code` is
    unique where it is present, which is the 2014-2025 fires that were matched to
    a record; the other 48,861 rows have nothing published that could identify
    them, not even within one layer — ten pairs share a year and a burnt area to
    fifteen decimal places. Re-importing is therefore controlled by
    :attr:`source_layer` at the layer level, not row by row: see
    :mod:`src.apps.imports.wildfires.portugal_icnf.import_wildfires`.
    """

    __tablename__ = "icnf_wildfire"

    __table_args__ = (
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{precision}'" for precision in DATE_TIME_PRECISIONS)
            + ")",
            name="ck_icnf_wildfire_date_time_precision",
        ),
        Index("ix_icnf_wildfire_source_layer", "source_layer"),
        Index("ix_icnf_wildfire_year", "year"),
        Index("ix_icnf_wildfire_cause_id", "cause_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    sgif_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    anepc_code: Mapped[str | None] = mapped_column(String, nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)
    first_response_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dicofre_code: Mapped[str | None] = mapped_column(String, nullable=True)
    nuts3_name: Mapped[str | None] = mapped_column(String, nullable=True)
    district_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    parish_name: Mapped[str | None] = mapped_column(String, nullable=True)
    place_name: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_id: Mapped[int | None] = mapped_column(ForeignKey(IcnfFireCause.id), nullable=True)
    area_ha_gis: Mapped[float] = mapped_column(Float, nullable=False)
    area_ha_sgif: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_forest_stand: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_shrubland: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_agricultural: Mapped[float | None] = mapped_column(Float, nullable=True)
    edition_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    perimeter_etrs89_tm06: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID), nullable=True
    )

    cause: Mapped[IcnfFireCause | None] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "icnf_wildfire",
    }

    def __repr__(self) -> str:
        return (f"IcnfWildfire(id={self.id!r}, sgif_code={self.sgif_code!r}, "
                f"year={self.year!r})")
