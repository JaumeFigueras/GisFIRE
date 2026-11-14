#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Alaska (USWFS) lightning model and the provider constants.

What is worth pinning down: that a stroke is stored across the two tables and
loads back as an :class:`AlaskaUswfsLightning` from a query on the generic model;
that the published point is the parent's EPSG:4326 one, with no second point; that
the values the release leaves unknown (a cloud stroke's peak current, a semi-major
axis of 0, the first sequence numbers) can be NULL; that a flash is identified by
its first stroke's id, which the CHECKs enforce; that the other CHECKs hold and the
edges seen in the release pass them; and that the partial index on ``lightning``
exists and covers only this provider.

The stroke values are those of real strokes (U.S. Wildland Fire Service, Alaska
Lightning Detection Network, public domain).
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
from src.providers import alaska_uswfs
from src.providers.alaska_uswfs.lightning import AlaskaUswfsLightning

UTC = datetime.timezone.utc

#: 2025-07-01 22:42:58.009 UTC, near the Alaska-Yukon border: the first of three
#: ground strokes within a quarter of a second and 3 km, one flash by the import's
#: rule. Local ids 101 to 103, so the flash is 101.
DETECTED = datetime.datetime(2025, 7, 1, 22, 42, 58, 9000, tzinfo=UTC)

#: The two strokes after the first, as published (ellipse in metres), by their
#: number in the flash.
SUBSEQUENT = {
    2: {"date_time": datetime.datetime(2025, 7, 1, 22, 42, 58, 18000, tzinfo=UTC),
        "point": "POINT(-141.6045164 65.3348045)", "peak_current": -22.1,
        "ellipse_semi_major_axis": 4000.0, "ellipse_angle": 72.0, "sequence_number": 53587},
    3: {"date_time": datetime.datetime(2025, 7, 1, 22, 42, 58, 262000, tzinfo=UTC),
        "point": "POINT(-141.6682276 65.2959655)", "peak_current": -32.5,
        "ellipse_semi_major_axis": 4000.0, "ellipse_angle": 71.0, "sequence_number": 53588},
}


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=alaska_uswfs.PROVIDER_NAME,
                            product=alaska_uswfs.PROVIDER_PRODUCT,
                            full_name=alaska_uswfs.PROVIDER_FULL_NAME,
                            description=alaska_uswfs.PROVIDER_DESCRIPTION,
                            url=alaska_uswfs.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_stroke(provider, **overrides) -> AlaskaUswfsLightning:
    """The first stroke of a three-stroke flash, as stored: kA, metres, its own flash."""
    values = {
        "id": 101,
        "data_provider": provider,
        "date_time": DETECTED,
        "geometry": "SRID=4326;POINT(-141.6709543 65.3145394)",
        "peak_current": -17.1,
        "cloud_to_ground": True,
        "flash_id": 101,
        "multiplicity": 3,
        "stroke_index": 1,
        "network_code": 0,
        "sequence_number": 53586,
        "gdop": 3,
        "ellipse_semi_major_axis": 3000.0,
        "ellipse_semi_minor_axis": 1000.0,
        "ellipse_angle": 72.0,
    }
    values.update(overrides)
    return AlaskaUswfsLightning(**values)


def a_subsequent_stroke(provider, number, **overrides) -> AlaskaUswfsLightning:
    """Stroke ``number`` (2 or 3) of the same flash, local id ``100 + number``."""
    values = dict(SUBSEQUENT[number])
    point = values.pop("point")
    values.update({"id": 100 + number, "stroke_index": number, "geometry": f"SRID=4326;{point}"})
    values.update(overrides)
    return a_stroke(provider, **values)


def a_lone_stroke(provider, **overrides) -> AlaskaUswfsLightning:
    """A single-stroke flash: the stroke is its own flash, local id 200."""
    values = {"id": 200, "flash_id": 200, "multiplicity": 1, "stroke_index": 1}
    values.update(overrides)
    return a_stroke(provider, **values)


# --- Provider constants ------------------------------------------------------


def test_the_provider_constants_make_a_storable_row(db_session, provider):
    stored = db_session.scalar(select(DataProvider))
    assert (stored.name, stored.product) == ("USWFS", "ALDN")
    assert stored.full_name == "U.S. Wildland Fire Service, Alaska Geographic Area"


