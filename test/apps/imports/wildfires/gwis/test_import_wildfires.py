#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the GWIS GlobFire wildfire import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostGIS and a small shapefile archive laid out exactly like the published one —
same field names, same field types (``Integer64``, ``Date``), same directory
nesting inside the zip. A mocked ``ogr2ogr`` would test none of what actually
breaks here.

The seven fires in the fixture are synthetic rather than cut from the published
files, because what has to be asserted is *where each one is*: which time zone,
which country, which side of a border. That can only be stated against a world
the test defines, so the fixture builds one — four rectangular countries and
five rectangular time zones, in roughly the real places, with real IANA names so
that ``AT TIME ZONE`` resolves genuine daylight-saving rules.
"""

import datetime
import logging
import shutil

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.time_zones.timezone_boundary_builder import import_time_zones as time_zone_app
from src.apps.imports.wildfires.gwis import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.wildfire import Wildfire
from src.providers import ocha
from src.providers.gwis.wildfire import GwisWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.settings import ROOT_DIR

SAMPLE_ARCHIVE = ROOT_DIR / "test" / "fixtures" / "data" / "gwis_globfire_sample.zip"
TIME_ZONE_ARCHIVE = ROOT_DIR / "test" / "fixtures" / "data" / "tzbb_time_zones_sample.zip"

#: The four countries of the fixture world, in the order they are inserted —
#: Spain first, so that its id is the lowest. Fire 1004 straddles the
#: Spain/France border with four fifths of its area in France, so a country
#: attribution that picked the first or the lowest-numbered candidate instead of
#: the largest overlap would answer "Spain" and be caught.
COUNTRIES = [
    ("ESP", "Spain", "MULTIPOLYGON(((-9 36, 3 36, 3 44, -9 44, -9 36)))"),
    ("FRA", "France", "MULTIPOLYGON(((3 42, 8 42, 8 51, 3 51, 3 42)))"),
    ("USA", "United States", "MULTIPOLYGON(((-124 36, -120 36, -120 42, -124 42, -124 36)))"),
    ("AUS", "Australia", "MULTIPOLYGON(((145 -38, 154 -38, 154 -28, 145 -28, 145 -38)))"),
]

UTC = datetime.timezone.utc


def instant(text_value: str) -> datetime.datetime:
    """Parse an ISO instant into an aware UTC datetime, for comparing against the model."""
    return datetime.datetime.fromisoformat(text_value).astimezone(UTC)


needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-gwis-import")


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
def connection_arguments(database):
    _, info = database
    return ["--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user,
            "--db-password", info.password or ""]


@pytest.fixture
def boundaries(database, connection_arguments):
    """The four fixture countries, as OCHA boundaries under an OCHA provider row."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        for code, name, wkt in COUNTRIES:
            session.add(OchaAdminBoundary(
                data_provider_id=provider.id, source_id=code, level=0, name=name,
                geometry=f"SRID=4326;{wkt}", source=code, iso_code=1, iso_2=code[:2],
                iso_3=code, iso_name=name, iso_3_group=code,
                region1_code=1, region1_name="r1", region2_code=2, region2_name="r2",
                region3_code=3, region3_name="r3", status_code=1, status_name="State",
                valid_date=datetime.date(2025, 1, 1), update_date=datetime.date(2025, 1, 1),
                land_source="osm", view="intl",
            ))
        session.commit()


@pytest.fixture
def time_zones(database, connection_arguments):
    """The five fixture time zone areas, imported through the real importer."""
    engine, _ = database
    time_zone_app.main(["-s", str(TIME_ZONE_ARCHIVE), *connection_arguments])


@pytest.fixture
def args(connection_arguments):
    """Command-line arguments importing the sample archive into the ephemeral database."""
    return app.parse_arguments(["--shapefile", str(SAMPLE_ARCHIVE), *connection_arguments])


@pytest.fixture
def imported(database, boundaries, time_zones, args):
    """The sample archive imported into a world that has both countries and zones."""
    engine, _ = database
    count = app.import_wildfires(args, engine, logger)
    return engine, count


def fire(session: Session, gwis_id: str) -> GwisWildfire:
    return session.scalar(select(GwisWildfire).where(GwisWildfire.gwis_id == gwis_id))


# --------------------------------------------------------------------------
# Arguments (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_a_directory_and_a_file_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", "/data", "-s", "one.zip"])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-d", "/data"])
    assert parsed.directory == Path("/data")
    assert (parsed.id_field, parsed.start_field, parsed.end_field) == ("id", "idate", "fdate")
    assert parsed.staging_table == app.DEFAULT_STAGING_TABLE


