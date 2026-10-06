#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WOD ignition model.

Where a New Zealand wildfire was recorded: the published ``X``/``Y``, on the NZTM2000
grid.

The generic :class:`~src.data_model.ignition.Ignition` already holds the point in
EPSG:4326, the instant and the administrative boundary. This model adds the
published point **in the CRS it was published in**, the record's identifier and the
two columns a location query wants without a join.

Every record has one, and it is never moved
--------------------------------------------

Unlike NFDB's, this point is not filtered. The paper is explicit that every record
has a point, taken from the NZTM coordinates of the original record, and the import
stores all of them as published:

* the **92 points in the sea**, which have no FENZ district and therefore no
  :attr:`~src.data_model.ignition.Ignition.admin_boundary_id` either;
* the **15 FENZ points on the placeholder coordinate**
  (:data:`~src.providers.new_zealand_wod.PLACEHOLDER_X`,
  :data:`~src.providers.new_zealand_wod.PLACEHOLDER_Y`), also in the sea;
* the point of every **polygon record**, which is the location of the original
  record and *not* derived from the polygon — it is neither the centroid nor the
  origin, and only 21% of them fall inside their own perimeter.

The point is stored twice, on purpose: :attr:`WodIgnition.geometry_nztm` as published
and the parent's ``geometry`` as its EPSG:4326 reprojection, which is the NFDB rule.
The published ``Lat``/``Lon`` are not stored: they agree with that reprojection to
1e-9 degrees, so they are a copy and not an observation.

.. warning::

   **This is where the fire was reported, not necessarily where it started**, and
   :attr:`~src.data_model.ignition.Ignition.date_time` is when it was reported. FENZ
   records were historically tied to a road, often a roadside address, even for a
   fire away from the road — the paper warns that this can exaggerate the role of
   roads. For DOC records, which carry no time, the instant is local midnight.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition
from src.providers.new_zealand_wod import SOURCE_SRID
from src.providers.new_zealand_wod import SOURCES


class WodIgnition(Ignition):
    """The point a New Zealand wildfire was recorded at, as published.

    Uses joined table inheritance: the columns shared by every ignition live in the
    ``ignition`` table and only the WOD ones are stored here, in ``wod_ignition``,
    whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE identifier,
        shared with the parent row.
    wod_id : str
        The published ``ID`` of the record the point came from, repaired by
        :func:`~src.providers.new_zealand_wod.wod_id`. **Unique**: one record, one
        point.
    year : int
        The published year. Indexed: it is how a year is re-imported.
    source : str
        Who recorded the point, :data:`~src.providers.new_zealand_wod.SOURCE_FENZ` or
        :data:`~src.providers.new_zealand_wod.SOURCE_DOC`. Carried here as well as on
        the fire because the precision of a location is a property of who recorded
        it.
    geometry_nztm : geoalchemy2.elements.WKBElement
        The published ``X``/``Y`` in :data:`~src.providers.new_zealand_wod.SOURCE_SRID`
        (NZTM2000), untouched.
    """

    __tablename__ = "wod_ignition"

    __table_args__ = (
        CheckConstraint(
            "source IN (" + ", ".join(f"'{source}'" for source in SOURCES) + ")",
            name="ck_wod_ignition_source",
        ),
        Index("ix_wod_ignition_year", "year"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    wod_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    geometry_nztm: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID), nullable=False
    )

    __mapper_args__ = {
        "polymorphic_identity": "wod_ignition",
    }

    def __repr__(self) -> str:
        return f"WodIgnition(id={self.id!r}, wod_id={self.wod_id!r}, year={self.year!r})"
