#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF wildfire model.

The *Parte de Incendio Forestal* itself: one row per official fire report. The
generic :class:`~src.data_model.wildfire.Wildfire` already holds the detection and
extinction instants; this model adds the report number, where the fire is filed
administratively, what it burnt, and the links to its cause and motivation.

There is no perimeter, ever
---------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every EGIF
fire and always will be. EGIF is an administrative statistic and publishes no
burnt area polygon in any of its exports — what it publishes is a burnt *area*, in
hectares, split by land type.

Perimeters for Spanish fires are expected to come later from the autonomous
regions, each of which will be a data provider of its own with its own
:class:`~src.data_model.wildfire.Wildfire` subclass. **They will not be written
into this row.** A row belongs to the provider named by its
``data_provider_id``, which is what makes that column mean anything; a Catalan
polygon on a MITECO row would quietly make the provenance a lie. The two are
related instead, by a link between the two wildfires, which is deliberately not
modelled yet — its vocabulary should be derived from a real matching exercise
against real regional data rather than guessed in advance.

The location is administrative, and it is not the point
-------------------------------------------------------

EGIF states where a fire is filed — *comunidad*, province, municipality, comarca,
*entidad menor* — and separately gives a coordinate, which lives on
:class:`~src.providers.egif.ignition.EgifIgnition`. The two can disagree, and when
they do the administrative answer is the one the statistic is compiled on. So
:attr:`~src.data_model.wildfire.Wildfire.admin_boundary_id` is resolved from
:attr:`EgifWildfire.municipality_ine_code` rather than by point-in-polygon, and a
containment test is worth running at import only as a check on the coordinate.

Which of the two identifiers you get depends on the export.
:attr:`province_ine_code` is free either way — it is the middle field of the report
number, verified one-to-one against all fifty province names — but the municipal
code is published only in the XML. From the Excel there is a name, in INE's own
uppercase inverted form (``"MOLAR, EL"``, ``"KANPEZU/CAMPEZO"``), which has to be
matched against :attr:`~src.providers.ign.admin_boundary.IgnAdminBoundary.ine_code`
on ``(province, name)`` — six names in the sample occur in two provinces each, and
one is the sentinel ``"OTRA PROVINCIA"``.

The two exports fill different columns
--------------------------------------

Everything on this table is published by the Excel export except
:attr:`egif_id`, :attr:`municipality_ine_code` and the ``paraje`` on the ignition.
Everything the XML adds *beyond* this table is on
:class:`~src.providers.egif.wildfire_report.EgifWildfireReport`, whose presence is
how you tell which exports a fire has been seen in. See :mod:`src.providers.egif`.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.wildfire import Wildfire
from src.providers.egif.fire_cause import EgifFireCause
from src.providers.egif.fire_motivation import EgifFireMotivation
from src.providers.egif.ignition import EgifIgnition


