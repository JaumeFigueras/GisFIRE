#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from src.data_model.data_provider import DataProvider

from typing import List
from typing import Union


@pytest.fixture(scope='function')
def data_provider_list(request) -> Union[List[DataProvider], None]:
    """
    Provides the list of data providers to insert in the database requested in the request

    :param request:
    :return:
    """
    if hasattr(request, 'param'):
        names: List[str] = request.param['data_providers'] if 'data_providers' in request.param else None
        if names is None:
            return None
        data_providers: List[DataProvider] = list()
        for name in names:
            if name == 'Meteo.cat':
                data_provider = DataProvider('Meteo.cat', 'Servei Meteorològic de Catalunya', 'https://www.meteo.cat/')
            elif name == 'Bombers.cat':
                data_provider = DataProvider('Bombers.cat', 'Bombers de la Generalitat de Catalunya', 'https://interior.gencat.cat/ca/arees_dactuacio/bombers')
            else:
                data_provider = DataProvider(name, 'unknown','https://unknown.com')
            data_providers.append(data_provider)
        return data_providers
    else:
        return None
