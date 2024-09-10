#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import datetime

from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.ext.mutable import MutableDict

from src.data_model import Base
from src.data_model import HashableMutableDict
from src.data_model import HashableHSTORE


class Experiment(Base):
    """
    Represents a experiment with the data
    """
    __tablename__ = 'experiment'
    name: Mapped[str] = mapped_column('name', String, primary_key=True)
    params: Mapped[MutableDict] = mapped_column('params', HashableMutableDict.as_mutable(HashableHSTORE), primary_key=True, default={})
    results: Mapped[MutableDict] = mapped_column('results', HashableMutableDict.as_mutable(HashableHSTORE), nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
