#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data_model.data_provider import DataProvider


def main(db_session: Session) -> None:
    """
    Main function to create the GisFIRE known data providers:
      - Servei Meteorològic de Catalunya: Meteo.cat
      - Bombers de la Generalitat de Catalunya
    :param db_session: SQLAlchemy session
    :type db_session: Session
    :return:
    """
    stmt = select(func.count(DataProvider.name)).where(DataProvider.name == "Meteo.cat")
    quantity = db_session.execute(stmt).scalar()
    if quantity == 0:
        meteo_cat = DataProvider('Meteo.cat', 'Servei Meteorològic de Catalunya', 'https://www.meteo.cat/')
        db_session.add(meteo_cat)
    stmt = select(func.count(DataProvider.name)).where(DataProvider.name == "Bombers.cat")
    quantity = db_session.execute(stmt).scalar()
    if quantity == 0:
        bombers_gencat = DataProvider('Bombers.cat', 'Bombers de la Generalitat de Catalunya', 'https://interior.gencat.cat/ca/arees_dactuacio/bombers')
        db_session.add(bombers_gencat)
    db_session.commit()


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
