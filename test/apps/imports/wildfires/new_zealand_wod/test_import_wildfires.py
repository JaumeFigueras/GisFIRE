#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the WOD import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and two real shapefiles, so the whole path is exercised — the two loads into one
staging table, the column conversions, the checks and the SQL mapping.

The fixture release is built the way the WOD publishes:

* two layers, ``WOD_points`` and ``WOD_polygons``, in NZTM2000, carrying all 109
  published attributes;
* ``-9999`` for no value everywhere, ``NA:NA`` for no time, ``Null`` for no cause;
* ``WS``, ``FDC*``, ``HFI*`` and ``ROS*`` published as **text**;
* every problem the import corrects: ``WOD1e+05``, a negative area, an invalid
  polygon, a point on the sea placeholder, a Chatham Islands record, a DOC record
  without a time, report times in a daylight-saving gap and overlap.
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

from src.apps.imports.wildfires.new_zealand_wod import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import new_zealand_wod
from src.providers import ocha
from src.providers.new_zealand_wod.ignition import WodIgnition
from src.providers.new_zealand_wod.terrain import WodTerrain
from src.providers.new_zealand_wod.weather import WodWeather
from src.providers.new_zealand_wod.wildfire import WodWildfire

UTC = datetime.timezone.utc

#: Mainland New Zealand in EPSG:4326, as a polygon's rings, east of North Cape stopping short of the
#: placeholder coordinate (178.97°E), which must fall in no zone.
MAINLAND = "((166 -48, 178.6 -48, 178.6 -34, 166 -34, 166 -48))"

#: The Chatham Islands, across the antimeridian from the mainland.
CHATHAM = "((-177.5 -45, -175.5 -45, -175.5 -43, -177.5 -43, -177.5 -45))"

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-wod-import")

#: The published attributes, in published order, with the type the WOD gives each.
TEXT = ["ID", "Source", "OrgID", "Time", "Hour", "Minute", "Season", "FY", "AreaCat",
        "OrgVeg", "IgnSource", "FENZDist", "OrgIDDrop", "AspectCar", "AspectCar2",
        "AspectCar3", "LandCvr", "LandCvr2", "LandCvr3", "FuelType", "Landform",
        "Landform2", "Landform3", "ClimZnName", "WxName", "WxID", "FuelClass", "WS",
        "FDCNoon", "FDC", "FDC8B", "FDC8A", "HFINoon", "HFI", "HFI8B", "HFI8A",
        "ROSNoon", "ROS", "ROS8B", "ROS8A", "ENSO"]
INTEGER = ["Day", "Month", "Year"]
FIELDS = [
    "ID", "Source", "OrgID", "X", "Y", "Lat", "Lon", "Day", "Month", "Year", "Time",
    "Hour", "Minute", "Season", "StartFY", "EndFY", "FY", "AreaHa", "AreaCat", "OrgVeg",
    "IgnSource", "FENZDist", "OrgIDDrop", "Elev", "MinElev", "MaxElev", "Slope",
    "MinSlope", "MaxSlope", "AspectDeg", "AspectCar", "AspectCar2", "AspectCar3",
    "LandCvr", "LandCvr2", "LandCvr3", "FuelType", "Landform", "Landform2", "Landform3",
    "ClimZnName", "WxName", "WxID", "WxDist", "FuelClass", "Temp", "TempNoon",
    "TempMax8B", "TempMin8B", "TempAvg8B", "TempMax8A", "TempMin8A", "TempAvg8A", "RH",
    "RHNoon", "RHMax8B", "RHMin8B", "RHAvg8B", "RHMax8A", "RHMin8A", "RHAvg8A", "WS",
    "WSNoon", "WSMax8B", "WSMin8B", "WSAvg8B", "WSMax8A", "WSMin8A", "WSAvg8A", "WD",
    "SoilMoist", "SoilTemp", "FFMCNoon", "FFMC", "FFMC8B", "FFMC8A", "ISINoon", "ISI",
    "ISI8B", "ISI8A", "FWINoon", "FWI", "FWI8B", "FWI8A", "FDCNoon", "FDC", "FDC8B",
    "FDC8A", "HFINoon", "HFI", "HFI8B", "HFI8A", "ROSNoon", "ROS", "ROS8B", "ROS8A",
    "DMCNoon", "DCNoon", "BUINoon", "DSRNoon", "PrecipNoon", "Precip24hr", "Precip48hr",
    "Precip72hr", "NoRain1", "NoRain2", "NoRain3", "SOI", "ENSO",
]

