#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import multiprocessing as mp
import datetime
import pytz
import argparse
import csv
import sys
import logging

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from logging.handlers import RotatingFileHandler
from logging import Logger

from src.meteocat.data_model.lightning import MeteocatLightning
from src.meteocat.remote_api.meteocat_api import get_lightning_request_equivalent

from typing import TextIO
from typing import Any
from typing import List

# manager = mp.Manager()
# shared_list = manager.list()
# logger: Logger


def init_pool(lock_instance, logger_instance, shared_result_list_instance, process_id_instance):
    global lock
    global logger
    global shared_result_list
    global process_id
    lock = lock_instance
    logger = logger_instance
    shared_result_list = shared_result_list_instance
    process_id = process_id_instance


def process_lightnings(rows: List[Any]):
    with lock:
        my_id = process_id[0]
        process_id[0] += 1
        logger.info("Process: {} - Processing lightning chunk of: {} lightnings".format(my_id, len(rows)))
    start_time = time.time()
    lightnings: List[Any] = list()
    for row in rows:
        lightning: MeteocatLightning = MeteocatLightning()
        try:
            lightning.meteocat_id = int(row[0])
            lightning.date_time = datetime.datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=pytz.UTC)
            lightning.peak_current = float(row[2])
            lightning.chi_squared = float(row[3])
            lightning.ellipse_major_axis = float(row[4])
            lightning.ellipse_minor_axis = float(row[5])
            lightning.ellipse_angle = 0.0
            lightning.number_of_sensors = int(row[6])
            lightning.hit_ground = row[7] == 't'
            lightning.municipality_id = int(row[8]) if row[8] != '' else None
            lightning.x_4258 = float(row[9])
            lightning.y_4258 = float(row[10])
            lightning.data_provider_name = 'Meteo.cat'
            lightnings.append(lightning)
        except ValueError as e:
            lightnings.append("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(row[0], str(e)))
    with lock:
        shared_result_list.append(lightnings)
        logger.info("Process: {} - Finished processing in {} seconds".format(my_id, time.time() - start_time))


def process_requests(db_session, year):
    """
    Add the equivalent request responses to the database for the given year

    :param db_session: SQLAlchemy database session
    :type db_session: sqlalchemy.orm.Session
    :param year: Year to process requests into the database
    :type year: int
    :return: None
    """
    logger.info("Starting population of equivalent requests to Meteo.cat")
    date = datetime.datetime(year, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    i = 0
    try:
        while date.year == year:
            simulated_request = get_lightning_request_equivalent(date)
            date = date + datetime.timedelta(hours=1)
            db_session.add(simulated_request)
            if i % 24 == 0:
                logger.info("Processing day: {0:}".format(date.strftime("%Y-%m-%d")))
            i += 1
        db_session.commit()
    except SQLAlchemyError as e:
        logger.error("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(i, str(e)))
        db_session.rollback()
        raise e


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located', required=True)
    parser.add_argument('-p', '--port', type=int, help='Database cluster port', required=True)
    parser.add_argument('-d', '--database', help='Database name', required=True)
    parser.add_argument('-u', '--username', help='Database username', required=True)
    parser.add_argument('-w', '--password', help='Database password', required=True)
    parser.add_argument('-f', '--file', help='File to retrieve data from', required=True)
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

    # Set up the CSV file
    try:
        csv_file: TextIO = open(args.file)
        reader: csv.reader = csv.reader(csv_file, delimiter=';')
    except Exception as ex:
        logger.error("Error opening CSV file: {0:}".format(ex))
        sys.exit(-1)
    # Create the CSV rows to process
    logger.info("Starting read CSV File: {}".format(args.file))
    csv_rows = list()
    next(reader)  # Skip the header
    for row in reader:
        csv_rows.append(row)
    logger.info("Finished read CSV File with {} records".format(len(csv_rows)))
    # Create the chunks to process in parallel
    logger.info("Starting processing all lightnings in parallel")
    chunks = [csv_rows[i:i + 10000] for i in range(0, len(csv_rows), 10000)]
    mg = mp.Manager()
    lock = mg.Lock()
    shared_result_list = mg.list()
    process_id = mg.list()
    process_id.append(0)
    pool = mp.Pool(mp.cpu_count() - 1, initializer=init_pool, initargs=(lock, logger, shared_result_list, process_id))
    pool.map(func=process_lightnings, iterable=chunks)
    pool.close()
    pool.join()
    logger.info("Finished processing all lightnings in parallel")

    # Start preparing lightnings to process in database
    logger.info("Starting joining all lightnings ({0:} chunk results)".format(len(shared_result_list)))
    processed_lightnings = list()
    for item in shared_result_list:
        processed_lightnings += item
    # Check there are no errors
    for lightning in processed_lightnings:
        if not isinstance(lightning, MeteocatLightning):
            logger.info("Found error while testing all lightnings")
            logger.info("Error: {}".format(lightning))
            sys.exit(-1)
    logger.info("Finished joining all lightnings with a resulting list of: {} lightnings to store in the database".format(len(processed_lightnings)))

    # Create the database URL
    database_url: URL = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                                   port=args.port, database=args.database)
    # Connect to the database
    try:
        engine: Engine = create_engine(database_url)
        session: Session = Session(engine)
    except SQLAlchemyError as ex:
        print(ex)
        sys.exit(-1)
    logger.info("Starting insert to the database")
    session.add_all(processed_lightnings)
    session.commit()
    logger.info("Finished insert to the database")

    # Set up requests equivalents
    process_requests(session, processed_lightnings[0].date_time.year)


