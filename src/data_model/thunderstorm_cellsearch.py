#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Output specific to Cellsearch (Tuomi & Larjavaara 2005).

Cellsearch adds the flashes of a cell one by one and moves the cell's centre
after each of them: "a new centre point is calculated and plotted for each new
flash" (Fig. 8 of the article). That trajectory is structured output no other
algorithm produces, so it gets a table of its own; everything generic (the
cell's strokes, its time span, its number of flashes, its area, its hull) is in
the tables of :mod:`src.data_model.thunderstorm`.

::

    thunderstorm 1──n thunderstorm_lightning 1──0..1 thunderstorm_cellsearch_flash
         │ 1                                              n │
         └──────────────────────────────────────────────────┘

Only cells with at least ``min_flashes`` flashes (the experiment's N_min) are
stored, so only their flashes have a row here. The flash's time and location
error are not repeated: they are its representative stroke's
(:attr:`~src.data_model.lightning.Lightning.date_time` and the provider's error,
e.g. ``meteocat_lightning.ellipse_major_axis``).
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Integer
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import backref
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.data_model.lightning import Lightning
from src.data_model.thunderstorm import Thunderstorm


class ThunderstormCellsearchFlash(Base):
    """One flash of a Cellsearch cell, with the cell's centre right after it.

    Two composite foreign keys keep the row consistent:

    * ``(thunderstorm_id, experiment_id)`` → ``thunderstorm(id,
      experiment_id)``: ``experiment_id`` is the cell's, so the database can
      keep a stroke as the representative of at most one flash per experiment;
    * ``(thunderstorm_id, lightning_id)`` → ``thunderstorm_lightning``: the
      representative stroke is one of the cell's linked strokes.

    Both cascade, so deleting the experiment, the cell or the link deletes the
    row. It is set from the cell when made through :attr:`thunderstorm`.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key: the integer key QGIS needs for the
        per-flash view.
    thunderstorm_id : int
        The cell.
    sequence : int
        The flash's position in its cell, from 1 in time order; unique per
        cell.
    experiment_id : int
        The cell's experiment.
    lightning_id : int
        The stroke that represents the flash (its most accurate one); unique per
        experiment.
    centre : geoalchemy2.elements.WKBElement
        The cell's running centre right after this flash, a ``POINT`` in
        EPSG:4326: the mean position of the cell's last ``min(I, sequence)``
        flashes, computed in the projected CRS of the experiment's parameters.
        Indexed (GiST).
    thunderstorm : Thunderstorm
        The cell. It lists these rows, in sequence order, as
        ``Thunderstorm.cellsearch_flashes``.
    lightning : Lightning
        The representative stroke (read-only).
    """

    __tablename__ = "thunderstorm_cellsearch_flash"

    __table_args__ = (
        ForeignKeyConstraint(
            ["thunderstorm_id", "experiment_id"], ["thunderstorm.id", "thunderstorm.experiment_id"],
            ondelete="CASCADE", name="fk_thunderstorm_cellsearch_flash_thunderstorm",
        ),
        ForeignKeyConstraint(
            ["thunderstorm_id", "lightning_id"],
            ["thunderstorm_lightning.thunderstorm_id", "thunderstorm_lightning.lightning_id"],
            ondelete="CASCADE", name="fk_thunderstorm_cellsearch_flash_link",
        ),
        CheckConstraint("sequence >= 1", name="ck_thunderstorm_cellsearch_flash_sequence"),
        UniqueConstraint("thunderstorm_id", "sequence",
                         name="uq_thunderstorm_cellsearch_flash_sequence"),
        UniqueConstraint("experiment_id", "lightning_id",
                         name="uq_thunderstorm_cellsearch_flash_experiment_lightning"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thunderstorm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    experiment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lightning_id: Mapped[int] = mapped_column(Integer, nullable=False)
    centre: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

    thunderstorm: Mapped[Thunderstorm] = relationship(
        backref=backref("cellsearch_flashes", order_by="ThunderstormCellsearchFlash.sequence",
                        cascade="all, delete-orphan", passive_deletes=True),
    )
    lightning: Mapped[Lightning] = relationship(
        primaryjoin="Lightning.id == foreign(ThunderstormCellsearchFlash.lightning_id)",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (f"ThunderstormCellsearchFlash(id={self.id!r}, "
                f"thunderstorm_id={self.thunderstorm_id!r}, sequence={self.sequence!r}, "
                f"lightning_id={self.lightning_id!r})")
