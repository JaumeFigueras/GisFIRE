#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alaska lightning model.

One row per stroke of the Alaska Lightning Detection Network, as released by the
U.S. Wildland Fire Service.

The generic :class:`~src.data_model.lightning.Lightning` already holds the
instant, the point in EPSG:4326, the signed peak current, whether the stroke was
cloud-to-ground and the administrative boundary. This model adds what is
particular to the network: the flash the import groups the stroke into, how well
it was located, and the two counters the release carries.

See :mod:`src.providers.alaska_uswfs` for the release itself.

From the published fields to the columns
----------------------------------------

=====================  ==============================================================
Published              Stored
=====================  ==============================================================
``UTCDATETIME``        parent's ``date_time``, with the ``MILLISECONDS`` added
``MILLISECONDS``       (the fraction of the second, despite the metadata)
``LATITUDE``,          parent's ``geometry``, as published: WGS 84 is EPSG:4326, so
``LONGITUDE``          there is no second point to keep
``AMPLITUDE``          parent's ``peak_current``, **A → kA**; ``NULL`` on a cloud
                       stroke, whose 0 is not a measurement
``STROKETYPE``         parent's ``cloud_to_ground`` = ``STROKETYPE == GROUND_STROKE``
``NETWORKCODE``        :attr:`AlaskaUswfsLightning.network_code`
``GDOP``               :attr:`AlaskaUswfsLightning.gdop`
``ERRSEMIMAJOR``       :attr:`AlaskaUswfsLightning.ellipse_semi_major_axis`, **km → m**;
                       ``NULL`` when published 0
``ERRSEMIMINOR``       :attr:`AlaskaUswfsLightning.ellipse_semi_minor_axis`, **km → m**
``ERRELIPSEANGLE``     :attr:`AlaskaUswfsLightning.ellipse_angle`
``STRIKESEQNUMBER``    :attr:`AlaskaUswfsLightning.sequence_number`
``LOCALDATETIME``      not stored: three different offsets over the years, wrong for
                       12.6 % of the rows
``STRIKETIME``         not stored: ``LOCALDATETIME`` cut to the minute
``POLARITY``           not stored: the sign of the amplitude (and missing or wrong
                       on some strokes)
=====================  ==============================================================

The ellipse is published as semi-axes and stored under that name, in metres like
MeteoCat's and FMI's axes. Whether those two publish semi-axes or full axes is
not documented, so a location error read from different providers need not mean
the same.

Flashes: computed, not published
--------------------------------

The network publishes strokes only. The import groups them into flashes (the rule
is in :mod:`src.providers.alaska_uswfs`) and stores three values, which mean the
same as MeteoCat's and FMI's, so that the same query works on the three
providers:

* :attr:`AlaskaUswfsLightning.flash_id` — the local identifier of the flash's
  **first stroke**, the same on every stroke of the flash. Unique in the database
  without a counter of its own.
* :attr:`AlaskaUswfsLightning.multiplicity` — how many strokes the flash has.
* :attr:`AlaskaUswfsLightning.stroke_index` — the position of the stroke in the
  flash, from 1, by instant and then by the import's order for strokes of the same
  millisecond.

The import draws the identifiers in the same order — by instant, then by value —
so the first stroke of a flash always has its smallest identifier. Two CHECKs hold
the model to that: ``flash_id`` is never larger than ``id``, and it equals ``id``
on exactly the stroke whose ``stroke_index`` is 1. ``stroke_index = 1`` is then
one point per flash, its first stroke, as for the other two providers.

The projected point
-------------------

The point lives on ``lightning``, not here, so the index behind the
``v_alaska_uswfs_lightning_3338`` view is on ``lightning`` too: a **partial**
expression index, over this provider's strokes only (``WHERE type =
'alaska_uswfs_lightning'``), declared here and attached to the parent table.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import SmallInteger
from sqlalchemy import text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.lightning import Lightning
from src.providers.alaska_uswfs import PROJECTED_SRID

#: The polymorphic identity, and the value of ``lightning.type`` the partial index
#: and the views filter on.
IDENTITY = "alaska_uswfs_lightning"

#: The parent's EPSG:4326 point reprojected to NAD83 / Alaska Albers, cast back so
#: it keeps its type and SRID. The ``v_alaska_uswfs_lightning_3338`` view selects this
#: expression and the partial index below is built on it; written the way
#: PostgreSQL prints it back, for the reason given at
#: :data:`src.providers.catalonia_meteocat.lightning.GEOMETRY_25831`.
GEOMETRY_3338 = (f"(st_transform({{column}}, {PROJECTED_SRID})"
                 f"::geometry(Point,{PROJECTED_SRID}))")


