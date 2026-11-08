#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the MeteoCat lightning import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on extracts written like the delivery. What is being tested is
what this dataset makes hard: that a **UTC year** is the unit replaced, since
nothing identifies a stroke; that the published ETRS89 point is stored as published
beside its EPSG:4326 reprojection; that the flash numbering reaches the database;
and that the country is resolved by a spatial join, strokes at sea having none.
"""

import datetime
import logging

from pathlib import Path

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.lightnings.catalonia_meteocat import import_lightnings as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import catalonia_meteocat
from src.providers import ocha
from src.providers.catalonia_meteocat.lightning import MeteocatLightning

from .conftest import CATALONIA_WKT
from .conftest import ROWS_2009
from .conftest import ROWS_2010
from .conftest import extract_2009
from .conftest import extract_2010
from .conftest import write_extract

UTC = datetime.timezone.utc


@pytest.fixture
def database(postgresql):
    """An empty GisFIRE schema on an ephemeral PostgreSQL, and its URL."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, url
    engine.dispose()


@pytest.fixture
def catalonia(database):
    """An OCHA country boundary roughly the shape of Catalonia's coast."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name="OCHA")
        session.add(provider)
        session.flush()
        boundary = AdminBoundary(data_provider_id=provider.id, source_id="ESP", level=0,
                                 name="Spain", geometry=f"SRID=4326;{CATALONIA_WKT}")
        session.add(boundary)
        session.commit()
        return boundary.id


def run(url: str, *paths: Path, extra: list[str] | None = None, directory: Path | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    source = ["-d", str(directory)] if directory is not None else ["-s", *[str(path) for path in paths]]
    argv = [*source,
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def strokes(engine) -> list[MeteocatLightning]:
    """Every stroke, by instant and then by flash numbering."""
    with Session(engine) as session:
        return session.scalars(select(MeteocatLightning).order_by(
            MeteocatLightning.date_time, MeteocatLightning.stroke_index)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


def stroke_at(engine, current: float) -> MeteocatLightning:
    """The one stroke with this peak current (they are all different)."""
    with Session(engine) as session:
        return session.scalars(select(MeteocatLightning)
                               .where(MeteocatLightning.peak_current == current)).one()


# --------------------------------------------------------------------------
# An extract round trips
# --------------------------------------------------------------------------

def test_an_extract_is_imported_whole(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert count(engine, "meteocat_lightning") == len(ROWS_2009)


def test_the_provider_row_is_created_once(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    with Session(engine) as session:
        providers = session.scalars(select(DataProvider)).all()
    assert len(providers) == 1
    provider = providers[0]
    assert (provider.name, provider.product) == (catalonia_meteocat.PROVIDER_NAME,
                                                 catalonia_meteocat.PROVIDER_PRODUCT)
    assert provider.full_name == catalonia_meteocat.PROVIDER_FULL_NAME
    assert provider.description == catalonia_meteocat.PROVIDER_DESCRIPTION
    assert provider.url == catalonia_meteocat.PROVIDER_URL


def test_a_version_2_stroke_is_stored_as_published(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, -30.5)
    assert stroke.type == "meteocat_lightning"
    assert stroke.date_time == datetime.datetime(2009, 9, 15, 14, 2, 11, 500000, tzinfo=UTC)
    assert stroke.cloud_to_ground is True
    assert (stroke.network_version, stroke.flash_id) == (2, 1832764)
    assert stroke.chi_squared == 1.2
    assert (stroke.ellipse_major_axis, stroke.ellipse_minor_axis) == (1800.0, 500.0)
    assert stroke.ellipse_angle is None
    assert stroke.number_of_sensors == 3
    assert stroke.municipality_code is None


def test_a_version_1_stroke_stores_not_recorded_as_null(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, 12.198)
    assert stroke.network_version == 1
    assert stroke.number_of_sensors is None
    assert stroke.chi_squared is None
    assert stroke.municipality_code == "080193"
    assert stroke.date_time == datetime.datetime(2009, 1, 2, 5, 32, 19, 3386, tzinfo=UTC)


def test_the_point_is_stored_as_published_and_in_4326(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    stroke = stroke_at(engine, -30.5)
    assert to_shape(stroke.geometry_etrs89) == Point(1.51, 41.61)
    reprojected = to_shape(stroke.geometry)
    assert reprojected.distance(Point(1.51, 41.61)) < 1e-5
    with Session(engine) as session:
        srids = session.execute(text(
            "SELECT DISTINCT ST_SRID(l.geometry), ST_SRID(m.geometry_etrs89) "
            "FROM lightning l JOIN meteocat_lightning m ON m.id = l.id")).all()
    assert srids == [(4326, 4258)]


def test_an_intra_cloud_stroke_is_stored_as_such(database, tmp_path):
    engine, url = database
    assert run(url, extract_2010(tmp_path)) == 0

    assert stroke_at(engine, 40.1).cloud_to_ground is False


# --------------------------------------------------------------------------
# Flashes
# --------------------------------------------------------------------------

def test_the_flash_numbering_is_stored(database, tmp_path):
    """Version 1's flash 910429 is published 2nd, 1st, 3rd."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    numbering = [(stroke_at(engine, current).stroke_index, stroke_at(engine, current).multiplicity)
                 for current in (-2.241, -1.532, 0.71)]
    assert numbering == [(1, 3), (2, 3), (3, 3)]


