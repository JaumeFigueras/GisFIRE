#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import json

from sqlalchemy import create_engine
from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import select
from sqlalchemy.orm import Session
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
from src.data_model.measure import Measure
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableState
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableTimeBase
from src.meteocat.data_model.measure import MeteocatMeasure


def main(db_session: Session):
    states_assoc = list(db_session.execute(select(MeteocatAssociationStationVariableState)).scalars().all())
    states = list(db_session.execute(select(MeteocatVariableState)).scalars().all())
    time_bases_assoc = list(db_session.execute(select(MeteocatAssociationStationVariableTimeBase)).scalars().all())
    time_bases = list(db_session.execute(select(MeteocatVariableTimeBase)).scalars().all())
    with open('meteocat_assoc_states.json', 'w', encoding='utf-8') as f:
        json.dump(states_assoc, f, cls=MeteocatAssociationStationVariableState.JSONEncoder, ensure_ascii=False, indent=4)
    with open('meteocat_states.json', 'w', encoding='utf-8') as f:
        json.dump(states, f, cls=MeteocatVariableState.JSONEncoder, ensure_ascii=False, indent=4)
    with open('meteocat_assoc_time_bases.json', 'w', encoding='utf-8') as f:
        json.dump(time_bases_assoc, f, cls=MeteocatAssociationStationVariableTimeBase.JSONEncoder, ensure_ascii=False, indent=4)
    with open('meteocat_time_bases.json', 'w', encoding='utf-8') as f:
        json.dump(time_bases, f, cls=MeteocatVariableTimeBase.JSONEncoder, ensure_ascii=False, indent=4)


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
        engine: Engine = create_engine(database_url)
        session: Session = Session(engine)
    except SQLAlchemyError as ex:
        print(ex)
        sys.exit(-1)

    main(session)
