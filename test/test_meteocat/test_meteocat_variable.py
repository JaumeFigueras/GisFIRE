#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import json
import pytest

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.json_decoders.no_none_in_list import NoNoneInList
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableCategory
from src.meteocat.data_model.variable import MeteocatVariableStateCategory
from src.meteocat.data_model.variable import MeteocatVariableTimeBaseCategory
from src.data_model.data_provider import DataProvider

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_variables

from typing import List
from typing import Union

def test_meteocat_variable_01() -> None:
    variable = MeteocatVariable()
    assert variable.name is None
    assert variable.code is None
    assert variable.unit is None
    assert variable.acronym is None
    assert variable.category is None
    assert variable.decimal_positions is None
    variable = MeteocatVariable(name='VAR')
    assert variable.name == 'VAR'
    assert variable.code is None
    assert variable.unit is None
    assert variable.acronym is None
    assert variable.category is None
    assert variable.decimal_positions is None
    variable = MeteocatVariable(code=34)
    assert variable.name is None
    assert variable.code == 34
    assert variable.unit is None
    assert variable.acronym is None
    assert variable.category is None
    assert variable.decimal_positions is None
    variable = MeteocatVariable(unit='unit')
    assert variable.name is None
    assert variable.code is None
    assert variable.unit == 'unit'
    assert variable.acronym is None
    assert variable.category is None
    assert variable.decimal_positions is None
    variable = MeteocatVariable(acronym='ACR')
    assert variable.name is None
    assert variable.code is None
    assert variable.unit is None
    assert variable.acronym == 'ACR'
    assert variable.category is None
    assert variable.decimal_positions is None
    variable = MeteocatVariable(category=MeteocatVariableCategory.DAT)
    assert variable.name is None
    assert variable.code is None
    assert variable.unit is None
    assert variable.acronym is None
    assert variable.category == MeteocatVariableCategory.DAT
    assert variable.decimal_positions is None
    variable = MeteocatVariable(decimal_positions=3)
    assert variable.name is None
    assert variable.code is None
    assert variable.unit is None
    assert variable.acronym is None
    assert variable.category is None
    assert variable.decimal_positions == 3
    variable = MeteocatVariable(name='VAR', code=34, unit='unit', acronym='ACR', category=MeteocatVariableCategory.DAT, decimal_positions=3)
    assert variable.name == 'VAR'
    assert variable.code == 34
    assert variable.unit == 'unit'
    assert variable.acronym == 'ACR'
    assert variable.category == MeteocatVariableCategory.DAT
    assert variable.decimal_positions == 3


def test_variable_iter_01() -> None:
    """
    TODO
    :return:
    """
    variable = MeteocatVariable(name='VAR', code=34, unit='unit', acronym='ACR', category=MeteocatVariableCategory.DAT, decimal_positions=3)
    assert dict(variable) == {
        'id': None,
        'name': 'VAR',
        'code': 34,
        'unit': 'unit',
        'acronym': 'ACR',
        'category': 'DAT',
        'decimal_positions': 3,
        'ts': None,
    }


