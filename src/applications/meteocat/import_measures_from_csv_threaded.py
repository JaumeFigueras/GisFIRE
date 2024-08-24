#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import csv
import pytz
import time
import multiprocessing as mp

from logging.handlers import RotatingFileHandler
from logging import Logger

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableStateCategory
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory
from src.meteocat.data_model.measure import MeteocatMeasure
from src.meteocat.data_model.measure import MeteocatMeasureValidityCategory

from typing import TextIO
from typing import List
from typing import Dict
from typing import Union
from typing import Any

PROCESS_ID = 0
STATIONS = 1
VARIABLES = 2
STATES = 3
TIME_BASES = 4


def init_pool(lock_instance, logger_instance, shared_result_list_instance, shared_data_instance):
    global lock
    global logger
    global shared_result_list
    global shared_data
    lock = lock_instance
    logger = logger_instance
    shared_result_list = shared_result_list_instance
    shared_data = shared_data_instance


def populate_shared_data(db_session: Session, shared_data: List):
    stations = db_session.execute(select(MeteocatWeatherStation)).unique().scalars().all()
    shared_data[STATIONS] = {station.code: station for station in stations}
    variables = db_session.execute(select(MeteocatVariable)).unique().scalars().all()
    shared_data[VARIABLES] = {variable.code: variable for variable in variables}
    dct_states = dict()
    dct_time_bases = dict()
    for station in stations:
        for variable in variables:
            states = (db_session.execute(select(MeteocatVariableState).
                                         where(MeteocatVariableState.meteocat_weather_station_id == station.id).
                                         where(MeteocatVariableState.meteocat_variable_id == variable.id).
                                         where(MeteocatVariableState.code == MeteocatVariableStateCategory.ACTIVE)).
                      scalars().all())
            states = list(states)
            if states is not None and len(states) > 0:
                dct_states[station.code + str(variable.code)] = states
            time_bases = (db_session.
                          execute(select(MeteocatVariableTimeBase).
                                  where(MeteocatVariableTimeBase.meteocat_weather_station_id == station.id).
                                  where(MeteocatVariableTimeBase.meteocat_variable_id == variable.id)).
                          scalars().all())
            time_bases = list(time_bases)
            if time_bases is not None and len(time_bases) > 0:
                dct_time_bases[station.code + str(variable.code)] = time_bases
    shared_data[STATES] = dct_states
    shared_data[TIME_BASES] = dct_time_bases

