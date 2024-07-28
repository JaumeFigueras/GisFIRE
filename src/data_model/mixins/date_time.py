#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from sqlalchemy import DateTime
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from typing import Optional
from typing import Union


class DateTimeMixIn(object):

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    _date_time: Mapped[datetime.datetime] = mapped_column('date_time', DateTime(timezone=True), nullable=False)
    _tzinfo: Mapped[str] = mapped_column('tzinfo', nullable=False)

    def __init__(self, date_time: Optional[datetime.datetime] = None):
        super().__init__()
        if date_time is not None:
            if date_time.tzinfo is None:
                raise ValueError('Date must contain timezone information')
            self._tzinfo = str(date_time.tzinfo)
        self._date_time = date_time

    def __iter__(self):
        if self._tzinfo.startswith('tzoffset'):
            tmp = self._date_time.astimezone(pytz.UTC)
            yield "date_time", tmp.astimezone(eval(self._tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            yield "date", self._date_time.astimezone(pytz.timezone(self._tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")

    @property
    def date(self) -> Optional[datetime.datetime]:
        return self._date_time

    @date.setter
    def date(self, value: datetime.datetime) -> None:
        if value.tzinfo is None:
            raise ValueError('Date must contain timezone information')
        self._tzinfo = str(value.tzinfo)
        self._date_time = value

