#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from src.data_model import Base
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy import Integer
from sqlalchemy import Enum
from sqlalchemy.orm import mapped_column
from sqlalchemy.dialects.postgresql import HSTORE
from enum import StrEnum

from sqlalchemy.orm import Mapped
from typing import Optional
from typing import Dict

class ThunderStormExperimentAlgorithm(StrEnum):
    """
    Enumeration of algorithms used in thunderstorm experiments.

    This enum defines various strategies for analyzing thunderstorm data,
    including time-based, distance-based, and clustering approaches.

    Attributes
    ----------
    TIME : str
        Clustering algorithm that considers only temporal proximity of events.
    DISTANCE : str
        Clustering algorithm that considers only spatial proximity of events.
    TIME_DISTANCE : str
        Clustering algorithm that combines both temporal and spatial proximity.
    DBSCAN_TIME : str
        DBSCAN clustering algorithm applied using time as the feature.
    DBSCAN_TIME_DISTANCE : str
        DBSCAN clustering algorithm applied using both time and distance features.
    """
    TIME = "TIME"
    DISTANCE = "DISTANCE"
    TIME_DISTANCE = "TIME_DISTANCE"
    DBSCAN_TIME = "DBSCAN_TIME"
    DBSCAN_TIME_DISTANCE = "DBSCAN_TIME_DISTANCE"


class ThunderstormExperiment(Base, TimeStampMixIn):
    # Metadata for SQLAlchemy
    __tablename__ = "thunderstorm_experiment"
    # Table columns
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    algorithm: Mapped[ThunderStormExperimentAlgorithm] = mapped_column('algorithm', Enum(ThunderStormExperimentAlgorithm, name="THUNDERSTORM_EXPERIMENT_ALGORITHM_ENUM", native_enum=True))
    parameters: Mapped[Optional[Dict[str, str]]] = mapped_column('parameters', HSTORE)
    # Relations
    thunderstorms: Mapped[List["ThunderStorm"]]

    def __init__(self, algorithm: Optional[str] = None, parameters: Optional[Dict[str, str]] = None) -> None:
        """
        Default constructor for a thunderstorm experiment.

        Parameters
        ----------
        algorithm: The name of the algorithm to use for the clustering
        parameters
        """
        self.algorithm = algorithm
        self.parameters = parameters