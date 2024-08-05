#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationCategory
from src.meteocat.data_model.state import MeteocatState
from src.meteocat.data_model.state import MeteocatStateCategory

from typing import List


def test_meteocat_weather_station_01() -> None:
    station = MeteocatWeatherStation()
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(name='ST')
    assert station.name == 'ST'
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(altitude=129)
    assert station.name is None
    assert station.altitude == 129
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(category=MeteocatWeatherStationCategory.AUTO)
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category == MeteocatWeatherStationCategory.AUTO
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(longitude_epsg_4258=2.3697)
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 == 2.3697
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(latitude_epsg_4258=42.3697)
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 == 42.3697
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(placement='PLACE')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement == 'PLACE'
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(municipality_code='08222')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code == '08222'
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(municipality_name='MUNICIPALITY')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name == 'MUNICIPALITY'
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(county_code='25')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code == '25'
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(county_name='COUNTY')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name == 'COUNTY'
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(province_code='8')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code == '8'
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(province_name='PROVINCE')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name == 'PROVINCE'
    assert station.network_code is None
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(network_code='1')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code == '1'
    assert station.network_name is None
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(network_name='XEMA')
    assert station.name is None
    assert station.altitude is None
    assert station.x_4326 is None
    assert station.y_4326 is None
    assert station.geometry_4326 is None
    assert station.category is None
    assert station.x_4258 is None
    assert station.y_4258 is None
    assert station.geometry_4258 is None
    assert station.placement is None
    assert station.municipality_code is None
    assert station.municipality_name is None
    assert station.county_code is None
    assert station.county_name is None
    assert station.province_code is None
    assert station.province_name is None
    assert station.network_code is None
    assert station.network_name == 'XEMA'
    assert station.x_25831 is None
    assert station.y_25831 is None
    assert station.geometry_25831 is None
    assert station.data_provider_name is None
    station = MeteocatWeatherStation(name='NAME', code='ST', altitude=129, category=MeteocatWeatherStationCategory.AUTO,
                                     longitude_epsg_4258=2.18091, latitude_epsg_4258=41.39004, placement='PLACE',
                                     municipality_code='08222', municipality_name='MUNI', county_code='25',
                                     county_name='CT', province_code='8', province_name='PROV', network_code='1',
                                     network_name='XEMA')
    assert station.name == 'NAME'
    assert station.altitude == 129
    assert station.x_4326 == 2.18091
    assert station.y_4326 == 41.39004
    assert station.geometry_4326 == "SRID=4326;POINT(2.18091 41.39004)"
    assert station.code == 'ST'
    assert station.category == MeteocatWeatherStationCategory.AUTO
    assert station.x_4258 == 2.18091
    assert station.y_4258 == 41.39004
    assert station.geometry_4258 == "SRID=4258;POINT(2.18091 41.39004)"
    assert station.placement == 'PLACE'
    assert station.municipality_code == '08222'
    assert station.municipality_name == 'MUNI'
    assert station.county_code == '25'
    assert station.county_name == 'CT'
    assert station.province_code == '8'
    assert station.province_name == 'PROV'
    assert station.network_code == '1'
    assert station.network_name == 'XEMA'
    assert station.x_25831 == 5131215.529498735
    assert station.y_25831 == 308107.46729102544
    assert station.geometry_25831 == "SRID=25831;POINT(5131215.529498735 308107.46729102544)"
    assert station.data_provider_name is None


def test_meteocat_weather_station_dict_01() -> None:
    station = MeteocatWeatherStation(name='ESTACIÓ', altitude=129, code='ST',
                                     category=MeteocatWeatherStationCategory.AUTO, longitude_epsg_4258=2.18091,
                                     latitude_epsg_4258=41.39004, placement='PLACE', municipality_code='08222',
                                     municipality_name='MUNI', county_code='25', county_name='CT', province_code='8',
                                     province_name='PROV', network_code='1', network_name='XEMA')
    assert dict(station) == {
        'id': None,
        'name': 'ESTACIÓ',
        'altitude': 129,
        'x_4326': 2.18091,
        'y_4326': 41.39004,
        'code': 'ST',
        'category': 'AUTO',
        'x_4258': 2.18091,
        'y_4258': 41.39004,
        'placement': 'PLACE',
        'municipality_code': '08222',
        'municipality_name': 'MUNI',
        'county_code': '25',
        'county_name': 'CT',
        'province_code': '8',
        'province_name': 'PROV',
        'network_code': '1',
        'network_name': 'XEMA',
        'x_25831': 5131215.529498735,
        'y_25831': 308107.46729102544,
        'states': [],
        'data_provider': None
    }


def test_meteocat_weather_station_json_parser(meteocat_api_weather_stations: str) -> None:
    stations: List[MeteocatWeatherStation] = json.loads(meteocat_api_weather_stations, cls=NoNoneInList,
                                                        object_hook=MeteocatWeatherStation.object_hook_meteocat_api)
    for station in stations:
        assert isinstance(station, MeteocatWeatherStation)
    station = stations[0]
    assert isinstance(station, MeteocatWeatherStation)
    assert station.name == 'Barcelona - Av. Lluís Companys'
    assert station.altitude == 7.5
    assert station.x_4326 == 2.18091
    assert station.y_4326 == 41.39004
    assert station.geometry_4326 == "SRID=4326;POINT(2.18091 41.39004)"
    assert station.code == 'AN'
    assert station.category == MeteocatWeatherStationCategory.AUTO
    assert station.x_4258 == 2.18091
    assert station.y_4258 == 41.39004
    assert station.geometry_4258 == "SRID=4258;POINT(2.18091 41.39004)"
    assert station.placement == 'Av. Lluís Companys (Ciutadella)'
    assert station.municipality_code == '080193'
    assert station.municipality_name == 'Barcelona'
    assert station.county_code == '13'
    assert station.county_name == 'Barcelonès'
    assert station.province_code == '8'
    assert station.province_name == 'Barcelona'
    assert station.network_code == '1'
    assert station.network_name == 'XEMA'
    assert station.x_25831 == 5131215.529498735
    assert station.y_25831 == 308107.46729102544
    assert station.geometry_25831 == "SRID=25831;POINT(5131215.529498735 308107.46729102544)"
    assert len(station.states) == 2
    state_1 = station.states[0]
    assert isinstance(state_1, MeteocatState)
    assert state_1.code == MeteocatStateCategory.ACTIVE
    assert state_1.valid_from == datetime.datetime(1992, 5, 11, 15, 30, tzinfo=pytz.UTC)
    assert state_1.tzinfo_valid_from == 'UTC'
    assert state_1.valid_until == datetime.datetime(2002, 10, 29, 5, 0, tzinfo=pytz.UTC)
    assert state_1.tzinfo_valid_until == 'UTC'
    state_2 = station.states[1]
    assert isinstance(state_2, MeteocatState)
    assert state_2.code == MeteocatStateCategory.DISMANTLED
    assert state_2.valid_from == datetime.datetime(2002, 10, 29, 5, 0, tzinfo=pytz.UTC)
    assert state_2.tzinfo_valid_from == 'UTC'
    assert state_2.valid_until is None
    assert state_2.tzinfo_valid_until is None
