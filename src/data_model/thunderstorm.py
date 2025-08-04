#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from src.data_model import Base
from src.data_model.mixins.location import LocationMixIn
from src.data_model.mixins.date_time import DateTimeMixIn
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy import Integer
from sqlalchemy.orm import mapped_column, relationship

from sqlalchemy.orm import Mapped
from typing import List

class Thunderstorm(Base, DateTimeMixIn, TimeStampMixIn):
    # Metaclass date attributes
    __date__ = [
        {'name': 'date_time_start', 'nullable': False},
        {'name': 'date_time_end', 'nullable': False},
    ]
    # Type hint for generated date and tzinfo attributes by the metaclass
    date_time_start: datetime.datetime
    tzinfo_date_time_start: str
    date_time_end: datetime.datetime
    tzinfo_date_time_end: str
    # Class data
    __tablename__ = "thunderstorm"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)



