#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz
import pytest

from sqlalchemy.orm import Session
from shapely.geometry import Point

from src.data_model.wildfire_ignition import WildfireIgnition
from src.data_model.wildfire_ignition import WildfireIgnitionCategory
from src.data_model.data_provider import DataProvider

from test.fixtures.database.database import populate_data_providers

from typing import Union
from typing import List


def test_wildfire_ignition_01() -> None:
    """
    Tests the initialization of a wildfire ignition
    """
    ignition = WildfireIgnition()
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
    ignition = WildfireIgnition(name='Wildfire')
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
    ignition = WildfireIgnition(ignition_cause=WildfireIgnitionCategory.LIGHTNING)
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
    ignition = WildfireIgnition(start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC))
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
    ignition = WildfireIgnition(longitude_epsg_4326=23.45)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 == 23.45
    assert ignition.y_4326 is None
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    ignition = WildfireIgnition(latitude_epsg_4326=12.34)
    assert ignition.id is None
    assert ignition.name is None
    assert ignition.ignition_cause is None
    assert ignition.start_date_time is None
    assert ignition.tzinfo_start_date_time is None
    assert ignition.x_4326 is None
    assert ignition.y_4326 == 12.34
    assert ignition.geometry_4326 is None
    assert ignition.ts is None
    assert ignition.data_provider_name is None
    ignition = WildfireIgnition(name='Wildfire', ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                longitude_epsg_4326=23.45, latitude_epsg_4326=12.34)
    assert ignition.id is None
    assert ignition.name == 'Wildfire'
    assert ignition.ignition_cause == WildfireIgnitionCategory.REKINDLED_WILDFIRE
    assert ignition.start_date_time == datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC)
    assert ignition.tzinfo_start_date_time == 'UTC'
    assert ignition.x_4326 == 23.45
    assert ignition.y_4326 == 12.34
    assert ignition.geometry_4326 == "SRID=4326;POINT(23.45 12.34)"
    assert ignition.ts is None
    assert ignition.data_provider_name is None


def test_wildfire_ignition_02() -> None:
    """
    Tests the incorrect initialization of a wildfire ignition
    """
    with pytest.raises(ValueError):
        _ = WildfireIgnition(latitude_epsg_4326=90.01)
    with pytest.raises(ValueError):
        _ = WildfireIgnition(latitude_epsg_4326=-90.01)
    with pytest.raises(ValueError):
        _ = WildfireIgnition(longitude_epsg_4326=180.01)
    with pytest.raises(ValueError):
        _ = WildfireIgnition(longitude_epsg_4326=-180.01)
    with pytest.raises(ValueError):
        _ = WildfireIgnition(latitude_epsg_4326=90.01, longitude_epsg_4326=180.01)
    with pytest.raises(ValueError):
        _ = WildfireIgnition(start_date_time=datetime.datetime(2024, 4, 1, 15,  34, 56))


def test_iter_01() -> None:
    ignition = WildfireIgnition(name='Wildfire', ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                longitude_epsg_4326=23.45, latitude_epsg_4326=12.34)
    dct = dict(ignition)
    assert dct == {
        'id': None,
        'name': 'Wildfire',
        'ignition_cause': WildfireIgnitionCategory.REKINDLED_WILDFIRE.name,
        'start_date_time': '2024-01-01T16:00:00+0000',
        'x_4326': 23.45,
        'y_4326': 12.34,
        'ts': None,
        'data_provider': None
    }


@pytest.mark.parametrize('data_provider_list', [{'data_providers': ['Bombers.cat']},], indirect=True)
def test_iter_02(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                 patch_postgresql_time) -> None:
    with patch_postgresql_time("2024-02-01 16:00:00", tzinfo=pytz.UTC, tick=False):
        populate_data_providers(db_session, data_provider_list)
        ignition = WildfireIgnition(name='Wildfire', ignition_cause=WildfireIgnitionCategory.REKINDLED_WILDFIRE,
                                    start_date_time=datetime.datetime(2024, 1, 1, 16, 0, 0, tzinfo=pytz.UTC),
                                    longitude_epsg_4326=23.45, latitude_epsg_4326=12.34)
        ignition.data_provider_name = "Bombers.cat"
        db_session.add(ignition)
        db_session.commit()
        dct = dict(ignition)
        assert dct == {
            'id': 1,
            'name': 'Wildfire',
            'ignition_cause': WildfireIgnitionCategory.REKINDLED_WILDFIRE.name,
            'x_4326': 23.45,
            'y_4326': 12.34,
            'start_date_time': '2024-01-01T16:00:00+0000',
            'ts': "2024-02-01T16:00:00+0000",
            'data_provider': 'Bombers.cat'
        }
