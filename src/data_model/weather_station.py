#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import pytz

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from geoalchemy2 import Geometry
from geoalchemy2 import WKBElement
from geoalchemy2 import shape
from shapely.geometry import Point

from src.data_model.data_provider import DataProvider
from src.geo.location_converter import LocationConverter

from typing import Optional
from typing import Union


class WeatherStation(Base):
    __tablename__ = "whether_station"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column('name', String, nullable=False)
    altitude: Mapped[Optional[float]] = mapped_column('altitude', Float, nullable=True)
    _latitude_epsg_4326: Mapped[Optional[float]] = mapped_column('latitude_epsg_4326', Float, nullable=False)
    _longitude_epsg_4326: Mapped[Optional[float]] = mapped_column('longitude_epsg_4326', Float, nullable=False)
    geometry_epsg_4326: Mapped[Optional[WKBElement]] = mapped_column('geom_epsg_4326',
                                                                     Geometry(geometry_type='POINT', srid=4326))
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    type: Mapped[str]

    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="lightnings")

    __mapper_args__ = {
        "polymorphic_identity": "weather_station",
        "polymorphic_on": "type",
    }

    def __init__(self, name: Optional[str] = None, altitude: Optional[float] = None,
                 latitude_epsg_4326: Optional[float] = None, longitude_epsg_4326: Optional[float] = None) -> None:
        super().__init__()
        if (latitude_epsg_4326 is not None) and not (-90 <= latitude_epsg_4326 <= 90):
            raise ValueError("Latitude WGS84 out of range")
        if (longitude_epsg_4326 is not None) and not (-180 <= longitude_epsg_4326 <= 180):
            raise ValueError("Longitude WGS84 out of range")
        self.converter_4326 = LocationConverter("_longitude_epsg_4326", "_latitude_epsg_4326", "4326", "geometry_epsg_4326")
        self.name = name
        self.altitude = altitude
        self.latitude_epsg_4326 = latitude_epsg_4326
        self.longitude_epsg_4326 = longitude_epsg_4326
        self.converter_4326.generate_geometry(self)

    @property
    def latitude_epsg_4326(self) -> Union[float, None]:
        return self._latitude_epsg_4326

    @latitude_epsg_4326.setter
    def latitude_epsg_4326(self, latitude_epsg_4326: Union[float, None]) -> None:
        if latitude_epsg_4326 is not None:
            if not (-90 <= latitude_epsg_4326 <= 90):
                raise ValueError("Latitude WGS84 out of range")
        self._latitude_epsg_4326 = latitude_epsg_4326
        self.converter_4326.generate_geometry(self)

    @property
    def longitude_epsg_4326(self) -> Union[float, None]:
        return self._latitude_epsg_4326

    @longitude_epsg_4326.setter
    def longitude_epsg_4326(self, longitude_epsg_4326: Union[float, None]) -> None:
        if longitude_epsg_4326 is not None:
            if not (-90 <= longitude_epsg_4326 <= 90):
                raise ValueError("Latitude WGS84 out of range")
        self._longitude_epsg_4326 = longitude_epsg_4326
        self.converter_4326.generate_geometry(self)

    @property
    def geometry_epsg_4326_as_point(self) -> Union[Point, None]:
        return shape.to_shape(self.geometry_epsg_4326)
