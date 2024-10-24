#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time

from typing import List
from typing import Dict
from typing import Any
from typing import Tuple


def order_x(points: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
    """
    Return a new list with the elements ordered by the component x

    Parameters
    ----------
    points: list of dict of str: any
        List of the elements to be sorted, the elements of the list must be a dict with at least an 'x' and 'y' keywords
        of type float

    Returns
    -------
    points: list of dict of str: any
        A sorted list using the 'x' component
    execution_time: float
        The execution time of the function
    """
    # Record processing time
    start_time: float = time.time()
    # Sort
    points = points[:]
    sorted(points, key=lambda point: point['x'])
    return points, time.time() - start_time


def remove_duplicates(points: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Return a new list without the elements that have the same location. The list must be ordered by the component x and
    they must have a 'x' and 'y' keyword.

    Parameters
    ----------
    points: list of dict of str: any
        List of elements to remove the duplicates from

    Returns
    -------
    points: list of dict of str: any
        The list pf points without duplicates
    removed_points: list of dict of str: any
        The list of points removed
    execution_time: float
        The execution time of the function
    """
    # Record processing time
    start_time: float = time.time()
    # Search the indices to be removed of the list
    indices_to_remove: List[int] = list()
    for i in range(len(points) - 1):
        if points[i]['x'] == points[i + 1]['x'] and points[i]['y'] == points[i + 1]['y']:
            indices_to_remove.append(i + 1)
    # Create the return lists
    points = points[:]
    removed_points = list()
    # Remove the points (reversed) preventing alteration of the iteration list
    for i in sorted(list(indices_to_remove), reverse=True):
        removed_points.append(points[i])
        del points[i]
    return points, removed_points, time.time() - start_time



