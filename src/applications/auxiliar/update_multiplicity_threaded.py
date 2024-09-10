#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import time
import pytz
import json
import multiprocessing as mp

from logging.handlers import RotatingFileHandler
from logging import Logger

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.bomberscat.data_model.wildfire_ignition import BomberscatValidationLevelCategory
from src.data_model.experiment import Experiment
from src.gisfire_api.remote_api import get_meteocat_lightnings_list

from typing import TextIO




def init_pool(lock_instance, logger_instance, shared_result_list_instance, process_id_instance, engine_instance):
    global lock
    global logger
    global process_id
    global engine
    lock = lock_instance
    logger = logger_instance
    process_id = process_id_instance
    engine = engine_instance


def process_month(params):
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        logger.info("Process: {} - Experiment for year {} and month {}".format(my_id, params[0], params[1]))
    year = params[0]
    month = params[1]
    session = None
    try:
        session = Session(bind=engine)
        next_month = month + 1
        next_year = year
        if month == 12:
            next_month = 1
            next_year = year + 1
        lightnings = (session.execute(select(MeteocatLightning).
                                      where(MeteocatLightning._date_time >= datetime.datetime(year, month, 1, 0, 0, 0, tzinfo=pytz.UTC)).
                                      where(MeteocatLightning._date_time < datetime.datetime(next_year, next_month, 1, 0, 0, 0, tzinfo=pytz.UTC))).
                      scalars())
        for lightning in lightnings:
            multiplicity = (session.execute(select(func.count(MeteocatLightning.meteocat_id)).
                                            where(MeteocatLightning.meteocat_id == lightning.meteocat_id)).
                            scalar())
            lightning.multiplicity = multiplicity
        logger.info("Process: {} - Commiting multiplicities for year {} and month {}".format(my_id, year, month))
        session.commit()
        session.close()
    except Exception as xcpt:
        logger.error("Process: {} - Exception closed experiment unexpectedly".format(my_id))
        logger.error("Process: {} - Exception text: {}".format(my_id, str(xcpt)))
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error("Process: {} - Exception info: {}".format(my_id, str(exc_type)))
        logger.error("Process: {} - Exception info: {}".format(my_id, str(exc_obj)))
        logger.error("Process: {} - Exception info: {}".format(my_id, str(exc_tb.tb_lineno)))
    finally:
        if session is not None:
            session.close()


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
    logger.info("Processing lightnings")
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
    logger.info("Generating experiments")
    # Build experiment parameters
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    experiments = list()
    for year in range(2006, 2021):
        for month in range(1, 13):
            experiments.append([year, month])
    logger.info("Generating {} processes".format(len(experiments)))
    process_id = mg.list()
    process_id.append(0)
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, logger, shared_result_list, process_id, engine))
    pool.map(func=process_month, iterable=experiments)
    pool.close()
    pool.join()
    logger.info("Finished processing all experiments in parallel")


