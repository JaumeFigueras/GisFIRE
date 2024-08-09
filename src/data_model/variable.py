#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.data_model import Base
from src.data_model.mixins.time_stamp import TimeStampMixIn

from typing import Optional
from typing import Iterator
from typing import Any


class Variable(Base, TimeStampMixIn):
    # SQLAlchemy columns
    __tablename__ = "variable"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column('name', String, nullable=False)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="variables")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "variable",
        "polymorphic_on": "type",
    }

    def __init__(self, name: Optional[str] = None) -> None:
        """
        Class constructor

        :param name: The name of the variable
        :type name: str
        :return: None
        """
        super().__init__()
        self.name = name

    def __iter__(self) -> Iterator[str, Any]:
        """
        Class iterator to convert the object to a dict

        :return: The attributes that define the class
        """
        yield 'id', self.id
        yield 'name', self.name
        yield from TimeStampMixIn.__iter__(self)
