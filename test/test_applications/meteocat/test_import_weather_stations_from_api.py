#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import pytest
import logging

import pytz
import requests_mock

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from shapely.geometry import Point


from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.weather_station import MeteocatWeatherStationCategory
from src.meteocat.data_model.weather_station import MeteocatWeatherStationState
from src.meteocat.data_model.state import MeteocatStateCategory
from src.data_model.data_provider import DataProvider
from src.meteocat.remote_api.meteocat_api import XEMA_STATIONS

from test.fixtures.database.database import populate_data_providers

from src.applications.meteocat.import_weather_sattions_from_api import main

from typing import List
from typing import Union


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_main_01(db_session: Session, meteocat_api_weather_stations: str,
                 data_provider_list: Union[List[DataProvider], None]) -> None:
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatWeatherStationState.id))).scalar_one() == 0
    # Test function
    with requests_mock.Mocker() as rm:
        url = XEMA_STATIONS
        rm.get(url, text=meteocat_api_weather_stations, status_code=200)
        main(db_session, '1234', logger)
        # Assert the results
        assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 240
        assert db_session.execute(select(func.count(MeteocatWeatherStationState.id))).scalar_one() == 303
    station: MeteocatWeatherStation = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'WY')).unique().scalar_one()
    assert station.code == 'WY'
    assert station.name == "Sant Sadurní d'Anoia - el Clot de les Comes"
    assert station.category == MeteocatWeatherStationCategory.AUTO
    assert station.x_4258 == 1.79429
    assert station.y_4258 == 41.43386
    assert station.geometry_4258 == Point(1.79429, 41.43386)
    assert station.placement == '-'
    assert station.altitude == 164
    assert station.municipality_code == '082401'
    assert station.municipality_name == "Sant Sadurní d'Anoia"
    assert station.county_code == '3'
    assert station.county_name == "Alt Penedès"
    assert station.province_code == '8'
    assert station.province_name == "Barcelona"
    assert station.network_code == '1'
    assert station.network_name == 'XEMA'
    assert len(station.states) == 2
    assert station.states[0].code == MeteocatStateCategory.ACTIVE
    assert station.states[0].valid_from == datetime.datetime(2006, 4, 11, 0, 0, tzinfo=pytz.UTC)
    assert station.states[0].tzinfo_valid_from == 'UTC'
    assert station.states[0].valid_until == datetime.datetime(2021, 5, 7, 9, 0, tzinfo=pytz.UTC)
    assert station.states[0].tzinfo_valid_until == 'UTC'
    assert station.states[1].code == MeteocatStateCategory.DISMANTLED
    assert station.states[1].valid_from == datetime.datetime(2021, 5, 7, 9, 0, tzinfo=pytz.UTC)
    assert station.states[1].tzinfo_valid_from == 'UTC'
    assert station.states[1].valid_until is None
    assert station.states[1].tzinfo_valid_until is None
    assert station.x_4326 == 1.79429
    assert station.y_4326 == 41.43386
    assert station.geometry_4326 == Point(1.79429, 41.43386)
    assert station.x_4326 == 1.79429
    assert station.y_4326 == 41.43386
    assert station.geometry_4326 == Point(1.79429, 41.43386)

