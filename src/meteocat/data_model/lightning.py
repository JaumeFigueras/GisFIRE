#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# type: ignore[assignment]

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
from shapely.geometry import Point

from typing import Optional
from typing import Union


class MeteocatLightning(Lightning):
    # Metaclass location attributes
    location = [
        {'epsg': 4258, 'validation': 'geographic', 'conversion': [
            {'src': 4258, 'dst': 4326},
            {'src': 4258, 'dst': 25831}
        ]},
        {'epsg': 25831, 'validation': False, 'conversion': False}
    ]

    x_25831: float
    y_25831: float
    geometry_4258: Union[str, Point]
    geometry_25831: Union[str, Point]

    __tablename__ = "meteocat_lightning"
    id: Mapped[int] = mapped_column(ForeignKey("lightning.id"), primary_key=True)
    meteocat_id: Mapped[int] = mapped_column('meteocat_id', Integer, nullable=False)
    peak_current: Mapped[float] = mapped_column('meteocat_peak_current', Float, nullable=False)
    multiplicity: Mapped[str] = mapped_column('meteocat_multiplicity', Integer, nullable=True, default=None)
    chi_squared: Mapped[float] = mapped_column('meteocat_chi_squared', Float, default=None)
    ellipse_major_axis: Mapped[float] = mapped_column('meteocat_ellipse_major_axis', Float, nullable=False)
    ellipse_minor_axis: Mapped[float] = mapped_column('meteocat_ellipse_minor_axis', Float, nullable=False)
    ellipse_angle: Mapped[float] = mapped_column('meteocat_ellipse_angle', Float, nullable=False)
    number_of_sensors: Mapped[Union[int, None]] = mapped_column('meteocat_number_of_sensors', Integer, nullable=False)
    hit_ground: Mapped[bool] = mapped_column('meteocat_hit_ground', Boolean, nullable=False, default=False)
    municipality_code: Mapped[str] = mapped_column('meteocat_municipality_code', String, default=None, nullable=True)

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
        self.x_4258 = latitude_epsg_4258
        self.y_4258 = longitude_epsg_4258

    def __iter__(self):
        super().__iter__()
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
        yield "longitude_epsg_4258", self._longitude_epsg_4258
        yield "latitude_epsg_4258", self._latitude_epsg_4258
        if self.geometry_epsg_4326 is not None:
            if isinstance(self.geometry_epsg_4326, str):
                yield "geometry_epsg_4258", self.geometry_epsg_4258
            else:
                yield "geometry_epsg_4258", self.geometry_epsg_4258_as_point.wkt
        else:
            yield "geometry_epsg_4258", None
        yield "longitude_epsg_25831", self._longitude_epsg_25831
        yield "latitude_epsg_25831", self._latitude_epsg_25831
        if self.geometry_epsg_25831 is not None:
            if isinstance(self.geometry_epsg_25831, str):
                yield "geometry_epsg_25831", self.geometry_epsg_25831
            else:
                yield "geometry_epsg_25831", self.geometry_epsg_25831_as_point.wkt
        else:
            yield "geometry_epsg_25831", None


