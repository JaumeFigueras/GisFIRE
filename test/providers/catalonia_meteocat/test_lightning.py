#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the MeteoCat lightning model and the provider constants.

What is worth pinning down: that a stroke is stored across the two tables and
loads back as a :class:`MeteocatLightning` from a query on the generic model;
that the published ETRS89 point is kept beside the EPSG:4326 one; that a flash is
identified by the network version *and* the flash id, never alone and never per
stroke; that "not recorded" is ``NULL`` and a version-1 ``0`` is refused; and
that the CHECKs on multiplicity, stroke index and the ellipse hold.
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
from src.providers import catalonia_meteocat
from src.providers.catalonia_meteocat.lightning import MeteocatLightning

UTC = datetime.timezone.utc

#: 2014-05-26 08:29:25.737483 UTC, a version-2 stroke of flash 9926356.
DETECTED = datetime.datetime(2014, 5, 26, 8, 29, 25, 737483, tzinfo=UTC)


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=catalonia_meteocat.PROVIDER_NAME,
                            product=catalonia_meteocat.PROVIDER_PRODUCT,
                            full_name=catalonia_meteocat.PROVIDER_FULL_NAME,
                            description=catalonia_meteocat.PROVIDER_DESCRIPTION,
                            url=catalonia_meteocat.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_stroke(provider, **overrides) -> MeteocatLightning:
    """One version-2 stroke, as the 2014 file publishes it."""
    values = {
        "data_provider": provider,
        "date_time": DETECTED,
        "geometry": "SRID=4326;POINT(2.1812854 40.942856)",
        "geometry_etrs89": "SRID=4258;POINT(2.1812854 40.942856)",
        "peak_current": 22.4405,
        "cloud_to_ground": True,
        "network_version": 2,
        "flash_id": 9926356,
        "multiplicity": 1,
        "stroke_index": 1,
        "chi_squared": 1.5,
        "ellipse_major_axis": 1500.0,
        "ellipse_minor_axis": 400.0,
        "number_of_sensors": 2,
        "municipality_code": None,
    }
    values.update(overrides)
    return MeteocatLightning(**values)


def a_version_1_stroke(provider, **overrides) -> MeteocatLightning:
    """One version-1 stroke, as the 2006 file publishes it, "not recorded" as NULL."""
    values = {
        "date_time": datetime.datetime(2006, 1, 2, 11, 40, 1, 3499, tzinfo=UTC),
        "geometry": "SRID=4326;POINT(3.703 41.0538)",
        "geometry_etrs89": "SRID=4258;POINT(3.703 41.0538)",
        "peak_current": 2.09,
        "network_version": 1,
        "flash_id": 3803582,
        "chi_squared": None,
        "ellipse_major_axis": 2450.0,
        "ellipse_minor_axis": 2450.0,
        "number_of_sensors": None,
    }
    values.update(overrides)
    return a_stroke(provider, **values)


# --- Provider constants ------------------------------------------------------


def test_the_provider_constants_make_a_storable_row(db_session, provider):
    stored = db_session.scalar(select(DataProvider))
    assert (stored.name, stored.product) == ("MeteoCat", "XDDE")
    assert stored.full_name == "Servei Meteorològic de Catalunya"


def test_the_published_crs_is_etrs89():
    assert catalonia_meteocat.SOURCE_SRID == 4258
    assert catalonia_meteocat.PROJECTED_SRID == 25831


def test_the_network_versions_are_numbered_from_one():
    assert sorted(catalonia_meteocat.NETWORK_VERSIONS) == [1, 2]


# --- Persistence -------------------------------------------------------------


def test_a_stroke_persists_across_both_tables(db_session, provider):
    db_session.add(a_stroke(provider, municipality_code="082589"))
    db_session.commit()

    stored = db_session.scalar(select(MeteocatLightning))
    assert stored.type == "meteocat_lightning"
    assert stored.date_time == DETECTED
    assert stored.peak_current == 22.4405
    assert stored.cloud_to_ground is True
    assert (stored.network_version, stored.flash_id) == (2, 9926356)
    assert (stored.multiplicity, stored.stroke_index) == (1, 1)
    assert stored.chi_squared == 1.5
    assert (stored.ellipse_major_axis, stored.ellipse_minor_axis) == (1500.0, 400.0)
    assert stored.ellipse_angle is None
    assert stored.number_of_sensors == 2
    assert stored.municipality_code == "082589"
    assert stored.data_provider.name == "MeteoCat"

    parent, child = db_session.execute(text(
        "SELECT (SELECT count(*) FROM lightning), (SELECT count(*) FROM meteocat_lightning)")).one()
    assert (parent, child) == (1, 1)


