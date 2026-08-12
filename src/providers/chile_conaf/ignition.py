#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONAF ignition model (Chile).

Where a Chilean fire was reported, as the office filed it: a point on one of the
two UTM grids CONAF publishes on.

The generic :class:`~src.data_model.ignition.Ignition` already holds the point in
EPSG:4326, the instant and the administrative boundary. This model adds the
published point **in the CRS it was published in**, the published coordinate
triple beside it, and the two numbers that locate the row in its archive.

Two projected columns, because Chile has two grids
----------------------------------------------------

:mod:`src.providers.canada_nfdb` stores one ``geometry_lambert`` because Canada
publishes on one national grid. Chile does not have one. The mainland archives are
on :data:`~src.providers.chile_conaf.SOURCE_SRID_MAINLAND` (UTM 19S) and the
Easter Island archives on
:data:`~src.providers.chile_conaf.SOURCE_SRID_EASTER` (UTM 12S), which are seven
zones and five thousand kilometres apart; no projected CRS covers both without
distorting one of them past usefulness.

So there are two nullable columns and a ``CHECK`` that exactly one is filled.
:attr:`geometry_utm19s` holds 95,625 points and :attr:`geometry_utm12s` holds 243.
Both are the geometry *as published*; the parent's EPSG:4326 point is the
reprojection, derived from whichever of the two this row has.

A ``COALESCE`` of the two is not a geometry — the values are metres on different
grids and adding them would be adding apples to kilometres. A query that wants
both datasets at once wants the parent's EPSG:4326 point, which is what it is for.

The published coordinate is kept as numbers
---------------------------------------------

:attr:`utm_easting`, :attr:`utm_northing`, :attr:`utm_zone` and :attr:`utm_band`
are the ``UTM_E``, ``UTM_N`` and ``HUSO`` cells, read by
:func:`~src.providers.chile_conaf.published_utm`. They are **provenance, not a
second geometry**: the point that is stored comes from the shapefile's own
geometry.

They are kept because they are what CONAF prints in its own reports, and because
the zone is information the geometry does not carry — a mainland fire published as
zone 18 has been reprojected into zone 19 to sit in its layer, and
:attr:`utm_zone` is the only record of which grid the office actually worked on.

They are absent on more than half the rows: 43,636 of the 95,868 features publish
a readable triple, the rest publishing no ``HUSO``, a zeroed pair, or both. Where
both exist they agree with the geometry exactly — checked over the whole archive —
which is what licenses treating the geometry as the truth and these as the record.

.. warning::

   **This is where the fire was reported, not necessarily where it started.** The
   report archive's points are filed by CONAF's regional offices and by the
   forestry companies' own brigades — see
   :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.reporter` — and the
   most common ``INICIO_C``, the place the fire started, is *camino principal* or
   *camino secundario*: a road. A fire recorded at the road it was seen from is
   still recorded at a road.

   It is modelled as an ignition because it is a point and an instant, which is
   what the generic model is. Treat the precision as varying by season, by region
   and by who filed it.

One point per report
---------------------

Every one of the 95,868 published features carries a geometry — there are no
exceptions, checked — so there is one ``conaf_ignition`` row per report and
:attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.ignition_id` is
``NOT NULL``. That is unlike Spain, where half the archive has no coordinate,
unlike Greece, where four fires in five have none, and unlike
:mod:`src.providers.canada_nfdb`, where a handful do not.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition
from src.providers.chile_conaf import SOURCE_SRID_EASTER
from src.providers.chile_conaf import SOURCE_SRID_MAINLAND
from src.providers.chile_conaf import UTM_ZONES


class ConafIgnition(Ignition):
    """The point a Chilean fire was reported at, as published.

    Uses joined table inheritance: the columns shared by every ignition live in the
    ``ignition`` table and only the Chilean ones are stored here, in
    ``conaf_ignition``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE identifier,
        shared with the parent row.
    season_start_year : int
        First year of the ``TEMPORADA`` the point was published in — ``2010`` for
        ``"2010-2011"``. ``NOT NULL`` and indexed: it is how a season is
        re-imported and what every report groups on.
    number : int or None
        The published ``NUMERO_REG``, the office's own running number for the fire.
        Carried here as well as on the report because it is half of what the
        perimeter binder matches on, and a binding query should not have to join to
        get it. ``None`` where the archive publishes zero or nothing, which is
        every fire of 2010-2011 and 2013-2014.

        **Not a key.** See :mod:`src.providers.chile_conaf`.
    region_code : str or None
        The zero-padded ``CODREG`` — ``'08'`` for Biobío. The other half of the
        binder's strongest rule, here for the same reason as :attr:`number`.
    utm_easting : decimal.Decimal or None
        The published ``UTM_E``, read by
        :func:`~src.providers.chile_conaf.published_utm`. Provenance; see the
        module docstring.
    utm_northing : decimal.Decimal or None
        The published ``UTM_N``.
    utm_zone : int or None
        The UTM zone the pair above is on, from ``HUSO``: one of
        :data:`~src.providers.chile_conaf.UTM_ZONES`. **This is not the zone the
        geometry is on** — a zone 18 fire is reprojected into zone 19 to sit in its
        mainland layer — it is the zone the office worked in.
    utm_band : str or None
        The MGRS latitude band letter, where ``HUSO`` carries one: the ``K`` of
        ``'19K'``. ``None`` for the seasons that publish a bare ``'19'``.
    geometry_utm19s : geoalchemy2.elements.WKBElement or None
        The point as published on
        :data:`~src.providers.chile_conaf.SOURCE_SRID_MAINLAND`, for a mainland
        fire. 95,625 rows.
    geometry_utm12s : geoalchemy2.elements.WKBElement or None
        The point as published on
        :data:`~src.providers.chile_conaf.SOURCE_SRID_EASTER`, for an Easter Island
        fire. 243 rows.

    Notes
    -----
    No unique constraint. Nothing in this dataset identifies a fire — see
    :mod:`src.providers.chile_conaf` — so any constraint here would be a claim the
    published data does not support.

    :attr:`~src.data_model.ignition.Ignition.date_time` is the same instant as the
    fire's :attr:`~src.data_model.wildfire.Wildfire.start_date_time`: CONAF
    publishes one start for both, and for half the archive that start is the first
    instant of the season rather than a time anybody observed.
    """

    __tablename__ = "conaf_ignition"

    __table_args__ = (
        #: Exactly one grid, never both and never neither. The point is the reason
        #: this row exists, so a row with no published geometry at all is not a
        #: thinner row — it is a row that should not have been written.
        CheckConstraint(
            "num_nonnulls(geometry_utm19s, geometry_utm12s) = 1",
            name="ck_conaf_ignition_one_grid",
        ),
        CheckConstraint(
            "utm_zone IS NULL OR utm_zone IN ("
            + ", ".join(str(zone) for zone in UTM_ZONES) + ")",
            name="ck_conaf_ignition_utm_zone",
        ),
        Index("ix_conaf_ignition_season_start_year", "season_start_year"),
        Index("ix_conaf_ignition_number", "number"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    season_start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region_code: Mapped[str | None] = mapped_column(String, nullable=True)
    utm_easting: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    utm_northing: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    utm_zone: Mapped[int | None] = mapped_column(Integer, nullable=True)
    utm_band: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_utm19s: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID_MAINLAND), nullable=True
    )
    geometry_utm12s: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID_EASTER), nullable=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "conaf_ignition",
    }

    def __repr__(self) -> str:
        return (f"ConafIgnition(id={self.id!r}, "
                f"season_start_year={self.season_start_year!r}, "
                f"number={self.number!r})")
