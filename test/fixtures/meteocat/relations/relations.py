#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import os
import json

from pathlib import Path

from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableState
from src.meteocat.data_model.variable_station_relations import MeteocatAssociationStationVariableTimeBase
from src.json_decoders.no_none_in_list import NoNoneInList

from typing import Union
from typing import List


@pytest.fixture(scope='function')
def meteocat_variable_state() -> str:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_states.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_variable_states_list(request, meteocat_variable_state: str) -> Union[List[MeteocatVariableState], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_variable_state:
    :return:
    """
    states: List[MeteocatVariableState] = json.loads(meteocat_variable_state, cls=NoNoneInList,
                                                     object_hook=MeteocatVariableState.object_hook_gisfire_api)
    return states


@pytest.fixture(scope='function')
def meteocat_variable_time_base() -> str:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_time_bases.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_variable_time_bases_list(request, meteocat_variable_time_base: str) -> Union[List[MeteocatVariableTimeBase], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_variable_time_base:
    :return:
    """
    time_bases: List[MeteocatVariableTimeBase] = json.loads(meteocat_variable_time_base, cls=NoNoneInList,
                                                            object_hook=MeteocatVariableTimeBase.object_hook_gisfire_api)
    return time_bases


@pytest.fixture(scope='function')
def meteocat_assoc_state() -> str:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_assoc_states.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_assoc_states_list(request, meteocat_assoc_state: str) -> Union[List[MeteocatAssociationStationVariableState], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_assoc_state:
    :return:
    """
    states: List[MeteocatAssociationStationVariableState] = json.loads(meteocat_assoc_state, cls=NoNoneInList,
                                                                       object_hook=MeteocatAssociationStationVariableState.object_hook_gisfire_api)
    return states


@pytest.fixture(scope='function')
def meteocat_assoc_time_base() -> str:
    current_dir: Path = Path(__file__).parent
    json_file: str = os.path.join(str(current_dir), os.path.join("jsons", "meteocat_assoc_time_bases.json"))
    with open(json_file, 'r') as file:
        data = file.read()
        return data


@pytest.fixture(scope='function')
def meteocat_assoc_time_bases_list(request, meteocat_assoc_time_base: str) -> Union[List[MeteocatAssociationStationVariableTimeBase], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_assoc_time_base:
    :return:
    """
    time_bases: List[MeteocatAssociationStationVariableTimeBase] = json.loads(meteocat_assoc_time_base,
                                                                              cls=NoNoneInList,
                                                                              object_hook=MeteocatAssociationStationVariableTimeBase.object_hook_gisfire_api)
    return time_bases

