#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared test fixtures.

Spins up an ephemeral PostgreSQL instance per test (via ``pytest-postgresql``),
enables PostGIS and builds the schema from the ORM metadata with
``Base.metadata.create_all``.
"""

import pytest

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.data_model import Base


@pytest.fixture
def db_session(postgresql):
    """Yield a SQLAlchemy ``Session`` bound to an ephemeral PostgreSQL database.

    The schema is (re)created from ``Base.metadata`` for each test, so tests are
    fully isolated.
    """
    info = postgresql.info
    url = f"postgresql+psycopg://{info.user}:{info.password or ''}@{info.host}:{info.port}/{info.dbname}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
