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
from src.meteocat.data_model.lightning import MeteocatLightning

from test.fixtures.database.database import populate_users
from test.fixtures.database.database import populate_data_providers
from test.fixtures.database.database import populate_lightnings


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


def test_api_lightning_entrypoint_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a data_provider argument but with an invalid data provider

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
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_05(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed date from

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_06(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed date to

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T44:00:00Z',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T44:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_07(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'pepito'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_08(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:assc'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:assc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_09(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,pepito'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_10(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,radius,desc'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,radius,desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_11(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,radius:descc'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,radius:descc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_12(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,radius:desc:asc'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,radius:desc:asc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_13(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed order_by

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'date:asc,date:desc'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "Repeated order by parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=date:asc,date:desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_14(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed epsg

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'epsg': 'pepito',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid epsg parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&epsg=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_15(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed x

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'x': '3,5',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid x parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&x=3,5'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_16(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed y

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'y': '3,5',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid y parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&y=3,5'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_17(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed radius

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'radius': '3,5',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid radius parameter"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&radius=3,5'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 404


def test_api_lightning_entrypoint_18(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a missing location parameter

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'radius': 3.5,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid location parameters"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&radius=3.5'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'radius': '3.5'}
    assert user_access.result == 404


def test_api_lightning_entrypoint_19(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a missing location parameter

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'radius': 3.5,
        'x': 23445,
        'y': 23445,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 2
    assert data['error'] == "No valid location parameters"
    assert data['status_code'] == 404
    assert response.status_code == 404
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&radius=3.5&x=23445&y=23445'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'radius': '3.5', 'x': '23445', 'y': '23445'}
    assert user_access.result == 404


def test_api_lightning_entrypoint_20(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user and a valid data_provider argument but with a malformed limit

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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'radius': 3.5,
        'x': 23445,
        'y': 23445,
        'epsg': 25831,
        'limit': 'pepito',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&radius=3.5&x=23445&y=23445&epsg=25831&limit=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'radius': '3.5', 'x': '23445', 'y': '23445', 'epsg': '25831'}
    assert user_access.result == 404


def test_api_lightning_entrypoint_21(db_session: Session, api: FlaskClient, user_list) -> None:
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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'order_by': 'radius:asc',
        'radius': 3.5,
        'x': 23445,
        'y': 23445,
        'epsg': 25831,
        'limit': 123,
        'offset': 'pepito'
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&order_by=radius:asc&radius=3.5&x=23445&y=23445&epsg=25831&limit=123&offset=pepito'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'radius': '3.5', 'x': '23445', 'y': '23445', 'epsg': '25831', 'limit': '123'}
    assert user_access.result == 404


def test_api_lightning_entrypoint_22(db_session: Session, api: FlaskClient, user_list) -> None:
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
        'data_provider': 'Meteo.cat',
        'from': '2020-01-01T00:00:00Z',
        'to': '2020-01-02T00:00:00Z',
        'radius': 3.5,
        'x': 23445,
        'y': 23445,
        'epsg': 25831,
        'limit': 123,
        'offset': 456,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
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
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2020-01-01T00:00:00Z&to=2020-01-02T00:00:00Z&radius=3.5&x=23445&y=23445&epsg=25831&limit=123&offset=456'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'radius': '3.5', 'x': '23445', 'y': '23445', 'epsg': '25831', 'limit': '123', 'offset': '456'}
    assert user_access.result == 404


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_01(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
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
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 999
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_02(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings from a date
    an order_by argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'from': '2013-01-13T00:00:00Z',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 911
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2013-01-13T00:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_03(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings until a date
    an order_by argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'to': '2013-01-13T00:00:00Z',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 88
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&to=2013-01-13T00:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_04(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings from and until a date
    an order_by argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'from': '2013-01-13T00:00:00Z',
        'to': '2013-01-13T02:00:00Z',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 212
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2013-01-13T00:00:00Z&to=2013-01-13T02:00:00Z'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_05(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings from and until a date limited to 200
    an order_by argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'from': '2013-01-13T00:00:00Z',
        'to': '2013-01-13T02:00:00Z',
        'limit': 200
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 200
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2013-01-13T00:00:00Z&to=2013-01-13T02:00:00Z&limit=200'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == { **params, 'limit': '200'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_06(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings from and until a date limited to 200 with
    offset 200
    an order_by argument

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'from': '2013-01-13T00:00:00Z',
        'to': '2013-01-13T02:00:00Z',
        'order_by': 'date:asc',
        'limit': 200,
        'offset': 200,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 12
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2013-01-13T00:00:00Z&to=2013-01-13T02:00:00Z&order_by=date:asc&limit=200&offset=200'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'limit': '200', 'offset': '200'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_07(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings from and until a date ordered descended by date

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    params = {
        'data_provider': 'Meteo.cat',
        'from': '2013-01-13T00:00:00Z',
        'to': '2013-01-13T02:00:00Z',
        'order_by': 'date:desc',
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 212
    assert response.status_code == 200
    assert data[0]['date_time'] == "2013-01-13T01:59:53+0000"
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&from=2013-01-13T00:00:00Z&to=2013-01-13T02:00:00Z&order_by=date:desc'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == params
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_08(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    transformer = Transformer.from_crs("EPSG:4258", "EPSG:25831", always_xy=True)
    x, y = transformer.transform(4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'x': x,
        'y': y,
        'epsg': 25831,
        'radius': 5000,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 9
    for i in range(len(data)):
        assert len(data[i]) == 2
        assert 'lightning' in data[i]
        assert 'distance' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&x={0:}&y={1:}&epsg=25831&radius=5000'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '25831', 'radius': '5000'}
    assert user_access.result == 200
    assert False


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_09(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    transformer = Transformer.from_crs("EPSG:4258", "EPSG:25831", always_xy=True)
    x, y = transformer.transform(4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'order_by': 'radius',
        'x': x,
        'y': y,
        'epsg': 25831,
        'radius': 5000,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 9
    for i in range(len(data) - 1):
        assert data[i]['distance'] <= data[i+1]['distance']
    for i in range(len(data)):
        assert len(data[i]) == 2
        assert 'lightning' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&order_by=radius&x={0:}&y={1:}&epsg=25831&radius=5000'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '25831', 'radius': '5000'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_10(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    transformer = Transformer.from_crs("EPSG:4258", "EPSG:25831", always_xy=True)
    x, y = transformer.transform(4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'order_by': 'radius:desc',
        'x': x,
        'y': y,
        'epsg': 25831,
        'radius': 5000,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 9
    for i in range(len(data) - 1):
        assert data[i]['distance'] >= data[i+1]['distance']
    for i in range(len(data)):
        assert len(data[i]) == 2
        assert 'lightning' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&order_by=radius:desc&x={0:}&y={1:}&epsg=25831&radius=5000'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '25831', 'radius': '5000'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_11(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    x, y = (4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'order_by': 'radius',
        'x': x,
        'y': y,
        'epsg': 4258,
        'radius': 0.05,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 8
    for i in range(len(data) - 1):
        assert data[i]['distance'] <= data[i+1]['distance']
    for i in range(len(data)):
        assert len(data[i]) == 2
        assert 'lightning' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&order_by=radius&x={0:}&y={1:}&epsg=4258&radius=0.05'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '4258', 'radius': '0.05'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_12(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    x, y = (4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'order_by': 'radius',
        'x': x,
        'y': y,
        'epsg': 4326,
        'radius': 0.05,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 8
    for i in range(len(data) - 1):
        assert data[i]['distance'] <= data[i+1]['distance']
    for i in range(len(data)):
        assert len(data[i]) == 2
        assert 'lightning' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&order_by=radius&x={0:}&y={1:}&epsg=4326&radius=0.05'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '4326', 'radius': '0.05'}
    assert user_access.result == 200


@pytest.mark.parametrize('meteocat_lightnings_list', [
    {'year': 2013},
], indirect=True)
@pytest.mark.parametrize('data_provider_list', [
    {'data_providers': ['Meteo.cat', 'Bombers.cat']},
], indirect=True)
def test_api_lightning_query_13(db_session: Session, api: FlaskClient, user_list, data_provider_list, meteocat_lightnings_list) -> None:
    """
    Test a GET to /v2/lightning with a standard user getting lightnings near a location with a epsg on the fly

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :param user_list: Fixture that adds two users, one admin one standard
    :return: None
    """
    populate_users(db_session, user_list)
    populate_data_providers(db_session, data_provider_list)
    populate_lightnings(db_session, meteocat_lightnings_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    assert db_session.execute(select(func.count(DataProvider.name))).scalar_one() == 2
    assert db_session.execute(select(func.count(MeteocatLightning.id))).scalar_one() == 999
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    transformer = Transformer.from_crs("EPSG:4258", "EPSG:4087", always_xy=True)
    x, y = transformer.transform(4.090933, 42.23929)
    params = {
        'data_provider': 'Meteo.cat',
        'order_by': 'radius',
        'x': x,
        'y': y,
        'epsg': 4087,
        'radius': 5000,
    }
    response = api.get('/v2/lightning', headers=headers, query_string=params)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 6
    for i in range(len(data) - 1):
        assert data[i]['distance'] <= data[i+1]['distance']
    for i in range(len(data)):
        assert len(data[i]) == 4
        assert 'x_4087' in data[i]
        assert 'y_4087' in data[i]
        assert 'lightning' in data[i]
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 2
    assert user_access.user.username == 'jack'
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/lightning?data_provider=Meteo.cat&order_by=radius&x={0:}&y={1:}&epsg=4087&radius=5000'.format(x, y)
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {**params, 'x': str(x), 'y': str(y), 'epsg': '4087', 'radius': '5000'}
    assert user_access.result == 200