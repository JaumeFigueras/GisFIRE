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
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.remote_api.meteocat_api import get_station_variables_list

from typing import List


def main(db_session: Session, api_key: str, logger: Logger):
    """
    Process a CSV file with the lightning information (the CSV file is obtained from MeteoCat) and stores in a database.
    In case of error the data insertions are rolled back.


    """
    logger.info("Getting stations from API.")
    stations = db_session.execute(select(MeteocatWeatherStation)).unique().scalars().all()
    for station in stations:
        logger.info("Getting variables from API for station: {0:} - {1:}".format(station.code, station.name))
        variables = get_station_variables_list(api_key, station.code)
        for variable in variables:
            print(dict(variable))
            variable_db: MeteocatVariable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == variable.code)).unique().scalar_one()
            print(dict(variable_db))
            for state in variable.meteocat_variable_states:
                new_state = MeteocatVariableState(state=state)
                new_state.meteocat_variable_id = variable_db.id
                new_state.meteocat_weather_station_id = station.id
                variable_db.meteocat_variable_states.append(new_state)
            for time_base in variable.meteocat_variable_time_bases:
                new_time_base = MeteocatVariableTimeBase(time_base=time_base, code=time_base.code)
                new_time_base.meteocat_variable_id = variable_db.id
                new_time_base.meteocat_weather_station_id = station.id
                variable_db.meteocat_variable_time_bases.append(new_time_base)
            db_session.commit()
        logger.info("Storing relations to database for station: {0:}".format(station.name))
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
    logger.info("Starting variables of weather stations import from meteocat")
    main(session, args.api_key, logger)
    logger.info("Finished variables of weather stations import from meteocat")
