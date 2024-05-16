#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Creation of a declarative base for the SQL Alchemy models to inherit from
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Imports needed by SQL Alchemy to process the relations correctly
from src.data_model.data_provider import *  # noqa: E402
from src.data_model.lightning import *  # noqa: E402
from src.meteocat.data_model.lightning import *  # noqa: E402

