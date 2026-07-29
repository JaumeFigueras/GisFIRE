#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EGIF wildfire report detail — the part of the *parte* only the XML publishes.

A one-to-one optional child of :class:`~src.providers.egif.wildfire.EgifWildfire`,
holding the fields of the full report that the Excel "resumen" export throws away:
when the fire was brought under control and when each kind of resource reached it,
how it was detected, how sure anyone is of the cause, the weather at the time, and
how serious it was declared.

Its existence is the provenance
-------------------------------

A fire read from an Excel export has no row here. A fire read from an XML export
has one. Nothing else in the schema records which format a fire came from, and
nothing else needs to: ``LEFT JOIN egif_wildfire_report`` answers it, and
``WHERE r.id IS NULL`` finds the fires still waiting for their XML.

Keeping these columns off the parent is what makes that work, and it keeps the
fire-level table — the one the QGIS view is built on — narrow enough to read.

Why these fields and not the other hundred and fifty
----------------------------------------------------

The full PIF is about 200 fields across some forty relations. This table takes the
**scalar, one-per-fire** fields of four blocks (``pif_tiempos``, ``pif_deteccion``,
``pif_causa``, ``pif_condiciones``) plus the severity index from
``pif_incidencias``, and stops there. What it deliberately leaves unmodelled:

* the **repeating** sub-elements — ``RelTipoAreaIniciadoPif``,
  ``RelIniciadoJuntoAPif``, ``RelModeloCombustionPif``, ``RelTipoFuegoPif`` — each
  of which is a one-to-many needing a table of its own;
* ``pif_medios`` (personnel, aircraft, machinery), ``pif_tecnicas``,
  ``pif_perdidas`` beyond the areas already on the parent, ``pif_anexo``, and the
  whole per-forest-unit ``ParteMonte`` block with its species breakdown and
  economic valuation.

Those are a great deal of schema for questions that have not been asked yet, and
they can be added later without touching anything here.

The one field this table exists for
-----------------------------------

:attr:`EgifWildfireReport.days_since_storm`. It is the interval between the storm
and the fire — the **holdover** — and it is published nowhere else: not in the
Excel, not in the ICNF data, not in GWIS or GFA. In the Barcelona 2020 sample it
is non-zero on three fires, all three in cause family
:data:`~src.providers.egif.CAUSE_LIGHTNING`, and zero on all ninety other fires,
which is what confirmed that family is *Rayo* in the first place.

The codes here are stored bare
------------------------------

``iddetectadopor``, ``idcertidumbrecausa`` and the rest point into catalogues
GisFIRE does not have. The service's endpoints that would return them are behind a
login, and the Excel export — the way the cause and motivation catalogues were
recovered — does not carry these fields at all. So they are kept as text, exactly
as published, and labelled by whoever eventually gets the lists. Text rather than
integers for the reason given in
:class:`~src.providers.egif.fire_cause.EgifFireCause`: they are identifiers, not
quantities, and one of them (``idataque``, not stored here) is even 0-based while
its neighbours are 1-based.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Time
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.providers.egif.wildfire import EgifWildfire


