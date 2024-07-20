#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import _csv
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select

from src.meteocat.data_model.lightning import MeteocatLightning
from src.data_model.request import Request
from src.data_model.data_provider import DataProvider
from test.fixtures.database.database import populate_data_providers

from src.applications.meteocat.import_lightnings_from_csv import process_lightnings
from src.applications.meteocat.import_lightnings_from_csv import process_requests

from typing import List
from typing import Union


@pytest.mark.parametrize('meteocat_lightnings_csv_reader', [
    {'year': 2013},
    {'year': 2017},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_process_lightnings_01(db_session: Session, meteocat_lightnings_csv_reader: Union[_csv.reader, None],
                               data_provider_list: Union[List[DataProvider], None]) -> None:
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    # Test function
    process_lightnings(db_session, meteocat_lightnings_csv_reader, logger)
    # Assert the results
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999


@pytest.mark.parametrize('year', [2013, 2017])
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_process_requests_01(db_session: Session, data_provider_list: Union[List[DataProvider], None], year: int) -> None:
    # Logger setup
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    logging.basicConfig(format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s', handlers=[handler], encoding='utf-8', level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
    # Assert the database is OK
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    # Test function
    process_requests(db_session, year, logger)
    # Assert the results
    assert db_session.execute(select(func.count(Request.uri))).scalar_one() == 365*24
