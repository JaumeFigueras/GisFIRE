#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import pytz

from sqlalchemy import Integer
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
from src.data_model.located_entity import LocatedEntityEPSG4326

from typing import Optional
from typing import Union


class Lightning(Base, LocatedEntityEPSG4326):
    __tablename__ = "lightning"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    _date: Mapped[datetime.datetime] = mapped_column('date', DateTime(timezone=True), nullable=False)
    _tzinfo: Mapped[str] = mapped_column('tzinfo', nullable=False)
    _latitude_epsg_4326: Mapped[Union[float, None]] = mapped_column('latitude_epsg_4326', Float, nullable=False)
    _longitude_epsg_4326: Mapped[Union[float, None]] = mapped_column('longitude_epsg_4326', Float, nullable=False)
    geometry_epsg_4326: Mapped[Union[WKBElement, None]] = mapped_column('geom_epsg_4326',
                                                                        Geometry(geometry_type='POINT', srid=4326))
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    type: Mapped[str]

    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="lightnings")

    __mapper_args__ = {
        "polymorphic_identity": "lightning",
        "polymorphic_on": "type",
    }

    def __init__(self, date: Optional[datetime.datetime] = None, latitude_epsg_4326: Optional[float] = None,
                 longitude_epsg_4326: Optional[float] = None):
        Base.__init__(self)
        LocatedEntityEPSG4326.__init__(self, longitude_epsg_4326=longitude_epsg_4326, latitude_epsg_4326=latitude_epsg_4326)
        if date is not None:
            if date.tzinfo is None:
                raise ValueError('Date must contain timezone information')
            self._tzinfo = str(date.tzinfo)
        self._date = date
        print("Init Lightning")

    def __iter__(self):
        yield "id", self.id
        if self._tzinfo.startswith('tzoffset'):
            tmp = self._date.astimezone(pytz.UTC)
            yield "date", tmp.astimezone(eval(self._tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            yield "date", self._date.astimezone(pytz.timezone(self._tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
        yield from super(LocatedEntityEPSG4326).__iter__()

    @property
    def date(self) -> Optional[datetime.datetime]:
        return self._date

    @date.setter
    def date(self, value: datetime.datetime) -> None:
        if value.tzinfo is None:
            raise ValueError('Date must contain timezone information')
        self._tzinfo = str(value.tzinfo)
        self._date = value

