#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import os
import json

from pathlib import Path

from typing import Dict
from typing import Any


@pytest.fixture(scope='function')
def meteocat_api_weather_stations() -> str:
    """
    Reads the JSON file of weather stations from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/estacions/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "estacions.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_api_weather_station_states() -> str:
    """
    Reads the JSON file of weather stations from the meteocat API, extracts weather stations states and returns it as
    string.

    https://api.meteo.cat/xema/v1/estacions/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "estacions.json"))
    with open(json_file, 'r') as file:
        weather_stations = json.load(file)
        lst = list()
        for weather_station in weather_stations:
            states = weather_station['estats']
            lst.append(states)
        return json.dumps(lst)


@pytest.fixture(scope='function')
def meteocat_api_variables_mesurades() -> str:
    """
    Reads the JSON file of measured variables from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/variables/mesurades/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_mesurades.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_api_variables_auxiliars() -> str:
    """
    Reads the JSON file of measured variables from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/variables/auxiliars/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_auxiliars.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_api_variables_multivariable() -> str:
    """
    Reads the JSON file of measured variables from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/variables/auxiliars/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_multivariable.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_api_station_variables_mesurades(request: pytest.FixtureRequest) -> Dict[str, str]:
    if hasattr(request, 'param'):
        stations = request.param['weather_stations'] if 'weather_stations' in request.param else []
        current_dir: Path = Path(__file__).parent
        dct = dict()
        for station in stations:
            json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_mesurades_{0:}.json".format(station)))
            with open(json_file, 'r') as file:
                data = file.read()
                dct[station] = data
        return dct
    return dict()


@pytest.fixture(scope='function')
def meteocat_api_station_variables_auxiliars(request: pytest.FixtureRequest) -> Dict[str, str]:
    if hasattr(request, 'param'):
        stations = request.param['weather_stations'] if 'weather_stations' in request.param else []
        current_dir: Path = Path(__file__).parent
        dct = dict()
        for station in stations:
            json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_auxiliars_{0:}.json".format(station)))
            with open(json_file, 'r') as file:
                data = file.read()
                dct[station] = data
        return dct
    return dict()


@pytest.fixture(scope='function')
def meteocat_api_station_variables_multivariable(request: pytest.FixtureRequest) -> Dict[str, str]:
    if hasattr(request, 'param'):
        stations = request.param['weather_stations'] if 'weather_stations' in request.param else []
        current_dir: Path = Path(__file__).parent
        dct = dict()
        for station in stations:
            json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "variables_multivariable_{0:}.json".format(station)))
            with open(json_file, 'r') as file:
                data = file.read()
                dct[station] = data
        print(dct)
        return dct
    return dict()
