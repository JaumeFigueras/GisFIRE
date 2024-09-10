#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import time
import pytz
import json
import multiprocessing as mp

from logging.handlers import RotatingFileHandler
from logging import Logger

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy import cast
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION
from sqlalchemy.dialects.postgresql import INTEGER

from src.meteocat.data_model.lightning import MeteocatLightning
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.bomberscat.data_model.wildfire_ignition import BomberscatValidationLevelCategory
from src.data_model.experiment import Experiment
from src.gisfire_api.remote_api import get_meteocat_lightnings_list

from typing import TextIO






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

    table = list()
    g = open("sensivity_table.dat", "a")
    g.write(' ')
    for val in range(24, 24 * 11, 24):
        g.write("{} ".format(val))
    g.write('\n')
    for radius in [2000, 3000, 4000, 5000, 7500, 10000, 15000, 20000]:
        values = list()
        last_hour = None
        for hour in range(24, 24 * 11, 24):
            sbqr = select(cast(Experiment.params['ignition_id'], INTEGER))
            sbqr = sbqr.where(cast(Experiment.results['B'], DOUBLE_PRECISION) > 0)
            sbqr = sbqr.where(Experiment.params['hours'] == str(hour))
            sbqr = sbqr.where(Experiment.params['radius'] == str(radius))
            sbqr = sbqr.where(Experiment.name == 'assign_lightning_to_wildfire')
            stmt = select(BomberscatWildfireIgnition)
            stmt = stmt.where(BomberscatWildfireIgnition._start_date_time >= datetime.datetime(2009, 1, 1))
            stmt = stmt.where(BomberscatWildfireIgnition._start_date_time < datetime.datetime(2020, 1, 1))
            stmt = stmt.where(or_(BomberscatWildfireIgnition.validation_level == BomberscatValidationLevelCategory.NONE,
                                  BomberscatWildfireIgnition.validation_level == BomberscatValidationLevelCategory.CORRECTED))
            stmt = stmt.where(BomberscatWildfireIgnition.id.in_(sbqr))
            results = session.execute(stmt).scalars().all()
            values.append([hour, len(results)])
            last_hour = hour
        f = open("sensivity_{}.dat".format(radius), "a")
        for value in values:
            f.write("{} {}\n".format(value[0], value[1]))
        f.close()
        g.write(str(radius) + ' ')
        for value in values:
            g.write("{} ".format(value[1]))
        g.write("\n")
    g.close()


