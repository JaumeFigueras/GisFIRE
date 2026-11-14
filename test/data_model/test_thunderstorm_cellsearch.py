#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Cellsearch flash table (``thunderstorm_cellsearch_flash``).

What is pinned down is what the database enforces on its own: a row cannot
point at another experiment's cell nor at a stroke that is not linked to its
cell, a stroke represents at most one flash per experiment, positions are
unique and start at 1, and everything goes away with the experiment, the cell
or the link while the strokes stay.
"""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.lightning import Lightning
from src.data_model.thunderstorm import Thunderstorm
from src.data_model.thunderstorm import ThunderstormExperiment
from src.data_model.thunderstorm import ThunderstormLightning
from src.data_model.thunderstorm_cellsearch import ThunderstormCellsearchFlash

UTC = datetime.timezone.utc

START = datetime.datetime(2020, 7, 13, tzinfo=UTC)
END = datetime.datetime(2020, 7, 14, tzinfo=UTC)
STORM_START = datetime.datetime(2020, 7, 13, 14, 0, tzinfo=UTC)

PARAMETERS = {"attraction_radius_km": 15.0, "max_waiting_time_min": 15.0,
              "time_distance_limit_min_km": None, "inertia": 20, "max_location_error_km": 10.0,
              "min_flashes": 5, "srid": 25831}


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------

def centre(x: float = 1.75, y: float = 41.4) -> str:
    return f"SRID=4326;POINT({x} {y})"


def an_experiment(provider, **overrides) -> ThunderstormExperiment:
    values = {
        "data_provider_id": provider.id,
        "algorithm": "CELLSEARCH_TUOMI_LARJAVAARA_2005",
        "parameters": PARAMETERS,
        "lightning_filter": {"network": "newest"},
        "date_time_start": START,
        "date_time_end": END,
        "software_version": "0.1.0",
    }
    values.update(overrides)
    return ThunderstormExperiment(**values)


def a_cell(experiment, strokes, label: int = 1) -> Thunderstorm:
    storm = Thunderstorm(experiment=experiment, label=label, date_time_start=STORM_START,
                         date_time_end=STORM_START + datetime.timedelta(minutes=len(strokes)),
                         number_of_lightnings=len(strokes), number_of_flashes=len(strokes))
    storm.lightning_links = [ThunderstormLightning(lightning=stroke) for stroke in strokes]
    return storm


def a_flash(storm, lightning_id: int, sequence: int, **overrides) -> ThunderstormCellsearchFlash:
    values = {"thunderstorm": storm, "sequence": sequence, "lightning_id": lightning_id,
              "centre": centre()}
    values.update(overrides)
    return ThunderstormCellsearchFlash(**values)


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="MeteoCat", product="XDDE", full_name="Servei Meteorològic de Catalunya")
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def strokes(db_session, provider):
    strokes = [Lightning(data_provider_id=provider.id,
                         date_time=STORM_START + datetime.timedelta(minutes=minute),
                         geometry=f"SRID=4326;POINT({1.7 + 0.01 * minute} 41.4)",
                         peak_current=-20.0, cloud_to_ground=True)
               for minute in range(6)]
    db_session.add_all(strokes)
    db_session.commit()
    return strokes


@pytest.fixture
def experiment(db_session, provider):
    experiment = an_experiment(provider)
    db_session.add(experiment)
    db_session.commit()
    return experiment


@pytest.fixture
def cell(db_session, experiment, strokes):
    """A cell linked to the first four strokes, with three flashes."""
    ids = [stroke.id for stroke in strokes]
    storm = a_cell(experiment, strokes[:4])
    db_session.add(storm)
    db_session.commit()
    db_session.add_all([a_flash(storm, ids[0], 1, centre=centre(1.70)),
                        a_flash(storm, ids[2], 2, centre=centre(1.71)),
                        a_flash(storm, ids[3], 3, centre=centre(1.72))])
    db_session.commit()
    return storm


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def test_flashes_persist_and_read_back_in_sequence(db_session, cell, strokes):
    db_session.expire_all()
    storm = db_session.scalar(select(Thunderstorm))
    assert [flash.sequence for flash in storm.cellsearch_flashes] == [1, 2, 3]
    assert [flash.lightning_id for flash in storm.cellsearch_flashes] == [
        strokes[0].id, strokes[2].id, strokes[3].id]
    assert [to_shape(flash.centre) for flash in storm.cellsearch_flashes] == [
        Point(1.70, 41.4), Point(1.71, 41.4), Point(1.72, 41.4)]
    assert storm.cellsearch_flashes[1].lightning.date_time == strokes[2].date_time


def test_a_flash_takes_the_experiment_of_its_cell(db_session, cell):
    db_session.expire_all()
    assert set(db_session.scalars(select(ThunderstormCellsearchFlash.experiment_id))) == {
        cell.experiment_id}


def test_a_cell_and_its_flashes_can_be_written_in_one_go(db_session, experiment, strokes):
    """The links are inserted before the flashes that reference them."""
    ids = [stroke.id for stroke in strokes]
    storm = a_cell(experiment, strokes[:2])
    storm.cellsearch_flashes = [
        ThunderstormCellsearchFlash(sequence=1, lightning_id=ids[0], centre=centre()),
        ThunderstormCellsearchFlash(sequence=2, lightning_id=ids[1], centre=centre()),
    ]
    db_session.add(storm)
    db_session.commit()
    assert count(db_session, ThunderstormCellsearchFlash) == 2


def test_the_centre_is_a_point_in_4326(db_session, cell):
    kind, srid = db_session.execute(
        select(func.GeometryType(ThunderstormCellsearchFlash.centre),
               func.ST_SRID(ThunderstormCellsearchFlash.centre)).limit(1)
    ).one()
    assert (kind, srid) == ("POINT", 4326)


def test_a_flash_needs_a_centre(db_session, cell, strokes):
    db_session.add(a_flash(cell, strokes[1].id, 4, centre=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_centre_that_is_not_a_point_is_refused(db_session, cell, strokes):
    db_session.add(a_flash(cell, strokes[1].id, 4, centre="SRID=4326;LINESTRING(1.6 41.3, 1.9 41.5)"))
    with pytest.raises(Exception, match="(?i)geometry type"):
        db_session.commit()


@pytest.mark.parametrize("sequence", [0, -1])
def test_a_sequence_starts_at_one(db_session, cell, strokes, sequence):
    db_session.add(a_flash(cell, strokes[1].id, sequence))
    with pytest.raises(IntegrityError, match="ck_thunderstorm_cellsearch_flash_sequence"):
        db_session.commit()


def test_a_sequence_is_used_once_per_cell(db_session, cell, strokes):
    db_session.add(a_flash(cell, strokes[1].id, 2))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_cellsearch_flash_sequence"):
        db_session.commit()


def test_a_stroke_represents_at_most_one_flash_per_experiment(db_session, cell, strokes):
    db_session.add(a_flash(cell, strokes[0].id, 4))
    with pytest.raises(IntegrityError, match="uq_thunderstorm_cellsearch_flash_experiment_lightning"):
        db_session.commit()


def test_a_stroke_can_represent_a_flash_in_each_experiment(db_session, provider, cell, strokes):
    first = strokes[0].id
    other = an_experiment(provider, parameters={**PARAMETERS, "inertia": 10})
    storm = a_cell(other, strokes[:1])
    db_session.add(storm)
    db_session.commit()
    db_session.add(a_flash(storm, first, 1))
    db_session.commit()
    assert count(db_session, ThunderstormCellsearchFlash) == 4


# --------------------------------------------------------------------------
# The composite foreign keys
# --------------------------------------------------------------------------

def test_the_representative_must_be_a_stroke_of_the_cell(db_session, cell, strokes):
    """Stroke 5 exists but is not linked to the cell."""
    db_session.add(a_flash(cell, strokes[5].id, 4))
    with pytest.raises(IntegrityError, match="fk_thunderstorm_cellsearch_flash_link"):
        db_session.commit()


def test_the_representative_cannot_be_a_stroke_of_another_cell(db_session, experiment, cell,
                                                              strokes):
    other = a_cell(experiment, strokes[4:6], label=2)
    db_session.add(other)
    db_session.commit()
    db_session.add(a_flash(cell, strokes[4].id, 4))
    with pytest.raises(IntegrityError, match="fk_thunderstorm_cellsearch_flash_link"):
        db_session.commit()


def test_a_flash_cannot_claim_another_experiment(db_session, provider, cell, strokes):
    other = an_experiment(provider, parameters={**PARAMETERS, "inertia": 10})
    db_session.add(other)
    db_session.commit()
    with pytest.raises(IntegrityError, match="fk_thunderstorm_cellsearch_flash_thunderstorm"):
        db_session.execute(text(
            "INSERT INTO thunderstorm_cellsearch_flash (thunderstorm_id, sequence, experiment_id, "
            "lightning_id, centre) VALUES (:t, 4, :e, :l, ST_GeomFromEWKT(:c))"),
            {"t": cell.id, "e": other.id, "l": strokes[1].id, "c": centre()})


# --------------------------------------------------------------------------
# Deletes
# --------------------------------------------------------------------------

def test_deleting_the_experiment_deletes_the_flashes(db_session, cell):
    db_session.execute(delete(ThunderstormExperiment))
    db_session.commit()
    assert count(db_session, ThunderstormCellsearchFlash) == 0
    assert count(db_session, Lightning) == 6


def test_deleting_the_cell_deletes_its_flashes(db_session, cell):
    db_session.delete(cell)
    db_session.commit()
    assert count(db_session, ThunderstormCellsearchFlash) == 0
    assert count(db_session, ThunderstormLightning) == 0
    assert count(db_session, Lightning) == 6


def test_deleting_a_link_deletes_its_flash_only(db_session, cell, strokes):
    db_session.execute(delete(ThunderstormLightning).where(
        ThunderstormLightning.lightning_id == strokes[2].id))
    db_session.commit()
    db_session.expire_all()
    assert [flash.sequence for flash in db_session.scalars(
        select(ThunderstormCellsearchFlash).order_by(ThunderstormCellsearchFlash.sequence))] == [1, 3]


def test_a_representative_stroke_cannot_be_deleted(db_session, cell, strokes):
    with pytest.raises(IntegrityError, match="thunderstorm_lightning_lightning_id_fkey"):
        db_session.execute(delete(Lightning).where(Lightning.id == strokes[0].id))


def test_repr_names_the_cell_the_position_and_the_stroke(db_session, cell, strokes):
    flash = db_session.scalar(select(ThunderstormCellsearchFlash).where(
        ThunderstormCellsearchFlash.sequence == 2))
    assert repr(flash) == (f"ThunderstormCellsearchFlash(id={flash.id}, thunderstorm_id={cell.id}, "
                           f"sequence=2, lightning_id={strokes[2].id})")
