#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Global Fire Atlas perimeter import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and a real shapefile, so the whole path is exercised — the subprocess,
the staging table and the SQL mapping. A mocked ``ogr2ogr`` would test nothing
that matters here.

The shapefile is built from the GeoJSON below rather than checked in as a binary:
the point of every fixture fire is *which* zone, country and geometry it has, and
that has to be readable to be worth asserting against.
"""

import datetime
import json
import logging
import shutil
import subprocess

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.time_zones.timezone_boundary_builder import import_time_zones as time_zone_app
from src.apps.imports.wildfires.gfa import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import ocha
from src.providers.gfa.wildfire import GfaWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.settings import ROOT_DIR

TIME_ZONE_ARCHIVE = ROOT_DIR / "test" / "fixtures" / "data" / "tzbb_time_zones_sample.zip"

#: The fixture world, identical to the one the GWIS tests use: each country's box
#: is also a time zone's box, except for the Canary hole punched out of Madrid.
COUNTRIES = [
    ("ESP", "Spain", "MULTIPOLYGON(((-9 36, 3 36, 3 44, -9 44, -9 36)))"),
    ("FRA", "France", "MULTIPOLYGON(((3 42, 8 42, 8 51, 3 51, 3 42)))"),
    ("USA", "United States", "MULTIPOLYGON(((-124 36, -120 36, -120 42, -124 42, -124 36)))"),
    ("AUS", "Australia", "MULTIPOLYGON(((145 -38, 154 -38, 154 -28, 145 -28, 145 -38)))"),
]

UTC = datetime.timezone.utc


def square(lon: float, lat: float, side: float = 0.02) -> list:
    """A small axis-aligned square as GeoJSON Polygon coordinates."""
    return [[[lon, lat], [lon + side, lat], [lon + side, lat + side],
             [lon, lat + side], [lon, lat]]]


def attributes(fire_id: int, lon: float, lat: float, start: str, end: str | None,
               **overrides) -> dict:
    """One feature's attributes, named exactly as the published files name them."""
    values = {
        "fire_ID": fire_id, "lat": lat, "lon": lon,
        "size": 3.64, "perimeter": 12.96,
        "start_date": start, "end_date": end,
        "duration": 2, "fire_line": 1.39, "spread": 0.64, "speed": 1.41,
        "direction": "east", "direc_frac": 0.33,
        "MODIS_tile": "h18v08", "landcover": "Savannas", "landc_frac": 1.0,
        "GFED_regio": 8,
    }
    values.update(overrides)
    return values


#: Ten features, nine fires. Every one is placed deliberately:
#:
#: * 20000001 Spain / Europe/Madrid, the ordinary case.
#: * 20000002 and 20000003 both in California, one in July and one in January, so
#:   that a fixed offset instead of a per-date one would be caught.
#: * 20000004 is *two* features sharing an id — the multipart case, which must
#:   come back as one fire with a two-part perimeter.
#: * 20000005 is a self-intersecting bowtie, invalid as published.
#: * 20000006 is in the middle of the Atlantic: no country, no zone.
#: * 20000007 carries the sentinels the later files are full of.
#: * 20000008 sits in the Canary hole inside the Spanish box, so its zone and its
#:   country come from different polygons.
#: * 20000009 has no end date.
FEATURES = [
    (attributes(20000001, -3.70, 40.40, "2002-06-25", "2002-06-26"), square(-3.70, 40.40)),
    (attributes(20000002, -122.00, 38.00, "2002-07-29", "2002-07-30"), square(-122.00, 38.00)),
    (attributes(20000003, -122.00, 39.00, "2002-01-15", "2002-01-16"), square(-122.00, 39.00)),
    (attributes(20000004, -5.00, 39.00, "2002-08-01", "2002-08-03"), square(-5.00, 39.00)),
    (attributes(20000004, -5.00, 39.00, "2002-08-01", "2002-08-03"), square(-4.50, 39.00)),
    (attributes(20000005, 5.00, 45.00, "2002-09-10", "2002-09-11"),
     [[[5.0, 45.0], [5.02, 45.02], [5.02, 45.0], [5.0, 45.02], [5.0, 45.0]]]),
    (attributes(20000006, -30.00, 20.00, "2002-10-01", "2002-10-02"), square(-30.00, 20.00)),
    (attributes(20000007, 150.00, -33.00, "2002-11-05", "2002-11-06",
                direction="none", direc_frac=0.0,
                landcover="Unclassified", landc_frac=1.0, GFED_regio=0), square(150.00, -33.00)),
    (attributes(20000008, 0.50, 43.50, "2002-12-01", "2002-12-02"), square(0.50, 43.50)),
    (attributes(20000009, -2.00, 41.00, "2002-05-05", None), square(-2.00, 41.00)),
]