def test_the_archives_of_a_directory_are_found_in_order(tmp_path):
    """Sorted, so the years are imported oldest first."""
    for year in (2021, 2000, 2010):
        (tmp_path / f"Final_GlobFirev3_GWIS_MCD64A1__{year}.zip").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")

    found = app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))
    assert [path.name for path in found] == [
        "Final_GlobFirev3_GWIS_MCD64A1__2000.zip",
        "Final_GlobFirev3_GWIS_MCD64A1__2010.zip",
        "Final_GlobFirev3_GWIS_MCD64A1__2021.zip",
    ]


def test_an_empty_directory_is_an_error(tmp_path):
    """Far more likely a wrong path than an empty download."""
    with pytest.raises(RuntimeError, match="No .zip archives"):
        app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent/gwis", "--db-name", "x", "--db-user", "y"]) == 1
    assert "Not found" in caplog.text


def test_main_reports_a_missing_ogr2ogr(caplog):
    exit_code = app.main(["-s", str(SAMPLE_ARCHIVE), "--db-name", "x", "--db-user", "y",
                          "--ogr2ogr", "/nonexistent/ogr2ogr"])
    assert exit_code == 1
    assert "GDAL" in caplog.text


# --------------------------------------------------------------------------
# Reading the published archive layout
# --------------------------------------------------------------------------

def test_the_shapefile_is_found_inside_the_zip_without_unpacking():
    """The published archives nest the shapefile in a directory named after itself."""
    datasource, layer = app.common.shapefile_datasource(SAMPLE_ARCHIVE)
    assert datasource.startswith("/vsizip/")
    assert datasource.endswith("Final_GlobFirev3_GWIS_MCD64A1__2021.shp")
    # The layer name carries the year, so it differs per archive and cannot be a
    # default; it has to be derived from the file.
    assert layer == "Final_GlobFirev3_GWIS_MCD64A1__2021"


def test_an_archive_without_a_shapefile_is_reported(tmp_path):
    import zipfile
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "no shapefile here")

    with pytest.raises(RuntimeError, match="no shapefile"):
        app.common.shapefile_datasource(archive)


# --------------------------------------------------------------------------
# The import itself (real ogr2ogr, real PostGIS, real archive)
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_fire_is_imported(imported):
    engine, count = imported
    assert count == 7

    with Session(engine) as session:
        ids = session.scalars(select(GwisWildfire.gwis_id).order_by(GwisWildfire.gwis_id)).all()
        assert ids == ["1001", "1002", "1003", "1004", "1005", "1006", "1007"]


@needs_ogr2ogr
def test_the_joined_inheritance_rows_are_written_in_pairs(imported):
    """Every ``wildfire`` row must have its ``gwis_wildfire`` half and vice versa."""
    engine, _ = imported
    with Session(engine) as session:
        orphan_parents = session.scalar(text(
            "SELECT count(*) FROM wildfire w LEFT JOIN gwis_wildfire g ON g.id = w.id "
            "WHERE g.id IS NULL"
        ))
        orphan_children = session.scalar(text(
            "SELECT count(*) FROM gwis_wildfire g LEFT JOIN wildfire w ON w.id = g.id "
            "WHERE w.id IS NULL"
        ))
        assert (orphan_parents, orphan_children) == (0, 0)
        assert session.scalars(select(Wildfire.type).distinct()).all() == ["gwis_wildfire"]


@needs_ogr2ogr
def test_a_bare_date_becomes_local_midnight(imported):
    """``IDate`` has no time; the day starts at 00:00 where the fire burnt.

    2021-07-29 in California is PDT, seven hours behind UTC.
    """
    engine, _ = imported
    with Session(engine) as session:
        california = fire(session, "1001")
        assert california.time_zone == "America/Los_Angeles"
        assert california.start_date_time == instant("2021-07-29T07:00:00+00:00")


@needs_ogr2ogr
def test_the_end_date_is_the_last_second_of_its_day(imported):
    """``FDate`` closes the fire at 23:59:59 local, not at midnight starting it."""
    engine, _ = imported
    with Session(engine) as session:
        california = fire(session, "1001")
        # 2021-09-21 23:59:59 PDT.
        assert california.end_date_time == instant("2021-09-22T06:59:59+00:00")


