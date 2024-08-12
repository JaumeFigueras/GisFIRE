#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse  # pragma: no cover
import datetime  # pragma: no cover
import logging  # pragma: no cover
import sys  # pragma: no cover
import pytz  # pragma: no cover

from logging.handlers import RotatingFileHandler  # pragma: no cover

from sqlalchemy import URL  # pragma: no cover
from sqlalchemy import Engine  # pragma: no cover
from sqlalchemy import create_engine  # pragma: no cover
from sqlalchemy.exc import SQLAlchemyError  # pragma: no cover
from sqlalchemy.orm import Session  # pragma: no cover
from sqlalchemy import select  # pragma: no cover

from src.meteocat.data_model.weather_station import MeteocatWeatherStation  # pragma: no cover
from src.meteocat.data_model.weather_station import MeteocatWeatherStationCategory  # pragma: no cover
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState  # pragma: no cover
from src.meteocat.data_model.weather_station import MeteocatWeatherStationStateCategory  # pragma: no cover


def main(db_session: Session) -> None:  # pragma: no cover
    """
    Process a CSV file with the lightning information (the CSV file is obtained from MeteoCat) and stores in a database.
    In case of error the data insertions are rolled back.

    :param db_session: SQLAlchemy database session
    :type db_session: sqlalchemy.orm.Session

    """
    if db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'Z8')).unique().scalar_one_or_none() is None:
        ze = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'ZE')).unique().scalar_one()
        z8 = MeteocatWeatherStation()
        z8.name = 'el Port del Comte (2.316 m)'
        z8.altitude = 2316
        z8.data_provider_name = "Meteo.cat"
        z8.code = 'Z8'
        z8.category = MeteocatWeatherStationCategory.AUTO
        z8.placement = 'Port del Comte'
        z8.municipality_code = ze.municipality_code
        z8.municipality_name = ze.municipality_name
        z8.county_code = ze.county_code
        z8.county_name = ze.county_name
        z8.province_code = ze.province_code
        z8.province_name = ze.province_name
        z8.network_code = ze.network_code
        z8.network_name = ze.network_name
        z8.x_4258 = 1.52407
        z8.y_4258 = 42.18254
        z8state = MeteocatWeatherStationState()
        z8state.code = MeteocatWeatherStationStateCategory.ACTIVE
        z8state.valid_from = datetime.datetime(2002, 10, 3, 0, 0, 0, tzinfo=pytz.UTC)
        z8state.valid_until = ze.meteocat_weather_station_states[0].valid_from
        z8state2 = MeteocatWeatherStationState()
        z8state2.code = MeteocatWeatherStationStateCategory.DISMANTLED
        z8state2.valid_from = ze.meteocat_weather_station_states[0].valid_from
        z8state2.valid_until = None
        z8.meteocat_weather_station_states.append(z8state)
        z8.meteocat_weather_station_states.append(z8state2)
        session.add(z8)
        db_session.commit()
    if db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'CU')).unique().scalar_one_or_none() is None:
        yn = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'YN')).unique().scalar_one()
        cu = MeteocatWeatherStation()
        cu.name = 'Vielha'
        cu.altitude = 1002
        cu.data_provider_name = "Meteo.cat"
        cu.code = 'CU'
        cu.category = MeteocatWeatherStationCategory.AUTO
        cu.placement = 'Prat de Tixineret'
        cu.municipality_code = yn.municipality_code
        cu.municipality_name = yn.municipality_name
        cu.county_code = yn.county_code
        cu.county_name = yn.county_name
        cu.province_code = yn.province_code
        cu.province_name = yn.province_name
        cu.network_code = yn.network_code
        cu.network_name = yn.network_name
        cu.x_4258 = 0.79397
        cu.y_4258 = 42.69856
        custate = MeteocatWeatherStationState()
        custate.code = MeteocatWeatherStationStateCategory.ACTIVE
        custate.valid_from = datetime.datetime(1996, 2, 15, 0, 0, 0, tzinfo=pytz.UTC)
        custate.valid_until = yn.meteocat_weather_station_states[0].valid_from
        custate2 = MeteocatWeatherStationState()
        custate2.code = MeteocatWeatherStationStateCategory.DISMANTLED
        custate2.valid_from = yn.meteocat_weather_station_states[0].valid_from
        custate2.valid_until = None
        cu.meteocat_weather_station_states.append(custate)
        cu.meteocat_weather_station_states.append(custate2)
        session.add(cu)
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
    main(session)
    logger.info("Finished weather stations import from meteocat")
