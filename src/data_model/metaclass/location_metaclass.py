#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import Float
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.orm import mapped_column
from geoalchemy2 import shape
from geoalchemy2 import Geometry

from src.geo.location_converter import LocationConverter
from src.geo.geometry_generator import GeometryGenerator

from typing import Optional
from typing import List


class LocationMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):

        def property_factory_xy(attr: str, generator_attr: Optional[str] = None,
                                converter_attrs: Optional[List[str]] = None, validator: Optional[str] = None) -> property:
            def getter(self):
                return getattr(self, '_' + attr)

            def setter(self, value):
                if validator is not None and value is not None:
                    if validator == 'longitude':
                        if not (-180 <= value <= 180):
                            raise ValueError("Longitude out of range")
                    elif validator == 'latitude':
                        if not (-90 <= value <= 90):
                            raise ValueError("Latitude out of range")
                setattr(self, '_' + attr, value)
                if generator_attr is not None:
                    generator: GeometryGenerator = getattr(self, generator_attr)
                    generator.generate(self)
                if converter_attrs is not None:
                    for converter_attr in converter_attrs:
                        converter: LocationConverter = getattr(self, converter_attr)
                        converter.convert(self)

            return property(getter, setter)

        def property_factory_geometry(attr):
            def getter(self):
                geometry = getattr(self, '_' + attr)
                if geometry is not None:
                    if isinstance(geometry, str):
                        return geometry
                    else:
                        return shape.to_shape(geometry)
                return None

            def setter(self, value):
                pass

            return property(getter, setter)

        if 'location' in dct:
            location = dct.pop('location', [])
            for col_def in location:
                epsg = str(col_def['epsg'])
                validation = col_def['validation']
                conversion = col_def['conversion']
                setattr(cls, '_x_' + epsg, mapped_column('x_' + epsg, Float, nullable=False))
                setattr(cls, '_y_' + epsg, mapped_column('y_' + epsg, Float, nullable=False))
                setattr(cls, '_geometry_' + epsg, mapped_column('geometry_' + epsg, Geometry(geometry_type='POINT', srid=4326), nullable=False))
                setattr(cls, 'geometry_' + epsg, property_factory_geometry('geometry_' + epsg))
                generator = GeometryGenerator('_x_' + epsg, '_y_' + epsg,  epsg, '_geometry_' + epsg)
                setattr(cls, 'geometry_generator_' + epsg, generator)
                converter_attrs = None
                if conversion:
                    converter_attrs = list()
                    for conversion_parameters in conversion:
                        src = str(conversion_parameters['src'])
                        dst = str(conversion_parameters['dst'])
                        converter = LocationConverter('_x_' + src, '_y_' + src,  src, '_geometry_' + src, '_x_' + dst,
                                                      '_y_' + dst,  dst, '_geometry_' + dst)
                        setattr(cls, 'geometry_converter_' + src + '_' + 'dst', converter)
                        converter_attrs.append('geometry_converter_' + src + '_' + 'dst')
                if validation == 'geographic':
                    setattr(cls, 'x_' + epsg, property_factory_xy('x_' + epsg, 'geometry_generator_' + epsg, converter_attrs, 'longitude'))
                    setattr(cls, 'y_' + epsg, property_factory_xy('y_' + epsg, 'geometry_generator_' + epsg, converter_attrs, 'latitude'))
                else:
                    setattr(cls, 'x_' + epsg, property_factory_xy('x_' + epsg, 'geometry_generator_' + epsg, converter_attrs))
                    setattr(cls, 'y_' + epsg, property_factory_xy('y_' + epsg, 'geometry_generator_' + epsg, converter_attrs))

        super().__init__(name, bases, dct)


