#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.variable import MeteocatVariable

from typing import List
from typing import Union


@pytest.fixture(scope='function')
def meteocat_variables_list(request, meteocat_api_variables_mesurades: str, meteocat_api_variables_auxiliars: str,
                            meteocat_api_variables_multivariable: str) -> Union[List[MeteocatVariable], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :param meteocat_api_variables_mesurades:
    :param meteocat_api_variables_auxiliars:
    :param meteocat_api_variables_multivariable:
    :return:
    """
    variables_1: List[MeteocatVariable] = json.loads(meteocat_api_variables_mesurades, cls=NoNoneInList,
                                                     object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    variables_2: List[MeteocatVariable] = json.loads(meteocat_api_variables_auxiliars, cls=NoNoneInList,
                                                     object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    variables_3: List[MeteocatVariable] = json.loads(meteocat_api_variables_multivariable, cls=NoNoneInList,
                                                     object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    variables = variables_1 + variables_2 + variables_3
    for variable in variables:
        variable.data_provider_name = "Meteo.cat"
    return variables
