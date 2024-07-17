#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

from sqlalchemy.orm import Session
from flask.testing import FlaskClient


def test_api_main_entrypoint_01(db_session: Session, api: FlaskClient) -> None:
    """
    Test the main entry point to the API. The / provide no answer, so a 500 (internal server error) code is thrown

    :param api: GisFIRE api fixture
    :return: None
    """
    response = api.get('/')
    assert response.content_type == 'application/json'
    data = json.loads(response.get_data(as_text=True))
    assert len(data) == 1
    assert data['status_code'] == 500
    assert response.status_code == 500
    # cursor = postgresql_schema.cursor()
    # cursor.execute("SELECT count(*) FROM user_access")
    # record = cursor.fetchone()
    # assert record[0] == count + 1
    # cursor.execute("SELECT id, user_id, ip, url, method, params, result_code FROM user_access")
    # record = cursor.fetchone()
    # assert record[1] is None
    # assert record[2] == '127.0.0.1'
    # assert record[3] == 'http://localhost/'
    # assert record[4] == 'GET'
    # assert record[5] == '{}'
    # assert record[6] == 500


# def test_api_main_entrypoint_02(api, postgresql_schema):
#     """
#     Test the main entry point to the API. The /api will return a not found, so a 404 (not found) code is thrown
#
#     :param api: GisFIRE api fixture
#     :return: Nothing
#     """
#
#     cursor = postgresql_schema.cursor()
#     cursor.execute("SELECT count(*) FROM user_access")
#     record = cursor.fetchone()
#     count = record[0]
#     response = api.get('/api')
#     assert response.content_type == 'application/json'
#     data = json.loads(response.get_data(as_text=True))
#     assert len(data) == 1
#     assert data['status_code'] == 404
#     assert response.status_code == 404
#     cursor = postgresql_schema.cursor()
#     cursor.execute("SELECT count(*) FROM user_access")
#     record = cursor.fetchone()
#     assert record[0] == count + 1
#     cursor.execute("SELECT id, user_id, ip, url, method, params, result_code FROM user_access")
#     record = cursor.fetchone()
#     assert record[1] is None
#     assert record[2] == '127.0.0.1'
#     assert record[3] == 'http://localhost/api'
#     assert record[4] == 'GET'
#     assert record[5] == '{}'
#     assert record[6] == 404