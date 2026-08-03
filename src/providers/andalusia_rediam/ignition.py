#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REDIAM ignition model.

Where an Andalusian fire started, as the service publishes it: ``X_INIC`` and
``Y_INIC``, a point on the same ETRS89 / UTM 30N grid as the perimeter.

The generic :class:`~src.data_model.ignition.Ignition` already holds the point in
EPSG:4326, the instant and the country; this model adds the identity of the fire —
the published code and date — and the two published coordinates as they were written.

Four years, and only four
--------------------------

The coordinates exist in the **yearly** layers of 2021, 2022, 2023 and 2024, and
nowhere else: not in the combined ``PERIMETROS_COR_2008_2025`` layer that the
perimeters are read from, and not in the 2025 yearly layer. 201 fires of the 907 have
a point, and for the rest the service published none.

So :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.ignition_id` is
``NULL`` on four fires out of five, and that is a fact about the archive rather than
about the import. See :mod:`src.providers.andalusia_rediam` for the whole shape of
the dataset.

The published coordinates are kept as well as the point
--------------------------------------------------------

:attr:`RediamIgnition.utm_x` and :attr:`RediamIgnition.utm_y` are the numbers in the
DBF; :attr:`~src.data_model.ignition.Ignition.geometry` is their reprojection to
EPSG:4326, derived from them at import.

The same argument as everywhere else in this project — a published value is kept and
a derived one is derived — and here it has a second use: the 2021 layer publishes
them as integers and the later ones as reals, so the pair also records how precisely
the service placed the fire that year.

.. warning::

   **The point is not guaranteed to be inside the perimeter of its own fire.** 88 of
   the 201 are; the rest lie outside by anything from a metre to three kilometres,
   and one 2022 fire's point is 19.5 km away.

   Nothing here corrects that. A start point reported by the service and a perimeter
   mapped afterwards are two observations of one fire, and where they disagree the
   disagreement is the information — which is exactly why the ignition is a row of
   its own rather than two columns on the perimeter.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Date
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.ignition import Ignition


class RediamIgnition(Ignition):
    """The point an Andalusian fire started at, as published.

    Uses joined table inheritance: the columns shared by every ignition live in the
    ``ignition`` table and only the Andalusian ones are stored here, in
    ``rediam_ignition``, whose primary key is also a foreign key to the parent row.

    Attributes
    ----------
    id : int
        Primary key, and a foreign key to
        :attr:`~src.data_model.ignition.Ignition.id`. The local GisFIRE identifier,
        shared with the parent row.
    source_layer : str
        The yearly layer the point was read from, upper-cased —
        ``PERIMETROS_COR_2022``. Provenance, and what tells a point apart from the
        perimeter it belongs to, which comes from the combined layer.
    code : str
        The published ``CODIGO`` of the fire, exactly as published, and the same
        value as :attr:`~src.providers.andalusia_rediam.wildfire.RediamWildfire.code`.
    fire_date : datetime.date
        The published ``FECHA_INC`` of the fire.

        With :attr:`code` this is the natural key of the fire, and it is what the
        import joins a point to its perimeter on — the two come from different files,
        so there is no row identity to use instead.
    utm_x, utm_y : float
        ``X_INIC`` and ``Y_INIC`` as published: easting and northing in metres on
        EPSG:25830 (:data:`~src.providers.andalusia_rediam.SOURCE_SRID`).

        The parent's :attr:`~src.data_model.ignition.Ignition.geometry` is these two
        reprojected to EPSG:4326; keeping both means the published numbers survive
        and the geometry is provably the same point.

    Notes
    -----
    ``(code, fire_date)`` is unique here as it is on the perimeter: one published
    point per fire.
    """

    __tablename__ = "rediam_ignition"

    __table_args__ = (
        UniqueConstraint("code", "fire_date", name="uq_rediam_ignition_code_fire_date"),
    )

    id: Mapped[int] = mapped_column(ForeignKey(Ignition.id), primary_key=True)
    source_layer: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    fire_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    utm_x: Mapped[float] = mapped_column(Float, nullable=False)
    utm_y: Mapped[float] = mapped_column(Float, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "rediam_ignition",
    }

    def __repr__(self) -> str:
        return (f"RediamIgnition(id={self.id!r}, code={self.code!r}, "
                f"fire_date={self.fire_date!r})")
