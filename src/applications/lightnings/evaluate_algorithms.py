#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import dateutil.parser
import logging
import sys
import csv
import math
import random

from logging.handlers import RotatingFileHandler

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.storm_cell import StormCell
from src.algorithms.set_cover import naive
from src.algorithms.set_cover import greedy_naive
from src.algorithms.set_cover import max_cliques_ortools_scip
from src.algorithms.set_cover import greedy_max_cliques
from src.algorithms.set_cover import dumitrescu_approximation_2018
from src.algorithms.set_cover import aprox_biniaz_et_al
from src.algorithms.set_cover import exact
from src.algorithms.set_cover import greedy_max_cliques_improved
from src.algorithms.helpers import remove_duplicates
from src.algorithms.helpers import order_x
from src.geo.data_model.catalunya import Catalunya

from sklearn.cluster import DBSCAN

from logging import Logger

from typing import List
from typing import Union
from typing import Any



if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located', required=True)
    parser.add_argument('-p', '--port', type=int, help='Database cluster port', required=True)
    parser.add_argument('-d', '--database', help='Database name', required=True)
    parser.add_argument('-u', '--username', help='Database username', required=True)
    parser.add_argument('-w', '--password', help='Database password', required=True)
    parser.add_argument('-l', '--log-file', help='File to log progress or errors', required=False)
    args = parser.parse_args()

    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Processing ignitions from 2009 to 2019")
    logger.info("Connecting to database")
    database_url: URL = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                                   port=args.port, database=args.database)
    try:
        engine: Engine = create_engine(database_url)
        session: Session = Session(engine)
    except SQLAlchemyError as ex:
        logger.error("Can't connect to database")
        logger.error("Exception: {}".format(str(ex)))
        sys.exit(-1)

    header = ['Range', 'Number of Lightnings', 'Naive', 'Naive ET', 'Greedy', 'Greedy Et', 'Greedy MAX Cliques',
              'Greedy MAX Cliques ET', 'Biniaz', 'Biniaz ET', 'Dumitrescu', 'Dumitrescu ET', 'Exact',
              'Exact ET']
    header = ['Range', 'Number of Lightnings', 'Greedy MAX Cliques IMP', 'Greedy MAX Cliques IMP ET']
    results: List[Any] = list()
    quantities = [0, 100, 200, 400, 800, 1600, 3200, 6400, 12800]
    quantities = [0, 50, 100, 150, 200, 300, 400, 600, 800, 1200]
    for i in range(len(quantities)-1):
        n_from = quantities[i]
        n_to = quantities[i+1]
        storms = session.query(StormCell).filter(
            and_(
                StormCell.number_of_lightnings >= n_from,
                StormCell.number_of_lightnings < n_to
            )
        ).order_by(StormCell._date_time_start).all()
        random.Random(2406).shuffle(storms)
        storms = storms[:min(100, len(storms))]
        result: Union[List[Union[str, int, float]], None] = None
        for j, storm in enumerate(storms):
            logger.info(f"Range {n_from}-{n_to}; Storm {j}")
            lightnings = storm.lightnings
            meteocat_lightnings = [session.query(MeteocatLightning).where(MeteocatLightning.id == lightning.id).scalar() for lightning in lightnings]
            points = [{'id': l.id, 'x': l.x_25831, 'y': l.y_25831} for l in meteocat_lightnings]
            points, _ = order_x(points)
            points, _, _ = remove_duplicates(points)
            result: List[Union[str, int, float]] = [f"{n_from}-{n_to}", len(points)]
            """
            # Naive
            disks, _, execution_time = naive(points, 1000)
            result.append(len(disks))
            result.append(execution_time)
            # Greedy
            disks, _, execution_time = greedy_naive(points, 1000)
            result.append(len(disks))
            result.append(execution_time)
            # Greedy MAX Cliques
            disks, _, execution_time = greedy_max_cliques(points, 1000)
            result.append(len(disks))
            result.append(execution_time)
            # Biniaz
            disks, _, execution_time = aprox_biniaz_et_al(points, 1000)
            result.append(len(disks))
            result.append(execution_time)
            # Dumitrescu
            # disks, _, execution_time = ip_complete_cliques(points, 1000)
            disks, _, execution_time = dumitrescu_approximation_2018(points, 1000)
            result.append(len(disks))
            result.append(execution_time)"""
            # Exact
            # disks, _, execution_time = ip_complete_cliques(points, 1000)
            #disks, _, execution_time = max_cliques_ortools_scip(points, 1000)
            disks, _, execution_time = greedy_max_cliques_improved(points, 1000)
            result.append(len(disks))
            result.append(execution_time)
            results.append(result[:])
    with open('evaluation3.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(results)
    session.close()






