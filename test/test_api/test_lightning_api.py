#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import freezegun
import pytz

from ipaddress import IPv4Address
from base64 import b64encode
from dateutil.tz import tzoffset

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select
from flask.testing import FlaskClient

from src.data_model.user_access import UserAccess
from src.data_model.user_access import HttpMethods
from src.data_model.user import User

from test.fixtures.database.database import populate_users


def test_api_lightning_entrypoint_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test a GET to /v2/lightning with no user causing an access authentication error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.get('/v2/lightning')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 401
    assert response.status_code == 401
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_lightning_entrypoint_02(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with an admin user causing a semantic error because there is no data_provider argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    response = api.get('/v2/lightning', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No data_provider provided"
    assert data['status_code'] == 400
    assert response.status_code == 400
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert user_access.user.username == 'admin'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 400


def test_api_lightning_entrypoint_03(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user causing a semantic error because there is no data_provider argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    response = api.get('/v2/lightning', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No data_provider provided"
    assert data['status_code'] == 400
    assert response.status_code == 400
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 400
