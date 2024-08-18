#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations  # Needed to allow returning type of enclosing class PEP 563

import enum
import datetime

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from shapely.geometry import Point

from src.data_model import Base
from src.data_model.mixins.location import LocationMixIn
from src.data_model.mixins.date_time import DateTimeMixIn
from src.data_model.mixins.time_stamp import TimeStampMixIn

from typing import Optional
from typing import Union


class WildfireIgnitionCategory(enum.StrEnum):
    LIGHTNING = 'LIGHTNING'
    AGRICOLE_BURNING = 'AGRICOLE_BURNING'
    PASTURE_BURNING = 'PASTURE_BURNING'
    FORESTRY_ACTIVITIES = 'FORESTRY_ACTIVITIES'
    BONFIRE = 'BONFIRE'
    SMOKERS = 'SMOKERS'
    GARBAGE_BURNING = 'GARBAGE_BURNING'
    LANDFILL = 'LANDFILL'
    STUBBLE_BURNING = 'STUBBLE_BURNING'
    OTHER_NEGLIGENCE = 'OTHER_NEGLIGENCE'
    RAILWAY = 'RAILWAY'
    ELECTRIC_LINES = 'ELECTRIC_LINES'
    ENGINES_OR_MACHINES = 'ENGINES_OR_MACHINES'
    MILITARY_MANEUVERS = 'MILITARY_MANEUVERS'
    OTHER_ACCIDENTS = 'OTHER_ACCIDENTS'
    INTENTIONAL = 'INTENTIONAL'
    UNKNOWN = 'UNKNOWN'
    REKINDLED_WILDFIRE = 'REKINDLED_WILDFIRE'


class WildfireIgnition(Base, LocationMixIn, DateTimeMixIn, TimeStampMixIn):
    # Metaclass location attributes
    __location__ = [
        {'epsg': 4326, 'validation': 'geographic', 'conversion': False}
    ]
    # Type hint fot generated attributes by the metaclass
    x_4326: float
    y_4326: float
    geometry_4326: Union[str, Point]
    # Metaclass date_time attributes
    __date__ = [
        {'name': 'start_date_time', 'nullable': False}
    ]
    # Type hint for generated attributes by the metaclass
    start_date_time: datetime.datetime
    tzinfo_start_date_time: str
    # SQLAlchemy columns
    __tablename__ = "wildfire_ignition"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column('name', String, nullable=False)
    ignition_cause: Mapped[WildfireIgnitionCategory] = mapped_column('ignition_cause', Enum(WildfireIgnitionCategory, name='wildfire_ignition_category'), nullable=False)
    type: Mapped[str]
    # SQLAlchemy relations
    data_provider_name: Mapped[str] = mapped_column('data_provider_name', ForeignKey('data_provider.name'),
                                                    nullable=False)
    data_provider: Mapped["DataProvider"] = relationship(back_populates="wildfire_ignitions")
    # SQLAlchemy Inheritance options
    __mapper_args__ = {
        "polymorphic_identity": "wildfire_ignition",
        "polymorphic_on": "type",
    }

    def __init__(self, name: Optional[str] = None, ignition_cause: Optional[WildfireIgnitionCategory] = None,
                 start_date_time: Optional[datetime.datetime] = None, longitude_epsg_4326: Optional[float] = None,
                 latitude_epsg_4326: Optional[float] = None) -> None:
        super().__init__()
        self.name = name
        self.ignition_cause = ignition_cause
        self.start_date_time = start_date_time
        self.x_4326 = longitude_epsg_4326
        self.y_4326 = latitude_epsg_4326

    def __iter__(self):
        yield 'id', self.id
        yield 'name', self.name
        yield 'ignition_cause', self.ignition_cause.name
        yield from LocationMixIn.__iter__(self)
        yield from DateTimeMixIn.__iter__(self)
        yield from TimeStampMixIn.__iter__(self)
        yield 'data_provider', self.data_provider_name
