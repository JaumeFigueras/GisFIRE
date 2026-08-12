#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Greek Fire Service ignition model.

Where a Greek fire started, as the service publishes it: ``X-ENGAGE`` and
``Y-ENGAGE``, a longitude and a latitude in decimal degrees.

The generic :class:`~src.data_model.ignition.Ignition` already holds the point in
EPSG:4326, the instant and the administrative boundary. This model adds the two
identifiers of the published row it came from, and nothing else — for a reason
worth setting out, because every other ignition in the project carries more.

Six years, and only six
------------------------

The coordinate columns appear in 2020 and are published in every year since.
Before that there is nothing: **201,948 of the 260,194 fires in the archive have
no coordinate at all**, and neither has the 6.4% of 2020-2025 for which the
service writes a pair of zeros.

So :attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.ignition_id` is
``NULL`` on 205,703 fires out of 260,194 — four rows in five — and that is a fact
about the archive rather than about the import. See :mod:`src.providers.greece_ffa`.

The published coordinates are *not* kept a second time
-------------------------------------------------------

:class:`~src.providers.spain_egif.ignition.EgifIgnition` keeps ``utm_x``/``utm_y``
and :class:`~src.providers.andalusia_rediam.ignition.RediamIgnition` keeps
``X_INIC``/``Y_INIC``, in both cases alongside the parent's EPSG:4326 geometry,
because in both cases the published numbers are in *another* CRS and the geometry
is a reprojection of them — a derivation that is neither free nor exactly
reversible.

Here they are the same CRS. The service publishes WGS 84 longitude and latitude
(:data:`~src.providers.greece_ffa.SOURCE_SRID`), so
:attr:`~src.data_model.ignition.Ignition.geometry` *is* the published pair, held
as the two doubles they were read as, and ``ST_X``/``ST_Y`` give them back
unchanged. Storing them again would be storing the same two numbers twice, with
the usual consequence: two places to disagree and no rule for which wins.

This is the same argument that keeps the Spanish columns and not a contradiction
of it. What the project stores is the published value; what it declines to store
is a second copy of one.

.. warning::

   **The point is where the service was engaged, not necessarily where the fire
   began.** ``ENGAGE`` is the dispatch system, and the coordinate is the incident
   location it recorded. For a fire reported by the person standing next to it the
   two are the same; for one reported from a village down the valley they are not,
   and nothing published says which happened.

   It is modelled as an ignition because it is a point and an instant and that is
   what the generic model is, and because there is no second, better point to
   prefer. Treat the precision as *the fire was somewhere near here* rather than
   as a mapped origin.
"""

from __future__ import annotations

from sqlalchemy import BigInteger
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition


class GreeceFfaIgnition(Ignition):
    """The point a Greek fire was reported at, as published.

    Uses joined table inheritance: the columns shared by every ignition live in the
    ``ignition`` table and only the Greek ones are stored here, in
    ``greece_ffa_ignition``, whose primary key is also a foreign key to the parent
    row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE identifier,
        shared with the parent row.
    year : int
        The year of the sheet the point was read from. Indexed, and ``NOT NULL``:
        it is how a year is re-imported, and — since the dataset has no fire
        identifier of any kind — the only unit an import can replace. Always
        2020 or later, because no earlier year publishes a coordinate.
    record_number : int or None
        ``Α/Α ΕΓΓΡΑΦΗΣ`` of the row the coordinate was published on, the same value
        as :attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.record_number`.
        Indexed and **not** unique: 512 record numbers in the archive are used by
        more than one row.
    engage_id : int or None
        ``Α/Α ENGAGE``, the incident number in the service's dispatch system — and
        the key the 2022-2024 workbooks look the coordinate up by, in a helper
        sheet, with a ``VLOOKUP``. ``None`` in 2025, which publishes the column
        under a Latin-``A`` spelling and leaves it empty for some rows.

        Not unique either: 48 of them repeat. A ``bigint``, for the reason given
        on :attr:`~src.providers.greece_ffa.wildfire.GreeceFfaWildfire.engage_id`
        — two published values do not fit in 32 bits.

    Notes
    -----
    There is no unique constraint on this table. Nothing in the dataset identifies
    a fire — see :mod:`src.providers.greece_ffa` — so any constraint here would be
    a claim the published data does not support, and would reject rows the service
    really published.

    :attr:`~src.data_model.ignition.Ignition.date_time` is the same instant as the
    fire's :attr:`~src.data_model.wildfire.Wildfire.start_date_time`: both are the
    published ``Ημερ/νία Έναρξης`` and ``Ώρα Έναρξης``. The dataset reports one
    time, not two.
    """

    __tablename__ = "greece_ffa_ignition"

    __table_args__ = (
        Index("ix_greece_ffa_ignition_year", "year"),
        Index("ix_greece_ffa_ignition_record_number", "record_number"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    record_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    engage_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "greece_ffa_ignition",
    }

    def __repr__(self) -> str:
        return (f"GreeceFfaIgnition(id={self.id!r}, year={self.year!r}, "
                f"record_number={self.record_number!r})")
