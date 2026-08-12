#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NFDB wildfire model.

One agency fire report: what a provincial, territorial or Parks Canada fire
management agency filed about one fire. The generic
:class:`~src.data_model.wildfire.Wildfire` already holds the start and end instants;
this model adds the published identifiers, which agency filed it, the reported size,
the cause, the response, the three published dates and the link to the point.

See :mod:`src.providers.canada_nfdb` for the dataset itself — the thirteen agencies,
the identifiers that do not identify, the dirt and where it is.

There is no perimeter, ever
---------------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every NFDB fire
and always will be, for the reason it is ``NULL`` on every EGIF and Greek one: the
agencies publish a fire's *location and size*, not its shape.

Perimeters for Canadian fires exist and come from
:mod:`src.providers.canada_nbac`, which is a data provider of its own. **They will
not be written into this row.** A row belongs to the provider named by its
``data_provider_id``, and an NBAC polygon on an NFDB row would quietly make the
provenance a lie. The two are related instead by
:attr:`~src.providers.canada_nbac.wildfire.NbacWildfire.nfdb_wildfire_id`, and the
link points that way — from the shape to the report — because the report is the
record the fire is filed under.

The size is reported, and it is not the perimeter's
-----------------------------------------------------

:attr:`size_ha` is what the agency filed. Over the archive it sums to 166.5 million
hectares against NBAC's 132.7 million of mapped burn, and the gap is not an error
in either: one is what an agency recorded at the time, the other is what a
satellite could see afterwards.

A reported ``0`` is an answer and not a silence — 40,025 fires carry it — and
283,363 more are under one hectare. Anything reasoning about fire size here should
know that two thirds of the archive is smaller than a football pitch, and that the
service's own *large fire* distribution, which is a different download, keeps only
the 21,677 fires of 200 ha or more and accounts for over 97% of the area.

The dates are three, and two of them are usually missing
----------------------------------------------------------

``REP_DATE`` is when the fire was reported and is what
:attr:`~src.data_model.wildfire.Wildfire.start_date_time` is resolved from.
``ATTK_DATE`` is when the agency began fighting it and ``OUT_DATE`` when it was
declared out; the second is ``NULL`` on 216,601 rows, 48% of the archive.

Unlike :mod:`src.providers.canada_nbac.wildfire` there is **no fallback**: this
dataset publishes no second date to resolve a start from, so a row with no
``REP_DATE`` — 4,047 of them — is refused by the import rather than dated to 1
January of its year. Inventing a date here would put four thousand fires on New
Year's Day, which is exactly the artefact the Portuguese archive is full of and
which :mod:`src.providers.portugal_icnf` has to warn about.

There is consequently no ``date_time_precision`` column: every stored fire has a
published day, so a column recording how much of the date is real would be the
constant ``day``.

``FIRE_TYPE`` is thirteen vocabularies, not one
-------------------------------------------------

The agencies do not agree on what it means. British Columbia files ``Fire``,
Alberta ``IFR`` and ``OFR``, others ``Wildfire``, ``Surface``, ``Ground``,
``Crown``, ``Forest``, ``Grass``, ``Other`` — and 144,476 rows leave it empty.
Some of those describe *what burned*, some *how it burned* and some *what kind of
incident it was*.

It is stored exactly as published, uninterpreted and unconstrained, because there
is nothing to normalise it to. Read it only per
:attr:`src_agency`; a count over the whole archive by ``FIRE_TYPE`` is a count of
thirteen different questions.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers.canada_nfdb import FIRE_CAUSES
from src.providers.canada_nfdb.ignition import NfdbIgnition


