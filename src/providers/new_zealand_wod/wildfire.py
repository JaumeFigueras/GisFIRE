#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WOD wildfire model.

A New Zealand wildfire record as the Wildfire Occurrence Database publishes it: who
recorded it, when it was reported, how large it was said to be, what started it
and, for 2,089 of 128,020 records, the perimeter.

The generic :class:`~src.data_model.wildfire.Wildfire` holds the instant, the time
zone, the EPSG:4326 perimeter and the administrative boundary. This model adds what
the agency recorded. The point is a
:class:`~src.providers.new_zealand_wod.ignition.WodIgnition`; the topography and
weather the compilers attached are a
:class:`~src.providers.new_zealand_wod.terrain.WodTerrain` and a
:class:`~src.providers.new_zealand_wod.weather.WodWeather`, one each per fire.

The identifier is a key
-----------------------

``ID`` is the WOD's own sequence, ``WOD1`` onwards, in the order records were added,
and it is stable across releases — every identifier of the 2023 release is in the
2025 one with the same content. So, unlike NFDB's and GWIS's, it is **unique** here,
and it is what a re-import matches on.

``OrgID``, the agency's own number (the CAD number for FENZ), is not: 3.7% of records
have none and 23 DOC numbers are used twice.

The perimeter, where there is one
----------------------------------

Most records are points. 1,078 FENZ and 1,011 DOC records carry a polygon: FENZ ones
drawn by staff or from GPS (the square placeholders FENZ sometimes drew from the
reported area were removed by the compilers), DOC ones mostly digitised from paper
maps. :attr:`WodWildfire.perimeter_nztm` holds it as published, made valid; the
parent's ``perimeter`` holds the EPSG:4326 reprojection, the NBAC rule. There are no
perimeters for 2012-2016.

