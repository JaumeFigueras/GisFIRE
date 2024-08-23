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

from src.meteocat.data_model.lightning import MeteocatLightning


def main(db_session: Session) -> None:
    """
    Main function to create the GisFIRE known data providers:
      - Servei Meteorològic de Catalunya: Meteo.cat
      - Bombers de la Generalitat de Catalunya
    :param db_session: SQLAlchemy session
    :type db_session: Session
    :return:
    """
    i = 0
    lightnings = db_session.execute(select(MeteocatLightning)).scalars()
    for lightning in lightnings:
        multiplicity = db_session.execute(select(func.count(MeteocatLightning.meteocat_id)).where(MeteocatLightning.meteocat_id == lightning.meteocat_id)).scalar()
        lightning.multiplicity = multiplicity
        i += 1
        if i % 10000 == 0:
            print(i)
            db_session.commit()
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
