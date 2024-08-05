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
from src.meteocat.data_model.state import MeteocatState

from typing import Union
from typing import Dict
from typing import Optional
from typing import Any
from typing import List


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


class MeteocatVariableTimeBaseCategory(str, enum.Enum):
    """
    Defines the different types of sampling times for a variable
    """
    HO = 'HO'
    SH = 'SH'
    DM = 'DM'
    MI = 'MI'
    D5 = 'D5'


class MeteocatVariableState(MeteocatState):
    # SQLAlchemy columns
    __tablename__ = 'meteocat_variable_state'
    # SQLAlchemy relations
    variable: Mapped["MeteocatAssociationStationVariableState"] = relationship('MeteocatAssociationStationVariableState', back_populates='variable_state')

    def __init__(self, state: Optional[MeteocatState] = None, *args, **kwargs):
        if state is None:
            super().__init__(*args, **kwargs)
        else:
            super().__init__(code=state.code, valid_from=state.valid_from, valid_until=state.valid_until)

    @staticmethod
    def object_hook_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariableState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        state = MeteocatState.object_hook_meteocat_api(dct)
        if state is not None:
            return MeteocatVariableState(state)
        return None  # pragma: no cover


class MeteocatVariableTimeBase(MeteocatState):
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
    code = mapped_column('code', Enum(MeteocatVariableTimeBaseCategory, name='meteocat_variable_time_base_category'), nullable=False, use_existing_column=False)
    variables_time_base: Mapped["MeteocatAssociationStationVariableTimeBase"] = relationship('MeteocatAssociationStationVariableTimeBase', back_populates='variable_time_base')

    def __init__(self, state: Optional[MeteocatState] = None, code: Optional[MeteocatVariableTimeBaseCategory, None] = None,
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
        if state is None:
            super().__init__(valid_from=valid_from, valid_until=valid_until)
            self.code = code
        else:
            if code is None:
                raise ValueError("Must provide a code when initializing a time base state from another state")
            super().__init__(valid_from=state.valid_from, valid_until=state.valid_until)
            self.code = code

    @staticmethod
    def object_hook_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatVariableTimeBase, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a VariableTimeBase object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: VariableTimeBase
        """
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            code = MeteocatVariableTimeBaseCategory(dct['codi'])
            dct['codi'] = 1
            state = MeteocatState.object_hook_meteocat_api(dct)
            if state is not None:
                return MeteocatVariableTimeBase(state=state, code=code)
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
                dct_variable_time_base = dict()
                dct_variable_time_base['code'] = str(obj.code.value)
                dct_state = State.JSONEncoder().default(obj)
                # Merges the two dicts with values from dct_weather_station_state replacing those from dct_state
                return {**dct_state, **dct_variable_time_base}
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
    weather_stations: Mapped[List["MeteocatAssociationStationVariableState"]] = relationship('MeteocatAssociationStationVariableState', back_populates='variable', overlaps='variable, weather_stations')
    variable_states: Mapped[List["MeteocatAssociationStationVariableState"]] = relationship('MeteocatAssociationStationVariableState', back_populates='variable', overlaps='variable, weather_stations')
    weather_stations_time_base: Mapped[List["MeteocatAssociationStationVariableTimeBase"]] = relationship('MeteocatAssociationStationVariableTimeBase', back_populates='variable', overlaps='variable, weather_stations_time_base')
    variable_states_time_base: Mapped[List["MeteocatAssociationStationVariableTimeBase"]] = relationship('MeteocatAssociationStationVariableTimeBase', back_populates='variable', overlaps='variable, weather_stations_time_base')
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
        self.unbinded_states: Union[List[MeteocatVariableState], None] = None
        self.unbinded_time_bases: Union[List[MeteocatVariableTimeBase], None] = None

    def __iter__(self):
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
                variable.unbinded_states = dct['estats']
            else:
                variable.unbinded_states = list()
            if 'basesTemporals' in dct:
                variable.unbinded_time_bases = dct['basesTemporals']
            else:
                variable.unbinded_time_bases = list()
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
            if isinstance(obj, Variable):
                obj: Variable
                dct = dict()
                dct['code'] = obj.code
                dct['name'] = obj.name
                dct['category'] = obj.category.value
                dct['unit'] = obj.unit
                dct['acronym'] = obj.acronym
                dct['decimal_positions'] = obj.decimal_positions
                dct['states'] = [MeteocatVariableState.JSONEncoder().default(state) for state in obj.states]
                dct['time_bases'] = [MeteocatVariableTimeBase.JSONEncoder().default(time_base) for time_base in obj.time_bases]
                return dct
            return json.JSONEncoder.default(self, obj)  # pragma: no cover