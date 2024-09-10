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
    global shared_result_list
    global process_id
    global engine
    lock = lock_instance
    logger = logger_instance
    shared_result_list = shared_result_list_instance
    process_id = process_id_instance
    engine = engine_instance


def process_ignitions(params):
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        logger.info("Process: {} - Experiment for year {}, radius {}m, time back {}h".format(my_id, params[0], params[1], params[2]))
    session = None
    try:
        start_time: float = time.time()
        logger.info("Process: {} - Starting get lightnings for ignition".format(my_id))
        year = params[0]
        radius = params[1]
        time_back = params[2]
        session = Session(bind=engine)
        ignitions = (session.execute(select(BomberscatWildfireIgnition).
                                    where(BomberscatWildfireIgnition._start_date_time >= datetime.datetime(year, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)).
                                    where(BomberscatWildfireIgnition._start_date_time < datetime.datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)).
                                    where(or_(BomberscatWildfireIgnition.validation_level == BomberscatValidationLevelCategory.NONE, BomberscatWildfireIgnition.validation_level == BomberscatValidationLevelCategory.CORRECTED))).
                     scalars().all())
        ignitions = {ignition.id: {'ignition': ignition} for ignition in ignitions}
        for id, ignition_dct in ignitions.items():
            ignition = ignition_dct['ignition']
            stmt = select(MeteocatLightning, func.ST_Distance(func.ST_GeomFromEWKT('SRID=25831;POINT({0:f} {1:f})'.format(ignition.x_25831, ignition.y_25831)), MeteocatLightning._geometry_25831).label('distance'))
            stmt = stmt.where(func.ST_Contains(func.ST_Buffer(func.ST_GeomFromEWKT('SRID=25831;POINT({0:f} {1:f})'.format(ignition.x_25831, ignition.y_25831)), radius), MeteocatLightning._geometry_25831))
            stmt = stmt.where(MeteocatLightning._date_time >= (ignition.start_date_time - datetime.timedelta(hours=time_back)))
            stmt = stmt.where(MeteocatLightning._date_time <= ignition.start_date_time)
            stmt = stmt.order_by(MeteocatLightning._date_time)
            rows = session.execute(stmt).all()
            lightnings = list()
            for row in rows:
                lightnings.append({'lightning': row[0], 'distance': row[1]})
            ignition_dct['lightnings'] = lightnings
        logger.info("Process: {} - Finished get lightnings for ignition in {}".format(my_id, time.time() - start_time))
        logger.info("Process: {} - Starting experiment calculations".format(my_id))
        for id, ignition_dct in ignitions.items():
            ignition = ignition_dct['ignition']
            for lightning_dct in ignition_dct['lightnings']:
                lightning = lightning_dct['lightning']
                distance = lightning_dct['distance']
                t = (ignition.start_date_time - lightning.date_time).total_seconds() / 3600
                a = (1 - (t / time_back)) * (1 - (distance / radius))
                lightning_dct['A'] = a
            mult = 1
            suma = 0
            for lightning_dct in ignition_dct['lightnings']:
                mult = mult * (1 - lightning_dct['A']) if lightning_dct['A'] > 0 else mult
                suma = suma + lightning_dct['A'] if lightning_dct['A'] > 0 else suma
            ignition_dct['B'] = 1 - mult
            for lightning_dct in ignition_dct['lightnings']:
                lightning_dct['P'] = ignition_dct['B'] * (lightning_dct['A'] / suma)
        logger.info("Process: {} - Finished experiment calculations in {}".format(my_id, time.time() - start_time))
        logger.info("Process: {} - Starting result write".format(my_id))
        for id, ignition_dct in ignitions.items():
            ignition = ignition_dct['ignition']
            experiment = Experiment()
            experiment.name = 'assign_lightning_to_wildfire'
            experiment.params = {
                'ignition_id': str(id),
                'year': str(year),
                'radius': str(radius),
                'hours': str(time_back)
            }
            experiment.results = {
                'ignition_id': str(id),
                'B': str(ignition_dct['B']),
                'lightnings': json.dumps([{'lightning_id': lightning_dct['lightning'].id, 'P': lightning_dct['P']} for lightning_dct in ignition_dct['lightnings']])
            }
            session.add(experiment)
        session.commit()
        logger.info("Process: {} - Finished result write in {}".format(my_id, time.time() - start_time))
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
    logger.info("Generating experiments")
    # Build experiment parameters
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    experiments = list()
    for year in range(2009, 2020):
        for radius in [2000, 3000, 4000, 5000, 7500, 10000, 15000, 20000]:
            for hours in range(24, 24*11, 24):
                experiments.append([year, radius, hours])
    logger.info("Generating {} processes".format(len(experiments)))
    process_id = mg.list()
    process_id.append(0)
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, logger, shared_result_list, process_id, engine))
    pool.map(func=process_ignitions, iterable=experiments)
    pool.close()
    pool.join()
    logger.info("Finished processing all experiments in parallel")