def test_the_published_crs_is_wgs84_and_the_projected_one_alaska_albers():
    assert alaska_uswfs.SOURCE_SRID == 4326
    assert alaska_uswfs.PROJECTED_SRID == 3338


def test_the_units_are_converted_by_these_factors():
    """Amperes to kiloamperes, kilometres to metres."""
    assert -17100 / alaska_uswfs.AMPERES_PER_KILOAMPERE == -17.1
    assert 3 * alaska_uswfs.ELLIPSE_AXIS_FACTOR == 3000.0


def test_the_file_columns_are_the_fifteen_published():
    assert alaska_uswfs.FILE_COLUMNS == (
        "STROKETYPE", "NETWORKCODE", "UTCDATETIME", "LOCALDATETIME", "MILLISECONDS",
        "LATITUDE", "LONGITUDE", "AMPLITUDE", "GDOP", "ERRSEMIMAJOR", "ERRSEMIMINOR",
        "ERRELIPSEANGLE", "STRIKETIME", "STRIKESEQNUMBER", "POLARITY")


def test_the_network_area_crosses_the_antimeridian_and_holds_the_release():
    """Written past 180: the westernmost stroke is at 168.84 E, the easternmost at
    96.99 W, which is 263.01 in that frame."""
    west, south, east, north = alaska_uswfs.NETWORK_AREA
    assert west < 180 < east
    assert west <= 168.8395933 and east >= -96.9890332 + 360
    assert south <= 46.110856 and north >= 79.3717645


def test_the_flash_rule_is_the_nldn_one():
    assert (alaska_uswfs.FLASH_MAX_DURATION_S, alaska_uswfs.FLASH_MAX_INTERVAL_S,
            alaska_uswfs.FLASH_MAX_DISTANCE_KM) == (1.0, 0.5, 10.0)


# --- Persistence -------------------------------------------------------------


def test_a_stroke_persists_across_both_tables(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(AlaskaUswfsLightning))
    assert stored.type == "alaska_uswfs_lightning"
    assert stored.date_time == DETECTED
    assert stored.peak_current == -17.1
    assert stored.cloud_to_ground is True
    assert (stored.id, stored.flash_id) == (101, 101)
    assert (stored.multiplicity, stored.stroke_index) == (3, 1)
    assert (stored.network_code, stored.sequence_number, stored.gdop) == (0, 53586, 3)
    assert (stored.ellipse_semi_major_axis, stored.ellipse_semi_minor_axis) == (3000.0, 1000.0)
    assert stored.ellipse_angle == 72.0
    assert stored.data_provider.name == "USWFS"

    parent, child = db_session.execute(text(
        "SELECT (SELECT count(*) FROM lightning), "
        "(SELECT count(*) FROM alaska_uswfs_lightning)")).one()
    assert (parent, child) == (1, 1)


def test_the_millisecond_is_kept(db_session, provider):
    """The release's ``MILLISECONDS`` is the fraction of the second."""
    db_session.add(a_stroke(provider))
    db_session.commit()

    assert db_session.scalar(select(Lightning.date_time)).microsecond == 9000


def test_a_query_on_the_generic_model_loads_the_subclass(db_session, provider):
    db_session.add(a_stroke(provider))
    db_session.commit()
    db_session.expunge_all()

    assert isinstance(db_session.scalar(select(Lightning)), AlaskaUswfsLightning)


def test_the_published_point_is_the_parent_one(db_session, provider):
    """WGS 84 as published: no second point, unlike MeteoCat's and FMI's ETRS89."""
    db_session.add(a_stroke(provider))
    db_session.commit()

    stored = db_session.scalar(select(AlaskaUswfsLightning))
    assert to_shape(stored.geometry) == Point(-141.6709543, 65.3145394)
    assert db_session.scalar(select(func.ST_SRID(Lightning.geometry))) == 4326
    geometry_columns = db_session.scalar(text(
        "SELECT count(*) FROM geometry_columns WHERE f_table_name = 'alaska_uswfs_lightning'"))
    assert geometry_columns == 0