SEASONS = {1: "Summer", 2: "Summer", 3: "Autumn", 4: "Autumn", 5: "Autumn", 6: "Winter",
           7: "Winter", 8: "Winter", 9: "Spring", 10: "Spring", 11: "Spring",
           12: "Summer"}


def record(wod_id: str, x: float, y: float, date: str, time: str = "14:10", *,
           source="FENZ", cause="Matches", area=0.5, district="Canterbury",
           **published) -> dict:
    """One published record, every attribute present and ``-9999`` where unset."""
    year, month, day = (int(part) for part in date.split("-"))
    values = {name: ("-9999" if name in TEXT else -9999 if name in INTEGER else -9999.0)
              for name in FIELDS}
    start_fy = year if month >= 7 else year - 1
    values.update({
        "ID": wod_id, "Source": source, "OrgID": f"F{wod_id[3:]}", "X": x, "Y": y,
        "Lat": -40.0, "Lon": 174.0, "Day": day, "Month": month, "Year": year,
        "Time": time, "Season": SEASONS[month], "StartFY": float(start_fy),
        "EndFY": float(start_fy + 1), "FY": f"{start_fy}/{start_fy + 1}",
        "AreaHa": float(area), "AreaCat": "< 1" if 0 <= area < 1 else "1 to 5",
        "IgnSource": cause, "FENZDist": district, "SOI": 5.3, "ENSO": "La Nina",
    })
    values.update(published)
    return values


#: A square perimeter near Christchurch, in NZTM2000 metres, and its published point
#: 300 m outside it — the X/Y a polygon record carries is not its centroid.
SQUARE = [[[1570000, 5180000], [1570500, 5180000], [1570500, 5180500],
           [1570000, 5180500], [1570000, 5180000]]]

#: A self-intersecting bow tie: invalid, and two triangles once made valid.
BOW_TIE = [[[1580000, 5190000], [1580400, 5190400], [1580400, 5190000],
            [1580000, 5190400], [1580000, 5190000]]]

POINTS = [
    # WOD1 itself: Auckland, 23:35 NZST, a published area of 0.
    record("WOD1", 1743575, 5922720, "1998-07-30", "23:35", cause="Matches", area=0.0,
           district="Auckland", Elev=80.95, AspectCar="Northeast",
           LandCvr="Built-up Area (settlement)", FuelType="Non-Fuel",
           FuelClass="Non Fuel", WxName="Cornwallis Depot Raws", WxID="42910435",
           WxDist=18.92, TempNoon=16.0, RHNoon=60.0, WS="5.59", FDCNoon="1",
           FDC8B="-9999.0", HFINoon="620", ROSNoon="24.9"),
    # Lightning, FENZ's spelling.
    record("WOD2", 1571000, 5181000, "2020-01-15", cause="Lightning discharge",
           area=2.5),
    # DOC: no time, its own misspelling of lightning, and a dropped FENZ record.
    record("WOD3", 1572000, 5182000, "2005-02-06", "NA:NA", source="DOC",
           cause="Lightening Strike", OrgIDDrop="F0001", OrgVeg="Gorse."),
    # The identifier the export wrote in scientific notation.
    record("WOD1e+05", 1573000, 5183000, "2020-03-01", cause="Debris burning"),
    # On the placeholder coordinate, in the sea: no district, no zone, no country.
    record("WOD7", 2147484, 6147484, "2016-11-20", district="-9999"),
    # The Chatham Islands, 45 minutes ahead of the mainland.
    record("WOD8", 2440933, 5092729, "2016-12-01", "10:00", district="Chatham Islands"),
    # The one negative area.
    record("WOD9", 1574000, 5184000, "2016-01-10", area=-0.0001),
    # Before the default year cut.
    record("WOD10", 1575000, 5185000, "1960-01-10", "NA:NA", source="DOC",
           cause="Unknown"),
    # No cause, as DOC writes it.
    record("WOD11", 1576000, 5186000, "2005-03-01", "NA:NA", source="DOC", cause="Null"),
    # A trailing space in a FENZ cause.
    record("WOD12", 1577000, 5187000, "2016-02-01", cause="Electrical Fence "),
    # 02:30 on the night the clocks went forward: a time that does not exist.
    record("WOD13", 1578000, 5188000, "2020-09-27", "02:30"),
    # 02:30 on the night the clocks went back: a time that exists twice.
    record("WOD14", 1579000, 5189000, "2020-04-05", "02:30"),
]

