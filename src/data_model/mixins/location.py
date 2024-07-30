#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytz
from dateutil.tz import tzoffset  # Do not remove, necessary for eval tzoffset in run-time

from sqlalchemy.orm import declarative_mixin

from typing import List
from typing import Dict
from typing import Any


@declarative_mixin
class LocationMixIn(object):

    __date__: List[Dict[str, Any]]

    def __iter__(self):
        for cls in self.__class__.mro():
            if hasattr(cls, '__location__'):
                locations = cls.__location__
                for location in locations:
                    epsg = str(location['epsg'])
                    yield 'x_' + epsg, getattr(self, 'x_' + epsg)
                    yield 'y_' + epsg, getattr(self, 'y_' + epsg)
