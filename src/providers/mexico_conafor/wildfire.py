#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAFOR wildfire model.

A burnt area polygon from the Mexican national cartography. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start, the end and
the perimeter; this model adds the published key, the administrative location,
the burnt area and its six strata, the classification attributes and the link to
the cause.

See :mod:`src.providers.mexico_conafor` for the dataset — the fourteen layers,
the schema that changes every year, and what
:data:`~src.providers.mexico_conafor.FIELD_ALIASES` does about it.

Only one perimeter, unlike ICNF and NBAC
-----------------------------------------

There is **no second geometry column here**. :mod:`src.providers.portugal_icnf`
keeps its polygons in EPSG:3763 as well as EPSG:4326 because ETRS89 / Portugal
TM06 is the projected grid Portuguese forestry measures on and reprojecting is
neither free nor lossless; :mod:`src.providers.canada_nbac` does the same with
EPSG:3978. CONAFOR publishes in **EPSG:4326 already**, in all fourteen archives,
so :attr:`~src.data_model.wildfire.Wildfire.perimeter` is the published geometry
rather than a reprojection of it. Adding a national grid would mean *inventing* a
projection the provider never used and storing a derived geometry as if it were
published, which is the opposite of what the ICNF column does.

There is no ignition point either
----------------------------------

CONAFOR publishes a perimeter and a :attr:`property_name` — the *predio*, the
estate or landholding the fire was on — and never a coordinate for where it
started. There is therefore no :class:`~src.data_model.ignition.Ignition` for a
CONAFOR fire, exactly as for an ICNF one and unlike a GFA or NFDB one: there is
no point to put in it.

The area is the polygon's, except in 2010
------------------------------------------

:attr:`area_ha` is ``AREA_HA`` as published, and from 2016 it *is* the geodesic
area of the polygon beside it — median ratio 1.000, four rows in five within 1%.
Which makes 2010 the thing to know about this column: there the median ratio is
3.0 and the 90th percentile is 65, and the two numbers are unrelated. Anything
measuring burnt area across the series should either start at
:data:`~src.providers.mexico_conafor.FIRST_YEAR_WITH_MEASURED_AREA` or measure
from the geometry, and either way should not average the 2010 column with the
rest. :attr:`year` is what makes that filter possible, which is one of the two
reasons it is ``NOT NULL`` and indexed.

The other is that :attr:`year` is what an import replaces: one published archive
is one year, and re-running the import for 2021 should not have to know which
rows it wrote last time.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.mexico_conafor import DATE_TIME_PRECISIONS
from src.providers.mexico_conafor.fire_cause import ConaforFireCause


