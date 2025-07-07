#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import dateutil.parser
import logging
import sys
import pytz
import math

from logging.handlers import RotatingFileHandler

from sqlalchemy import URL
from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.storm_cell import StormCell
from src.geo.data_model.catalunya import Catalunya

from sklearn.cluster import DBSCAN

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
    exists = session.query(StormCell).filter(
        and_(StormCell.algorithm_used=='TIME',
             StormCell.maximum_gap_between_lightnings==algorithm_time
             )
    ).first() is not None
    if exists:
        logger.error(f"Storms with algorithm TIME with maximum gap between lightnings {algorithm_time} already exists")
        return
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
                storm_cell: StormCell = StormCell(date_time_start=storm_start_time,
                                                  date_time_end=storm_end_time,
                                                  algorithm_used='TIME',
                                                  maximum_gap_between_lightnings=algorithm_time,
                                                  number_of_lightnings=len(lightnings_in_storm))
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
                                                      algorithm_parameter_distance=algorithm_distance,
                                                      number_of_lightnings=len(lightnings_to_scan))
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


def dbscan_time_distance_algorithm(session: Session, from_date: datetime.datetime, to_date: datetime.datetime, algorithm_time: float, algorithm_distance: float, storm_max_time: float, logger: Logger) -> None:
    """
    TODO
    Parameters
    ----------
    session :
    from_date :
    to_date :
    algorithm_time :
    algorithm_distance :
    storm_max_time :
    logger :

    Returns
    -------

    """
    exists = session.query(StormCell).filter(
        and_(StormCell.algorithm_used=='DBSCAN-TD',
             StormCell.algorithm_parameter_time==algorithm_time,
             StormCell.algorithm_parameter_distance==algorithm_distance,
             StormCell.maximum_gap_between_lightnings==storm_max_time
             )
    ).first() is not None
    if exists:
        logger.error(f"Storms with algorithm DBSCAN-TD with algorithm time {algorithm_time}, algorithm distance {algorithm_distance} and maximum gap between lightnings {storm_max_time} already exists")
        return
    date = from_date
    last_lightning_date = from_date
    lightnings_to_scan = list()
    while date < to_date:
        lightnings = (session.execute(select(MeteocatLightning).join(Catalunya, Catalunya.id == 1).
                                     where(MeteocatLightning._date_time >= date).
                                     where(MeteocatLightning._date_time < date + datetime.timedelta(days=1)).
                                     where(func.ST_Contains(Catalunya.geometry_25831, MeteocatLightning._geometry_25831)).
                                     order_by(MeteocatLightning._date_time)).
                      scalars().all())
        for lightning in lightnings:
            if lightning.date_time > (last_lightning_date + datetime.timedelta(seconds=storm_max_time)):
                if len(lightnings_to_scan) == 0:
                    last_lightning_date = lightning.date_time
                    lightnings_to_scan = [lightning]
                elif len(lightnings_to_scan) == 1:
                    storm_cell: StormCell = StormCell(date_time_start=lightnings_to_scan[0].date_time,
                                                      date_time_end=lightnings_to_scan[0].date_time,
                                                      algorithm_used='DBSCAN-T',
                                                      algorithm_parameter_time=algorithm_time,
                                                      algorithm_parameter_distance=algorithm_distance,
                                                      maximum_gap_between_lightnings=storm_max_time,
                                                      number_of_lightnings=1)
                    storm_cell.lightnings = lightnings_to_scan
                    storm_cell.data_provider_name = args.data_provider
                    session.add(storm_cell)
                    logger.info("New storm assigned from {} to {} with {} lightnings".format(
                        storm_cell.date_time_start.strftime("%Y-%m-%d %H:%M:%S"),
                        storm_cell.date_time_end.strftime("%Y-%m-%d %H:%M:%S"),
                        1))
                    last_lightning_date = lightning.date_time
                    lightnings_to_scan = [lightning]
                else:
                    print('DBSCAN')
                    dbscan_list = [[l.x_25831, l.y_25831, l.date_time.timestamp()] for l in lightnings_to_scan]
                    dbs = DBSCAN(eps=math.sqrt(algorithm_time**2 + algorithm_distance**2), min_samples=1)
                    result = dbs.fit(dbscan_list)
                    max_label = max(label for label in result.labels_ if label != -1)
                    clusters = {i: list() for i in range(max_label+1)}
                    for label, l in zip(result.labels_, lightnings_to_scan):
                        clusters[label].append(l)
                    for _, ltngs in clusters.items():
                        storm_cell: StormCell = StormCell(date_time_start=ltngs[0].date_time,
                                                          date_time_end=ltngs[-1].date_time,
                                                          algorithm_used='DBSCAN-TD',
                                                          algorithm_parameter_time=algorithm_time,
                                                          algorithm_parameter_distance=algorithm_distance,
                                                          maximum_gap_between_lightnings=storm_max_time,
                                                          number_of_lightnings=len(ltngs))
                        storm_cell.lightnings = ltngs
                        storm_cell.data_provider_name = args.data_provider
                        session.add(storm_cell)
                        logger.info("New storm assigned from {} to {} with {} lightnings".format(
                            storm_cell.date_time_start.strftime("%Y-%m-%d %H:%M:%S"),
                            storm_cell.date_time_end.strftime("%Y-%m-%d %H:%M:%S"),
                            len(ltngs)))
                    last_lightning_date = lightning.date_time
                    lightnings_to_scan = [lightning]
            else:
                last_lightning_date = lightning.date_time
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
    parser.add_argument('-m', '--algorithm-time', help='Algorithm time parameter to consider a new storm', required=False, type=float, default=-1)
    parser.add_argument('-c', '--algorithm-distance', help='Algorithm distance parameter to consider a new storm', required=False, type=float, default=-1)
    parser.add_argument('-s', '--storm_max_time', help='Maximum gap between lightnings', required=True, type=float)
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
        time_algorithm(session, args.from_date, args.end_date, args.storm_max_time, logger)
    elif args.algorithm == 'DBSCAN-D':
        dbscan_distance_algorithm(session, args.from_date, args.end_date, args.algorithm_time, args.algorithm_distance, args.storm_max_time, logger)
    elif args.algorithm == 'DBSCAN-TD':
        dbscan_time_distance_algorithm(session, args.from_date, args.end_date, args.algorithm_time, args.algorithm_distance, args.storm_max_time, logger)

    session.close()






