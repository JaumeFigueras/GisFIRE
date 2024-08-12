#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse  # pragma: no cover
import sys  # pragma: no cover
import json  # pragma: no cover

from sqlalchemy import create_engine  # pragma: no cover
from sqlalchemy import URL  # pragma: no cover
from sqlalchemy import Engine  # pragma: no cover
from sqlalchemy import select  # pragma: no cover
from sqlalchemy.orm import Session  # pragma: no cover
from sqlalchemy.exc import SQLAlchemyError  # pragma: no cover

from src.meteocat.data_model.weather_station import MeteocatWeatherStation  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariable  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariableState  # pragma: no cover
from src.meteocat.data_model.variable import MeteocatVariableTimeBase  # pragma: no cover


def main(db_session: Session):  # pragma: no cover
    stations = list(db_session.execute(select(MeteocatWeatherStation)).unique().scalars().all())
    with open('meteocat_weather_stations.json', 'w', encoding='utf-8') as f:
        json.dump(stations, f, cls=MeteocatWeatherStation.JSONEncoder, ensure_ascii=False, indent=4)
    variables = list(db_session.execute(select(MeteocatVariable)).unique().scalars().all())
    with open('meteocat_variables.json', 'w', encoding='utf-8') as f:
        json.dump(variables, f, cls=MeteocatVariable.JSONEncoder, ensure_ascii=False, indent=4)
    states = list(db_session.execute(select(MeteocatVariableState)).scalars().all())
    with open('meteocat_variable_states.json', 'w', encoding='utf-8') as f:
        json.dump(states, f, cls=MeteocatVariableState.JSONEncoder, ensure_ascii=False, indent=4)
    time_bases = list(db_session.execute(select(MeteocatVariableTimeBase)).scalars().all())
    with open('meteocat_variable_time_bases.json', 'w', encoding='utf-8') as f:
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
