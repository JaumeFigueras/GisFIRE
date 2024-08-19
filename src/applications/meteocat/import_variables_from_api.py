#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import logging

from logging.handlers import RotatingFileHandler
from logging import Logger
from sqlalchemy import URL
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.remote_api.meteocat_api import get_variables_list

from typing import List


def main(db_session: Session, api_key: str, logger: Logger) -> None:
    """
    Gets from the Meteo.cat API and stores in a database the Meteo.cat variables that are used in the weather stations

    :param db_session: SQLAlchemy database session
    :type db_session: Session
    :param api_key: Meteo.cat API key
    :type api_key: str
    :param logger: Logger instance to record process and errors
    :type logger: Logger
    :return: None
    """
    logger.info("Getting variables from API.")
    variables: List[MeteocatVariable] = get_variables_list(api_key=api_key)
    for variable in variables:
        variable.data_provider_name = 'Meteo.cat'
    logger.info("Storing variables to Database.")
    db_session.add_all(variables)
    db_session.commit()


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located')
    parser.add_argument('-p', '--port', type=int, help='Database cluster port')
    parser.add_argument('-d', '--database', help='Database name')
    parser.add_argument('-u', '--username', help='Database username')
    parser.add_argument('-w', '--password', help='Database password')
    parser.add_argument('-a', '--api-key', help='API key to access meteocat', required=True)
    parser.add_argument('-l', '--log-file', help='File to log progress or errors', required=False)
    # noinspection DuplicatedCode
    args = parser.parse_args()

    # Create the database session with SQL Alchemy
    database_url = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                              port=args.port, database=args.database)
    # Connect to the database
    try:
        engine = create_engine(database_url)
        session = Session(engine)
    except SQLAlchemyError as ex:
        print(ex)
        sys.exit(-1)
    # Set up the logging engine
    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Starting variables import from meteocat")
    main(session, args.api_key, logger)
    logger.info("Finished variables import from meteocat")
