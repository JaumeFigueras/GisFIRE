#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime

import requests
import json
from requests.exceptions import RequestException
from requests.exceptions import HTTPError

from src.json_decoders.no_none_in_list import NoNoneInList
from src.exceptions.status_code_error import StatusCodeError
from src.data_model.request import Request
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable

from typing import List
from typing import Union
from typing import Optional
from typing import Dict

TIMEOUT = 5
RETRIES = 3

XDDE = "https://api.meteo.cat/xdde/v1/catalunya/{0:02d}/{1:02d}/{2:02d}/{3:02d}"
XEMA_STATIONS = "https://api.meteo.cat/xema/v1/estacions/metadades"
XEMA_VARIABLES_MESURADES = "https://api.meteo.cat/xema/v1/variables/mesurades/metadades"
XEMA_VARIABLES_AUXILIARS = "https://api.meteo.cat/xema/v1/variables/auxiliars/metadades"
XEMA_VARIABLES_MULTIVARIABLE = "https://api.meteo.cat/xema/v1/variables/cmv/metadades"
XEMA_STATION_VARIABLES_MESURADES = "https://api.meteo.cat/xema/v1/estacions/{0:}/variables/mesurades/metadades"
XEMA_STATION_VARIABLES_AUXILIARS = "https://api.meteo.cat/xema/v1/estacions/{0:}/variables/auxiliars/metadades"
XEMA_STATION_VARIABLES_MULTIVARIABLE = "https://api.meteo.cat/xema/v1/estacions/{0:}/variables/cmv/metadades"


def get_from_api(api_url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> requests.Response:
    """
    Gets the data returned by the FMP API call. Uses the default time-out time and retries (in case of error in the
    communications).

    :return: JSON metadata obtained from the API
    :rtype: requests.Response
    """
    retries: int = 0
    response: Union[requests.Response, None] = None
    xcpt: Union[Exception, None] = None

    while retries != RETRIES:
        try:
            response = requests.get(api_url, timeout=TIMEOUT, params=params, headers=headers)
            break
        except (RequestException, HTTPError) as e:
            retries += 1
            xcpt = e

    if retries == RETRIES:
        raise xcpt
    else:
        return response


def get_lightning_request_equivalent(date: datetime.datetime) -> Request:
    """
    Retrieves the request object involved in a real request of the XDDE network in the Meteo.cat

    :param date: The date from the data is requested
    :type date: datetime.datetime
    """
    req: Request = Request(uri=XDDE.format(date.year, date.month, date.day, date.hour), request_result=200, data_provider_name='Meteo.cat')
    return req


def get_weather_stations_list(api_key: str) -> List[MeteocatWeatherStation]:
    """
    TODO:
    """
    try:
        headers = {
            'X-Api-Key': api_key,
        }
        response = get_from_api(XEMA_STATIONS, headers=headers)
        if response.ok:
            values = json.loads(response.text, cls=NoNoneInList,
                                object_hook=MeteocatWeatherStation.object_hook_meteocat_api)
            return values
        else:
            raise StatusCodeError(response.status_code, response.text)
    except Exception as xcpt:
        raise xcpt


def get_variables_list(api_key: str) -> List[MeteocatVariable]:
    try:
        headers = {
            'X-Api-Key': api_key,
        }
        values: List[MeteocatVariable] = list()
        for url in [XEMA_VARIABLES_MESURADES, XEMA_VARIABLES_AUXILIARS, XEMA_VARIABLES_MULTIVARIABLE]:
            response = get_from_api(url, headers=headers)
            if response.ok:
                values += json.loads(response.text, cls=NoNoneInList,
                                     object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
            else:
                raise StatusCodeError(response.status_code, response.text)
        return values
    except Exception as xcpt:
        raise xcpt


def get_station_variables_list(api_key: str, station_name: str) -> List[MeteocatVariable]:
    """

    :param api_key:
    :param station_name:
    :return:
    """
    try:
        headers = {
            'X-Api-Key': api_key,
        }
        values: List[MeteocatVariable] = list()
        for url in [XEMA_STATION_VARIABLES_MESURADES, XEMA_STATION_VARIABLES_AUXILIARS, XEMA_STATION_VARIABLES_MULTIVARIABLE]:
            response = get_from_api(url.format(station_name), headers=headers)
            if response.ok:
                values += json.loads(response.text, cls=NoNoneInList,
                                     object_hook=MeteocatVariable.object_hook_variables_of_station_meteocat_api)
            else:
                raise StatusCodeError(response.status_code, response.text)
        return values
    except Exception as xcpt:
        raise xcpt
