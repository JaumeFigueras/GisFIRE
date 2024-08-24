#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy import literal_column

from src.api import db
from src.meteocat.data_model.lightning import MeteocatLightning

from typing import Union
from typing import Tuple
from typing import List
from typing import Optional


def get_meteocat_lightning(from_date: Optional[datetime.datetime] = None, to_date: Optional[datetime.datetime] = None,
                           x: Optional[float] = None, y: Optional[float] = None, epsg: Optional[int] = None,
                           radius: Optional[float] = None, order: Optional[List[Tuple[str, str]]] = None,
                           limit: Optional[int] = 1000, offset: Optional[int] = 0) -> Union[List[MeteocatLightning], List[Tuple[MeteocatLightning, float]]]:
    """
    Retrieves all the lightnings according to the given parameters.

    TODO: Add all arguments
    :param from_date:
    :param to_date:
    :param x:
    :param y:
    :param epsg:
    :param radius:
    :param order:
    :param limit:
    :param offset:
    :return:
    """
    if x is not None:
        if epsg == 25831:
            stmt = select(MeteocatLightning, func.ST_Distance(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), MeteocatLightning._geometry_25831).label('dista'))
            stmt = stmt.where(func.ST_Contains(func.ST_Buffer(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), radius), MeteocatLightning._geometry_25831))
        elif epsg == 4258:
            stmt = select(MeteocatLightning, func.ST_Distance(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), MeteocatLightning._geometry_4258).label('dista'))
            stmt = stmt.where(func.ST_Contains(func.ST_Buffer(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), radius), MeteocatLightning._geometry_4258))
        elif epsg == 4326:
            stmt = select(MeteocatLightning, func.ST_Distance(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), MeteocatLightning._geometry_4326).label('dista'))
            stmt = stmt.where(func.ST_Contains(func.ST_Buffer(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), radius), MeteocatLightning._geometry_4326))
        else:
            stmt = select(MeteocatLightning,
                          func.ST_Distance(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), func.ST_Transform(MeteocatLightning._geometry_4258, epsg)).label('dista'),
                          func.ST_X(MeteocatLightning._geometry_4258.ST_Transform(epsg)).label('x'),
                          func.ST_Y(MeteocatLightning._geometry_4258.ST_Transform(epsg).label('y')))
            stmt = stmt.where(func.ST_Contains(func.ST_Buffer(func.ST_GeomFromEWKT('SRID={0:d};POINT({1:f} {2:f})'.format(epsg, x, y)), radius), func.ST_Transform(MeteocatLightning._geometry_4258, epsg)))
    else:
        stmt = select(MeteocatLightning)
    if from_date is not None:
        stmt = stmt.where(MeteocatLightning._date_time >= from_date)
    if to_date is not None:
        stmt = stmt.where(MeteocatLightning._date_time < to_date)
    if order is not None:
        for key, direction in order:
            if key == 'date':
                if direction == 'asc':
                    stmt = stmt.order_by(MeteocatLightning._date_time)
                else:
                    stmt = stmt.order_by(MeteocatLightning._date_time.desc())
            else:
                if direction == 'asc':
                    stmt = stmt.order_by(literal_column('dista'))
                else:
                    stmt = stmt.order_by(literal_column('dista').desc())
    stmt = stmt.offset(offset).limit(limit)
    print(stmt)
    rows = db.session.execute(stmt).all()
    lightnings = list()
    for row in rows:
        if len(row) == 1:
            lightnings.append(row[0])
        elif len(row) == 2:
            lightnings.append({'lightning': dict(row[0]), 'distance': row[1]})
        else:
            lightnings.append({'lightning': dict(row[0]), 'distance': row[1], 'x_' + str(epsg): row[2], 'y_' + str(epsg): row[3]})
    return lightnings
