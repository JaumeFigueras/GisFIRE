#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytz
import datetime

from sqlalchemy import select

from src.api import db
from src.meteocat.data_model.lightning import MeteocatLightning

from typing import Union
from typing import Tuple
from typing import List
from typing import Optional


def get_meteocat_lightning(from_date: Optional[datetime.datetime] = None, to_date: Optional[datetime.datetime] = None,
                           x: Optional[float] = None, y: Optional[float] = None, epsg: Optional[int] = None,
                           radius: Optional[float] = None, order: Optional[List[Tuple[str, str]]] = None,
                           limit: Optional[int] = 1000, offset: Optional[int] = 0) -> List[MeteocatLightning]:
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
    stmt = select(MeteocatLightning)
    if from_date is not None:
        stmt = stmt.where(MeteocatLightning.date_time >= from_date)
    if to_date is not None:
        stmt = stmt.where(MeteocatLightning.date_time < to_date)
    stmt.offset(offset).limit(limit)
    lightnings: List[MeteocatLightning] = list(db.session.execute(stmt).unique().scalars().all())
    return lightnings
