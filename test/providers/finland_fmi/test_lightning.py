#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the FMI lightning model and the provider constants.

What is worth pinning down: that a stroke is stored across the two tables and
loads back as a :class:`FmiLightning` from a query on the generic model; that the
published ETRS89 point is kept beside the EPSG:4326 one; that a flash is
``flash_id`` alone and not a stroke key; that FMI's published multiplicity is
kept beside the computed one; that the indicators are stored whatever their
value; and that the CHECKs hold.

The stroke values are those of real strokes (FMI open data, CC BY 4.0).
"""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.lightning import Lightning
from src.providers import finland_fmi
from src.providers.finland_fmi.lightning import FmiLightning

UTC = datetime.timezone.utc

#: 2023-07-01 12:00:15 UTC: flash 30645787, four strokes, all within that second.
DETECTED = datetime.datetime(2023, 7, 1, 12, 0, 15, tzinfo=UTC)

#: The three strokes after the first, as published (ellipse in metres), by their
#: number in the flash.
SUBSEQUENT = {
    2: {"point": "POINT(31.8249 59.7173)", "peak_current": -27.0, "number_of_sensors": 5,
        "degrees_of_freedom": 7, "chi_squared": 1.5, "ellipse_major_axis": 800.0,
        "ellipse_minor_axis": 300.0, "ellipse_angle": 120.3, "rise_time": 18.4,
        "peak_to_zero_time": 13.7},
    3: {"point": "POINT(31.8056 59.7292)", "peak_current": -13.0, "number_of_sensors": 4,
        "degrees_of_freedom": 5, "chi_squared": 0.7, "ellipse_major_axis": 1900.0,
        "ellipse_minor_axis": 400.0, "ellipse_angle": 85.3, "rise_time": 3.6,
        "peak_to_zero_time": 17.0},
    4: {"point": "POINT(31.841 59.718)", "peak_current": -12.0, "number_of_sensors": 3,
        "degrees_of_freedom": 3, "chi_squared": 0.2, "ellipse_major_axis": 6300.0,
        "ellipse_minor_axis": 1100.0, "ellipse_angle": 55.8, "rise_time": 7.9,
        "peak_to_zero_time": 9.1},
}


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=finland_fmi.PROVIDER_NAME,
                            product=finland_fmi.PROVIDER_PRODUCT,
                            full_name=finland_fmi.PROVIDER_FULL_NAME,
                            description=finland_fmi.PROVIDER_DESCRIPTION,
                            url=finland_fmi.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_stroke(provider, **overrides) -> FmiLightning:
    """The first stroke of a four-stroke flash, as published, ellipse in metres."""
    values = {
        "data_provider": provider,
        "date_time": DETECTED,
        "geometry": "SRID=4326;POINT(31.8554 59.7094)",
        "geometry_etrs89": "SRID=4258;POINT(31.8554 59.7094)",
        "peak_current": -83.0,
        "cloud_to_ground": True,
        "flash_id": 30645787,
        "multiplicity": 4,
        "stroke_index": 1,
        "published_multiplicity": 4,
        "number_of_sensors": 10,
        "degrees_of_freedom": 7,
        "chi_squared": 0.4,
        "ellipse_major_axis": 700.0,
        "ellipse_minor_axis": 100.0,
        "ellipse_angle": 109.9,
        "rise_time": 8.9,
        "peak_to_zero_time": 30.4,
        "stroke_status": 17,
        "angle_indicator": 1,
        "signal_indicator": 0,
        "timing_indicator": 1,
    }
    values.update(overrides)
    return FmiLightning(**values)


def a_subsequent_stroke(provider, number, **overrides) -> FmiLightning:
    """Stroke ``number`` (2 to 4) of the same flash: published multiplicity 0."""
    values = dict(SUBSEQUENT[number])
    point = values.pop("point")
    values.update({"stroke_index": number, "published_multiplicity": 0,
                   "geometry": f"SRID=4326;{point}", "geometry_etrs89": f"SRID=4258;{point}"})
    values.update(overrides)
    return a_stroke(provider, **values)


# --- Provider constants ------------------------------------------------------


def test_the_provider_constants_make_a_storable_row(db_session, provider):
    stored = db_session.scalar(select(DataProvider))
    assert (stored.name, stored.product) == ("FMI", "Lightning strikes")
    assert stored.full_name == "Ilmatieteen laitos (Finnish Meteorological Institute)"


def test_the_published_crs_is_etrs89_and_the_projected_one_tm35fin():
    assert finland_fmi.SOURCE_SRID == 4258
    assert finland_fmi.PROJECTED_SRID == 3067


def test_the_service_constants():
    assert finland_fmi.WFS_URL == "https://opendata.fmi.fi/wfs"
    assert finland_fmi.STORED_QUERY == "fmi::observations::lightning::multipointcoverage"
    assert finland_fmi.MAX_REQUEST_HOURS == 168
    assert finland_fmi.ELLIPSE_AXIS_FACTOR == 1000.0


def test_the_parameters_are_the_sixteen_served():
    assert finland_fmi.PARAMETERS == (
        "flash_id", "multiplicity", "peak_current", "cloud_indicator", "sensors",
        "freedom_degree", "ellipse_angle", "ellipse_major", "ellipse_minor", "chi_square",
        "rise_time", "ptz_time", "angle_indicator", "signal_indicator", "timing_indicator",
        "stroke_status")


# --- Persistence -------------------------------------------------------------


def test_a_stroke_persists_across_both_tables(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(FmiLightning))
    assert stored.type == "fmi_lightning"
    assert stored.date_time == DETECTED
    assert stored.peak_current == -83.0
    assert stored.cloud_to_ground is True
    assert stored.flash_id == 30645787
    assert (stored.multiplicity, stored.stroke_index, stored.published_multiplicity) == (4, 1, 4)
    assert (stored.number_of_sensors, stored.degrees_of_freedom) == (10, 7)
    assert stored.chi_squared == 0.4
    assert (stored.ellipse_major_axis, stored.ellipse_minor_axis) == (700.0, 100.0)
    assert stored.ellipse_angle == 109.9
    assert (stored.rise_time, stored.peak_to_zero_time) == (8.9, 30.4)
    assert stored.stroke_status == 17
    assert (stored.angle_indicator, stored.signal_indicator, stored.timing_indicator) == (1, 0, 1)
    assert stored.data_provider.name == "FMI"

    parent, child = db_session.execute(text(
        "SELECT (SELECT count(*) FROM lightning), (SELECT count(*) FROM fmi_lightning)")).one()
    assert (parent, child) == (1, 1)


def test_a_query_on_the_generic_model_loads_the_subclass(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()
    db_session.expunge_all()

    assert isinstance(db_session.scalar(select(Lightning)), FmiLightning)


def test_the_published_point_is_kept_in_etrs89(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(FmiLightning))
    assert to_shape(stored.geometry_etrs89) == Point(31.8554, 59.7094)
    kind, srid = db_session.execute(select(
        func.GeometryType(FmiLightning.geometry_etrs89),
        func.ST_SRID(FmiLightning.geometry_etrs89))).one()
    assert (kind, srid) == ("POINT", 4258)
    assert db_session.scalar(select(func.ST_SRID(Lightning.geometry))) == 4326


def test_a_peak_current_not_recorded_is_null(db_session, provider):
    """2005-2008 publish 0 for "not recorded"; the import stores NULL."""
    db_session.add(a_stroke(provider, peak_current=None, stroke_status=0))
    db_session.commit()

    assert db_session.scalar(select(FmiLightning)).peak_current is None


def test_an_intra_cloud_stroke_is_stored(db_session, provider):
    db_session.add(a_stroke(provider, cloud_to_ground=False, peak_current=9.0, multiplicity=1,
                            published_multiplicity=1))
    db_session.commit()

    assert db_session.scalar(select(FmiLightning)).cloud_to_ground is False


@pytest.mark.parametrize(("angle", "signal", "timing"), [(0, 0, 0), (1, 0, 0), (1, 0, 1)])
def test_the_indicators_are_stored_as_published(db_session, provider, angle, signal, timing):
    """1998-2004 have strokes with angle and/or timing indicator 0; no CHECK on them."""
    db_session.add(a_stroke(provider, angle_indicator=angle, signal_indicator=signal,
                            timing_indicator=timing, stroke_status=0))
    db_session.commit()

    stored = db_session.scalar(select(FmiLightning))
    assert (stored.angle_indicator, stored.signal_indicator, stored.timing_indicator) == \
        (angle, signal, timing)


# --- Flashes -----------------------------------------------------------------


def test_a_flash_has_several_strokes(db_session, provider):
    """The flash id is not a stroke key, and only the first stroke publishes a count."""
    db_session.add(a_stroke(provider))
    for index in (2, 3, 4):
        db_session.add(a_subsequent_stroke(provider, index))
    db_session.commit()

    strokes = db_session.execute(
        select(FmiLightning.stroke_index, FmiLightning.multiplicity,
               FmiLightning.published_multiplicity)
        .where(FmiLightning.flash_id == 30645787)
        .order_by(FmiLightning.stroke_index)).all()
    assert strokes == [(1, 4, 4), (2, 4, 0), (3, 4, 0), (4, 4, 0)]


def test_two_strokes_may_share_flash_second_and_position(db_session, provider):
    """26 such pairs in one week of 2018: there is deliberately no unique constraint."""
    db_session.add(a_stroke(provider, multiplicity=2, published_multiplicity=2))
    db_session.add(a_subsequent_stroke(provider, 2, multiplicity=2,
                                       geometry="SRID=4326;POINT(31.8554 59.7094)",
                                       geometry_etrs89="SRID=4258;POINT(31.8554 59.7094)"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(FmiLightning)) == 2


def test_the_published_multiplicity_may_exceed_the_strokes_stored(db_session, provider):
    """FMI drops badly located strokes, so a flash can announce more than it has."""
    db_session.add(a_stroke(provider, multiplicity=1, published_multiplicity=2))
    db_session.commit()

    stored = db_session.scalar(select(FmiLightning))
    assert (stored.multiplicity, stored.published_multiplicity) == (1, 2)


def test_a_lone_subsequent_stroke_is_allowed(db_session, provider):
    """A flash whose first stroke was dropped: published 0, still stroke 1 of 1."""
    db_session.add(a_subsequent_stroke(provider, 2, multiplicity=1, stroke_index=1))
    db_session.commit()

    stored = db_session.scalar(select(FmiLightning))
    assert (stored.multiplicity, stored.stroke_index, stored.published_multiplicity) == (1, 1, 0)


# --- Constraints -------------------------------------------------------------


@pytest.mark.parametrize("missing", [
    "flash_id", "multiplicity", "stroke_index", "published_multiplicity", "number_of_sensors",
    "degrees_of_freedom", "chi_squared", "ellipse_major_axis", "ellipse_minor_axis",
    "ellipse_angle", "rise_time", "peak_to_zero_time", "stroke_status", "angle_indicator",
    "signal_indicator", "timing_indicator", "geometry_etrs89",
])
def test_required_columns_are_enforced(db_session, provider, missing):
    db_session.add(a_stroke(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("overrides", [
    pytest.param({"flash_id": -1}, id="negative-flash-id"),
    pytest.param({"multiplicity": 0, "stroke_index": 0}, id="multiplicity-0"),
    pytest.param({"stroke_index": 0}, id="stroke-index-0"),
    pytest.param({"stroke_index": 5}, id="stroke-index-past-multiplicity"),
    pytest.param({"published_multiplicity": -1}, id="negative-published-multiplicity"),
    pytest.param({"number_of_sensors": 0}, id="zero-sensors"),
    pytest.param({"degrees_of_freedom": -1}, id="negative-degrees-of-freedom"),
    pytest.param({"chi_squared": -0.1}, id="negative-chi-squared"),
    pytest.param({"ellipse_minor_axis": -1.0}, id="negative-minor-axis"),
    pytest.param({"ellipse_major_axis": 100.0, "ellipse_minor_axis": 700.0},
                 id="minor-larger-than-major"),
    pytest.param({"ellipse_angle": -0.1}, id="negative-angle"),
    pytest.param({"ellipse_angle": 180.1}, id="angle-past-180"),
    pytest.param({"rise_time": -0.1}, id="negative-rise-time"),
    pytest.param({"peak_to_zero_time": -0.1}, id="negative-peak-to-zero-time"),
])
def test_the_checks_refuse_impossible_values(db_session, provider, overrides):
    db_session.add(a_stroke(provider, **overrides))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("overrides", [
    pytest.param({"chi_squared": 0.0, "number_of_sensors": 2, "degrees_of_freedom": 0},
                 id="two-sensor-fit"),
    pytest.param({"ellipse_minor_axis": 0.0}, id="zero-minor-axis"),
    pytest.param({"ellipse_major_axis": 300.0, "ellipse_minor_axis": 300.0}, id="circle"),
    pytest.param({"ellipse_angle": 0.0}, id="angle-0"),
    pytest.param({"ellipse_angle": 180.0}, id="angle-180"),
    pytest.param({"rise_time": 0.0, "peak_to_zero_time": 0.0}, id="zero-times"),
])
def test_the_edges_seen_in_the_data_are_allowed(db_session, provider, overrides):
    """Every one of these values occurs in the 1998-2025 samples."""
    db_session.add(a_stroke(provider, **overrides))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(FmiLightning)) == 1


def test_the_parent_row_is_required(db_session, provider):
    """The child's primary key is a foreign key to ``lightning``."""
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "INSERT INTO fmi_lightning (id, flash_id, multiplicity, stroke_index, "
            "published_multiplicity, number_of_sensors, degrees_of_freedom, chi_squared, "
            "ellipse_major_axis, ellipse_minor_axis, ellipse_angle, rise_time, "
            "peak_to_zero_time, stroke_status, angle_indicator, signal_indicator, "
            "timing_indicator, geometry_etrs89) VALUES (999, 1, 1, 1, 1, 2, 1, 0, 100, 100, "
            "0, 1, 1, 17, 1, 0, 1, ST_GeomFromText('POINT(25 60)', 4258))"))
        db_session.commit()


def test_repr_before_persist():
    stroke = FmiLightning(date_time=DETECTED, flash_id=30645787)
    assert repr(stroke) == f"FmiLightning(id=None, date_time={DETECTED!r}, flash_id=30645787)"
