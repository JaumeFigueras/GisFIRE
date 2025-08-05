#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from src.data_model import Base
from src.data_model.mixins.location import LocationMixIn
from src.data_model.mixins.date_time import DateTimeMixIn
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from sqlalchemy.orm import Mapped
from typing import List

class ThunderstormLightningAssociation(Base):
    __tablename__ = "thunderstorm_lightning_association"
    thunderstorm_id: Mapped[int] = mapped_column(ForeignKey("thunderstorm.id"), primary_key=True)
    lightning_id: Mapped[int] = mapped_column(ForeignKey("lightning.id"), primary_key=True)
    lightning: Mapped["Lightning"] = relationship(back_populates="thunderstorm_associations")
    thunderstorm: Mapped["Thunderstorm"] = relationship(back_populates="lightning_associations")



class Thunderstorm(Base, DateTimeMixIn, TimeStampMixIn):
    # Metaclass date attributes
    __date__ = [
        {'name': 'date_time_start', 'nullable': False},
        {'name': 'date_time_end', 'nullable': False},
    ]
    # Type hint for generated date and tzinfo attributes by the metaclass
    date_time_start: datetime.datetime
    tzinfo_date_time_start: str
    date_time_end: datetime.datetime
    tzinfo_date_time_end: str
    # Class data
    __tablename__ = "thunderstorm"
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    # Relations
    thunderstorm_experiment_id: Mapped[int] = mapped_column('thunderstorm_experiment_id', ForeignKey('thunderstorm_experiment.id'), nullable=False)
    thunderstorm_experiment: Mapped["ThunderstormExperiment"] = relationship(back_populates="thunderstorms")
    # many-to-many relationship to Child, bypassing the `Association` class
    lightnings: Mapped[List["Lightning"]] = relationship(secondary="thunderstorm_lightning_association", back_populates="thunderstorms")
    # association between Parent -> Association -> Child
    lightnings_associations: Mapped[List["ThunderstormLightningAssociation"]] = relationship(back_populates="thunderstorm")



