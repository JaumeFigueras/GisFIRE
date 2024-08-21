#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest
import json

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy import func

from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.bomberscat.data_model.wildfire_ignition import BomberscatValidationLevelCategory
from src.data_model.wildfire_ignition import WildfireIgnitionCategory
from src.data_model.data_provider import DataProvider
from src.json_decoders.no_none_in_list import NoNoneInList

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_bomberscat_wildfire_ignitions

from typing import Union
from typing import List
from typing import Callable


def test_bomberscat_wildfire_ignition_01() -> None:
    """
    Tests the initialization of a wildfire ignition
    """
    ignition = BomberscatWildfireIgnition()
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(name='Wildfire')
    assert ignition.id is None
    assert ignition.name == 'Wildfire'
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(ignition_cause=WildfireIgnitionCategory.LIGHTNING)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause == WildfireIgnitionCategory.LIGHTNING
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC))
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time == datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC)
    assert ignition.tzinfo_start_date_time == 'UTC'
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(region='RMN')
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region == 'RMN'
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(validation_level=BomberscatValidationLevelCategory.CORRECTED)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level == BomberscatValidationLevelCategory.CORRECTED
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(burned_surface=0.258)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface == 0.258
    assert ignition.x_25831 is None
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(x_epsg_25831=452365)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 == 452365
    assert ignition.y_25831 is None
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(y_epsg_25831=369852)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region is None
    assert ignition.validation_level is None
    assert ignition.burned_surface is None
    assert ignition.x_25831 is None
    assert ignition.y_25831 == 369852
    assert ignition.geometry_25831 is None
    assert ignition.x_4258 is None
    assert ignition.y_4258 is None
    assert ignition.geometry_4258 is None
    ignition = BomberscatWildfireIgnition(name='Wildfire', ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                          start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                          x_epsg_25831=330207, y_epsg_25831=4594229, region='RMN',
                                          validation_level=BomberscatValidationLevelCategory.NONE, burned_surface=0.01)
    assert ignition.id is None
    assert ignition.name == 'Wildfire'
    assert ignition.ignition_cause == WildfireIgnitionCategory.REKINDLED_WILDFIRE
    assert ignition.start_date_time == datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC)
    assert ignition.tzinfo_start_date_time == 'UTC'
    assert ignition.x_4326 == 0.966269446118163
    assert ignition.y_4326 == 41.48169947274781
    assert ignition.geometry_4326 == "SRID=4326;POINT(0.966269446118163 41.48169947274781)"
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    assert ignition.region == 'RMN'
    assert ignition.validation_level == BomberscatValidationLevelCategory.NONE
    assert ignition.burned_surface == 0.01
    assert ignition.x_25831 == 330207
    assert ignition.y_25831 == 4594229
    assert ignition.geometry_25831 == "SRID=25831;POINT(330207 4594229)"
    assert ignition.x_4258 == 0.966269446118163
    assert ignition.y_4258 == 41.48169947274781
    assert ignition.geometry_4258 == "SRID=4258;POINT(0.966269446118163 41.48169947274781)"


def test_wildfire_ignition_02() -> None:
    """
    Tests the incorrect initialization of a wildfire ignition
    """
    with pytest.raises(ValueError):
        _ = BomberscatWildfireIgnition(start_date_time=datetime.datetime(2024, 4, 1, 15,  34, 56))


def test_iter_01() -> None:
    """
    Tests the iterator function of a naive ignition to obtain a Dict

    :return None:
    """
    ignition = BomberscatWildfireIgnition(name='Wildfire', ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                          start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                          x_epsg_25831=330207, y_epsg_25831=4594229, region='RMN',
                                          validation_level=BomberscatValidationLevelCategory.NONE, burned_surface=0.01)
    dct = dict(ignition)
    assert dct == {
        'id': None,
        'name': 'Wildfire',
        'ignition_cause': WildfireIgnitionCategory.REKINDLED_WILDFIRE.name,
        'start_date_time': '2024-01-01T16:00:00+0000',
        'x_4326': 0.966269446118163,
        'y_4326': 41.48169947274781,
        'ts': None,
        'data_provider': None,
        'validation_level': 'NONE',
        'region': 'RMN',
        'burned_surface': 0.01,
        'x_25831': 330207,
        'y_25831': 4594229,
        'x_4258': 0.966269446118163,
        'y_4258': 41.48169947274781,
    }


