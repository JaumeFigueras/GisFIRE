#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime
import json

from src.data_model import Base
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
from sqlalchemy import DateTime
from sqlalchemy import func

from typing import Dict
from typing import Any
from typing import Union


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

    def __iter__(self):
        yield from TimeStampMixIn.__iter__(self)
        yield 'weather_station_id', self.weather_station_id
        yield 'variable_id', self.variable_id
        yield 'variable_state_id', self.variable_state_id

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatAssociationStationVariableState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('weather_station_id', 'variable_id', 'variable_state_id')):
            assoc = MeteocatAssociationStationVariableState()
            assoc.weather_station_id = dct['weather_station_id']
            assoc.variable_id = dct['variable_id']
            assoc.variable_state_id = dct['variable_state_id']
            return assoc
        return None  # pragma: no cover

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a database VariableTimeBase to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Variable time bas2 data

            :param obj:
            :type obj: Lightning
            :return: dict
            """
            if isinstance(obj, MeteocatAssociationStationVariableState):
                obj: MeteocatAssociationStationVariableState
                dct_variable_state = dict(obj)
                return dct_variable_state
            return json.JSONEncoder.default(self, obj)  # pragma: no cover


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

    def __iter__(self):
        yield from TimeStampMixIn.__iter__(self)
        yield 'weather_station_id', self.weather_station_id
        yield 'variable_id', self.variable_id
        yield 'variable_time_base_id', self.variable_time_base_id

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatAssociationStationVariableTimeBase, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('weather_station_id', 'variable_id', 'variable_time_base_id')):
            assoc = MeteocatAssociationStationVariableTimeBase()
            assoc.weather_station_id = dct['weather_station_id']
            assoc.variable_id = dct['variable_id']
            assoc.variable_time_base_id = dct['variable_time_base_id']
            return assoc
        return None  # pragma: no cover

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a database VariableTimeBase to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Variable time bas2 data

            :param obj:
            :type obj: Lightning
            :return: dict
            """
            if isinstance(obj, MeteocatAssociationStationVariableTimeBase):
                obj: MeteocatAssociationStationVariableTimeBase
                dct_variable_time_base = dict(obj)
                return dct_variable_time_base
            return json.JSONEncoder.default(self, obj)  # pragma: no cover

