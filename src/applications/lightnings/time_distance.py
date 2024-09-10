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
    parser.add_argument('-f', '--csv-file', help='CSV file to store the data', required=True)
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

    date = datetime.datetime(year=2006, month=1, day=1, hour=0, minute=0, second=0, tzinfo=pytz.UTC)
    max_date = datetime.datetime(year=2021, month=1, day=1, hour=0, minute=0, second=1, tzinfo=pytz.UTC)
    storm_start_time = datetime.datetime(year=1974, month=1, day=1, hour=0, minute=0, second=0, tzinfo=pytz.UTC)
    storm_end_time = storm_start_time
    storms = list()
    number_of_lightnings = 0
    total_lightnings = 0
    while date < max_date:
        lightnings = (session.execute(select(MeteocatLightning).join(Catalunya, Catalunya.id == 1).
                                     where(MeteocatLightning._date_time >= date).
                                     where(MeteocatLightning._date_time < date + datetime.timedelta(days=1)).
                                     where(func.ST_Contains(Catalunya.geometry_25831, MeteocatLightning._geometry_25831)).
                                     where(Catalunya.id == 1).
                                     order_by(MeteocatLightning._date_time)).
                      scalars().all())
        for lightning in lightnings:
            total_lightnings += 1
            if lightning.date_time > (storm_end_time + datetime.timedelta(minutes=120)):
                storms.append([storm_start_time.strftime("%Y-%m-%d %H:%M:%S"), storm_end_time.strftime("%Y-%m-%d %H:%M:%S"), number_of_lightnings])
                logger.info("New storm assigned from {} to {} with {} lightnings".format(storm_start_time.strftime("%Y-%m-%d %H:%M:%S"), storm_end_time.strftime("%Y-%m-%d %H:%M:%S"), number_of_lightnings))
                storm_start_time = lightning.date_time
                storm_end_time = lightning.date_time
                number_of_lightnings = 1
            else:
                storm_end_time = lightning.date_time
                number_of_lightnings += 1
        date = date + datetime.timedelta(days=1)
    session.close()
    with open(args.csv_file, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(storms[1:])