@pytest.mark.parametrize('data_provider_list', [{'data_providers': ['Bombers.cat']},], indirect=True)
def test_iter_02(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                 patch_postgresql_time: Callable) -> None:
    """
    Tests the iterator function of an ignition stored in a database to obtain a Dict

    :param db_session: SQLAlchemy database session
    :type db_session: Session
    :param data_provider_list: List of data providers
    :type data_provider_list: Union[List[DataProvider], None]
    :param patch_postgresql_time: Patch PostgreSQL date and time
    :return None:
    """
    with patch_postgresql_time("2024-02-01 16:00:00", tzinfo=pytz.UTC, tick=False):
        populate_data_providers(db_session, data_provider_list)
        ignition = BomberscatWildfireIgnition(name='Wildfire',
                                              ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                              start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                              x_epsg_25831=330207, y_epsg_25831=4594229, region='RMN',
                                              validation_level=BomberscatValidationLevelCategory.NONE,
                                              burned_surface=0.01)
        ignition.data_provider_name = "Bombers.cat"
        db_session.add(ignition)
        db_session.commit()
        dct = dict(ignition)
        assert dct == {
            'id': 1,
            'name': 'Wildfire',
            'ignition_cause': WildfireIgnitionCategory.REKINDLED_WILDFIRE.name,
            'x_4326': 0.966269446118163,
            'y_4326': 41.48169947274781,
            'start_date_time': '2024-01-01T16:00:00+0000',
            'ts': "2024-02-01T16:00:00+0000",
            'data_provider': 'Bombers.cat',
            'validation_level': 'NONE',
            'region': 'RMN',
            'burned_surface': 0.01,
            'x_25831': 330207,
            'y_25831': 4594229,
            'x_4258': 0.966269446118163,
            'y_4258': 41.48169947274781,
        }


