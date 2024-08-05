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
from shapely.geometry import Point

from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableCategory
from src.data_model.data_provider import DataProvider
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_MESURADES
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_AUXILIARS
from src.meteocat.remote_api.meteocat_api import XEMA_VARIABLES_MULTIVARIABLE

from test.fixtures.database.database import populate_data_providers

from src.applications.meteocat.import_variables_from_api import main

from typing import List
from typing import Union


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_main_01(db_session: Session, meteocat_api_variables_mesurades: str, meteocat_api_variables_auxiliars: str,
                 meteocat_api_variables_multivariable: str,
                 data_provider_list: Union[List[DataProvider], None]) -> None:
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
    # Test function
    with requests_mock.Mocker() as rm:
        for url, response in [(XEMA_VARIABLES_MESURADES, meteocat_api_variables_mesurades),
                              (XEMA_VARIABLES_AUXILIARS, meteocat_api_variables_auxiliars),
                              (XEMA_VARIABLES_MULTIVARIABLE, meteocat_api_variables_multivariable)]:
            rm.get(url, text=response, status_code=200)
        main(db_session, '1234', logger)
        # Assert the results
        assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    variable: MeteocatVariable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 2)).unique().scalar_one()
    assert variable.code == 2
    assert variable.name == "Pressió atmosfèrica mínima"
    assert variable.unit == "hPa"
    assert variable.category == MeteocatVariableCategory.DAT
    assert variable.decimal_positions == 1
    variable: MeteocatVariable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 901)).unique().scalar_one()
    assert variable.code == 901
    assert variable.name == "Precipitació acumulada en 1 min"
    assert variable.unit == "mm"
    assert variable.category == MeteocatVariableCategory.AUX
    assert variable.decimal_positions == 1
    variable: MeteocatVariable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 6006)).unique().scalar_one()
    assert variable.code == 6006
    assert variable.name == "Evapotranspiració de referència"
    assert variable.unit == "mm"
    assert variable.category == MeteocatVariableCategory.CMV
    assert variable.decimal_positions == 2
