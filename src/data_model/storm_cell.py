#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import pytz

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.mixins.time_stamp import TimeStampMixIn
from src.data_model.mixins.date_time import DateTimeMixIn
from src.data_model.mixins.location import LocationMixIn
from src.data_model.lightning import Lightning

from typing import Optional
from typing import List

class StormCellLightningAssociation(Base):
    __tablename__ = "storm_cell_lightning_association_table"
    storm_cell_id: Mapped[int] = mapped_column(ForeignKey("storm_cell.id"), primary_key=True)
    lightning_id: Mapped[int] = mapped_column(ForeignKey("lightning.id"), primary_key=True)
    lightning: Mapped["Lightning"] = relationship(back_populates="storm_cell_associations")
    storm_cell: Mapped["StormCell"] = relationship(back_populates="lightning_associations")


class StormCell(Base, DateTimeMixIn, TimeStampMixIn):
    # Metaclass date_time attributes
    __date__ = [
        {'name': 'date_time_start', 'nullable': False},
        {'name': 'date_time_end', 'nullable': False},
    ]
    # Type hint for generated attributes by the metaclass
    date_time_start: datetime.datetime
    tzinfo_date_time_start: str
    date_time_end: datetime.datetime
    tzinfo_date_time_end: str
    # SQLAlchemy columns
    __tablename__ = "storm_cell"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    algorithm_used: Mapped[str] = mapped_column('algorithm_used', String)
    algorithm_parameter_time: Mapped[float] = mapped_column('algorithm_parameter_time', Float, nullable=True, default=None)
    algorithm_parameter_distance: Mapped[float] = mapped_column('algorithm_parameter_distance', Float, nullable=True, default=None)
    maximum_gap_between_lightnings: Mapped[float] = mapped_column('maximum_gap_between_lightnings', Float, nullable=False)
    number_of_lightnings: Mapped[int] = mapped_column('number_of_lightnings', Integer, nullable=False)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    # many-to-many relationship to Child, bypassing the `Association` class
    lightnings: Mapped[List["Lightning"]] = relationship(secondary="storm_cell_lightning_association_table", back_populates="storm_cells")
    # association between Parent -> Association -> Child
    lightning_associations: Mapped[List["StormCellLightningAssociation"]] = relationship(back_populates="storm_cell")
    data_provider: Mapped["DataProvider"] = relationship(back_populates="storm_cell")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "storm_cell",
        "polymorphic_on": "type",
    }

    def __init__(self, date_time_start: Optional[datetime.datetime] = None,
                 date_time_end: Optional[datetime.datetime] = None, algorithm_used: Optional[str] = None,
                 algorithm_parameter_time: Optional[float] = None,
                 algorithm_parameter_distance: Optional[float] = None,
                 maximum_gap_between_lightnings: Optional[float]= None,
                 number_of_lightnings: Optional[int] = -1) -> None:
        Base.__init__(self)
        # DateTimeMixIn.__init__(self, date_time)
        TimeStampMixIn.__init__(self)
        self.date_time_start = date_time_start
        self.date_time_end = date_time_end
        self.algorithm_used = algorithm_used
        self.algorithm_parameter_time = algorithm_parameter_time
        self.algorithm_parameter_distance = algorithm_parameter_distance
        self.maximum_gap_between_lightnings = maximum_gap_between_lightnings
        self.number_of_lightnings = number_of_lightnings

    def __iter__(self):
        yield "id", self.id
        yield "data_provider", self.data_provider_name
        yield "algorithm_used", self.algorithm_used
        yield "algorithm_parameter_time", self.algorithm_parameter_time
        yield "algorithm_parameter_distance", self.algorithm_parameter_distance
        yield "maximum_gap_between_lightnings", self.maximum_gap_between_lightnings
        yield "number_of_lightnings", self.number_of_lightnings
        yield from LocationMixIn.__iter__(self)
        yield from DateTimeMixIn.__iter__(self)

