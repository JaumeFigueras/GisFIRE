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

from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition  # pragma: no cover


def main(db_session: Session):  # pragma: no cover
    ignitions = list(db_session.execute(select(BomberscatWildfireIgnition)).unique().scalars().all())
    with open('bombers_ignitions.json', 'w', encoding='utf-8') as f:
        json.dump(ignitions, f, cls=BomberscatWildfireIgnition.JSONEncoder, ensure_ascii=False, indent=4)


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