POLYGONS = [
    (record("WOD4", 1570800, 5180250, "2005-02-10", "NA:NA", source="DOC", area=25.0,
            cause="Burn Breakaway - authorised", Elev=120.0, MinElev=100.0,
            MaxElev=140.0, LandCvr="Gorse and/or Broom", LandCvr2="Exotic Forest"),
     SQUARE),
    (record("WOD5", 1580200, 5190500, "2020-02-10", area=8.0), BOW_TIE),
]


def write_layer(directory: Path, layer: str, features: list[dict]) -> None:
    """Write one published layer, the way the WOD does."""
    collection = {"type": "FeatureCollection", "features": features}
    source = directory / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")
    subprocess.run(
        ["ogr2ogr", "-f", "ESRI Shapefile", str(directory / f"{layer}.shp"), str(source),
         "-a_srs", "EPSG:2193", "-nln", layer, "-lco", "ENCODING=UTF-8"],
        check=True, capture_output=True,
    )
    source.unlink()


def write_release(directory: Path, points=None, polygons=None) -> Path:
    """Build a WOD_shp_* folder holding both layers."""
    directory.mkdir(parents=True, exist_ok=True)
    write_layer(directory, "WOD_points", [
        {"type": "Feature", "properties": values,
         "geometry": {"type": "Point", "coordinates": [values["X"], values["Y"]]}}
        for values in (POINTS if points is None else points)
    ])
    write_layer(directory, "WOD_polygons", [
        {"type": "Feature", "properties": values,
         "geometry": {"type": "Polygon", "coordinates": rings}}
        for values, rings in (POLYGONS if polygons is None else polygons)
    ])
    return directory


@pytest.fixture
def release(tmp_path) -> Path:
    return write_release(tmp_path / "WOD_shp_1931-2025")


@pytest.fixture
def database(postgresql):
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
def with_boundaries(database):
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(
            data_provider=provider, source_id="NZL", name="New Zealand",
            name_en="New Zealand", level=0,
            geometry=f"SRID=4326;MULTIPOLYGON({MAINLAND},{CHATHAM})"))
        session.add(TimeZone(name="Pacific/Auckland",
                             geometry=f"SRID=4326;MULTIPOLYGON({MAINLAND})"))
        session.add(TimeZone(name="Pacific/Chatham",
                             geometry=f"SRID=4326;MULTIPOLYGON({CHATHAM})"))
        session.commit()
    return database


