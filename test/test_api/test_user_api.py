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


def test_api_user_entrypoint_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test a GET to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.get('/v2/user')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_02(db_session: Session, api: FlaskClient) -> None:
    """
    Test a HEAD to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.head('/v2/user')
    assert response.content_type == 'application/json'
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.HEAD
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_03(db_session: Session, api: FlaskClient) -> None:
    """
    Test a PUT to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.put('/v2/user')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_04(db_session: Session, api: FlaskClient) -> None:
    """
    Test a DELETE to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.delete('/v2/user')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_05(db_session: Session, api: FlaskClient) -> None:
    """
    Test a TRACE to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.trace('/v2/user')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.TRACE
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_06(db_session: Session, api: FlaskClient) -> None:
    """
    Test a PATCH to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.patch('/v2/user')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.PATCH
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_07(db_session: Session, api: FlaskClient) -> None:
    """
    Test a GET to /v2/user/ causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.get('/v2/user/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.GET
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_08(db_session: Session, api: FlaskClient) -> None:
    """
    Test a HEAD to /v2/user/ causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.head('/v2/user/')
    assert response.content_type == 'application/json'
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.HEAD
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_09(db_session: Session, api: FlaskClient) -> None:
    """
    Test a PUT to /v2/user/ causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.put('/v2/user/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_10(db_session: Session, api: FlaskClient) -> None:
    """
    Test a DELETE to /v2/user/ causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.delete('/v2/user/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_11(db_session: Session, api: FlaskClient) -> None:
    """
    Test a TRACE to /v2/user/ causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.trace('/v2/user/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.TRACE
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_12(db_session: Session, api: FlaskClient) -> None:
    """
    Test a PATCH to /v2/user causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.patch('/v2/user/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/'
    assert user_access.method == HttpMethods.PATCH
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_13(db_session: Session, api: FlaskClient) -> None:
    """
    Test a POST to /v2/user/username causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.post('/v2/user/pepito')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/pepito'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_entrypoint_14(db_session: Session, api: FlaskClient) -> None:
    """
    Test a POST to /v2/user/username causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.post('/v2/user/pepito/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 405
    assert response.status_code == 405
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id is None
    assert user_access.user is None
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/pepito/'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 405


def test_api_user_post_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test a POST to /v2/user without authorization causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.post('/v2/user')
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
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_user_post_02(db_session: Session, api: FlaskClient) -> None:
    """
    Test a POST to /v2/user with incorrect authorization causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"john.doe:qwertyuiop123456789").decode("utf-8"))}
    response = api.post('/v2/user', headers=headers)
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
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_user_post_03(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization but nou admin causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"jack:5678").decode("utf-8"))}
    response = api.post('/v2/user', headers=headers)
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
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_user_post_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and without parameters causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    response = api.post('/v2/user', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 422


def test_api_user_post_05(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and without username in the parameters causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until': '2024-01-01 00:00:00'}
    response = api.post('/v2/user', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_06(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with just the username, creating a new user with valid_date +1 year
    and TZ UTC

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally'}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'sally'
    assert len(data['token']) == 64
    assert not data['is_admin']
    assert data['valid_until'] == "2024-01-01T12:00:00+0000"
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 3
    user = db_session.execute(select(User).where(User.username == 'sally')).scalar_one()
    assert user.username == 'sally'
    assert user.valid_until == datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=pytz.UTC)
    assert len(user.token) == 64
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally'}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_07(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with username and valid date without TZ creating a new user with
    valid_date with TZ UTC

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'valid_until': '2024-01-01T12:00:00'}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'sally'
    assert len(data['token']) == 64
    assert not data['is_admin']
    assert data['valid_until'] == "2024-01-01T12:00:00+0000"
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 3
    user = db_session.execute(select(User).where(User.username == 'sally')).scalar_one()
    assert user.username == 'sally'
    assert user.valid_until == datetime.datetime(2024, 1,  1, 12, 0, 0, tzinfo=pytz.UTC)
    assert len(user.token) == 64
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'valid_until': '2024-01-01T12:00:00'}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_08(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with username and valid date with TZ but incorrect key causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'valid_unkil': "2024-01-01T13:00:00+0100"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'valid_unkil': "2024-01-01T13:00:00+0100"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_09(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with username and valid date with TZ creating a new user with
    valid_date with TZ +0100

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'valid_until': "2024-01-01T13:00:00+0400"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'sally'
    assert len(data['token']) == 64
    assert not data['is_admin']
    assert data['valid_until'] == "2024-01-01T13:00:00+0400"
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 3
    user = db_session.execute(select(User).where(User.username == 'sally')).scalar_one()
    assert user.username == 'sally'
    assert user.valid_until == datetime.datetime(2024, 1,  1, 13, 0, 0, tzinfo=tzoffset(None, 14400))
    assert len(user.token) == 64
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'valid_until': "2024-01-01T13:00:00+0400"}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_10(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with username, valid date with timezone and timezone UTC causing en
    error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'valid_until': "2024-01-01T13:00:00+0100", 'timezone': 'UTC'}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'valid_until': "2024-01-01T13:00:00+0100", 'timezone': 'UTC'}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_11(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and with username, valid date without timezone and timezone
    Europe/Andorra creating the user accordingly

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'valid_until': "2024-01-01T13:00:00", 'timezone': 'Europe/Andorra'}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'sally'
    assert len(data['token']) == 64
    assert not data['is_admin']
    assert data['valid_until'] == "2024-01-01T13:00:00+0100"
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 3
    user = db_session.execute(select(User).where(User.username == 'sally')).scalar_one()
    assert user.username == 'sally'
    assert user.valid_until == pytz.timezone('Europe/Andorra').localize(datetime.datetime(2024, 1,  1, 13, 0, 0))
    assert len(user.token) == 64
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'valid_until': "2024-01-01T13:00:00", 'timezone': 'Europe/Andorra'}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_13(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization without username

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until': "2024-01-01T13:00:00"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'valid_until': "2024-01-01T13:00:00"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_14(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization without valid_until but with timezone

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'sally', 'timezone': "UTC"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally', 'timezone': "UTC"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_15(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization creating an existent user

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'jack', 'valid_until': "2024-01-01T13:00:00"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'jack', 'valid_until': "2024-01-01T13:00:00"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_16(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a POST to /v2/user with authorization and invalid date

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'jack', 'valid_until': "2024-013-01T13:00:00"}
    response = api.post('/v2/user', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'jack', 'valid_until': "2024-013-01T13:00:00"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_01(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization without parameters

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    response = api.put('/v2/user/jack', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_02(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username without authorization with parameters

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    data = {'username': 'jack', 'valid_until': "2024-01-01T13:00:00"}
    response = api.put('/v2/user/jack', data=data)
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
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'username': 'jack', 'valid_until': "2024-01-01T13:00:00"}
    assert user_access.result == 401


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_03(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with invalid parameter name

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until_now': "2024-01-01T13:00:00"}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'valid_until_now': "2024-01-01T13:00:00"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with invalid token parameter

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'token': "123456789"}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'token': "123456789"}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_05(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters to update the token

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    old_token = db_session.execute(select(User.token).where(User.username == 'jack')).scalar_one()
    assert old_token == '5678'
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'token': 'new'}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'jack'
    assert data['valid_until'] == '2024-01-01T12:00:00+0000'
    assert not data['is_admin']
    assert len(data['token']) == 64
    assert data['token'] != old_token
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    user = db_session.execute(select(User).where(User.username == 'jack')).scalar_one()
    assert user.username == 'jack'
    assert user.valid_until == pytz.timezone('Europe/Andorra').localize(datetime.datetime(2024, 1,  1, 13, 0, 0))
    assert len(user.token) == 64
    assert user.token != old_token
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'token': "new"}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_06(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters to update validity

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until': '2026-01-01T12:00:00'}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'jack'
    assert data['valid_until'] == '2026-01-01T12:00:00+0000'
    assert not data['is_admin']
    assert data['token'] == '5678'
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    user = db_session.execute(select(User).where(User.username == 'jack')).scalar_one()
    assert user.username == 'jack'
    assert user.valid_until == datetime.datetime(2026, 1,  1, 12, 0, 0, tzinfo=pytz.UTC)
    assert len(user.token) == 4
    assert user.token == '5678'
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'valid_until': '2026-01-01T12:00:00'}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_07(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters to update validity with timezone

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until': '2026-01-01T12:00:00', 'timezone': 'Europe/Andorra'}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 4
    assert data['username'] == 'jack'
    assert data['valid_until'] == '2026-01-01T12:00:00+0100'
    assert not data['is_admin']
    assert data['token'] == '5678'
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    user = db_session.execute(select(User).where(User.username == 'jack')).scalar_one()
    assert user.username == 'jack'
    assert user.valid_until == pytz.timezone('Europe/Andorra').localize(datetime.datetime(2026, 1,  1, 12, 0, 0))
    assert len(user.token) == 4
    assert user.token == '5678'
    assert not user.is_admin
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'valid_until': '2026-01-01T12:00:00', 'timezone': 'Europe/Andorra'}
    assert user_access.result == 200


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_08(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters to update validity only with timezone causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'timezone': 'Europe/Andorra'}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'timezone': 'Europe/Andorra'}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_09(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters updating an unexisting user

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'token': 'new'}
    response = api.put('/v2/user/sally', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/sally'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'token': 'new'}
    assert user_access.result == 422


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_put_10(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a PUT to /v2/user/username with authorization with parameters to update validity with timezone and timezone
    parameter causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'valid_until': '2024-01-01 00:00:00+0500', 'timezone': 'Europe/Andorra'}
    response = api.put('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.PUT
    assert user_access.params == {'valid_until': '2024-01-01 00:00:00+0500', 'timezone': 'Europe/Andorra'}
    assert user_access.result == 422


def test_api_user_delete_01(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a DELETE to /v2/user/username without authorization causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    response = api.delete('/v2/user/jack')
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
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {}
    assert user_access.result == 401


def test_api_user_delete_02(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a DELETE to /v2/user/username with authorization with parameters causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    data = {'username': 'jack'}
    response = api.delete('/v2/user/jack', headers=headers, data=data)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {'username': 'jack'}
    assert user_access.result == 422


def test_api_user_delete_03(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a DELETE to /v2/user/username with authorization with parameters causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    response = api.delete('/v2/user/sally', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 422
    assert response.status_code == 422
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/sally'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {}
    assert user_access.result == 422


def test_api_user_delete_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test a DELETE to /v2/user/username with authorization with parameters causing an error

    :param db_session: SQLAlchemy session
    :type db_session: Session
    :param api: GisFIRE api fixture
    :type api: FlaskClient
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
    # Tests the API
    headers = {'Authorization': 'Basic {}'.format(b64encode(b"admin:1234").decode("utf-8"))}
    response = api.delete('/v2/user/jack', headers=headers)
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 0
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user/jack'
    assert user_access.method == HttpMethods.DELETE
    assert user_access.params == {}
    assert user_access.result == 200