class EgifWildfire(Wildfire):
    """An official Spanish fire report (*parte de incendio forestal*).

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the EGIF-specific ones are stored here, in
    ``egif_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE
        identifier, shared with the parent row.
    report_number : str
        The fire's ``numeroparte``, **unique**, and the natural key both exports
        share — which is what lets an Excel import and an XML import of the same
        fire land on one row. Ten characters, year plus INE province plus
        sequence; see
        :attr:`~src.providers.egif.ignition.EgifIgnition.report_number`.
    egif_id : int or None
        EGIF's own internal primary key for the report (``idpif``). Published in
        the XML only, and ``None`` for a fire that has only ever been read from an
        Excel export. Unique where present.

        :attr:`report_number` is the identifier to use: it is in both exports, it
        is human-readable and it carries the year and province. This one is kept
        because it is what the service's own systems key on.
    campaign : int
        The campaign year the report is filed under (``Campania``), which is the
        first four characters of :attr:`report_number` and not necessarily the
        year of :attr:`~src.data_model.wildfire.Wildfire.start_date_time`.
        Indexed: it is how a year is re-imported and how the incompleteness
        described in :mod:`src.providers.egif` is reasoned about.
    status : str or None
        The report's state (``Estado``). Every fire the public service exports is
        ``"Cerrado Revisión"`` — closed and reviewed — which is precisely why the
        published data is never a complete year.
    ignition_id : int
        Foreign key to the :class:`~src.providers.egif.ignition.EgifIgnition`
        holding the fire's point of origin. ``NOT NULL``: every EGIF fire in both
        exports carries a coordinate, and a *parte* without one would be a report
        of a fire nobody located.
    ignition : EgifIgnition
        The fire's point of origin.
    ccaa_name : str or None
        *Comunidad autónoma*, as published (uppercase, ``"CASTILLA-MANCHA"``).
    province_name : str or None
        Province, as published.
    province_ine_code : str
        The two-digit INE province code, taken from characters 5-6 of
        :attr:`report_number`. ``NOT NULL``: it is a pure function of a column
        that is itself ``NOT NULL``, and it was verified one-to-one against all
        fifty province names in the 2022-2023 export, so a row without one means
        the importer mis-parsed a report number.
    municipality_name : str or None
        Municipality, as published: INE's uppercase inverted form, bilingual
        where the region is. May be ``"OTRA PROVINCIA"`` for a fire that spread in
        from elsewhere.
    municipality_ine_code : str or None
        The five-digit INE municipal code, what
        :attr:`~src.providers.ign.admin_boundary.IgnAdminBoundary.ine_code` joins
        on. Published in the XML only; ``None`` for a fire read from an Excel
        export until a name match fills it in.
    comarca_name : str or None
        *Comarca* or island, as published.
    minor_entity_name : str or None
        *Entidad menor* — the village or hamlet within the municipality
        (``EntidadMenor``). Filled on 8,049 of the 13,656 fires in the sample.
    affected_municipality_count : int or None
        How many municipalities the fire burnt in
        (``NumeroMunicipiosAfectados``). 354 fires in the sample cross a boundary,
        one of them into eleven municipalities, and for those the single
        :attr:`municipality_name` is where the fire is *filed*, not the whole of
        where it burnt.
    cause_id : int or None
        Foreign key to the :class:`~src.providers.egif.fire_cause.EgifFireCause`
        the fire was classified as. Nullable because an XML import into a
        database whose catalogue has not been seeded cannot resolve one — the
        Excel export classifies every fire.
    cause : EgifFireCause or None
        The fire's cause.
    motivation_id : int or None
        Foreign key to the
        :class:`~src.providers.egif.fire_motivation.EgifFireMotivation`.
        ``None`` unless the cause is :data:`~src.providers.egif.CAUSE_INTENTIONAL`
        — the motivation is published on intentional fires and on no others.
    motivation : EgifFireMotivation or None
        Why the fire was lit, for an intentional fire.
    area_ha_wooded : float or None
        Burnt forest area that was wooded (``SuperficieArbolada``), in hectares.
    area_ha_non_wooded : float or None
        Burnt forest area that was not wooded (``SuperficieNoArbolada``).
    area_ha_forest_total : float or None
        Total burnt forest area (``SuperficieTotalForestal``). It is exactly
        :attr:`area_ha_wooded` plus :attr:`area_ha_non_wooded` — checked on all
        13,656 rows of the sample — and is stored anyway, as published, so a row
        can be compared with the source without arithmetic.
    area_ha_agricultural : float or None
        Burnt agricultural area (``SuperficieAgricola``). **Not** part of
        :attr:`area_ha_forest_total`; EGIF counts forest and non-forest
        separately, so summing the forest total across fires gives the published
        national figure and adding this to it does not.
    area_ha_other_non_forest : float or None
        Other burnt non-forest area (``OtrasSuperficiesNoforestales``). Also
        outside the forest total.
    wui_affected : bool or None
        Whether the fire reached a wildland-urban interface
        (``AfectoZonasInterfazUrbanoForestal``). ``None`` when the report does not
        say.
    wui_compact : bool or None
        Of the interface types affected, *compacta* — continuous built-up edge.
        Meaningful only where :attr:`wui_affected` is true. The export publishes
        the three as one concatenated flag string (``"1"``, ``"23"``, ``"123"``);
        they are stored apart because they are three independent facts and a fire
        can affect any combination, as 51 in the sample do.
    wui_scattered : bool or None
        Of the interface types affected, *diseminada* — scattered housing.
    wui_isolated : bool or None
        Of the interface types affected, *aislada* — isolated buildings.
    protected_space_affected : bool or None
        Whether the fire burnt inside a protected natural space
        (``AfectoEspacioProtegido``).
    agricultural_land_affected : bool or None
        Whether it burnt agricultural or reforested land
        (``AfectoTierrasAgrarias``).
    zar_affected : bool or None
        Whether it burnt a *Zona de Alto Riesgo* (``AfectoZar``).
    pss_report_number : str or None
        Report number of the related *parte suplementario de seguimiento*
        (``NumeroPartePss``), where one exists. One fire in 13,656 has it.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **detection**
    instant, and :attr:`~src.data_model.wildfire.Wildfire.end_date_time` the
    extinction. Neither is the ignition: nothing in EGIF says when the fire
    actually started, and the interval between them is unreliable at the tail —
    the sample has a 0.02 ha fire stamped as burning for exactly 365 days.
    """

    __tablename__ = "egif_wildfire"

    __table_args__ = (
        Index("ix_egif_wildfire_campaign", "campaign"),
        Index("ix_egif_wildfire_cause_id", "cause_id"),
        Index("ix_egif_wildfire_motivation_id", "motivation_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    report_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    egif_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    campaign: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    ignition_id: Mapped[int] = mapped_column(ForeignKey(EgifIgnition.id), nullable=False)
    ccaa_name: Mapped[str | None] = mapped_column(String, nullable=True)
    province_name: Mapped[str | None] = mapped_column(String, nullable=True)
    province_ine_code: Mapped[str] = mapped_column(String, nullable=False)
    municipality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_ine_code: Mapped[str | None] = mapped_column(String, nullable=True)
    comarca_name: Mapped[str | None] = mapped_column(String, nullable=True)
    minor_entity_name: Mapped[str | None] = mapped_column(String, nullable=True)
    affected_municipality_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause_id: Mapped[int | None] = mapped_column(ForeignKey(EgifFireCause.id), nullable=True)
    motivation_id: Mapped[int | None] = mapped_column(
        ForeignKey(EgifFireMotivation.id), nullable=True
    )
    area_ha_wooded: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_non_wooded: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_forest_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_agricultural: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha_other_non_forest: Mapped[float | None] = mapped_column(Float, nullable=True)
    wui_affected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wui_compact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wui_scattered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wui_isolated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    protected_space_affected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    agricultural_land_affected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    zar_affected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pss_report_number: Mapped[str | None] = mapped_column(String, nullable=True)

    ignition: Mapped[EgifIgnition] = relationship()
    cause: Mapped[EgifFireCause | None] = relationship()
    motivation: Mapped[EgifFireMotivation | None] = relationship()

    __mapper_args__ = {
        "polymorphic_identity": "egif_wildfire",
    }

    def __repr__(self) -> str:
        return (f"EgifWildfire(id={self.id!r}, report_number={self.report_number!r}, "
                f"campaign={self.campaign!r})")