def argv_for(url: str, path: Path, extra: list[str] | None = None) -> list[str]:
    """The command line reaching the ephemeral database the fixtures built."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", str(path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return argv + (extra or [])


def run(url: str, path: Path, extra: list[str] | None = None) -> int:
    return app.main(argv_for(url, path, extra))


def audit_of(engine, url: str, path: Path, extra: list[str] | None = None) -> app.Audit:
    """Run the import and return its audit rather than an exit code."""
    return app.import_wildfires(app.parse_arguments(argv_for(url, path, extra)), engine,
                                logger)


def fires(engine) -> dict[str, WodWildfire]:
    with Session(engine, expire_on_commit=False) as session:
        return {fire.wod_id: fire for fire in session.scalars(select(WodWildfire)).all()}


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


def scalar(engine, statement):
    with Session(engine) as session:
        return session.scalar(statement)


# --------------------------------------------------------------------------
# A record, four rows
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_record_in_scope_becomes_four_rows(release, with_boundaries):
    engine, url = with_boundaries
    assert run(url, release) == 0

    # 14 published, one before 1998.
    for table in ("wod_wildfire", "wildfire", "wod_ignition", "ignition", "wod_terrain",
                  "wod_weather"):
        assert count(engine, table) == 13, table


@needs_ogr2ogr
def test_a_record_round_trips(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    fire = fires(engine)["WOD1"]
    assert (fire.source, fire.org_id, fire.year) == ("FENZ", "F1", 1998)
    assert fire.report_date == datetime.date(1998, 7, 30)
    assert fire.report_time == datetime.time(23, 35)
    assert (fire.season, fire.financial_year) == ("Winter", 1998)
    assert (fire.area_ha, fire.area_category) == (0.0, "< 1")
    assert (fire.ignition_source, fire.fire_cause) == ("Matches", "human")
    assert fire.fenz_district == "Auckland"


@needs_ogr2ogr
def test_the_report_time_is_local_and_stored_as_an_instant(release, with_boundaries):
    """23:35 NZST on 30 July 1998 is 11:35 UTC."""
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        fire = session.scalar(select(WodWildfire).where(WodWildfire.wod_id == "WOD1"))
        assert fire.start_date_time == datetime.datetime(1998, 7, 30, 11, 35, tzinfo=UTC)
        assert fire.time_zone == "Pacific/Auckland"
        assert fire.end_date_time is None
        assert fire.ignition.date_time == fire.start_date_time


@needs_ogr2ogr
def test_a_doc_record_without_a_time_starts_at_local_midnight(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    local = scalar(engine, select(func.timezone(WodWildfire.time_zone,
                                                WodWildfire.start_date_time))
                   .where(WodWildfire.wod_id == "WOD3"))
    assert fires(engine)["WOD3"].report_time is None
    assert local == datetime.datetime(2005, 2, 6, 0, 0)


@needs_ogr2ogr
def test_the_point_is_the_published_x_y_in_both_crss(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        x, y, srid, srid_4326 = session.execute(
            select(func.ST_X(WodIgnition.geometry_nztm), func.ST_Y(WodIgnition.geometry_nztm),
                   func.ST_SRID(WodIgnition.geometry_nztm), func.ST_SRID(Ignition.geometry))
            .where(WodIgnition.wod_id == "WOD1")).one()
    assert (x, y, srid, srid_4326) == (1743575.0, 5922720.0, 2193, 4326)


@needs_ogr2ogr
def test_a_polygon_record_keeps_its_point_and_its_perimeter(release, with_boundaries):
    """The point is the published X/Y, outside the square, not its centroid."""
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        fire = session.scalar(select(WodWildfire).where(WodWildfire.wod_id == "WOD4"))
        x = session.scalar(select(func.ST_X(WodIgnition.geometry_nztm))
                           .where(WodIgnition.id == fire.ignition_id))
        area = session.scalar(select(func.ST_Area(WodWildfire.perimeter_nztm))
                              .where(WodWildfire.id == fire.id))
        srid = session.scalar(select(func.ST_SRID(Wildfire.perimeter))
                              .where(Wildfire.id == fire.id))
    assert x == 1570800.0
    assert area == pytest.approx(500 * 500)
    assert srid == 4326


@needs_ogr2ogr
def test_a_point_record_has_no_perimeter(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    assert fires(engine)["WOD1"].perimeter_nztm is None


# --------------------------------------------------------------------------
# What is corrected
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_scientific_identifier_is_repaired(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    assert "WOD100000" in fires(engine)
    assert "WOD1e+05" not in fires(engine)
    assert audit.ids_repaired == 1


@needs_ogr2ogr
def test_the_negative_area_is_stored_as_zero(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    assert fires(engine)["WOD9"].area_ha == 0.0
    assert audit.areas_clamped == 1


@needs_ogr2ogr
def test_an_invalid_perimeter_is_made_valid(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    with Session(engine) as session:
        valid, parts = session.execute(
            select(func.ST_IsValid(WodWildfire.perimeter_nztm),
                   func.ST_NumGeometries(WodWildfire.perimeter_nztm))
            .where(WodWildfire.wod_id == "WOD5")).one()
    assert valid and parts == 2
    assert audit.perimeters_repaired == 1
    assert audit.with_polygon == 2


@needs_ogr2ogr
def test_the_placeholder_point_in_the_sea_is_kept_as_published(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    with Session(engine) as session:
        fire = session.scalar(select(WodWildfire).where(WodWildfire.wod_id == "WOD7"))
        x, y = session.execute(select(func.ST_X(WodIgnition.geometry_nztm),
                                      func.ST_Y(WodIgnition.geometry_nztm))
                               .where(WodIgnition.id == fire.ignition_id)).one()
        assert (x, y) == (new_zealand_wod.PLACEHOLDER_X, new_zealand_wod.PLACEHOLDER_Y)
        assert fire.fenz_district is None
        assert fire.admin_boundary_id is None
        assert fire.time_zone == "Pacific/Auckland", "the mainland zone is the fallback"
    assert (audit.without_district, audit.placeholder_points) == (1, 1)
    assert audit.zone_fallbacks == 1


@needs_ogr2ogr
def test_a_chatham_record_is_dated_in_the_chatham_zone(release, with_boundaries):
    """10:00 CHADT (+13:45) on 1 December 2016 is 20:15 UTC the day before."""
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    with Session(engine) as session:
        fire = session.scalar(select(WodWildfire).where(WodWildfire.wod_id == "WOD8"))
        assert fire.time_zone == "Pacific/Chatham"
        assert fire.start_date_time == datetime.datetime(2016, 11, 30, 20, 15, tzinfo=UTC)
    assert audit.chatham == 1


@needs_ogr2ogr
def test_a_chatham_record_in_no_zone_still_gets_the_chatham_zone(release, database):
    """No time zone areas at all: the district decides."""
    engine, url = database
    run(url, release)

    with Session(engine) as session:
        zones = dict(session.execute(select(WodWildfire.wod_id,
                                            WodWildfire.time_zone)).all())
    assert zones["WOD8"] == "Pacific/Chatham"
    assert zones["WOD1"] == "Pacific/Auckland"


@needs_ogr2ogr
def test_daylight_saving_gaps_and_overlaps_are_counted(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    assert audit.dst_gaps == 1
    assert audit.dst_overlaps == 1


# --------------------------------------------------------------------------
# Causes
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_causes_are_stored_as_published_and_classified(release, with_boundaries):
    engine, url = with_boundaries
    audit = audit_of(engine, url, release)

    stored = fires(engine)
    assert (stored["WOD2"].ignition_source, stored["WOD2"].fire_cause) == (
        "Lightning discharge", "lightning")
    assert (stored["WOD3"].ignition_source, stored["WOD3"].fire_cause) == (
        "Lightening Strike", "lightning")
    assert (stored["WOD11"].ignition_source, stored["WOD11"].fire_cause) == (None, "unknown")
    assert (stored["WOD12"].ignition_source, stored["WOD12"].fire_cause) == (
        "Electrical Fence", "human")
    assert stored["WOD4"].fire_cause == "human"
    assert (audit.lightning, audit.natural, audit.unknown) == (2, 0, 1)
    assert audit.lightning + audit.natural + audit.human + audit.unknown == audit.written


@needs_ogr2ogr
def test_an_unmapped_cause_stops_the_run_before_anything_is_written(tmp_path,
                                                                    with_boundaries):
    engine, url = with_boundaries
    release = write_release(tmp_path / "new", points=POINTS + [
        record("WOD20", 1571000, 5181000, "2021-01-01", cause="Volcanic eruption")])

    with pytest.raises(RuntimeError, match="Volcanic eruption"):
        audit_of(engine, url, release)
    assert count(engine, "wod_wildfire") == 0


# --------------------------------------------------------------------------
# Terrain and weather
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_terrain_and_weather_are_stored_with_no_value_as_null(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        fire = session.scalar(select(WodWildfire).where(WodWildfire.wod_id == "WOD1"))
        terrain, weather = fire.terrain, fire.weather
        assert terrain.elev == pytest.approx(80.95)
        assert terrain.min_elev is None
        assert terrain.land_cvr == "Built-up Area (settlement)"
        assert terrain.land_cvr_2 is None
        assert weather.wx_id == "42910435"
        assert weather.temp is None
        assert weather.temp_noon == 16.0
        assert (weather.soi, weather.enso) == (5.3, "La Nina")


@needs_ogr2ogr
def test_numbers_published_as_text_are_numbers(release, with_boundaries):
    """WS, FDC*, HFI* and ROS* are text in the DBF; '-9999.0' is no value too."""
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        weather = session.scalar(select(WodWeather).join(WodWildfire)
                                 .where(WodWildfire.wod_id == "WOD1"))
        assert weather.ws == pytest.approx(5.59)
        assert weather.fdc_noon == 1
        assert weather.fdc_8b is None
        assert weather.hfi_noon == 620.0
        assert weather.ros_noon == pytest.approx(24.9)


@needs_ogr2ogr
def test_a_polygon_record_keeps_its_second_land_cover(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        terrain = session.scalar(select(WodTerrain).join(WodWildfire)
                                 .where(WodWildfire.wod_id == "WOD4"))
        assert (terrain.min_elev, terrain.max_elev) == (100.0, 140.0)
        assert (terrain.land_cvr, terrain.land_cvr_2) == ("Gorse and/or Broom",
                                                          "Exotic Forest")


# --------------------------------------------------------------------------
# The year cut
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_records_before_1998_are_left_out_by_default(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    assert "WOD10" not in fires(engine)


@needs_ogr2ogr
def test_all_years_imports_the_whole_release(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release, extra=["--all-years"])

    assert "WOD10" in fires(engine)
    assert count(engine, "wod_wildfire") == 14


def test_all_years_starts_where_the_archive_does():
    arguments = app.parse_arguments(["-s", "x", "--all-years"])
    assert arguments.from_year == new_zealand_wod.PUBLISHED_FIRST_YEAR == 1931


def test_the_year_cut_defaults_to_the_fenz_records():
    assert app.parse_arguments(["-s", "x"]).from_year == new_zealand_wod.FIRST_YEAR == 1998


def test_all_years_and_a_from_year_are_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-s", "x", "--all-years", "--from-year", "2000"])


# --------------------------------------------------------------------------
# Replacing years
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_replaces_the_years(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)
    assert run(url, release) == 0

    for table in ("wod_wildfire", "wildfire", "wod_ignition", "ignition", "wod_terrain",
                  "wod_weather"):
        assert count(engine, table) == 13, table


@needs_ogr2ogr
def test_only_the_year_asked_for_is_replaced(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)
    before = {fire.wod_id: fire.id for fire in fires(engine).values() if fire.year != 2020}

    run(url, release, extra=["--year", "2020"])
    after = {fire.wod_id: fire.id for fire in fires(engine).values() if fire.year != 2020}
    assert before == after
    assert count(engine, "wod_wildfire") == 13


@needs_ogr2ogr
def test_a_record_moved_to_another_year_replaces_its_old_copy(tmp_path, with_boundaries):
    """The identifier is unique, so the old copy must go wherever it is."""
    engine, url = with_boundaries
    run(url, write_release(tmp_path / "old"))

    moved = [record("WOD2", 1571000, 5181000, "2016-01-15", cause="Lightning discharge")
             if values["ID"] == "WOD2" else values for values in POINTS]
    assert run(url, write_release(tmp_path / "new", points=moved),
               extra=["--year", "2016"]) == 0

    assert fires(engine)["WOD2"].year == 2016
    assert count(engine, "wod_wildfire") == 13


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(release, with_boundaries):
    engine, url = with_boundaries
    assert run(url, release, extra=["--dry-run"]) == 0

    assert count(engine, "wod_wildfire") == 0
    assert count(engine, "ignition") == 0


@needs_ogr2ogr
def test_the_provider_carries_the_paper_and_the_licence(release, with_boundaries):
    engine, url = with_boundaries
    run(url, release)

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider).where(
            DataProvider.product == new_zealand_wod.PROVIDER_PRODUCT))
        assert provider.url == new_zealand_wod.PROVIDER_URL
        assert "CC BY 4.0" in provider.description


@needs_ogr2ogr
def test_a_second_run_is_refused_while_one_holds_the_staging_table(release,
                                                                  with_boundaries):
    engine, url = with_boundaries
    args = app.parse_arguments(argv_for(url, release))
    staging = f"{args.staging_schema}.{args.staging_table}"
    log = logging.LoggerAdapter(logger, {"archive": release.name})

    with app.exclusive_run(engine, staging, log):
        assert run(url, release) == 1
        assert count(engine, "wod_wildfire") == 0


def test_a_year_that_lost_its_staged_rows_is_not_committed():
    with pytest.raises(RuntimeError, match="changed while this run was reading it"):
        app.assert_year_survived(2016, app.Audit(in_scope=0), "staging.wod_records")
    app.assert_year_survived(2016, app.Audit(in_scope=1), "staging.wod_records")


def test_the_audits_of_the_years_add_up():
    first = app.Audit(in_scope=3, written=3, lightning=1, human=2)
    second = app.Audit(in_scope=2, written=2, unknown=2, ids_repaired=1)

    total = first + second
    assert (total.in_scope, total.written, total.lightning, total.unknown) == (5, 5, 1, 2)
    assert total.ids_repaired == 1
    assert app.Audit() + first == first


# --------------------------------------------------------------------------
# Releases the import refuses
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_release_missing_a_layer_is_refused(tmp_path, with_boundaries):
    _, url = with_boundaries
    release = write_release(tmp_path / "half")
    for path in release.glob("WOD_polygons.*"):
        path.unlink()

    assert run(url, release) == 1


@needs_ogr2ogr
@pytest.mark.parametrize("bad, message", [
    (record("WOD2", 1571000, 5181000, "2021-01-01"), "shared by two records"),
    (record("WOD30", 1571000, 5181000, "2021-01-01", Season="Wet"), "season"),
    (record("WOD31", 1571000, 5181000, "2021-01-01", time="25:00"), "HH:MM"),
    (record("WOD32", 1571000, 5181000, "2021-01-01", FDCNoon="7"), "fdcnoon"),
    (record("XYZ", 1571000, 5181000, "2021-01-01"), "not WOD identifiers"),
])
def test_a_release_the_model_cannot_hold_is_refused_whole(tmp_path, with_boundaries,
                                                          bad, message):
    engine, url = with_boundaries
    release = write_release(tmp_path / "bad", points=POINTS + [bad])

    with pytest.raises(RuntimeError, match=message):
        audit_of(engine, url, release)
    assert count(engine, "wod_wildfire") == 0


def test_the_published_integer64_date_parts_are_converted():
    """Day, Month and Year are Integer64 in the DBF, bigint once staged."""
    assert "bigint" not in app.COMPATIBLE_TYPES["integer"]
    assert {app.STAGING_COLUMNS[name] for name in ("day", "month", "year")} == {"integer"}


def test_every_side_table_column_is_staged():
    """The staged names are the model's without underscores: TempMax8B, temp_max_8b."""
    staged = set(app.STAGING_COLUMNS)
    for column in app.TERRAIN_COLUMNS + app.WEATHER_COLUMNS:
        assert app.staged_name(column.name) in staged
    assert app.staged_name("temp_max_8b") == "tempmax8b"
    assert app.staged_name("land_cvr_2") == "landcvr2"
    assert len(app.STAGING_COLUMNS) == 17 + 18 + 68
