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

from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.bomberscat.data_model.wildfire_ignition import BomberscatValidationLevelCategory
from src.data_model.wildfire_ignition import WildfireIgnitionCategory

from typing import TextIO


def process_ignitions(db_session: Session, csv_reader: csv.reader, logger: Logger) -> None:
    """
    Process a CSV file with the ignitions information (the CSV file is provided by Bombers of Catalonia) and stores them
    a database. In case of error the data insertions are rolled back.

    :param db_session: SQLAlchemy database session
    :type db_session: sqlalchemy.orm.Session
    :param csv_reader: CSV file reader
    :type csv_reader: csvs.Reader
    :param logger: Logger to log progress or errors
    :type logger: Logger
    :return: None
    """
    logger.info("Starting ignition import to database.")
    next(csv_reader)  # Remove the header
    i: int = 0
    for row in csv_reader:
        ignition: BomberscatWildfireIgnition = BomberscatWildfireIgnition()
        try:
            ignition.service_id = str(row[0])
            if str(row[2]) == '#VALUE!':
                date_time = str(row[1]) + ' 00:00:00'
            else:
                date_time = str(row[1]) + ' ' + str(row[2])
            ignition.start_date_time = datetime.datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.timezone('Europe/Andorra')) + datetime.timedelta(days=1)
            ignition.x_25831 = float(str(row[3]).replace(',', '.'))
            ignition.y_25831 = float(str(row[4]).replace(',', '.'))
            ignition.name = str(row[5])
            ignition.region = str(row[6])
            if str(row[7]) == '#VALUE!':
                ignition.burned_surface = None
            else:
                ignition.burned_surface = float(str(row[7]).replace(',', '.'))
            ignition.comments = str(row[8])
            validity = str(row[9])
            if validity == '' or validity is None:
                ignition.validation_level = BomberscatValidationLevelCategory.NONE
            elif validity == 'C':
                ignition.validation_level = BomberscatValidationLevelCategory.CORRECTED
            elif validity == 'D':
                ignition.validation_level = BomberscatValidationLevelCategory.DISCARDED
            elif validity == 'N':
                ignition.validation_level = BomberscatValidationLevelCategory.UNUSABLE
            ignition.ignition_cause = WildfireIgnitionCategory.LIGHTNING
            ignition.data_provider_name = 'Bombers.cat'
        except ValueError as e:  # pragma: no cover
            logger.error("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(i, str(e)))
            db_session.rollback()
            raise e
        db_session.add(ignition)
        i += 1
    logger.info("Committing all {0:} records.".format(i))
    db_session.commit()


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
        reader: csv.reader = csv.reader(csv_file, delimiter=',')
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
    process_ignitions(session, reader, logger)
    logger.info("Completed import of file: {0:}".format(args.file))
