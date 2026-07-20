#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCHA administrative boundary model.

The *Global International Boundaries (OSM)* layer supplies, for each country, a
name, a geometry and a nesting level — exactly what the generic
:class:`~src.data_model.geography.admin_boundary.AdminBoundary` already holds —
plus the identifiers and metadata this model adds: the ISO country codes, the UN
M49 region the division belongs to, its statehood status and the provenance of
the geometry.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.geography.admin_boundary import AdminBoundary


class OchaAdminBoundary(AdminBoundary):
    """An administrative division as published by OCHA's international boundaries.

    Sourced from *Global International Boundaries (OSM)* on HDX,
    https://data.humdata.org/dataset/global-international-boundaries-osm.

    Uses joined table inheritance: the columns shared by every boundary live in
    the ``admin_boundary`` table and only the OCHA-specific ones are stored here,
    in ``ocha_admin_boundary``, whose primary key is also a foreign key to the
    parent row.

    The layer's ``fid`` is not kept: it is the GeoPackage's own row number, which
    changes between releases. ``adm0_id`` — which carries the release date, as in
    ``"AND-20250729"`` — is the stable identifier, and is stored on the parent
    row as :attr:`~src.data_model.geography.admin_boundary.AdminBoundary.source_id`.
    The layer's ``adm0_name`` maps onto the parent's ``name``; ``adm0_name1`` is a
    different thing despite the name and is kept here as :attr:`iso_name`.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.geography.admin_boundary.AdminBoundary.id`. This is
        the local GisFIRE identifier, shared with the parent row.
    source : str
        The layer's ``adm0_src``: which authority the division's definition comes
        from, usually the ISO 3166-1 alpha-3 code of the country that claims it.
    name_alt : str or None
        The layer's ``adm0_name2``: an alternative name for the division, where
        one exists. Empty for every feature of the 2025-07-29 release.
    iso_code : int
        The layer's ``iso_cd``: ISO 3166-1 numeric country code.
    iso_2 : str or None
        ISO 3166-1 alpha-2 country code (``"AD"``), or ``None``. Disputed and
        jointly administered areas have no alpha-2 code — 36 of the 318 features
        of the 2025-07-29 release, Abyei and Jammu and Kashmir among them — even
        though every one of them has an alpha-3 code in :attr:`iso_3`.
    iso_3 : str
        ISO 3166-1 alpha-3 country code (``"AND"``). **Not unique**: a single ISO
        entity may be published as several features, one per landmass — ``ATF``
        covers eight scattered island groups, each its own row.
    iso_name : str
        The layer's ``adm0_name1``: the name of the ISO entity :attr:`iso_3`
        stands for, which is not the name of this particular feature. Kerguelen
        is ``name="Kerguelen Islands (Fr.)"`` but
        ``iso_name="French Southern Territories"``, the ISO name it shares with
        the seven other ``ATF`` islands. The two agree for most countries and
        differ for 118 of the 318 features.
    iso_3_group : str
        The layer's ``iso_3_grp``: alpha-3 code of the country this division is
        grouped under for reporting, which differs from :attr:`iso_3` for
        dependencies and disputed territories.
    region1_code, region2_code, region3_code : int
        UN M49 codes of the three nested regions the division sits in, from
        continent (``150``, Europe) down to sub-region (``39``, Southern Europe).
    region1_name, region2_name, region3_name : str
        Names of those three regions.
    status_code : int
        The layer's ``status_cd``: statehood status code.
    status_name : str
        The layer's ``status_nm``, the status in words (``"State"``).
    valid_date : datetime.date
        The layer's ``wld_date``: the date the boundary is valid as of.
    update_date : datetime.date
        The layer's ``wld_update``: the date OCHA last revised the record. Also
        the suffix of ``adm0_id``.
    land_source : str
        The layer's ``wld_land``: provenance of the land geometry (``"osm"``).
    view : str
        The layer's ``wld_view``: whose view of the boundary this is
        (``"intl"`` for the international one). Contested boundaries are
        published once per view, which is why a country can appear more than once
        in the layer.
    notes : str or None
        The layer's ``wld_notes``: free-text remarks, where any.

    Notes
    -----
    The ``region*`` columns are a hierarchy of their own — Europe contains
    Southern Europe contains Andorra — that OCHA flattens into columns. They are
    kept flat here rather than turned into
    :class:`~src.data_model.geography.admin_boundary.AdminBoundary` rows because
    the layer gives them no geometry, and a boundary row without one would be a
    different kind of thing. If those regions are ever needed as clipping areas,
    build them as their own rows from a union of their members.
    """

    __tablename__ = "ocha_admin_boundary"

    id: Mapped[int] = mapped_column(ForeignKey(AdminBoundary.id), primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    name_alt: Mapped[str | None] = mapped_column(String, nullable=True)
    iso_code: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_2: Mapped[str | None] = mapped_column(String, nullable=True)
    iso_3: Mapped[str] = mapped_column(String, nullable=False)
    iso_name: Mapped[str] = mapped_column(String, nullable=False)
    iso_3_group: Mapped[str] = mapped_column(String, nullable=False)
    region1_code: Mapped[int] = mapped_column(Integer, nullable=False)
    region1_name: Mapped[str] = mapped_column(String, nullable=False)
    region2_code: Mapped[int] = mapped_column(Integer, nullable=False)
    region2_name: Mapped[str] = mapped_column(String, nullable=False)
    region3_code: Mapped[int] = mapped_column(Integer, nullable=False)
    region3_name: Mapped[str] = mapped_column(String, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    status_name: Mapped[str] = mapped_column(String, nullable=False)
    valid_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    update_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    land_source: Mapped[str] = mapped_column(String, nullable=False)
    view: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "ocha_admin_boundary",
    }

    def __repr__(self) -> str:
        return f"OchaAdminBoundary(id={self.id!r}, iso_3={self.iso_3!r}, name={self.name!r})"
