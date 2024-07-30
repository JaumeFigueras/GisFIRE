#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from sqlalchemy import DateTime, String
from sqlalchemy import Float
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.orm import mapped_column
from geoalchemy2 import shape
from geoalchemy2 import Geometry
from shapely.geometry import Point

from src.geo.location_converter import LocationConverter
from src.geo.geometry_generator import GeometryGenerator

from typing import Optional
from typing import List
from typing import Union
from typing import Any


class ModelMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        """
        Metaclass Constructor. Creates the Location and DateTime parts of the database tables with its getters and
        setters

        :param name:
        :param bases:
        :param dct:
        """

        def property_factory_xy(attr: str, generator_attr: Optional[str] = None,
                                converter_attrs: Optional[List[str]] = None,
                                validator: Optional[str] = None) -> property:
            """
            Factory to create the getters and setters of the x, y location attributes

            :param attr:
            :param generator_attr:
            :param converter_attrs:
            :param validator:
            :return:
            """
            def getter(self) -> float:
                """
                Getter of the x, y location attributes
                :param self:
                :return:
                """
                return getattr(self, '_' + attr)

            def setter(self, value) -> None:
                """
                Setter of the x, y location attributes. Applies the value validation depending on the validation string
                received by the factory

                :param self:
                :param value:
                :return:
                """
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

        def property_factory_geometry(attr) -> property:
            """
            Factory to create the geometry attribute

            :param attr:
            :return:
            """
            def getter(self) -> Union[str, Point, None]:
                geometry = getattr(self, '_' + attr)
                if geometry is not None:
                    if isinstance(geometry, str):
                        return geometry
                    else:
                        return shape.to_shape(geometry)
                return None

            def setter(self, value) -> None:
                """
                The geometry attribute cannot be set, so the function does nothing

                :param self:
                :param value:
                :return:
                """
                pass

            return property(getter, setter)

        def property_factory_datetime(attr: str) -> property:
            """
            Factory to create the datetime attributes

            :param attr:
            :return:
            """
            def getter(self) -> datetime.datetime:
                """
                Returns the date time attribute

                :param self:
                :return:
                """
                return getattr(self, attr)

            def setter(self, value) -> None:
                """
                Sets the datetime and timezone information of the attribute

                :param self:
                :param value:
                :return:
                """
                if value is not None:
                    if value.tzinfo is None:
                        raise ValueError('Date must contain timezone information')
                    setattr(self, '_tzinfo' + attr, str(value.tzinfo))
                    setattr(self, attr, value)
                else:
                    setattr(self, '_tzinfo' + attr, None)
                    setattr(self, attr, None)

            return property(getter, setter)

        def property_factory_default(attr: str) -> property:
            """
            Implements a property factory with the default getter and setter

            :param attr:
            :return:
            """
            def getter(self) -> Any:
                """
                Default getter

                :param self:
                :return:
                """
                return getattr(self, attr)

            def setter(self, value: Any) -> None:
                """
                Default setter

                :param self:
                :param value:
                :return:
                """
                setattr(self, attr, value)

            return property(getter, setter)

        if '__location__' in dct:
            location = dct.pop('__location__', [])
            for col_def in location:
                epsg = str(col_def['epsg'])
                validation = col_def['validation']
                conversion = col_def['conversion']
                setattr(cls, '_x_' + epsg, mapped_column('x_' + epsg, Float, nullable=False))
                setattr(cls, '_y_' + epsg, mapped_column('y_' + epsg, Float, nullable=False))
                setattr(cls, '_geometry_' + epsg, mapped_column('geometry_' + epsg, Geometry(geometry_type='POINT', srid=int(epsg)), nullable=False))
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
                        setattr(cls, 'geometry_converter_' + src + '_' + dst, converter)
                        converter_attrs.append('geometry_converter_' + src + '_' + dst)
                if validation == 'geographic':
                    setattr(cls, 'x_' + epsg, property_factory_xy('x_' + epsg, 'geometry_generator_' + epsg, converter_attrs, 'longitude'))
                    setattr(cls, 'y_' + epsg, property_factory_xy('y_' + epsg, 'geometry_generator_' + epsg, converter_attrs, 'latitude'))
                else:
                    setattr(cls, 'x_' + epsg, property_factory_xy('x_' + epsg, 'geometry_generator_' + epsg, converter_attrs))
                    setattr(cls, 'y_' + epsg, property_factory_xy('y_' + epsg, 'geometry_generator_' + epsg, converter_attrs))

        if '__date__' in dct:
            dates = dct.pop('__date__', [])
            for attribute in dates:
                attribute_name = column_name = attribute['name']
                protected_attribute_name = '_' + attribute_name
                nullable = attribute['nullable']
                setattr(cls, protected_attribute_name, mapped_column(column_name, DateTime(timezone=True), nullable=nullable))
                setattr(cls, '_tzinfo' + protected_attribute_name, mapped_column('tzinfo_' + column_name, String, nullable=nullable))
                setattr(cls, attribute_name, property_factory_datetime(protected_attribute_name))
                setattr(cls, 'tzinfo_' + attribute_name, property_factory_default('_tzinfo' + protected_attribute_name))

        super().__init__(name, bases, dct)
