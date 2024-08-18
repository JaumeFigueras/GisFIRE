#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json
import pytest

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.json_decoders.no_none_in_list import NoNoneInList
from src.data_model.data_provider import DataProvider
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationCategory
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.data_model.weather_station import MeteocatWeatherStationStateCategory
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_weather_stations
from test.fixtures.database.database import populate_meteocat_variables
from test.fixtures.database.database import populate_meteocat_variable_states
from test.fixtures.database.database import populate_meteocat_variable_time_bases

from typing import List
from typing import Union
from typing import Dict
from typing import Any


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
    assert station.x_25831 == 431520.6685930927
    assert station.y_25831 == 4582380.322073667
    assert station.geometry_25831 == "SRID=25831;POINT(431520.6685930927 4582380.322073667)"
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
        'x_25831': 431520.6685930927,
        'y_25831': 4582380.322073667,
        'states': [],
        'data_provider': None,
        'ts': None,
    }


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_meteocat_weather_station_dict_02(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                          meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                                          patch_postgresql_time) -> None:
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 1
        station = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'CA')).unique().scalar_one()
        assert dict(station) == {
            'id': 1,
            'name': 'Clariana de Cardener',
            'altitude': 693.0,
            'x_4326': 1.5851,
            'y_4326': 41.95378,
            'code': 'CA',
            'category': 'AUTO',
            'x_4258': 1.5851,
            'y_4258': 41.95378,
            'placement': 'Abocador comarcal',
            'municipality_code': '250753',
            'municipality_name': 'Clariana de Cardener',
            'county_code': '35',
            'county_name': 'Solsonès',
            'province_code': '25',
            'province_name': 'Lleida',
            'network_code': '1',
            'network_name': 'XEMA',
            'x_25831': 382735.30061883596,
            'y_25831': 4645612.566118578,
            'states': [
                {
                    'code': 'ACTIVE',
                    'id': 1,
                    'weather_station_id': 1,
                    'ts': '2024-01-01T12:00:00+0000',
                    'valid_from': '1996-05-02T09:00:00+0000',
                    'valid_until': '2012-07-10T13:00:00+0000',
                },
                {
                    'code': 'DISMANTLED',
                    'id': 2,
                    'weather_station_id': 1,
                    'ts': '2024-01-01T12:00:00+0000',
                    'valid_from': '2012-07-10T13:00:00+0000',
                    'valid_until': None,
                },
            ],
            'data_provider': 'Meteo.cat',
            'ts': '2024-01-01T12:00:00+0000',
        }


