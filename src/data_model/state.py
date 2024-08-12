#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime
import dateutil.parser
import json

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import Integer
from sqlalchemy import DateTime
from sqlalchemy import func

from src.data_model import Base
from src.data_model.mixins.date_time import DateTimeMixIn
from src.data_model.mixins.time_stamp import TimeStampMixIn

from typing import Dict
from typing import Optional
from typing import Any
from typing import Union


class State(Base, DateTimeMixIn, TimeStampMixIn):
    """
    Class container for a state. Implements a base abstract class with common properties between states. Will be used in
    variables and weather stations

    :type id: int or Column
    :type from_date: datetime.datetime or Column or None
    :type to_date: datetime.datetime or Column or None
    :type ts: datetime.datetime or Column
    """
    # Metaclass date_time attributes
    __date__ = [
        {'name': 'valid_from', 'nullable': False},
        {'name': 'valid_until', 'nullable': True}
    ]
    # Type hint for generated attributes by the metaclass
    valid_from: datetime.datetime
    tzinfo_valid_from: str
    valid_until: datetime.datetime
    tzinfo_valid_until: str
    # SQLAlchemy columns
    __abstract__ = True  # SQLAlchemy directive for abstract data_model
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SQLAlchemy Inheritance options

    def __init__(self, valid_from: Optional[datetime.datetime] = None,
                 valid_until: Optional[datetime.datetime] = None) -> None:
        """
        Class constructor

        :param from_date: Date the state begins to be valid
        :type from_date: datetime
        :param to_date: Date when the state finishes its validity
        :type to_date: datetime
        """
        super().__init__()
        self.valid_from = valid_from
        self.valid_until = valid_until

    def __iter__(self):
        yield 'id', self.id
        yield from DateTimeMixIn.__iter__(self)
        yield from TimeStampMixIn.__iter__(self)
