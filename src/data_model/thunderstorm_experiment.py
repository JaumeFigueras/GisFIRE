#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from src.data_model import Base
from src.data_model.mixins.time_stamp import TimeStampMixIn

from sqlalchemy import Integer
from sqlalchemy import Enum
from sqlalchemy.orm import mapped_column, relationship
from sqlalchemy.dialects.postgresql import HSTORE
from enum import StrEnum

from sqlalchemy.orm import Mapped
from typing import Optional
from typing import Dict
from typing import List

class ThunderstormExperimentAlgorithm(StrEnum):
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
    """
    Represents a thunderstorm experiment configuration and its associated data.

    This class models the metadata and relationships for a single thunderstorm
    experiment. Each experiment uses a specific clustering algorithm to
    analyze thunderstorm data and stores parameters relevant to the analysis.

    Attributes
    ----------
    id : int
        Unique identifier for the experiment (primary key).
    algorithm : :class:`~src.data_model.thunderstorm_experiment.ThunderstormExperimentAlgorithm`
        Clustering algorithm applied to the thunderstorm data.
    parameters : dict of str, str
        Key-value pairs specifying configuration parameters for the experiment algorithm.
    thunderstorms : list of :class:`Thunderstorm`
        List of thunderstorm events associated with this experiment.

    See Also
    --------
    :class:`~src.data_model.thunderstorm_experiment.ThunderstormExperimentAlgorithm`
        Enum of available clustering algorithms used for analysis.
    :class:`~src.data_model.thunderstorm.Thunderstorm`
        Model representing individual thunderstorm records linked to an experiment.
    """
    # Metadata for SQLAlchemy
    __tablename__ = "thunderstorm_experiment"
    # Table columns
    id: Mapped[int] = mapped_column('id', Integer, primary_key=True, autoincrement=True)
    algorithm: Mapped[ThunderstormExperimentAlgorithm] = mapped_column('algorithm', Enum(ThunderstormExperimentAlgorithm, name="THUNDERSTORM_EXPERIMENT_ALGORITHM_ENUM", native_enum=True))
    parameters: Mapped[Optional[Dict[str, str]]] = mapped_column('parameters', HSTORE, nullable=False)
    # Relations
    thunderstorms: Mapped[List["Thunderstorm"]] = relationship(back_populates="thunderstorm_experiment")

    def __init__(self, algorithm: Optional[ThunderstormExperimentAlgorithm] = None, parameters: Optional[Dict[str, str]] = None) -> None:
        """
        Initialize a ThunderstormExperiment instance with optional algorithm and parameters.

        Parameters
        ----------
        algorithm : Optional[:class:`~src.data_model.thunderstorm_experiment.ThunderstormExperimentAlgorithm`]
            Clustering algorithm to be applied during the experiment.
        parameters : Optional[dict of str, str]
            Dictionary of configuration parameters relevant to the experiment algorithm.

        Notes
        -----
        This constructor sets up the base metadata for a thunderstorm experiment,
        including which algorithm is used to cluster thunderstorm data and any
        additional settings passed as key-value pairs.

        See Also
        --------
        :class:`~src.data_model.thunderstorm_experiment.ThunderstormExperimentAlgorithm`
            Enumeration of supported clustering strategies.
        :class:`~src.data_model.thunderstorm_experiment.ThunderstormExperiment`
            The enclosing experiment model class.
        """
        super().__init__()
        self.algorithm = algorithm
        self.parameters = parameters