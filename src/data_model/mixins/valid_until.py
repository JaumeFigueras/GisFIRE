#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from dateutil.tz import tzoffset  # Do not remove, necessary for eval tzoffset in run-time

from sqlalchemy import DateTime
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import synonym
from sqlalchemy.orm import declarative_mixin

from src.data_model.mixins.date_time import DateTimeMixIn

from typing import Optional
from typing import Union


@declarative_mixin
class ValidUntilMixIn(DateTimeMixIn):

    @declared_attr
    def valid_until(cls):
        return synonym('_date_time', descriptor=property(cls.get_date_time, cls.set_date_time))

    def __init__(self, valid_until: Optional[datetime.datetime] = None) -> None:
        if valid_until is None:
            valid_until = self._generate_valid_until()
        super().__init__(valid_until)

    @staticmethod
    def _generate_valid_until() -> datetime.datetime:
        """
        Calculates a valid until date one year

        :return: Actual date plus one year
        :rtype: datetime.datetime
        """
        return datetime.datetime.now(pytz.utc) + datetime.timedelta(days=365)

    def __iter__(self):
        dct = dict()
        for key, item in super().__iter__():
            dct[key] = item
        yield 'valid_until', dct['date_time']
