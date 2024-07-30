#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Creation of a declarative base for the SQL Alchemy models to inherit from
from sqlalchemy.orm import declarative_base

from src.data_model.metaclass.location_metaclass import LocationMeta


Base = declarative_base(metaclass=LocationMeta)


# Imports needed by SQL Alchemy to process the relations correctly
from src.data_model.data_provider import *  # noqa: E402
from src.data_model.request import *  # noqa: E402

