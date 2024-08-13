#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import enum
import datetime
import json

from sqlalchemy import Float
from sqlalchemy import String
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model.wildfire_ignition import WildfireIgnition
from src.data_model.wildfire_ignition import WildfireIgnitionCategory

from typing import Union
from typing import Dict
from typing import Optional
from typing import Any
from typing import Iterator


class BomberscatValidationLevelCategory(enum.StrEnum):
    NONE = 'NONE'
    CORRECTED = 'CORRECTED'
    UNUSABLE = 'UNUSABLE'
    DISCARDED = 'DISCARDED'


class BomberscatWildfireIgnition(WildfireIgnition):
    """
    Class container for the weather station table.  Provides the SQL Alchemy access to the different weather stations.

    The weather station information is obtained from the MeteoCat API call described in:
    https://apidocs.meteocat.gencat.cat/documentacio/metadades-estacions/#metadades-de-totes-les-estacions

    :type __tablename__: str
    :type id: int
    :type code: str
    :type name: str
    :type category: WeatherStationCategory
    :type _coordinates_latitude: float
    :type _coordinates_longitude: float
    :type placement: str
    :type altitude: float
    :type municipality_code: int
    :type municipality_name: str
    :type county_code: int
    :type county_name: str
    :type province_code: int
    :type province_name: str
    :type network_code: int
    :type network_name: str
    :type ts: datetime
    :type postgis_geometry = str or Column
    :type states: relationship
    :type measures: relationship
    """
    # Metaclass location attributes
    __location__ = [
        {'epsg': 25831, 'validation': False, 'conversion': [
            {'src': 25831, 'dst': 4326},
            {'src': 25831, 'dst': 4258}
        ]},
        {'epsg': 4258, 'validation': False, 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_25831: float
    y_25831: float
    geometry_25831: Union[str, Point]
    x_4258: float
    y_4258: float
    geometry_4258: Union[str, Point]
    # SQLAlchemy columns
    __tablename__ = 'bomberscat_wildfire_ignition'
    id: Mapped[int] = mapped_column(ForeignKey("wildfire_ignition.id"), primary_key=True)
    region: Mapped[str] = mapped_column('region', String, nullable=False)
    burned_surface: Mapped[float] = mapped_column('burned_surface', Float)
    validation_level: Mapped[BomberscatValidationLevelCategory] = mapped_column('validation_level', Enum(BomberscatValidationLevelCategory, name='bomberscat_validation_level_category'), nullable=False)
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_weather_station",
    }

    def __init__(self, name: Optional[str] = None, ignition_cause: Optional[WildfireIgnitionCategory] = None,
                 x_epsg_25831: Optional[float] = None, y_epsg_25831: Optional[float] = None,
                 region: Optional[str] = None, burned_surface: Optional[float] = None,
                 validation_level: Optional[BomberscatValidationLevelCategory] = None) -> None:
        """

        :param name:
        :param ignition_cause:
        :param longitude_epsg_25831:
        :param latitude_epsg_25831:
        :param region:
        :param burned_surface:
        :param validation_level:
        """
        super().__init__(name, ignition_cause)
        self.x_25831 = x_epsg_25831
        self.y_25831 = y_epsg_25831
        self.region = region
        self.burned_surface = burned_surface
        self.validation_level = validation_level

    def __iter__(self) -> Iterator[Any]:
        yield from super().__iter__()
        yield 'region', self.region
        yield 'validation_level', self.validation_level.name
        yield 'burned_surface', self.burned_surface

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[BomberscatWildfireIgnition, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a Lightning object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: dict
        :return: Lightning
        """
        # Lat-lon coordinates dict of the Meteocat API JSON
        if all(k in dct for k in ('id', 'name', 'ignition_cause', 'region', 'burned_surface', 'validation_level',
                                  'data_provider', 'x_4326', 'y_4326', 'x_25831', 'y_25831', 'x_4258', 'y_4258',
                                  'date_time', 'ts')):
            ignition = BomberscatWildfireIgnition()
            ignition.id = dct['id']
            ignition.name = dct['name']
            ignition.ignition_cause = dct['ignition_cause']
            ignition.x_25831 = dct['x_4258']
            ignition.y_25831 = dct['y_4258']
            ignition.data_provider_name = dct['data_provider']
            ignition.date_time = datetime.datetime.strptime(dct['date_time'], "%Y-%m-%dT%H:%M:%S%z")
            ignition.validation_level = BomberscatValidationLevelCategory[dct['validation_level']]
            ignition.burned_surface = dct['burned_surface']
            return ignition
        return None  # pragma: no cover

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a database lightning to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj:
            :type obj: object
            :return: dict
            """
            if isinstance(obj, BomberscatWildfireIgnition):
                obj: BomberscatWildfireIgnition
                dct_ignition = dict(obj)
                return dct_ignition
            return json.JSONEncoder.default(self, obj)  # pragma: no cover

    class GeoJSONEncoder(json.JSONEncoder):
        """
        Geo JSON Encoder to convert a database weather station to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj:
            :type obj: object
            :return: dict
            """
            if isinstance(obj, BomberscatWildfireIgnition):
                obj: BomberscatWildfireIgnition
                dct = dict()
                dct['type'] = 'Feature'
                dct['id'] = obj.id
                dct['geometry'] = dict()
                dct['geometry']['type'] = 'Point'
                dct['geometry']['coordinates'] = [obj.x_4326, obj.y_4326]
                dct['properties'] = dict(obj)
                return dct
            return json.JSONEncoder.default(self, obj)  # pragma: no cover