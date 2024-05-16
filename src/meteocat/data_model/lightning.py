#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime

from src.data_model.lightning import Lightning

from sqlalchemy import Integer
from sqlalchemy import Float
from sqlalchemy import Boolean
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from geoalchemy2 import Geometry

from pyproj import Transformer

from typing import Optional
from typing import Union


class MeteocatLightning(Lightning):
    __tablename__ = "meteocat_lightning"
    id: Mapped[int] = mapped_column(ForeignKey("lightning.id"), primary_key=True)
    meteocat_id = mapped_column('meteocat_id', Integer, nullable=False)
    peak_current = mapped_column('meteocat_peak_current', Float, nullable=False)
    multiplicity = mapped_column('meteocat_multiplicity', Integer, nullable=True, default=None)
    chi_squared = mapped_column('meteocat_chi_squared', Float, default=None)
    ellipse_major_axis = mapped_column('meteocat_ellipse_major_axis', Float, nullable=False)
    ellipse_minor_axis = mapped_column('meteocat_ellipse_minor_axis', Float, nullable=False)
    ellipse_angle = mapped_column('meteocat_ellipse_angle', Float, nullable=False)
    number_of_sensors = mapped_column('meteocat_number_of_sensors', Integer, nullable=False)
    hit_ground = mapped_column('meteocat_hit_ground', Boolean, nullable=False, default=False)
    municipality_code = mapped_column('meteocat_municipality_code', String, default=None)
    _latitude_etrs89 = mapped_column('meteocat_latitude_erts89', Float, nullable=False)
    _longitude_etrs89 = mapped_column('meteocat_longitude_erts89', Float, nullable=False)
    _geometry_etrs89 = mapped_column('meteocat_geom_erts89', Geometry(geometry_type='POINT', srid=4258))

    __mapper_args__ = {
        "polymorphic_identity": "meteocat_lightning",
    }

    def __init__(self, date: Optional[datetime.datetime] = None, meteocat_id: Optional[int] = None,
                 peak_current: Optional[float] = None, chi_squared: Optional[float] = None,
                 ellipse_major_axis: Optional[float] = None, ellipse_minor_axis: Optional[float] = None,
                 ellipse_angle: Optional[float] = None, number_of_sensors: Optional[int] = None,
                 hit_ground: bool = False, municipality_code: Optional[str] = None,
                 latitude_etrs89: Optional[float] = None, longitude_etrs89: Optional[float] = None):
        super().__init__(date=date)
        if (latitude_etrs89 is not None) and not (-90 <= latitude_etrs89 <= 90):
            raise ValueError("Latitude ETRS89 out of range")
        if (longitude_etrs89 is not None) and not (-180 <= longitude_etrs89 <= 180):
            raise ValueError("Longitude ETRS89 out of range")
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
        self._latitude_etrs89 = latitude_etrs89
        self._longitude_etrs89 = longitude_etrs89
        if (self._latitude_etrs89 is not None) and (self._longitude_etrs89 is not None):
            self._geometry_etrs89 = "SRID=4258;POINT({0:} {1:})".format(self._longitude_etrs89, self._latitude_etrs89)
            transformer = Transformer.from_crs("EPSG:4258", "EPSG:4326")
            self.longitude_wgs84, self.latitude_wgs84 = transformer.transform(self._longitude_etrs89,
                                                                              self._latitude_etrs89)
        else:
            self._geometry_etrs89 = None
            self.longitude_wgs84 = None
            self.latitude_wgs84 = None

    @property
    def latitude_etrs89(self) -> Union[float, None]:
        return self._latitude_etrs89

    @latitude_etrs89.setter
    def latitude_etrs89(self, latitude_etrs89: Union[float, None]) -> None:
        if latitude_etrs89 is None:
            self._latitude_etrs89 = None
            self._geometry_etrs89 = None
            self.latitude_wgs84 = None
            return
        if (latitude_etrs89 is not None) and (-90 <= latitude_etrs89 <= 90):
            self._latitude_etrs89 = latitude_etrs89
            if self._longitude_etrs89 is not None:
                self._geometry_etrs89 = "SRID=4258;POINT({0:} {1:})".format(self._longitude_etrs89,
                                                                            self._latitude_etrs89)
                transformer = Transformer.from_crs("EPSG:4258", "EPSG:4326")
                self.longitude_wgs84, self.latitude_wgs84 = transformer.transform(self._longitude_etrs89,
                                                                                  self._latitude_etrs89)
            else:
                self._geometry_etrs89 = None
                self.longitude_wgs84 = None
                self.latitude_wgs84 = None
        else:
            raise ValueError("Latitude ERTS89 out of range")

    @property
    def longitude_etrs89(self) -> Union[float, None]:
        return self._longitude_etrs89

    @longitude_etrs89.setter
    def longitude_etrs89(self, longitude_erts89: Union[float, None]) -> None:
        if longitude_erts89 is None:
            self._longitude_etrs89 = None
            self._geometry_etrs89 = None
            self.longitude_wgs84 = None
            return
        if (longitude_erts89 is not None) and (-180 <= longitude_erts89 <= 180):
            self._longitude_etrs89 = longitude_erts89
            if self._latitude_etrs89 is not None:
                self._geometry_etrs89 = "SRID=4258;POINT({0:} {1:})".format(self._longitude_etrs89,
                                                                            self._latitude_etrs89)
                transformer = Transformer.from_crs("EPSG:4258", "EPSG:4326")
                self.longitude_wgs84, self.latitude_wgs84 = transformer.transform(self._longitude_etrs89,
                                                                                  self._latitude_etrs89)
            else:
                self._geometry_etrs89 = None
                self.longitude_wgs84 = None
                self.latitude_wgs84 = None
        else:
            raise ValueError("Longitude ERTS89 out of range")

    @property
    def geometry_etrs89(self) -> Union[Geometry, None]:
        return self._geometry_etrs89