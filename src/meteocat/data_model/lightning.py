#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# type: ignore[assignment]

from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime
import json

from src.data_model.lightning import Lightning

from sqlalchemy import Integer
from sqlalchemy import Float
from sqlalchemy import Boolean
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from typing import Optional
from typing import Union
from typing import Dict
from typing import Any


class MeteocatLightning(Lightning):
    # Metaclass location attributes
    __location__ = [
        {'epsg': 4258, 'validation': 'geographic', 'conversion': [
            {'src': 4258, 'dst': 4326},
            {'src': 4258, 'dst': 25831}
        ]},
        {'epsg': 25831, 'validation': False, 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_25831: float
    y_25831: float
    x_4258: float
    y_4258: float
    geometry_4258: Union[str, Point]
    geometry_25831: Union[str, Point]
    # SQLAlchemy columns
    __tablename__ = "meteocat_lightning"
    id: Mapped[int] = mapped_column(ForeignKey("lightning.id"), primary_key=True)
    meteocat_id: Mapped[int] = mapped_column('meteocat_id', Integer, nullable=False)
    peak_current: Mapped[float] = mapped_column('meteocat_peak_current', Float, nullable=False)
    multiplicity: Mapped[int] = mapped_column('meteocat_multiplicity', Integer, nullable=True, default=None)
    chi_squared: Mapped[float] = mapped_column('meteocat_chi_squared', Float, default=None)
    ellipse_major_axis: Mapped[float] = mapped_column('meteocat_ellipse_major_axis', Float, nullable=False)
    ellipse_minor_axis: Mapped[float] = mapped_column('meteocat_ellipse_minor_axis', Float, nullable=False)
    ellipse_angle: Mapped[float] = mapped_column('meteocat_ellipse_angle', Float, nullable=False)
    number_of_sensors: Mapped[Union[int, None]] = mapped_column('meteocat_number_of_sensors', Integer, nullable=False)
    hit_ground: Mapped[bool] = mapped_column('meteocat_hit_ground', Boolean, nullable=False, default=False)
    municipality_code: Mapped[str] = mapped_column('meteocat_municipality_code', String, default=None, nullable=True)
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_lightning",
    }

    def __init__(self, date_time: Optional[datetime.datetime] = None, meteocat_id: Optional[int] = None,
                 peak_current: Optional[float] = None, chi_squared: Optional[float] = None,
                 ellipse_major_axis: Optional[float] = None, ellipse_minor_axis: Optional[float] = None,
                 ellipse_angle: Optional[float] = None, number_of_sensors: Optional[int] = None,
                 hit_ground: bool = False, municipality_code: Optional[str] = None,
                 longitude_epsg_4258: Optional[float] = None, latitude_epsg_4258: Optional[float] = None) -> None:
        super().__init__(date_time=date_time, longitude_epsg_4326=None, latitude_epsg_4326=None)
        if (number_of_sensors is not None) and (number_of_sensors < 1):
            raise ValueError("Number of sensors must be a positive integer")
        self.meteocat_id = meteocat_id
        self.peak_current = peak_current
        self.chi_squared = chi_squared
        self.ellipse_major_axis = ellipse_major_axis
        self.ellipse_minor_axis = ellipse_minor_axis
        self.ellipse_angle = ellipse_angle
        self.number_of_sensors = number_of_sensors
        self.hit_ground = hit_ground
        self.municipality_code = municipality_code
        self.x_4258 = longitude_epsg_4258
        self.y_4258 = latitude_epsg_4258

    def __iter__(self):
        yield from super().__iter__()
        yield "meteocat_id", self.meteocat_id
        yield "peak_current", self.peak_current
        yield "multiplicity", self.multiplicity
        yield "chi_squared", self.chi_squared
        yield "ellipse_major_axis", self.ellipse_major_axis
        yield "ellipse_minor_axis", self.ellipse_minor_axis
        yield "ellipse_angle", self.ellipse_angle
        yield "number_of_sensors", self.number_of_sensors
        yield "hit_ground", self.hit_ground
        yield "municipality_code", self.municipality_code

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatLightning, Dict[str, Any], None]:
        """
        Decodes a JSON originated dict from the GisFIRE API to a MeteocatLightning object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: dict
        :return: Lightning
        """

        if all(k in dct for k in ('lightning', 'distance')):
            return dct
        if all(k in dct for k in ("meteocat_id", "peak_current", "multiplicity", "chi_squared",
                                  "ellipse_major_axis", "ellipse_minor_axis", "ellipse_angle",
                                  "number_of_sensors", "hit_ground", "municipality_code", "id",
                                  "data_provider", "x_25831", "y_25831", "x_4258", "y_4258",
                                  "date_time")):
            lightning = MeteocatLightning()
            lightning.meteocat_id = int(dct['meteocat_id'])
            lightning.peak_current = float(dct['peak_current'])
            lightning.multiplicity = int(dct['multiplicity']) if dct['multiplicity'] is not None else None
            lightning.chi_squared = float(dct['chi_squared'])
            lightning.ellipse_major_axis = float(dct['ellipse_major_axis'])
            lightning.ellipse_minor_axis = float(dct['ellipse_minor_axis'])
            lightning.ellipse_angle = float(dct['ellipse_angle'])
            lightning.number_of_sensors = int(dct['number_of_sensors'])
            lightning.hit_ground = bool(dct['hit_ground'])
            lightning.municipality_code = dct['municipality_code']
            lightning.id = int(dct['id'])
            lightning.data_provider_name = dct['data_provider']
            lightning.x_4258 = float(dct['x_4258'])
            lightning.y_4258 = float(dct['y_4258'])
            lightning.date_time = datetime.datetime.strptime(dct['date_time'], "%Y-%m-%dT%H:%M:%S%z")
            return lightning
        return None  # pragma: no cover


