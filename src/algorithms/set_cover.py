#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random
import time
import numpy as np
import networkx as nx
import gc

from ortools.linear_solver import pywraplp
from ortools.linear_solver.pywraplp import Solver

from typing import Dict
from typing import Any
from typing import List
from typing import Tuple
from typing import Optional
from typing import Union
from networkx.classes.graph import Graph

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


def isolated(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Covers all isolated points with a disk.

    :param points: A list of points to compute the isolation and coverage. A point must contain at least the id, x and
    y fields
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disk
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: The list of disks tha covers all the isolated points, the list of covered points and the execution time
    of the function
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    disks: List[Dict[str, Any]] = list()
    disk_id: int = start_disk_id
    adjacency_matrix = np.zeros((len(points), len(points)), dtype=np.int16)
    # Compute adjacency matrix using radius as threshold
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if math.sqrt((points[i]['x'] - points[j]['x']) ** 2 + (points[i]['y'] - points[j]['y']) ** 2) <= 2 * radius:
                adjacency_matrix[i, j] = 1
                adjacency_matrix[j, i] = 1
    # Search isolated points and cover them with a disk
    for i in range(len(points)):
        if points[i]['covered_by'] is None:
            num_adjacencies = np.sum(adjacency_matrix[i, :])
            if num_adjacencies == 0:
                disks.append({
                    'id': disk_id,
                    'x': points[i]['x'],
                    'y': points[i]['y'],
                    'covers': {points[i]['id']: points[i]['id']}
                })
                points[i]['covered_by'] = {disk_id: disk_id}
                disk_id += 1
            elif num_adjacencies == 1:
                j = np.where(adjacency_matrix[i, :] == 1)[0][0]
                if np.sum(adjacency_matrix[j, :]) == 1:
                    disks.append({
                        'id': disk_id,
                        'x': (points[i]['x'] + points[j]['x']) / 2,
                        'y': (points[i]['y'] + points[j]['y']) / 2,
                        'covers': {points[i]['id']: points[i]['id'], points[j]['id']: points[j]['id']}
                    })
                    points[i]['covered_by'] = {disk_id: disk_id}
                    points[j]['covered_by'] = {disk_id: disk_id}
                    disk_id += 1
    disks = [dict(disk, **{'covers_set': frozenset(disk['covers'].values())}) for disk in disks]
    return disks, [point for point in points if point['covered_by'] is not None], time.time() - start_time

def naive(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Computes a list of discs of provided radius covering all points in the points list using a naive algorithm, locating
    a disc center in a point and testing if the disc contains any other point inside

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: Return a list of discs. The discs are modeled with a numeric 'id', the 'x' and 'y' components and the
    coverage information. The covered points and the execution time of the function are also returned
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    disks: List[Dict[str, Any]] = list()
    disk_id: int = start_disk_id
    # Iterate over all points
    for i in range(len(points)):
        if points[i]['covered_by'] is None:
            # Create a disk if the point is not covered
            current_disk = {
                'id': disk_id,
                'x': points[i]['x'],
                'y': points[i]['y'],
                'covers': {points[i]['id']: points[i]['id']}
            }
            points[i]['covered_by'] = {disk_id: disk_id}
            # Iterate over non processed points
            for j in range(i + 1, len(points)):
                if points[j]['covered_by'] is None:
                    if math.sqrt((points[j]['x'] - current_disk['x']) ** 2 + (points[j]['y'] - current_disk['y']) ** 2) <= radius:
                        # Add coverage if the point lies inside the proposed disk
                        points[j]['covered_by'] = {disk_id: disk_id}
                        current_disk['covers'][points[j]['id']] = points[j]['id']
            disks.append(current_disk)
            disk_id += 1
    points, disks, _ = adjust_coverage(points, disks, radius)
    return disks, [point for point in points if point['covered_by'] is not None], time.time() - start_time


def greedy_naive(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Computes a list of discs of provided radius covering all points in the points list using a naive greedy algorithm,
    locating a disc center in a point and testing if the disc contains any other point inside adjusting the disk center
    allowing to cover other points not covered by the initial disk

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: Return a list of discs. The discs are modeled with a numeric 'id', the 'x' and 'y' components and the
    coverage information. The covered points and the execution time of the function are also returned
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    disks: List[Dict[str, Any]] = list()
    disk_id: int = start_disk_id
    # Iterate over all points
    for i in range(len(points)):
        if points[i]['covered_by'] is None:
            # If not covered, create the disk and the list (cluster) of points covered by the disk
            cluster: List[int] = [i]
            points[i]['covered_by'] = {disk_id: disk_id}
            current_disk = {
                'id': disk_id,
                'x': points[i]['x'],
                'y': points[i]['y'],
                'covers': {points[i]['id']: points[i]['id']}
            }
            changed = True
            while changed:
                # While the cluster does not change add new uncovered points if lie inside the disk and adjust the
                # circle center
                changed = False
                for j in range(i + 1, len(points)):
                    if points[j]['covered_by'] is None:
                        if math.sqrt((points[j]['x'] - current_disk['x']) ** 2 + (points[j]['y'] - current_disk['y']) ** 2) <= radius:
                            points[j]['covered_by'] = {disk_id: disk_id}
                            current_disk['covers'][points[j]['id']] = points[j]['id']
                            cluster.append(j)
                            changed = True
                circle = minimum_enclosing_circle([(points[j]['x'], points[j]['y']) for j in cluster])
                current_disk['x'] = circle['x']
                current_disk['y'] = circle['y']
            disks.append(current_disk)
            disk_id += 1
    points, disks, _ = adjust_coverage(points, disks, radius)
    return disks, [point for point in points if point['covered_by'] is not None], time.time() - start_time


def greedy_cliques(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Computes a list of discs of provided radius covering all points in the points list using a greedy clique algorithm,
    cliques can be used to solve the disk cover problem as Disk Cover Problem can be reduced to Minimal Clique Cover
    problem. The algorith converts the points to a graph, fins the graph cliques and using a greedy strategy start
    covering the points with the maximum cardinality cliques and removing the covered points from the graph.

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: Return a list of discs. The discs are modeled with a numeric 'id', the 'x' and 'y' components and the
    coverage information. The covered points and the execution time of the function are also returned
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    # Remove isolated points from the problem
    disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disk_id = start_disk_id + len(disks)
    points = [point for point in points if point['id'] not in [point['id'] for point in isolated_points]]
    points_lut = {point['id']: point for point in points}
    # Build the graph. Remember that threshold is not 2R since the maximum distance between 3 points to be inside a
    # circle of radius R is R√3
    graph: Graph = create_graph(points, radius * math.sqrt(3))
    connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    for subgraph in connected_components:
        while subgraph.number_of_nodes() != 0:
            covered_nodes = set()
            cliques = list(nx.enumerate_all_cliques(subgraph))[::-1]
            if len(cliques[0]) > 1:
                cliques = cliques[:next(i for i, clique in enumerate(cliques) if len(clique) < len(cliques[0]))]
            for clique in cliques:
                clique_set = set(clique)
                if clique_set.isdisjoint(covered_nodes):
                    clique_points = [points_lut[elem] for elem in clique]
                    circle = minimum_enclosing_circle([(clique_point['x'], clique_point['y']) for clique_point in clique_points])
                    disks.append({
                        'id': disk_id,
                        'x': circle['x'],
                        'y': circle['y'],
                        'covers': {node: node for node in clique}
                    })
                    for clique_point in clique_points:
                        if clique_point['covered_by'] is None:
                            clique_point['covered_by'] = {disk_id: disk_id}
                    disk_id += 1
                    covered_nodes |= clique_set
            subgraph.remove_nodes_from(covered_nodes)
    points, disks, _ = adjust_coverage(points, disks, radius)
    disks, _ = remove_redundant_disks(disks)
    return disks, [point for point in points + isolated_points if point['covered_by'] is not None], time.time() - start_time


def ip_max_cliques(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Computes a list of discs of provided radius covering all points in the points list using a greedy clique algorithm,
    cliques can be used to solve the disk cover problem as Disk Cover Problem can be reduced to Minimal Clique Cover
    problem. The algorith converts the points to a graph, fins the graph cliques and using a greedy strategy start
    covering the points with the maximum cardinality cliques and removing the covered points from the graph.

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: Return a list of discs. The discs are modeled with a numeric 'id', the 'x' and 'y' components and the
    coverage information. The covered points and the execution time of the function are also returned
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    # Remove isolated points from the problem
    isolated_disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disk_id = start_disk_id + len(isolated_disks)
    points = [point for point in points if point['id'] not in [point['id'] for point in isolated_points]]
    points_lut = {point['id']: point for point in points}
    new_points = isolated_points[:]
    new_disks = isolated_disks[:]
    # Build the graph. Remember that threshold is not 2R since the maximum distance between 3 points to be inside a
    # circle of radius R is R√3
    graph: Graph = create_graph(points, radius * math.sqrt(3))
    connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    for subgraph in connected_components:
        subgraph_disks: List[Dict[str, Any]] = list()
        subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
        for node in subgraph.nodes:
            cliques = list(nx.find_cliques(subgraph, [node]))
            for clique in cliques:
                clique_points = [points_lut[elem] for elem in clique]
                circle = minimum_enclosing_circle([(clique_point['x'], clique_point['y']) for clique_point in clique_points])
                subgraph_disks.append({
                    'id': disk_id,
                    'x': circle['x'],
                    'y': circle['y'],
                    'covers': {node: node for node in clique}
                })
                disk_id += 1
        subgraph_points, subgraph_disks, _ = adjust_coverage(subgraph_points, subgraph_disks, radius)
        subgraph_disks, _ = remove_redundant_disks(subgraph_disks)
        # Convert disks and points to IP
        coverage_matrix = np.zeros([len(subgraph_points), len(subgraph_disks)], dtype=int)
        subgraph_points = [dict(point, **{'ip_id': i}) for i, point in enumerate(subgraph_points, 0)]
        subgraph_points_dict = {point['id']: point for point in subgraph_points}
        for i, disk in enumerate(subgraph_disks, 0):
            for cover in disk['covers'].values():
                coverage_matrix[subgraph_points_dict[cover]['ip_id'], i] = 1
        selected_columns = [None for x in range(len(subgraph_disks))]
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            raise RuntimeError("Failed to create SCIP solver")
        for i in range(len(subgraph_disks)):
            selected_columns[i] = solver.IntVar(0, 1, "")
        for i in range(len(subgraph_points)):
            solver.Add(solver.Sum(selected_columns[j] * coverage_matrix[i, j] for j in range(len(subgraph_disks))) >= 1)
        solver.Minimize(solver.Sum(selected_columns))
        status = solver.Solve()
        if status == pywraplp.Solver.OPTIMAL:
            # print("Optimal solution found: ", [col.solution_value() for col in selected_columns])
            pass
        elif status == pywraplp.Solver.FEASIBLE:
            # print("Feasible solution found: ", [col.solution_value() for col in selected_columns])
            pass
        else:
            # print("Solution not found")
            pass
        covered_points = set()
        for i in range(len(subgraph_disks)):
            if selected_columns[i].solution_value() == 1:
                covered_points = covered_points.union(set(subgraph_disks[i]['covers'].values()))
        print(covered_points)
        new_points += [subgraph_points_dict[covered] for covered in covered_points]
        new_disks += [subgraph_disks[i] for i in range(len(subgraph_disks)) if selected_columns[i].solution_value() == 1]
    return new_disks, [point for point in new_points if point['covered_by'] is not None], time.time() - start_time


def ip_complete_cliques(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Computes a list of discs of provided radius covering all points in the points list using a greedy clique algorithm,
    cliques can be used to solve the disk cover problem as Disk Cover Problem can be reduced to Minimal Clique Cover
    problem. The algorith converts the points to a graph, fins the graph cliques and using a greedy strategy start
    covering the points with the maximum cardinality cliques and removing the covered points from the graph.

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :param start_disk_id: Identifier to assign to the first computed disk
    :type start_disk_id: int
    :return: Return a list of discs. The discs are modeled with a numeric 'id', the 'x' and 'y' components and the
    coverage information. The covered points and the execution time of the function are also returned
    :rtype: Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    points = [dict(point, **{'covered_by': None}) for point in points]
    # Remove isolated points from the problem
    isolated_disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disk_id = start_disk_id + len(isolated_disks)
    points = [point for point in points if point['id'] not in [point['id'] for point in isolated_points]]
    points_lut = {point['id']: point for point in points}
    new_points = isolated_points[:]
    new_disks = isolated_disks[:]
    # Build the graph. Remember that threshold is not 2R since the maximum distance between 3 points to be inside a
    # circle of radius R is R√3
    graph: Graph = create_graph(points, radius * math.sqrt(3))
    connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    for subgraph in connected_components:
        subgraph_disks: List[Dict[str, Any]] = list()
        subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
        cliques = list(nx.enumerate_all_cliques(subgraph))
        for clique in cliques:
            clique_points = [points_lut[elem] for elem in clique]
            circle = minimum_enclosing_circle([(clique_point['x'], clique_point['y']) for clique_point in clique_points])
            subgraph_disks.append({
                'id': disk_id,
                'x': circle['x'],
                'y': circle['y'],
                'covers': {node: node for node in clique}
            })
            disk_id += 1
        subgraph_points, subgraph_disks, _ = adjust_coverage(subgraph_points, subgraph_disks, radius)
        subgraph_disks, _ = remove_redundant_disks(subgraph_disks)
        # Convert disks and points to IP
        coverage_matrix = np.zeros([len(subgraph_points), len(subgraph_disks)], dtype=int)
        subgraph_points = [dict(point, **{'ip_id': i}) for i, point in enumerate(subgraph_points, 0)]
        subgraph_points_dict = {point['id']: point for point in subgraph_points}
        for i, disk in enumerate(subgraph_disks, 0):
            for cover in disk['covers'].values():
                coverage_matrix[subgraph_points_dict[cover]['ip_id'], i] = 1
        selected_columns: Union[Any, None] = [None for x in range(len(subgraph_disks))]
        solver: Solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            raise RuntimeError("Failed to create SCIP solver")
        for i in range(len(subgraph_disks)):
            selected_columns[i] = solver.IntVar(0, 1, "")
        for i in range(len(subgraph_points)):
            solver.Add(solver.Sum(selected_columns[j] * coverage_matrix[i, j] for j in range(len(subgraph_disks))) >= 1)
        solver.Minimize(solver.Sum(selected_columns))
        status = solver.Solve()
        if status == pywraplp.Solver.OPTIMAL:
            # print("Optimal solution found: ", [col.solution_value() for col in selected_columns])
            pass
        elif status == pywraplp.Solver.FEASIBLE:
            # print("Feasible solution found: ", [col.solution_value() for col in selected_columns])
            pass
        else:
            # print("Solution not found")
            pass
        covered_points = set()
        for i in range(len(subgraph_disks)):
            if selected_columns[i].solution_value() == 1:
                covered_points = covered_points.union(set(subgraph_disks[i]['covers'].values()))
        print(covered_points)
        new_points += [subgraph_points_dict[covered] for covered in covered_points]
        new_disks += [subgraph_disks[i] for i in range(len(subgraph_disks)) if selected_columns[i].solution_value() == 1]
    return new_disks, [point for point in new_points if point['covered_by'] is not None], time.time() - start_time


def aprox_hochbaum_mass(points: List[Dict[str, Any]], radius: float, l: int, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    # Compute max and min in x and y
    x_min = points[0]['x']
    x_max = points[-1]['x']
    y_min = points[0]['y']
    y_max = points[0]['y']
    for i in range(1, len(points)):
        if points[i]['y'] < y_min:
            y_min = points[i]['y']
        if points[i]['y'] > y_max:
            y_max = points[i]['y']
    squares: List[Dict[str, float]] = [{
        'top_left_x': x_min,
        'top_left_y': y_max,
        'bottom_right_x': x_min + (radius * 2 * l),
        'bottom_right_y': y_max - (radius * 2 * l),
    }]
    while squares[-1]['top_left_x'] < x_max:
        while squares[-1]['bottom_right_y'] > y_min:
            squares.append({
                'top_left_x': squares[-1]['top_left_x'],
                'top_left_y': squares[-1]['bottom_right_y'],
                'bottom_right_x': squares[-1]['bottom_right_x'],
                'bottom_right_y': squares[-1]['bottom_right_y'] - (radius * 2 * l),
            })
        squares.append({
            'top_left_x': squares[-1]['bottom_right_x'],
            'top_left_y': squares[0]['top_left_y'],
            'bottom_right_x': squares[-1]['bottom_right_x'] + (radius * 2 * l),
            'bottom_right_y': squares[0]['bottom_right_y'],
        })
    del squares[-1]



    return squares, squares, 0


def export_to_ampl_ip_max_cliques(points: List[Dict[str, Any]], radius: float, bases_bombers: List[any], start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    TODO

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :return: Return a list of discs. The discs are modeled with a numeric 'id', and the 'x' and 'y' components of the
    center in the Euclidean space
    :rtype: List[Dict[str, Any]]
    """
    # Record processing time
    start_time: float = time.time()
    # Rearrange IDs
    points = [dict(point, **{'covered_by': None}) for point in points]
    points_lut = {point['id']: point for point in points}
    # Remove isolated points from the problem
    print("Remove isolated points")
    isolated_disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disks: List[Dict[str, Any]] = isolated_disks
    disk_id = start_disk_id + len(disks)
    points_not_isolated = [point for point in points if point['id'] not in [point['id'] for point in isolated_points]]
    # Build the graph
    print("Build graph")
    graph = create_graph(points_not_isolated, radius * math.sqrt(3))
    # Compute connected components
    print("Computing subgraphs")
    connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    connected_components.sort(key=lambda x: len(x), reverse=True)
    for subgraph_id, subgraph in enumerate(connected_components):
        print(f"Searching cliques of subgraph {subgraph_id}")
        subgraph_disks: List[Dict[str, Any]] = list()
        subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
        cliques = list(nx.enumerate_all_cliques(subgraph))
        print(f"Found {len(cliques)} cliques in subgraph {subgraph_id}")
        print(f"Computing disks of subgraph {subgraph_id}")
        # for clique in cliques:
        #     clique_points = [points_lut[elem] for elem in clique]
        #     circle = minimum_enclosing_circle([(clique_point['x'], clique_point['y']) for clique_point in clique_points])
        #     subgraph_disks.append({
        #         'id': disk_id,
        #         'x': circle['x'],
        #         'y': circle['y'],
        #         'covers': {node: node for node in clique},
        #     })
        #     disk_id += 1
        # print(f"Found {len(subgraph_disks)} disks in subgraph {subgraph_id}")
        # print("Computing disk coverage of subgraph {subgraph_id}")
        # subgraph_points, subgraph_disks, _ = adjust_coverage(subgraph_points, subgraph_disks, radius)
        # print("Deleting redundant disks of subgraph {subgraph_id}")
        # subgraph_disks, _ = remove_redundant_disks(subgraph_disks)
        # disks += subgraph_disks
        # print(f"Found {len(subgraph_disks)} different disks in subgraph {subgraph_id}")
    print("Computing distance matrix")
    # Add bases as disks
    bases_disks = list()
    for base in bases_bombers:
        base_disk = {
            'id': disk_id,
            'x': base[1],
            'y': base[2],
        }
        disk_id += 1
        bases_disks.append(base_disk)
    disks_and_bases = disks + bases_disks
    distance_matrix = np.zeros((len(disks_and_bases), len(disks_and_bases)), dtype=int)
    for i in range(len(disks_and_bases)):
        for j in range(i, len(disks_and_bases)):
            distance = int(math.sqrt((disks_and_bases[i]['x'] - disks_and_bases[j]['x']) ** 2 + (disks_and_bases[i]['y'] - disks_and_bases[j]['y']) ** 2))
            distance_matrix[i, j] = distance
            distance_matrix[j, i] = distance
    # Build the set cover matrix
    print(f"Computing coverage matrix")
    cover_matrix = np.zeros((len(points), len(disks)))
    tr_local_id_to_row = {point['id']: i for i, point in enumerate(points, 0)}
    for i in range(len(disks)):
        for node in disks[i]['covers'].values():
            cover_matrix[tr_local_id_to_row[node], i] = 1
    file = open(f"/home/jaume/tmp/dades-v6.dat", "w")
    file.write("data;\n\n")
    file.write("set CLH := ")
    for i in range(len(disks_and_bases)):
        file.write(f" {i:6d}")
    file.write(";\n\n")
    file.write("set H := ")
    for i in range(len(disks_and_bases) - 17, len(disks_and_bases)):
        file.write(f" {i:6d}")
    file.write(";\n\n")
    file.write("param dMaxH := \n")
    for i in range(len(disks_and_bases) - 17, len(disks_and_bases)):
        file.write(f" {i:6d} 400000\n")
    file.write(";\n\n")
    file.write("set LL := ")
    for point in points:
        file.write("  {}".format(point['id']))
    file.write(";\n\n")
    file.write("set C :=\n")
    for i in range(len(disks)):
        file.write("  ({}, *) ".format(i))
        for point_id in disks[i]['covers'].values():
            file.write("  {}".format(point_id))
        file.write("\n")
    file.write(";\n\n")
    file.write("param d : ")
    for i in range(len(disks_and_bases)):
        file.write("{:8d} ".format(i))
    file.write(":=\n")
    for i in range(len(disks_and_bases)):
        file.write("          {:6d} ".format(i))
        for j in range(len(disks_and_bases)):
            file.write("  {:6d}".format(distance_matrix[i, j]))
        file.write("\n")
    file.write(";\n")
    file.close()

    # Create disks
    return disks, [point for point in points if point['covered_by'] is not None], time.time() - start_time


def export_to_ampl_all_cliques_incremental_segmented(points: List[Dict[str, Any]], radius: float, bases: List[any], start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    Generates the AMPL data files to run in an AMPL optimization modes by segmenting the space into overlapping squares
    in order to reduce the memory complexity while obtaining all cliques of the lightnings (points). Use an incremental
    clique store and retrieval to minimize memory usage. Searches the covering disks using all possible cliques of the
    adjacency graph.

    Parameters
    ----------
    points : list of dict of str: any
        A list of ordered in the X component of points corresponding a lightning strike. Each point is a dictionary
        with at least the 'x', 'y' and 'id' keys.
    radius : float
        The radius of the cover disk
    bases : list of dict of str: any
        A list of locations of the helicopter bases. Each base is a dictionary with at least the 'x', 'y' keys.
    start_disk_id : int, optional (default=0)
        The starting ID of the disk to compute

    Returns
    -------
    disks: list of dict of str: any
        A list of disks that cover the points. Each disk contain the 'x', 'y', 'id', 'covers' and 'covers_set' keys.
        The 'x' and 'y' are the location components of the center of the disk, 'id' is the unique identifier of the disk
        and 'covers' and 'covers_set' are a dict and a frozenset (to have a hashable element) with the list of point
        identifiers that are covered by the disk. There are no duplicated disks (two disks that cover the same points)
        and the identifiers are not guaranteed to be consecutive
    points: list of dict of str: any
        The same list of points passed as a parameter with the 'covered_by' key containing the dict of disks identifiers
        that cover each point
    execution_time: float
        The execution time in seconds of the function
    """
    # Record processing time
    start_time: float = time.time()
    # add covered_by keyword
    points = [dict(point, **{'covered_by': None}) for point in points]
    points_dict = {point['id']: point for point in points}
    # Calculate the bounding box of all points
    x_min = points[0]['x']
    x_max = points[-1]['x']
    y_min = points[0]['y']
    y_max = points[0]['y']
    for i in range(1, len(points)):
        if points[i]['y'] < y_min:
            y_min = points[i]['y']
        if points[i]['y'] > y_max:
            y_max = points[i]['y']
    # Calculate the overlapping squares to divide the problem in order to reduce the complexity. The squares are,
    # 20x20 km with a 2XR overlap
    square_side = 20000
    squares: List[Dict[str, float]] = [{
        'top_left_x': x_min,
        'top_left_y': y_max,
        'bottom_right_x': x_min + square_side,
        'bottom_right_y': y_max - square_side,
    }]
    while squares[-1]['top_left_x'] - (2 * radius) < x_max:
        while squares[-1]['bottom_right_y'] + (2 * radius) > y_min:
            squares.append({
                'top_left_x': squares[-1]['top_left_x'],
                'top_left_y': squares[-1]['bottom_right_y'] + (2 * radius),
                'bottom_right_x': squares[-1]['bottom_right_x'],
                'bottom_right_y': squares[-1]['bottom_right_y'] + (2 * radius) - square_side,
            })
        squares.append({
            'top_left_x': squares[-1]['bottom_right_x'] - (2 * radius),
            'top_left_y': squares[0]['top_left_y'],
            'bottom_right_x': squares[-1]['bottom_right_x'] - (2 * radius) + square_side,
            'bottom_right_y': squares[0]['bottom_right_y'],
        })
    del squares[-1]
    # Create disks structures
    disks: List[Dict[str, Any]] = list()
    disks_covers: Dict[frozenset, Dict[str, Any]] = dict()
    # Search isolated disks and
    # TODO: Remove
    print("Analyzing isolated points")
    disks_isolated, points_isolated, _ = isolated(points, radius, start_disk_id)
    disks += disks_isolated
    disk_id = start_disk_id + len(disks)
    points_not_isolated = [point for point in points if point['covered_by'] is None]
    # TODO: Remove
    print(f"Found {len(disks_isolated)} disks that cover {len(points_isolated)} points")
    # Iterate over squares
    for i, square in enumerate(squares):
        # TODO: Remove
        print(f"Analyzing square #{i}")
        # Create a list of points inside square
        points_in_square = list()
        for point in points_not_isolated:
            if point['x'] < square['top_left_x']:
                continue
            elif point['x'] >= square['bottom_right_x']:
                break
            else:
                if square['top_left_y'] >= point['y'] > square['bottom_right_y']:
                    points_in_square.append(point)
        # TODO: Remove
        print(f"Square #{i} has {len(points_in_square)} points")
        # Create the graph for the points inside the square
        graph = create_graph(points_in_square, radius * math.sqrt(3))
        disks_of_square: List[Dict[str, Any]] = list()
        # Add a disk for each clique if its points are not yet covered by an equal disk
        j = 0
        for j, clique in enumerate(nx.enumerate_all_cliques(graph)):
            # Find the circle
            clique_points = [points_dict[node] for node in clique]
            circle_points = [(clique_point['x'], clique_point['y']) for clique_point in clique_points]
            circle = minimum_enclosing_circle(circle_points)
            disk = {
                'id': disk_id,
                'x': circle['x'],
                'y': circle['y'],
                'covers': {node: node for node in clique},
            }
            # Compute which points are covered
            disk, _ = adjust_disk_coverage(points, disk, radius)
            if disk['covers_set'] not in disks_covers:
                disks_covers[disk['covers_set']] = disk
                disks_of_square.append(disk)
                disk_id += 1
            if j % 10000 == 0:
                # TODO: Remove
                print(f"Analyzing {j} cliques with {len(disks_of_square)} new disks in square {i}")
        else:
            total_cliques = j
        disks += disks_of_square
        # TODO: Remove
        print(f"Analyzed {total_cliques} cliques with {len(disks_of_square)} new disks in square {i}")
    # TODO: add covers for points
    # TODO: Remove
    print(f"Total disks: {len(disks)}")
    return disks, [dict()], 0


def export_to_ampl_all_cliques_incremental(points: List[Dict[str, Any]], radius: float, bases_bombers: List[any], start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    TODO

    :param points: List with all points to be covered, the elements of the list must be a dict with at least an 'x' and
    'y' components of type float
    :type points: List[Dict[str, Any]]
    :param radius: Radius of the disc
    :type radius: float
    :return: Return a list of discs. The discs are modeled with a numeric 'id', and the 'x' and 'y' components of the
    center in the Euclidean space
    :rtype: List[Dict[str, Any]]
    """
    # Record processing time
    start_time: float = time.time()
    # Rearrange IDs
    points = [dict(point, **{'covered_by': None}) for point in points]
    points_lut = {point['id']: point for point in points}
    # Remove isolated points from the problem
    print("Remove isolated points")
    isolated_disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disks: List[Dict[str, Any]] = isolated_disks
    disks_covers: Dict[frozenset, Dict[str, Any]] = {disk['covers_set']: disk for disk in disks}
    disk_id = start_disk_id + len(disks)
    points_not_isolated = [point for point in points if point['covered_by'] is None]
    # Build the graph
    print("Build graph")
    graph = create_graph(points_not_isolated, radius * math.sqrt(3))
    # Compute connected components
    print("Computing subgraphs")
    connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    connected_components.sort(key=lambda x: len(x), reverse=True)
    for subgraph_id, subgraph in enumerate(connected_components):
        print(f"Searching cliques of subgraph {subgraph_id}")
        subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
        for i, clique in enumerate(nx.enumerate_all_cliques(subgraph)):
            clique_points = [points_lut[elem] for elem in clique]
            circle_points = [(clique_point['x'], clique_point['y']) for clique_point in clique_points]
            circle = minimum_enclosing_circle(circle_points)
            disk = {
                'id': disk_id,
                'x': circle['x'],
                'y': circle['y'],
                'covers': {node: node for node in clique},
            }
            disk_id += 1
            _ = adjust_coverage_single_disk(subgraph_points, disk, radius)
            disk['covers_set'] = frozenset(disk['covers'].values())
            if disk['covers_set'] not in disks_covers:
                disks_covers[disk['covers_set']] = disk
                disks.append(disk)
            else:
                del disk
            del clique_points
            del circle_points
            del circle
            del clique
            if i % 100000 == 0:
                print(f"Analyzed clique {i} of subgraph {subgraph_id}. Collected {len(disks)} different disks.")
                gc.collect()
    print("Computing distance matrix")
    # Add bases as disks
    bases_disks = list()
    for base in bases_bombers:
        base_disk = {
            'id': disk_id,
            'x': base[1],
            'y': base[2],
        }
        disk_id += 1
        bases_disks.append(base_disk)
    disks_and_bases = disks + bases_disks
    distance_matrix = np.zeros((len(disks_and_bases), len(disks_and_bases)), dtype=int)
    for i in range(len(disks_and_bases)):
        for j in range(i, len(disks_and_bases)):
            distance = int(math.sqrt((disks_and_bases[i]['x'] - disks_and_bases[j]['x']) ** 2 + (disks_and_bases[i]['y'] - disks_and_bases[j]['y']) ** 2))
            distance_matrix[i, j] = distance
            distance_matrix[j, i] = distance
    # Build the set cover matrix
    print(f"Computing coverage matrix")
    cover_matrix = np.zeros((len(points), len(disks)))
    tr_local_id_to_row = {point['id']: i for i, point in enumerate(points, 0)}
    for i in range(len(disks)):
        for node in disks[i]['covers'].values():
            cover_matrix[tr_local_id_to_row[node], i] = 1
    file = open(f"/home/jaume/tmp/dades-v6.dat", "w")
    file.write("data;\n\n")
    file.write("set CLH := ")
    for i in range(len(disks_and_bases)):
        file.write(f" {i:6d}")
    file.write(";\n\n")
    file.write("set H := ")
    for i in range(len(disks_and_bases) - 17, len(disks_and_bases)):
        file.write(f" {i:6d}")
    file.write(";\n\n")
    file.write("param dMaxH := \n")
    for i in range(len(disks_and_bases) - 17, len(disks_and_bases)):
        file.write(f" {i:6d} 400000\n")
    file.write(";\n\n")
    file.write("set LL := ")
    for point in points:
        file.write("  {}".format(point['id']))
    file.write(";\n\n")
    file.write("set C :=\n")
    for i in range(len(disks)):
        file.write("  ({}, *) ".format(i))
        for point_id in disks[i]['covers'].values():
            file.write("  {}".format(point_id))
        file.write("\n")
    file.write(";\n\n")
    file.write("param d : ")
    for i in range(len(disks_and_bases)):
        file.write("{:8d} ".format(i))
    file.write(":=\n")
    for i in range(len(disks_and_bases)):
        file.write("          {:6d} ".format(i))
        for j in range(len(disks_and_bases)):
            file.write("  {:6d}".format(distance_matrix[i, j]))
        file.write("\n")
    file.write(";\n")
    file.close()

    # Create disks
    return disks, [point for point in points if point['covered_by'] is not None], time.time() - start_time


def adjust_disk_coverage(points: List[Dict[str, Any]], disk: Dict[str, Any], radius: float) -> Tuple[Dict[str, Any], float]:
    """
    Adds to the disk 'covers' attribute the points that are geometrically covered using a certain radius.

    Parameters
    ----------
    points : list os dict of str: any
        List of points to search for the disk coverage. The point must be a dict with at least the 'id', 'x' and 'y'
        keywords
    disk : dict of str: any
        The disk to search the coverage from. The point must be a dict with at least the 'x' and 'y' keywords
    radius : float
        The radius of the disk

    Returns
    -------
    disk: dict of str: any
        The provided disk with the coverage added. The coverage is a dict of points IDs (str: str) under the 'covers'
        keyword and a frozenset with the same point IDs to have a hashable element to search for future duplicated
        disks. This set is under the 'covers_set' keyword.
    execution_time: float
        The execution time in seconds of the function
    """
    # Record processing time
    start_time: float = time.time()
    # Iterate for all points
    for i in range(len(points)):
        point = points[i]
        if not (disk['x'] - point['x'] > radius): # As points are ordered by the x component, do nothing unless its x
                                                  # lays at the right of the x limit of the center - radius
            if point['x'] - disk['x'] > radius: # Stop iterating if the point lays right of the center + radius
                break
            elif math.sqrt((disk['x'] - point['x']) ** 2 + (disk['y'] - point['y']) ** 2) <= radius:
                if disk['covers'] is not None and point['id'] not in disk['covers']:
                    disk['covers'][point['id']] = point['id']
                elif disk['covers'] is None:
                    disk['covers'] = {point['id']: point['id']}
        disk['covers_set'] = frozenset(disk['covers'].keys())
    return disk, time.time() - start_time


def adjust_coverage_single_disk(points: List[Dict[str, Any]], disk: Dict[str, Any], radius: float) -> float:
    """
    It is geometrically possible that several disks having different initial points end up covering points not
    intended by the used algorithm. So, for information purposes, it is useful to update the coverage information of
    points and disks
    :param points:
    :param disk:
    :param radius:
    :return:
    """
    # Record processing time
    start_time: float = time.time()
    for i in range(len(points)):
        point = points[i]
        if not (disk['x'] - point['x'] > radius):
            if point['x'] - disk['x'] > radius:
                break
            elif math.sqrt((disk['x'] - point['x']) ** 2 + (disk['y'] - point['y']) ** 2) <= radius:
                if point['covered_by'] is not None and disk['id'] not in point['covered_by']:
                    point['covered_by'][disk['id']] = disk['id']
                elif point['covered_by'] is None:
                    point['covered_by'] = {disk['id']: disk['id']}
                if disk['covers'] is not None and point['id'] not in disk['covers']:
                    disk['covers'][point['id']] = point['id']
                elif disk['covers'] is None:
                    disk['covers'] = {point['id']: point['id']}
    return time.time() - start_time



def adjust_coverage(points: List[Dict[str, Any]], disks: List[Dict[str, Any]], radius: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """
    It is geometrically possible that several disks having different initial points end up covering points not 
    intended by the used algorithm. So, for information purposes, it is useful to update the coverage information of 
    points and disks 
    :param points: 
    :param disks: 
    :param radius: 
    :return: 
    """
    # Record processing time
    start_time: float = time.time()
    print("Ordenant Punts i disks")
    points = order_points_x(points)
    disks = order_points_x(disks)
    # Iterate to update coverage values
    first_point_index: int = 0
    break_point: int = 0
    for d, disk in enumerate(disks):
        first_point_index_updated: bool = False
        for i in range(first_point_index, len(points)):
            point = points[i]
            if not (disk['x'] - point['x'] > radius):
                if not first_point_index_updated:
                    first_point_index = i
                    first_point_index_updated = True
                if point['x'] - disk['x'] > radius:
                    break_point = i
                    break
                elif math.sqrt((disk['x'] - point['x']) ** 2 + (disk['y'] - point['y']) ** 2) <= radius:
                    if point['covered_by'] is not None and disk['id'] not in point['covered_by']:
                        point['covered_by'][disk['id']] = disk['id']
                    elif point['covered_by'] is None:
                        point['covered_by'] = {disk['id']: disk['id']}
                    if disk['covers'] is not None and point['id'] not in disk['covers']:
                        disk['covers'][point['id']] = point['id']
                    elif disk['covers'] is None:
                        disk['covers'] = {point['id']: point['id']}
        if d % 1000 == 0:
            print(f"Analitzant disk {d} de {len(disks)}; Punt d'inici: {first_point_index}, punt de break {break_point} de {len(points)} punts totals en {time.time() - start_time}s")
            start_time = time.time()
    return points, disks, time.time() - start_time
            

def remove_redundant_disks(disks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
    """
    Removes disks that cover exactly the same points. It is geometrically possible that several disks having different
    initial points end up covering the same points, so it is better to remove them to reduce complexity.

    :param disks: Disks covering lightning strikes. A disk is a dictionary with at least a x and y fields.
    :type disks: List[Dict[str, Any]]
    :return: The list of disks covering the provided points without redundancies
    """
    # Record processing time
    start_time: float = time.time()
    # Data initialization
    disks = [dict(disk, **{'covers_set': frozenset(disk['covers'].values())}) for disk in disks]
    duplicated_disks = list()
    aux_dict = {}
    # Iterate over disks
    for i in range(len(disks)):
        if disks[i]['covers_set'] in aux_dict:
            duplicated_disks.append(i)
        else:
            aux_dict[disks[i]['covers_set']] = 1
    # Remove indices backwards to avoid index modification
    for i in sorted(list(duplicated_disks), reverse=True):
        del disks[i]
    return disks, time.time() - start_time

def create_graph(points: List[Dict[str, Any]], distance: float) -> nx.Graph :
    """
    Creates a NetworkX Graph with the adjacency points using the provided distance. The provided points must contain
    an id, x and y fields. The id field will be used as the node identifier

    :param points: a list of points. A point is a dictionary with at lest an id, x and y field
    :type points: List[Dict[str, Any]]
    :param distance: Distance between points to consider them adjacent
    :type distance: float
    :return: A graph of adjacent nodes
    :rtype: nx.Graph
    """
    graph = nx.Graph()
    for i in range(len(points)):
        graph.add_node(points[i]['id'], **points[i])
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if math.sqrt((points[i]['x'] - points[j]['x']) ** 2 + (points[i]['y'] - points[j]['y']) ** 2) <= distance:
                graph.add_edge(points[i]['id'], points[j]['id'])
    return graph


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