FIRE_IDS = {values["fire_ID"] for values, _ in FEATURES}

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-gfa-import")


def instant(text_value: str) -> datetime.datetime:
    """Parse an ISO instant into an aware UTC datetime, for comparing against the model."""
    return datetime.datetime.fromisoformat(text_value).astimezone(UTC)


def write_shapefile(directory: Path, year: int, features: list) -> Path:
    """Build one year's shapefile from ``features``, named as the Atlas names them."""
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": values,
             "geometry": {"type": "Polygon", "coordinates": coordinates}}
            for values, coordinates in features
        ],
    }
    source = directory / f"source_{year}.geojson"
    source.write_text(json.dumps(collection))

    target = directory / f"GFA_v20260408_perimeters_{year}.shp"
    # DATE_AS_STRING, because the published files hold the dates as String(50) and
    # the importer casts them itself. Without it GDAL recognises "2002-06-25" and
    # writes a Date field, which is not what the mapping is written against.
    subprocess.run(["ogr2ogr", "-f", "ESRI Shapefile", str(target), str(source),
                    "-oo", "DATE_AS_STRING=YES"],
                   check=True, capture_output=True)
    source.unlink()
    return target


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
def boundaries(database):
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
    time_zone_app.main(["-s", str(TIME_ZONE_ARCHIVE), *connection_arguments])


@pytest.fixture
def perimeters(tmp_path):
    """A directory holding one year's shapefile, as the download lays it out."""
    write_shapefile(tmp_path, 2002, FEATURES)
    return tmp_path


@pytest.fixture
def args(perimeters, connection_arguments):
    return app.parse_arguments(["--directory", str(perimeters), *connection_arguments])


@pytest.fixture
def imported(database, boundaries, time_zones, args):
    """The fixture year imported into a world that has both countries and zones."""
    engine, _ = database
    count = app.import_wildfires(args, engine, logger)
    return engine, count


def fire(session: Session, gfa_id: int) -> GfaWildfire:
    return session.scalar(select(GfaWildfire).where(GfaWildfire.gfa_id == gfa_id))


# --------------------------------------------------------------------------
# Arguments (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_a_directory_and_a_file_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", "dir", "-s", "one.shp"])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-s", "one.shp"])
    assert parsed.id_field == app.DEFAULT_ID_FIELD
    assert parsed.staging_table == app.DEFAULT_STAGING_TABLE
    assert parsed.keep_staging is False


def test_the_shapefiles_of_a_directory_are_found_in_order(tmp_path):
    """The Atlas ships loose .shp files, not archives, and the years must go in in order."""
    for year in (2004, 2002, 2003):
        (tmp_path / f"GFA_v20260408_perimeters_{year}.shp").touch()
    (tmp_path / "notes.txt").touch()

    found = app.find_shapefiles(app.parse_arguments(["-d", str(tmp_path)]))
    assert [path.name for path in found] == [
        "GFA_v20260408_perimeters_2002.shp",
        "GFA_v20260408_perimeters_2003.shp",
        "GFA_v20260408_perimeters_2004.shp",
    ]


def test_an_empty_directory_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="no .shp"):
        app.find_shapefiles(app.parse_arguments(["-d", str(tmp_path)]))


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent", "--db-name", "x", "--db-user", "y"]) == 1
    assert "Not found" in caplog.text


# --------------------------------------------------------------------------
# One fire per fire_ID
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_fire_is_imported_once(imported):
    """Ten features, nine fires: the multipart pair must not become two rows."""
    engine, count = imported
    assert count == len(FIRE_IDS) == 9

    with Session(engine) as session:
        assert {row.gfa_id for row in session.scalars(select(GfaWildfire))} == FIRE_IDS


@needs_ogr2ogr
def test_the_parts_of_a_multipart_fire_become_one_perimeter(imported):
    """The two features sharing 20000004 are two pieces of one burn, not two fires."""
    engine, _ = imported
    with Session(engine) as session:
        multipart = fire(session, 20000004)
        parts = session.scalar(select(func.ST_NumGeometries(Wildfire.perimeter))
                               .where(Wildfire.id == multipart.id))
        assert parts == 2
        # The attributes repeat across the parts, so the fire keeps them once.
        assert multipart.size_km2 == pytest.approx(3.64)


