#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Creation of a declarative base for the SQL Alchemy models to inherit from
from sqlalchemy.orm import declarative_base

from src.data_model.metaclass.model_metaclass import ModelMeta


Base = declarative_base(metaclass=ModelMeta)


# Imports needed by SQL Alchemy to process the relations correctly
from src.data_model.data_provider import *  # noqa: E402
from src.data_model.measure import *  # noqa: E402
from src.data_model.lightning import *  # noqa: E402
from src.data_model.weather_station import *  # noqa: E402
from src.data_model.variable import *  # noqa: E402
from src.data_model.request import *  # noqa: E402
