#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import enum
import datetime
import json

import dateutil.parser
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model.weather_station import WeatherStation
from src.data_model.state import State

from typing import Union
from typing import Dict
from typing import Optional
from typing import Any
from typing import List
from typing import Iterator


class MeteocatStateCategory(enum.Enum):
    """
    Defines the three types os statuses

    DISMANTLED for dismantled stations
    ACTIVE for active station
    REPAIR for station under some type of repair or temporal inactivity
    """
    ACTIVE = 2
    DISMANTLED = 1
    REPAIR = 3


class MeteocatState(State):
    """
    Class container for the weather station status table.  Provides the SQL Alchemy access to the different status of
    the timeline of a weather station. A weather station status informs of the presence of a certain weather station in
    the system.

    The weather station status information is obtained from the MeteoCat API call described in:
    https://apidocs.meteocat.gencat.cat/documentacio/metadades-estacions/#metadades-de-totes-les-estacions

    :type __tablename__: str
    :type code: WeatherStationStateCategory or Column or None
    :type weather_station_id: int or Column
    :type ts: datetime.datetime or Column
    :type station: relationship
    """
    # SQLAlchemy columns
    __abstract__ = True


    def __init__(self, code: Optional[MeteocatStateCategory] = None,
                 valid_from: Optional[datetime.datetime, None] = None,
                 valid_until: Optional[datetime.datetime, None] = None) -> None:
        super().__init__(valid_from, valid_until)
        self.code = code

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, MeteocatState):
            equals: bool = super().__eq__(other)
            equals = equals and self.code == other.code
            return equals
        return False

    def __iter__(self) -> Iterator[Any]:
        yield 'code', self.code.name
        yield from super().__iter__()

    @staticmethod
    def object_hook_meteocat_api(dct: Dict[str, Any]) -> Union[MeteocatState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            state = MeteocatState()
            state.code = MeteocatStateCategory(dct['codi'])
            state.valid_from = datetime.datetime.strptime(dct['dataInici'], "%Y-%m-%dT%H:%M%z")
            if dct['dataFi'] is not None:
                state.valid_until = datetime.datetime.strptime(dct['dataFi'], "%Y-%m-%dT%H:%M%z")
            return state
        return None  # pragma: no cover

    @staticmethod
    def object_hook_gisfire_api(dct: Dict[str, Any]) -> Union[MeteocatState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        if all(k in dct for k in ('id', 'code', 'valid_from', 'valid_until', 'ts')):
            state = MeteocatState()
            state.id = int(dct['id'])
            state.code = MeteocatStateCategory[dct['code']]
            state.valid_from = datetime.datetime.strptime(dct['valid_from'], "%Y-%m-%dT%H:%M:%S%z")
            if dct['valid_until'] is not None:
                state.valid_until = datetime.datetime.strptime(dct['valid_until'], "%Y-%m-%dT%H:%M:%S%z")
            return state
        return None  # pragma: no cover

    class JSONEncoder(json.JSONEncoder):
        """
        JSON Encoder to convert a database WeatherStationStatus to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj:
            :type obj: Lightning
            :return: dict
            """

            def default(self, obj: object) -> Dict[str, Any]:
                """
                Default procedure to create a dictionary with the Variable time bas2 data

                :param obj:
                :type obj: Lightning
                :return: dict
                """
                if isinstance(obj, MeteocatState):
                    obj: MeteocatState
                    dct_state = dict(obj)
                    return dct_state
                return json.JSONEncoder.default(self, obj)  # pragma: no cover

