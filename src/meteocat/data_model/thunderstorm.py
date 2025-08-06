#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# General imports
import datetime

from sqlalchemy import Integer
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from geoalchemy2 import shape
from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement

# Local project imports
from src.data_model.thunderstorm import Thunderstorm

# Typing hints imports
from sqlalchemy.orm import Mapped
from typing import List
from typing import Union
from shapely.geometry import Point
from shapely.geometry import Polygon


class MeteocatThunderstorm(Thunderstorm):
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
    # Class data
    __tablename__ = "meteocat_thunderstorm"
    _convex_hull_4258: Mapped[WKBElement] = mapped_column('convex_hull_4258', Geometry(geometry_type='POLYGON', srid=int(4258)), nullable=True)
    _convex_hull_25831: Mapped[WKBElement] = mapped_column('convex_hull_25831', Geometry(geometry_type='POLYGON', srid=int(25831)), nullable=True)
    # Inheritance
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_thunderstorm",
    }

    def __init__(self) -> None:
        """
        Initializes a Thunderstorm instance.

        This constructor delegates initialization to the base classes via `super()`.
        It does not perform any additional setup beyond inherited behavior.

        Notes
        -----
        The actual initialization must be done attribute by attribute after object creation.
        """
        super().__init__()

    @property
    def convex_hull_4258(self) -> Polygon:
        """
        Converts the stored geometry to a Shapely Polygon object.

        Returns
        -------
        shapely.geometry.Polygon
            A Shapely representation of the region's geometry.
        """
        return shape.to_shape(self._convex_hull_4258)

    @property
    def convex_hull_25831(self) -> Polygon:
        """
        Converts the stored geometry to a Shapely Polygon object.

        Returns
        -------
        shapely.geometry.Polygon
            A Shapely representation of the region's geometry.
        """
        return shape.to_shape(self._convex_hull_25831)

    def compute_lightnings_per_minute(self) -> None:
        pass

    def compute_distance(self) -> None:
        pass

    def compute_cardinal_direction(self) -> None:
        pass

    def compute_speed(self) -> None:
        pass

    def compute_convex_hull(self) -> None:
        pass

