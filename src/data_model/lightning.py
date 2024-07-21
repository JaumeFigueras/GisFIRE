#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime

from sqlalchemy import Integer
from sqlalchemy import Float
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from geoalchemy2 import Geometry

from typing import Optional
from typing import Union


class Lightning(Base):
    __tablename__ = "lightning"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    _date = mapped_column('date', DateTime(timezone=True), nullable=False)
    tzinfo: Mapped[str] = mapped_column('tzinfo', nullable=False)
    _latitude_wgs84 = mapped_column('latitude_wgs84', Float, nullable=False)
    _longitude_wgs84 = mapped_column('longitude_wgs84', Float, nullable=False)
    _geometry_wgs84 = mapped_column('geom_wgs84', Geometry(geometry_type='POINT', srid=4326))
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    type: Mapped[str]

    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'), nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="lightnings")

    __mapper_args__ = {
        "polymorphic_identity": "lightning",
        "polymorphic_on": "type",
    }

    def __init__(self, date: Optional[datetime.datetime] = None, latitude_wgs84: Optional[float] = None,
                 longitude_wgs84: Optional[float] = None):
        super().__init__()
        if (latitude_wgs84 is not None) and not (-90 <= latitude_wgs84 <= 90):
            raise ValueError("Latitude WGS84 out of range")
        if (longitude_wgs84 is not None) and not (-180 <= longitude_wgs84 <= 180):
            raise ValueError("Longitude WGS84 out of range")
        if date is not None:
            if date.tzinfo is None:
                raise ValueError('Date must contain timezone information')
            self.tzinfo = str(date.tzinfo)
        self._date = date
        self._latitude_wgs84 = latitude_wgs84
        self._longitude_wgs84 = longitude_wgs84
        if (self._latitude_wgs84 is not None) and (self._longitude_wgs84 is not None):
            self._geometry_wgs84 = "SRID=4326;POINT({0:} {1:})".format(self._longitude_wgs84, self._latitude_wgs84)
        else:
            self._geometry_wgs84 = None

    def __iter__(self):
        pass

    @property
    def date(self) -> Optional[datetime.datetime]:
        return self._date

    @date.setter
    def date(self, value: datetime.datetime) -> None:
        if value.tzinfo is None:
            raise ValueError('Date must contain timezone information')
        self.tzinfo = str(value.tzinfo)
        self._date = value

    @property
    def latitude_wgs84(self) -> Union[float, None]:
        return self._latitude_wgs84

    @latitude_wgs84.setter
    def latitude_wgs84(self, latitude_wgs84: Union[float, None]) -> None:
        if latitude_wgs84 is None:
            self._latitude_wgs84 = None
            self._geometry_wgs84 = None
            return
        if -90 <= latitude_wgs84 <= 90:
            self._latitude_wgs84 = latitude_wgs84
            if (self._longitude_wgs84 is not None) and (self._latitude_wgs84 is not None):
                self._geometry_wgs84 = "SRID=4326;POINT({0:} {1:})".format(self._longitude_wgs84, self._latitude_wgs84)
            else:
                self._geometry_wgs84 = None
        else:
            raise ValueError("Latitude WGS84 out of range")

    @property
    def longitude_wgs84(self) -> Union[float, None]:
        return self._longitude_wgs84

    @longitude_wgs84.setter
    def longitude_wgs84(self, longitude_wgs84: Union[float, None]) -> None:
        if longitude_wgs84 is None:
            self._longitude_wgs84 = None
            self._geometry_wgs84 = None
            return
        if -90 <= longitude_wgs84 <= 90:
            self._longitude_wgs84 = longitude_wgs84
            if (self._longitude_wgs84 is not None) and (self._latitude_wgs84 is not None):
                self._geometry_wgs84 = "SRID=4326;POINT({0:} {1:})".format(self._longitude_wgs84, self._latitude_wgs84)
            else:
                self._geometry_wgs84 = None
        else:
            raise ValueError("Latitude WGS84 out of range")

    @property
    def geometry_wgs84(self) -> Union[Geometry, None]:
        return self._geometry_wgs84
