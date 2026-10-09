#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Korea Forest Service wildfire model.

One row per fire of the KFS wildfire statistics. The generic
:class:`~src.data_model.wildfire.Wildfire` holds the start and the end of
suppression; this model adds the year, where the fire was filed, its cause and
the burnt area.

See :mod:`src.providers.south_korea_kfs` for the dataset itself.

There is no geometry
--------------------

:attr:`~src.data_model.wildfire.Wildfire.perimeter` is ``NULL`` on every row and
there is no ignition: the statistics publish neither a shape nor a coordinate,
only names. :attr:`~src.data_model.wildfire.Wildfire.admin_boundary_id` is
``NULL`` as well — it is the result of a point-in-polygon test, and there is no
point to test. Placing these fires on a map means matching the names against
Korean administrative boundaries, which GisFIRE does not hold yet.

The names are stored twice
--------------------------

Each place name is stored as published (trimmed, ``NULL`` when blank) and in the
Revised Romanization (``*_rr``), computed by
:func:`~src.providers.south_korea_kfs.romanize` when the row is imported. The
Korean is the data; the romanization is there so that a reader who does not
read Hangul can tell the rows apart.

A ``NULL`` township is a city neighbourhood, not a missing value, and a ``NULL``
municipality is Sejong (or, on two rows, an omission). See the provider module.

The cause is stored four ways
-----------------------------

As published, in :attr:`cause_category_code`, :attr:`cause_detail` and
:attr:`cause_text`; translated, in :attr:`cause_text_en`; classified, in
:attr:`cause_class`, one of the eighteen
:data:`~src.providers.south_korea_kfs.CAUSE_CLASSES`; and reduced to
:attr:`fire_cause`, one of the four
:data:`~src.providers.south_korea_kfs.FIRE_CAUSES` shared with the New Zealand
WOD. The two classifications are constrained; the published code is not — four
letters observed in one release are not a vocabulary a ``CHECK`` should freeze.
"""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.wildfire import Wildfire
from src.providers.south_korea_kfs import CAUSE_CLASSES
from src.providers.south_korea_kfs import END_DATE_PROBLEMS
from src.providers.south_korea_kfs import FIRE_CAUSES


def _in(column: str, values: tuple[str, ...]) -> str:
    """``column IN ('a', 'b', …)``, for a ``CHECK``."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class KfsWildfire(Wildfire):
    """A fire of the Korea Forest Service wildfire statistics.

    Uses joined table inheritance: the columns shared by every wildfire live in the
    ``wildfire`` table and only the Korean ones are stored here, in
    ``kfs_wildfire``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.wildfire.Wildfire.id`.
    year : int
        ``발생일시_년``, the year the fire started. ``NOT NULL`` and indexed: it is
        what an import replaces, since nothing identifies a single fire.
    source_file : str
        The name of the file the row was read from — the release.
    source_row : int
        The row's line in that file, the header being line 1. With
        :attr:`source_file`, the only way to point back at a published row.
    office_name, office_name_rr : str
        ``발생장소_관서``, the filing office, and its romanization.
    province_name, province_name_rr : str
        ``발생장소_시도``, the province abbreviation (``경북``), and its
        romanization (``Gyeongbuk``).
    municipality_name, municipality_name_rr : str or None
        ``발생장소_시군구``, without its suffix. ``None`` for Sejong.
    township_name, township_name_rr : str or None
        ``발생장소_읍면``. ``None`` for a city neighbourhood.
    village_name, village_name_rr : str or None
        ``발생장소_동리``, the village or neighbourhood.
    cause_category_code : str or None
        ``발생원인_구분``, as published: ``입``, ``쓰``, ``담``, ``기`` or ``None``.
    cause_detail : str
        ``발생원인_세부원인``, as published.
    cause_text : str
        ``발생원인_기타``, the cause in words, as published but trimmed.
    cause_text_en : str
        Its English translation.
    cause_class : str
        One of :data:`~src.providers.south_korea_kfs.CAUSE_CLASSES`. Indexed.
    fire_cause : str
        One of :data:`~src.providers.south_korea_kfs.FIRE_CAUSES`. Indexed.
    cause_suspected : bool
        Whether the text gives the cause as suspected or under investigation.
    area_ha : float
        ``피해면적_합계``, the burnt area in hectares, as published.
    end_date_problem : str or None
        Why :attr:`~src.data_model.wildfire.Wildfire.end_date_time` is ``NULL``
        although an end was published — one of
        :data:`~src.providers.south_korea_kfs.END_DATE_PROBLEMS` — or ``None``
        when the end is stored.

    Notes
    -----
    :attr:`~src.data_model.wildfire.Wildfire.start_date_time` is when the fire
    started (``발생일시``) and :attr:`~src.data_model.wildfire.Wildfire.end_date_time`
    when suppression ended (``진화종료시간``), both read in ``Asia/Seoul``.
    """

    __tablename__ = "kfs_wildfire"
    __table_args__ = (
        CheckConstraint(_in("cause_class", CAUSE_CLASSES),
                        name="ck_kfs_wildfire_cause_class"),
        CheckConstraint(_in("fire_cause", FIRE_CAUSES),
                        name="ck_kfs_wildfire_fire_cause"),
        CheckConstraint("end_date_problem IS NULL OR "
                        + _in("end_date_problem", END_DATE_PROBLEMS),
                        name="ck_kfs_wildfire_end_date_problem"),
        CheckConstraint("area_ha >= 0", name="ck_kfs_wildfire_area_ha"),
        Index("ix_kfs_wildfire_year", "year"),
        Index("ix_kfs_wildfire_province_name", "province_name"),
        Index("ix_kfs_wildfire_cause_class", "cause_class"),
        Index("ix_kfs_wildfire_fire_cause", "fire_cause"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Wildfire.id), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file: Mapped[str] = mapped_column(String, nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    office_name: Mapped[str] = mapped_column(String, nullable=False)
    office_name_rr: Mapped[str] = mapped_column(String, nullable=False)
    province_name: Mapped[str] = mapped_column(String, nullable=False)
    province_name_rr: Mapped[str] = mapped_column(String, nullable=False)
    municipality_name: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality_name_rr: Mapped[str | None] = mapped_column(String, nullable=True)
    township_name: Mapped[str | None] = mapped_column(String, nullable=True)
    township_name_rr: Mapped[str | None] = mapped_column(String, nullable=True)
    village_name: Mapped[str | None] = mapped_column(String, nullable=True)
    village_name_rr: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_category_code: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_detail: Mapped[str] = mapped_column(String, nullable=False)
    cause_text: Mapped[str] = mapped_column(String, nullable=False)
    cause_text_en: Mapped[str] = mapped_column(String, nullable=False)
    cause_class: Mapped[str] = mapped_column(String, nullable=False)
    fire_cause: Mapped[str] = mapped_column(String, nullable=False)
    cause_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    end_date_problem: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "kfs_wildfire",
    }

    def __repr__(self) -> str:
        return (f"KfsWildfire(id={self.id!r}, year={self.year!r}, "
                f"source_row={self.source_row!r})")
