#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the time zone area import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and a small shapefile archive laid out like the published release, so
the whole path is exercised — the subprocess, ``/vsizip/``, the staging table and
the SQL mapping. A mocked ``ogr2ogr`` would test nothing that matters here.
"""

import logging
import shutil

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.time_zones.timezone_boundary_builder import import_time_zones as app
from src.data_model import Base
from src.data_model.geography.time_zone import TimeZone
from src.settings import ROOT_DIR

#: Five zones, hand-built rather than cut from the 100 MB release: the tests need
#: to know exactly which point falls in which zone, and a synthetic fixture is
#: the only way to state that. ``Europe/Madrid`` is drawn with a hole that
#: ``Atlantic/Canary`` fills exactly, so no point is ever in two zones — which is
#: also what the real release guarantees, and what lets the wildfire importer
#: take the first match it finds.
SAMPLE_ARCHIVE = ROOT_DIR / "test" / "fixtures" / "data" / "tzbb_time_zones_sample.zip"

SAMPLE_ZONES = {"America/Los_Angeles", "Europe/Madrid", "Atlantic/Canary",
                "Europe/Paris", "Australia/Sydney"}

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-time-zone-import")


@pytest.fixture
def database(postgresql):
    """An ephemeral PostGIS database with the model schema, plus its connection info."""
    info = postgresql.info
    url = f"postgresql+psycopg://{info.user}:{info.password or ''}@{info.host}:{info.port}/{info.dbname}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, info
    engine.dispose()


@pytest.fixture
def args(database):
    """Command-line arguments pointing at the ephemeral database and the sample archive."""
    _, info = database
    return app.parse_arguments([
        "--shapefile", str(SAMPLE_ARCHIVE),
        "--db-host", info.host, "--db-port", str(info.port),
        "--db-name", info.dbname, "--db-user", info.user,
        "--db-password", info.password or "",
    ])


# --------------------------------------------------------------------------
# Arguments (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_the_shapefile_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-s", "timezones.zip"])
    assert parsed.shapefile == Path("timezones.zip")
    assert parsed.tzid_field == app.DEFAULT_TZID_FIELD
    assert parsed.staging_schema == "staging"
    assert parsed.keep_staging is False


def test_main_reports_a_missing_file_with_the_download_url(caplog):
    """The file is a 100 MB download the user has to fetch by hand, so say where from."""
    assert app.main(["-s", "/nonexistent/timezones.zip", "--db-name", "x", "--db-user", "y"]) == 1
    assert "not found" in caplog.text
    assert "github.com/evansiroky/timezone-boundary-builder" in caplog.text


def test_main_reports_a_missing_ogr2ogr(caplog):
    exit_code = app.main(["-s", str(SAMPLE_ARCHIVE), "--db-name", "x", "--db-user", "y",
                          "--ogr2ogr", "/nonexistent/ogr2ogr"])
    assert exit_code == 1
    assert "GDAL" in caplog.text


# --------------------------------------------------------------------------
# The import itself (real ogr2ogr, real PostGIS, real archive)
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_sample_is_imported(database, args):
    engine, _ = database
    assert app.import_time_zones(args, engine, logger) == len(SAMPLE_ZONES)

    with Session(engine) as session:
        assert set(session.scalars(select(TimeZone.name)).all()) == SAMPLE_ZONES


@needs_ogr2ogr
def test_the_archive_is_read_without_being_unpacked(database, args, tmp_path):
    """GDAL reads the shapefile out of the zip, so a 100 MB release needs no temp space."""
    datasource, layer = app.common.shapefile_datasource(SAMPLE_ARCHIVE)
    assert datasource.startswith("/vsizip/")
    assert layer == "combined-shapefile-with-oceans"

    engine, _ = database
    app.import_time_zones(args, engine, logger)
    assert not list(tmp_path.iterdir())


@needs_ogr2ogr
def test_the_geometries_arrive_as_multipolygons_in_4326(database, args):
    """``ST_Collect`` on multipolygons yields a GEOMETRYCOLLECTION the column rejects."""
    engine, _ = database
    app.import_time_zones(args, engine, logger)

    with Session(engine) as session:
        assert set(session.scalars(select(func.GeometryType(TimeZone.geometry))).all()) == {"MULTIPOLYGON"}
        assert set(session.scalars(select(func.ST_SRID(TimeZone.geometry))).all()) == {4326}


@needs_ogr2ogr
def test_every_imported_name_is_one_postgresql_can_resolve(database, args):
    """A zone name is only worth storing if ``AT TIME ZONE`` accepts it."""
    engine, _ = database
    app.import_time_zones(args, engine, logger)

    with Session(engine) as session:
        unknown = session.scalars(text(
            "SELECT time_zone.name FROM time_zone WHERE NOT EXISTS "
            "(SELECT 1 FROM pg_timezone_names WHERE pg_timezone_names.name = time_zone.name)"
        )).all()
        assert unknown == []


@needs_ogr2ogr
def test_the_hole_in_a_zone_belongs_to_the_zone_that_fills_it(database, args):
    """Zones tile the area they cover: a point is in exactly one of them."""
    engine, _ = database
    app.import_time_zones(args, engine, logger)

    with Session(engine) as session:
        # A point in the pocket cut out of Europe/Madrid.
        matches = session.scalars(text(
            "SELECT name FROM time_zone WHERE ST_Contains(geometry, ST_SetSRID(ST_Point(0.5, 43.5), 4326))"
        )).all()
        assert matches == ["Atlantic/Canary"]


@needs_ogr2ogr
def test_re_importing_replaces_the_geometry_rather_than_duplicating(database, args):
    """Re-running is how the table is upgraded to a newer IANA release."""
    engine, _ = database
    assert app.import_time_zones(args, engine, logger) == len(SAMPLE_ZONES)
    # Every row is written again, so the count is the same, not zero as it would
    # be for an importer that skipped conflicts.
    assert app.import_time_zones(args, engine, logger) == len(SAMPLE_ZONES)

    with Session(engine) as session:
        assert len(session.scalars(select(TimeZone)).all()) == len(SAMPLE_ZONES)


@needs_ogr2ogr
def test_the_staging_table_is_dropped(database, args):
    engine, _ = database
    app.import_time_zones(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.tzbb_time_zones')")) is None


@needs_ogr2ogr
def test_the_staging_table_can_be_kept(database, args):
    engine, _ = database
    args.keep_staging = True
    app.import_time_zones(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT COUNT(*) FROM staging.tzbb_time_zones")) == len(SAMPLE_ZONES)


@needs_ogr2ogr
def test_a_broken_archive_is_reported(database, args, tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_text("this is not a zip")
    args.shapefile = broken

    engine, _ = database
    with pytest.raises(Exception):
        app.import_time_zones(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database):
    """The single command a user actually types."""
    engine, info = database
    exit_code = app.main([
        "-s", str(SAMPLE_ARCHIVE),
        "--db-host", info.host, "--db-port", str(info.port),
        "--db-name", info.dbname, "--db-user", info.user,
        "--db-password", info.password or "",
    ])
    assert exit_code == 0

    with Session(engine) as session:
        assert len(session.scalars(select(TimeZone)).all()) == len(SAMPLE_ZONES)
