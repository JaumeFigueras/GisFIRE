#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random

from typing import Dict
from typing import Any
from typing import List
from typing import Tuple
from typing import Optional

def order_points_x(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return a new list with the elements ordered by the component x

    :param points: List with all points to be sorted, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :return: A sorted list using the 'x' component
    :rtype: List[Dict[str, Any]]
    """
    points = points[:]
    return sorted(points, key=lambda point: point['x'])


def remove_duplicates(points: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Return a new list without the points that have the same location. The list must be ordered

    :param points:
    :return:
    """
    indices_to_remove: List[int] = list()
    for i in range(len(points) - 1):
        if points[i]['x'] == points[i + 1]['x'] and points[i]['y'] == points[i + 1]['y']:
            indices_to_remove.append(i + 1)
    points = points[:]
    removed_points = list()
    for i in sorted(list(indices_to_remove), reverse=True):
        removed_points.append(points[i])
        del points[i]
    return points, removed_points

def naive(points: List[Dict[str, Any]], radius: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Return a list of discs of provided radius covering all points in the points list using a naive algorithm, locating
    a disc center in a point and testing if the disc contains any other point inside
    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :return: Return a list of discs. The discs are modeled with a numeric 'id', and the 'x' and 'y' components of the
    center in the Euclidean space
    :rtype: List[Dict[str, Any]]
    """
    points = [dict(point, **{'covered_by': None}) for point in points]
    disks: List[Dict[str, Any]] = list()
    disk_id: int = 0
    for i in range(len(points)):
        if points[i]['covered_by'] is None:
            current_disk = {
                'id': disk_id,
                'x': points[i]['x'],
                'y': points[i]['y']
            }
            points[i]['covered_by'] = current_disk['id']
            for j in range(i + 1, len(points)):
                if points[j]['covered_by'] is None:
                    if math.sqrt((points[j]['x'] - current_disk['x']) ** 2 + (points[j]['y'] - current_disk['y']) ** 2) <= radius:
                        points[j]['covered_by'] = current_disk['id']
            disks.append(current_disk)
            disk_id += 1
    return disks, [point for point in points if point['covered_by'] is not None]


def greedy_naive(points: List[Dict[str, Any]], radius: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """

    :param points:
    :param radius:
    :return:
    """
    points = [dict(point, **{'covered_by': None}) for point in points]
    disks: List[Dict[str, Any]] = list()
    disk_id: int = 0
    for i in range(len(points)):
        if points[i]['covered_by'] is None:
            cluster: List[int] = [i]
            points[i]['covered_by'] = disk_id
            current_disk = {
                'id': disk_id,
                'x': points[i]['x'],
                'y': points[i]['y']
            }
            changed = True
            while changed:
                changed = False
                for j in range(i + 1, len(points)):
                    if points[j]['covered_by'] is None:
                        if math.sqrt((points[j]['x'] - current_disk['x']) ** 2 + (points[j]['y'] - current_disk['y']) ** 2) <= radius:
                            points[j]['covered_by'] = disk_id
                            cluster.append(j)
                            changed = True
                circle = minimum_enclosing_circle([(points[j]['x'], points[j]['y']) for j in cluster])
                current_disk = {
                    'id': disk_id,
                    'x': circle['x'],
                    'y': circle['y']
                }
            disks.append(current_disk)
            disk_id += 1
    return disks, [point for point in points if point['covered_by'] is not None]


def minimum_enclosing_circle(points: List[Tuple[float, float]]) -> Dict[str, float]:
    """
    Computes the minimal enclosing circle Welzl recursive, but linear cost, algorithm. Solves the problem explained
    https://en.wikipedia.org/wiki/Smallest-circle_problem implementing a smaller version from
    https://www.nayuki.io/page/smallest-enclosing-circle

    :param points: The set of points to find the minimum enclosing centre
    :type points: List[Tuple[float, float]]
    :return: The minimal enclosing circle as a dictionary with the x, y and radius of the circle
    :rtype: Dict[str, float]
    """
    random.shuffle(points)
    circle = mec(points, len(points), [(0,0), (0, 0), (0, 0)], 0)
    return {
        'x': circle[0],
        'y': circle[1],
        'radius': circle[2]
    }


def point_inside_circle(circle: Tuple[float, float, float], point: Tuple[float, float]) -> bool:
    """
    Return True if the provided point is inside the circle, False otherwise

    :param circle: The circle as a tuple of x, y, radius
    :type circle: Tuple[float, float, float]
    :param point: The point to check
    :type point: Tuple[float, float]
    :return: True if the provided point is inside the circle, False otherwise
    :rtype: bool
    """
    return math.sqrt((point[0] - circle[0]) ** 2 + (point[1] - circle[1]) ** 2) < circle[2]

def compute_circle(a: Tuple[float, float], b: Optional[Tuple[float, float]] = None, c: Tuple[float, float] = None) -> Tuple[float, float, float]:
    """
    Calculates the circle that contains the points a, b and c if all of three points are provided, the circle in the
    middle of the line segment if only a and b points are provided or the circle in the point a with radius 0 if only
    the point a is provided

    :param a: First point
    :type a: Tuple[float, float]
    :param b: Second point
    :type b: Tuple[float, float]
    :param c: Third point
    :type c: Tuple[float, float]
    :return: The circle that contains the points a, b and c
    :rtype: Tuple[float, float, float]
    """
    if b is not None and c is not None:
        aa = b[0] - a[0]
        bb = b[1] - a[1]
        cc = c[0] - a[0]
        dd = c[1] - a[1]
        ee = aa * (b[0] + a[0]) * 0.5 + bb * (b[1] + a[1]) * 0.5
        ff = cc * (c[0] + a[0]) * 0.5 + dd * (c[1] + a[1]) * 0.5
        det = aa * dd - bb * cc
        cx = (dd * ee - bb * ff) / det
        cy = (-cc * ee + aa * ff) / det
        return cx, cy, math.sqrt((a[0] - cx) ** 2 + (a[1] - cy) ** 2)
    elif b is not None and c is None:
        return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) / 2
    else:
        return a[0], a[1], 0


def mec(points: List[Tuple[float, float]], n: int, boundary: List[Tuple[float, float]], b: int) -> Tuple[float, float, float]:
    """
    Implements the Welzl algorithm to find the minimal enclosing circle
    https://en.wikipedia.org/wiki/Smallest-circle_problem#Welzl's_algorithm

    :param points: A list of random placed points
    :type points: List[Tuple[float, float]]
    :param n: The number of points to find the minimum enclosing circle
    :type n: int
    :param boundary: A list of maximum three points that define the boundary of the enclosing circle
    :type boundary: List[Tuple[float, float]]
    :param b: The number of points defining the boundary circle
    :type b: int
    :return: The minimal enclosing circle
    :rtype: Tuple[float, float, float]
    """
    circle: Tuple[float, float, float]
    if b == 3:
        circle = compute_circle(boundary[0], boundary[1], boundary[2])
    elif n == 1 and b == 0:
        circle = compute_circle(points[0])
    elif n == 0 and b == 2:
        circle = compute_circle(boundary[0], boundary[1])
    elif n == 1 and b == 1:
        circle = compute_circle(boundary[0], points[0])
    else:
        circle = mec(points, n - 1, boundary, b)
        if not point_inside_circle(circle, points[n-1]):
            boundary[b] = points[n-1]
            b += 1
            circle = mec(points, n - 1, boundary, b)
    return circle