@needs_ogr2ogr
def test_daylight_saving_is_resolved_from_each_date(imported):
    """The offset is a property of the date, which is why the zone is stored by name.

    Two fires in the same place, one in January and one in July: Madrid is UTC+1
    in winter and UTC+2 in summer. A stored fixed offset could not get both
    right.
    """
    engine, _ = imported
    with Session(engine) as session:
        winter, summer = fire(session, "1002"), fire(session, "1003")
        assert winter.time_zone == summer.time_zone == "Europe/Madrid"
        assert winter.start_date_time == instant("2021-01-14T23:00:00+00:00")   # CET,  UTC+1
        assert summer.start_date_time == instant("2021-06-30T22:00:00+00:00")   # CEST, UTC+2


@needs_ogr2ogr
def test_the_published_local_reading_is_recoverable(imported):
    """The point of keeping the zone: ``AT TIME ZONE`` gives the dates back as published."""
    engine, _ = imported
    with Session(engine) as session:
        local = session.execute(text(
            "SELECT (start_date_time AT TIME ZONE w.time_zone)::date, "
            "       (end_date_time AT TIME ZONE w.time_zone)::date "
            "FROM wildfire w JOIN gwis_wildfire g ON g.id = w.id WHERE g.gwis_id = '1001'"
        )).one()
        assert local == (datetime.date(2021, 7, 29), datetime.date(2021, 9, 21))


@needs_ogr2ogr
def test_a_fire_with_no_end_date_keeps_none(imported):
    engine, _ = imported
    with Session(engine) as session:
        australia = fire(session, "1006")
        assert australia.end_date_time is None
        # The start is still resolved: AEST, ten hours ahead, and no DST in June.
        assert australia.start_date_time == instant("2021-05-31T14:00:00+00:00")


@needs_ogr2ogr
def test_the_zone_comes_from_a_point_inside_the_burn(imported):
    """A C-shaped burn's centroid lands in the unburnt pocket it wraps around.

    The fixture puts a different time zone in that pocket, so a centroid-based
    lookup would answer ``Atlantic/Canary`` for a fire that is entirely inside
    ``Europe/Madrid``.
    """
    engine, _ = imported
    with Session(engine) as session:
        crescent = fire(session, "1007")
        assert crescent.time_zone == "Europe/Madrid"
        assert crescent.start_date_time == instant("2021-07-14T22:00:00+00:00")

        # The property that makes it work, stated directly.
        on_surface, centroid = session.execute(text(
            "SELECT ST_Contains(perimeter, ST_PointOnSurface(perimeter)), "
            "       ST_Contains(perimeter, ST_Centroid(perimeter)) "
            "FROM wildfire WHERE id = :id"
        ), {"id": crescent.id}).one()
        assert (on_surface, centroid) == (True, False)


@needs_ogr2ogr
def test_a_fire_outside_every_zone_falls_back_to_utc(imported):
    """The fixture zones do not cover the ocean, as a release without oceans would not."""
    engine, _ = imported
    with Session(engine) as session:
        atlantic = fire(session, "1005")
        assert atlantic.time_zone is None
        assert atlantic.start_date_time == instant("2021-05-05T00:00:00+00:00")
        assert atlantic.end_date_time == instant("2021-05-06T23:59:59+00:00")


# --------------------------------------------------------------------------
# Country attribution
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_each_fire_gets_the_country_it_burnt_in(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "1001").admin_boundary.name == "United States"
        assert fire(session, "1002").admin_boundary.name == "Spain"
        assert fire(session, "1006").admin_boundary.name == "Australia"


@needs_ogr2ogr
def test_a_border_straddling_fire_goes_to_the_country_holding_most_of_it(imported):
    """Fire 1004 spans lon 2.9-3.8: one tenth in Spain, the rest in France.

    Spain is inserted first and so has the lower id, which is what makes this
    test able to tell "largest overlap" apart from "first match" or "lowest id".
    """
    engine, _ = imported
    with Session(engine) as session:
        straddler = fire(session, "1004")
        assert straddler.admin_boundary.name == "France"

        spain = session.scalar(select(AdminBoundary).where(AdminBoundary.name == "Spain"))
        france = session.scalar(select(AdminBoundary).where(AdminBoundary.name == "France"))
        assert spain.id < france.id
        # It really does touch both, so the choice was between them.
        touched = session.scalar(text(
            "SELECT count(*) FROM admin_boundary b JOIN wildfire w ON ST_Intersects(b.geometry, w.perimeter) "
            "WHERE w.id = :id"
        ), {"id": straddler.id})
        assert touched == 2


