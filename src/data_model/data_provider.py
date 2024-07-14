#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from . import Base

import datetime

from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from typing import Optional
from typing import List


class DataProvider(Base):
    """
    The class represents a data provider of GisFIRE
    """
    __tablename__ = 'data_provider'
    name: Mapped[str] = mapped_column('name', primary_key=True)
    description: Mapped[str] = mapped_column('description')
    url: Mapped[str] = mapped_column('url')
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lightnings: Mapped[List["Lightning"]] = relationship(back_populates="data_provider")
    requests: Mapped[List["Request"]] = relationship(back_populates="data_provider")

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None,
                 url: Optional[str] = None) -> None:
        """
        Data provider constructor

        :param name: The representative name of the data provider
        :type name: Optional[str]
        :param description: The description of the data provider
        :type description: Optional[str]
        :param url: The website URL od the data provider
        :type url: Optional[str]
        """
        super().__init__()
        self.name = name
        self.description = description
        self.url = url
