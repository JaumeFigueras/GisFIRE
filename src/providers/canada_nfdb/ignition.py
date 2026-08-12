#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NFDB ignition model.

Where a Canadian fire was reported, as the agency filed it: a point on the NAD83 /
Canada Atlas Lambert grid.

The generic :class:`~src.data_model.ignition.Ignition` already holds the point in
EPSG:4326, the instant and the administrative boundary. This model adds the
published point **in the CRS it was published in**, and the two identifiers of the
row it came from.

The point is stored twice, on purpose
--------------------------------------

:attr:`~src.data_model.ignition.Ignition.geometry` is the reprojection to
EPSG:4326, which is what makes a Canadian fire comparable with any other and what
every cross-provider query uses. :attr:`NfdbIgnition.geometry_lambert` is the point
in :data:`~src.providers.canada_nfdb.SOURCE_SRID`, as published.

This is the same rule the perimeters follow — see
:mod:`src.providers.canada_nbac.wildfire` — applied to a point, and it is a
departure from :mod:`src.providers.greece_ffa.ignition`, which stores no second
copy. The difference is which CRS the source published in. Greece publishes WGS 84
degrees, so its geometry *is* the published pair and a copy would be the same two
numbers twice. Canada publishes metres on a national grid, so the EPSG:4326 point
is a **reprojection** — derived, not published — and the grid coordinates are the
original numbers.

Why the published ``LATITUDE`` and ``LONGITUDE`` are not stored
----------------------------------------------------------------

The shapefile carries them as attribute columns beside the geometry, and they are
not kept, which needs saying because this project's habit is to keep what a
provider published.

They are not an independent observation: they are the service's own convenience
reprojection of the same point, and where they disagree with the geometry it is
because they are wrong — the published ``LONGITUDE`` minimum is −5,617,700, an
easting that has leaked into a degrees column. 244 rows are like this.

So there is nothing to preserve. The import tests them with
:func:`~src.providers.canada_nfdb.is_located`, refuses the rows where they and the
geometry disagree, and stores the geometry — which leaves no row whose two copies
could differ, and therefore no reason for a third column.

There is one point per report, or none
---------------------------------------

An ``nfdb_ignition`` row means *this fire has a usable published location*.
:attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.ignition_id` is nullable
for the handful that do not, and after the import's filtering that is a very small
number — unlike Spain, where half the archive has no coordinate, and unlike Greece,
where four fires in five have none.

.. warning::

   **This is where the fire was reported, not necessarily where it started.** The
   published summary says so: *"Locations are approximate."* Thirteen agencies
   contribute at thirteen standards, and a point filed in 1975 from a lookout
   tower's bearing is not a point filed in 2020 from a GPS.

   It is modelled as an ignition because it is a point and an instant and that is
   what the generic model is. Treat the precision as varying by agency and by
   decade, and see :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.
   src_agency`.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition
from src.providers.canada_nfdb import SOURCE_SRID


class NfdbIgnition(Ignition):
    """The point a Canadian fire was reported at, as published.

    Uses joined table inheritance: the columns shared by every ignition live in the
    ``ignition`` table and only the Canadian ones are stored here, in
    ``nfdb_ignition``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE identifier,
        shared with the parent row.
    nfdb_fire_id : str or None
        The published ``NFDBFIREID`` of the row the point came from, the same value
        as :attr:`~src.providers.canada_nfdb.wildfire.NfdbWildfire.nfdb_fire_id`.
        Indexed and **not unique**: 1,684 of the published values are used by more
        than one row.
    year : int or None
        The published fire year. Indexed, and how a year is re-imported. ``None``
        where the service wrote its :data:`~src.providers.canada_nfdb.UNKNOWN_YEAR`
        sentinel.
    src_agency : str or None
        Which agency filed the point — ``BC``, ``AB``, ``ON``, ``PC``, … Carried
        here as well as on the fire because the precision of a *location* is a
        property of who recorded it, and a query about location quality should not
        have to join to find out.
    geometry_lambert : geoalchemy2.elements.WKBElement
        The point as published, in :data:`~src.providers.canada_nfdb.SOURCE_SRID`
        (NAD83 / Canada Atlas Lambert). ``NOT NULL``: an ignition row exists only
        where there is a usable point, and this is the published one it exists
        because of.

    Notes
    -----
    No unique constraint. Nothing in this dataset identifies a fire — see
    :mod:`src.providers.canada_nfdb` — so any constraint here would be a claim the
    published data does not support.

    :attr:`~src.data_model.ignition.Ignition.date_time` is the same instant as the
    fire's :attr:`~src.data_model.wildfire.Wildfire.start_date_time`: both are the
    published ``REP_DATE``, which is the only date the agency reports for the start.
    """

    __tablename__ = "nfdb_ignition"

    __table_args__ = (
        Index("ix_nfdb_ignition_nfdb_fire_id", "nfdb_fire_id"),
        Index("ix_nfdb_ignition_year", "year"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    nfdb_fire_id: Mapped[str | None] = mapped_column(String, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    src_agency: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_lambert: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID), nullable=False
    )

    __mapper_args__ = {
        "polymorphic_identity": "nfdb_ignition",
    }

    def __repr__(self) -> str:
        return (f"NfdbIgnition(id={self.id!r}, nfdb_fire_id={self.nfdb_fire_id!r}, "
                f"year={self.year!r})")
