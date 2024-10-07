#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import multiprocessing as mp
import datetime

import networkx as nx
import pytz
import argparse
import json
import sys
import logging

from logging.handlers import RotatingFileHandler
from logging import Logger

from typing import Any
from typing import List


def init_pool(lock_instance, logger_instance, shared_result_list_instance, process_id_instance):
    global lock
    global logger
    global shared_result_list
    global process_id
    lock = lock_instance
    logger = logger_instance
    shared_result_list = shared_result_list_instance
    process_id = process_id_instance


def process_subgraph(arguments: List[Any]):
    filename = arguments[0]
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        logger.info("Process: {} - Processing graph: {}".format(my_id, filename))
    start_time = time.time()
    graph_json = ''
    with open(filename) as f:
        graph_json = json.load(f)
    graph = nx.node_link_graph(graph_json)
    cliques = list(nx.enumerate_all_cliques(graph))
    with lock:
        logger.info("Process: {} - Finished processing in {} seconds. Found {} cliques".format(my_id, time.time() - start_time, len(cliques)))


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log-file', help='File to log progress or errors', required=False)
    args = parser.parse_args()

    # Set up the Logger
    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Create the chunks to process in parallel
    logger.info("Starting processing all lightnings in parallel")
    chunks = [['/home/jaume/tmp/subgraph_{}.json'.format(i), i] for i in range(47)]
    print(chunks)
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    process_id = mg.list()
    process_id.append(0)
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, logger, shared_result_list, process_id))
    pool.map(func=process_subgraph, iterable=chunks)
    pool.close()
    pool.join()
    logger.info("Finished processing all lightnings in parallel")