@needs_ogr2ogr
def test_the_joined_inheritance_rows_are_written_in_pairs(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 9
        assert session.scalar(select(func.count()).select_from(GfaWildfire)) == 9


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_an_invalid_perimeter_is_repaired(imported):
    """A bowtie is invalid as published; ST_MakeValid splits it into two triangles."""
    engine, _ = imported
    with Session(engine) as session:
        bowtie = fire(session, 20000005)
        valid, parts = session.execute(
            select(func.ST_IsValid(Wildfire.perimeter),
                   func.ST_NumGeometries(Wildfire.perimeter)).where(Wildfire.id == bowtie.id)
        ).one()
        assert valid is True
        assert parts == 2


@needs_ogr2ogr
def test_every_perimeter_is_a_valid_multipolygon_in_4326(imported):
    engine, _ = imported
    with Session(engine) as session:
        types = set(session.scalars(select(func.GeometryType(Wildfire.perimeter))).all())
        assert types == {"MULTIPOLYGON"}
        assert set(session.scalars(select(func.ST_SRID(Wildfire.perimeter)).select_from(Wildfire))) == {4326}
        assert all(session.scalars(select(func.ST_IsValid(Wildfire.perimeter))).all())


@needs_ogr2ogr
def test_the_ignition_point_is_built_from_lat_and_lon(imported):
    """lon then lat: swapping them would put every Spanish fire in the Indian Ocean."""
    engine, _ = imported
    with Session(engine) as session:
        spain = fire(session, 20000001)
        lon, lat = session.execute(
            select(func.ST_X(GfaWildfire.ignition_point), func.ST_Y(GfaWildfire.ignition_point))
            .where(GfaWildfire.id == spain.id)
        ).one()
        assert (lon, lat) == pytest.approx((-3.70, 40.40))


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_bare_date_becomes_local_midnight(imported):
    engine, _ = imported
    with Session(engine) as session:
        spain = fire(session, 20000001)
        assert spain.start_date_time == instant("2002-06-25T00:00:00+02:00")
        assert spain.time_zone == "Europe/Madrid"


@needs_ogr2ogr
def test_daylight_saving_is_resolved_from_each_date(imported):
    """Same zone, two dates: California is UTC-7 in July and UTC-8 in January."""
    engine, _ = imported
    with Session(engine) as session:
        summer = fire(session, 20000002)
        winter = fire(session, 20000003)
        assert summer.start_date_time == instant("2002-07-29T00:00:00-07:00")
        assert winter.start_date_time == instant("2002-01-15T00:00:00-08:00")
        assert summer.time_zone == winter.time_zone == "America/Los_Angeles"


@needs_ogr2ogr
def test_the_end_date_is_the_last_second_of_its_day(imported):
    engine, _ = imported
    with Session(engine) as session:
        spain = fire(session, 20000001)
        assert spain.end_date_time == instant("2002-06-26T23:59:59+02:00")


@needs_ogr2ogr
def test_a_fire_with_no_end_date_keeps_none(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, 20000009).end_date_time is None


@needs_ogr2ogr
def test_a_fire_outside_every_zone_falls_back_to_utc(imported):
    engine, _ = imported
    with Session(engine) as session:
        atlantic = fire(session, 20000006)
        assert atlantic.time_zone is None
        assert atlantic.start_date_time == instant("2002-10-01T00:00:00+00:00")


# --------------------------------------------------------------------------
# Country, from the ignition point
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_each_fire_gets_the_country_it_ignited_in(imported):
    engine, _ = imported
    with Session(engine) as session:
        for gfa_id, expected in [(20000001, "Spain"), (20000002, "United States"),
                                 (20000005, "France"), (20000007, "Australia")]:
            assert fire(session, gfa_id).admin_boundary.name == expected


@needs_ogr2ogr
def test_the_zone_and_the_country_are_resolved_independently(imported):
    """The Canary hole sits inside the Spanish box: different polygons, one point."""
    engine, _ = imported
    with Session(engine) as session:
        canary = fire(session, 20000008)
        assert canary.time_zone == "Atlantic/Canary"
        assert canary.admin_boundary.name == "Spain"


@needs_ogr2ogr
def test_a_fire_outside_every_country_gets_none(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, 20000006).admin_boundary_id is None


@needs_ogr2ogr
def test_fires_import_without_any_boundaries(database, time_zones, args, caplog):
    """The perimeters and the dates are worth having before the boundaries exist."""
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 9
    assert "no country" in caplog.text

    with Session(engine) as session:
        assert all(row.admin_boundary_id is None for row in session.scalars(select(Wildfire)))


# --------------------------------------------------------------------------
# The GFA attributes
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_measurements_are_stored_as_published(imported):
    engine, _ = imported
    with Session(engine) as session:
        spain = fire(session, 20000001)
        assert spain.size_km2 == pytest.approx(3.64)
        assert spain.perimeter_km == pytest.approx(12.96)
        assert spain.duration_days == 2
        assert spain.fire_line_km == pytest.approx(1.39)
        assert spain.spread_km2_day == pytest.approx(0.64)
        assert spain.speed_km_day == pytest.approx(1.41)
        assert spain.direction == "east"
        assert spain.direction_fraction == pytest.approx(0.33)
        assert spain.modis_tile == "h18v08"
        assert spain.landcover == "Savannas"
        assert spain.landcover_fraction == pytest.approx(1.0)
        assert spain.gfed_region == 8


@needs_ogr2ogr
def test_the_sentinels_of_the_later_files_are_kept_as_published(imported):
    """'none' and 'Unclassified' are the provider's own words and are not translated."""
    engine, _ = imported
    with Session(engine) as session:
        sentinel = fire(session, 20000007)
        assert sentinel.direction == "none"
        assert sentinel.direction_fraction == pytest.approx(0.0)
        assert sentinel.landcover == "Unclassified"
        assert sentinel.gfed_region == 0


# --------------------------------------------------------------------------
# Provider, re-running, staging
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_data_provider_is_created_on_first_import(imported):
    engine, _ = imported
    with Session(engine) as session:
        provider = session.scalar(select(DataProvider).where(DataProvider.name == "GFA"))
        assert provider.product == "Fire Atlas"
        assert provider.full_name == "Global Fire Atlas"
        assert all(row.data_provider_id == provider.id
                   for row in session.scalars(select(Wildfire)))


@needs_ogr2ogr
def test_re_importing_is_a_no_op(database, boundaries, time_zones, args, caplog):
    """fire_ID is a real key here, so a second run must add nothing at all."""
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 9
    # Reported at INFO, not as a warning: re-running is a normal thing to do here.
    with caplog.at_level(logging.INFO):
        assert app.import_wildfires(args, engine, logger) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GfaWildfire)) == 9
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 9
    assert "9 GFA fires already stored" in caplog.text


