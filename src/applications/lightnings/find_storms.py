#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import dateutil.parser
import logging
import sys
import pytz

from logging.handlers import RotatingFileHandler

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.storm_cell import StormCell
from src.geo.data_model.catalunya import Catalunya

from logging import Logger


def time_algorithm(session: Session, from_date: datetime.datetime, to_date: datetime.datetime, algorithm_time: float, logger: Logger) -> None:
    """
    TODO:

    Parameters
    ----------
    session :
    from_date :
    to_date :
    algorithm_time :

    Returns
    -------

    """
    date = from_date
    storm_start_time = from_date
    storm_end_time = storm_start_time
    lightnings_in_storm = list()
    number_of_lightnings = 0
    total_lightnings = 0
    while date < to_date:
        lightnings = (session.execute(select(MeteocatLightning).join(Catalunya, Catalunya.id == 1).
                                     where(MeteocatLightning._date_time >= date).
                                     where(MeteocatLightning._date_time < date + datetime.timedelta(days=1)).
                                     where(func.ST_Contains(Catalunya.geometry_25831, MeteocatLightning._geometry_25831)).
                                     order_by(MeteocatLightning._date_time)).
                      scalars().all())
        for lightning in lightnings:
            total_lightnings += 1
            if lightning.date_time > (storm_end_time + datetime.timedelta(seconds=algorithm_time)):
                storm_cell: StormCell = StormCell(date_time_start=storm_start_time, date_time_end=storm_end_time, algorithm_used='TIME', algorithm_parameter_time=algorithm_time)
                storm_cell.lightnings = lightnings_in_storm
                storm_cell.data_provider_name = args.data_provider
                if len(lightnings_in_storm) > 0:
                    session.add(storm_cell)
                    logger.info("New storm assigned from {} to {} with {} lightnings".format(storm_start_time.strftime("%Y-%m-%d %H:%M:%S"), storm_end_time.strftime("%Y-%m-%d %H:%M:%S"), number_of_lightnings))
                storm_start_time = lightning.date_time
                storm_end_time = lightning.date_time
                number_of_lightnings = 1
                lightnings_in_storm = [lightning]
            else:
                storm_end_time = lightning.date_time
                number_of_lightnings += 1
                lightnings_in_storm.append(lightning)
        date = date + datetime.timedelta(days=1)
        session.commit()

def dbscan_distance_algorithm(session: Session, from_date: datetime.datetime, to_date: datetime.datetime, algorithm_time: float, algorithm_distance: float, logger: Logger) -> None:
    """
    TODO
    Parameters
    ----------
    session :
    from_date :
    to_date :
    algorithm_time :
    algorithm_distance :
    logger :

    Returns
    -------

    """
    date = from_date
    first_lightning_date = from_date
    lightnings_to_scan = list()
    while date < to_date:
        lightnings = (session.execute(select(MeteocatLightning).join(Catalunya, Catalunya.id == 1).
                                     where(MeteocatLightning._date_time >= date).
                                     where(MeteocatLightning._date_time < date + datetime.timedelta(days=1)).
                                     where(func.ST_Contains(Catalunya.geometry_25831, MeteocatLightning._geometry_25831)).
                                     order_by(MeteocatLightning._date_time)).
                      scalars().all())
        for lightning in lightnings:
            if lightning.date_time > (first_lightning_date + datetime.timedelta(seconds=algorithm_time)):
                if len(lightnings_to_scan) == 0:
                    pass
                elif len(lightnings_to_scan) == 1:
                    storm_cell: StormCell = StormCell(date_time_start=lightnings_to_scan[0].date_time,
                                                      date_time_end=lightnings_to_scan[0].date_time,
                                                      algorithm_used='DBSCAN-T',
                                                      algorithm_parameter_time=algorithm_time,
                                                      algorithm_parameter_distance=algorithm_distance)
                    storm_cell.lightnings = lightnings_to_scan
                    storm_cell.data_provider_name = args.data_provider
                    session.add(storm_cell)
                    first_lightning_date = lightning.date_time
                    lightnings_to_scan = [lightning]
                else:
                    dbscan_list = list()
                    for lightning_to_scan in lightnings_to_scan:
                        dbscan_list.append([lightning_to_scan.x_25831, lightning_to_scan.y_25831])

                    # TODO:




            else:
                lightnings_to_scan.append(lightning)
        date = date + datetime.timedelta(days=1)
        session.commit()


if __name__ == "__main__":  # pragma: no cover
    # Config the program arguments
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', help='Host name were the database cluster is located', required=True)
    parser.add_argument('-p', '--port', type=int, help='Database cluster port', required=True)
    parser.add_argument('-d', '--database', help='Database name', required=True)
    parser.add_argument('-u', '--username', help='Database username', required=True)
    parser.add_argument('-w', '--password', help='Database password', required=True)
    parser.add_argument('-t', '--data-provider', help='Data provider name', required=True)
    parser.add_argument('-f', '--from-date', help='Initial date of storm clustering', required=False, type=dateutil.parser.isoparse, default=datetime.datetime(year=2006, month=1, day=1, hour=0, minute=0, second=0, tzinfo=pytz.UTC))
    parser.add_argument('-e', '--end-date', help='End date of storm clustering', required=False, type=dateutil.parser.isoparse, default=datetime.datetime(year=2021, month=1, day=1, hour=0, minute=0, second=1, tzinfo=pytz.UTC))
    parser.add_argument('-a', '--algorithm', help='Algorithm used for clustering (TIME, DBSCAN-D, DBSCAN-TD)', required=True, choices=['TIME', 'DBSCAN-T', 'DBSCAN-D', 'DBSCAN-TD'])
    parser.add_argument('-m', '--algorithm-time', help='Algorithm time parameter to consider a new storm', required=True, type=float)
    parser.add_argument('-c', '--algorithm-distance', help='Algorithm distance parameter to consider a new storm', required=False, type=float, default=-1)
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

    if args.algorithm == 'TIME':
        time_algorithm(session, args.from_date, args.end_date, args.algorithm_time, logger)
    elif args.algorithm == 'DBSCAN-D':
        dbscan_distance_algorithm(session, args.from_date, args.end_date, args.algorithm_time, args.algorithm_distance, logger)

    session.close()






