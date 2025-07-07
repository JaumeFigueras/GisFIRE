#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import dateutil.parser
import logging
import sys
import pytz
import math

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
from src.algorithms.set_cover import ip_complete_cliques
from src.algorithms.set_cover import aprox_hochbaum_mass
from src.algorithms.set_cover import aprox_biniaz_et_al
from src.algorithms.set_cover import max_cliques_ampl
from src.algorithms.helpers import remove_duplicates
from src.algorithms.helpers import order_x
from src.geo.data_model.catalunya import Catalunya

from sklearn.cluster import DBSCAN

from logging import Logger




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

    storms = session.query(StormCell).filter(
        and_(
            StormCell.number_of_lightnings >= 5000,
            StormCell.number_of_lightnings < 5200
        )
    ).first()
    lightnings = storms.lightnings
    meteocat_lightnings = [session.query(MeteocatLightning).where(MeteocatLightning.id == lightning.id).scalar() for lightning in lightnings]
    points = [{'id': l.id, 'x': l.x_25831, 'y': l.y_25831} for l in meteocat_lightnings]
    points, _ = order_x(points)
    points, _, _ = remove_duplicates(points)
    print(len(points))
    disks, _, execution_time = naive(points, 1000)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    disks, _, execution_time = greedy_naive(points, 1000)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    disks, _, execution_time = max_cliques_ortools_scip(points, 1000)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    disks, _, execution_time = ip_complete_cliques(points, 1000)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    _, disks, covered_points, execution_time = aprox_hochbaum_mass(points, 2000, 1)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    _, disks, covered_points, execution_time = aprox_hochbaum_mass(points, 2000, 2)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    _, disks, covered_points, execution_time = aprox_hochbaum_mass(points, 2000, 3)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    disks, _, execution_time = aprox_biniaz_et_al(points, 1000)
    print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    # disks, _, execution_time = max_cliques_ampl(points, 1000)
    # print(f"Disks: {len(disks)}, Execution time: {execution_time}")
    session.close()






