#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from dateutil.tz import tzoffset  # Do not remove, necessary for eval tzoffset in run-time

from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import synonym
from sqlalchemy.orm import declarative_mixin
from sqlalchemy.orm import DeclarativeMeta

from src.data_model.metaclass.location_metaclass import LocationMeta
from src.data_model import Base
from typing import Optional
from typing import List


class DateTimeMixIn(Base):

    attributes = [
        {'name': 'date_time', 'nullable': False}
    ]
    date_time: datetime.datetime
    tzinfo_date_time: str

    def __init__(self, date_time: Optional[datetime.datetime] = None):
        super().__init__()
        self.date_time = date_time

    def __iter__(self):
        for attribute in self.attributes:
            attribute_name = attribute['name']
            tzinfo_attribute_name = 'tzinfo_' + attribute_name
            date_time = getattr(self, attribute_name)
            tzinfo = getattr(self, tzinfo_attribute_name)
            if tzinfo.startswith('tzoffset'):
                tmp = date_time.astimezone(pytz.UTC)
                yield attribute_name, tmp.astimezone(eval(tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
            else:
                yield attribute_name, date_time.astimezone(pytz.timezone(tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
