#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import requests
import requests_mock
import datetime

from requests.exceptions import HTTPError
from requests.exceptions import ConnectTimeout
from requests.exceptions import RequestException

from src.meteocat.remote_api.meteocat_api import XEMA_STATIONS
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_MESURADES
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_AUXILIARS
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_MULTIVARIABLE
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_MESURADES
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_AUXILIARS
from src.meteocat.remote_api.meteocat_api import XEMA_STATION_VARIABLES_MULTIVARIABLE
from src.meteocat.remote_api.meteocat_api import get_weather_stations_list
from src.meteocat.remote_api.meteocat_api import get_variables_list
from src.meteocat.remote_api.meteocat_api import get_station_variables_list
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable
from src.exceptions.status_code_error import StatusCodeError

from typing import List
from typing import Dict


def test_get_weather_station_list_01() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Error
    """
    with requests_mock.Mocker() as rm:
        url = XEMA_STATIONS
        rm.get(url, exc=HTTPError)
        with pytest.raises(RequestException):
            _ = get_weather_stations_list('1234')


def test_get_weather_station_list_02() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        url = XEMA_STATIONS
        rm.get(url, exc=ConnectTimeout)
        with pytest.raises(RequestException):
            _ = get_weather_stations_list('1234')


def test_get_weather_station_list_03() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        url = XEMA_STATIONS
        rm.get(url, text='', status_code=404)
        with pytest.raises(StatusCodeError):
            _ = get_weather_stations_list('1234')


def test_get_weather_station_list_04(meteocat_api_weather_stations: str) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list
    """
    with requests_mock.Mocker() as rm:
        url = XEMA_STATIONS
        rm.get(url, text=meteocat_api_weather_stations, status_code=200)
        elements: List[MeteocatWeatherStation] = get_weather_stations_list('1234')
        assert len(elements) == 240
        for element in elements:
            assert isinstance(element, MeteocatWeatherStation)


def test_get_variable_list_01() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Error
    """
    with requests_mock.Mocker() as rm:
        for url in [XEMA_VARIABLES_MESURADES, XEMA_VARIABLES_AUXILIARS, XEMA_VARIABLES_MULTIVARIABLE]:
            rm.get(url, exc=HTTPError)
        with pytest.raises(RequestException):
            _ = get_variables_list('1234')


def test_get_variable_list_02() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        for url in [XEMA_VARIABLES_MESURADES, XEMA_VARIABLES_AUXILIARS, XEMA_VARIABLES_MULTIVARIABLE]:
            rm.get(url, exc=ConnectTimeout)
        with pytest.raises(RequestException):
            _ = get_variables_list('1234')


def test_get_variable_list_03(meteocat_api_weather_stations: str) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list
    """
    with requests_mock.Mocker() as rm:
        for url in [XEMA_VARIABLES_MESURADES, XEMA_VARIABLES_AUXILIARS, XEMA_VARIABLES_MULTIVARIABLE]:
            rm.get(url, text='', status_code=404)
        with pytest.raises(StatusCodeError):
            _ = get_variables_list('1234')


def test_get_variable_list_04(meteocat_api_variables_mesurades: str, meteocat_api_variables_auxiliars: str,
                              meteocat_api_variables_multivariable: str) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        for url, response in [(XEMA_VARIABLES_MESURADES, meteocat_api_variables_mesurades),
                              (XEMA_VARIABLES_AUXILIARS, meteocat_api_variables_auxiliars),
                              (XEMA_VARIABLES_MULTIVARIABLE, meteocat_api_variables_multivariable)]:
            rm.get(url, text=response, status_code=200)
        elements: List[MeteocatVariable] = get_variables_list('1234')
        assert len(elements) == 90
        for element in elements:
            assert isinstance(element, MeteocatVariable)


def test_get_station_variable_list_01() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Error
    """
    with requests_mock.Mocker() as rm:
        for url in [XEMA_STATION_VARIABLES_MESURADES.format('CA'),
                    XEMA_STATION_VARIABLES_AUXILIARS.format('CA'),
                    XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA')]:
            rm.get(url, exc=HTTPError)
        with pytest.raises(RequestException):
            _ = get_station_variables_list('1234', 'CA')


def test_get_station_variable_list_02() -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        for url in [XEMA_STATION_VARIABLES_MESURADES.format('CA'),
                    XEMA_STATION_VARIABLES_AUXILIARS.format('CA'),
                    XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA')]:
            rm.get(url, exc=ConnectTimeout)
        with pytest.raises(RequestException):
            _ = get_station_variables_list('1234', 'CA')


@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_get_station_variable_list_03(meteocat_api_station_variables_mesurades: Dict[str, str]) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list
    """
    with requests_mock.Mocker() as rm:
        rm.get(XEMA_STATION_VARIABLES_MESURADES.format('CA'), text=meteocat_api_station_variables_mesurades['CA'], status_code=200)
        rm.get(XEMA_STATION_VARIABLES_AUXILIARS.format('CA'), text="", status_code=400)
        rm.get(XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA'), text="", status_code=404)
        with pytest.raises(StatusCodeError):
            _ = get_station_variables_list('1234', 'CA')


@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_auxiliars', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.parametrize('meteocat_api_station_variables_multivariable', [
    {'weather_stations': ['CA']},
], indirect=True)
@pytest.mark.freeze_time('2024-08-01 12:00:00')
def test_get_station_variable_list_04(meteocat_api_station_variables_mesurades: Dict[str, str],
                                      meteocat_api_station_variables_auxiliars: Dict[str, str],
                                      meteocat_api_station_variables_multivariable: Dict[str, str]) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        for url, response in [
            (XEMA_STATION_VARIABLES_MESURADES.format('CA'), meteocat_api_station_variables_mesurades['CA']),
            (XEMA_STATION_VARIABLES_AUXILIARS.format('CA'), meteocat_api_station_variables_auxiliars['CA']),
            (XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA'), meteocat_api_station_variables_multivariable['CA'])
        ]:
            rm.get(url, text=response, status_code=200)
        variables: List[MeteocatVariable] = get_station_variables_list('1234', 'CA')
        assert len(variables) == 24
        for variable in variables:
            assert isinstance(variable, MeteocatVariable)


@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [
    {'weather_stations': ['CA']},
], indirect=True)
def test_get_station_variable_list_05(meteocat_api_station_variables_mesurades: Dict[str, str]) -> None:
    """
    Tests the get_exchanges_from_symbol_list method that retrieves the exchange list assuming an HTTP Connection
    Timeout Error
    """
    with requests_mock.Mocker() as rm:
        rm.get(XEMA_STATION_VARIABLES_MESURADES.format('CA'), text=meteocat_api_station_variables_mesurades['CA'], status_code=200)
        rm.get(XEMA_STATION_VARIABLES_AUXILIARS.format('CA'), text="", status_code=400)
        rm.get(XEMA_STATION_VARIABLES_MULTIVARIABLE.format('CA'), text="", status_code=400)
        variables: List[MeteocatVariable] = get_station_variables_list('1234', 'CA')
        assert len(variables) == 21
        for variable in variables:
            assert isinstance(variable, MeteocatVariable)

