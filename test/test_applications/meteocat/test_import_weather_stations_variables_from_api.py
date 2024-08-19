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
from src.meteocat.data_model.variable import MeteocatVariable
from src.data_model.data_provider import DataProvider
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_MESURADES
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_AUXILIARS
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_MULTIVARIABLE

from src.meteocat.remote_api.meteocat_api import XEMA_STATIONS

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_weather_stations
from test.fixtures.database.database import populate_meteocat_variables

from src.applications.meteocat.import_weather_stations_variables_from_api import main

from typing import List
from typing import Union
from typing import Dict


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_auxiliars', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_multivariable', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_main_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                 meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                 meteocat_variables_list: Union[List[MeteocatVariable]],
                 meteocat_api_station_variables_mesurades: Dict[str, str],
                 meteocat_api_station_variables_auxiliars: Dict[str, str],
                 meteocat_api_station_variables_multivariable: Dict[str, str]) -> None:
    """
    Tests the creation of the variable status and time bases for the Meteo.cat data provider.

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param data_provider_list: List of data providers to include in the database
    :type data_provider_list: List[DataProvider]
    :param meteocat_weather_station_list: List of weather stations to include in the database
    :type meteocat_weather_station_list: List[MeteocatWeatherStation]
    :param meteocat_variables_list: List of the variables for the selected weather stations
    :type meteocat_variables_list: List[MeteocatVariable]
    :param meteocat_api_station_variables_mesurades: Response of the Meteo.cat API call querying the measured variables
    of a weather station
    :type meteocat_api_station_variables_mesurades: Dict[str, str]
    :param meteocat_api_station_variables_auxiliars: Response of the Meteo.cat API call querying the auxiliary variables
    of a weather station
    :type meteocat_api_station_variables_auxiliars: Dict[str, str]
    :param meteocat_api_station_variables_multivariable: Response of the Meteo.cat API call querying the calculated
    multivariable data of the weather station
    :type meteocat_api_station_variables_multivariable: Dict[str, str]
    :return: None
    """
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler],
                        encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
    populate_meteocat_variables(db_session, meteocat_variables_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 0
    # Test function
    with requests_mock.Mocker() as rm:
        for url, response in [
            (XEMA_STATION_VARIABLES_MESURADES.format('CA'), meteocat_api_station_variables_mesurades['CA']),
            (XEMA_STATION_VARIABLES_AUXILIARS.format('CA'), meteocat_api_station_variables_auxiliars['CA']),
            (XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA'), meteocat_api_station_variables_multivariable['CA'])
        ]:
            rm.get(url, text=response, status_code=200)
        main(db_session, '1234', logger)
        # Assert the results
    assert db_session.execute(select(func.count(MeteocatVariableState.meteocat_variable_id))).scalar_one() == 50
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.meteocat_variable_id))).scalar_one() == 24


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_auxiliars', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_multivariable', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_main_02(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                 meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                 meteocat_variables_list: Union[List[MeteocatVariable]],
                 meteocat_api_station_variables_mesurades: Dict[str, str],
                 meteocat_api_station_variables_auxiliars: Dict[str, str],
                 meteocat_api_station_variables_multivariable: Dict[str, str]) -> None:
    """
    Tests the creation of the variable status and time bases for the Z8 weather station. Z8 station has data but the API
    call fails, so the code has an if to deal with this error and does nothing if Z8 is found. Another scrip adds
    manually the correct data for Z8 (updates_from_api_mail)

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param data_provider_list: List of data providers to include in the database
    :type data_provider_list: List[DataProvider]
    :param meteocat_weather_station_list: List of weather stations to include in the database
    :type meteocat_weather_station_list: List[MeteocatWeatherStation]
    :param meteocat_variables_list: List of the variables for the selected weather stations
    :type meteocat_variables_list: List[MeteocatVariable]
    :param meteocat_api_station_variables_mesurades: Response of the Meteo.cat API call querying the measured variables
    of a weather station
    :type meteocat_api_station_variables_mesurades: Dict[str, str]
    :param meteocat_api_station_variables_auxiliars: Response of the Meteo.cat API call querying the auxiliary variables
    of a weather station
    :type meteocat_api_station_variables_auxiliars: Dict[str, str]
    :param meteocat_api_station_variables_multivariable: Response of the Meteo.cat API call querying the calculated
    multivariable data of the weather station
    :type meteocat_api_station_variables_multivariable: Dict[str, str]
    :return: None
    """
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler],
                        encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    if len(meteocat_weather_station_list) != 1:
        assert False
    meteocat_weather_station_list[0].code = 'Z8'
    populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
    populate_meteocat_variables(db_session, meteocat_variables_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 0
    # Test function
    with requests_mock.Mocker() as rm:
        for url, response in [
            (XEMA_STATION_VARIABLES_MESURADES.format('Z8'), meteocat_api_station_variables_mesurades['CA']),
            (XEMA_STATION_VARIABLES_AUXILIARS.format('Z8'), meteocat_api_station_variables_auxiliars['CA']),
            (XEMA_STATION_VARIABLES_MULTIVARIABLE.format('Z8'), meteocat_api_station_variables_multivariable['CA'])
        ]:
            rm.get(url, text=response, status_code=200)
        main(db_session, '1234', logger)
        # Assert the results
    assert db_session.execute(select(func.count(MeteocatVariableState.meteocat_variable_id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.meteocat_variable_id))).scalar_one() == 0



