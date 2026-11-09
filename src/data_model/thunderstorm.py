#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thunderstorm models.

A thunderstorm is not observed: it is *inferred*, by grouping the lightning
strokes of one :class:`~src.data_model.data_provider.DataProvider` with some
clustering algorithm. The same strokes grouped by another algorithm, or by the
same one with other settings, give other thunderstorms. So every thunderstorm
belongs to the run that produced it, and the run records exactly how it was
produced.

Five tables
-----------

::

    data_provider 1──n thunderstorm_experiment 1──n thunderstorm 1──n thunderstorm_evolution
                               │ 1                    │ 1                 n │
                               └──n thunderstorm_tracking 1──────────────────┘
    lightning 1──n thunderstorm_lightning n──1 thunderstorm

:class:`ThunderstormExperiment`
    One run of a clustering algorithm: the provider, the strokes selected (a
    period and a filter), the algorithm and its parameters, and how the hulls
    were drawn.
:class:`Thunderstorm`
    One group the run found: its time span, its number of strokes and its
    concave hull.
:class:`ThunderstormLightning`
    Which strokes make up each thunderstorm. A stroke the algorithm left out
    (noise) has no row.
:class:`ThunderstormTracking`
    One run of the evolution on an experiment's thunderstorms: the window
    length and step, how windows are anchored, how a window's centre is
    computed. An experiment can be tracked any number of times with different
    windows without clustering again.
:class:`ThunderstormEvolution`
    One window of one thunderstorm in one tracking: its bounds, its number of
    strokes, its gravity centre and its concave hull.

The model assumes no algorithm. :attr:`ThunderstormExperiment.algorithm` is
free text and :attr:`ThunderstormExperiment.parameters` is JSONB, so a
multi-step method keeps one block per step.

Windows
-------

A window has a **length** *W* and a **step** *S*. With ``S < W`` the windows
overlap and each stroke falls in ``W/S`` of them: this is the window of a moving
average. With ``S = W`` they sit end to end (a fixed, or tumbling, window). Only
non-empty windows with at least
:attr:`ThunderstormTracking.min_lightnings` strokes get a row. A window's
strokes are not stored again: they are its thunderstorm's strokes with
``window_start <= date_time < window_end``.

What is derived and not stored
------------------------------