:attr:`WodWildfire.area_ha` is the *reported* area and the perimeter is not used to
correct it: the two agree to within a few percent on most records and disagree
wildly on some, and which is right is not something this model can know.
"""

from __future__ import annotations

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Time
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers.new_zealand_wod import AREA_CATEGORIES
from src.providers.new_zealand_wod import FIRE_CAUSES
from src.providers.new_zealand_wod import SEASONS
from src.providers.new_zealand_wod import SOURCE_SRID
from src.providers.new_zealand_wod import SOURCES
from src.providers.new_zealand_wod.ignition import WodIgnition


def _in(column: str, values: tuple[str, ...]) -> str:
    """``column IN ('a', 'b', …)``, for a ``CHECK``."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class WodWildfire(Wildfire):
    """A New Zealand wildfire record.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the WOD ones are stored here, in ``wod_wildfire``,
    whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`. The local GisFIRE identifier,
        shared with the parent row.
    wod_id : str
        The published ``ID``, repaired by
        :func:`~src.providers.new_zealand_wod.wod_id`. **Unique** and stable across
        releases.
    source : str
        ``Source``: :data:`~src.providers.new_zealand_wod.SOURCE_FENZ` or
        :data:`~src.providers.new_zealand_wod.SOURCE_DOC`. ``NOT NULL``, constrained
        and indexed. Coverage depends on it entirely — DOC alone before 1998, FENZ
        alone after 2011 — so a series that ignores it is partly a series about
        record keeping.
    org_id : str or None
        ``OrgID``, the agency's own number: the CAD (Computer Aided Dispatch) number
        for FENZ. Indexed and **not unique**: 23 DOC numbers occur twice.
    dropped_fenz_org_id : str or None
        ``OrgIDDrop``, on DOC records only: the CAD number of a FENZ record of the
        same fire (same day, within 600 m) that the compilers dropped in favour of
        this one. 862 records. None of those numbers survives as a FENZ record, so
        the two agencies are not counted twice.
    year : int
        The published ``Year``. Indexed: it is how a year is re-imported and what
        reports group on.
    report_date : datetime.date
        The published ``Day``/``Month``/``Year``: the local date the fire was
        reported.
    report_time : datetime.time or None
        The published ``Time``, local wall-clock, to the minute. ``None`` where the
        record has none — **every DOC record** — in which case
        :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is local midnight
        of :attr:`report_date`. That ``None`` is what tells such a midnight from the
        41 fires really reported at 00:00.
    season : str
        ``Season``, one of :data:`~src.providers.new_zealand_wod.SEASONS`, summer
        being December-February.
    financial_year : int
        ``StartFY``: the calendar year the New Zealand fire year began in. A fire
        year runs 1 July to 30 June, so 1998 is 1998/1999, and it is how FENZ and the
        annual summaries count. ``EndFY`` and ``FY`` follow from it and are not
        stored.
    area_ha : float or None
        ``AreaHa``, the burnt area as reported, in hectares. Never negative: the one
        published −0.0001 is imported as 0. A **0 is a reported value** and is kept —
        28,273 records carry it — although the paper warns that three of the largest
        1999 fires had been recorded as 0 before the compilers corrected them, so a 0
        is not proof of a small fire.
    area_category : str or None
        ``AreaCat``, one of :data:`~src.providers.new_zealand_wod.AREA_CATEGORIES`.
        Stored as published; it is :attr:`area_ha` binned.
    ignition_source : str or None
        ``IgnSource``, the cause as the agency recorded it, stripped and otherwise
        verbatim, or ``None`` where the record has none — see
        :func:`~src.providers.new_zealand_wod.published_ignition_source`.
    fire_cause : str
        :attr:`ignition_source` classified by
        :func:`~src.providers.new_zealand_wod.fire_cause` into one of
        :data:`~src.providers.new_zealand_wod.FIRE_CAUSES`. ``NOT NULL``,
        constrained and indexed.
    original_vegetation : str or None
        ``OrgVeg``, the vegetation as described in the field. DOC records only, and
        a third of those.
    fenz_district : str or None
        ``FENZDist``, the FENZ district the point falls in. ``None`` for the 92
        records whose point is in the sea.
    perimeter_nztm : geoalchemy2.elements.WKBElement or None
        The published polygon in :data:`~src.providers.new_zealand_wod.SOURCE_SRID`
        (NZTM2000), made valid and stored as a ``MULTIPOLYGON``. ``None`` for the
        point records.
    ignition_id : int
        Foreign key to the
        :class:`~src.providers.new_zealand_wod.ignition.WodIgnition`. ``NOT NULL``
        and unique: every record has exactly one point.
    ignition : WodIgnition
        The published point.
    terrain : WodTerrain
        The topography and fuel attached by the compilers.
    weather : WodWeather
        The weather, fire danger and climate attached by the compilers.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is the **report**
    instant, not the ignition: the paper takes the report time as the best proxy,
    noting that New Zealand fires are typically reported within an hour.
    :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is always ``None``; the
    WOD publishes no end.
    """

    __tablename__ = "wod_wildfire"

    __table_args__ = (
        CheckConstraint(_in("source", SOURCES), name="ck_wod_wildfire_source"),
        CheckConstraint(_in("fire_cause", FIRE_CAUSES), name="ck_wod_wildfire_fire_cause"),
        CheckConstraint(_in("season", SEASONS), name="ck_wod_wildfire_season"),
        CheckConstraint("area_category IS NULL OR " + _in("area_category", AREA_CATEGORIES),
                        name="ck_wod_wildfire_area_category"),
        CheckConstraint("area_ha IS NULL OR area_ha >= 0", name="ck_wod_wildfire_area_ha"),
        CheckConstraint("year = EXTRACT(YEAR FROM report_date)",
                        name="ck_wod_wildfire_year"),
        CheckConstraint("financial_year IN (year - 1, year)",
                        name="ck_wod_wildfire_financial_year"),
        Index("ix_wod_wildfire_year", "year"),
        Index("ix_wod_wildfire_source", "source"),
        Index("ix_wod_wildfire_fire_cause", "fire_cause"),
        Index("ix_wod_wildfire_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    wod_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    org_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dropped_fenz_org_id: Mapped[str | None] = mapped_column(String, nullable=True)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    report_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    report_time: Mapped[datetime.time | None] = mapped_column(Time, nullable=True)
    season: Mapped[str] = mapped_column(String, nullable=False)
    financial_year: Mapped[int] = mapped_column(Integer, nullable=False)

    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_category: Mapped[str | None] = mapped_column(String, nullable=True)

    ignition_source: Mapped[str | None] = mapped_column(String, nullable=True)
    fire_cause: Mapped[str] = mapped_column(String, nullable=False)

    original_vegetation: Mapped[str | None] = mapped_column(String, nullable=True)
    fenz_district: Mapped[str | None] = mapped_column(String, nullable=True)

    perimeter_nztm: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=SOURCE_SRID), nullable=True
    )

    ignition_id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), nullable=False,
                                             unique=True)

    ignition: Mapped[WodIgnition] = relationship(foreign_keys=[ignition_id])
    terrain: Mapped["WodTerrain | None"] = relationship(  # noqa: F821
        back_populates="wildfire", cascade="all, delete-orphan", passive_deletes=True
    )
    weather: Mapped["WodWeather | None"] = relationship(  # noqa: F821
        back_populates="wildfire", cascade="all, delete-orphan", passive_deletes=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "wod_wildfire",
    }

    def __repr__(self) -> str:
        return f"WodWildfire(id={self.id!r}, wod_id={self.wod_id!r}, year={self.year!r})"
