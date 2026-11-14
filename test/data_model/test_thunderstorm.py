#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the thunderstorm models.

What is pinned down is what the database must enforce on its own, because the
builder that fills these tables is not written yet and a later one must not be
able to get it wrong: one thunderstorm per stroke per experiment, no link or
window across experiments, no configuration stored twice (JSON compared by
value), the cascades from a run to everything it produced, and that a stroke in
a thunderstorm cannot be deleted from under it.
"""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.geometry import Polygon
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.lightning import Lightning
from src.data_model.thunderstorm import DEFAULT_HULL_PARAMETERS
from src.data_model.thunderstorm import CentreMethod
from src.data_model.thunderstorm import RunStatus
from src.data_model.thunderstorm import Thunderstorm
from src.data_model.thunderstorm import ThunderstormEvolution
from src.data_model.thunderstorm import ThunderstormExperiment
from src.data_model.thunderstorm import ThunderstormLightning
from src.data_model.thunderstorm import ThunderstormTracking
from src.data_model.thunderstorm import WindowAnchor

UTC = datetime.timezone.utc

START = datetime.datetime(2015, 1, 1, tzinfo=UTC)
END = datetime.datetime(2016, 1, 1, tzinfo=UTC)
#: A storm over the Penedès, 2015-07-01 14:00 to 14:42 UTC.
STORM_START = datetime.datetime(2015, 7, 1, 14, 0, tzinfo=UTC)
STORM_END = datetime.datetime(2015, 7, 1, 14, 42, tzinfo=UTC)
HULL = "SRID=4326;POLYGON((1.6 41.3, 1.9 41.3, 1.9 41.5, 1.6 41.5, 1.6 41.3))"
CENTRE = "SRID=4326;POINT(1.75 41.4)"

ALL_TABLES = (ThunderstormExperiment, Thunderstorm, ThunderstormLightning,
              ThunderstormTracking, ThunderstormEvolution)


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------

@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="MeteoCat", product="XDDE", full_name="Servei Meteorològic de Catalunya")
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def other_provider(db_session):
    provider = DataProvider(name="Other", product="Lightning", full_name="Another network")
    db_session.add(provider)
    db_session.commit()
    return provider


def an_experiment(provider, **overrides) -> ThunderstormExperiment:
    values = {
        "data_provider_id": provider.id,
        "algorithm": "DBSCAN",
        "parameters": {"eps_m": 10000, "eps_s": 1800, "min_samples": 5},
        "lightning_filter": {"stroke_index": 1, "network": "newest"},
        "date_time_start": START,
        "date_time_end": END,
        "software_version": "0.1.0+abc1234",
    }
    values.update(overrides)
    return ThunderstormExperiment(**values)


def a_storm(experiment, **overrides) -> Thunderstorm:
    values = {
        "experiment": experiment,
        "label": 0,
        "date_time_start": STORM_START,
        "date_time_end": STORM_END,
        "number_of_lightnings": 3,
        "concave_hull": HULL,
    }
    values.update(overrides)
    return Thunderstorm(**values)


def a_tracking(experiment, **overrides) -> ThunderstormTracking:
    values = {
        "experiment": experiment,
        "window_length": datetime.timedelta(minutes=10),
        "window_step": datetime.timedelta(minutes=2),
        "software_version": "0.1.0+abc1234",
    }
    values.update(overrides)
    return ThunderstormTracking(**values)


def a_window(tracking, storm, **overrides) -> ThunderstormEvolution:
    values = {
        "tracking": tracking,
        "thunderstorm": storm,
        "sequence": 1,
        "window_start": STORM_START,
        "window_end": STORM_START + datetime.timedelta(minutes=10),
        "number_of_lightnings": 2,
        "centre": CENTRE,
        "concave_hull": None,
    }
    values.update(overrides)
    return ThunderstormEvolution(**values)


def a_stroke(provider, minute: int = 0) -> Lightning:
    return Lightning(data_provider_id=provider.id,
                     date_time=STORM_START + datetime.timedelta(minutes=minute),
                     geometry="SRID=4326;POINT(1.7 41.4)", peak_current=-20.0, cloud_to_ground=True)


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


@pytest.fixture
def experiment(db_session, provider):
    experiment = an_experiment(provider)
    db_session.add(experiment)
    db_session.commit()
    return experiment


@pytest.fixture
def storm(db_session, experiment):
    storm = a_storm(experiment)
    db_session.add(storm)
    db_session.commit()
    return storm


@pytest.fixture
def tracking(db_session, experiment):
    tracking = a_tracking(experiment)
    db_session.add(tracking)
    db_session.commit()
    return tracking


@pytest.fixture
def strokes(db_session, provider):
    strokes = [a_stroke(provider, minute) for minute in (40, 0, 20)]
    db_session.add_all(strokes)
    db_session.commit()
    return strokes


@pytest.fixture
def everything(db_session, provider, strokes):
    """An experiment with a storm, its strokes, a tracking and two windows."""
    experiment = an_experiment(provider)
    storm = a_storm(experiment)
    storm.lightning_links = [ThunderstormLightning(lightning=stroke) for stroke in strokes]
    tracking = a_tracking(experiment)
    db_session.add_all([experiment, storm, tracking,
                        a_window(tracking, storm, sequence=1),
                        a_window(tracking, storm, sequence=2,
                                 window_start=STORM_START + datetime.timedelta(minutes=2),
                                 window_end=STORM_START + datetime.timedelta(minutes=12))])
    db_session.commit()
    return experiment


# --------------------------------------------------------------------------
# Experiment
# --------------------------------------------------------------------------

def test_an_experiment_persists_and_reads_back(db_session, experiment):
    db_session.expire_all()
    stored = db_session.scalar(select(ThunderstormExperiment))
    assert stored.data_provider.name == "MeteoCat"
    assert stored.algorithm == "DBSCAN"
    assert stored.parameters == {"eps_m": 10000, "eps_s": 1800, "min_samples": 5}
    assert stored.lightning_filter == {"stroke_index": 1, "network": "newest"}
    assert (stored.date_time_start, stored.date_time_end) == (START, END)
    assert stored.software_version == "0.1.0+abc1234"


def test_an_experiment_starts_running_with_the_default_hull(db_session, experiment):
    db_session.expire_all()
    stored = db_session.scalar(select(ThunderstormExperiment))
    assert stored.status == RunStatus.RUNNING
    assert stored.completed_at is None
    assert stored.hull_parameters == DEFAULT_HULL_PARAMETERS == {"ratio": 0.3, "allow_holes": False}


def test_the_default_hull_is_not_shared_between_runs(db_session, provider):
    """Each run gets its own copy: changing one must not change another or the default."""
    first = an_experiment(provider)
    second = an_experiment(provider, algorithm="HDBSCAN")
    db_session.add_all([first, second])
    db_session.flush()
    assert first.hull_parameters == second.hull_parameters == DEFAULT_HULL_PARAMETERS
    assert first.hull_parameters is not second.hull_parameters
    assert first.hull_parameters is not DEFAULT_HULL_PARAMETERS


def test_an_empty_filter_means_every_stroke(db_session, provider):
    experiment = an_experiment(provider)
    del experiment.lightning_filter
    db_session.add(experiment)
    db_session.commit()
    db_session.expire_all()
    assert db_session.scalar(select(ThunderstormExperiment)).lightning_filter == {}


def test_any_algorithm_name_is_accepted(db_session, provider):
    """The model assumes no method: a new one needs no migration."""
    db_session.add(an_experiment(provider, algorithm="HAYWARD_2023",
                                 parameters={"step_1": {"eps_m": 5000}, "step_2": {"overlap": 0.5}}))
    db_session.commit()
    db_session.expire_all()
    assert db_session.scalar(select(ThunderstormExperiment)).parameters["step_2"] == {"overlap": 0.5}


@pytest.mark.parametrize("status", list(RunStatus))
def test_every_status_is_accepted(db_session, provider, status):
    completed = datetime.datetime(2026, 11, 8, tzinfo=UTC) if status == RunStatus.COMPLETE else None
    db_session.add(an_experiment(provider, status=status.value, completed_at=completed))
    db_session.commit()


def test_an_unknown_status_is_refused(db_session, provider):
    db_session.add(an_experiment(provider, status="paused"))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_experiment_status"):
        db_session.commit()


@pytest.mark.parametrize(("status", "completed_at"), [
    pytest.param("complete", None, id="complete-without-instant"),
    pytest.param("running", datetime.datetime(2026, 11, 8, tzinfo=UTC), id="running-with-instant"),
    pytest.param("failed", datetime.datetime(2026, 11, 8, tzinfo=UTC), id="failed-with-instant"),
])
def test_completed_at_is_set_exactly_when_complete(db_session, provider, status, completed_at):
    db_session.add(an_experiment(provider, status=status, completed_at=completed_at))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_experiment_completed_at"):
        db_session.commit()


@pytest.mark.parametrize("end", [START, START - datetime.timedelta(seconds=1)],
                         ids=["empty", "reversed"])
def test_the_period_must_not_be_empty(db_session, provider, end):
    db_session.add(an_experiment(provider, date_time_end=end))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_experiment_period"):
        db_session.commit()


@pytest.mark.parametrize("missing", ["data_provider_id", "algorithm", "parameters",
                                     "date_time_start", "date_time_end", "software_version"])
def test_an_experiment_requires(db_session, provider, missing):
    db_session.add(an_experiment(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("blank", ["algorithm", "software_version"])
def test_an_experiment_refuses_a_blank(db_session, provider, blank):
    db_session.add(an_experiment(provider, **{blank: ""}))
    with pytest.raises(IntegrityError, match=f"ck_thunderstorm_experiment_{blank}"):
        db_session.commit()


@pytest.mark.parametrize("column", ["parameters", "lightning_filter", "hull_parameters", "summary"])
@pytest.mark.parametrize("value", [[1, 2], 5, "eps"], ids=["array", "number", "string"])
def test_a_json_setting_must_be_an_object(db_session, provider, column, value):
    db_session.add(an_experiment(provider, **{column: value}))
    with pytest.raises(IntegrityError, match=f"ck_thunderstorm_experiment_{column}"):
        db_session.commit()


def test_the_summary_is_empty_by_default(db_session, experiment):
    db_session.expire_all()
    assert db_session.scalar(select(ThunderstormExperiment)).summary == {}


def test_the_summary_server_default_matches_the_python_one(db_session, provider):
    """An experiment inserted without the ORM (the CLI's raw SQL) gets ``{}`` too."""
    db_session.execute(text(
        "INSERT INTO thunderstorm_experiment (data_provider_id, algorithm, parameters, "
        "lightning_filter, hull_parameters, date_time_start, date_time_end, software_version) "
        "VALUES (:p, 'X', '{}', '{}', '{}', :s, :e, 'x')"),
        {"p": provider.id, "s": START, "e": END})
    assert db_session.scalar(text("SELECT summary FROM thunderstorm_experiment")) == {}


def test_a_summary_reads_back(db_session, provider):
    summary = {"size_classes": {"1": {"cells": 3, "flashes": 3}}, "flashes_total": 10,
               "cells_open_at_end": 0, "activity_before_start": False}
    db_session.add(an_experiment(provider, summary=summary))
    db_session.commit()
    db_session.expire_all()
    assert db_session.scalar(select(ThunderstormExperiment)).summary == summary


def test_the_provider_must_exist(db_session, provider):
    db_session.add(an_experiment(provider, data_provider_id=provider.id + 999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_same_configuration_cannot_be_stored_twice(db_session, provider, experiment):
    db_session.add(an_experiment(provider))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_experiment_configuration"):
        db_session.commit()


@pytest.mark.parametrize("parameters", [
    pytest.param({"min_samples": 5, "eps_s": 1800, "eps_m": 10000}, id="other-key-order"),
    pytest.param({"eps_m": 10000.0, "eps_s": 1800, "min_samples": 5}, id="10000-as-10000.0"),
])
def test_json_settings_are_compared_by_value(db_session, provider, experiment, parameters):
    db_session.add(an_experiment(provider, parameters=parameters))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_experiment_configuration"):
        db_session.commit()


@pytest.mark.parametrize("change", [
    pytest.param({"software_version": "0.2.0+def5678"}, id="new-code"),
    pytest.param({"algorithm": "HDBSCAN"}, id="algorithm"),
    pytest.param({"parameters": {"eps_m": 5000, "eps_s": 1800, "min_samples": 5}}, id="parameters"),
    pytest.param({"lightning_filter": {"stroke_index": 1, "network": "newest",
                                       "cloud_to_ground": True}}, id="filter"),
    pytest.param({"hull_parameters": {"ratio": 0.1, "allow_holes": False}}, id="hull"),
    pytest.param({"date_time_end": datetime.datetime(2017, 1, 1, tzinfo=UTC)}, id="period"),
])
def test_a_configuration_differing_in_one_setting_is_another_run(db_session, provider, experiment,
                                                                 change):
    db_session.add(an_experiment(provider, **change))
    db_session.commit()
    assert count(db_session, ThunderstormExperiment) == 2


def test_the_summary_is_not_part_of_the_configuration(db_session, provider, experiment):
    """It is an output: a different summary does not make another run."""
    db_session.add(an_experiment(provider, summary={"flashes_total": 1}))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_experiment_configuration"):
        db_session.commit()


def test_the_same_configuration_on_another_provider_is_another_run(db_session, other_provider,
                                                                   experiment):
    db_session.add(an_experiment(other_provider))
    db_session.commit()
    assert count(db_session, ThunderstormExperiment) == 2


def test_experiment_timestamps_are_timezone_aware(db_session, experiment):
    db_session.expire_all()
    stored = db_session.scalar(select(ThunderstormExperiment))
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# Thunderstorm
# --------------------------------------------------------------------------

def test_a_thunderstorm_persists_and_reads_back(db_session, storm):
    db_session.expire_all()
    stored = db_session.scalar(select(Thunderstorm))
    assert stored.experiment.algorithm == "DBSCAN"
    assert (stored.label, stored.number_of_lightnings) == (0, 3)
    assert (stored.date_time_start, stored.date_time_end) == (STORM_START, STORM_END)
    assert to_shape(stored.concave_hull) == Polygon(
        [(1.6, 41.3), (1.9, 41.3), (1.9, 41.5), (1.6, 41.5), (1.6, 41.3)])


def test_the_hull_is_a_polygon_in_4326(db_session, storm):
    kind, srid = db_session.execute(
        select(func.GeometryType(Thunderstorm.concave_hull), func.ST_SRID(Thunderstorm.concave_hull))
    ).one()
    assert (kind, srid) == ("POLYGON", 4326)


def test_a_degenerate_hull_is_stored_as_none(db_session, experiment):
    """Two strokes have no polygon hull: it is NULL, not a point or a line."""
    db_session.add(a_storm(experiment, number_of_lightnings=2, concave_hull=None))
    db_session.commit()
    db_session.expire_all()
    assert db_session.scalar(select(Thunderstorm)).concave_hull is None


def test_a_hull_that_is_not_a_polygon_is_refused(db_session, experiment):
    db_session.add(a_storm(experiment, concave_hull="SRID=4326;LINESTRING(1.6 41.3, 1.9 41.5)"))
    with pytest.raises(Exception, match="(?i)geometry type"):
        db_session.commit()


def test_a_one_stroke_thunderstorm_starts_and_ends_together(db_session, experiment):
    db_session.add(a_storm(experiment, date_time_end=STORM_START, number_of_lightnings=1,
                           concave_hull=None))
    db_session.commit()


def test_a_thunderstorm_cannot_end_before_it_starts(db_session, experiment):
    db_session.add(a_storm(experiment, date_time_end=STORM_START - datetime.timedelta(seconds=1)))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_period"):
        db_session.commit()


def test_a_thunderstorm_has_at_least_one_stroke(db_session, experiment):
    db_session.add(a_storm(experiment, number_of_lightnings=0))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_number_of_lightnings"):
        db_session.commit()


def test_flashes_and_area_are_none_by_default(db_session, storm):
    """An algorithm or a provider without flashes leaves them out."""
    db_session.expire_all()
    stored = db_session.scalar(select(Thunderstorm))
    assert (stored.number_of_flashes, stored.area) == (None, None)


def test_flashes_and_area_read_back(db_session, experiment):
    db_session.add(a_storm(experiment, number_of_lightnings=3, number_of_flashes=2, area=123.25))
    db_session.commit()
    db_session.expire_all()
    stored = db_session.scalar(select(Thunderstorm))
    assert (stored.number_of_flashes, stored.area) == (2, 123.25)


@pytest.mark.parametrize("flashes", [1, 3], ids=["one", "as-many-as-strokes"])
def test_a_thunderstorm_has_between_one_flash_and_one_per_stroke(db_session, experiment, flashes):
    db_session.add(a_storm(experiment, number_of_lightnings=3, number_of_flashes=flashes))
    db_session.commit()


@pytest.mark.parametrize("flashes", [0, 4], ids=["none", "more-than-strokes"])
def test_a_thunderstorm_refuses_impossible_flash_counts(db_session, experiment, flashes):
    db_session.add(a_storm(experiment, number_of_lightnings=3, number_of_flashes=flashes))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_number_of_flashes"):
        db_session.commit()


@pytest.mark.parametrize("area", [0.0, -1.0])
def test_an_area_is_positive(db_session, experiment, area):
    """Undefined is NULL, never 0: a zero area would make an infinite density."""
    db_session.add(a_storm(experiment, area=area))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_area"):
        db_session.commit()


def test_a_label_is_unique_within_its_experiment(db_session, experiment, storm):
    db_session.add(a_storm(experiment))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_experiment_label"):
        db_session.commit()


def test_the_same_label_in_another_experiment_is_another_thunderstorm(db_session, provider, storm):
    db_session.add(a_storm(an_experiment(provider, algorithm="HDBSCAN")))
    db_session.commit()
    assert count(db_session, Thunderstorm) == 2


@pytest.mark.parametrize("missing", ["label", "date_time_start", "date_time_end",
                                     "number_of_lightnings"])
def test_a_thunderstorm_requires(db_session, experiment, missing):
    db_session.add(a_storm(experiment, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_thunderstorm_requires_an_experiment(db_session):
    db_session.add(a_storm(None))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --------------------------------------------------------------------------
# Strokes of a thunderstorm
# --------------------------------------------------------------------------

def test_a_link_takes_the_experiment_of_its_thunderstorm(db_session, everything):
    links = db_session.scalars(select(ThunderstormLightning)).all()
    assert {link.experiment_id for link in links} == {everything.id}


def test_the_strokes_of_a_thunderstorm_come_in_time_order(db_session, everything):
    db_session.expire_all()
    storm = db_session.scalar(select(Thunderstorm))
    minutes = [(stroke.date_time - STORM_START).seconds // 60 for stroke in storm.lightnings]
    assert minutes == [0, 20, 40]


def test_a_stroke_is_in_at_most_one_thunderstorm_per_experiment(db_session, experiment, strokes):
    first, second = a_storm(experiment, label=0), a_storm(experiment, label=1)
    first.lightning_links = [ThunderstormLightning(lightning=strokes[0])]
    second.lightning_links = [ThunderstormLightning(lightning=strokes[0])]
    db_session.add_all([first, second])
    with pytest.raises(IntegrityError, match="uq_thunderstorm_lightning_experiment_lightning"):
        db_session.commit()


def test_a_stroke_can_be_in_one_thunderstorm_of_each_experiment(db_session, provider, experiment,
                                                                strokes):
    other = an_experiment(provider, algorithm="HDBSCAN")
    db_session.add(other)
    for owner in (experiment, other):
        db_session.add(a_storm(owner, lightning_links=[ThunderstormLightning(lightning=strokes[0])]))
    db_session.commit()
    assert count(db_session, ThunderstormLightning) == 2


def test_a_link_cannot_claim_another_experiment(db_session, provider, storm, strokes):
    """The composite key: the copied experiment must be the thunderstorm's."""
    other = an_experiment(provider, algorithm="HDBSCAN")
    db_session.add(other)
    db_session.commit()
    db_session.add(ThunderstormLightning(thunderstorm_id=storm.id, experiment_id=other.id,
                                         lightning_id=strokes[0].id))
    with pytest.raises(IntegrityError, match="fk_thunderstorm_lightning_thunderstorm"):
        db_session.commit()


def test_a_stroke_must_exist(db_session, storm):
    db_session.add(ThunderstormLightning(thunderstorm_id=storm.id, experiment_id=storm.experiment_id,
                                         lightning_id=999999))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_stroke_in_a_thunderstorm_cannot_be_deleted(db_session, everything, strokes):
    """RESTRICT: re-importing a year must drop its experiments first."""
    with pytest.raises(IntegrityError, match="thunderstorm_lightning"):
        db_session.execute(delete(Lightning).where(Lightning.id == strokes[0].id))
    db_session.rollback()
    assert count(db_session, Lightning) == 3


def test_a_stroke_in_no_thunderstorm_can_be_deleted(db_session, everything, provider):
    loose = a_stroke(provider, minute=300)
    db_session.add(loose)
    db_session.commit()
    db_session.execute(delete(Lightning).where(Lightning.id == loose.id))
    db_session.commit()
    assert count(db_session, Lightning) == 3


def test_deleting_a_thunderstorm_deletes_its_links_not_its_strokes(db_session, everything):
    db_session.execute(delete(Thunderstorm))
    db_session.commit()
    assert count(db_session, ThunderstormLightning) == 0
    assert count(db_session, Lightning) == 3


# --------------------------------------------------------------------------
# Tracking
# --------------------------------------------------------------------------

def test_a_tracking_persists_with_its_defaults(db_session, tracking):
    db_session.expire_all()
    stored = db_session.scalar(select(ThunderstormTracking))
    assert stored.experiment.algorithm == "DBSCAN"
    assert stored.window_length == datetime.timedelta(minutes=10)
    assert stored.window_step == datetime.timedelta(minutes=2)
    assert stored.window_anchor == WindowAnchor.CLOCK
    assert stored.centre_method == CentreMethod.MEAN
    assert stored.min_lightnings == 1
    assert stored.hull_parameters == DEFAULT_HULL_PARAMETERS
    assert stored.status == RunStatus.RUNNING
    assert stored.completed_at is None


def test_the_server_defaults_match_the_python_ones(db_session, experiment):
    """A tracking inserted without the ORM gets the same defaults."""
    db_session.execute(text(
        "INSERT INTO thunderstorm_tracking (experiment_id, window_length, window_step, "
        "hull_parameters, software_version) VALUES (:e, '10 min', '2 min', '{}', 'x')"),
        {"e": experiment.id})
    row = db_session.execute(text(
        "SELECT window_anchor, centre_method, min_lightnings, status FROM thunderstorm_tracking")).one()
    assert tuple(row) == ("clock", "mean", 1, "running")


@pytest.mark.parametrize("anchor", list(WindowAnchor))
def test_every_window_anchor_is_accepted(db_session, experiment, anchor):
    db_session.add(a_tracking(experiment, window_anchor=anchor.value))
    db_session.commit()


@pytest.mark.parametrize("method", list(CentreMethod))
def test_every_centre_method_is_accepted(db_session, experiment, method):
    db_session.add(a_tracking(experiment, centre_method=method.value))
    db_session.commit()


@pytest.mark.parametrize(("column", "value"), [
    pytest.param("window_anchor", "noon", id="anchor"),
    pytest.param("centre_method", "median", id="centre"),
    pytest.param("status", "paused", id="status"),
])
def test_a_tracking_refuses_an_unknown_choice(db_session, experiment, column, value):
    db_session.add(a_tracking(experiment, **{column: value}))
    with pytest.raises(IntegrityError, match=f"ck_thunderstorm_tracking_{column}"):
        db_session.commit()


def test_a_fixed_window_is_a_step_equal_to_the_length(db_session, experiment):
    db_session.add(a_tracking(experiment, window_step=datetime.timedelta(minutes=10)))
    db_session.commit()


@pytest.mark.parametrize("step", [datetime.timedelta(0), datetime.timedelta(minutes=-2),
                                  datetime.timedelta(minutes=11)],
                         ids=["zero", "negative", "longer-than-the-window"])
def test_the_step_must_be_positive_and_not_longer_than_the_window(db_session, experiment, step):
    db_session.add(a_tracking(experiment, window_step=step))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_tracking_window"):
        db_session.commit()


def test_a_window_needs_at_least_one_stroke(db_session, experiment):
    db_session.add(a_tracking(experiment, min_lightnings=0))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_tracking_min_lightnings"):
        db_session.commit()


def test_a_complete_tracking_needs_its_completion_instant(db_session, experiment):
    db_session.add(a_tracking(experiment, status="complete"))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_tracking_completed_at"):
        db_session.commit()


@pytest.mark.parametrize("missing", ["window_length", "window_step", "software_version"])
def test_a_tracking_requires(db_session, experiment, missing):
    db_session.add(a_tracking(experiment, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_same_tracking_cannot_be_stored_twice(db_session, experiment, tracking):
    db_session.add(a_tracking(experiment))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_tracking_configuration"):
        db_session.commit()


def test_the_same_window_written_another_way_is_the_same_tracking(db_session, experiment, tracking):
    """Intervals compare by value: 600 seconds is 10 minutes."""
    db_session.add(a_tracking(experiment, window_length=datetime.timedelta(seconds=600),
                              window_step=datetime.timedelta(seconds=120)))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_tracking_configuration"):
        db_session.commit()


@pytest.mark.parametrize("change", [
    pytest.param({"window_length": datetime.timedelta(minutes=15)}, id="length"),
    pytest.param({"window_step": datetime.timedelta(minutes=5)}, id="step"),
    pytest.param({"window_anchor": "storm_start"}, id="anchor"),
    pytest.param({"min_lightnings": 3}, id="min-lightnings"),
    pytest.param({"hull_parameters": {"ratio": 0.1, "allow_holes": False}}, id="hull"),
    pytest.param({"software_version": "0.2.0+def5678"}, id="new-code"),
])
def test_an_experiment_can_be_tracked_with_other_windows(db_session, experiment, tracking, change):
    db_session.add(a_tracking(experiment, **change))
    db_session.commit()
    assert count(db_session, ThunderstormTracking) == 2


# --------------------------------------------------------------------------
# Evolution
# --------------------------------------------------------------------------

def test_a_window_persists_and_reads_back(db_session, everything):
    db_session.expire_all()
    first = db_session.scalar(select(ThunderstormEvolution).order_by(ThunderstormEvolution.sequence))
    assert first.thunderstorm.label == 0
    assert first.tracking.window_step == datetime.timedelta(minutes=2)
    assert first.experiment_id == everything.id
    assert (first.window_start, first.window_end) == (
        STORM_START, STORM_START + datetime.timedelta(minutes=10))
    assert first.number_of_lightnings == 2
    assert to_shape(first.centre) == Point(1.75, 41.4)
    assert first.concave_hull is None


def test_the_centre_is_a_point_and_the_hull_a_polygon_in_4326(db_session, storm, tracking):
    db_session.add(a_window(tracking, storm, concave_hull=HULL))
    db_session.commit()
    row = db_session.execute(select(
        func.GeometryType(ThunderstormEvolution.centre), func.ST_SRID(ThunderstormEvolution.centre),
        func.GeometryType(ThunderstormEvolution.concave_hull),
        func.ST_SRID(ThunderstormEvolution.concave_hull),
    )).one()
    assert tuple(row) == ("POINT", 4326, "POLYGON", 4326)


def test_a_window_needs_a_centre(db_session, storm, tracking):
    db_session.add(a_window(tracking, storm, centre=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_sequence_number_is_used_once_per_thunderstorm_and_tracking(db_session, everything):
    storm = db_session.scalar(select(Thunderstorm))
    tracking = db_session.scalar(select(ThunderstormTracking))
    db_session.add(a_window(tracking, storm, sequence=2))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_evolution_sequence"):
        db_session.commit()


def test_the_same_sequence_in_another_tracking_is_another_window(db_session, everything):
    storm = db_session.scalar(select(Thunderstorm))
    other = a_tracking(everything, window_step=datetime.timedelta(minutes=5))
    db_session.add(a_window(other, storm, sequence=1))
    db_session.commit()
    assert count(db_session, ThunderstormEvolution) == 3


@pytest.mark.parametrize(("change", "constraint"), [
    pytest.param({"sequence": 0}, "ck_thunderstorm_evolution_sequence", id="sequence-zero"),
    pytest.param({"window_end": STORM_START}, "ck_thunderstorm_evolution_window", id="empty-window"),
    pytest.param({"number_of_lightnings": 0}, "ck_thunderstorm_evolution_number_of_lightnings",
                 id="no-strokes"),
])
def test_a_window_refuses(db_session, storm, tracking, change, constraint):
    db_session.add(a_window(tracking, storm, **change))
    with pytest.raises(IntegrityError, match=constraint):
        db_session.commit()


@pytest.mark.parametrize("mismatch", ["thunderstorm", "tracking"])
def test_a_window_cannot_pair_a_thunderstorm_and_a_tracking_of_different_experiments(
        db_session, provider, storm, tracking, mismatch):
    other = an_experiment(provider, algorithm="HDBSCAN")
    other_storm, other_tracking = a_storm(other), a_tracking(other)
    db_session.add_all([other_storm, other_tracking])
    db_session.commit()
    # Written by id, as a bulk builder would, so the ORM cannot paper over it.
    pair = {"thunderstorm": (other_storm.id, tracking.id), "tracking": (storm.id, other_tracking.id)}
    storm_id, tracking_id = pair[mismatch]
    db_session.add(ThunderstormEvolution(
        tracking_id=tracking_id, thunderstorm_id=storm_id, experiment_id=storm.experiment_id,
        sequence=1, window_start=STORM_START, window_end=STORM_END, number_of_lightnings=1,
        centre=CENTRE))
    with pytest.raises(IntegrityError, match=f"fk_thunderstorm_evolution_{mismatch}"):
        db_session.commit()


# --------------------------------------------------------------------------
# Cascades
# --------------------------------------------------------------------------

def test_deleting_a_tracking_deletes_its_windows_not_its_thunderstorms(db_session, everything):
    db_session.execute(delete(ThunderstormTracking))
    db_session.commit()
    assert count(db_session, ThunderstormEvolution) == 0
    assert count(db_session, Thunderstorm) == 1
    assert count(db_session, ThunderstormLightning) == 3


def test_deleting_a_thunderstorm_deletes_its_windows(db_session, everything):
    db_session.execute(delete(Thunderstorm))
    db_session.commit()
    assert count(db_session, ThunderstormEvolution) == 0
    assert count(db_session, ThunderstormTracking) == 1


def test_deleting_an_experiment_in_sql_deletes_everything_it_produced(db_session, everything):
    """The importer's ``--drop-thunderstorms`` relies on this cascade."""
    db_session.execute(delete(ThunderstormExperiment))
    db_session.commit()
    assert [count(db_session, model) for model in ALL_TABLES] == [0, 0, 0, 0, 0]
    assert count(db_session, Lightning) == 3


def test_deleting_an_experiment_through_the_orm_deletes_everything(db_session, everything):
    db_session.delete(everything)
    db_session.commit()
    assert [count(db_session, model) for model in ALL_TABLES] == [0, 0, 0, 0, 0]
    assert count(db_session, Lightning) == 3


def test_deleting_one_experiment_leaves_the_others(db_session, provider, everything, strokes):
    other = an_experiment(provider, algorithm="HDBSCAN")
    storm = a_storm(other)
    storm.lightning_links = [ThunderstormLightning(lightning=strokes[0])]
    db_session.add(storm)
    db_session.commit()
    db_session.delete(everything)
    db_session.commit()
    assert count(db_session, ThunderstormExperiment) == 1
    assert count(db_session, ThunderstormLightning) == 1


# --------------------------------------------------------------------------
# repr
# --------------------------------------------------------------------------

def test_reprs_before_persist():
    assert repr(ThunderstormExperiment(algorithm="DBSCAN", status="running")) == \
        "ThunderstormExperiment(id=None, algorithm='DBSCAN', status='running')"
    assert repr(Thunderstorm(label=3)) == "Thunderstorm(id=None, experiment_id=None, label=3)"
    assert repr(ThunderstormLightning(lightning_id=7)) == \
        "ThunderstormLightning(thunderstorm_id=None, lightning_id=7)"
    minutes = datetime.timedelta(minutes=10)
    assert repr(ThunderstormTracking(window_length=minutes, window_step=minutes)) == (
        f"ThunderstormTracking(id=None, experiment_id=None, window_length={minutes!r}, "
        f"window_step={minutes!r})")
    assert repr(ThunderstormEvolution(sequence=1)) == (
        "ThunderstormEvolution(id=None, tracking_id=None, thunderstorm_id=None, sequence=1)")
