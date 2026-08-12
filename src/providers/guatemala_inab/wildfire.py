#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INAB wildfire model.

One fire report from Guatemala's *Monitoreo de Incendios Forestales*. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start instant; this
model adds the report's identifier, what became of it, who reported it and how,
where it was in administrative terms, and the link to the point.

See :mod:`src.providers.guatemala_inab` for the dataset — the 4,615 records, the
false alarms, the personal data that is not imported, and why one fire can appear
twice.

Neither a perimeter nor an area
--------------------------------

This is the first provider in GisFIRE that publishes **no size information at
all**, and the absence shapes the whole model.

:mod:`src.providers.spain_egif` and :mod:`src.providers.greece_ffa` publish no
perimeter but do publish burnt areas — five figures and eight respectively — so
their models carry hectares and their statistics applications report them. INAB
publishes thirty-three attributes and not one of them is a size. There is
therefore no ``area_ha`` on this model, nothing for an
``--area-method`` to choose between, and
:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every row.

What this dataset answers is *where and when*, not *how much*.

The end date is always absent
------------------------------

:attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL`` on every INAB
fire, and not because the provider does not know. The companion ``informes``
layer on the same service — 5,812 rows — holds when the first crews arrived and
when the fire was controlled and extinguished, and it is not modelled here.

Adding it is a second model rather than a column: there are more *informes* than
there are fires, because one fire is reported on several times, so the arrival and
extinction times are a one-to-many relationship and not two more fields.

A report is not a fire
-----------------------

:attr:`InabWildfire.global_id` is unique because a **report** is unique. 57 pairs
of published records share an exact coordinate and an exact minute — the same fire
called in twice, by two institutions, sometimes reaching two different outcomes.

Deduplicating them is deliberately not done at import. The two rows disagree about
``estado_aviso``, and choosing between a ``no_verificado`` and a
``cierre_operaciones`` for the same fire is a judgement about which reporter to
believe. That belongs in an analysis that can state its rule, not in an import
that would have to make it silently.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire


class InabWildfire(Wildfire):
    """A fire report as published by INAB.

    Uses joined table inheritance: the columns shared by every wildfire live in
    the ``wildfire`` table and only the INAB-specific ones are stored here, in
    ``inab_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE
        identifier, shared with the parent row.
    global_id : str
        The published ``GlobalID``, a braced UUID —
        ``'{49585C0C-4FE2-45A3-A50C-405E6C4EF418}'``. **Unique**, ``NOT NULL``,
        and the only identifier in this dataset worth having.

        It identifies a *report*, not a fire: see the module docstring on the 57
        duplicated pairs. It is also the only key that survives a republication,
        which :attr:`object_id` does not.
    object_id : int or None
        The published ``OBJECTID``. Provenance only, and **not an identifier**:
        the layer is a hosted view, its values run 13 to 4,798 with gaps across
        4,615 rows, and they are reassigned when INAB republishes.

        Stored so that a stored row can be matched back to a downloaded file, and
        indexed for that purpose, but never unique-constrained and never a key.
    source_id : int or None
        ``ob_id``, an identifier from whatever system feeds the view. 4,454 of the
        4,615 records have one and they do not repeat, but 161 have none, so it
        cannot be the key either.
    report_status : str or None
        ``estado_aviso``, what became of the report:
        :data:`~src.providers.guatemala_inab.STATUS_CLOSED` (4,375),
        :data:`~src.providers.guatemala_inab.STATUS_FALSE` (140),
        :data:`~src.providers.guatemala_inab.STATUS_UNVERIFIED` (90),
        :data:`~src.providers.guatemala_inab.STATUS_TRUE` (4) or
        :data:`~src.providers.guatemala_inab.STATUS_ACTIVE` (2).

        **The most important column in the table after the date.** 140 records
        say there was no fire, and any count that does not filter on this is
        3% too high — use
        :func:`~src.providers.guatemala_inab.is_false_alarm`. Indexed, because
        that filter belongs on every query.

        Given no ``CHECK``: this is one publication's vocabulary observed once,
        and a constraint built from it would reject the first outcome INAB adds —
        the same call :mod:`src.providers.greece_ffa` makes.
    report_channel : str or None
        ``forma_comunicacion``, how the report arrived: ``telefono`` (3,853),
        ``personal``, ``app``, ``redes_sociales`` or ``radio``. A measure of how
        Guatemala hears about its fires, and the only such measure in the project.
    institution : str or None
        ``institucion``, which organisation reported it. Fourteen values, led by
        ``conred`` (2,066, the national disaster agency) and ``conap`` (756, the
        protected areas council).

        This is the part of *who reported it* that has analytical meaning and is
        not personal data. The reporter's name and telephone number are published
        and are **not** imported; see
        :data:`~src.providers.guatemala_inab.PERSONAL_FIELDS`.
    institution_other : str or None
        ``institucion_otra``, free text naming the organisation when
        :attr:`institution` is ``otra``. Filled on 466 of the 476 that are.
    fire_location : str or None
        ``tipo_incendio``, whether the fire was
        :data:`~src.providers.guatemala_inab.LOCATION_IN_FOREST` (383) or
        :data:`~src.providers.guatemala_inab.LOCATION_OUT_OF_FOREST` (106).

        The only classification of the fire itself the dataset carries, and it is
        ``NULL`` on 4,126 records — **89% of them**. Anything grouping by it is
        describing one record in ten.
    department_name : str or None
        ``departamento``, as published: a lower-case slug, ``peten``,
        ``el_progreso``. All twenty-two departments appear.
    municipality_name : str or None
        ``municipio``, as published, **code included** — ``rio_hondo_1903``. Kept
        whole rather than split, on the project's rule that a provider's text is
        stored as it was published; :attr:`municipality_code` is the derived form
        beside it.
    municipality_code : int or None
        The INE municipality code parsed out of :attr:`municipality_name` by
        :func:`~src.providers.guatemala_inab.parse_municipality`, and validated
        against the department — 1903 for Río Hondo, 114 for Amatitlán.

        This is the national code, unlike
        :attr:`~src.providers.mexico_conafor.wildfire.ConaforWildfire.
        municipality_code`, which is only a number within its state. Reading its
        department means zero-padding to four first, department 01 publishing its
        codes without the leading zero.

        ``None`` for the 22 records whose slug carries a truncated code that names
        the wrong department. Their :attr:`department_name` is still good.
    locality_name : str or None
        ``aldea_lugar``, the *lugar poblado* — free text, 3,780 distinct values,
        and the finest location the dataset gives in words.
    estate_name : str or None
        ``finca``, the estate or property, on 1,039 records.
    inab_region : str or None
        ``region_inab``, INAB's own administrative region, as a lower-case Roman
        numeral: ``i`` to ``x``. Not a national division — it is the forestry
        service's internal geography, and region ``viii`` (1,202 records) is
        Petén.
    inab_subregion : str or None
        ``subregion_inab``, the subdivision below it. Thirty-nine values.
    protected_area_name : str or None
        ``nombre_ap_1``, the protected area the point falls in — *Reserva de la
        Biosfera Maya* leads with 528. Filled on 1,455 records, **one in three**,
        which is a real property of Guatemalan fire rather than a gap in the data.
    protected_area_name_secondary : str or None
        ``nombre_ap_2``, a second overlapping area, filled on the same 1,455
        records. Guatemala's reserves nest — a fire can be in the *Reserva de la
        Biosfera Maya* and in the *Parque Nacional Sierra del Lacandón* inside it
        — so the two columns are a containment, not a disagreement.
    published_at : datetime.datetime or None
        ``created_date``, when the record was created. Not an event time: it is
        the provider's bookkeeping, and it is what tells you whether a record has
        been added since a previous download.

        Worth knowing: **36 records were created before the fire they report**,
        which is a data-entry error in the fire's date rather than in this one.
    edited_at : datetime.datetime or None
        ``last_edited_date``, when it was last revised. What says a published
        record is still being corrected, and so whether re-importing is worth
        doing.
    ignition_id : int or None
        Foreign key to the :class:`~src.providers.guatemala_inab.ignition.
        InabIgnition` for this report.

        Nullable, and filled on every record published today: all 4,615 carry a
        point. It is nullable because a report with no location is a thing this
        source could publish — four records already carry nothing but an
        identifier and a map tap — and a ``NOT NULL`` would mean dropping such a
        record rather than storing what it does say.
    ignition : Ignition or None
        Where the fire was reported to be.

    Notes
    -----
    There is no ``area_ha`` and no ``date_time_precision``.

    No area because the provider publishes none — see the module docstring. No
    precision column because every published instant is a real minute: unlike
    :mod:`src.providers.portugal_icnf`, where 71% of the dates are a placeholder,
    or :mod:`src.providers.mexico_conafor`, where none of the fourteen layers
    publishes a time at all, this dataset's times are observations. A column whose
    every value would be ``'minute'`` would say nothing.
    """

    __tablename__ = "inab_wildfire"

    __table_args__ = (
        Index("ix_inab_wildfire_report_status", "report_status"),
        Index("ix_inab_wildfire_object_id", "object_id"),
        Index("ix_inab_wildfire_department_name", "department_name"),
        Index("ix_inab_wildfire_municipality_code", "municipality_code"),
        Index("ix_inab_wildfire_ignition_id", "ignition_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    global_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_status: Mapped[str | None] = mapped_column(String, nullable=True)
    report_channel: Mapped[str | None] = mapped_column(String, nullable=True)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    institution_other: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_location: Mapped[str | None] = mapped_column(String, nullable=True)
    department_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    estate_name: Mapped[str | None] = mapped_column(String, nullable=True)
    inab_region: Mapped[str | None] = mapped_column(String, nullable=True)
    inab_subregion: Mapped[str | None] = mapped_column(String, nullable=True)
    protected_area_name: Mapped[str | None] = mapped_column(String, nullable=True)
    protected_area_name_secondary: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    edited_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ignition_id: Mapped[int | None] = mapped_column(ForeignKey(Ignition.id), nullable=True)

    ignition: Mapped[Ignition | None] = relationship(foreign_keys=[ignition_id])

    __mapper_args__ = {
        "polymorphic_identity": "inab_wildfire",
    }

    def __repr__(self) -> str:
        return (f"InabWildfire(id={self.id!r}, global_id={self.global_id!r}, "
                f"report_status={self.report_status!r})")