class ConaforWildfire(Wildfire):
    """A burnt area as published by CONAFOR.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the CONAFOR-specific ones are stored here, in
    ``conafor_wildfire``, whose primary key is also a foreign key to the parent
    row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. This is the local GisFIRE
        identifier, shared with the parent row.
    fire_code : str
        The published ``CLAVEINC`` — ``CLAVE`` in 2012, ``CLAVE_DEL`` in 2015 —
        ``YY-EE-NNNN``: two digits of year, two of INEGI state, four of sequence
        within that state and year. **Unique**, and the only usable identifier the
        dataset has.

        Text, and stored whole: the three parts are also stored separately in
        :attr:`year` and :attr:`state_code`, but the key a CONAFOR record is known
        by is the string, and reassembling it from three integers would be one
        more place to get the zero padding wrong.

        Unique is safe because the five repeats in the archive — all in 2021 — are
        exact duplicate features, identical down to the geometry. See
        :mod:`src.providers.mexico_conafor`.
    year : int
        The year the polygon burnt in, taken from the layer being read rather than
        from the two-digit prefix of :attr:`fire_code`, which has no century. The
        unit an import replaces, and the filter anything comparing burnt areas
        across the series needs. ``NOT NULL`` and indexed.

        Nine fires have a ``FECHAINIC`` in a different calendar year — five 2016
        dates in the 2017 layer, and four others — so this is the *published year*
        and not a restatement of the start date.
    source_layer : str
        Name of the archive this row was read from — ``"incendios_2021"``.
        Provenance, and what an import checks to know whether it has already loaded
        a layer. Indexed.
    state_code : int
        INEGI state code, 1 to 32, parsed from :attr:`fire_code`. ``NOT NULL``:
        every one of the 45,914 published rows has a well-formed key, and in all
        but one of them this code agrees with the published state name.

        Derived rather than published, and worth deriving: the names are spelled
        34 ways for 32 states — *Distrito Federal* and *Ciudad de México* are the
        same state either side of 2016, *México* and *Estado de México* the same
        one throughout — and one of them is simply wrong, ``15-17-0054`` being
        filed under *Distrito Federal* in a layer whose own key says Morelos. So
        grouping by :attr:`state_name` gives the wrong answer and grouping by this
        gives the right one.
    state_name : str
        *Entidad federativa*, as published. ``ESTADO`` in thirteen layers and
        ``ESTADO_1`` in 2015, where ``ESTADO`` is the numeric code instead — see
        the warning on :data:`~src.providers.mexico_conafor.FIELD_ALIASES`. Kept
        for the same reason ICNF's district name is: it is what the file says.
        Group by :attr:`state_code`.
    municipality_code : int or None
        *Municipio* number (``CLAVEMUN``), published from 2018 and ``None`` for the
        13,872 fires before that.

        **Not a national code.** It is the municipality's number *within its
        state*, 1 to 570, and means nothing without :attr:`state_code` beside it.
        The national INEGI key is the two composed, two digits of state and three
        of municipality::

            LPAD(state_code::text, 2, '0') || LPAD(municipality_code::text, 3, '0')
    municipality_name : str
        *Municipio* (``MUNICIPIO``), as published. 1,482 distinct spellings, which
        is more municipalities than Mexico has, for the usual reasons.
    property_name : str or None
        The *predio* — estate, *ejido*, *bienes comunales* or ranch — the fire was
        on (``PREDIO``, ``PREDIO_O_P`` in 2011). Free text, and the finest location
        the dataset gives in words. ``None`` for the 7,513 fires of 2023, whose
        layer drops the field.
    date_time_precision : str
        How much of :attr:`~src.data_model.wildfire.Wildfire.start_date_time` the
        provider actually published — :data:`~src.providers.mexico_conafor.
        PRECISION_DAY` or :data:`~src.providers.mexico_conafor.PRECISION_YEAR`.
        Constrained to those two.

        It is ``day`` on every row of the archive as published today: no layer of
        any year carries a time, and every importable row has a readable date. The
        column is here so that the parent's instants are not read as if they were
        timed — local midnight is a placeholder for the hours, not a claim that
        the fire started at midnight — and so that a future release with a
        dateless row has somewhere to say so.
    cause_id : int or None
        Foreign key to the :class:`~src.providers.mexico_conafor.fire_cause.
        ConaforFireCause` the fire was classified as. ``None`` for a fire whose
        ``CAUSA`` is one of the missing-value tokens — 2010 writes ``'0'`` into it
        seven times and 2011 writes ``'No'`` 153 times.
    cause : ConaforFireCause or None
        The fire's cause. Its ``cause``/``specific_cause`` are the published
        Spanish, ``cause_normalised`` the canonical Spanish to group by and
        ``cause_en``/``specific_cause_en`` the English.
    fire_type : str or None
        How the fire burnt (``TIPOINC``; ``TIPO_INC`` in 2012 and 2016-2017,
        ``TIPO_DE_IN`` in 2015), as
        published: *Superficial* (surface, 42,410 rows), *Mixto* (mixed, 1,997),
        *Subterráneo* (ground, 101) or *De copa* (crown, 24). Ten spellings for
        those four.

        Given no ``CHECK``: this is a published vocabulary observed once, and a
        constraint built from it would reject the first term CONAFOR adds — the
        same call :mod:`src.providers.greece_ffa` makes for its incident category.
    impact_level : str or None
        Severity (``TIPIMPAC``, ``TIPO_DE_IM`` in 2015), as published: *Impacto
        Mínimo* (41,198 rows), *Impacto Moderado* (3,329) or *Impacto Severo*
        (437), in fourteen spellings. ``None`` for 2012, which does not publish it, and for the 654
        rows of 2010-2011 that say *Sin dato*.

        Note how skewed it is — nine fires in ten are *mínimo* — which is a
        property of the classification, not of Mexican fires.
    vegetation_type : str or None
        Vegetation the fire burnt (``TIPVEG``; ``TIPVEGE`` in 2011, ``TIP_VEG`` in
        2012 and 2016-2017, ``TIPO_DE_VE`` in 2015), as published, INEGI code
        suffix included where the file writes one. 156 spellings, and see the
        mojibake warning in
        :mod:`src.providers.mexico_conafor` before grouping by it.
    vegetation_type_code : str or None
        The INEGI code parsed out of :attr:`vegetation_type` when it carries one —
        ``BPQ`` for *Bosque de Pino-Encino* — and ``None`` for the forty thousand
        rows that do not. 5,366 rows carry one, most of them in 2015 and 2019. See
        :func:`~src.providers.mexico_conafor.split_vegetation_type`,
        which will not mistake the *Pino* of ``'Bosque de Encino - Pino'`` for one.
    protected_area_name : str or None
        The *Área Natural Protegida* the fire touched (``ANP``), as published. 485
        distinct areas; ``None`` for the 32,214 rows that write ``'0'``, ``'N/A'``
        or nothing, which is most of them.
    area_ha_protected : float or None
        Hectares of that protected area that burnt (``ANP_HA``; ``SUPAFECANP`` in
        2016-2017, ``ANP_HECTAR`` in 2015). Zero rather than ``None`` when the fire touched no protected
        area, because zero is a measurement: see
        :func:`~src.providers.mexico_conafor.is_missing`.
    area_ha : float or None
        Total burnt area in hectares (``AREA_HA``, ``TOTAL`` in 2012). **The 2010
        values do not describe the 2010 polygons**; see the module docstring.

        Nullable for **one row in 45,914**. ``21-24-0078`` — San Luis Potosí,
        December 2021 — publishes a key, a municipality, a *predio*, a cause, both
        dates, a vegetation type, a 6.41 ha herbaceous stratum and a polygon, and
        leaves this field empty. A ``NOT NULL`` here would delete that fire, which
        is a worse answer than storing what CONAFOR actually published; its area
        is recoverable from either its strata or its geometry, and inventing it at
        import would put a derived number in a column that means *reported*.
    area_ha_tree : float or None
        Of :attr:`area_ha`, the hectares of *arbolado adulto*, mature trees
        (``ARBOR_HA``; ``ARB_ADUL`` in 2012, ``ARBADULTO`` in 2015).
    area_ha_regeneration : float or None
        Of :attr:`area_ha`, *renuevo* — regeneration, young growth (``RENUEV_HA``,
        ``RENUEV``).
    area_ha_shrub : float or None
        Of :attr:`area_ha`, *arbustivo*, shrub layer (``ARBUSTI_HA``, ``ARBUST``).
    area_ha_herbaceous : float or None
        Of :attr:`area_ha`, *herbáceo* / *pasto*, grass and herbs (``HERBAC_HA``,
        ``PASTO``).
    area_ha_litter : float or None
        Of :attr:`area_ha`, *hojarasca*, leaf litter (``HOJAR_HA``,
        ``HOJARASCA``).
    area_ha_organic_soil : float or None
        Of :attr:`area_ha`, *suelo orgánico*, organic soil (``SUELORG_HA``,
        ``SUELO_ORG_``, ``SUELO_ORG``). The first of the strata to go: absent from
        2020 on, where the remaining five still sum to the total, which says the
        hectares were folded in rather than lost.

        All six are ``None`` for the 14,231 fires of 2022 and 2023, whose layers
        publish a total and no breakdown at all. Where they are published they add
        up: 44,215 of the 44,222 rows that have both agree with :attr:`area_ha` to
        within 1%.
    perimeter_source : str or None
        How the polygon was drawn (``POLIGONO``) — ``IMAGEN`` from a satellite
        image, ``COORD`` from ground or air coordinates, ``AQSPPIF`` from the
        agency's aerial product. See
        :data:`~src.providers.mexico_conafor.PERIMETER_SOURCES`.

        **Published by the 2023 layer and by no other**, so it is ``None`` on
        38,401 of the 45,914 rows. It is stored anyway, and is the most useful
        single attribute in the dataset: it is the only thing CONAFOR ever says
        about how good a perimeter is, and the year that says it shows the mix —
        69% digitised from imagery, 25% surveyed.

    Notes
    -----
    :attr:`fire_code` is unique, which makes this the first perimeter provider in
    the project that can be re-imported row by row rather than layer by layer.
    ICNF cannot (48,861 of its features publish no identifier), Greece cannot
    (nothing identifies a fire), GWIS cannot (its id is not unique). Here an
    ``ON CONFLICT (fire_code)`` upsert is correct, and :attr:`source_layer` is
    provenance rather than the unit of replacement — though replacing a whole year
    is still the simpler operation and is what the import does.
    """

    __tablename__ = "conafor_wildfire"

    __table_args__ = (
        CheckConstraint(
            "date_time_precision IN ("
            + ", ".join(f"'{precision}'" for precision in DATE_TIME_PRECISIONS)
            + ")",
            name="ck_conafor_wildfire_date_time_precision",
        ),
        Index("ix_conafor_wildfire_year", "year"),
        Index("ix_conafor_wildfire_source_layer", "source_layer"),
        Index("ix_conafor_wildfire_state_code", "state_code"),
        Index("ix_conafor_wildfire_cause_id", "cause_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    fire_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    state_code: Mapped[int] = mapped_column(Integer, nullable=False)
    state_name: Mapped[str] = mapped_column(String, nullable=False)
    municipality_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    municipality_name: Mapped[str] = mapped_column(String, nullable=False)
    property_name: Mapped[str | None] = mapped_column(String, nullable=True)
    date_time_precision: Mapped[str] = mapped_column(String, nullable=False)
    cause_id: Mapped[int | None] = mapped_column(ForeignKey(ConaforFireCause.id), nullable=True)
    fire_type: Mapped[str | None] = mapped_column(String, nullable=True)
    impact_level: Mapped[str | None] = mapped_column(String, nullable=True)
    vegetation_type: Mapped[str | None] = mapped_column(String, nullable=True)
    vegetation_type_code: Mapped[str | None] = mapped_column(String, nullable=True)
    protected_area_name: Mapped[str | None] = mapped_column(String, nullable=True)
    area_ha_protected: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_tree: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_regeneration: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_shrub: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_herbaceous: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_litter: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_organic_soil: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter_source: Mapped[str | None] = mapped_column(String, nullable=True)

    cause: Mapped[ConaforFireCause | None] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "conafor_wildfire",
    }

    def __repr__(self) -> str:
        return (f"ConaforWildfire(id={self.id!r}, fire_code={self.fire_code!r}, "
                f"year={self.year!r})")
