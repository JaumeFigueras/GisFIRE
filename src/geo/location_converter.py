#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pyproj import Transformer

from typing import Any
from typing import Optional


class LocationConverter:
    def __init__(self, src_x_attr: str, src_y_attr: str, src_epsg: str, src_geom_attr: str, dst_x_attr: Optional[str] = None,
                 dst_y_attr: Optional[str] = None, dst_epsg: Optional[str] = None, dst_geom_attr: Optional[str] = None) -> None:
        self.src_x_attr = src_x_attr
        self.src_y_attr = src_y_attr
        self.src_epsg = src_epsg
        self.src_geom_attr = src_geom_attr
        self.dst_x_attr = dst_x_attr
        self.dst_y_attr = dst_y_attr
        self.dst_epsg = dst_epsg
        self.dst_geom_attr = dst_geom_attr

    def convert(self, obj: Any):
        """
        Converts the source location attributes with specified CRS to the destination location attributes with specified
        CRS and generates the Geometry string for both source and destination locations.
        """
        if hasattr(obj, self.src_x_attr) and hasattr(obj, self.src_y_attr) and hasattr(obj, self.dst_x_attr) and hasattr(obj, self.dst_y_attr):
            if getattr(obj, self.src_x_attr) is None or getattr(obj, self.src_y_attr) is None:
                setattr(obj, self.dst_x_attr, None)
                setattr(obj, self.dst_y_attr, None)
                setattr(obj, self.src_geom_attr, None)
                setattr(obj, self.dst_geom_attr, None)
                return
        if (getattr(obj, self.src_x_attr) is not None) and (getattr(obj, self.src_y_attr) is not None):
            setattr(obj, self.src_geom_attr, "SRID={2:};POINT({0:} {1:})".format(getattr(obj, self.src_x_attr), getattr(obj, self.src_y_attr), self.src_epsg))
            transformer = Transformer.from_crs("EPSG:{0:}".format(self.src_epsg), "EPSG:{0:}".format(self.dst_epsg), always_xy=True)
            tmp_x, tmp_y = transformer.transform(getattr(obj, self.src_x_attr), getattr(obj, self.src_y_attr))
            setattr(obj, self.dst_x_attr, tmp_x)
            setattr(obj, self.dst_y_attr, tmp_y)
            setattr(obj, self.dst_geom_attr, "SRID={2};POINT({0:} {1:})".format(tmp_x, tmp_y, self.dst_epsg))


