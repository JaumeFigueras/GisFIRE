#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse  # pragma: no cover
import sys  # pragma: no cover

from sqlalchemy import create_engine  # pragma: no cover
from sqlalchemy import URL  # pragma: no cover
from sqlalchemy import Engine  # pragma: no cover
from sqlalchemy.exc import SQLAlchemyError  # pragma: no cover
from sqlalchemy.schema import CreateTable  # pragma: no cover

from src.data_model import Base  # pragma: no cover
from src.data_model.data_provider import DataProvider  # pragma: no cover
from src.data_model.lightning import Lightning  # pragma: no cover
from src.data_model.request import Request  # pragma: no cover
from src.meteocat.data_model.lightning import MeteocatLightning  # pragma: no cover
from src.data_model.user import User  # pragma: no cover
from src.data_model.user_access import UserAccess  # pragma: no cover
from src.data_model.weather_station import WeatherStation  # pragma: no cover
from src.data_model.variable import Variable  # pragma: no cover
from src.data_model.measure import Measure  # pragma: no cover
from src.data_model.wildfire_ignition import WildfireIgnition  # pragma: no cover
from src.meteocat.data_model.weather_station import MeteocatWeatherStation  # pragma: no cover
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariable  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariableState  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariableTimeBase  # pragma: no cover
from src.meteocat.data_model.measure import MeteocatMeasure  # pragma: no cover
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition  # pragma: no cover


def main(e: Engine):  # pragma: no cover
    print(Base.metadata.tables.keys())
    # Base.metadata.create_all(e)
    print(CreateTable(DataProvider.__table__).compile(e))
    print(CreateTable(Lightning.__table__).compile(e))
    print(CreateTable(MeteocatLightning.__table__).compile(e))
    print(CreateTable(Request.__table__).compile(e))
    print(CreateTable(User.__table__).compile(e))
    print(CreateTable(UserAccess.__table__).compile(e))
    print(CreateTable(WeatherStation.__table__).compile(e))
    print(CreateTable(MeteocatWeatherStation.__table__).compile(e))
    print(CreateTable(MeteocatWeatherStationState.__table__).compile(e))
    print(CreateTable(Variable.__table__).compile(e))
    print(CreateTable(MeteocatVariable.__table__).compile(e))
    print(CreateTable(MeteocatVariableState.__table__).compile(e))
    print(CreateTable(MeteocatVariableTimeBase.__table__).compile(e))
    print(CreateTable(Measure.__table__).compile(e))
    print(CreateTable(MeteocatMeasure.__table__).compile(e))
    print(CreateTable(WildfireIgnition.__table__).compile(e))
    print(CreateTable(BomberscatWildfireIgnition.__table__).compile(e))


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located', required=True)
    parser.add_argument('-p', '--port', type=int, help='Database cluster port', required=True)
    parser.add_argument('-d', '--database', help='Database name', required=True)
    parser.add_argument('-u', '--username', help='Database username', required=True)
    parser.add_argument('-w', '--password', help='Database password', required=True)
    args = parser.parse_args()

    database_url = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                              port=args.port, database=args.database)

    try:
        engine = create_engine(database_url)
    except SQLAlchemyError as ex:
        print(ex)
        sys.exit(-1)

    main(engine)
