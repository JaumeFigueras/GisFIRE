#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

from ipaddress import IPv4Address

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select
from flask.testing import FlaskClient

from src.data_model.user_access import UserAccess
from src.data_model.user_access import HttpMethods


def test_api_main_entrypoint_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.get('/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 500
    assert response.status_code == 500
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}


