#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FMI lightning model.

One row per stroke published by the Finnish Meteorological Institute's open-data
WFS.

The generic :class:`~src.data_model.lightning.Lightning` already holds the
instant, the point in EPSG:4326, the signed peak current, whether the stroke was
cloud-to-ground and the administrative boundary. This model adds what is
particular to FMI: the published point **in the CRS it was published in**, the
flash the stroke belongs to, how well it was located, the waveform times and the
stroke status.

See :mod:`src.providers.finland_fmi` for the dataset itself.

From the published fields to the columns
----------------------------------------

=====================  ==============================================================
Published              Stored
=====================  ==============================================================
position (ETRS89)      :attr:`FmiLightning.geometry_etrs89`, and its EPSG:4326
                       reprojection on the parent's ``geometry``
time (UTC, seconds)    parent's ``date_time``
``peak_current``       parent's ``peak_current``; ``0`` (not recorded, 2005-2008)
                       is ``NULL``
``cloud_indicator``    parent's ``cloud_to_ground`` = ``cloud_indicator == 0``
``flash_id``           :attr:`FmiLightning.flash_id`
``multiplicity``       :attr:`FmiLightning.published_multiplicity`, as published
``sensors``            :attr:`FmiLightning.number_of_sensors`
``freedom_degree``     :attr:`FmiLightning.degrees_of_freedom`
``chi_square``         :attr:`FmiLightning.chi_squared`
``ellipse_major``      :attr:`FmiLightning.ellipse_major_axis`, **km → m**
``ellipse_minor``      :attr:`FmiLightning.ellipse_minor_axis`, **km → m**
``ellipse_angle``      :attr:`FmiLightning.ellipse_angle`
``rise_time``          :attr:`FmiLightning.rise_time`
``ptz_time``           :attr:`FmiLightning.peak_to_zero_time`
``stroke_status``      :attr:`FmiLightning.stroke_status`
``angle_indicator``    :attr:`FmiLightning.angle_indicator`
``signal_indicator``   :attr:`FmiLightning.signal_indicator`
``timing_indicator``   :attr:`FmiLightning.timing_indicator`
=====================  ==============================================================

The ellipse axes are converted to metres so that they mean the same as
MeteoCat's and can be used as a location error without knowing the provider.

Flashes: multiplicity and stroke index
--------------------------------------

A flash is identified by :attr:`FmiLightning.flash_id` alone: FMI numbers its
flashes in one sequence since 1998. As for MeteoCat, two values are computed by
the import over the strokes of a flash, so that the same query works on both
providers:

* :attr:`FmiLightning.multiplicity` — how many strokes of the flash are stored,
  the same on every stroke of it. Usually equal to
  :attr:`FmiLightning.published_multiplicity` of the first stroke; about 0.01 % of
  the flashes have lost strokes to FMI's quality filter and differ.
* :attr:`FmiLightning.stroke_index` — the position of the stroke in the flash,
  from 1. Stroke 1 is the one FMI marks as first (``multiplicity`` not 0), or the
  earliest when no stroke is marked; the others follow by instant. FMI publishes
  whole seconds, and strokes of the same second come in an order that is not
  stable between requests, so the import puts them in an order of its own,
  computed from their values; beyond the first stroke, the index within a second
  is that order, not a measured one. ``stroke_index = 1`` is reliable: one stroke
  per flash, the first.

The import also inserts the strokes in that order, so the order of the local
identifiers — which the thunderstorm algorithms use to break ties between
strokes of the same second — does not depend on the order a download happened
to return.

A flash lasts at most a second or so, so a flash can straddle two downloaded
periods; the import recomputes both values for every flash it touches, over all
the stored strokes of that flash.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
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
from src.providers.finland_fmi import PROJECTED_SRID
from src.providers.finland_fmi import SOURCE_SRID

#: The ETRS89 point reprojected to ETRS-TM35FIN, cast back so it keeps its type and
#: SRID. The ``v_fmi_lightning_3067`` view selects this expression and an expression
#: index is built on it; written the way PostgreSQL prints it back, for the reason
#: given at :data:`src.providers.catalonia_meteocat.lightning.GEOMETRY_25831`.
GEOMETRY_3067 = (f"(st_transform({{column}}, {PROJECTED_SRID})"
                 f"::geometry(Point,{PROJECTED_SRID}))")


