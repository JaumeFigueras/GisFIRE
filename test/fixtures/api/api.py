#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from src.api import create_app


@pytest.fixture(scope="function")
def api(postgresql_schema):
    cursor = postgresql_schema.cursor()
    cursor.execute("SET SESSION AUTHORIZATION gisfire_user; SET ROLE gisfire_user;")
    postgresql_schema.commit()

    app = create_app(postgresql_schema)
    app.config['TESTING'] = True
    app.config['DEBUG'] = True

    with app.test_client() as client:
        yield client