def test_variable_json_parser_01(meteocat_api_variables_mesurades: str) -> None:
    """
    Tests the METEOCAT API parsing of a variable (variables mesurades)

    :param meteocat_api_variables_mesurades:
    :return:
    """
    variables: List[MeteocatVariable] = json.loads(meteocat_api_variables_mesurades, cls=NoNoneInList,
                                                   object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    assert len(variables) == 87
    for variable in variables:
        assert isinstance(variable, MeteocatVariable)
    variable = variables[0]
    assert variable.name == 'Pressió atmosfèrica màxima'
    assert variable.code == 1
    assert variable.unit == 'hPa'
    assert variable.acronym == 'Px'
    assert variable.category == MeteocatVariableCategory.DAT
    assert variable.decimal_positions == 1
    variable = variables[86]
    assert variable.name == 'Precipitació acumulada prova'
    assert variable.code == 102
    assert variable.unit == 'mm'
    assert variable.acronym == 'PPTac2'
    assert variable.category == MeteocatVariableCategory.DAT
    assert variable.decimal_positions == 1


def test_variable_json_parser_02(meteocat_api_variables_auxiliars: str) -> None:
    """
    Tests the METEOCAT API parsing of a variable (variables auxiliars)

    :param meteocat_api_variables_auxiliars:
    :return:
    """
    variables: List[MeteocatVariable] = json.loads(meteocat_api_variables_auxiliars, cls=NoNoneInList,
                                                   object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    assert len(variables) == 2
    for variable in variables:
        assert isinstance(variable, MeteocatVariable)
    variable = variables[0]
    assert variable.name == 'Precipitació acumulada en 10 min'
    assert variable.code == 900
    assert variable.unit == 'mm'
    assert variable.acronym == 'PPT10min'
    assert variable.category == MeteocatVariableCategory.AUX
    assert variable.decimal_positions == 1
    variable = variables[1]
    assert variable.name == 'Precipitació acumulada en 1 min'
    assert variable.code == 901
    assert variable.unit == 'mm'
    assert variable.acronym == 'PPT1min'
    assert variable.category == MeteocatVariableCategory.AUX
    assert variable.decimal_positions == 1


def test_variable_json_parser_03(meteocat_api_variables_multivariable: str) -> None:
    """
    Tests the METEOCAT API parsing of a variable (variables calculades multivariable)

    :param meteocat_api_variables_multivariable:
    :return:
    """
    variables: List[MeteocatVariable] = json.loads(meteocat_api_variables_multivariable, cls=NoNoneInList,
                                                   object_hook=MeteocatVariable.object_hook_variable_meteocat_api)
    assert len(variables) == 1
    for variable in variables:
        assert isinstance(variable, MeteocatVariable)
    variable = variables[0]
    assert variable.name == 'Evapotranspiració de referència'
    assert variable.code == 6006
    assert variable.unit == 'mm'
    assert variable.acronym == 'ETo'
    assert variable.category == MeteocatVariableCategory.CMV
    assert variable.decimal_positions == 2


@pytest.mark.parametrize('meteocat_api_station_variables_mesurades', [{'weather_stations': ['CA']}], indirect=True)
def test_variable_json_parser_04(meteocat_api_station_variables_mesurades) -> None:
    """
    Tests the METEOCAT API parsing of a variable of a specific station (variables mesurades)

    :param meteocat_api_station_variables_mesurades:
    :return:
    """
    for key, data in meteocat_api_station_variables_mesurades.items():
        variables: List[MeteocatVariable] = json.loads(data, cls=NoNoneInList,
                                                       object_hook=MeteocatVariable.object_hook_variables_of_station_meteocat_api)
        assert len(variables) == 21
        for variable in variables:
            assert isinstance(variable, MeteocatVariable)
        variable = variables[0]
        assert variable.name == 'Pressió atmosfèrica màxima'
        assert variable.code == 1
        assert variable.unit == 'hPa'
        assert variable.acronym == 'Px'
        assert variable.category == MeteocatVariableCategory.DAT
        assert variable.decimal_positions == 1
        assert len(variable.meteocat_variable_states) == 2
        state = variable.meteocat_variable_states[0]
        assert state.code == MeteocatVariableStateCategory.ACTIVE
        assert state.valid_from == datetime.datetime(1996, 5, 2, 21, 0, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_from == 'UTC'
        assert state.valid_until == datetime.datetime(2012, 7, 10, 13, 0, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_until == 'UTC'
        state = variable.meteocat_variable_states[1]
        assert state.code == MeteocatVariableStateCategory.DISMANTLED
        assert state.valid_from == datetime.datetime(2012, 7, 10, 13, 0, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_from == 'UTC'
        assert state.valid_until is None
        assert state.tzinfo_valid_until is None
        assert len(variable.meteocat_variable_time_bases) == 1
        time_base = variable.meteocat_variable_time_bases[0]
        assert time_base.code == MeteocatVariableTimeBaseCategory.SH
        assert time_base.valid_from == datetime.datetime(1996, 5, 2, 21, 0, tzinfo=pytz.UTC)
        assert time_base.tzinfo_valid_from == 'UTC'
        assert time_base.valid_until is None
        assert time_base.tzinfo_valid_until is None


@pytest.mark.parametrize('meteocat_api_station_variables_auxiliars', [{'weather_stations': ['CA']}], indirect=True)
def test_variable_json_parser_05(meteocat_api_station_variables_auxiliars) -> None:
    """
    Tests the METEOCAT API parsing of a variable of a specific station (variables auxiliars)

    :param meteocat_api_station_variables_auxiliars:
    :return:
    """
    for key, data in meteocat_api_station_variables_auxiliars.items():
        variables: List[MeteocatVariable] = json.loads(data, cls=NoNoneInList,
                                                       object_hook=MeteocatVariable.object_hook_variables_of_station_meteocat_api)
        assert len(variables) == 2
        for variable in variables:
            assert isinstance(variable, MeteocatVariable)
        variable = variables[0]
        assert variable.name == 'Precipitació acumulada en 10 min'
        assert variable.code == 900
        assert variable.unit == 'mm'
        assert variable.acronym == 'PPT10min'
        assert variable.category == MeteocatVariableCategory.AUX
        assert variable.decimal_positions == 1
        assert len(variable.meteocat_variable_states) == 2
        state = variable.meteocat_variable_states[0]
        assert state.code == MeteocatVariableStateCategory.ACTIVE
        assert state.valid_from == datetime.datetime(2007, 7, 1, 17, 40, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_from == 'UTC'
        assert state.valid_until == datetime.datetime(2012, 7, 10, 13, 0, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_until == 'UTC'
        state = variable.meteocat_variable_states[1]
        assert state.code == MeteocatVariableStateCategory.DISMANTLED
        assert state.valid_from == datetime.datetime(2012, 7, 10, 13, 0, tzinfo=pytz.UTC)
        assert state.tzinfo_valid_from == 'UTC'
        assert state.valid_until is None
        assert state.tzinfo_valid_until is None
        assert len(variable.meteocat_variable_time_bases) == 1
        time_base = variable.meteocat_variable_time_bases[0]
        assert time_base.code == MeteocatVariableTimeBaseCategory.DM
        assert time_base.valid_from == datetime.datetime(2007, 7, 1, 17, 40, tzinfo=pytz.UTC)
        assert time_base.tzinfo_valid_from == 'UTC'
        assert time_base.valid_until is None
        assert time_base.tzinfo_valid_until is None


@pytest.mark.parametrize('meteocat_api_station_variables_multivariable', [{'weather_stations': ['CA']}], indirect=True)
def test_variable_json_parser_06(meteocat_api_station_variables_multivariable) -> None:
    """
    Tests the METEOCAT API parsing of a variable of a specific station (variables calculades multivariable)

    :param meteocat_api_station_variables_multivariable:
    :return:
    """
    for key, data in meteocat_api_station_variables_multivariable.items():
        variables: List[MeteocatVariable] = json.loads(data, cls=NoNoneInList,
                                                       object_hook=MeteocatVariable.object_hook_variables_of_station_meteocat_api)
        assert len(variables) == 1
        for variable in variables:
            assert isinstance(variable, MeteocatVariable)
        variable = variables[0]
        assert variable.name == 'Evapotranspiració de referència'
        assert variable.code == 6006
        assert variable.unit == 'mm'
        assert variable.acronym == 'ETo'
        assert variable.category == MeteocatVariableCategory.CMV
        assert variable.decimal_positions == 2
        assert len(variable.meteocat_variable_states) == 0
        assert len(variable.meteocat_variable_time_bases) == 1
        time_base = variable.meteocat_variable_time_bases[0]
        assert time_base.code == MeteocatVariableTimeBaseCategory.HO
        assert time_base.valid_from == datetime.datetime(1995, 12, 1, 17, 30, tzinfo=pytz.UTC)
        assert time_base.tzinfo_valid_from == 'UTC'
        assert time_base.valid_until is None
        assert time_base.tzinfo_valid_until is None


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_meteocat_weather_station_json_encoder_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                                  meteocat_variables_list: Union[List[MeteocatVariable], None],
                                                  patch_postgresql_time) -> None:
    """
    TODO
    :param db_session:
    :param data_provider_list:
    :param meteocat_weather_station_list:
    :param patch_postgresql_time:
    :return:
    """
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_meteocat_variables(db_session, meteocat_variables_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(MeteocatVariable.id))).scalar_one() == 90
        variable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.category == MeteocatVariableCategory.DAT).order_by(MeteocatVariable.id)).unique().scalars().first()
        variable_dict = {
            'id': 1,
            'name': 'Pressió atmosfèrica màxima',
            'code': 1,
            'unit': 'hPa',
            'acronym': 'Px',
            'category': 'DAT',
            'decimal_positions': 1,
            'ts': "2024-01-01T12:00:00+0000",
        }
        assert json.loads(json.dumps(variable, cls=MeteocatVariable.JSONEncoder)) == variable_dict
        variable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.category == MeteocatVariableCategory.AUX).order_by(MeteocatVariable.id)).unique().scalars().first()
        variable_dict = {
            'id': 88,
            'name': 'Precipitació acumulada en 10 min',
            'code': 900,
            'unit': 'mm',
            'acronym': 'PPT10min',
            'category': 'AUX',
            'decimal_positions': 1,
            'ts': "2024-01-01T12:00:00+0000",
        }
        assert json.loads(json.dumps(variable, cls=MeteocatVariable.JSONEncoder)) == variable_dict
        variable = db_session.execute(select(MeteocatVariable).where(MeteocatVariable.category == MeteocatVariableCategory.CMV).order_by(MeteocatVariable.id)).unique().scalars().first()
        variable_dict = {
            'id': 90,
            'name': 'Evapotranspiració de referència',
            'code': 6006,
            'unit': 'mm',
            'acronym': 'ETo',
            'category': 'CMV',
            'decimal_positions': 2,
            'ts': "2024-01-01T12:00:00+0000",
        }
        assert json.loads(json.dumps(variable, cls=MeteocatVariable.JSONEncoder)) == variable_dict

