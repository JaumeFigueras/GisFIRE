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


def process_measures(db_session: Session, csv_reader: csv.reader, logger: Logger) -> None:
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
    logger.info("Starting measures import to database.")
    next(csv_reader)  # Remove the header
    i: int = 0  # Counter for information purposes
    stations: Dict[str, MeteocatWeatherStation] = dict()
    variables: Dict[int, MeteocatVariable] = dict()
    states: Dict[str, List[MeteocatVariableState]] = dict()
    time_bases: Dict[str, List[MeteocatVariableTimeBase]] = dict()
    for row in csv_reader:
        measure: MeteocatMeasure = MeteocatMeasure()
        try:
            measure.meteocat_id = row[0]
            station_code = str(row[1])
            if station_code not in stations:
                try:
                    station = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == station_code)).unique().scalar_one()
                    stations[station_code] = station
                except SQLAlchemyError as xcpt:
                    logger.error(str(xcpt))
                    raise ValueError("Station {0:} in CSV not found in elements".format(station_code))
            else:
                station = stations[station_code]
            measure.weather_station_id = stations[station_code].id
            variable_code: int = int(row[2])
            if variable_code not in variables:
                try:
                    variable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == variable_code)).unique().scalar_one()
                    variables[variable_code] = variable
                except SQLAlchemyError as xcpt:
                    logger.error(str(xcpt))
                    raise ValueError("Variable {0:} in CSV not found in elements".format(variable_code))
            else:
                variable = variables[variable_code]
            measure.variable_id = variable_code
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
            if (station_code + str(variable_code)) not in states:
                try:
                    valid_states = list(db_session.execute(select(MeteocatVariableState).where(MeteocatVariableState.meteocat_weather_station_id == station.id).where(MeteocatVariableState.meteocat_variable_id == variable.id).where(MeteocatVariableState.code == MeteocatVariableStateCategory.ACTIVE)).scalars())
                    if len(valid_states) == 0:
                        if station_code == 'Z8':
                            valid_states.append(MeteocatVariableState(code=MeteocatVariableStateCategory.ACTIVE, valid_from=datetime.datetime(1990, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)))
                        else:
                            logger.error('Error in row: {0:}'.format(str(row)))
                            raise ValueError("No active states for station: {0:} and variable: {1:} found".format(station_code, variable_code))
                    states[station_code + str(variable_code)] = valid_states
                except SQLAlchemyError as xcpt:  # pragma: no cover
                    logger.error(str(xcpt))
                    return
            else:
                valid_states = states[station_code + str(variable_code)]
            valid = False
            for valid_state in valid_states:
                if (valid_state.valid_from <= measure_date and valid_state.valid_until is None) or (valid_state.valid_from <= measure_date <= valid_state.valid_until):
                    valid = True
            if not valid:
                logger.error("Measure {0:} in CSV out of validity range for station {1:} and variable {2:}".format(measure.meteocat_id, station_code, variable_code))
            if (station_code + str(variable_code)) not in time_bases:
                try:
                    available_time_bases = list(db_session.execute(select(MeteocatVariableTimeBase).where(MeteocatVariableTimeBase.meteocat_weather_station_id == station.id).where(MeteocatVariableTimeBase.meteocat_variable_id == variable.id)).scalars())
                    if len(available_time_bases) == 0:
                        if station_code == 'Z8':
                            available_time_bases.append(MeteocatVariableTimeBase(code=MeteocatVariableTimeBaseCategory[time_base_category], valid_from=datetime.datetime(1990, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)))
                        else:
                            logger.error('Error in row: {0:}'.format(str(row)))
                            raise ValueError("No available time_bases for station: {0:} and variable: {1:} found".format(station_code, variable_code))
                    time_bases[station_code + str(variable_code)] = available_time_bases
                except SQLAlchemyError as xcpt:  # pragma: no cover
                    logger.error(str(xcpt))
                    return
            else:
                available_time_bases = time_bases[station_code + str(variable_code)]
            valid = False
            for time_base in available_time_bases:
                if (time_base.valid_from <= measure_date and time_base.valid_until is None) or (time_base.valid_from <= measure_date <= time_base.valid_until):
                    if time_base.code == time_base_category:
                        valid = True
            if not valid:
                logger.error('Error in row: {0:}'.format(str(row)))
                logger.error("Measure {0:} in CSV out of time base for station {1:} and variable {2:}".format(measure.meteocat_id, station_code, variable_code))
            measure.meteocat_weather_station_id = station.id
            measure.meteocat_variable_id = variable.id
        except ValueError as e:
            logger.error("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(i, str(e)))
            db_session.rollback()
            raise e
        measure.data_provider_name = "Meteo.cat"
        db_session.add(measure)
        if i % 10000 == 0:
            logger.info("Processed {0:} measure records.".format(i))
            logger.info("Committing all {0:} records.".format(i))
            db_session.commit()
        i += 1
    logger.info("Committing remaining records.")
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
    try:
        process_measures(session, reader, logger)
    except Exception as xcpt:
        logger.error(str(xcpt))
        print(str(xcpt))
    logger.info("Completed import of file: {0:}".format(args.file))