The direction vectors (the movement from one window's centre to the next), the
path (the line through the centres), the speeds and bearings, and the convex
hulls are all computed by the database views from what is stored here. They can
never disagree with it. A concave hull contains every stroke and its vertices
are strokes, so its convex hull *is* the convex hull of the strokes.

Integrity the database enforces
-------------------------------

* A stroke belongs to at most one thunderstorm per experiment.
* A link, and a window, cannot pair a thunderstorm with an experiment or a
  tracking it does not belong to: they carry ``experiment_id`` and reference
  ``(id, experiment_id)`` with composite foreign keys.
* The same configuration cannot be stored twice: each run is unique on its
  whole configuration, ``software_version`` included. ``jsonb`` compares by
  value, so the key order of a JSON setting does not make two runs different;
  the builder must store complete settings, defaults included, for the same
  reason.
* Deleting an experiment deletes everything it produced; deleting a tracking
  deletes its windows.
* A stroke that is in a thunderstorm cannot be deleted (``ON DELETE
  RESTRICT``). Re-importing a provider's year must first drop the experiments
  covering it.

What the database does not enforce, and the builder must: that a run's strokes
come from its provider and period, that a thunderstorm's strokes and its
windows lie within its time span, and that a window has at least
``min_lightnings`` strokes.

All instants are UTC ``timestamptz``, like
:attr:`~src.data_model.lightning.Lightning.date_time`; all geometries are
EPSG:4326, computed in the projected CRS named in the hull parameters.
"""

from __future__ import annotations

import datetime

from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.lightning import Lightning


class RunStatus(StrEnum):
    """Where an experiment or a tracking stands. Views show complete runs only."""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class WindowAnchor(StrEnum):
    """Where a tracking's windows start.

    ``clock`` starts them at multiples of the step (10:00, 10:02 …), so windows
    line up across thunderstorms and with other data; ``storm_start`` starts
    them at each thunderstorm's first stroke.
    """

    CLOCK = "clock"
    STORM_START = "storm_start"


class CentreMethod(StrEnum):
    """How a window's gravity centre is computed from its strokes.

    ``mean`` is the plain mean of their coordinates in the projected CRS.
    """

    MEAN = "mean"


#: The concave-hull settings used unless a run says otherwise: the target
#: ratio of PostGIS ``ST_ConcaveHull`` and no holes. The builder adds the
#: projected ``srid`` the hull is computed in.
DEFAULT_HULL_PARAMETERS: dict[str, Any] = {"ratio": 0.3, "allow_holes": False}


def _in(column: str, values: type[StrEnum]) -> str:
    """``column IN ('a', 'b', …)``, for a ``CHECK``."""
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _completed(table: str) -> CheckConstraint:
    """A run has a completion instant exactly when it is complete."""
    return CheckConstraint(
        f"(status = '{RunStatus.COMPLETE}') = (completed_at IS NOT NULL)",
        name=f"ck_{table}_completed_at",
    )


def _object(table: str, column: str) -> CheckConstraint:
    """A JSON setting is an object: not a bare ``null``, number, string or array."""
    return CheckConstraint(f"jsonb_typeof({column}) = 'object'", name=f"ck_{table}_{column}")


#: JSONB that stores a Python ``None`` as SQL ``NULL`` (refused by ``NOT NULL``)
#: rather than as the JSON value ``null``.
_JSON = JSONB(none_as_null=True)


def _default_hull_parameters() -> dict[str, Any]:
    return dict(DEFAULT_HULL_PARAMETERS)


class ThunderstormExperiment(Base):
    """One run of a clustering algorithm over one provider's strokes.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key.
    data_provider_id : int
        Foreign key to the :class:`~src.data_model.data_provider.DataProvider`
        whose strokes were clustered. A run never mixes providers.
    data_provider : DataProvider
        That provider.
    algorithm : str
        Name of the clustering method, free text (``"DBSCAN"``,
        ``"HAYWARD_2023"`` …), so a new method needs no migration.
    parameters : dict
        The method's settings, complete (defaults included), as JSONB.
    lightning_filter : dict
        Which of the provider's strokes in the period were clustered, complete,
        as JSONB (for MeteoCat, for example ``{"stroke_index": 1, "network":
        "newest"}``). ``{}`` means all of them.
    hull_parameters : dict
        How the concave hulls were drawn, as JSONB; defaults to
        :data:`DEFAULT_HULL_PARAMETERS`.
    date_time_start, date_time_end : datetime.datetime
        The period of strokes read, half-open: ``start <= date_time < end``.
        Indexed with the provider, for the importer's overlap check.
    software_version : str
        The GisFIRE version that produced the run. Part of the run's identity:
        the same configuration may be run again with other code, not with the
        same.
    status : str
        A :class:`RunStatus`; ``running`` on insert.
    completed_at : datetime.datetime or None
        When the run completed; set exactly when ``status`` is ``complete``.
    thunderstorms : list[Thunderstorm]
        The thunderstorms the run found.
    trackings : list[ThunderstormTracking]
        The evolutions computed on them.
    created_at, updated_at : datetime.datetime
        Timezone-aware timestamps, set by the database.
    """

    __tablename__ = "thunderstorm_experiment"

    __table_args__ = (
        CheckConstraint("date_time_end > date_time_start",
                        name="ck_thunderstorm_experiment_period"),
        CheckConstraint("algorithm <> ''", name="ck_thunderstorm_experiment_algorithm"),
        CheckConstraint("software_version <> ''",
                        name="ck_thunderstorm_experiment_software_version"),
        CheckConstraint(_in("status", RunStatus), name="ck_thunderstorm_experiment_status"),
        _completed("thunderstorm_experiment"),
        _object("thunderstorm_experiment", "parameters"),
        _object("thunderstorm_experiment", "lightning_filter"),
        _object("thunderstorm_experiment", "hull_parameters"),
        UniqueConstraint("data_provider_id", "algorithm", "parameters", "lightning_filter",
                         "hull_parameters", "date_time_start", "date_time_end",
                         "software_version",
                         name="uq_thunderstorm_experiment_configuration"),
        Index("ix_thunderstorm_experiment_period",
              "data_provider_id", "date_time_start", "date_time_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_provider_id: Mapped[int] = mapped_column(ForeignKey(DataProvider.id), nullable=False)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    lightning_filter: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    hull_parameters: Mapped[dict[str, Any]] = mapped_column(
        _JSON, nullable=False, default=_default_hull_parameters
    )
    date_time_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_time_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    software_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=RunStatus.RUNNING.value,
        server_default=text(f"'{RunStatus.RUNNING}'"),
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_provider: Mapped[DataProvider] = relationship()
    thunderstorms: Mapped[list[Thunderstorm]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True
    )
    trackings: Mapped[list[ThunderstormTracking]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return (f"ThunderstormExperiment(id={self.id!r}, algorithm={self.algorithm!r}, "
                f"status={self.status!r})")


class Thunderstorm(Base):
    """One group of strokes found by an experiment.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key.
    experiment_id : int
        Foreign key to the :class:`ThunderstormExperiment` that found it;
        deleting the experiment deletes it.
    experiment : ThunderstormExperiment
        That experiment.
    label : int
        The group's label in its run, unique within the run.
    date_time_start, date_time_end : datetime.datetime
        Its first and last stroke (equal for a one-stroke group).
    number_of_lightnings : int
        How many strokes make it up, at least one.
    concave_hull : geoalchemy2.elements.WKBElement or None
        The concave hull of its strokes, a ``POLYGON`` in EPSG:4326, computed
        in the projected CRS of the experiment's hull parameters. ``None`` when
        the hull is not a polygon — fewer than three strokes, or all in a line.
        Indexed (GiST).
    lightning_links : list[ThunderstormLightning]
        Its rows in ``thunderstorm_lightning``.
    lightnings : list[Lightning]
        Its strokes, in time order (read-only; add links to change them).
    evolutions : list[ThunderstormEvolution]
        Its windows, in every tracking.
    created_at, updated_at : datetime.datetime
        Timezone-aware timestamps, set by the database.
    """

    __tablename__ = "thunderstorm"

    __table_args__ = (
        CheckConstraint("date_time_end >= date_time_start", name="ck_thunderstorm_period"),
        CheckConstraint("number_of_lightnings >= 1", name="ck_thunderstorm_number_of_lightnings"),
        UniqueConstraint("experiment_id", "label", name="uq_thunderstorm_experiment_label"),
        # The target of the composite foreign keys of the links and the windows.
        UniqueConstraint("id", "experiment_id", name="uq_thunderstorm_id_experiment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey(ThunderstormExperiment.id, ondelete="CASCADE"), nullable=False
    )
    label: Mapped[int] = mapped_column(Integer, nullable=False)
    date_time_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_time_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    number_of_lightnings: Mapped[int] = mapped_column(Integer, nullable=False)
    concave_hull: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    experiment: Mapped[ThunderstormExperiment] = relationship(back_populates="thunderstorms")
    lightning_links: Mapped[list[ThunderstormLightning]] = relationship(
        back_populates="thunderstorm", cascade="all, delete-orphan", passive_deletes=True,
        overlaps="experiment,thunderstorms",
    )
    lightnings: Mapped[list[Lightning]] = relationship(
        secondary="thunderstorm_lightning",
        primaryjoin="Thunderstorm.id == ThunderstormLightning.thunderstorm_id",
        secondaryjoin="Lightning.id == ThunderstormLightning.lightning_id",
        order_by=Lightning.date_time,
        viewonly=True,
    )
    evolutions: Mapped[list[ThunderstormEvolution]] = relationship(
        back_populates="thunderstorm", cascade="all, delete-orphan", passive_deletes=True,
        overlaps="evolutions,tracking",
    )

    def __repr__(self) -> str:
        return (f"Thunderstorm(id={self.id!r}, experiment_id={self.experiment_id!r}, "
                f"label={self.label!r})")


class ThunderstormLightning(Base):
    """A stroke of a thunderstorm.

    ``experiment_id`` repeats the thunderstorm's, so that the database can keep
    a stroke in at most one thunderstorm per experiment; the composite foreign
    key to ``thunderstorm(id, experiment_id)`` keeps the copy right. It is set
    from the thunderstorm when the link is made through
    :attr:`thunderstorm`.

    Attributes
    ----------
    thunderstorm_id : int
        The thunderstorm; deleting it deletes the link.
    experiment_id : int
        The thunderstorm's experiment.
    lightning_id : int
        The stroke. A stroke with links cannot be deleted (``RESTRICT``).
        Indexed.
    thunderstorm : Thunderstorm
    lightning : Lightning
    """

    __tablename__ = "thunderstorm_lightning"

    __table_args__ = (
        ForeignKeyConstraint(
            ["thunderstorm_id", "experiment_id"], ["thunderstorm.id", "thunderstorm.experiment_id"],
            ondelete="CASCADE", name="fk_thunderstorm_lightning_thunderstorm",
        ),
        UniqueConstraint("experiment_id", "lightning_id",
                         name="uq_thunderstorm_lightning_experiment_lightning"),
        Index("ix_thunderstorm_lightning_lightning_id", "lightning_id"),
    )

    thunderstorm_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lightning_id: Mapped[int] = mapped_column(
        ForeignKey(Lightning.id, ondelete="RESTRICT"), primary_key=True
    )
    experiment_id: Mapped[int] = mapped_column(Integer, nullable=False)

    thunderstorm: Mapped[Thunderstorm] = relationship(
        back_populates="lightning_links", overlaps="experiment,thunderstorms"
    )
    lightning: Mapped[Lightning] = relationship()

    def __repr__(self) -> str:
        return (f"ThunderstormLightning(thunderstorm_id={self.thunderstorm_id!r}, "
                f"lightning_id={self.lightning_id!r})")


class ThunderstormTracking(Base):
    """One computation of the evolution of an experiment's thunderstorms.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key.
    experiment_id : int
        The experiment whose thunderstorms are tracked; deleting it deletes the
        tracking.
    experiment : ThunderstormExperiment
    window_length : datetime.timedelta
        How much time a window covers, *W*.
    window_step : datetime.timedelta
        How far a window moves each time, *S*: ``0 < S <= W``. ``S < W`` is a
        moving-average (sliding) window, ``S = W`` a fixed one.
    window_anchor : str
        A :class:`WindowAnchor`; ``clock`` by default.
    min_lightnings : int
        The fewest strokes a window needs to get a row, at least one; 1 by
        default.
    centre_method : str
        A :class:`CentreMethod`; ``mean`` by default.
    hull_parameters : dict
        How the windows' concave hulls were drawn, as JSONB; defaults to
        :data:`DEFAULT_HULL_PARAMETERS`.
    software_version : str
        The GisFIRE version that produced it; part of its identity.
    status : str
        A :class:`RunStatus`; ``running`` on insert.
    completed_at : datetime.datetime or None
        When it completed; set exactly when ``status`` is ``complete``.
    evolutions : list[ThunderstormEvolution]
        Its windows.
    created_at, updated_at : datetime.datetime
        Timezone-aware timestamps, set by the database.
    """

    __tablename__ = "thunderstorm_tracking"

    __table_args__ = (
        CheckConstraint("window_step > INTERVAL '0' AND window_step <= window_length",
                        name="ck_thunderstorm_tracking_window"),
        CheckConstraint("min_lightnings >= 1", name="ck_thunderstorm_tracking_min_lightnings"),
        CheckConstraint(_in("window_anchor", WindowAnchor),
                        name="ck_thunderstorm_tracking_window_anchor"),
        CheckConstraint(_in("centre_method", CentreMethod),
                        name="ck_thunderstorm_tracking_centre_method"),
        CheckConstraint("software_version <> ''",
                        name="ck_thunderstorm_tracking_software_version"),
        CheckConstraint(_in("status", RunStatus), name="ck_thunderstorm_tracking_status"),
        _completed("thunderstorm_tracking"),
        _object("thunderstorm_tracking", "hull_parameters"),
        UniqueConstraint("experiment_id", "window_length", "window_step", "window_anchor",
                         "min_lightnings", "centre_method", "hull_parameters", "software_version",
                         name="uq_thunderstorm_tracking_configuration"),
        # The target of the windows' composite foreign key.
        UniqueConstraint("id", "experiment_id", name="uq_thunderstorm_tracking_id_experiment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey(ThunderstormExperiment.id, ondelete="CASCADE"), nullable=False
    )
    window_length: Mapped[datetime.timedelta] = mapped_column(Interval, nullable=False)
    window_step: Mapped[datetime.timedelta] = mapped_column(Interval, nullable=False)
    window_anchor: Mapped[str] = mapped_column(
        String, nullable=False, default=WindowAnchor.CLOCK.value,
        server_default=text(f"'{WindowAnchor.CLOCK}'"),
    )
    min_lightnings: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    centre_method: Mapped[str] = mapped_column(
        String, nullable=False, default=CentreMethod.MEAN.value,
        server_default=text(f"'{CentreMethod.MEAN}'"),
    )
    hull_parameters: Mapped[dict[str, Any]] = mapped_column(
        _JSON, nullable=False, default=_default_hull_parameters
    )
    software_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=RunStatus.RUNNING.value,
        server_default=text(f"'{RunStatus.RUNNING}'"),
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    experiment: Mapped[ThunderstormExperiment] = relationship(back_populates="trackings")
    evolutions: Mapped[list[ThunderstormEvolution]] = relationship(
        back_populates="tracking", cascade="all, delete-orphan", passive_deletes=True,
        overlaps="evolutions,thunderstorm",
    )

    def __repr__(self) -> str:
        return (f"ThunderstormTracking(id={self.id!r}, experiment_id={self.experiment_id!r}, "
                f"window_length={self.window_length!r}, window_step={self.window_step!r})")


class ThunderstormEvolution(Base):
    """One window of one thunderstorm in one tracking.

    It carries ``experiment_id`` so that two composite foreign keys, to
    ``thunderstorm(id, experiment_id)`` and to ``thunderstorm_tracking(id,
    experiment_id)``, guarantee the thunderstorm and the tracking belong to the
    same experiment. It is set from either when the window is made through
    :attr:`thunderstorm` or :attr:`tracking`.

    Attributes
    ----------
    id : int
        Surrogate autoincrement primary key.
    tracking_id : int
        The tracking; deleting it deletes the window.
    thunderstorm_id : int
        The thunderstorm; deleting it deletes the window. Indexed.
    experiment_id : int
        The experiment of both.
    sequence : int
        The window's place in its thunderstorm's evolution, from 1 in time
        order; unique per tracking and thunderstorm.
    window_start, window_end : datetime.datetime
        The window's bounds, half-open: ``start <= date_time < end``.
    number_of_lightnings : int
        How many of the thunderstorm's strokes fall in it, at least one.
    centre : geoalchemy2.elements.WKBElement
        Its gravity centre, a ``POINT`` in EPSG:4326. Indexed (GiST).
    concave_hull : geoalchemy2.elements.WKBElement or None
        The concave hull of its strokes, a ``POLYGON`` in EPSG:4326; ``None``
        when it is not a polygon. Indexed (GiST).
    tracking : ThunderstormTracking
    thunderstorm : Thunderstorm
    created_at, updated_at : datetime.datetime
        Timezone-aware timestamps, set by the database.
    """

    __tablename__ = "thunderstorm_evolution"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tracking_id", "experiment_id"],
            ["thunderstorm_tracking.id", "thunderstorm_tracking.experiment_id"],
            ondelete="CASCADE", name="fk_thunderstorm_evolution_tracking",
        ),
        ForeignKeyConstraint(
            ["thunderstorm_id", "experiment_id"], ["thunderstorm.id", "thunderstorm.experiment_id"],
            ondelete="CASCADE", name="fk_thunderstorm_evolution_thunderstorm",
        ),
        CheckConstraint("sequence >= 1", name="ck_thunderstorm_evolution_sequence"),
        CheckConstraint("window_end > window_start", name="ck_thunderstorm_evolution_window"),
        CheckConstraint("number_of_lightnings >= 1",
                        name="ck_thunderstorm_evolution_number_of_lightnings"),
        UniqueConstraint("tracking_id", "thunderstorm_id", "sequence",
                         name="uq_thunderstorm_evolution_sequence"),
        Index("ix_thunderstorm_evolution_thunderstorm_id", "thunderstorm_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thunderstorm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    experiment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    number_of_lightnings: Mapped[int] = mapped_column(Integer, nullable=False)
    centre: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    concave_hull: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tracking: Mapped[ThunderstormTracking] = relationship(
        back_populates="evolutions", overlaps="evolutions,thunderstorm"
    )
    thunderstorm: Mapped[Thunderstorm] = relationship(
        back_populates="evolutions", overlaps="evolutions,tracking"
    )

    def __repr__(self) -> str:
        return (f"ThunderstormEvolution(id={self.id!r}, tracking_id={self.tracking_id!r}, "
                f"thunderstorm_id={self.thunderstorm_id!r}, sequence={self.sequence!r})")
