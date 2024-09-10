#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import TypeDecorator
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import HSTORE

from src.data_model.metaclass.model_metaclass import ModelMeta


# Creation of a declarative base for the SQL Alchemy models to inherit from
Base = declarative_base(metaclass=ModelMeta)


class HashableMutableDict(MutableDict):
    def __hash__(self):
        text = json.dumps(self, sort_keys=True)
        return hash(text)


class HashableHSTORE(TypeDecorator):
    impl = HSTORE
    cache_ok = True

    def process_result_value(self, value, dialect):
        return HashableMutableDict(value)


# Imports needed by SQL Alchemy to process the relations correctly
from src.data_model.data_provider import *  # noqa: E402
from src.data_model.measure import *  # noqa: E402
from src.data_model.lightning import *  # noqa: E402
from src.data_model.weather_station import *  # noqa: E402
from src.data_model.variable import *  # noqa: E402
from src.data_model.request import *  # noqa: E402
from src.data_model.wildfire_ignition import *  # noqa: E402
