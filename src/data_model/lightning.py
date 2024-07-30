#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import pytz

from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model.data_provider import DataProvider
from src.data_model.mixins.time_stamp import TimeStampMixIn

from typing import Optional
from typing import Union


class Lightning(Base, TimeStampMixIn):
    # Metaclass location attributes
    location = [
        {'epsg': 4326, 'validation': 'geographic', 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_4326: float
    y_4326: float
    geometry_4326: Union[str, Point]

    attributes = [
        {'name': 'date_time', 'nullable': False}
    ]
    date_time: datetime.datetime
    tzinfo_date_time: str

    # SQLAlchemy columns
    __tablename__ = "lightning"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped[DataProvider] = relationship(back_populates="lightnings")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "lightning",
        "polymorphic_on": "type",
    }

    def __init__(self, date_time: Optional[datetime.datetime] = None, longitude_epsg_4326: Optional[float] = None,
                 latitude_epsg_4326: Optional[float] = None) -> None:
        Base.__init__(self)
        # DateTimeMixIn.__init__(self, date_time)
        TimeStampMixIn.__init__(self)
        self.x_4326 = longitude_epsg_4326
        self.y_4326 = latitude_epsg_4326
        self.date_time = date_time

    def __iter__(self):
        yield "id", self.id
        yield 'x_4326', self.x_4326
        yield 'y_4326', self.y_4326
        yield from DateTimeMixIn.__iter__(self)

