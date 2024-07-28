#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any


class GeometryGenerator(object):
    def __init__(self, src_x_attr: str, src_y_attr: str, src_epsg: str, src_geom_attr: str) -> None:
        self.src_x_attr = src_x_attr
        self.src_y_attr = src_y_attr
        self.src_epsg = src_epsg
        self.src_geom_attr = src_geom_attr

    def generate(self, obj: Any):
        if (getattr(obj, self.src_x_attr) is not None) and (getattr(obj, self.src_y_attr) is not None):
            setattr(obj, self.src_geom_attr, "SRID={2:};POINT({0:} {1:})".format(getattr(obj, self.src_x_attr), getattr(obj, self.src_y_attr), self.src_epsg))
        else:
            setattr(obj, self.src_geom_attr, None)

