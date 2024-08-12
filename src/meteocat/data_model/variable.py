#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import enum
import datetime
import json

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import relationship

from src.data_model.state import State
from src.data_model.variable import Variable

from typing import Union
from typing import Dict
from typing import Optional
from typing import Any
from typing import List
from typing import Iterator


class MeteocatVariableCategory(str, enum.Enum):
    """
    Defines thr three types of variables

    DAT for real measured data
    AUX for auxiliary data
    CMV for compound multivariate data that is calculated
    """
    DAT = 'DAT'
    AUX = 'AUX'
    CMV = 'CMV'


class MeteocatVariableStateCategory(enum.Enum):
    """
    Defines the three types os statuses

    DISMANTLED for dismantled stations
    ACTIVE for active station
    REPAIR for station under some type of repair or temporal inactivity
    """
    ACTIVE = 2
    DISMANTLED = 1
    REPAIR = 3


class MeteocatVariableTimeBaseCategory(str, enum.Enum):
    """
    Defines the different types of sampling times for a variable
    """
    HO = 'HO'
    SH = 'SH'
    DM = 'DM'
    MI = 'MI'
    D5 = 'D5'


class MeteocatVariableState(State):
    # SQLAlchemy columns
    __tablename__ = 'meteocat_variable_state'
    code = mapped_column('code', Enum(MeteocatVariableStateCategory, name='meteocat_variable_state_category'), nullable=False)
    # SQLAlchemy relations
    meteocat_weather_station_id: Mapped[int] = mapped_column(Integer, ForeignKey('meteocat_weather_station.id'))
    meteocat_weather_station: Mapped["MeteocatWeatherStation"] = relationship('MeteocatWeatherStation', back_populates='meteocat_variable_states')
    meteocat_variable_id: Mapped[int] = mapped_column(Integer, ForeignKey('meteocat_variable.id'), nullable=False)
    meteocat_variable: Mapped["MeteocatVariable"] = relationship('MeteocatVariable', back_populates='meteocat_variable_states')

    def __init__(self, state: Optional[MeteocatVariableState] = None,
                 code: Optional[MeteocatVariableStateCategory] = None,
                 valid_from: Optional[datetime.datetime, None] = None,
                 valid_until: Optional[datetime.datetime, None] = None) -> None:
        if state is not None and isinstance(state, MeteocatVariableState):
            code = state.code
            valid_from = state.valid_from
            valid_until = state.valid_until
        super().__init__(valid_from=valid_from, valid_until=valid_until)
        self.code = code

    def __iter__(self):
        yield from super().__iter__()
        yield 'code', self.code.name
        yield 'variable_id', self.meteocat_variable_id
        yield 'weather_station_id', self.meteocat_weather_station_id

    @staticmethod
    def object_hook_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariableState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            state = MeteocatVariableState()
            state.code = MeteocatVariableStateCategory(dct['codi'])
            state.valid_from = datetime.datetime.strptime(dct['dataInici'], "%Y-%m-%dT%H:%M%z")
            if dct['dataFi'] is not None:
                state.valid_until = datetime.datetime.strptime(dct['dataFi'], "%Y-%m-%dT%H:%M%z")
            return state
        return None  # pragma: no cover

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatVariableState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('id', 'code', 'valid_from', 'valid_until', 'ts', 'variable_id', 'weather_station_id')):
            time_base = MeteocatVariableState()
            time_base.id = dct['id']
            time_base.code = MeteocatVariableStateCategory[dct['code']]
            time_base.valid_from = datetime.datetime.strptime(dct['valid_from'], "%Y-%m-%dT%H:%M:%S%z")
            if dct['valid_until'] is not None:
                time_base.valid_until = datetime.datetime.strptime(dct['valid_until'], "%Y-%m-%dT%H:%M:%S%z")
            time_base.meteocat_variable_id = dct['variable_id']
            time_base.meteocat_weather_station_id = dct['weather_station_id']
            return time_base
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
            if isinstance(obj, MeteocatVariableState):
                obj: MeteocatVariableState
                dct_variable_state = dict(obj)
                return dct_variable_state
            return json.JSONEncoder.default(self, obj)  # pragma: no cover


