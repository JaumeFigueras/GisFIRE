#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MeteoCat lightning model.

One row per stroke located by the XDDE, MeteoCat's lightning-detection network.

The generic :class:`~src.data_model.lightning.Lightning` already holds the
instant, the point in EPSG:4326, the signed peak current, whether the stroke was
cloud-to-ground and the administrative boundary. This model adds what is
particular to the XDDE: the published point **in the CRS it was published in**,
the flash the stroke belongs to, how well it was located, and which generation of
the network located it.

See :mod:`src.providers.catalonia_meteocat` for the dataset itself.

The point is stored twice
-------------------------

:attr:`MeteocatLightning.geometry_etrs89` is the published ``longitud``/``latitud``
in ETRS89 (EPSG:4258), untouched; the parent's ``geometry`` is its EPSG:4326
reprojection, which is what lets a stroke be compared with every other dataset.
The two differ by well under a metre, but the published value is the observation
and is kept as such.

Flashes: multiplicity and stroke index
--------------------------------------

A flash is identified by ``(network_version, flash_id)`` — the two networks number
their flashes independently. Both values below are computed by the import, over
the strokes of a flash, ordered by instant (and, for the few strokes sharing an
instant, by their order in the file):

* :attr:`MeteocatLightning.multiplicity` — how many strokes the flash has, the same
  on every stroke of it;
* :attr:`MeteocatLightning.stroke_index` — the position of the stroke in the
  flash, from 1. ``stroke_index = 1`` selects the first stroke of every flash,
  which is what flash-density maps count and what tells a first stroke from a
  subsequent one without a window function over the whole table.

Not recorded is ``NULL``, not ``0``
-----------------------------------

The first generation of the network did not record the number of sensors or the
chi-squared, and published ``0`` for both. A count of zero sensors cannot locate
anything, so the import stores those as ``NULL``; the ``CHECK`` constraints below
refuse a ``0`` sensor count so that a version-1 ``0`` cannot slip through as a
value.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.lightning import Lightning
from src.providers.catalonia_meteocat import PROJECTED_SRID
from src.providers.catalonia_meteocat import SOURCE_SRID

#: The ETRS89 point reprojected to ETRS89 / UTM 31N, cast back so it keeps its type
#: and SRID. The ``v_meteocat_lightning_25831`` view selects this expression and an
#: expression index is built on it; the planner uses the index only while the two
#: are the same expression. Written the way PostgreSQL prints it back (lower case,
#: ``::`` cast, outer parentheses — which ``CREATE INDEX`` needs around anything
#: that is not a bare function call), because that is the text Alembic compares the
#: index against.
GEOMETRY_25831 = (f"(st_transform({{column}}, {PROJECTED_SRID})"
                  f"::geometry(Point,{PROJECTED_SRID}))")


class MeteocatLightning(Lightning):
    """A stroke located by MeteoCat's XDDE network, as published.

    Uses joined table inheritance: the columns shared by every stroke live in the
    ``lightning`` table and only the MeteoCat ones are stored here, in
    ``meteocat_lightning``, whose primary key is also a foreign key to the parent
    row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.lightning.Lightning.id`. The local GisFIRE
        identifier, shared with the parent row.
    network_version : int
        Generation of the network that located the stroke, one of the keys of
        :data:`~src.providers.catalonia_meteocat.NETWORK_VERSIONS`.
    flash_id : int
        The published ``secidx``: the flash the stroke belongs to. Unique only
        together with :attr:`network_version`, and not unique per stroke.
        Indexed with it.
    multiplicity : int
        Number of strokes of the flash. At least 1.
    stroke_index : int
        Position of the stroke in its flash, from 1 to :attr:`multiplicity`.
    chi_squared : float or None
        Chi-squared of the location fit, ``None`` where the network did not
        record it (version 1). Not negative.
    ellipse_major_axis : float
        Major axis of the location confidence ellipse, in metres. Not negative.
    ellipse_minor_axis : float
        Minor axis of the location confidence ellipse, in metres. Not negative
        and not larger than the major axis.
    ellipse_angle : float or None
        Orientation of the ellipse, in degrees, as the API publishes it.
        ``None`` for strokes from the CSV delivery, which does not include it.
    number_of_sensors : int or None
        Number of sensors that detected the stroke, ``None`` where the network
        did not record it (version 1). At least 1.
    municipality_code : str or None
        Six-digit INE code of the Catalan municipality the stroke fell in, as
        published; ``None`` outside Catalonia.
    geometry_etrs89 : geoalchemy2.elements.WKBElement
        The published ``longitud``/``latitud`` in
        :data:`~src.providers.catalonia_meteocat.SOURCE_SRID` (ETRS89),
        untouched.
    """

    __tablename__ = "meteocat_lightning"

    __table_args__ = (
        CheckConstraint("network_version >= 1", name="ck_meteocat_lightning_network_version"),
        CheckConstraint("multiplicity >= 1", name="ck_meteocat_lightning_multiplicity"),
        CheckConstraint("stroke_index >= 1 AND stroke_index <= multiplicity",
                        name="ck_meteocat_lightning_stroke_index"),
        CheckConstraint("chi_squared >= 0", name="ck_meteocat_lightning_chi_squared"),
        CheckConstraint("ellipse_minor_axis >= 0 AND ellipse_minor_axis <= ellipse_major_axis",
                        name="ck_meteocat_lightning_ellipse_axes"),
        CheckConstraint("number_of_sensors >= 1", name="ck_meteocat_lightning_number_of_sensors"),
        CheckConstraint("municipality_code ~ '^[0-9]{6}$'",
                        name="ck_meteocat_lightning_municipality_code"),
        Index("ix_meteocat_lightning_flash", "network_version", "flash_id"),
        # Behind the ``v_meteocat_lightning_25831`` view, which selects exactly this
        # expression: see GEOMETRY_25831.
        Index("idx_meteocat_lightning_geometry_25831",
              text(GEOMETRY_25831.format(column="geometry_etrs89")),
              postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Lightning.id), primary_key=True)
    network_version: Mapped[int] = mapped_column(Integer, nullable=False)
    flash_id: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplicity: Mapped[int] = mapped_column(Integer, nullable=False)
    stroke_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chi_squared: Mapped[float | None] = mapped_column(Float, nullable=True)
    ellipse_major_axis: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_minor_axis: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    number_of_sensors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    municipality_code: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_etrs89: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID), nullable=False
    )

    __mapper_args__ = {
        "polymorphic_identity": "meteocat_lightning",
    }

    def __repr__(self) -> str:
        return (f"MeteocatLightning(id={self.id!r}, date_time={self.date_time!r}, "
                f"network_version={self.network_version!r}, flash_id={self.flash_id!r})")
