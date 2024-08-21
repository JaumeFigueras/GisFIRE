#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from sqlalchemy import select

from src.api import db
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition

from typing import Tuple
from typing import List
from typing import Optional


def get_bomberscat_ignition(from_date: Optional[datetime.datetime] = None, to_date: Optional[datetime.datetime] = None,
                            order: Optional[List[Tuple[str, str]]] = None, limit: Optional[int] = 1000,
                            offset: Optional[int] = 0) -> List[BomberscatWildfireIgnition]:
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
    stmt = select(BomberscatWildfireIgnition)
    if from_date is not None:
        stmt = stmt.where(BomberscatWildfireIgnition._start_date_time >= from_date)
    if to_date is not None:
        stmt = stmt.where(BomberscatWildfireIgnition._start_date_time < to_date)
    if order is not None:
        for key, direction in order:
            if key == 'date':
                if direction == 'asc':
                    stmt = stmt.order_by(BomberscatWildfireIgnition._start_date_time)
                else:
                    stmt = stmt.order_by(BomberscatWildfireIgnition._start_date_time.desc())
    stmt = stmt.offset(offset).limit(limit)
    ignitions = list(db.session.execute(stmt).scalars().all())
    return ignitions
