#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import json
import datetime

from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import HSTORE

from typing import Optional
from typing import Dict
from typing import Any
from typing import Union


class Request(Base):
    """
    Represents a request sent to a data provider
    """
    __tablename__ = 'request'
    uri: Mapped[str] = mapped_column('uri', String, primary_key=True)
    params: Mapped[str] = mapped_column('params', MutableDict.as_mutable(HSTORE), primary_key=True)
    request_result: Mapped[int] = mapped_column('request_result', nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'), nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="requests")

    def __init__(self, symbol: Optional[str] = None, request_from_date: Optional[datetime.date] = None,
                 request_to_date: Optional[datetime.date] = None, request_result: Optional[int] = None):
        super().__init__()
        self.symbol = symbol
        self.request_from_date = request_from_date
        self.request_to_date = request_to_date
        self.request_result = request_result

