#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import freezegun

from ipaddress import IPv4Address
from base64 import b64encode

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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.head('/v2/user')
    assert response.content_type == 'application/json'
    # data = json.loads(response.get_data(as_text=True))
    # assert len(data) == 1
    # assert data['status_code'] == 500
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
    :return: None
    """
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    # Tests the API
    response = api.head('/v2/user/')
    assert response.content_type == 'application/json'
    # data = json.loads(response.get_data(as_text=True))
    # assert len(data) == 1
    # assert data['status_code'] == 500
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_entrypoint_15(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_entrypoint_16(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_entrypoint_17(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_entrypoint_18(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_post_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
    :return: None
    """
    populate_users(db_session, user_list)
    # Assert the database is OK
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(User.id))).scalar_one() == 2
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


def test_api_user_post_04(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


def test_api_user_post_05(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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


@freezegun.freeze_time('2023-01-01 12:00:00')
def test_api_user_post_06(db_session: Session, api: FlaskClient, user_list) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
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
    assert data['valid_until'] == "2024-01-01T13:00:00+0100"
    assert response.status_code == 200
    # Assert database
    assert db_session.execute(select(func.count(UserAccess.id))).scalar_one() == 1
    user_access = db_session.execute(select(UserAccess)).scalar_one()
    assert user_access.user_id == 1
    assert isinstance(user_access.user, User)
    assert user_access.ip == IPv4Address('127.0.0.1')
    assert user_access.url == 'http://localhost/v2/user'
    assert user_access.method == HttpMethods.POST
    assert user_access.params == {'username': 'sally'}
    assert user_access.result == 200


