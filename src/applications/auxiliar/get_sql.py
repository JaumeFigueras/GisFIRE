#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.lightning import Lightning
from src.data_model.request import Request
from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.user import User
from src.data_model.user_access import UserAccess
from src.data_model.weather_station import WeatherStation
from src.data_model.variable import Variable
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableState
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableTimeBase



def main(e: Engine):
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
    print(CreateTable(MeteocatAssociationStationVariableState.__table__).compile(e))
    print(CreateTable(MeteocatAssociationStationVariableTimeBase.__table__).compile(e))


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