def test_meteocat_weather_station_json_parser(meteocat_api_weather_stations: str) -> None:
    """
    TODO
    :param meteocat_api_weather_stations:
    :return:
    """
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
    assert station.x_25831 == 431520.6685930927
    assert station.y_25831 == 4582380.322073667
    assert station.geometry_25831 == "SRID=25831;POINT(431520.6685930927 4582380.322073667)"
    assert len(station.meteocat_weather_station_states) == 2
    state_1 = station.meteocat_weather_station_states[0]
    assert isinstance(state_1, MeteocatWeatherStationState)
    assert state_1.code == MeteocatWeatherStationStateCategory.ACTIVE
    assert state_1.valid_from == datetime.datetime(1992, 5, 11, 15, 30, tzinfo=pytz.UTC)
    assert state_1.tzinfo_valid_from == 'UTC'
    assert state_1.valid_until == datetime.datetime(2002, 10, 29, 5, 0, tzinfo=pytz.UTC)
    assert state_1.tzinfo_valid_until == 'UTC'
    state_2 = station.meteocat_weather_station_states[1]
    assert isinstance(state_2, MeteocatWeatherStationState)
    assert state_2.code == MeteocatWeatherStationStateCategory.DISMANTLED
    assert state_2.valid_from == datetime.datetime(2002, 10, 29, 5, 0, tzinfo=pytz.UTC)
    assert state_2.tzinfo_valid_from == 'UTC'
    assert state_2.valid_until is None
    assert state_2.tzinfo_valid_until is None


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_meteocat_weather_station_json_encoder_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                                  meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                                                  patch_postgresql_time) -> None:
    """
    TODO
    :param db_session:
    :param data_provider_list:
    :param meteocat_weather_station_list:
    :param patch_postgresql_time:
    :return:
    """
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 1
        station = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'CA')).unique().scalar_one()
        station_dict = {
            'id': 1,
            'name': 'Clariana de Cardener',
            'altitude': 693.0,
            'x_4326': 1.5851,
            'y_4326': 41.95378,
            'code': 'CA',
            'category': 'AUTO',
            'x_4258': 1.5851,
            'y_4258': 41.95378,
            'placement': 'Abocador comarcal',
            'municipality_code': '250753',
            'municipality_name': 'Clariana de Cardener',
            'county_code': '35',
            'county_name': 'Solsonès',
            'province_code': '25',
            'province_name': 'Lleida',
            'network_code': '1',
            'network_name': 'XEMA',
            'x_25831': 382735.30061883596,
            'y_25831': 4645612.566118578,
            'states': [
                {
                    'code': 'ACTIVE',
                    'id': 1,
                    'weather_station_id': 1,
                    'ts': '2024-01-01T12:00:00+0000',
                    'valid_from': '1996-05-02T09:00:00+0000',
                    'valid_until': '2012-07-10T13:00:00+0000',
                },
                {
                    'code': 'DISMANTLED',
                    'id': 2,
                    'weather_station_id': 1,
                    'ts': '2024-01-01T12:00:00+0000',
                    'valid_from': '2012-07-10T13:00:00+0000',
                    'valid_until': None,
                },
            ],
            'data_provider': 'Meteo.cat',
            'ts': '2024-01-01T12:00:00+0000',
        }
        assert json.loads(json.dumps(station, cls=MeteocatWeatherStation.JSONEncoder)) == station_dict


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_meteocat_weather_station_geojson_encoder_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                                     meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                                                     patch_postgresql_time) -> None:
    """
    TODO
    :param db_session:
    :param data_provider_list:
    :param meteocat_weather_station_list:
    :param patch_postgresql_time:
    :return:
    """
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 1
        station = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'CA')).unique().scalar_one()
        station_dict = {
            "type": "Feature",
            "id": 1,
            "geometry": {
                "type": "Point",
                "coordinates": [1.5851, 41.95378]
            },
            "properties": {
                "id": 1,
                "name": "Clariana de Cardener",
                "altitude": 693.0,
                "x_4258": 1.5851,
                "y_4258": 41.95378,
                'x_25831': 382735.30061883596,
                'y_25831': 4645612.566118578,
                "x_4326": 1.5851,
                "y_4326": 41.95378,
                "ts": "2024-01-01T12:00:00+0000",
                "data_provider": "Meteo.cat",
                "code": "CA",
                "category": "AUTO",
                "placement": "Abocador comarcal",
                "municipality_code": "250753",
                "municipality_name": "Clariana de Cardener",
                "county_code": "35",
                "county_name": "Solsonès",
                "province_code": "25",
                "province_name": "Lleida",
                "network_code": "1",
                "network_name": "XEMA",
                "states": [
                    {
                        "code": "ACTIVE",
                        "id": 1,
                        "valid_from": "1996-05-02T09:00:00+0000",
                        "valid_until": "2012-07-10T13:00:00+0000",
                        "ts": "2024-01-01T12:00:00+0000",
                        "weather_station_id": 1
                    },
                    {
                        "code": "DISMANTLED",
                        "id": 2,
                        "valid_from": "2012-07-10T13:00:00+0000",
                        "valid_until": None,
                        "ts": "2024-01-01T12:00:00+0000",
                        "weather_station_id": 1
                    }
                ]
            }
        }
        assert json.loads(json.dumps(station, cls=MeteocatWeatherStation.GeoJSONEncoder)) == station_dict


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_weather_station_variables_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                      gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                                      gisfire_variables_list: Union[List[MeteocatVariable], None],
                                      gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                                      gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None]
                                      ) -> None:
    """
    Tests all is OK

    :param db_session:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Test function
    station = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'CA')).unique().scalar_one()
    variables = station.meteocat_variables
    assert len(variables) == 23



