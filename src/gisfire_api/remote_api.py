#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime

import requests
import json

from requests.exceptions import RequestException
from requests.exceptions import HTTPError
from base64 import b64encode

from src.json_decoders.no_none_in_list import NoNoneInList
from src.exceptions.status_code_error import StatusCodeError
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.meteocat.data_model.lightning import MeteocatLightning

from typing import List
from typing import Union
from typing import Optional
from typing import Dict

TIMEOUT = 5
RETRIES = 3

IGNITIONS = "https://gisfire.petprojects.tech/api/v2/ignition"
LIGHTNINGS = "https://gisfire.petprojects.tech/api/v2/lightning"


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


def get_bomberscat_ignition_list(username: str, token: str, from_date: Optional[datetime.datetime] = None,
                                 to_date: Optional[datetime.datetime] = None, order: Optional[str] = None) -> List[BomberscatWildfireIgnition]:
    """
    Gets the list of wildfire ignitions from Bombers.cat according to the date filters and order provided

    :param username: Username to access the GisFIRE API
    :type username: str
    :param token: Token belonging to the user to access the GisFIRE API
    :type token: str
    :param from_date: Date to pick the ignitions from
    :type from_date: datetime.datetime
    :param to_date: Date to pick the ignitions until
    :type to_date: datetime.datetime
    :param order: Order string. Possible values are: date, date:asc or date:desc
    :type order: str
    :return: The list of ignitions provided by the GisFIRE API
    :rtype: List[BomberscatWildfireIgnition]
    """
    try:
        headers = {'Authorization': 'Basic {}'.format(b64encode(f"{username}:{token}".encode('utf-8')).decode("ascii"))}
        params = {'data_provider': 'Bombers.cat'}
        if from_date is not None:
            params['from'] = from_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        if to_date is not None:
            params['to'] = to_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        if order is not None:
            params['order'] = order
        response = get_from_api(IGNITIONS, headers=headers, params=params)
        if response.ok:
            values = json.loads(response.text, cls=NoNoneInList,
                                object_hook=BomberscatWildfireIgnition.object_hook_gisfire_api)
            return values
        else:
            raise StatusCodeError(response.status_code, response.text)
    except Exception as xcpt:
        raise xcpt


def get_meteocat_lightnings_list(username: str, token: str, from_date: Optional[datetime.datetime] = None,
                                 to_date: Optional[datetime.datetime] = None, order: Optional[str] = None,
                                 x: Optional[float] = None, y: Optional[float] = None, epsg: Optional[int] = None,
                                 radius: Optional[float] = None) -> Union[List[MeteocatLightning], List[Dict[str, Union[MeteocatLightning, float]]]]:
    """
    Gets the list of lightnings from Meteo.cat according to the date filters, order, location and radius provided

    :param username: Username to access the GisFIRE API
    :type username: str
    :param token: Token belonging to the user to access the GisFIRE API
    :type token: str
    :param from_date: Date to pick the ignitions from
    :type from_date: datetime.datetime
    :param to_date: Date to pick the ignitions until
    :type to_date: datetime.datetime
    :param order: Order string. Possible values are: date, date:asc or date:desc
    :type order: str
    :param x:
    :param y:
    :param epsg:
    :param radius:
    :return: The list of ignitions provided by the GisFIRE API
    :rtype: List[BomberscatWildfireIgnition]
    """
    try:
        headers = {'Authorization': 'Basic {}'.format(b64encode(f"{username}:{token}".encode('utf-8')).decode("ascii"))}
        params = {'data_provider': 'Meteo.cat'}
        if from_date is not None:
            params['from'] = from_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        if to_date is not None:
            params['to'] = to_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        if order is not None:
            params['order'] = order
        if x is not None:
            params['x'] = x
        if y is not None:
            params['y'] = y
        if epsg is not None:
            params['epsg'] = epsg
        if radius is not None:
            params['radius'] = radius
        response = get_from_api(LIGHTNINGS, headers=headers, params=params)
        if response.ok:
            values = json.loads(response.text, cls=NoNoneInList, object_hook=MeteocatLightning.object_hook_gisfire_api)
            return values
        else:
            raise StatusCodeError(response.status_code, response.text)
    except Exception as xcpt:
        raise xcpt