class EgifWildfireReport(Base):
    """The XML-only detail of one *parte de incendio forestal*.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.providers.egif.wildfire.EgifWildfire.id`. One row per fire at
        most, which is what makes this a detail table rather than a second
        wildfire.
    wildfire : EgifWildfire
        The fire this detail belongs to.
    control_date_time : datetime.datetime or None
        When the fire was brought under control (``pif_tiempos/controlado``) —
        contained, but not yet out. Between the parent's ``start_date_time`` and
        ``end_date_time``, and the instant most fire-behaviour work actually
        wants. Timezone-aware, resolved the same way as the parent's instants.
    first_ground_response_date_time : datetime.datetime or None
        Arrival of the first ground resource (``llegadapmt``).
    first_aerial_response_date_time : datetime.datetime or None
        Arrival of the first aerial resource (``llegadapmae``).
    first_helitransported_response_date_time : datetime.datetime or None
        Arrival of the first helitransported crew (``llegadapbh``).
    first_coordination_response_date_time : datetime.datetime or None
        Arrival of the first coordination resource (``llegadapac``).
    first_notification_from_112 : bool or None
        Whether the first notification came through the 112 emergency number
        (``primeranotificaciondesde112``).
    detected_by_code : str or None
        Who or what detected the fire (``iddetectadopor``) — fixed lookout, forest
        ranger, aircraft, member of the public, and so on.
    started_next_to_other : str or None
        Free text naming what the fire started next to when the coded list did not
        have it (``iniciadojuntootros``), ``"Ribera del río"``. Kept because it is
        the only part of that block that is not a bare code.
    responsibility_grade_code : str or None
        Degree of responsibility established (``idgradoresponsabilidad``):
        natural, accidental, negligent, intentional, undetermined.
    days_since_storm : int or None
        Days between the storm and the fire (``diastormenta``) — the holdover
        interval. See the module docstring: this is the field the table is for.
        ``0`` means no storm was involved, not "the same day", so a query for
        holdovers has to exclude zero rather than treat it as an interval.
    cause_investigated_code : str or None
        Whether the cause was formally investigated (``idinvestigacioncausa``).
    cause_certainty_code : str or None
        How certain the cause is (``idcertidumbrecausa``): established or
        presumed. The column that says whether a cause attribution is evidence or
        an opinion, and the one to filter on before counting causes.
    offender_identified_code : str or None
        Whether whoever caused it was identified (``idcausante``).
    activity_authorisation_code : str or None
        Whether the activity that started the fire was permitted
        (``idautorizacionactividad``).
    day_class_code : str or None
        What kind of day it was (``idclasedia``): holiday, Saturday, working day
        before a holiday, working day.
    weather_station_code : str or None
        Identifier of the weather station the observations below were taken at
        (``idestacionmeteorologica``), ``"080055"``. Text: it is zero-padded.
    weather_observation_time : datetime.time or None
        Time of day of the weather observation (``pif_condiciones/hora``), **and
        only the time**.

        The published value is a full datetime and its date is wrong: on the first
        record of the Barcelona 2020 sample a fire detected on 2020-01-01 at 16:30
        carries an observation stamped 2023-12-18 at 16:35 — the time of day is
        the observation's, the date is when somebody typed the form in. Storing
        the datetime would be storing a falsehood with the truth inside it, so
        only the part that means something is kept.
    days_since_rain : int or None
        Days since the last rain (``diasultimalluvia``).
    max_temperature_celsius : float or None
        Maximum temperature, in degrees Celsius (``tempmaxima``).
    relative_humidity_percent : float or None
        Relative humidity, per cent (``humrelativa``).
    wind_speed_km_h : float or None
        Wind speed, in km/h (``velocidadviento``). The unit is the form's, printed
        beside the field.
    wind_direction_degrees : int or None
        Wind direction, in degrees (``direccionviento``).
    max_severity_level : int or None
        The *Índice de Gravedad Potencial* (``idnivelgravedadmaximo``), 0 to 3.

        Despite the ``id`` prefix this is **not** a foreign key into a catalogue:
        it is the index itself, an ordinal severity that can be compared and
        ordered. All 98 fires of the Barcelona 2020 sample are 0.
    created_at : datetime.datetime
        Timezone-aware creation timestamp, set by the database on insert.
    updated_at : datetime.datetime
        Timezone-aware last-modification timestamp, refreshed by the database on
        every update.
    """

    __tablename__ = "egif_wildfire_report"

    id: Mapped[int] = mapped_column(ForeignKey(EgifWildfire.id), primary_key=True)
    control_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_ground_response_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_aerial_response_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_helitransported_response_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_coordination_response_date_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_notification_from_112: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    detected_by_code: Mapped[str | None] = mapped_column(String, nullable=True)
    started_next_to_other: Mapped[str | None] = mapped_column(String, nullable=True)
    responsibility_grade_code: Mapped[str | None] = mapped_column(String, nullable=True)
    days_since_storm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause_investigated_code: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_certainty_code: Mapped[str | None] = mapped_column(String, nullable=True)
    offender_identified_code: Mapped[str | None] = mapped_column(String, nullable=True)
    activity_authorisation_code: Mapped[str | None] = mapped_column(String, nullable=True)
    day_class_code: Mapped[str | None] = mapped_column(String, nullable=True)
    weather_station_code: Mapped[str | None] = mapped_column(String, nullable=True)
    weather_observation_time: Mapped[datetime.time | None] = mapped_column(Time, nullable=True)
    days_since_rain: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_km_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_degrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_severity_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    wildfire: Mapped[EgifWildfire] = relationship()

    def __repr__(self) -> str:
        return f"EgifWildfireReport(id={self.id!r})"
