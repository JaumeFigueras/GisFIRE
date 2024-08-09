#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import pytz

from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model.mixins.time_stamp import TimeStampMixIn
from src.data_model.mixins.date_time import DateTimeMixIn

from typing import Optional
from typing import Union


class Measure(Base, DateTimeMixIn, TimeStampMixIn):
    # Metaclass date_time attributes
    __date__ = [
        {'name': 'measure_date_time', 'nullable': False},
    ]
    # Type hint for generated attributes by the metaclass
    measure_date_time: datetime.datetime
    tzinfo_measure_date_time: str
    # SQLAlchemy columns
    __tablename__ = "measure"
    id: Mapped[str] = mapped_column('id', String, primary_key=True)
    value: Mapped[float] = mapped_column('value', Float, nullable=False)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="measures")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "measure",
        "polymorphic_on": "type",
    }

    def __init__(self, measure_date_time: Optional[datetime.datetime] = None) -> None:
        Base.__init__(self)
        DateTimeMixIn.__init__(self)
        TimeStampMixIn.__init__(self)
        self.measure_date_time = measure_date_time

    def __iter__(self):
        yield "id", self.id
        yield "data_provider", self.data_provider_name
        yield from DateTimeMixIn.__iter__(self)