class AlaskaUswfsLightning(Lightning):
    """A stroke of the Alaska Lightning Detection Network.

    Uses joined table inheritance: the columns shared by every stroke live in the
    ``lightning`` table and only the network's own are stored here, in
    ``alaska_uswfs_lightning``, whose primary key is also a foreign key to the parent
    row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.lightning.Lightning.id`. The local GisFIRE
        identifier, shared with the parent row.
    flash_id : int
        The flash the stroke belongs to, computed by the import: the :attr:`id` of
        the flash's first stroke. Never larger than :attr:`id`, and equal to it on
        the first stroke only. Indexed.
    multiplicity : int
        Number of strokes of the flash, computed by the import. At least 1.
    stroke_index : int
        Position of the stroke in its flash, from 1 to :attr:`multiplicity`.
    network_code : int
        The published ``NETWORKCODE``; ``0`` on every stroke of the 2012-2026
        release. Not negative.
    sequence_number : int or None
        The published ``STRIKESEQNUMBER``, a 16-bit counter of the processor (0 to
        65535) that wraps and repeats: it identifies nothing. ``None`` where it is
        not published (the first eight strokes of 2012). Not negative.
    gdop : int
        The published ``GDOP``, geometric dilution of precision of the location.
        At least 1; 255 is the ceiling of the published field.
    ellipse_semi_major_axis : float or None
        Semi-major axis of the location error ellipse, **in metres** (published in
        whole kilometres). ``None`` where the release has 0 — no ellipse has a
        semi-major axis of 0 beside a semi-minor of 1 km. Not smaller than the
        semi-minor axis.
    ellipse_semi_minor_axis : float
        Semi-minor axis of the ellipse, in metres. Greater than 0.
    ellipse_angle : float
        Orientation of the ellipse, in degrees from -90 to 90 (published from -89
        to 89, whole degrees); the reference direction is not documented.
    """

    __tablename__ = "alaska_uswfs_lightning"

    __table_args__ = (
        CheckConstraint("flash_id >= 1 AND flash_id <= id",
                        name="ck_alaska_uswfs_lightning_flash_id"),
        CheckConstraint("(stroke_index = 1) = (flash_id = id)",
                        name="ck_alaska_uswfs_lightning_first_stroke"),
        CheckConstraint("multiplicity >= 1", name="ck_alaska_uswfs_lightning_multiplicity"),
        CheckConstraint("stroke_index >= 1 AND stroke_index <= multiplicity",
                        name="ck_alaska_uswfs_lightning_stroke_index"),
        CheckConstraint("network_code >= 0", name="ck_alaska_uswfs_lightning_network_code"),
        CheckConstraint("sequence_number >= 0", name="ck_alaska_uswfs_lightning_sequence_number"),
        CheckConstraint("gdop >= 1", name="ck_alaska_uswfs_lightning_gdop"),
        CheckConstraint("ellipse_semi_minor_axis > 0 AND (ellipse_semi_major_axis IS NULL "
                        "OR ellipse_semi_major_axis >= ellipse_semi_minor_axis)",
                        name="ck_alaska_uswfs_lightning_ellipse_axes"),
        CheckConstraint("ellipse_angle >= -90 AND ellipse_angle <= 90",
                        name="ck_alaska_uswfs_lightning_ellipse_angle"),
        Index("ix_alaska_uswfs_lightning_flash_id", "flash_id"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Lightning.id), primary_key=True)
    flash_id: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplicity: Mapped[int] = mapped_column(Integer, nullable=False)
    stroke_index: Mapped[int] = mapped_column(Integer, nullable=False)
    network_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gdop: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ellipse_semi_major_axis: Mapped[float | None] = mapped_column(Float, nullable=True)
    ellipse_semi_minor_axis: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_angle: Mapped[float] = mapped_column(Float, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": IDENTITY,
    }

    def __repr__(self) -> str:
        return (f"AlaskaUswfsLightning(id={self.id!r}, date_time={self.date_time!r}, "
                f"flash_id={self.flash_id!r})")


#: Behind the ``v_alaska_uswfs_lightning_3338`` view, which selects exactly this
#: expression and filters on the same type: see GEOMETRY_3338. On ``lightning``,
#: where the point is, and partial, so the other providers' strokes are not in it.
Lightning.__table__.append_constraint(
    Index("idx_lightning_alaska_uswfs_geometry_3338",
          text(GEOMETRY_3338.format(column="geometry")),
          postgresql_using="gist",
          postgresql_where=text(f"type = '{IDENTITY}'")))
