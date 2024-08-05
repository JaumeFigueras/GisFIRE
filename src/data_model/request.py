#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import json
import datetime

from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy import TypeDecorator
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import HSTORE

from typing import Optional
from typing import Dict
from typing import Union


class HashableMutableDict(MutableDict):
    def __hash__(self):
        text = json.dumps(self, sort_keys=True)
        return hash(text)


class HashableHSTORE(TypeDecorator):
    impl = HSTORE
    cache_ok = True

    def process_result_value(self, value, dialect):
        return HashableMutableDict(value)


class Request(Base):
    """
    Represents a request sent to a data provider
    """
    __tablename__ = 'request'
    uri: Mapped[str] = mapped_column('uri', String, primary_key=True)
    params: Mapped[MutableDict] = mapped_column('params', HashableMutableDict.as_mutable(HashableHSTORE), primary_key=True, default={})
    request_result: Mapped[int] = mapped_column('request_result', nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'), nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="requests")

    def __init__(self, uri: Optional[str] = None, params: Optional[Union[MutableDict, Dict]] = {},
                 request_result: Optional[int] = None, data_provider_name: Optional[str] = None) -> None:
        """
        TODO:
        """
        super().__init__()
        self.uri = uri
        self.params = params
        self.request_result = request_result
        self.data_provider_name = data_provider_name

