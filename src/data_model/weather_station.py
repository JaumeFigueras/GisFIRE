#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model.data_provider import DataProvider
from src.data_model.mixins.time_stamp import TimeStampMixIn

from typing import Optional
from typing import Union


class WeatherStation(Base, TimeStampMixIn):
    # Metaclass location attributes
    location = [
        {'epsg': 4326, 'validation': 'geographic', 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_4326: float
    y_4326: float
    geometry_4326: Union[str, Point]
    # SQLAlchemy columns
    __tablename__ = "whether_station"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column('name', String, nullable=False)
    altitude: Mapped[Optional[float]] = mapped_column('altitude', Float, nullable=True)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="lightnings")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "weather_station",
        "polymorphic_on": "type",
    }

    def __init__(self, name: Optional[str] = None, altitude: Optional[float] = None,
                 longitude_epsg_4326: Optional[float] = None, latitude_epsg_4326: Optional[float] = None) -> None:
        super().__init__()
        self.name = name
        self.altitude = altitude
        self.x_4326 = longitude_epsg_4326
        self.y_4326 = latitude_epsg_4326
