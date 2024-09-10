#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import pytz
import csv

from logging.handlers import RotatingFileHandler

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.geo.data_model.catalunya import Catalunya


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

    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Processing ignitions from 2009 to 2019")
    logger.info("Connecting to database")
    database_url: URL = URL.create('postgresql+psycopg', username=args.username, password=args.password, host=args.host,
                                   port=args.port, database=args.database)
    try:
        engine: Engine = create_engine(database_url)
        session: Session = Session(engine)
    except SQLAlchemyError as ex:
        logger.error("Can't connect to database")
        logger.error("Exception: {}".format(str(ex)))
        sys.exit(-1)

    storms = list()
    number_of_lightnings = 0
    for year in range(2006, 2021):
        print(year)
        lightnings = (session.execute(select(MeteocatLightning).join(Catalunya, Catalunya.id == 1).
                                     where(MeteocatLightning._date_time >= datetime.datetime(year=year, month=1, day=1, hour=0, minute=0, second=0, tzinfo=pytz.UTC)).
                                     where(MeteocatLightning._date_time < datetime.datetime(year=year+1, month=1, day=1, hour=0, minute=0, second=0, tzinfo=pytz.UTC)).
                                     where(func.ST_Intersects(Catalunya.geometry_25831, func.ST_Buffer(MeteocatLightning._geometry_25831, MeteocatLightning.ellipse_major_axis))).
                                     order_by(MeteocatLightning._date_time)).
                      scalars().all())
        dict_list = [dict(lightning) for lightning in lightnings]
        with open("lightnings_{}.csv".format(year), "w", newline="") as f:
            w = csv.DictWriter(f, dict_list[0].keys())
            w.writeheader()
            w.writerows(dict_list)
    session.close()




