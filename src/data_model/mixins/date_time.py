#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytz
from dateutil.tz import tzoffset  # Do not remove, necessary for eval tzoffset in run-time

from sqlalchemy.orm import declarative_mixin

from typing import List
from typing import Dict
from typing import Any


@declarative_mixin
class DateTimeMixIn(object):

    __date__: List[Dict[str, Any]]

    def __iter__(self):
        for cls in self.__class__.mro():
            if hasattr(cls, '__date__'):
                dates = cls.__date__
                for attribute in dates:
                    attribute_name = attribute['name']
                    tzinfo_attribute_name = 'tzinfo_' + attribute_name
                    date_time = getattr(self, attribute_name)
                    tzinfo = getattr(self, tzinfo_attribute_name)
                    if tzinfo.startswith('tzoffset'):
                        tmp = date_time.astimezone(pytz.UTC)
                        yield attribute_name, tmp.astimezone(eval(tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
                    else:
                        yield attribute_name, date_time.astimezone(pytz.timezone(tzinfo)).strftime("%Y-%m-%dT%H:%M:%S%z")
