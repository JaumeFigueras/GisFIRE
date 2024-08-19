#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import csv
import pytz

from logging.handlers import RotatingFileHandler
from logging import Logger

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.meteocat.remote_api.meteocat_api import get_lightning_request_equivalent

from typing import TextIO


def process_lightnings(db_session: Session, csv_reader: csv.reader, logger: Logger):
    """
    Process a CSV file with the lightning information (the CSV file is obtained from MeteoCat) and stores in a database.
    In case of error the data insertions are rolled back.

    :param db_session: SQLAlchemy database session
    :type db_session: sqlalchemy.orm.Session
    :param csv_reader: CSV file reader
    :type csv_reader: csvs.Reader
    :param logger: Logger to log progress or errors
    :type logger: Logger
    :return: The processed year
    :rtype: int
    """
    logger.info("Starting lightning import to database.")
    next(csv_reader)  # Remove the header
    i: int = 0  # Counter for information purposes
    year: int = 0
    for row in csv_reader:
        lightning: MeteocatLightning = MeteocatLightning()
        try:
            lightning.meteocat_id = int(row[0])
            lightning.date_time = datetime.datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=pytz.UTC)
            year = lightning.date_time.year
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
        except ValueError as e:
            logger.error("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(i, str(e)))
            db_session.rollback()
            raise e
        db_session.add(lightning)
        if i % 10000 == 0:
            logger.info("Processed {0:} records.".format(i))
        i += 1
    logger.info("Committing all {0:} records.".format(i))
    db_session.commit()
    return year


def process_requests(db_session, year, logger: Logger):
    """
    Add the equivalent request responses to the database for the given year

    :param db_session: SQLAlchemy database session
    :type db_session: sqlalchemy.orm.Session
    :param year: Year to process requests into the database
    :type year: int
    :param logger: Logger to log progress or errors
    :type logger: Logger
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

    # Create the CSV file reader
    try:
        csv_file: TextIO = open(args.file)
        reader: csv.reader = csv.reader(csv_file, delimiter=';')
    except Exception as ex:
        print(ex)
        sys.exit(-1)

    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Processing file: {0:}".format(args.file))
    processed_year = process_lightnings(session, reader, logger)
    if processed_year is not None:
        # Add the requests equivalencies to the database
        process_requests(session, processed_year, logger)
    logger.info("Completed import of file: {0:}".format(args.file))
