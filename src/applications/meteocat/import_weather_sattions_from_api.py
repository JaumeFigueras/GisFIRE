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
from sqlalchemy import select
from sqlalchemy import func


from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.remote_api.meteocat_api import get_weather_stations_list

from typing import List


def main(db_session: Session, api_key: str, logger: Logger):
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
    logger.info("Getting stations from API.")
    stations = get_weather_stations_list(api_key)
    for station in stations:
        station.data_provider_name = "Meteo.cat"
    db_session.add_all(stations)
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
    parser.add_argument('-a', '--api-key', help='API key to access meteocat', required=True)
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

    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Starting weather stations import from meteocat")
    main(session, args.api_key, logger)
    logger.info("Finished weather stations import from meteocat")
