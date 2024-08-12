#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import os
import json

from pathlib import Path

from typing import Dict
from typing import Any


@pytest.fixture(scope='function')
def gisfire_api_weather_stations() -> str:
    """
    Reads the JSON file of weather stations from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/estacions/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_weather_stations.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def gisfire_api_variables() -> str:
    """
    Reads the JSON file of weather stations from the meteocat API, extracts weather stations states and returns it as
    string.

    https://api.meteo.cat/xema/v1/estacions/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_variables.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def gisfire_api_variable_states() -> str:
    """
    Reads the JSON file of measured variables from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/variables/mesurades/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_variable_states.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def gisfire_api_variable_time_bases() -> str:
    """
    Reads the JSON file of measured variables from the meteocat API and returns it as string.

    https://api.meteo.cat/xema/v1/variables/auxiliars/metadades
    """
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_variable_time_bases.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data

