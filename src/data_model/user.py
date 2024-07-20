#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime
import random

from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from typing import Optional
from typing import List


class User(Base):
    """
    The class represents a user of GisFIRE
    """
    __tablename__ = 'user'
    id: Mapped[int] = mapped_column('id', primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column('username', unique=True, nullable=False)
    token: Mapped[str] = mapped_column('token', unique=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column('is_admin', nullable=False, default=False)
    valid_until: Mapped[datetime.datetime] = mapped_column('valid_until', nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user_accesses: Mapped[List["UserAccess"]] = relationship(back_populates="user")

    def __init__(self, username: Optional[str] = None, token: Optional[str] = None, is_admin: Optional[bool] = None,
                 valid_until: Optional[datetime.datetime] = None) -> None:
        """
        User constructor

        :param username:
        :param token:
        :param is_admin:
        :param valid_until:
        """
        super().__init__()
        self.username = username
        if token is None:
            self.token = self._generate_token()
        else:
            self.token = token
        self.is_admin = is_admin
        if valid_until is None:
            self.valid_until = self._generate_valid_until()
        else:
            self.valid_until = valid_until

    @staticmethod
    def _generate_token() -> str:
        """
        Adds a token to the user

        :return: A random token
        :rtype: str
        """
        chars: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!()_:;@?"
        length: int = 64
        token: str = ""
        for i in range(length):
            token += chars[random.randint(0, len(chars) - 1)]
        return token

    @staticmethod
    def _generate_valid_until() -> datetime.datetime:
        """
        Calculates a valid until date one year

        :return: Actual date plus one year
        :rtype: datetime.datetime
        """
        return datetime.datetime.now() + datetime.timedelta(days=365)
