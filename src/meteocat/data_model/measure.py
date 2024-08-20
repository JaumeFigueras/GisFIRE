#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime
import enum

from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model.measure import Measure
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory

from typing import Optional


class MeteocatMeasureValidityCategory(str, enum.Enum):
    """
    Defines the three types of measure validity
    """
    NO_DATA = ''
    PENDING = ' '
    VALID = 'V'
    VALIDATING = 'T'


class MeteocatMeasure(Measure):
    # Metaclass date_time attributes
    __date__ = [
        {'name': 'extreme_date_time', 'nullable': True},
    ]
    # Type hint for generated attributes by the metaclass
    extreme_date_time: datetime.datetime
    tzinfo_extreme_date_time: str
    # SQLAlchemy columns
    __tablename__ = "meteocat_measure"
    id: Mapped[str] = mapped_column(ForeignKey("measure.id"), primary_key=True)
    meteocat_id = mapped_column('meteocat_id', String, nullable=False)
    validity_state = mapped_column('validity_state', Enum(MeteocatMeasureValidityCategory, name='meteocat_measure_validity_category'), nullable=False)
    time_base_category = mapped_column('time_base_category', Enum(MeteocatVariableTimeBaseCategory, name='meteocat_variable_time_base_category'), nullable=False)
    # SQLAlchemy relations
    meteocat_weather_station_id = mapped_column(Integer, ForeignKey('meteocat_weather_station.id'), nullable=False)
    meteocat_variable_id = mapped_column(Integer, ForeignKey('meteocat_variable.id'), nullable=False)
    # meteocat_weather_station: Mapped["MeteocatWeatherStation"] = relationship(back_populates='meteocat_measures')
    # meteocat_variable: Mapped["MeteocatVariable"] = relationship(back_populates='meteocat_measures')
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_measure",
    }

    def __init__(self, meteocat_id: Optional[str, None] = None, measure_date_time: Optional[datetime.datetime, None] = None,
                 extreme_date_time: Optional[datetime.datetime, None] = None, value: Optional[float, None] = None,
                 validity_state: Optional[MeteocatMeasureValidityCategory, None] = None,
                 time_base: Optional[MeteocatVariableTimeBaseCategory, None] = None) -> None:
        super().__init__(measure_date_time=measure_date_time)
        self.meteocat_id = meteocat_id
        self.extreme_date_time = extreme_date_time
        self.value = value
        self.validity_state = validity_state
        self.time_base = time_base

    def __iter__(self):
        yield from super().__iter__()
        yield 'meteocat_id', self.meteocat_id
        yield 'value', self.value
        yield 'validity_state', self.validity_state.name
        yield 'time_base', self.time_base.name
