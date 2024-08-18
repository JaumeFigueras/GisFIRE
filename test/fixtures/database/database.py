#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import datetime
import pytz

from freezegun import freeze_time
from sqlalchemy import create_engine
from sqlalchemy import Engine
from sqlalchemy import event
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from contextlib import contextmanager


from src.data_model.data_provider import DataProvider
from src.data_model.user import User
from src.meteocat.data_model.weather_station import MeteocatWeatherStation
from src.meteocat.data_model.variable import MeteocatVariable
from src.meteocat.data_model.variable import MeteocatVariableState
from src.meteocat.data_model.variable import MeteocatVariableTimeBase
from src.bomberscat.data_model.wildfire_ignition import BomberscatWildfireIgnition
from src.data_model import Base

from typing import Any
from typing import Union
from typing import List
from typing import Optional


@pytest.fixture(scope='function')
def db_engine(postgresql_schema) -> Engine:
    """
    Yields a SQLAlchemy engine which is suppressed after the test session

    :param postgresql_schema: Postgresql database fixture
    :return: SqlAlchemy database engine
    """
    def db_creator():
        return postgresql_schema

    engine_ = create_engine('postgresql+psycopg://', creator=lambda: postgresql_schema)

    yield engine_

    engine_.dispose()


@pytest.fixture(scope='function')
def db_session_factory(db_engine: Engine) -> scoped_session[Union[Session, Any]]:
    """
    Returns a SQLAlchemy scoped session factory

    :param db_engine: SqlAlchemy database engine
    :return: A SqlAlchemy scoped session
    """
    return scoped_session(sessionmaker(bind=db_engine))


@pytest.fixture(scope='function')
def db_session(db_session_factory: scoped_session[Union[Session, Any]]) -> Session:
    """
    Yields a SQLAlchemy connection which is rollback after the test

    :param db_session_factory: A SqlAlchemy scoped session
    :return: A SqlAlchemy session
    """
    session_ = db_session_factory()

    yield session_

    session_.rollback()
    session_.close()


@contextmanager
def patch_time(time_to_freeze: str, tzinfo: Any = pytz.UTC, tick: bool = True):
    """
    Time Patcher for timestamps in Postgresql database
    :param time_to_freeze:
    :param tzinfo:
    :param tick:
    :return:
    """
    with freeze_time(time_to_freeze, tick=tick) as frozen_time:
        def set_timestamp(mapper, connection, target):
            now = datetime.datetime.now(tz=tzinfo)
            if hasattr(target, 'ts'):
                target.ts = now

        event.listen(Base, 'before_insert', set_timestamp, propagate=True)
        yield frozen_time
        event.remove(Base, 'before_insert', set_timestamp)


@pytest.fixture(scope='function')
def patch_postgresql_time():
    """
    Fixture time patcher for timestamps in Postgresql database
    :return:
    """
    return patch_time


def populate_data_providers(db_session: Session, data_providers: Union[List[DataProvider], None]) -> None:
    """
    Adds data providers data to the database
    """
    if data_providers is not None:
        db_session.add_all(data_providers)
        db_session.commit()


def populate_users(db_session: Session, user_list: Union[List[User], None]) -> None:
    """
    Adds data providers data to the database
    """
    if user_list is not None:
        db_session.add_all(user_list)
        db_session.commit()


def populate_meteocat_weather_stations(db_session: Session, meteocat_weather_stations: Union[List[MeteocatWeatherStation], None]) -> None:
    """
    Adds data providers data to the database
    """
    if meteocat_weather_stations is not None:
        db_session.add_all(meteocat_weather_stations)
        db_session.commit()


def populate_meteocat_variables(db_session: Session, meteocat_variables: Union[List[MeteocatVariable], None]) -> None:
    """
    Adds data providers data to the database
    """
    if meteocat_variables is not None:
        db_session.add_all(meteocat_variables)
        db_session.commit()


def populate_meteocat_variable_states(db_session: Session, meteocat_variable_states: Union[List[MeteocatVariableState], None]) -> None:
    """
    Adds data providers data to the database
    """
    if meteocat_variable_states is not None:
        db_session.add_all(meteocat_variable_states)
        db_session.commit()


def populate_meteocat_variable_time_bases(db_session: Session, meteocat_variable_time_bases: Union[List[MeteocatVariableTimeBase], None]) -> None:
    """
    Adds data providers data to the database
    """
    if meteocat_variable_time_bases is not None:
        db_session.add_all(meteocat_variable_time_bases)
        db_session.commit()


def populate_bomberscat_wildfire_ignitions(db_session: Session, bomberscat_wildfire_ignitions: Union[List[BomberscatWildfireIgnition], None]) -> None:
    """
    Adds data providers data to the database
    """
    if bomberscat_wildfire_ignitions is not None:
        db_session.add_all(bomberscat_wildfire_ignitions)
        db_session.commit()


#
# def populate_meteocat_assoc_states(db_session: Session, meteocat_assoc_states: Union[List[MeteocatAssociationStationVariableState], None]) -> None:
#     """
#     Adds data providers data to the database
#     """
#     if meteocat_assoc_states is not None:
#         db_session.add_all(meteocat_assoc_states)
#         db_session.commit()
#
#
# def populate_meteocat_assoc_time_bases(db_session: Session, meteocat_assoc_time_bases: Union[List[MeteocatAssociationStationVariableTimeBase], None]) -> None:
#     """
#     Adds data providers data to the database
#     """
#     if meteocat_assoc_time_bases is not None:
#         db_session.add_all(meteocat_assoc_time_bases)
#         db_session.commit()
#