def test_a_stroke_east_of_the_antimeridian_is_stored(db_session, provider):
    """2012-03-08 12:33:52.343, off Kamchatka, far from the network."""
    db_session.add(a_lone_stroke(
        provider, date_time=datetime.datetime(2012, 3, 8, 12, 33, 52, 343000, tzinfo=UTC),
        geometry="SRID=4326;POINT(172.2168772 52.7427544)", peak_current=-13.4,
        sequence_number=11448, gdop=74, ellipse_semi_major_axis=78000.0,
        ellipse_semi_minor_axis=4000.0, ellipse_angle=58.0))
    db_session.commit()

    assert to_shape(db_session.scalar(select(Lightning.geometry))) == Point(172.2168772, 52.7427544)


def test_a_cloud_stroke_has_no_peak_current(db_session, provider):
    """Published with amplitude 0, which is what makes it a cloud stroke."""
    db_session.add(a_lone_stroke(
        provider, date_time=datetime.datetime(2025, 7, 1, 2, 55, 5, 955000, tzinfo=UTC),
        geometry="SRID=4326;POINT(-142.0510035 65.3835595)", peak_current=None,
        cloud_to_ground=False, sequence_number=53404, gdop=4,
        ellipse_semi_major_axis=5000.0, ellipse_angle=60.0))
    db_session.commit()

    stored = db_session.scalar(select(AlaskaUswfsLightning))
    assert (stored.peak_current, stored.cloud_to_ground) == (None, False)


def test_a_semi_major_axis_published_as_0_is_unknown(db_session, provider):
    """2014-04-26 03:29:59.901: semi-major 0, semi-minor 1 km — no ellipse."""
    db_session.add(a_lone_stroke(
        provider, date_time=datetime.datetime(2014, 4, 26, 3, 29, 59, 901000, tzinfo=UTC),
        geometry="SRID=4326;POINT(-151.1559262 63.4966092)", peak_current=-53.8,
        sequence_number=65509, gdop=1, ellipse_semi_major_axis=None, ellipse_angle=-50.0))
    db_session.commit()

    stored = db_session.scalar(select(AlaskaUswfsLightning))
    assert (stored.ellipse_semi_major_axis, stored.ellipse_semi_minor_axis) == (None, 1000.0)


def test_a_stroke_without_sequence_number_is_stored(db_session, provider):
    """The first eight strokes of the release, 2012-03-07 and 08, have none."""
    db_session.add(a_lone_stroke(
        provider, date_time=datetime.datetime(2012, 3, 7, 7, 43, 29, 965000, tzinfo=UTC),
        geometry="SRID=4326;POINT(-159.6652234 59.7341875)", peak_current=-0.9,
        sequence_number=None, gdop=4, ellipse_semi_major_axis=5000.0, ellipse_angle=7.0))
    db_session.commit()

    assert db_session.scalar(select(AlaskaUswfsLightning)).sequence_number is None


# --- Flashes -----------------------------------------------------------------


def test_a_flash_is_its_first_stroke_id(db_session, provider):
    db_session.add(a_stroke(provider))
    for number in (2, 3):
        db_session.add(a_subsequent_stroke(provider, number))
    db_session.commit()

    strokes = db_session.execute(
        select(AlaskaUswfsLightning.id, AlaskaUswfsLightning.stroke_index,
               AlaskaUswfsLightning.multiplicity)
        .where(AlaskaUswfsLightning.flash_id == 101)
        .order_by(AlaskaUswfsLightning.stroke_index)).all()
    assert strokes == [(101, 1, 3), (102, 2, 3), (103, 3, 3)]


