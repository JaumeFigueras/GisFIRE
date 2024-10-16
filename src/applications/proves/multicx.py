#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import multiprocessing as mp
import math
import logging

from copy import deepcopy

from typing import Dict
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from networkx.classes.graph import Graph


def init_pool(lock_instance, logger_instance, shared_result_list_instance, process_id_instance):
    global lock
    global logger
    global shared_result_list
    global process_id
    lock = lock_instance
    logger = logger_instance
    shared_result_list = shared_result_list_instance
    process_id = process_id_instance


def generate_cpu_load(arguments):
    "Generate a utilization % for a duration of interval seconds"
    global lock
    global logger
    global shared_result_list
    global process_id
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        logger.info(f"Start process {my_id}")
    interval: int = arguments[0]
    utilization: int = arguments[1]
    start_time = time.time()
    for i in range(0,int(interval)):
        logger.info(f"Process {my_id}: About to do some arithmetic")
        while time.time()-start_time < utilization/100.0:
            a = math.sqrt(64*64*64*64*64)
        logger.info(f"Process {my_id}: Iteration" + str(i) + ". About to sleep")
        time.sleep(1-utilization/100.0)
        start_time += 1


if __name__ == "__main__":  # pragma: no cover
    # Setup a logger to stdout
    logger = logging.getLogger(__name__)
    handler = ch = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Create the chunks (simulated) to process in parallel
    logger.info("Setup process pool")
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    process_id = mg.list()
    process_id.append(0)
    chunks = [[100, 90] for i in range(100)]
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, logger, shared_result_list, process_id))
    pool.map(func=generate_cpu_load, iterable=chunks)
    pool.close()
    pool.join()
    logger.info("Finished processing all lightnings in parallel")



