#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from src.data_model import Base
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
from sqlalchemy import DateTime
from sqlalchemy import func


class MeteocatAssociationStationVariableState(Base, TimeStampMixIn):
    """
    Class container for the association table between weather stations, variables and the state of the variable.
    Provides the SQL Alchemy access to the ternary relation
    """
    __tablename__ = 'meteocat_association_station_variable_state'
    weather_station_id: Mapped[int] = mapped_column("meteocat_weather_station_id", ForeignKey("meteocat_weather_station.id"), primary_key=True)
    variable_id: Mapped[int] = mapped_column("meteocat_variable_id", ForeignKey("meteocat_variable.id"), primary_key=True)
    variable_state_id: Mapped[int] = mapped_column("meteocat_variable_state_id", ForeignKey("meteocat_variable_state.id"), primary_key=True)

    weather_station: Mapped["MeteocatWeatherStation"] = relationship('MeteocatWeatherStation', back_populates='variables')
    variable: Mapped["MeteocatVariable"] = relationship('MeteocatVariable', back_populates='weather_stations')
    variable_state: Mapped["MeteocatVariableState"] = relationship('MeteocatVariableState', back_populates='variable')


class MeteocatAssociationStationVariableTimeBase(Base, TimeStampMixIn):
    """
    Class container for the association table between weather stations, variables and the time basis of the variable.
    Provides the SQL Alchemy access to the ternary relation
    """
    __tablename__ = 'meteocat_association_station_variable_time_base'
    weather_station_id: Mapped[int] = mapped_column("meteocat_weather_station_id", ForeignKey('meteocat_weather_station.id'), primary_key=True)
    variable_id: Mapped[int] = mapped_column("meteocat_variable_id", ForeignKey('meteocat_variable.id'), primary_key=True)
    variable_time_base_id: Mapped[int] = mapped_column("meteocat_variable_time_base_id", ForeignKey('meteocat_variable_time_base.id'), primary_key=True)

    weather_station: Mapped["MeteocatWeatherStation"] = relationship('MeteocatWeatherStation', back_populates='variables_time_base')
    variable: Mapped["MeteocatVariable"]= relationship('MeteocatVariable', back_populates='weather_stations_time_base')
    variable_time_base: Mapped["MeteocatVariableTimeBase"] = relationship('MeteocatVariableTimeBase', back_populates='variables_time_base')