class NfdbWildfire(Wildfire):
    """A Canadian agency fire report.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Canadian ones are stored here, in
    ``nfdb_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE identifier,
        shared with the parent row.
    nfdb_fire_id : str or None
        The published ``NFDBFIREID``. Indexed and **not unique** — 1,684 of the
        values are used by more than one row — so it is a handle for finding a
        record, not a key for identifying one. See :mod:`src.providers.canada_nfdb`.
    agency_fire_id : str or None
        The published ``FIRE_ID``, the agency's own number for the fire. Only
        338,313 distinct values over 448,602 rows: unique within an agency and a
        year at best, and the field a Canadian fire manager will actually recognise.
    fire_name : str or None
        ``FIRENAME``, where the agency named the fire.
    src_agency : str
        ``SRC_AGENCY``, which agency filed this report: a province or territory code
        (``BC``, ``AB``, ``ON``, …) or ``PC`` for Parks Canada. ``NOT NULL`` and
        indexed.

        The most important column on this table after the cause. Coverage, accuracy,
        vocabulary and start year all vary by agency — British Columbia files
        156,554 of the 448,602 rows and Prince Edward Island 55 — so a figure
        computed over the whole archive without regard to it is a figure about
        reporting practice as much as about fire.
    nat_park : str or None
        ``NAT_PARK``, the national park the fire was in, for the Parks Canada rows.
    year : int or None
        The published fire year, or ``None`` where the service wrote
        :data:`~src.providers.canada_nfdb.UNKNOWN_YEAR`. Indexed: it is how a year
        is re-imported and what every report groups on.

        Nullable although :attr:`~src.data_model.wildfire.Wildfire.start_date_time`
        is not, because the two come from different published columns and can
        disagree: the year is ``YEAR`` and the instant is resolved from
        ``REP_DATE``.
    size_ha : float or None
        ``SIZE_HA``, the burnt area the agency reported, in hectares. Never null and
        never negative in the published archive; ``0`` on 40,025 rows, which is a
        report of a fire that burnt almost nothing rather than a missing value.
    fire_cause : str
        ``CAUSE``: :data:`~src.providers.canada_nfdb.CAUSE_NATURAL`,
        :data:`~src.providers.canada_nfdb.CAUSE_HUMAN` or
        :data:`~src.providers.canada_nfdb.CAUSE_UNKNOWN`. ``NOT NULL``, constrained
        to those three and indexed.

        ``N`` is the nearest thing to lightning this dataset has and **is not a
        lightning category** — see :data:`~src.providers.canada_nfdb.CAUSE_NATURAL`.
        195,240 fires carry it, which is what makes this archive the largest
        lightning-attributable set in GisFIRE.
    fire_cause_detail : str or None
        ``CAUSE2``, which repeats :attr:`fire_cause` on almost every row and refines
        it on a few thousand: ``H-PB`` for a prescribed burn (372 rows) and ``RE``
        for a re-burn (74). Unconstrained, because it is the column an agency would
        extend first.
    fire_type : str or None
        ``FIRE_TYPE``, as published and uninterpreted. Thirteen agencies, thirteen
        vocabularies — see the module docstring before using it.
    response : str or None
        ``RESPONSE``, what the agency did about the fire.
    protection_zone : str or None
        ``PROTZONE``, the protection zone it burnt in — which is largely what
        decides whether an agency responds at all, and therefore a confounder in any
        comparison of outcomes.
    prescribed : bool
        ``PRESCRIBED``, whether the agency reported a prescribed burn. ``NOT NULL``
        and **false by default**, resolved from the published text by
        :func:`~src.providers.canada_nfdb.is_prescribed`.

        The source writes ``1``, ``Yes``, ``0``, ``No`` and — on the overwhelming
        majority of rows — nothing at all, because most agencies do not publish the
        column. Anything unrecognised, blank included, is read as **false**: that is
        a deliberate, conservative choice rather than a claim. A prescribed burn is
        rare, so reading silence as *not prescribed* is wrong far less often than
        reading it as *prescribed* would be, and a nullable column would push the
        same decision onto every query instead of taking it once here.

        The cost is that this column cannot distinguish *the agency said no* from
        *the agency did not say*. Where that distinction matters, read
        :attr:`fire_cause_detail`, whose
        :data:`~src.providers.canada_nfdb.CAUSE2_PRESCRIBED_BURN` is published by the
        agencies that classify a prescribed burn as a cause — 372 rows — and is a
        positive statement rather than an absence.
    report_date : datetime.date or None
        ``REP_DATE``, when the fire was reported. What
        :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is resolved from;
        a row without one is not imported.
    attack_date : datetime.date or None
        ``ATTK_DATE``, when the agency began fighting the fire. The interval to
        :attr:`report_date` is the response time, which is one of the few things in
        GisFIRE that measures a *response* rather than an event.
    out_date : datetime.date or None
        ``OUT_DATE``, when the fire was declared out. ``None`` on 48% of the
        archive, and the source of
        :attr:`~src.data_model.wildfire.Wildfire.end_date_time`.
    acquisition_date : datetime.date or None
        ``ACQ_DATE``, when the Canadian Forest Service acquired the record from the
        agency. Provenance of the *compilation*, not of the fire.
    more_info : str or None
        ``MORE_INFO``, free text from the agency.
    cfs_note1, cfs_note2 : str or None
        ``CFS_NOTE1`` and ``CFS_NOTE2``, the compiler's own annotations — the two
        columns that say why a row is odd, and worth reading before deciding a row
        is wrong.
    ignition_id : int or None
        Foreign key to the
        :class:`~src.providers.canada_nfdb.ignition.NfdbIgnition` holding the point
        the fire was reported at.

        Nullable for the few rows whose published coordinate fails
        :func:`~src.providers.canada_nfdb.is_located`, which is a far smaller share
        than in the Spanish or Greek archives — this dataset is points first.
    ignition : NfdbIgnition or None
        The published point, where there is one.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **report**
    instant and :attr:`~src.data_model.wildfire.Wildfire.end_date_time` the *out*
    instant. Neither is the ignition: nothing here says when the fire actually
    started, and the report date is when somebody noticed.
    """

    __tablename__ = "nfdb_wildfire"

    __table_args__ = (
        CheckConstraint(
            "fire_cause IN ("
            + ", ".join(f"'{cause}'" for cause in FIRE_CAUSES)
            + ")",
            name="ck_nfdb_wildfire_fire_cause",
        ),
        CheckConstraint("size_ha IS NULL OR size_ha >= 0",
                        name="ck_nfdb_wildfire_size_ha"),
        Index("ix_nfdb_wildfire_year", "year"),
        Index("ix_nfdb_wildfire_fire_cause", "fire_cause"),
        Index("ix_nfdb_wildfire_src_agency", "src_agency"),
        Index("ix_nfdb_wildfire_nfdb_fire_id", "nfdb_fire_id"),
        Index("ix_nfdb_wildfire_ignition_id", "ignition_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    nfdb_fire_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agency_fire_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_name: Mapped[str | None] = mapped_column(String, nullable=True)
    src_agency: Mapped[str] = mapped_column(String, nullable=False)
    nat_park: Mapped[str | None] = mapped_column(String, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    size_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    fire_cause: Mapped[str] = mapped_column(String, nullable=False)
    fire_cause_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_type: Mapped[str | None] = mapped_column(String, nullable=True)
    response: Mapped[str | None] = mapped_column(String, nullable=True)
    protection_zone: Mapped[str | None] = mapped_column(String, nullable=True)
    prescribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    report_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    attack_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    out_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    acquisition_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    more_info: Mapped[str | None] = mapped_column(String, nullable=True)
    cfs_note1: Mapped[str | None] = mapped_column(String, nullable=True)
    cfs_note2: Mapped[str | None] = mapped_column(String, nullable=True)

    ignition_id: Mapped[int | None] = mapped_column(ForeignKey(Ignition.id), nullable=True)

    ignition: Mapped[NfdbIgnition | None] = relationship(foreign_keys=[ignition_id])

    __mapper_args__ = {
        "polymorphic_identity": "nfdb_wildfire",
    }

    def __repr__(self) -> str:
        return (f"NfdbWildfire(id={self.id!r}, nfdb_fire_id={self.nfdb_fire_id!r}, "
                f"year={self.year!r})")
