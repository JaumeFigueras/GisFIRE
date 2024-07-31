#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import enum
import datetime
import json

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


class MeteocatWeatherStationCategory(enum.Enum):
    """
    Defines the type of weather station

    AUTO for automatic weather stations
    OTHER for types different from automatic
    """
    AUTO = 0
    OTHER = 1


class MeteocatWeatherStationStateCategory(enum.Enum):
    """
    Defines the three types os statuses

    DISMANTLED for dismantled stations
    ACTIVE for active station
    REPAIR for station under some type of repair or temporal inactivity
    """
    ACTIVE = 2
    DISMANTLED = 1
    REPAIR = 3


class MeteocatWeatherStationState(State):
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
    __tablename__ = 'meteocat_weather_station_state'
    code = mapped_column('code', Enum(MeteocatWeatherStationCategory, name='meteocat_weather_station_state_category'), nullable=False)
    # SQLAlchemy relations
    weather_station_id = Column(Integer, ForeignKey('weather_station.id'))
    station: Mapped["WeatherStation"] = relationship(back_populates='states')

    def __init__(self, code: Optional[MeteocatWeatherStationStateCategory] = None,
                 valid_from: Optional[datetime.datetime, None] = None,
                 valid_until: Optional[datetime.datetime, None] = None) -> None:
        super().__init__(valid_from, valid_until)
        self.code = code

    @staticmethod
    def object_hook(dct: Dict[str, Any]) -> MeteocatWeatherStationState:
        """
        Decodes a JSON originated dict from the Meteocat API to a WeatherStationStatus object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: Dict[str, Any]
        :return: WeatherStationStatus
        """
        status = MeteocatWeatherStationState()
        status.code = MeteocatWeatherStationStateCategory(dct['codi'])
        State.object_hook_abstract(dct, status)
        return status

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
            if isinstance(obj, MeteocatWeatherStationState):
                obj: MeteocatWeatherStationState
                dct_weather_station_state = dict()
                dct_weather_station_state['code'] = int(obj.code.value)
                dct_state = State.JSONEncoder().default(obj)
                # Merges the two dicts with values from dct_weather_station_state replacing those from dct_state
                return {**dct_state, **dct_weather_station_state}
            return json.JSONEncoder.default(self, obj)  # pragma: no cover


