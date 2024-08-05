#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.weather_station import MeteocatWeatherStation

from typing import List
from typing import Union


@pytest.fixture(scope='function')
def meteocat_weather_station_list(request, meteocat_api_weather_stations: str) -> Union[List[MeteocatWeatherStation], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_api_weather_stations:
    :return:
    """
    if hasattr(request, 'param'):
        codes: List[str] = request.param['weather_stations'] if 'weather_stations' in request.param else None
        if codes is not None:
            stations: List[MeteocatWeatherStation] = json.loads(meteocat_api_weather_stations, cls=NoNoneInList,
                                                                object_hook=MeteocatWeatherStation.object_hook_meteocat_api)
            stations_dict = {station.code: station for station in stations}
            weather_stations: List[MeteocatWeatherStation] = list()
            for code in codes:
                weather_stations.append(stations_dict[code])
            for station in weather_stations:
                station.data_provider_name = "Meteo.cat"
            return weather_stations
    return None
