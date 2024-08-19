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

from src.data_model.data_provider import DataProvider
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition

from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_meteocat_weather_stations
from test.fixtures.database.database import populate_meteocat_variables
from test.fixtures.database.database import populate_meteocat_variable_states
from test.fixtures.database.database import populate_meteocat_variable_time_bases

from src.applications.bomberscat.import_ignitions_from_csv import process_ignitions

from typing import List
from typing import Union


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_process_ignitions_01(db_session: Session, data_provider_list: Union[List[DataProvider], None],
                              meteocat_ignition_csv_reader: Union[_csv.reader, None]) -> None:
    """
    Tests all is OK

    :param db_session:
    :param data_provider_list:
    :param meteocat_ignition_csv_reader:
    :return:
    """
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    # Test function
    process_ignitions(db_session, meteocat_ignition_csv_reader, logger)
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 782
