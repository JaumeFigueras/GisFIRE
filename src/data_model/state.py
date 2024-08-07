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

    def __eq__(self, other: State) -> bool:
        """
        Equality comparison, necessary to solve an error in the MeteoCat API

        :param other: The other State to compare
        :type other: State
        :return: Self == Other
        :rtype: bool
        """
        if isinstance(other, State):
            return DateTimeMixIn.__eq__(self, other)
        else:
            return False

    def __iter__(self):
        yield 'id', self.id
        yield from DateTimeMixIn.__iter__(self)

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a States to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj: Object to encode to JSON
            :type obj: State
            :return: dict
            """
            if isinstance(obj, State):
                obj: State
                dct = dict()
                dct['from_date'] = obj.from_date.strftime("%Y-%m-%dT%H:%MZ")
                dct['to_date'] = obj.to_date.strftime("%Y-%m-%dT%H:%MZ") if obj.to_date is not None else None
                return dct
            return json.JSONEncoder.default(self, obj)  # pragma: no cover