def test_bomberscat_wildfire_ignition_json_parser_01(gisfire_api_bomberscat_wildfire_ignition: str) -> None:
    """
    Tests the parsing of a JSON with a wildfire ignition using the GisFIRE API syntax

    :param gisfire_api_bomberscat_wildfire_ignition: The JSON with a wildfire ignitions
    :type gisfire_api_bomberscat_wildfire_ignition: str
    :return: None
    """
    ignitions: List[BomberscatWildfireIgnition] = json.loads(gisfire_api_bomberscat_wildfire_ignition, cls=NoNoneInList,
                                                             object_hook=BomberscatWildfireIgnition.object_hook_gisfire_api)
    for ignition in ignitions:
        assert isinstance(ignition, BomberscatWildfireIgnition)
    ignition = ignitions[0]
    assert isinstance(ignition, BomberscatWildfireIgnition)
    assert ignition.id == 2
    assert ignition.name == 'Batea - Pinyeres'
    assert ignition.ignition_cause == WildfireIgnitionCategory.LIGHTNING
    assert ignition.x_4326 == 0.21445579662077788
    assert ignition.y_4326 == 41.12865189782346
    assert ignition.geometry_4326 == "SRID=4326;POINT(0.21445579662077788 41.12865189782346)"
    print(ignition.tzinfo_start_date_time)
    assert ignition.start_date_time == datetime.datetime(2006, 6, 9, 20, 24, 0, tzinfo=datetime.timezone(datetime.timedelta(0, 7200)))
    assert ignition.region == 'RETE'
    assert ignition.burned_surface == 0.0
    assert ignition.validation_level == BomberscatValidationLevelCategory.NONE
    assert ignition.x_4258 == 0.21445579662077788
    assert ignition.y_4258 == 41.12865189782346
    assert ignition.geometry_4258 == "SRID=4258;POINT(0.21445579662077788 41.12865189782346)"
    assert ignition.x_25831 == 266175.0
    assert ignition.y_25831 == 4556779.0
    assert ignition.geometry_25831 == "SRID=25831;POINT(266175.0 4556779.0)"


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_bomberscat_wildfire_ignition_json_encoder_01(db_session: Session,
                                                      data_provider_list: Union[List[DataProvider], None],
                                                      bomberscat_wildfire_ignitions_list: List[BomberscatWildfireIgnition],
                                                      patch_postgresql_time: Callable) -> None:
    """
    Tests the generation of a JSON from an ignition in a database using the GisFIRE API syntax

    :param db_session: SQLAlchemy database session
    :type db_session: Session
    :param data_provider_list: List of data providers
    :type data_provider_list: Union[List[DataProvider], None]
    :param bomberscat_wildfire_ignitions_list: List of bomberscat ignitions
    :type bomberscat_wildfire_ignitions_list: List[BomberscatWildfireIgnition]
    :param patch_postgresql_time: Patch PostgreSQL date and time
    :type patch_postgresql_time: Callable
    :return:
    """
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
        station = db_session.execute(select(BomberscatWildfireIgnition).where(BomberscatWildfireIgnition.id == 1)).unique().scalar_one()
        ignition_dict = {
            "id": 1,
            "name": "Batea - Pinyeres",
            "ignition_cause": "LIGHTNING",
            "x_25831": 266175.0,
            "y_25831": 4556779.0,
            "x_4258": 0.21445579662077788,
            "y_4258": 41.12865189782346,
            "x_4326": 0.21445579662077788,
            "y_4326": 41.12865189782346,
            "start_date_time": "2006-06-09T20:24:00+0200",
            "ts": "2024-01-01T12:00:00+0000",
            "data_provider": "Bombers.cat",
            "region": "RETE",
            "validation_level": "NONE",
            "burned_surface": 0.0,
        }
        assert json.loads(json.dumps(station, cls=BomberscatWildfireIgnition.JSONEncoder)) == ignition_dict


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_meteocat_weather_station_geojson_encoder_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                                                     bomberscat_wildfire_ignitions_list: List[BomberscatWildfireIgnition],
                                                     patch_postgresql_time: Callable) -> None:
    """
    Tests the generation of a GeoJSON from an ignition in a database using the GisFIRE API syntax

    :param db_session: SQLAlchemy database session
    :type db_session: Session
    :param data_provider_list: List of data providers
    :type data_provider_list: Union[List[DataProvider], None]
    :param bomberscat_wildfire_ignitions_list: List of bomberscat ignitions
    :type bomberscat_wildfire_ignitions_list: List[BomberscatWildfireIgnition]
    :param patch_postgresql_time: Patch PostgreSQL date and time
    :type patch_postgresql_time: Callable
    :return:
    """
    with patch_postgresql_time("2024-01-01 12:00:00", tzinfo=pytz.UTC, tick=False):
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
        assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 0
        populate_data_providers(db_session, data_provider_list)
        populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
        assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
        ignition = db_session.execute(select(BomberscatWildfireIgnition).where(BomberscatWildfireIgnition.id == 1)).unique().scalar_one()
        ignition_dict = {
            "type": "Feature",
            "id": 1,
            "geometry": {
                "type": "Point",
                "coordinates": [0.21445579662077788, 41.12865189782346]
            },
            "properties": {
                "id": 1,
                "name": "Batea - Pinyeres",
                "ignition_cause": "LIGHTNING",
                "x_25831": 266175.0,
                "y_25831": 4556779.0,
                "x_4258": 0.21445579662077788,
                "y_4258": 41.12865189782346,
                "x_4326": 0.21445579662077788,
                "y_4326": 41.12865189782346,
                "start_date_time": "2006-06-09T20:24:00+0200",
                "ts": "2024-01-01T12:00:00+0000",
                "data_provider": "Bombers.cat",
                "region": "RETE",
                "validation_level": "NONE",
                "burned_surface": 0.0,
            }
        }
        assert json.loads(json.dumps(ignition, cls=BomberscatWildfireIgnition.GeoJSONEncoder)) == ignition_dict