class FmiLightning(Lightning):
    """A stroke published by the Finnish Meteorological Institute.

    Uses joined table inheritance: the columns shared by every stroke live in the
    ``lightning`` table and only the FMI ones are stored here, in
    ``fmi_lightning``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.lightning.Lightning.id`. The local GisFIRE
        identifier, shared with the parent row.
    flash_id : int
        The published ``flash_id``: the flash the stroke belongs to, unique per
        flash across the whole archive, not per stroke. Indexed.
    multiplicity : int
        Number of stored strokes of the flash, computed by the import. At least 1.
    stroke_index : int
        Position of the stroke in its flash, from 1 to :attr:`multiplicity`.
    published_multiplicity : int
        The published ``multiplicity``: FMI's stroke count of the flash on its
        first stroke, ``0`` on every other one. Not negative.
    number_of_sensors : int
        The published ``sensors``: how many sensors detected the stroke. At least
        1 (2 in every sample).
    degrees_of_freedom : int
        The published ``freedom_degree`` of the location fit. Not negative.
    chi_squared : float
        The published ``chi_square`` of the location fit. Not negative; ``0`` is
        a value (two-sensor fits).
    ellipse_major_axis : float
        Major axis of the location confidence ellipse, **in metres** (published in
        kilometres). Not negative.
    ellipse_minor_axis : float
        Minor axis of the ellipse, in metres. Not negative and not larger than the
        major axis.
    ellipse_angle : float
        Orientation of the ellipse, in degrees from 0 to 180, as published.
    rise_time : float
        The published ``rise_time`` of the waveform, apparently in microseconds.
        Not negative.
    peak_to_zero_time : float
        The published ``ptz_time``, peak-to-zero time of the waveform, apparently
        in microseconds. Not negative.
    stroke_status : int
        The published ``stroke_status``, undocumented: ``0``, ``101`` (2011-2012)
        or ``17`` (from 2017).
    angle_indicator : int
        The published ``angle_indicator``, undocumented; ``1`` in every sample
        from 1998 to 2025.
    signal_indicator : int
        The published ``signal_indicator``, undocumented; ``0`` in every sample.
    timing_indicator : int
        The published ``timing_indicator``, undocumented; ``1`` in every sample.
    geometry_etrs89 : geoalchemy2.elements.WKBElement
        The published position in
        :data:`~src.providers.finland_fmi.SOURCE_SRID` (ETRS89), untouched.
    """

    __tablename__ = "fmi_lightning"

    __table_args__ = (
        CheckConstraint("flash_id >= 0", name="ck_fmi_lightning_flash_id"),
        CheckConstraint("multiplicity >= 1", name="ck_fmi_lightning_multiplicity"),
        CheckConstraint("stroke_index >= 1 AND stroke_index <= multiplicity",
                        name="ck_fmi_lightning_stroke_index"),
        CheckConstraint("published_multiplicity >= 0",
                        name="ck_fmi_lightning_published_multiplicity"),
        CheckConstraint("number_of_sensors >= 1", name="ck_fmi_lightning_number_of_sensors"),
        CheckConstraint("degrees_of_freedom >= 0", name="ck_fmi_lightning_degrees_of_freedom"),
        CheckConstraint("chi_squared >= 0", name="ck_fmi_lightning_chi_squared"),
        CheckConstraint("ellipse_minor_axis >= 0 AND ellipse_minor_axis <= ellipse_major_axis",
                        name="ck_fmi_lightning_ellipse_axes"),
        CheckConstraint("ellipse_angle >= 0 AND ellipse_angle <= 180",
                        name="ck_fmi_lightning_ellipse_angle"),
        CheckConstraint("rise_time >= 0", name="ck_fmi_lightning_rise_time"),
        CheckConstraint("peak_to_zero_time >= 0", name="ck_fmi_lightning_peak_to_zero_time"),
        Index("ix_fmi_lightning_flash_id", "flash_id"),
        # Behind the ``v_fmi_lightning_3067`` view, which selects exactly this
        # expression: see GEOMETRY_3067.
        Index("idx_fmi_lightning_geometry_3067",
              text(GEOMETRY_3067.format(column="geometry_etrs89")),
              postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Lightning.id), primary_key=True)
    flash_id: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplicity: Mapped[int] = mapped_column(Integer, nullable=False)
    stroke_index: Mapped[int] = mapped_column(Integer, nullable=False)
    published_multiplicity: Mapped[int] = mapped_column(Integer, nullable=False)
    number_of_sensors: Mapped[int] = mapped_column(Integer, nullable=False)
    degrees_of_freedom: Mapped[int] = mapped_column(Integer, nullable=False)
    chi_squared: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_major_axis: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_minor_axis: Mapped[float] = mapped_column(Float, nullable=False)
    ellipse_angle: Mapped[float] = mapped_column(Float, nullable=False)
    rise_time: Mapped[float] = mapped_column(Float, nullable=False)
    peak_to_zero_time: Mapped[float] = mapped_column(Float, nullable=False)
    stroke_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    angle_indicator: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signal_indicator: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    timing_indicator: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    geometry_etrs89: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=SOURCE_SRID), nullable=False
    )

    __mapper_args__ = {
        "polymorphic_identity": "fmi_lightning",
    }

    def __repr__(self) -> str:
        return (f"FmiLightning(id={self.id!r}, date_time={self.date_time!r}, "
                f"flash_id={self.flash_id!r})")
