#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import multiprocessing as mp
import numpy as np
import networkx as nx
import math
import json

from copy import deepcopy

from ortools.linear_solver import pywraplp
from ortools.linear_solver.pywraplp import Solver

from .set_cover import isolated
from .set_cover import create_graph
from .set_cover import minimum_enclosing_circle
from .set_cover import adjust_coverage
from .set_cover import remove_redundant_disks

from typing import Dict
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from networkx.classes.graph import Graph

global lock
global shared_result_list
global process_id


def init_pool(lock_instance, shared_result_list_instance, process_id_instance):
    global lock
    global shared_result_list
    global process_id
    lock = lock_instance
    shared_result_list = shared_result_list_instance
    process_id = process_id_instance


def generate_cpu_load(arguments):
    "Generate a utilization % for a duration of interval seconds"
    global lock
    global shared_result_list
    global process_id
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        print("Start process {}".format(my_id))
    interval: int = arguments[0]
    utilization: int = arguments[1]
    start_time = time.time()
    for i in range(0,int(interval)):
        print("About to do some arithmetic")
        while time.time()-start_time < utilization/100.0:
            a = math.sqrt(64*64*64*64*64)
        print(str(i) + ". About to sleep")
        time.sleep(1-utilization/100.0)
        start_time += 1


def process_disks_ip(args: List[Any]):
    global lock
    global shared_result_list
    global process_id
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        print("Start process {}".format(my_id))
    start_time = time.time()
    # Get data
    subgraph = args[0]
    points = args[1]
    radius = args[2]
    points_lut = {point['id']: point for point in points}
    disk_id = 10000 * (my_id + 1)
    # Analyze subgraph
    subgraph_disks: List[Dict[str, Any]] = list()
    subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
    try:
        cliques = list(nx.enumerate_all_cliques(subgraph, backend='cugraph'))
    except RuntimeError:
        cliques = list(nx.enumerate_all_cliques(subgraph))
    for clique in cliques:
        clique_points = [points_lut[elem] for elem in clique]
        circle = minimum_enclosing_circle([(clique_point['x'], clique_point['y']) for clique_point in clique_points])
        subgraph_disks.append({
            'id': disk_id,
            'x': circle['x'],
            'y': circle['y'],
            'covers': clique,
        })
        disk_id += 1
    subgraph_points, subgraph_disks, _ = adjust_coverage(subgraph_points, subgraph_disks, radius)
    subgraph_disks, _ = remove_redundant_disks(subgraph_disks)
    # Convert disks and points to IP
    coverage_matrix = np.zeros([len(subgraph_points), len(subgraph_disks)], dtype=int)
    subgraph_points = [dict(point, **{'ip_id': i}) for i, point in enumerate(subgraph_points, 0)]
    subgraph_points_dict = {point['id']: point for point in subgraph_points}
    for i, disk in enumerate(subgraph_disks, 0):
        for cover in disk['covers']:
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
            covered_points = covered_points.union(set(subgraph_disks[i]['covers']))
    new_points = [subgraph_points_dict[covered] for covered in covered_points]
    new_disks = [subgraph_disks[i] for i in range(len(subgraph_disks)) if selected_columns[i].solution_value() == 1]
    with lock:
        shared_result_list.append([new_points, new_disks])
        print("Process {} finished".format(my_id))


def ip_complete_cliques_multiprocessing(points: List[Dict[str, Any]], radius: float, start_disk_id: Optional[int] = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
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
    points_lut = {point['id']: point for point in points}
    # Remove isolated points from the problem
    isolated_disks, isolated_points, _ = isolated(points, radius, start_disk_id)
    # Update the points
    disk_id = start_disk_id + len(isolated_disks)
    points = [point for point in points if point['id'] not in [point['id'] for point in isolated_points]]
    new_points = isolated_points[:]
    new_disks = isolated_disks[:]
    # Build the graph. Remember that threshold is not 2R since the maximum distance between 3 points to be inside a
    # circle of radius R is R√3
    print("Analyzing graph")
    graph: Graph = create_graph(points, radius * math.sqrt(3))
    try:
        connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph, backend='cugraph')]
    except RuntimeError:
        connected_components = [graph.subgraph(c).copy() for c in nx.connected_components(graph)]
    for i, subgraph in enumerate(connected_components, 0):
        subgraph_disks: List[Dict[str, Any]] = list()
        subgraph_points: List[Dict[str, Any]] = [point for point in points if point['id'] in subgraph.nodes]
        print("Finding cliques")
        cliques = list(nx.enumerate_all_cliques(subgraph))
        print(len(cliques))
        print("Generate disks")
        for clique in cliques:
            clique_points = [points_lut[elem] for elem in clique]
            circle = minimum_enclosing_circle(
                [(clique_point['x'], clique_point['y']) for clique_point in clique_points])
            subgraph_disks.append({
                'id': disk_id,
                'x': circle['x'],
                'y': circle['y'],
                'covers': clique,
            })
            disk_id += 1
        print("Adjusting coverage")
        subgraph_points, subgraph_disks, _ = adjust_coverage(subgraph_points, subgraph_disks, radius)
        print("Removing redundant disks")
        subgraph_disks, _ = remove_redundant_disks(subgraph_disks)
    return None
    print("Starting Multiprocessing")
    # Setup multiprocessing
    global lock
    global shared_result_list
    global process_id
    chunks = [[connected_components[i], [deepcopy(point) for point in points], radius] for i in range(len(connected_components))]
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    process_id = mg.list()
    process_id.append(0)
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, shared_result_list, process_id))
    pool.map(func=process_disks_ip, iterable=chunks)
    print(process_id[0])
    print("Waiting for processes")
    pool.close()
    pool.join()
    for result in shared_result_list:
        new_points += result[0]
        new_disks += result[1]
    return new_disks, [point for point in new_points if point['covered_by'] is not None], time.time() - start_time

