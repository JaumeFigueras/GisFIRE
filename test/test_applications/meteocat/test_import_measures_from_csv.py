#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime

import pytest
import _csv
import logging

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError


from src.data_model.data_provider import DataProvider
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_weather_stations
from test.fixtures.database.database import populate_meteocat_variables
from test.fixtures.database.database import populate_meteocat_variable_states
from test.fixtures.database.database import populate_meteocat_variable_time_bases

from src.applications.meteocat.import_lightnings_from_csv import process_lightnings
from src.applications.meteocat.import_lightnings_from_csv import process_requests

from typing import List
from typing import Union
from typing import Dict


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
    {'year': 2013},
    {'year': 2017},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('meteocat_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def no_test_process_measures_01(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             meteocat_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             meteocat_variables_list: Union[List[MeteocatVariable], None],
                             meteocat_variable_states_list: Union[List[MeteocatVariableState], None],
                             meteocat_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatAssociationStationVariableState.variable_id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatAssociationStationVariableTimeBase.variable_id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    populate_meteocat_weather_stations(db_session, meteocat_weather_station_list)
    populate_meteocat_variables(db_session, meteocat_variables_list)
    populate_meteocat_variable_states(db_session, meteocat_variable_states_list)
    populate_meteocat_variable_time_bases(db_session, meteocat_variable_time_bases_list)
    populate_meteocat_assoc_states(db_session, meteocat_assoc_states_list)
    populate_meteocat_assoc_time_bases(db_session, meteocat_assoc_time_bases_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 240
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    assert db_session.execute(select(func.count(MeteocatAssociationStationVariableState.variable_id))).scalar_one() == 0
    assert db_session.execute(select(func.count(MeteocatAssociationStationVariableTimeBase.variable_id))).scalar_one() == 0
    # Test function