def process_measures(rows: List[Any]) -> None:
    """
    Reads the CSV file obtained in the Gencat Dades Obertes with the records of all the measures of the weather
    stations. Then it stores in the database. The reader checks the validity os the variable and time base except
    for the Z8 station that has an error in the Meteo.cat API, we consider its data valid. The errors are detected and
    logged but except for those that are critical, the data is accepted since all detected errors are just data that
    is in the Meteo.cat database during weather stations dismantling process.

    :param db_session: SQLAlchemy database session
    :type db_session: Session
    :param csv_reader: CSV file reader
    :type csv_reader: csvs.Reader
    :param logger: Logger to log progress or errors
    :type logger: Logger
    :return: None
    """
    with lock:
        my_id = shared_data[PROCESS_ID]
        shared_data[PROCESS_ID] += 1
        logger.info("Process: {} - Processing measures chunk of: {} measures".format(my_id, len(rows)))
    start_time = time.time()
    measures: List[Any] = list()
    for row in rows:
        measure: MeteocatMeasure = MeteocatMeasure()
        try:
            measure.meteocat_id = row[0]
            station_code = str(row[1])
            if station_code not in shared_data[STATIONS]:
                with lock:
                    logger.error("Station {0:} in CSV not found in station list".format(station_code))
                    logger.error("Data that caused the error: {}".format(str(row)))
                continue
            measure.meteocat_weather_station_id = shared_data[STATIONS][station_code].id
            variable_code: int = int(row[2])
            if variable_code not in shared_data[VARIABLES]:
                with lock:
                    logger.error("Variable {0:} in CSV not found in variable list".format(variable_code))
                    logger.error("Data that caused the error: {}".format(str(row)))
                continue
            measure.meteocat_variable_id = shared_data[VARIABLES][variable_code].id
            utc_tz = pytz.timezone("UTC")
            measure_date: datetime.datetime = datetime.datetime.strptime(row[3], "%d/%m/%Y %I:%M:%S %p")
            measure_date = utc_tz.localize(measure_date)
            measure.measure_date_time = measure_date
            extreme_measure_date: Union[None, datetime.datetime] = None
            if row[4] != '':
                extreme_measure_date = datetime.datetime.strptime(row[4], "%d/%m/%Y %I:%M:%S %p")
                extreme_measure_date = utc_tz.localize(extreme_measure_date)
            measure.extreme_date_time = extreme_measure_date
            value: float = float(row[5])
            measure.value = value
            measure_status: MeteocatMeasureValidityCategory = MeteocatMeasureValidityCategory(str(row[6]))
            measure.validity_state = measure_status
            time_base_category: MeteocatVariableTimeBaseCategory = MeteocatVariableTimeBaseCategory(str(row[7]))
            measure.time_base_category = time_base_category
            valid_states = shared_data[STATES][station_code + str(variable_code)]
            valid = False
            for valid_state in valid_states:
                if (valid_state.valid_from <= measure_date and valid_state.valid_until is None) or (
                        valid_state.valid_from <= measure_date <= valid_state.valid_until):
                    valid = True
            if not valid:
                if station_code == 'Z8':
                    valid = True
            if not valid:
                with lock:
                    logger.warning("Measure {0:} in CSV out of validity range for station {1:} and variable {2:}".
                                   format(measure.meteocat_id, station_code, variable_code))
                    logger.warning("Data that caused the error: {}".format(str(row)))
            available_time_bases = shared_data[TIME_BASES][station_code + str(variable_code)]
            valid = False
            for time_base in available_time_bases:
                if (time_base.valid_from <= measure_date and time_base.valid_until is None) or (
                        time_base.valid_from <= measure_date <= time_base.valid_until):
                    if time_base.code == time_base_category:
                        valid = True
            if not valid:
                if station_code == 'Z8':
                    valid = True
            if not valid:
                with lock:
                    logger.warning("Measure {0:} in CSV out of time base for station {1:} and variable {2:}".
                                   format(measure.meteocat_id, station_code, variable_code))
                    logger.warning("Data that caused the error: {}".format(str(row)))
            measures.append(measure)
        except ValueError as e:
            with lock:
                logger.error("Error found converting row to measure. Exception text: {0:}".format(str(e)))
                logger.error("Data that caused the error: {0:}".format(str(row)))
    with lock:
        shared_result_list.append(measures)
        logger.info("Process: {} - Finished processing in {} seconds".format(my_id, time.time() - start_time))
        rows = None


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
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5 * 1024 * 1024, backupCount=15,
                                      encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler],
                            encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler],
                            encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    database_url: URL = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                                   port=args.port, database=args.database)
    # Connect to the database
    try:
        engine: Engine = create_engine(database_url)
        session: Session = Session(engine)
    except SQLAlchemyError as ex:
        logger.error("Error connecting to database: {0:}".format(str(ex)))
        sys.exit(-1)

    # Set up the CSV file
    lines = 0
    try:
        with open(args.file) as f:
            lines = sum(1 for line in f)
        csv_file: TextIO = open(args.file)
        reader: csv.reader = csv.reader(csv_file, delimiter=',')
    except Exception as ex:
        logger.error("Error opening CSV file: {0:}".format(ex))
        sys.exit(-1)
    mg = mp.Manager()
    lock = mg.Lock()
    shared_data = mg.list()
    shared_data.append(0)
    shared_data.append(None)
    shared_data.append(None)
    shared_data.append(None)
    shared_data.append(None)
    logger.info("Reading current stations and variables data")
    populate_shared_data(session, shared_data)
    print(shared_data[STATIONS])
    print(shared_data[VARIABLES])
    print(shared_data[STATES])
    session.close()
    # Create the CSV rows to process
    logger.info("Starting read CSV File: {}".format(args.file))
    next(reader)  # Skip the header
    end = False
    while not end:
        idx = 0
        shared_result_list = mg.list()
        csv_rows = list()
        while (row := next(reader, False)) and (idx < 2000000):
            csv_rows.append(row)
            idx += 1
        if not row:
            end = True
        logger.info("Finished read CSV File with {0:} records".format(len(csv_rows)))
        # Create the chunks to process in parallel
        logger.info("splitting measures in processable chunks")
        chunks = [csv_rows[i:i + 10000] for i in range(0, len(csv_rows), 10000)]
        logger.info("Starting processing all measures in parallel")
        pool = mp.Pool(mp.cpu_count() - 10, initializer=init_pool, initargs=(lock, logger, shared_result_list, shared_data))
        pool.map(func=process_measures, iterable=chunks)
        pool.close()
        pool.join()
        csv_rows = None
        chunks = None
        logger.info("Finished processing all measures in parallel")

        # Start preparing lightnings to process in database
        logger.info("Starting joining all measures ({0:} chunk results)".format(len(shared_result_list)))
        processed_measures = list()
        for item in shared_result_list:
            processed_measures += item
        # Check there are no errors
        for measure in processed_measures:
            if not isinstance(measure, MeteocatMeasure):
                logger.error("Found error while testing all measures")
                logger.error("Error: {}".format(str(measure)))
                sys.exit(-1)
        logger.info("Finished joining all measures with a resulting list of: {} measures to store in the database".format(len(processed_measures)))

        # Connect to the database
        try:
            session: Session = Session(engine)
        except SQLAlchemyError as ex:
            logger.error("Error connecting to database: {0:}".format(str(ex)))
            sys.exit(-1)
        logger.info("Starting insert to the database")
        # session.add_all(processed_measures)
        # session.commit()
        logger.info("Finished insert to the database")


