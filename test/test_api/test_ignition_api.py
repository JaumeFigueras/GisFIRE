#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json
import datetime
import pytz

from ipaddress import IPv4Address
from base64 import b64encode
from dateutil.tz import tzoffset
from pyproj import Transformer

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select
from flask.testing import FlaskClient

from src.data_model.user_access import UserAccess
from src.data_model.user_access import HttpMethods
from src.data_model.user import User
from src.data_model.data_provider import DataProvider
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition

from test.fixtures.database.database import populate_users
from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_bomberscat_wildfire_ignitions


def test_api_ignition_entrypoint_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test a GET to /v2/ignition with no user causing an access authentication error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.get('/v2/ignition')
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
    assert user_access.url == 'http://localhost/v2/ignition'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_ignition_entrypoint_02(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with an admin user causing a semantic error because there is no data_provider argument

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
    response = api.get('/v2/ignition', headers=headers)
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
    assert user_access.url == 'http://localhost/v2/ignition'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 400


def test_api_ignition_entrypoint_03(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user causing a semantic error because there is no data_provider argument

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
    response = api.get('/v2/ignition', headers=headers)
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
    assert user_access.url == 'http://localhost/v2/ignition'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 400


def test_api_ignition_entrypoint_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a data_provider argument but with an invalid data provider

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
    params = {'data_provider': 'pepito'}
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid data_provider provided"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_05(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed date from

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid from date provided"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_06(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed date to

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T44:00:00Z',
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid to date provided"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T44:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_07(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed order_by

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'pepito'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid order by parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_08(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed order_by

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:assc'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid order by sort parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:assc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_09(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed order_by

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,radius,desc'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid number of order by parameter elements"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,radius,desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_10(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed order_by

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc:desc'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid order by parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc:desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_11(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user and a valid data_provider argument but with a malformed limit

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc',
        'limit': 'pepito',
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid limit parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc&limit=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_ignition_entrypoint_12(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed offset

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc',
        'limit': 123,
        'offset': 'pepito'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid offset parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc&limit=123&offset=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'limit': '123'}
    assert user_access.result == 404


def test_api_ignition_entrypoint_13(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with an offset but without
    an order_by argument

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
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'limit': 123,
        'offset': 456,
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No order argument while offset parameter present"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&limit=123&offset=456'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'limit': '123', 'offset': '456'}
    assert user_access.result == 404


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_01(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting all available lightnings

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 21
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_02(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from a certain date

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 17
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_03(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from a certain date

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'to': '2015-01-01T00:00:00Z'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&to=2015-01-01T00:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_04(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from and until a certain date

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z',
        'to': '2017-06-26T00:00:00Z'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 16
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z&to=2017-06-26T00:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_05(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from and until a certain date with
    ordering

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z',
        'to': '2017-06-26T00:00:00Z',
        'order_by': 'date'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 16
    assert response.status_code == 200
    assert data[0]['start_date_time'] == '2016-07-22T21:30:00+0200'
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z&to=2017-06-26T00:00:00Z&order_by=date'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_06(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from and until a certain date with
    ordering desc

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z',
        'to': '2018-01-01T00:00:00Z',
        'order_by': 'date:desc'
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 17
    assert response.status_code == 200
    assert data[0]['start_date_time'] == '2017-06-26T02:11:40+0200'
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z&to=2018-01-01T00:00:00Z&order_by=date:desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_07(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from and until a certain date with
    ordering and limit

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z',
        'to': '2018-01-01T00:00:00Z',
        'order_by': 'date',
        'limit': 5
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 5
    assert response.status_code == 200
    assert data[0]['start_date_time'] == '2016-07-22T21:30:00+0200'
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z&to=2018-01-01T00:00:00Z&order_by=date&limit=5'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'limit': '5'}
    assert user_access.result == 200



@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_ignition_query_08(db_session: Session, api: FlaskClient, user_list, data_provider_list, bomberscat_wildfire_ignitions_list) -> None:
    """
    Test a GET to /v2/ignition with a standard user getting all available ignitions from and until a certain date with
    ordering and limit with offset

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_bomberscat_wildfire_ignitions(db_session, bomberscat_wildfire_ignitions_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(BomberscatWildfireIgnition.id))).scalar_one() == 21
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Bombers.cat',
        'from': '2015-01-01T00:00:00Z',
        'to': '2018-01-01T00:00:00Z',
        'order_by': 'date',
        'limit': 5,
        'offset': 10
    }
    response = api.get('/v2/ignition', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 5
    assert response.status_code == 200
    assert data[0]['start_date_time'] == '2017-05-19T15:30:00+0200'
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/ignition?data_provider=Bombers.cat&from=2015-01-01T00:00:00Z&to=2018-01-01T00:00:00Z&order_by=date&limit=5&offset=10'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'limit': '5', 'offset': '10'}
    assert user_access.result == 200