@needs_ogr2ogr
def test_a_fire_outside_every_country_gets_none(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "1005").admin_boundary is None


@needs_ogr2ogr
def test_fires_import_without_any_boundaries(database, time_zones, args, caplog):
    """The perimeters and dates are worth having before the boundaries are loaded."""
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 7

    with Session(engine) as session:
        assert session.scalars(select(Wildfire.admin_boundary_id).distinct()).all() == [None]
    assert "no country" in caplog.text


@needs_ogr2ogr
def test_fires_import_without_any_time_zones(database, boundaries, args, caplog):
    """Everything falls back to UTC, and the run says so rather than doing it quietly."""
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 7

    with Session(engine) as session:
        assert session.scalars(select(Wildfire.time_zone).distinct()).all() == [None]
        # 2021-05-05 00:00 UTC, untouched by any zone.
        assert fire(session, "1005").start_date_time == instant("2021-05-05T00:00:00+00:00")
    assert "No time zone areas loaded" in caplog.text


@needs_ogr2ogr
def test_a_time_zone_postgresql_cannot_resolve_stops_the_import(database, boundaries,
                                                                time_zones, args):
    """Caught up front: ``AT TIME ZONE`` on an unknown name would abort mid-file."""
    engine, _ = database
    with Session(engine) as session:
        session.execute(text("UPDATE time_zone SET name = 'Mars/Olympus_Mons' "
                             "WHERE name = 'Europe/Madrid'"))
        session.commit()

    with pytest.raises(RuntimeError, match="unknown to this PostgreSQL server"):
        app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        assert session.scalars(select(Wildfire)).all() == []