def test_two_strokes_may_share_their_millisecond_and_point(db_session, provider):
    """No unique constraint: 40,740 strokes share their millisecond with another."""
    db_session.add(a_stroke(provider, multiplicity=2))
    db_session.add(a_subsequent_stroke(provider, 2, multiplicity=2, date_time=DETECTED,
                                       geometry="SRID=4326;POINT(-141.6709543 65.3145394)"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(AlaskaUswfsLightning)) == 2


# --- Constraints -------------------------------------------------------------


@pytest.mark.parametrize("missing", [
    "flash_id", "multiplicity", "stroke_index", "network_code", "gdop",
    "ellipse_semi_minor_axis", "ellipse_angle",
])
def test_required_columns_are_enforced(db_session, provider, missing):
    db_session.add(a_stroke(provider, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("overrides", [
    pytest.param({"flash_id": 0, "stroke_index": 2}, id="flash-id-0"),
    pytest.param({"id": 101, "flash_id": 102, "stroke_index": 2}, id="flash-id-past-id"),
    pytest.param({"stroke_index": 2}, id="first-stroke-not-index-1"),
    pytest.param({"id": 102, "flash_id": 101, "stroke_index": 1}, id="index-1-not-first-stroke"),
    pytest.param({"multiplicity": 0}, id="multiplicity-0"),
    pytest.param({"id": 102, "flash_id": 101, "stroke_index": 0}, id="stroke-index-0"),
    pytest.param({"id": 104, "flash_id": 101, "stroke_index": 4},
                 id="stroke-index-past-multiplicity"),
    pytest.param({"network_code": -1}, id="negative-network-code"),
    pytest.param({"sequence_number": -1}, id="negative-sequence-number"),
    pytest.param({"gdop": 0}, id="gdop-0"),
    pytest.param({"ellipse_semi_minor_axis": 0.0}, id="semi-minor-0"),
    pytest.param({"ellipse_semi_major_axis": 0.0}, id="semi-major-0-not-null"),
    pytest.param({"ellipse_semi_major_axis": 1000.0, "ellipse_semi_minor_axis": 2000.0},
                 id="semi-minor-larger-than-semi-major"),
    pytest.param({"ellipse_angle": -90.5}, id="angle-below-minus-90"),
    pytest.param({"ellipse_angle": 90.5}, id="angle-past-90"),
])
def test_the_checks_refuse_impossible_values(db_session, provider, overrides):
    db_session.add(a_stroke(provider, **overrides))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("overrides", [
    pytest.param({"peak_current": 500.0}, id="plus-500-kA"),
    pytest.param({"peak_current": -500.0}, id="minus-500-kA"),
    pytest.param({"gdop": 255, "ellipse_semi_major_axis": 255000.0,
                  "ellipse_semi_minor_axis": 9000.0}, id="field-ceilings"),
    pytest.param({"ellipse_semi_major_axis": 1000.0}, id="circle"),
    pytest.param({"ellipse_angle": -89.0}, id="angle-minus-89"),
    pytest.param({"ellipse_angle": 89.0}, id="angle-89"),
    pytest.param({"ellipse_angle": -90.0}, id="angle-minus-90"),
    pytest.param({"ellipse_angle": 90.0}, id="angle-90"),
    pytest.param({"sequence_number": 0}, id="sequence-0"),
    pytest.param({"sequence_number": 65535}, id="sequence-65535"),
])
def test_the_edges_seen_in_the_release_are_allowed(db_session, provider, overrides):
    """Every one of these occurs in the 2012-2026 release (±90 for the angle is the
    same orientation as ±89.x, and allowed)."""
    db_session.add(a_lone_stroke(provider, **overrides))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(AlaskaUswfsLightning)) == 1


def test_the_parent_row_is_required(db_session, provider):
    """The child's primary key is a foreign key to ``lightning``."""
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "INSERT INTO alaska_uswfs_lightning (id, flash_id, multiplicity, stroke_index, "
            "network_code, sequence_number, gdop, ellipse_semi_major_axis, "
            "ellipse_semi_minor_axis, ellipse_angle) "
            "VALUES (999, 999, 1, 1, 0, 1, 1, 1000, 1000, 0)"))
        db_session.commit()


# --- The partial index on lightning ------------------------------------------


def test_the_projected_point_is_indexed_on_lightning_for_this_provider_only(db_session):
    """The point lives on ``lightning``, so the index of the 3338 view does too —
    partial, or it would index every provider's strokes."""
    definition = db_session.scalar(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'idx_lightning_alaska_uswfs_geometry_3338'"))
    assert definition.startswith("CREATE INDEX idx_lightning_alaska_uswfs_geometry_3338 "
                                 "ON public.lightning USING gist")
    # pg_get_indexdef adds a pair of parentheses around the function call.
    assert "st_transform(geometry, 3338))::geometry(Point,3338)" in definition
    assert "WHERE ((type)::text = 'alaska_uswfs_lightning'::text)" in definition


def test_repr_before_persist():
    stroke = AlaskaUswfsLightning(date_time=DETECTED, flash_id=101)
    assert repr(stroke) == f"AlaskaUswfsLightning(id=None, date_time={DETECTED!r}, flash_id=101)"
