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
from src.meteocat.data_model.weather_station import MeteocatWeatherStationStateCategory
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory
from src.meteocat.data_model.measure import MeteocatMeasure
from src.meteocat.data_model.measure import MeteocatMeasureValidityCategory

from src.meteocat.remote_api.meteocat_api import get_lightning_request_equivalent

from typing import TextIO
from typing import List
from typing import Dict
from typing import Union
from typing import Any


def load_stations_and_variables(db_session: Session) -> Dict[str, Dict[Any, Dict[Any, List[Union[MeteocatVariableState, MeteocatVariableTimeBase]]]]]:
    """

    :param db_session:
    :return:
    """
    memory = dict()
    stations = db_session.execute(select(MeteocatWeatherStation)).unique().scalars().all()
    stations = list(stations)
    for station in stations:
        memory[station.code] = dict()
        memory[station.code]['id'] = station.id
        variables = db_session.execute(select(MeteocatVariable).distinct(MeteocatVariable.id).join(MeteocatAssociationStationVariableState).where(MeteocatAssociationStationVariableState.weather_station_id == station.id).where(MeteocatVariable.id == MeteocatAssociationStationVariableState.variable_id)).unique().scalars().all()
        for variable in variables:
            memory[station.code][variable.code] = dict()
            memory[station.code][variable.code]['id'] = variable.id
            memory[station.code][variable.code]['states'] = list()
            memory[station.code][variable.code]['time_bases'] = list()
            states = db_session.execute(select(MeteocatVariableState).join(MeteocatAssociationStationVariableState).where(variable.id == MeteocatAssociationStationVariableState.variable_id).where(station.id == MeteocatAssociationStationVariableState.weather_station_id)).scalars().all()
            for state in states:
                if state.code == MeteocatStateCategory.ACTIVE:
                    memory[station.code][variable.code]['states'].append(state)
            time_bases = db_session.execute(select(MeteocatVariableState).join(MeteocatAssociationStationVariableTimeBase).where(
                variable.id == MeteocatAssociationStationVariableTimeBase.variable_id).where(
                station.id == MeteocatAssociationStationVariableTimeBase.weather_station_id)).scalars().all()
            for time_base in time_bases:
                memory[station.code][variable.code]['time_bases'].append(time_base)
    return memory


def process_measures(db_session: Session, csv_reader: csv.reader,
                     elements: Dict[str, Dict[Any, Dict[Any, List[Union[MeteocatVariableState, MeteocatVariableTimeBase]]]]],
                     logger: Logger):
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
    for row in csv_reader:
        measure: MeteocatMeasure = MeteocatMeasure()
        try:
            measure.meteocat_id = row[0]
            station_code = str(row[1])
            if station_code not in elements:
                raise ValueError("Station {0:} in CSV not found in elements".format(station_code))
            measure.weather_station_id = elements[station_code]['id']
            variable_code: int = int(row[2])
            if variable_code not in elements[station_code]:
                raise ValueError("Variable {0:} in CSV not found in elements".format(variable_code))
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
            measure_status: MeteocatMeasureValidityCategory = MeteocatMeasureValidityCategory(row[6])
            measure.validity_state = measure_status
            time_base_category: MeteocatVariableTimeBaseCategory = MeteocatVariableTimeBaseCategory(row[7])
            measure.time_base_category = time_base_category
            states = elements[station_code][variable_code]['states']
            valid = False
            for state in states:
                if (state.valid_from <= measure_date and state.valid_until is None) or (state.valid_from <= measure_date <= state.valid_until):
                    valid = True
            if not valid:
                raise ValueError("Measure {0:} in CSV out of validity range for station {1:} and variable {2:}".format(measure.meteocat_id, station_code, variable_code))
            time_bases = elements[station_code][variable_code]['time_bases']
            valid = False
            for time_base in time_bases:
                if (time_base.valid_from <= measure_date and time_base.valid_until is None) or (time_base.valid_from <= measure_date <= time_base.valid_until):
                    if time_base.code == time_base_category:
                        valid = True
            if not valid:
                raise ValueError("Measure {0:} in CSV out of time base for station {1:} and variable {2:}".format(measure.meteocat_id, station_code, variable_code))
        except ValueError as e:
            logger.error("Error found in record {0:}. Rolling back all changes. Exception text: {1:}".format(i, str(e)))
            db_session.rollback()
            raise e
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
    elements = load_stations_and_variables(session)
    process_measures(session, reader, elements, logger)
    logger.info("Completed import of file: {0:}".format(args.file))
