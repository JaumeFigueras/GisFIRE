#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime

import pytest
import _csv
import logging

import pytz
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError


from src.data_model.data_provider import DataProvider
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableStateCategory
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory
from src.meteocat.data_model.measure import MeteocatMeasure

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_weather_stations
from test.fixtures.database.database import populate_meteocat_variables
from test.fixtures.database.database import populate_meteocat_variable_states
from test.fixtures.database.database import populate_meteocat_variable_time_bases

from src.applications.meteocat.import_measures_from_csv import process_measures

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
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_01(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests all is OK

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Test function
    process_measures(db_session, meteocat_measures_csv_reader, logger)
    assert db_session.execute(select(func.count(MeteocatMeasure.id))).scalar_one() == 999


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_02(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests missing station

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    dd = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'DD')).unique().scalar_one()
    dd.code = 'DDD'
    db_session.commit()
    # Test function
    with pytest.raises(ValueError):
        process_measures(db_session, meteocat_measures_csv_reader, logger)


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_03(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests missing variable

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    v50 = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 50)).unique().scalar_one()
    v50.code = 551
    db_session.commit()
    # Test function
    with pytest.raises(ValueError):
        process_measures(db_session, meteocat_measures_csv_reader, logger)


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_04(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests missing variable states

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    dd = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'DD')).unique().scalar_one()
    v50 = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 50)).unique().scalar_one()
    db_session.execute(delete(MeteocatVariableState).where(MeteocatVariableState.meteocat_weather_station_id == dd.id).where(MeteocatVariableState.meteocat_variable_id == v50.id))
    db_session.commit()
    # Test function
    with pytest.raises(ValueError):
        process_measures(db_session, meteocat_measures_csv_reader, logger)


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_05(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests missing variable time bases

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    dd = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'DD')).unique().scalar_one()
    v50 = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 50)).unique().scalar_one()
    db_session.execute(delete(MeteocatVariableTimeBase).where(MeteocatVariableTimeBase.meteocat_weather_station_id == dd.id).where(MeteocatVariableTimeBase.meteocat_variable_id == v50.id))
    db_session.commit()
    # Test function
    with pytest.raises(ValueError):
        process_measures(db_session, meteocat_measures_csv_reader, logger)


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_06(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             ) -> None:
    """
    Tests measure out of validity in variable state

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    dd = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'DD')).unique().scalar_one()
    v50 = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 50)).unique().scalar_one()
    states = db_session.execute(select(MeteocatVariableState).where(MeteocatVariableState.meteocat_weather_station_id == dd.id).where(MeteocatVariableState.meteocat_variable_id == v50.id)).scalars()
    for state in states:
        if state.code == MeteocatVariableStateCategory.ACTIVE:
            state.valid_from = datetime.datetime(2023, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
            state.valid_until = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
    db_session.commit()
    # Test function
    with pytest.raises(ValueError):
        process_measures(db_session, meteocat_measures_csv_reader, logger)


@pytest.mark.parametrize('meteocat_measures_csv_reader', [
    {'year': 2009},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
@pytest.mark.parametrize('gisfire_weather_station_list', [
    {'weather_stations': ['all']},
], indirect=True)
def test_process_measures_07(db_session: Session, meteocat_measures_csv_reader: Union[_csv.reader, None],
                             data_provider_list: Union[List[DataProvider], None],
                             gisfire_weather_station_list: Union[List[MeteocatWeatherStation], None],
                             gisfire_variables_list: Union[List[MeteocatVariable], None],
                             gisfire_variable_states_list: Union[List[MeteocatVariableState], None],
                             gisfire_variable_time_bases_list: Union[List[MeteocatVariableTimeBase], None],
                             caplog) -> None:
    """
    Tests missing time base type in variable measure

    :param db_session:
    :param meteocat_measures_csv_reader:
    :param data_provider_list:
    :param gisfire_weather_station_list:
    :param gisfire_variables_list:
    :param gisfire_variable_states_list:
    :param gisfire_variable_time_bases_list:
    :return:
    """
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
    populate_data_providers(db_session, data_provider_list)
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    populate_meteocat_weather_stations(db_session, gisfire_weather_station_list)
    assert db_session.execute(select(func.count(MeteocatWeatherStation.id))).scalar_one() == 241
    populate_meteocat_variables(db_session, gisfire_variables_list)
    assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
    populate_meteocat_variable_states(db_session, gisfire_variable_states_list)
    assert db_session.execute(select(func.count(MeteocatVariableState.id))).scalar_one() == 9191
    populate_meteocat_variable_time_bases(db_session, gisfire_variable_time_bases_list)
    assert db_session.execute(select(func.count(MeteocatVariableTimeBase.id))).scalar_one() == 12744
    # Remove elements from database to generate errors to test
    dd = db_session.execute(select(MeteocatWeatherStation).where(MeteocatWeatherStation.code == 'DD')).unique().scalar_one()
    v50 = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.code == 50)).unique().scalar_one()
    time_bases = db_session.execute(select(MeteocatVariableTimeBase).where(MeteocatVariableTimeBase.meteocat_weather_station_id == dd.id).where(MeteocatVariableTimeBase.meteocat_variable_id == v50.id)).scalars()
    for time_base in time_bases:
        time_base.code = MeteocatVariableTimeBaseCategory.D5
    db_session.commit()
    # Test function
    process_measures(db_session, meteocat_measures_csv_reader, logger)
    assert len([record for record in caplog.records if record.levelname == 'ERROR']) == 6

