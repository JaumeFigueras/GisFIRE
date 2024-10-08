#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import sys
import csv
import pytz

from logging.handlers import RotatingFileHandler
from logging import Logger

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.gisfire_api.remote_api import get_bomberscat_ignition_list
from src.gisfire_api.remote_api import get_meteocat_lightnings_list

from typing import TextIO


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--username', type=str, help='Username to access the GisFIRE API', required=True)
    parser.add_argument('-t', '--token', type=str, help='Token to access the GisFIRE API', required=True)
    parser.add_argument('-f', '--file', type=str, help='CSV file to save the assignments', required=True)
    parser.add_argument('-l', '--log-file', type=str,  help='File to log progress or errors', required=False)
    args = parser.parse_args()

    # Create the CSV file writer
    try:
        csv_file: TextIO = open(args.file, 'w')
        writer: csv.writer = csv.writer(csv_file)
    except Exception as ex:
        print(ex)
        sys.exit(-1)

    logger = logging.getLogger(__name__)
    if args.log_file is not None:
        handler = RotatingFileHandler(args.log_file, mode='a', maxBytes=5*1024*1024, backupCount=15, encoding='utf-8', delay=False)
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        handler = ch = logging.StreamHandler()
        logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")

    # Process the CSV file and store it into the database
    logger.info("Processing ignitions and saving to file: {0:}".format(args.file))
    years = list(range(2009, 2021))
    for year in years:
        ignitions = get_bomberscat_ignition_list(args.username, args.token,
                                                 from_date=datetime.datetime(year, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                                 to_date=datetime.datetime(year+1, 1, 1, 0, 0, 0, tzinfo=pytz.UTC),
                                                 order='date:asc')
        for ignition in ignitions:
            data = get_meteocat_lightnings_list(args.username, args.token,
                                                from_date=ignition.start_date_time-datetime.timedelta(days=7),
                                                to_date=ignition.start_date_time,
                                                order='date:asc', x=ignition.x_25831, y=ignition.y_25831,
                                                epsg=25831, radius=5000)
            for elem in data:
                lightning: MeteocatLightning = elem['lightning']
                distance: float = elem['distance'] / 1000
                T = (ignition.start_date_time - lightning.date_time).total_seconds() / 3600
                a = (1 - (T / (24 * 7))) * (1 - (distance / 5))
                elem['a'] = a
            mult = 1
            suma = 0
            for elem in data:
                mult = mult * (1 - elem['a']) if elem['a'] > 0 else mult
                suma = suma + elem['a']
            for elem in data:
                elem['B'] = 1 - mult
                elem['P'] = elem['B'] * (elem['a'] / suma)
                print(elem['lightning'].meteocat_id, elem['a'], elem['B'], elem['P'])





    csv_file.close()