def test_the_same_flash_id_in_two_networks_is_numbered_separately(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    assert (stroke_at(engine, -15.2).network_version, stroke_at(engine, -15.2).multiplicity) == (1, 1)
    assert [(stroke_at(engine, c).stroke_index, stroke_at(engine, c).multiplicity)
            for c in (-30.5, -18.1)] == [(1, 2), (2, 2)]


def test_first_strokes_are_one_per_flash(database, tmp_path):
    """``stroke_index = 1`` is what a flash-density count selects."""
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    with Session(engine) as session:
        first = session.scalar(text("SELECT count(*) FROM meteocat_lightning WHERE stroke_index = 1"))
        flashes = session.scalar(text(
            "SELECT count(*) FROM (SELECT DISTINCT network_version, flash_id "
            "FROM meteocat_lightning) AS f"))
    assert first == flashes == 6


# --------------------------------------------------------------------------
# The administrative boundary
# --------------------------------------------------------------------------

def test_strokes_on_land_get_the_country_and_at_sea_none(database, catalonia, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0

    on_land = {12.198, -15.2, -30.5, -18.1}
    for stroke in strokes(engine):
        expected = catalonia if stroke.peak_current in on_land else None
        assert stroke.admin_boundary_id == expected, stroke.peak_current


def test_without_boundaries_the_strokes_are_still_imported(database, tmp_path, caplog):
    engine, url = database
    with caplog.at_level(logging.WARNING):
        assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert all(stroke.admin_boundary_id is None for stroke in strokes(engine))
    assert "boundaries" in caplog.text


# --------------------------------------------------------------------------
# The year is the unit
# --------------------------------------------------------------------------

def test_importing_a_year_again_replaces_it(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path)) == 0
    first_ids = {stroke.id for stroke in strokes(engine)}
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009)
    assert count(engine, "meteocat_lightning") == len(ROWS_2009)
    assert first_ids.isdisjoint({stroke.id for stroke in strokes(engine)})


def test_importing_a_year_leaves_the_others_alone(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009) + len(ROWS_2010)
    years = {stroke.date_time.year for stroke in strokes(engine)}
    assert years == {2009, 2010}


def test_the_year_boundary_is_utc(database, tmp_path):
    """The last stroke of 2009 and the first of 2010 are 73 seconds apart."""
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path)) == 0
    write_extract(tmp_path / "late.csv", [ROWS_2009[-1]])
    assert run(url, tmp_path / "late.csv") == 0

    # Re-importing 2009 from a one-stroke file leaves exactly that stroke in 2009,
    # and the stroke at 2010-01-01 00:00:00.000022 UTC untouched.
    assert count(engine, "lightning") == 1 + len(ROWS_2010)


def test_a_year_filter_imports_only_that_year(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extract_2010(tmp_path), extra=["--year", "2010"]) == 0

    assert {stroke.date_time.year for stroke in strokes(engine)} == {2010}


def test_strokes_of_other_providers_are_not_deleted(database, tmp_path):
    """Replacing a year deletes MeteoCat's strokes in it, nobody else's."""
    engine, url = database
    with engine.begin() as connection:
        other = connection.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('Other', 'Network', 'Other network') RETURNING id")).scalar()
        connection.execute(text(
            "INSERT INTO lightning (type, data_provider_id, date_time, geometry) "
            "VALUES ('lightning', :p, '2009-06-01T12:00:00Z', "
            "ST_GeomFromText('POINT(2 41)', 4326))"), {"p": other})
    assert run(url, extract_2009(tmp_path)) == 0
    assert run(url, extract_2009(tmp_path)) == 0

    assert count(engine, "lightning") == len(ROWS_2009) + 1


# --------------------------------------------------------------------------
# A directory, a dry run and the ways a run is refused
# --------------------------------------------------------------------------

def test_a_directory_imports_every_extract_and_skips_other_csvs(database, tmp_path):
    engine, url = database
    extract_2009(tmp_path)
    extract_2010(tmp_path)
    (tmp_path / "README.csv").write_text("not;an;extract\n", encoding="ascii")

    assert run(url, directory=tmp_path) == 0
    assert count(engine, "lightning") == len(ROWS_2009) + len(ROWS_2010)


def test_a_bad_row_is_skipped_and_the_rest_imported(database, tmp_path):
    engine, url = database
    bad = '1;"2009-07-01 10:00:00.000001";abc;1;300;100;3;t;"";2;41'
    path = write_extract(tmp_path / "x.csv", [*ROWS_2009, bad])

    assert run(url, path) == 0
    assert count(engine, "lightning") == len(ROWS_2009)


def test_a_dry_run_needs_no_database(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        assert app.main(["-s", str(extract_2009(tmp_path)), "--dry-run"]) == 0
    assert str(len(ROWS_2009)) in caplog.text


def test_a_dry_run_writes_nothing(database, tmp_path):
    engine, url = database
    assert run(url, extract_2009(tmp_path), extra=["--dry-run"]) == 0

    assert count(engine, "lightning") == 0


def test_a_missing_file_is_refused(database, tmp_path):
    _, url = database
    assert run(url, tmp_path / "nowhere.csv") == 1


def test_a_file_that_is_not_an_extract_is_refused(database, tmp_path):
    engine, url = database
    path = tmp_path / "other.csv"
    path.write_text("a;b;c\n1;2;3\n", encoding="ascii")

    assert run(url, path) == 1
    assert count(engine, "lightning") == 0


def test_an_unmigrated_database_is_refused(database, tmp_path):
    engine, url = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE meteocat_lightning"))

    assert run(url, extract_2009(tmp_path)) == 1