# --------------------------------------------------------------------------
# Geometry, provider and staging
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_perimeters_arrive_as_multipolygons_in_4326(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert set(session.scalars(select(func.GeometryType(Wildfire.perimeter))).all()) == {"MULTIPOLYGON"}
        assert set(session.scalars(select(func.ST_SRID(Wildfire.perimeter))).all()) == {4326}


@needs_ogr2ogr
def test_the_data_provider_is_created_on_first_import(imported):
    engine, _ = imported
    with Session(engine) as session:
        provider = session.scalar(
            select(DataProvider).where(DataProvider.name == "GWIS")
        )
        assert provider.product == "Global Wildfire Database v3"
        assert provider.full_name == "Global Wildfire Information System"
        assert provider.url.startswith("https://doi.pangaea.de/")

        # Every fire hangs off it, and the OCHA row is a separate provider.
        assert session.scalars(select(Wildfire.data_provider_id).distinct()).all() == [provider.id]
        assert len(session.scalars(select(DataProvider)).all()) == 2


@needs_ogr2ogr
def test_re_importing_stores_the_file_again_and_warns(database, boundaries, time_zones,
                                                      args, caplog):
    """GWIS ids are not unique, so nothing can be skipped — see GwisWildfire.

    Pinned by a test because it is a real operational hazard, not because it is
    desirable: the alternative would silently drop the 359 fires in the published
    dataset whose ids collide with another fire's.
    """
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 7
    assert app.import_wildfires(args, engine, logger) == 7

    with Session(engine) as session:
        assert len(session.scalars(select(Wildfire)).all()) == 14
        # Still one provider row, and still no orphans.
        assert len(session.scalars(select(DataProvider).where(DataProvider.name == "GWIS")).all()) == 1
    assert "already imported" in caplog.text


@needs_ogr2ogr
def test_the_staging_table_is_dropped(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.gwis_globfire')")) is None


@needs_ogr2ogr
def test_the_staging_table_can_be_kept(database, boundaries, time_zones, args):
    engine, _ = database
    args.keep_staging = True
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT COUNT(*) FROM staging.gwis_globfire")) == 7


@needs_ogr2ogr
def test_the_staging_schema_is_not_public(database, boundaries, time_zones, args):
    """A staging table in ``public`` would be dropped by the next Alembic autogenerate."""
    engine, _ = database
    args.keep_staging = True
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        schemas = session.scalars(text(
            "SELECT table_schema FROM information_schema.tables WHERE table_name = 'gwis_globfire'"
        )).all()
        assert schemas == ["staging"]


@needs_ogr2ogr
def test_a_directory_of_archives_is_imported(database, boundaries, time_zones,
                                             connection_arguments, tmp_path):
    """The normal invocation: point it at the directory the year files were downloaded to."""
    engine, _ = database
    for year in (2020, 2021):
        shutil.copy(SAMPLE_ARCHIVE, tmp_path / f"Final_GlobFirev3_GWIS_MCD64A1__{year}.zip")

    args = app.parse_arguments(["--directory", str(tmp_path), *connection_arguments])
    assert app.import_wildfires(args, engine, logger) == 14


@needs_ogr2ogr
def test_a_broken_archive_is_reported(database, boundaries, time_zones, args, tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_text("this is not a zip")
    args.shapefile = broken

    engine, _ = database
    with pytest.raises(Exception):
        app.import_wildfires(args, engine, logger)


# --------------------------------------------------------------------------
# Importing several archives at once (--jobs)
# --------------------------------------------------------------------------

def archive_directory(tmp_path, years):
    for year in years:
        shutil.copy(SAMPLE_ARCHIVE, tmp_path / f"Final_GlobFirev3_GWIS_MCD64A1__{year}.zip")
    return tmp_path


def test_one_job_is_the_default():
    assert app.parse_arguments(["-s", "x.zip"]).jobs == 1


@pytest.mark.parametrize("value", ["0", "-2"])
def test_jobs_below_one_is_rejected(value):
    with pytest.raises(SystemExit):
        app.parse_arguments(["-s", "x.zip", "--jobs", value])


@needs_ogr2ogr
def test_parallel_imports_everything_exactly_once(database, boundaries, time_zones,
                                                  connection_arguments, tmp_path):
    """Four archives across three processes must come to the same as importing them serially."""
    directory = archive_directory(tmp_path, (2018, 2019, 2020, 2021))
    args = app.parse_arguments(["--directory", str(directory), "--jobs", "3",
                                *connection_arguments])

    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 4 * 7

    with Session(engine) as session:
        assert len(session.scalars(select(GwisWildfire)).all()) == 4 * 7
        # One provider row, not one per worker: the ON CONFLICT lookup found it.
        assert len(session.scalars(
            select(DataProvider).where(DataProvider.name == "GWIS")).all()) == 1


@needs_ogr2ogr
def test_each_worker_stages_into_its_own_table_and_drops_it(database, boundaries, time_zones,
                                                            connection_arguments, tmp_path):
    """Sharing one staging table would have the workers overwrite each other's load."""
    directory = archive_directory(tmp_path, (2020, 2021))
    args = app.parse_arguments(["--directory", str(directory), "--jobs", "2",
                                "--keep-staging", *connection_arguments])

    engine, _ = database
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        kept = sorted(session.scalars(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'staging'"
        )).all())
    assert kept == ["gwis_globfire_00", "gwis_globfire_01"]


@needs_ogr2ogr
def test_one_bad_archive_does_not_cost_the_others(database, boundaries, time_zones,
                                                  connection_arguments, tmp_path, caplog):
    """Each archive is its own transaction, so the good ones are kept and reported."""
    directory = archive_directory(tmp_path, (2020, 2021))
    (directory / "Final_GlobFirev3_GWIS_MCD64A1__2022.zip").write_text("not a zip")

    args = app.parse_arguments(["--directory", str(directory), "--jobs", "3",
                                *connection_arguments])
    engine, _ = database
    with pytest.raises(RuntimeError, match="1 of 3 archive"):
        app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        assert len(session.scalars(select(GwisWildfire)).all()) == 2 * 7
    assert "2022.zip" in caplog.text


@needs_ogr2ogr
def test_more_jobs_than_archives_does_not_spawn_idle_workers(database, boundaries, time_zones,
                                                             args, monkeypatch):
    """One archive is a serial run whatever was asked for."""
    args.jobs = 8
    monkeypatch.setattr(app, "import_in_parallel",
                        lambda *a, **k: pytest.fail("a single archive went through the pool"))

    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 7


@needs_ogr2ogr
def test_main_runs_the_whole_import(database, boundaries, time_zones, connection_arguments):
    """The single command a user actually types."""
    engine, _ = database
    assert app.main(["-s", str(SAMPLE_ARCHIVE), *connection_arguments]) == 0

    with Session(engine) as session:
        assert len(session.scalars(select(GwisWildfire)).all()) == 7


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, connection_arguments, caplog):
    engine, _ = database
    exit_code = app.main(["-s", str(SAMPLE_ARCHIVE), "--id-field", "no_such_field",
                          *connection_arguments])
    assert exit_code == 1
    assert "Import failed" in caplog.text
