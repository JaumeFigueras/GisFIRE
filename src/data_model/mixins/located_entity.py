#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from src.data_model import Base

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
from sqlalchemy.ext.declarative import declared_attr
from geoalchemy2 import Geometry
from geoalchemy2 import WKBElement
from geoalchemy2 import shape
from shapely.geometry import Point

from src.data_model.data_provider import DataProvider
from src.geo.location_converter import LocationConverter

from typing import Optional
from typing import Union

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from typing import Any, Dict, List, Type


# Step 1: Define the extended metaclass with type hinting
class LocatedEntityMeta(DeclarativeMeta):
    def __init__(cls: Type['Base'], name: str, bases: tuple, dct: dict):
        dynamic_columns: List[Dict[str, Any]] = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name: str = col_def['attr_name']
            column_name: str = col_def['column_name']
            column_type = col_def['column_type']

            # Create the column
            if column_name.startswith('x') or column_name.startswith('y'):
                column: Mapped[column_type] = mapped_column(column_name, column_type, nullable=False)
            else:
                column: Mapped[column_type] = mapped_column(column_name, column_type, nullable=True)
            dct[attr_name] = column

            # Create getter
            def make_getter(attr_name: str):
                if attr_name.startswith('_geom'):
                    def getter(self) -> Union[str, Point, None]:
                        if isinstance(getattr(self, attr_name), str):
                            return getattr(self, attr_name)
                        elif getattr(self, attr_name) is None:
                            return None
                        else:
                            return shape.to_shape(getattr(self, attr_name))
                else:
                    def getter(self) -> Any:
                        return getattr(self, attr_name)
                return getter

            # Create setter with validation
            def make_setter(attr_name: str):
                def setter(self, value: Any) -> None:
                    if isinstance(value, str) and len(value) > 10:
                        raise ValueError(f"Value for {attr_name} cannot be longer than 10 characters")
                    setattr(self, attr_name, value)

                return setter

            # Add getter and setter to the class
            dct[column_name] = make_getter(attr_name)
            dct[column_name] = make_setter(attr_name)

        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
BaseMeta = declarative_base(metaclass=LocatedEntityMeta)


# Step 3: Define the models with type hinting
class LocatedEntityEPSG4326(BaseMeta):
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns: List[Dict[str, Any]] = [
        {'attr_name': '_x_epsg_4326', 'column_name': 'x_epsg_4326', 'column_type': Float},
        {'attr_name': '_y_epsg_4326', 'column_name': 'y_epsg_4326', 'column_type': Float},
        {'attr_name': '_geom_epsg_4326', 'column_name': 'geom_epsg_4326', 'column_type': Geometry(geometry_type='POINT', srid=4326)}
    ]


class LocatedEntityEPSG4326Old(object):

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    _latitude_epsg_4326: Mapped[Union[float, None]] = mapped_column('latitude_epsg_4326', Float, nullable=False)
    _longitude_epsg_4326: Mapped[Union[float, None]] = mapped_column('longitude_epsg_4326', Float, nullable=False)
    geometry_epsg_4326: Mapped[Union[WKBElement, None]] = mapped_column('geom_epsg_4326',
                                                                        Geometry(geometry_type='POINT', srid=4326))

    def __init__(self, latitude_epsg_4326: Optional[float] = None, longitude_epsg_4326: Optional[float] = None):
        super().__init__()
        if (latitude_epsg_4326 is not None) and not (-90 <= latitude_epsg_4326 <= 90):
            raise ValueError("Latitude WGS84 out of range")
        if (longitude_epsg_4326 is not None) and not (-180 <= longitude_epsg_4326 <= 180):
            raise ValueError("Longitude WGS84 out of range")
        self._latitude_epsg_4326 = latitude_epsg_4326
        self._longitude_epsg_4326 = longitude_epsg_4326
        self._geometry_generator_4326 = LocationConverter("_longitude_epsg_4326", "_latitude_epsg_4326", "4326", "geometry_epsg_4326")
        self._geometry_generator_4326.generate_geometry(self)
        print("Init LocatedEntity")

    def __iter__(self):
        yield "latitude_epsg_4326", self.latitude_epsg_4326
        yield "longitude_epsg_4326", self.longitude_epsg_4326
        if self.geometry_epsg_4326 is not None:
            if isinstance(self.geometry_epsg_4326, str):
                yield "geometry_epsg_4326", self.geometry_epsg_4326
            else:
                yield "geometry_epsg_4326", self.geometry_epsg_4326_as_point.wkt

    @property
    def latitude_epsg_4326(self) -> Union[float, None]:
        return self._latitude_epsg_4326

    @latitude_epsg_4326.setter
    def latitude_epsg_4326(self, latitude_epsg_4326: Union[float, None]) -> None:
        if latitude_epsg_4326 is not None:
            if not (-90 <= latitude_epsg_4326 <= 90):
                raise ValueError("Latitude WGS84 out of range")
        self._latitude_epsg_4326 = latitude_epsg_4326
        self._geometry_generator_4326.generate_geometry(self)

    @property
    def longitude_epsg_4326(self) -> Union[float, None]:
        return self._longitude_epsg_4326

    @longitude_epsg_4326.setter
    def longitude_epsg_4326(self, longitude_epsg_4326: Union[float, None]) -> None:
        if longitude_epsg_4326 is not None:
            if not (-90 <= longitude_epsg_4326 <= 90):
                raise ValueError("Latitude WGS84 out of range")
        self._longitude_epsg_4326 = longitude_epsg_4326
        self._geometry_generator_4326.generate_geometry(self)

    @property
    def geometry_epsg_4326_as_point(self) -> Union[Point, None]:
        return shape.to_shape(self.geometry_epsg_4326)