class MeteocatVariableTimeBase(State):
    """
    Class container for the variable time bases table. Provides the SQL Alchemy access to the different measurement
    intervals of a certain variable in a specific weather station. The different time intervals can be hourly,
    semi-hourly (30 min.), etc.

    The Variable time base is part of a ternary relation with a Variable and a Station.

    The variable information is obtained from the MeteoCat API call described in:
    https://apidocs.meteocat.gencat.cat/documentacio/dades-mesurades/#metadades-de-les-variables-duna-estacio

    :type __tablename__: str
    :type code: VariableStateCategory or Column or None
    :type ts: datetime.datetime or Column
    """
    __tablename__ = 'meteocat_variable_time_base'
    code = mapped_column('code', Enum(MeteocatVariableTimeBaseCategory, name='meteocat_variable_time_base_category'), nullable=False)
    # SQLAlchemy relations
    meteocat_weather_station_id: Mapped[int] = mapped_column(Integer, ForeignKey('meteocat_weather_station.id'))
    meteocat_weather_station: Mapped["MeteocatWeatherStation"] = relationship('MeteocatWeatherStation', back_populates='meteocat_variable_time_bases')
    meteocat_variable_id: Mapped[int] = mapped_column(Integer, ForeignKey('meteocat_variable.id'), nullable=False)
    meteocat_variable: Mapped["MeteocatVariable"] = relationship('MeteocatVariable', back_populates='meteocat_variable_time_bases')

    def __init__(self, time_base: Optional[MeteocatVariableTimeBase] = None,
                 code: Optional[MeteocatVariableTimeBaseCategory, None] = None,
                 valid_from: Optional[datetime.datetime, None] = None,
                 valid_until: Optional[datetime.datetime, None] = None) -> None:
        """
        Variable time base object constructor
        :param code: Variable time base type
        :type code: VariableTimeBaseCategory
        :param from_date: Start date of validity od the variable time base
        :type from_date: datetime
        :param to_date: Finishing date of the validity of the variable time base
        :type to_date: datetime
        """
        if time_base is not None and isinstance(time_base, MeteocatVariableTimeBase):
            code = time_base.code
            valid_from = time_base.valid_from
            valid_until = time_base.valid_until
        super().__init__(valid_from=valid_from, valid_until=valid_until)
        self.code = code

    def __iter__(self):
        yield from super().__iter__()
        yield 'code', self.code.name
        yield 'variable_id', self.meteocat_variable_id
        yield 'weather_station_id', self.meteocat_weather_station_id

    @staticmethod
    def object_hook_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariableTimeBase, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a VariableTimeBase object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: VariableTimeBase
        """
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            time_base = MeteocatVariableTimeBase()
            time_base.code = MeteocatVariableTimeBaseCategory(dct['codi'])
            time_base.valid_from = datetime.datetime.strptime(dct['dataInici'], "%Y-%m-%dT%H:%M%z")
            if dct['dataFi'] is not None:
                time_base.valid_until = datetime.datetime.strptime(dct['dataFi'], "%Y-%m-%dT%H:%M%z")
            return time_base
        return None  # pragma: no cover

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatVariableTimeBase, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('id', 'code', 'valid_from', 'valid_until', 'ts', 'variable_id', 'weather_station_id')):
            time_base = MeteocatVariableTimeBase()
            time_base.id = dct['id']
            time_base.code = MeteocatVariableTimeBaseCategory[dct['code']]
            time_base.valid_from = datetime.datetime.strptime(dct['valid_from'], "%Y-%m-%dT%H:%M:%S%z")
            if dct['valid_until'] is not None:
                time_base.valid_until = datetime.datetime.strptime(dct['valid_until'], "%Y-%m-%dT%H:%M:%S%z")
            time_base.meteocat_variable_id = dct['variable_id']
            time_base.meteocat_weather_station_id = dct['weather_station_id']
            return time_base
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
            if isinstance(obj, MeteocatVariableTimeBase):
                obj: MeteocatVariableTimeBase
                dct_variable_time_base = dict(obj)
                return dct_variable_time_base
            return json.JSONEncoder.default(self, obj)  # pragma: no cover


class MeteocatVariable(Variable):
    """
    Class container for the variable table.  Provides the SQL Alchemy access to the different variables that can be
    measured or calculated in the different weather stations.

    The variable information is obtained from the MeteoCat API call described in:
    https://apidocs.meteocat.gencat.cat/documentacio/dades-mesurades/#metadades-de-totes-les-variables

    :type __tablename__: str
    :type id: int
    :type code: int
    :type unit: str
    :type acronym: str
    :type category: VariableCategory
    :type decimal_positions: int
    :type measures: relationship
    :type states: list()
    :type time_bases: list()
    """
    # SQLAlchemy columns
    __tablename__ = 'meteocat_variable'
    id: Mapped[int] = mapped_column(ForeignKey('variable.id'), primary_key=True)
    code: Mapped[int] = mapped_column('code', Integer, nullable=False, unique=True)
    unit: Mapped[str] = mapped_column('unit', String, nullable=False)
    acronym: Mapped[str] = mapped_column('acronym', String, nullable=False)
    category: Mapped[MeteocatVariableCategory] = mapped_column('category', Enum(MeteocatVariableCategory, name='meteocat_variable_category'), nullable=False)
    decimal_positions: Mapped[int] = mapped_column('decimal_positions', Integer, nullable=False)
    # SQLAlchemy relations
    meteocat_variable_states: Mapped[List["MeteocatVariableState"]] = relationship('MeteocatVariableState', back_populates='meteocat_variable')
    meteocat_variable_time_bases: Mapped[List["MeteocatVariableTimeBase"]] = relationship('MeteocatVariableTimeBase', back_populates='meteocat_variable')
    # measures: Mapped[List["MeteocatMeasure"]] = relationship('MeteocatMeasure', back_populates='meteocat_variable')
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_variable",
    }

    def __init__(self, name: Optional[str] = None, code: Optional[int] = None, unit: Optional[str] = None,
                 acronym: Optional[str] = None, category: Optional[MeteocatVariableCategory] = None,
                 decimal_positions: Optional[int] = None) -> None:
        """
        Variable constructor

        :param code: MeteoCat code of the variable in its API
        :type code: int
        :param name: Name of the variable in the MeteoCat API
        :type name: str
        :param unit: Units of measure of the variable
        :type unit: str
        :param acronym: Acronym of the variable
        :type acronym: str
        :param category: Variable type. Can be DAT (real measured DATa), AUX (Auxiliary data) or CMV (Compound
        MultiVariate)
        :type category: VariableCategory
        :param decimal_positions: Number of significant decimals of the measures
        :type decimal_positions: int
        """
        super().__init__(name=name)
        self.code = code
        self.unit = unit
        self.acronym = acronym
        self.category = category
        self.decimal_positions = decimal_positions

    def __iter__(self) -> Iterator[Any]:
        yield from super().__iter__()
        yield 'code', self.code
        yield 'unit', self.unit
        yield 'acronym', self.acronym
        yield 'category', self.category.name
        yield 'decimal_positions', self.decimal_positions

    @staticmethod
    def object_hook_variable_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariable, None]:
        if all(k in dct for k in ('codi', 'nom', 'unitat', 'acronim', 'tipus', 'decimals')):
            variable = MeteocatVariable()
            variable.name = str(dct['nom'])
            variable.code = int(dct['codi'])
            variable.unit = str(dct['unitat'])
            variable.acronym = str(dct['acronim'])
            variable.category = MeteocatVariableCategory(dct['tipus'])
            variable.decimal_positions = int(dct['decimals'])
            return variable
        return None  # pragma: no cover

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatVariable, None]:
        if all(k in dct for k in ('id', 'name', 'ts', 'code', 'unit', 'acronym', 'category', 'decimal_positions', 'data_provider')):
            variable = MeteocatVariable()
            variable.id = dct['id']
            variable.name = dct['name']
            variable.code = dct['code']
            variable.unit = dct['unit']
            variable.acronym = dct['acronym']
            variable.category = MeteocatVariableCategory(dct['category'])
            variable.decimal_positions = dct['decimal_positions']
            variable.data_provider_name = dct['data_provider']
            print(dict(variable))
            return variable
        return None  # pragma: no cover


    @staticmethod
    def object_hook_variables_of_station_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariable, MeteocatVariableTimeBase, MeteocatVariableState, None]:
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            if isinstance(dct['codi'], str):
                time_base = MeteocatVariableTimeBase.object_hook_meteocat_api(dct)
                return time_base
            else:
                state = MeteocatVariableState.object_hook_meteocat_api(dct)
                return state
        if all(k in dct for k in ('codi', 'nom', 'unitat', 'acronim', 'tipus', 'decimals')):
            variable = MeteocatVariable()
            variable.name = str(dct['nom'])
            variable.code = int(dct['codi'])
            variable.unit = str(dct['unitat'])
            variable.acronym = str(dct['acronim'])
            variable.category = MeteocatVariableCategory(dct['tipus'])
            variable.decimal_positions = int(dct['decimals'])
            if 'estats' in dct and variable.category != MeteocatVariableCategory.CMV:
                variable.meteocat_variable_states = dct['estats']
            if 'basesTemporals' in dct:
                variable.meteocat_variable_time_bases = dct['basesTemporals']
            return variable
        return None  # pragma: no cover

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a database lightning to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj:
            :type obj: object
            :return: dict
            """
            if isinstance(obj, MeteocatVariable):
                obj: MeteocatVariable
                dct_variable = dict(obj)
                return dct_variable
            return json.JSONEncoder.default(self, obj)  # pragma: no cover