class MeteocatWeatherStation(WeatherStation):
    """
    Class container for the weather station table.  Provides the SQL Alchemy access to the different weather stations.

    The weather station information is obtained from the MeteoCat API call described in:
    https://apidocs.meteocat.gencat.cat/documentacio/metadades-estacions/#metadades-de-totes-les-estacions

    :type __tablename__: str
    :type id: int
    :type code: str
    :type name: str
    :type category: WeatherStationCategory
    :type _coordinates_latitude: float
    :type _coordinates_longitude: float
    :type placement: str
    :type altitude: float
    :type municipality_code: int
    :type municipality_name: str
    :type county_code: int
    :type county_name: str
    :type province_code: int
    :type province_name: str
    :type network_code: int
    :type network_name: str
    :type ts: datetime
    :type postgis_geometry = str or Column
    :type states: relationship
    :type measures: relationship
    """
    # Metaclass location attributes
    __location__ = [
        {'epsg': 4258, 'validation': 'geographic', 'conversion': [
            {'src': 4258, 'dst': 4326},
            {'src': 4258, 'dst': 25831}
        ]},
        {'epsg': 25831, 'validation': False, 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_4258: float
    y_4258: float
    geometry_4258: Union[str, Point]
    x_25831: float
    y_25831: float
    geometry_25831: Union[str, Point]
    # SQLAlchemy columns
    __tablename__ = 'meteocat_weather_station'
    id: Mapped[int] = mapped_column(ForeignKey("weather_station.id"), primary_key=True)
    code: Mapped[str] = mapped_column('meteocat_code', String, nullable=False, unique=True)
    category: Mapped[MeteocatWeatherStationCategory] = mapped_column('meteocat_type', Enum(MeteocatWeatherStationCategory, name='meteocat_weather_station_category'), nullable=False)
    placement: Mapped[str] = mapped_column('meteocat_placement', String, nullable=False)
    municipality_code: Mapped[str] = mapped_column('meteocat_municipality_code', String, nullable=False)
    municipality_name: Mapped[str] = mapped_column('meteocat_municipality_name', String, nullable=False)
    county_code: Mapped[str] = mapped_column('meteocat_county_code', Integer, nullable=False)
    county_name: Mapped[str] = mapped_column('meteocat_county_name', String, nullable=False)
    province_code: Mapped[str] = mapped_column('meteocat_province_code', String, nullable=False)
    province_name: Mapped[str] = mapped_column('meteocat_province_name', String, nullable=False)
    network_code: Mapped[str] = mapped_column('meteocat_network_code', String, nullable=False)
    network_name: Mapped[str] = mapped_column('meteocat_network_name', String, nullable=False)
    # SQLAlchemy Relations
    states: Mapped[List[MeteocatWeatherStationState]] = relationship("MeteocatWeatherStationState", back_populates='station', lazy='joined')
    measures = relationship("Measure", back_populates='station', lazy='select')
    # TODO: add variables relationship
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "meteocat_weather_station",
    }

    def __init__(self, code: Optional[str, None] = None, name: Optional[str, None] = None,
                 category: Optional[MeteocatWeatherStationCategory, None] = None,
                 longitude_epsg_4258: Optional[float, None] = None,
                 latitude_epsg_4258: Optional[float, None] = None, placement: Optional[str, None] = None,
                 altitude: Optional[float, None] = None, municipality_code: Optional[int, None] = None,
                 municipality_name: Optional[str, None] = None, county_code: Optional[int, None] = None,
                 county_name: Optional[str, None] = None, province_code: Optional[int, None] = None,
                 province_name: Optional[str, None] = None, network_code: Optional[int, None] = None,
                 network_name: Optional[str, None] = None) -> None:
        """

        :param code: Station code provided by the Meteocat API
        :type code: str
        :param name: Station name
        :type name: str
        :param category: Type of the station
        :type category: WeatherStationCategory
        :param coordinates_latitude: Latitude of the location of the weather station
        :type coordinates_latitude: float
        :param coordinates_longitude: Longitude of the location of the weather station
        :type coordinates_longitude: float
        :param placement: Description of the location of the station
        :type placement: str
        :param altitude: Altitude above the sea level of the station
        :type altitude: float
        :param municipality_code: Spanish INE municipality code of the station location
        :type municipality_code: int
        :param municipality_name: Name of the municipality where the station is located
        :type municipality_name: str
        :param county_code: Spanish INE county code of the station location
        :type county_code: int
        :param county_name: Name of the county where the station is located
        :type county_name: str
        :param province_code: Spanish INE province code of the station location
        :type province_code: int
        :param province_name: Name of the province where the station is located
        :type province_name: str
        :param network_code: Code of the network where the station belongs
        :type network_code: int
        :param network_name: Name of the network where the station belongs
        :type network_name: str
        """
        super().__init__(name, altitude)
        self.code = code
        self.category = category
        self.x_4258 = longitude_epsg_4258
        self.y_4258 = latitude_epsg_4258
        self.placement = placement
        self.municipality_code = municipality_code
        self.municipality_name = municipality_name
        self.county_code = county_code
        self.county_name = county_name
        self.province_code = province_code
        self.province_name = province_name
        self.network_code = network_code
        self.network_name = network_name

    def __iter__(self):
        yield 'code', self.code
        yield 'category', self.category
        yield 'placement', self.placement
        yield 'municipality_code', self.municipality_code
        yield 'municipality_name', self.municipality_name
        yield 'county_code', self.county_code
        yield 'county_name', self.county_name
        yield 'province_code', self.province_code
        yield 'province_name', self.province_name
        yield 'network_code', self.network_code
        yield 'network_name', self.network_name
        yield from super().__iter__()

    @staticmethod
    def object_hook(dct: Dict[str, Any]) -> Union[WeatherStation, Dict[str, Any], MeteocatWeatherStationState, None]:
        """
        Decodes a JSON originated dict from the Meteocat API to a Lightning object

        :param dct: Dictionary with the standard parsing of the json library
        :type dct: dict
        :return: Lightning
        """
        # 'municipi', 'comarca', 'provincia' or 'xarxa' dict of the Meteocat API JSON
        if all(k in dct for k in ('codi', 'nom')) and len(dct) == 2:
            return dct
        # weather station status dict of the Meteocat API JSON
        if all(k in dct for k in ('codi', 'dataInici', 'dataFi')):
            state = MeteocatWeatherStationState.object_hook(dct)
            return state
        # Lat-lon coordinates dict of the Meteocat API JSON
        if all(k in dct for k in ('latitud', 'longitud')):
            return dct
        if not (all(k in dct for k in ('codi', 'nom', 'tipus', 'coordenades', 'emplacament', 'altitud', 'municipi',
                                       'comarca', 'provincia', 'xarxa', 'estats'))):
            return None
        station = MeteocatWeatherStation()
        station.code = str(dct['codi'])
        station.name = str(dct['nom'])
        station.category = MeteocatWeatherStationCategory.AUTO if str(dct['tipus']) == 'A' else MeteocatWeatherStationCategory.OTHER
        station.placement = str(dct['emplacament'])
        station.altitude = float(dct['altitud'])
        station.x_4258 = float(dct['coordenades']['longitud'])
        station.y_4258 = float(dct['coordenades']['latitud'])
        station.municipality_code = int(dct['municipi']['codi'])
        station.municipality_name = str(dct['municipi']['nom'])
        station.county_code = int(dct['comarca']['codi'])
        station.county_name = str(dct['comarca']['nom'])
        station.province_code = int(dct['provincia']['codi'])
        station.province_name = str(dct['provincia']['nom'])
        station.network_code = int(dct['xarxa']['codi'])
        station.network_name = str(dct['xarxa']['nom'])
        for state in dct['estats']:
            state: MeteocatWeatherStationState
            station.states.append(state)
        return station

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
            if isinstance(obj, MeteocatWeatherStation):
                obj: MeteocatWeatherStation
                dct = dict()
                dct['code'] = obj.code
                dct['name'] = obj.name
                dct['category'] = obj.category.value
                dct['placement'] = obj.placement
                dct['altitude'] = obj.altitude
                dct['coordinates_latitude'] = obj._coordinates_latitude
                dct['coordinates_longitude'] = obj._coordinates_longitude
                dct['coordinates_epsg'] = WeatherStation.SRID_WEATHER_STATIONS
                dct['municipality_code'] = obj.municipality_code
                dct['municipality_name'] = obj.municipality_name
                dct['county_code'] = obj.county_code
                dct['county_name'] = obj.county_name
                dct['province_code'] = obj.province_code
                dct['province_name'] = obj.province_name
                dct['network_code'] = obj.network_code
                dct['network_name'] = obj.network_name
                dct['states'] = [WeatherStationState.JSONEncoder().default(state) for state in obj.states]
                return dct
            return json.JSONEncoder.default(self, obj)  # pragma: no cover

    class GeoJSONEncoder(json.JSONEncoder):
        """
        Geo JSON Encoder to convert a database weather station to JSON
        """

        def default(self, obj: object) -> Dict[str, Any]:
            """
            Default procedure to create a dictionary with the Lightning data

            :param obj:
            :type obj: object
            :return: dict
            """
            if isinstance(obj, WeatherStation):
                obj: WeatherStation
                dct = dict()
                dct['type'] = 'Feature'
                dct['id'] = obj.id
                dct['crs'] = dict()
                dct['crs']['type'] = 'link'
                dct['crs']['properties'] = dict()
                dct['crs']['properties']['href'] = 'https://spatialreference.org/ref/epsg/' + \
                                                   str(WeatherStation.SRID_WEATHER_STATIONS) + '/proj4/'
                dct['crs']['properties']['type'] = 'proj4'
                dct['geometry'] = dict()
                dct['geometry']['type'] = 'Point'
                dct['geometry']['coordinates'] = [obj._coordinates_longitude, obj._coordinates_latitude]
                dct['properties'] = WeatherStation.JSONEncoder().default(obj)
                return dct
            return json.JSONEncoder.default(self, obj)  # pragma: no cover