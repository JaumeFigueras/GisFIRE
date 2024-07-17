#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select

from src.data_model.data_provider import DataProvider
from test.fixtures.database.database import populate_data_providers

from src.applications.auxiliar.populate_data_providers import main

from typing import List
from typing import Union


@pytest.mark.parametrize('data_provider_list', [
    {},
    {'data_providers': ['Meteo.cat']},
    {'data_providers': ['Bombers.cat']},
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
    {'data_providers': ['Test.1', 'Test.2', 'Test.3']}
], indirect=True)
def test_main_01(db_session: Session, data_provider_list: Union[List[DataProvider], None]) -> None:
    # Assert the database is OK
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    populate_data_providers(db_session, data_provider_list)
    # Assert the database is correctly populated
    if data_provider_list is None:
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 0
    else:
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == len(data_provider_list)
    # Test function
    main(db_session)
    # Assert the results
    if data_provider_list is None:
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    elif len(data_provider_list) < 3:
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    elif len(data_provider_list) == 3:
        assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 5
