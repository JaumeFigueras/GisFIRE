#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random

from qgis.core import QgsPointXY

from typing import List
from typing import Tuple
from typing import Dict
from typing import Optional

def interpolate_circle(point: QgsPointXY, radius: float, num_points: int = 100) -> List[QgsPointXY]:
    """
    Interpolates a circle with center in point with radius and sampled with num_points

    :param point:
    :param radius:
    :param num_points:
    :return:
    """
    angles = [2 * math.pi * (i / num_points) for i in range(num_points)]
    points = [QgsPointXY(radius * math.cos(angle) + point.x(), radius * math.sin(angle) + point.y()) for angle in angles]
    points.append(points[0])
    return points