def test_a_query_on_the_generic_model_loads_the_subclass(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()
    db_session.expunge_all()

    assert isinstance(db_session.scalar(select(Lightning)), MeteocatLightning)


def test_the_published_point_is_kept_in_etrs89(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(MeteocatLightning))
    assert to_shape(stored.geometry_etrs89) == Point(2.1812854, 40.942856)
    kind, srid = db_session.execute(select(
        func.GeometryType(MeteocatLightning.geometry_etrs89),
        func.ST_SRID(MeteocatLightning.geometry_etrs89))).one()
    assert (kind, srid) == ("POINT", 4258)
    assert db_session.scalar(select(func.ST_SRID(Lightning.geometry))) == 4326


def test_the_api_ellipse_angle_is_stored_when_given(db_session, provider):
    db_session.add(a_stroke(provider, ellipse_angle=37.5))
    db_session.commit()

    assert db_session.scalar(select(MeteocatLightning)).ellipse_angle == 37.5


def test_a_version_1_stroke_stores_not_recorded_as_null(db_session, provider):
    db_session.add(a_version_1_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(MeteocatLightning))
    assert stored.network_version == 1
    assert stored.number_of_sensors is None
    assert stored.chi_squared is None


# --- Flashes -----------------------------------------------------------------


def test_a_flash_has_several_strokes(db_session, provider):
    """The flash id is not a stroke key: every stroke of the flash carries it."""
    db_session.add(a_stroke(provider, multiplicity=2, stroke_index=1))
    db_session.add(a_stroke(provider, multiplicity=2, stroke_index=2, peak_current=-22.903,
                            date_time=DETECTED + datetime.timedelta(microseconds=300)))
    db_session.commit()

    strokes = db_session.execute(select(MeteocatLightning.stroke_index, MeteocatLightning.multiplicity)
                                 .where(MeteocatLightning.flash_id == 9926356)
                                 .order_by(MeteocatLightning.stroke_index)).all()
    assert strokes == [(1, 2), (2, 2)]


def test_two_strokes_may_share_flash_and_instant(db_session, provider):
    """81 such pairs in the delivery: there is deliberately no unique constraint."""
    db_session.add(a_stroke(provider, multiplicity=2, stroke_index=1))
    db_session.add(a_stroke(provider, multiplicity=2, stroke_index=2, peak_current=-22.903,
                            geometry="SRID=4326;POINT(2.132422 40.963436)",
                            geometry_etrs89="SRID=4258;POINT(2.132422 40.963436)"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(MeteocatLightning)) == 2


def test_the_same_flash_id_in_two_networks_is_two_flashes(db_session, provider):
    """6,286 flash ids are used by both networks in 2009, for unrelated flashes."""
    db_session.add(a_stroke(provider, flash_id=1832764))
    db_session.add(a_version_1_stroke(provider, flash_id=1832764))
    db_session.commit()

    flashes = db_session.execute(select(MeteocatLightning.network_version, MeteocatLightning.flash_id)
                                 .distinct()).all()
    assert len(flashes) == 2


# --- Constraints -------------------------------------------------------------


@pytest.mark.parametrize("missing", [
    "network_version", "flash_id", "multiplicity", "stroke_index",
    "ellipse_major_axis", "ellipse_minor_axis", "geometry_etrs89",
])
def test_required_columns_are_enforced(db_session, provider, missing):
    db_session.add(a_stroke(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("overrides", [
    pytest.param({"network_version": 0}, id="network-version-0"),
    pytest.param({"multiplicity": 0, "stroke_index": 0}, id="multiplicity-0"),
    pytest.param({"stroke_index": 0}, id="stroke-index-0"),
    pytest.param({"multiplicity": 2, "stroke_index": 3}, id="stroke-index-past-multiplicity"),
    pytest.param({"chi_squared": -0.1}, id="negative-chi-squared"),
    pytest.param({"ellipse_minor_axis": -1.0}, id="negative-minor-axis"),
    pytest.param({"ellipse_major_axis": 400.0, "ellipse_minor_axis": 1500.0},
                 id="minor-larger-than-major"),
    pytest.param({"number_of_sensors": 0}, id="zero-sensors-is-not-recorded"),
    pytest.param({"municipality_code": "82589"}, id="municipality-code-five-digits"),
    pytest.param({"municipality_code": "08258A"}, id="municipality-code-not-digits"),
])
def test_the_checks_refuse_impossible_values(db_session, provider, overrides):
    db_session.add(a_stroke(provider, **overrides))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_a_circular_ellipse_is_allowed(db_session, provider):
    """Version 1 publishes major = minor on every stroke."""
    db_session.add(a_stroke(provider, ellipse_major_axis=2450.0, ellipse_minor_axis=2450.0))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(MeteocatLightning)) == 1


def test_the_parent_row_is_required(db_session, provider):
    """The child's primary key is a foreign key to ``lightning``."""
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "INSERT INTO meteocat_lightning (id, network_version, flash_id, multiplicity, "
            "stroke_index, ellipse_major_axis, ellipse_minor_axis, geometry_etrs89) "
            "VALUES (999, 2, 1, 1, 1, 100, 100, ST_GeomFromText('POINT(2 41)', 4258))"))
        db_session.commit()


def test_repr_before_persist():
    stroke = MeteocatLightning(date_time=DETECTED, network_version=2, flash_id=9926356)
    assert repr(stroke) == (f"MeteocatLightning(id=None, date_time={DETECTED!r}, "
                            f"network_version=2, flash_id=9926356)")


# --- Network version rule ----------------------------------------------------


@pytest.mark.parametrize(("sensors", "version"), [(0, 1), (1, 2), (2, 2), (5, 2)])
def test_the_network_version_is_told_by_the_sensor_count(sensors, version):
    assert catalonia_meteocat.network_version(sensors) == version


def test_a_negative_sensor_count_is_an_error():
    with pytest.raises(ValueError):
        catalonia_meteocat.network_version(-1)


def test_the_published_header():
    assert catalonia_meteocat.COLUMNS == (
        "secidx", "data", "correntpic", "chi2", "eixmajor", "eixmenor", "numsensors",
        "nuvolterra", "idmunicipi", "longitud", "latitud")