@needs_ogr2ogr
def test_a_second_year_adds_to_the_first(database, boundaries, time_zones,
                                         perimeters, connection_arguments):
    """The normal way to use it: a newly published year on top of the ones held."""
    engine, _ = database
    args = app.parse_arguments(["--directory", str(perimeters), *connection_arguments])
    assert app.import_wildfires(args, engine, logger) == 9

    next_year = [(attributes(30000001 + offset, -3.70, 40.40, "2003-06-25", "2003-06-26"),
                  square(-3.70 + offset, 40.40)) for offset in range(3)]
    write_shapefile(perimeters, 2003, next_year)

    assert app.import_wildfires(args, engine, logger) == 3
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GfaWildfire)) == 12


@needs_ogr2ogr
def test_the_staging_table_is_dropped(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.gfa_perimeters')")) is None


@needs_ogr2ogr
def test_the_staging_table_can_be_kept(database, boundaries, time_zones, args):
    args.keep_staging = True
    engine, _ = database
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.gfa_perimeters')")) is not None


@needs_ogr2ogr
def test_an_unmigrated_database_is_reported_before_the_staging_load(database, args):
    engine, _ = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE gfa_wildfire"))

    with pytest.raises(RuntimeError, match="make migrate"):
        app.import_wildfires(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database, boundaries, time_zones,
                                    perimeters, connection_arguments):
    """The single command a user actually types."""
    engine, _ = database
    assert app.main(["-d", str(perimeters), *connection_arguments]) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(GfaWildfire)) == 9


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, perimeters,
                                                     connection_arguments, caplog):
    engine, _ = database
    exit_code = app.main(["-d", str(perimeters), "--id-field", "no_such_field",
                          *connection_arguments])
    assert exit_code == 1
    assert "Import failed" in caplog.text
