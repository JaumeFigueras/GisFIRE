#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import random
import enum

from ipaddress import IPv4Address

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import HSTORE

from src.data_model.user import User

from typing import Optional
from typing import Dict
from typing import Union


class HttpMethods(enum.StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    CONNECT = "CONNECT"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
    PATCH = "PATCH"


class UserAccess(Base):
    """
    The class represents a user of GisFIRE
    """
    __tablename__ = 'user_access'
    id: Mapped[int] = mapped_column('id', primary_key=True, autoincrement=True)
    ip: Mapped[IPv4Address] = mapped_column('ip', INET, nullable=False)
    url: Mapped[str] = mapped_column('url', nullable=False)
    method: Mapped[HttpMethods] = mapped_column('method', nullable=False)
    params: Mapped[MutableDict] = mapped_column('params', HSTORE, nullable=True)
    result: Mapped[int] = mapped_column('result', nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user_id: Mapped[Optional[int]] = mapped_column('user_id', ForeignKey('user.id'), nullable=True)
    user: Mapped[Optional["User"]] = relationship('User', back_populates='user_accesses')

    def __init__(self, ip: Optional[IPv4Address] = None, url: Optional[str] = None, method: Optional[HttpMethods] = None,
                 params: Union[MutableDict[str, str], Dict[str, str]] = None, result: Optional[int] = 500,
                 user: Optional[Union[int, User]] = None) -> None:
        """
        UserAccess constructor.

        :param ip:
        :param url:
        :param method:
        :param params:
        :param result:
        :param user:
        """
        super().__init__()
        self.ip = ip
        self.url = url
        self.method = method
        self.params = params
        self.result = result
        if isinstance(user, int):
            self.user_id = user
        elif isinstance(user, User):
            self.user_id = user.id
            self.user = user
        else:
            self.user_id = None
            self.user = None

