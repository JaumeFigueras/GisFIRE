#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the NBAC perimeter import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and real shapefiles, so the whole path is exercised — the subprocess, the ``.prj``,
the reprojection, the staging table and the SQL mapping. A mocked ``ogr2ogr`` would
test none of the things that actually go wrong with this dataset.

The fixture layers are built from GeoJSON rather than checked in as binaries, and
they are built the way the service publishes them:

* coordinates in NAD83 / Canada Atlas Lambert metres;
* a ``.prj`` holding **the published ESRI string**, which carries no EPSG code at
  all — the one thing unique to this source, and the reason the import asserts 3978
  rather than reading it. A fixture that wrote a tidy ``EPSG:3978`` ``.prj`` would
  test a different program;
* ``YEAR`` and ``NFIREID`` as **Real** fields, which is what the published archives
  have and what makes ``make_date`` fail if the staged type is taken at face value;
* the four date fields as real DBF dates, and some of them empty.

Two layers, chosen for what each carries: 1980 holds the fire cut across a provincial
boundary, the fire with no date at all and an invalid ring; 2023 holds an ordinary
recent year, a fire dated only from a hotspot, and a prescribed burn.
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

from src.apps.imports.wildfires.canada_nbac import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import canada_nbac
from src.providers import ocha
from src.providers.canada_nbac.wildfire import NbacWildfire

UTC = datetime.timezone.utc

#: Canada, near enough for a fixture: it contains every fire below except the one in
#: the Pacific, which is the point of that one.
CANADA = "MULTIPOLYGON(((-141 41, -52 41, -52 84, -141 84, -141 41)))"

#: The published ``.prj``, verbatim from ``NBAC_2020_20260513.prj``.
#:
#: An ESRI dialect naming ``Canada_Lambert_Conformal_Conic`` with **no authority
#: code**. Its parameters are EPSG:3978's exactly, and GDAL can read them but cannot
#: name them — which is the trap this import steps around, and therefore the thing the
#: fixture has to reproduce.
PUBLISHED_PRJ = (
    'PROJCS["Canada_Lambert_Conformal_Conic",GEOGCS["GCS_North_American_1983",'
    'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",0.0],'
    'PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-95.0],'
    'PARAMETER["Standard_Parallel_1",49.0],PARAMETER["Standard_Parallel_2",77.0],'
    'PARAMETER["Latitude_Of_Origin",49.0],UNIT["Meter",1.0]]'
)

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-nbac-import")


def square(x: float, y: float, side: float = 1000.0) -> list:
    """A square in EPSG:3978 metres, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def feature(gid, nfireid, year, geometry, admin_name="AB", admin_div=None,
            cause="Natural", ag_sdate=None, ag_edate=None, hs_sdate=None,
            hs_edate=None, poly_ha=100.0, adj_ha=None, adj_flag=None,
            prescribed=None, basrc="MAFiMS", firemaps="Landsat",
            firemapm="Processed imagery", capdate=None, version="20260513") -> tuple:
    """One published feature, named exactly as the service names its fields."""
    values = {
        "YEAR": float(year), "NFIREID": float(nfireid), "GID": gid,
        "BASRC": basrc, "FIREMAPS": firemaps, "FIREMAPM": firemapm,
        "FIRECAUS": cause, "HS_SDATE": hs_sdate, "HS_EDATE": hs_edate,
        "AG_SDATE": ag_sdate, "AG_EDATE": ag_edate, "CAPDATE": capdate,
        "POLY_HA": poly_ha, "ADJ_HA": adj_ha if adj_ha is not None else poly_ha,
        "ADJ_FLAG": adj_flag, "ADMIN_NAME": admin_name, "ADMIN_DIV": admin_div,
        "PRESCRIBED": prescribed, "VERSION": version,
    }
    return values, geometry


#: 1980, the awkward year:
#:
#: * ``1980_1`` is an ordinary fire with an agency date.
#: * ``1980_189`` is **one fire in two provinces**, published as two polygons sharing
#:   a GID — 13 of 1980's 530 features are.
#: * ``1980_7`` publishes **no date at all**, as 102 of 1980's do.
#: * ``1980_9`` is a self-intersecting bowtie, invalid as published.
#: * ``1980_11`` is out in the Pacific: no country.
FEATURES_1980 = [
    feature("1980_1", 1, 1980, square(-1200000, 1500000), ag_sdate="1980-06-21",
            ag_edate="1980-07-30"),
    feature("1980_189", 189, 1980, square(-1000000, 1600000), admin_name="AB",
            ag_sdate="1980-05-03", poly_ha=300.0),
    feature("1980_189", 189, 1980, square(-999000, 1600000), admin_name="SK",
            ag_sdate="1980-05-05", ag_edate="1980-06-01", poly_ha=200.0),
    feature("1980_7", 7, 1980, square(-1100000, 1700000)),
    feature("1980_9", 9, 1980,
            [[[-900000.0, 1500000.0], [-899000.0, 1501000.0], [-899000.0, 1500000.0],
              [-900000.0, 1501000.0], [-900000.0, 1500000.0]]],
            ag_sdate="1980-08-01"),
    feature("1980_11", 11, 1980, square(-4000000, 1500000), ag_sdate="1980-08-02"),
]

#: 2023, an ordinary recent year: an agency-dated fire, one dated only from a
#: hotspot, a prescribed burn, and a fire in a national park.
FEATURES_2023 = [
    feature("2023_1", 1, 2023, square(-1200000, 1500000), ag_sdate="2023-05-03",
            ag_edate="2023-07-01", hs_sdate="2023-05-04", hs_edate="2023-06-12",
            poly_ha=12345.6, adj_ha=13000.0, adj_flag="true"),
    feature("2023_2", 2, 2023, square(-1150000, 1520000), hs_sdate="2023-06-10",
            hs_edate="2023-06-20"),
    feature("2023_3", 3, 2023, square(-1100000, 1540000), ag_sdate="2023-04-01",
            prescribed="true", cause="Human"),
    feature("2023_4", 4, 2023, square(-1050000, 1560000), ag_sdate="2023-07-11",
            admin_name="PC", admin_div="WB", cause="Undetermined"),
]

LAYERS = [("NBAC_1980_20260513", FEATURES_1980), ("NBAC_2023_20260513", FEATURES_2023)]


def write_layer(directory: Path, layer: str, features: list) -> Path:
    """Build one archive's shapefile, the way the service publishes it.

    ``-a_srs EPSG:3978`` *assigns* the CRS rather than reprojecting: the coordinates
    are already Lambert metres. The ``.prj`` GDAL writes is then **overwritten with
    the published ESRI string**, which is the whole point of the fixture.
    """
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": values,
             "geometry": {"type": "Polygon", "coordinates": coordinates}}
            for values, coordinates in features
        ],
    }
    source = directory / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")

    target = directory / f"{layer}.shp"
    subprocess.run(
        ["ogr2ogr", "-f", "ESRI Shapefile", str(target), str(source),
         "-a_srs", "EPSG:3978", "-nln", layer],
        check=True, capture_output=True,
    )
    (directory / f"{layer}.prj").write_text(PUBLISHED_PRJ, encoding="utf-8")
    source.unlink()
    return target


@pytest.fixture
def archives(tmp_path) -> Path:
    """A directory holding the two fixture archives."""
    directory = tmp_path / "nbac"
    directory.mkdir()
    for layer, features in LAYERS:
        write_layer(directory, layer, features)
    return directory


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
def with_boundaries(database):
    """The OCHA provider, a Canada-shaped boundary and a zone to resolve against."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="CAN",
                                  name="Canada", name_en="Canada", level=0,
                                  geometry=f"SRID=4326;{CANADA}"))
        session.add(TimeZone(name="America/Edmonton",
                             geometry=f"SRID=4326;{CANADA}"))
        session.commit()
    return database


def run(url: str, *paths: Path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", *[str(path) for path in paths],
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


def stored(engine, model=NbacWildfire):
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def by_gid(engine) -> dict:
    return {row.gid: row for row in stored(engine)}


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# The dissolve
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_cut_at_a_provincial_boundary_becomes_one_row(archives, with_boundaries):
    """Two published polygons sharing a GID are one fire, and the row says so."""
    engine, url = with_boundaries
    assert run(url, archives / "NBAC_1980_20260513.shp") == 0

    fires = by_gid(engine)
    fire = fires["1980_189"]
    assert fire.part_count == 2
    assert fire.crosses_admin is True
    assert fire.admin_name == "AB; SK"
    assert fire.area_ha_polygon == pytest.approx(500.0), "the two pieces' areas summed"


@needs_ogr2ogr
def test_a_single_polygon_fire_is_not_a_list(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    fire = by_gid(engine)["1980_1"]
    assert fire.part_count == 1
    assert fire.crosses_admin is False
    assert fire.admin_name == "AB"


@needs_ogr2ogr
def test_the_dissolved_geometry_covers_both_pieces(archives, with_boundaries):
    """The union, not one of the two — measured on the grid it was published on."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    with Session(engine) as session:
        area = session.scalar(
            select(func.ST_Area(NbacWildfire.perimeter_lambert))
            .where(NbacWildfire.gid == "1980_189"))
    assert area == pytest.approx(2_000_000.0), "two square kilometres, adjacent"


@needs_ogr2ogr
def test_the_dates_of_a_split_fire_are_the_widest(archives, with_boundaries):
    """The earliest agency start and the latest agency end, as NBAC itself does."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    fire = by_gid(engine)["1980_189"]
    assert fire.agency_start_date == datetime.date(1980, 5, 3)
    assert fire.agency_end_date == datetime.date(1980, 6, 1)


# --------------------------------------------------------------------------
# The dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_an_agency_date_is_preferred(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fire = by_gid(engine)["2023_1"]
    assert fire.date_source == canada_nbac.SOURCE_AGENCY
    assert fire.date_time_precision == canada_nbac.PRECISION_DAY
    assert fire.hotspot_start_date == datetime.date(2023, 5, 4), "and the other is kept"


@needs_ogr2ogr
def test_a_fire_with_no_agency_date_falls_back_to_the_hotspot(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fire = by_gid(engine)["2023_2"]
    assert fire.date_source == canada_nbac.SOURCE_HOTSPOT
    assert fire.date_time_precision == canada_nbac.PRECISION_DAY

    with Session(engine) as session:
        parent = session.get(Wildfire, fire.id)
        assert parent.start_date_time.date() == datetime.date(2023, 6, 10)


@needs_ogr2ogr
def test_a_fire_with_no_date_at_all_is_dated_to_its_year(archives, with_boundaries):
    """102 of 1980's fires. Imported, not dropped — and the precision says why."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    fire = by_gid(engine)["1980_7"]
    assert fire.date_source == canada_nbac.SOURCE_YEAR
    assert fire.date_time_precision == canada_nbac.PRECISION_YEAR

    with Session(engine) as session:
        parent = session.get(Wildfire, fire.id)
        assert parent.start_date_time.date() == datetime.date(1980, 1, 1)
        assert parent.end_date_time is None


@needs_ogr2ogr
def test_the_end_never_comes_from_a_hotspot(archives, with_boundaries):
    """A satellite losing sight of a fire is not an agency declaring it out."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fire = by_gid(engine)["2023_2"]
    assert fire.hotspot_end_date == datetime.date(2023, 6, 20)
    with Session(engine) as session:
        assert session.get(Wildfire, fire.id).end_date_time is None


# --------------------------------------------------------------------------
# The CRS
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_published_prj_names_no_epsg_and_the_geometry_lands_in_3978(archives,
                                                                       with_boundaries):
    """The whole reason the import asserts the CRS instead of reading it."""
    prj = (archives / "NBAC_1980_20260513.prj").read_text(encoding="utf-8")
    assert "AUTHORITY" not in prj.upper() and "3978" not in prj

    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    with Session(engine) as session:
        srids = session.execute(select(
            func.ST_SRID(NbacWildfire.perimeter_lambert),
            func.ST_SRID(NbacWildfire.perimeter),
        )).first()
    assert tuple(srids) == (3978, 4326)


@needs_ogr2ogr
def test_the_published_coordinates_are_not_moved(archives, with_boundaries):
    """``-t_srs EPSG:3978`` is a null transform for a file that is already 3978."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    with Session(engine) as session:
        x = session.scalar(
            select(func.ST_XMin(NbacWildfire.perimeter_lambert))
            .where(NbacWildfire.gid == "1980_1"))
    assert x == pytest.approx(-1200000.0)


# --------------------------------------------------------------------------
# Geometry, country and zone
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_an_invalid_ring_is_repaired_rather_than_dropped(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    assert "1980_9" in by_gid(engine)
    with Session(engine) as session:
        assert session.scalar(
            select(func.ST_IsValid(NbacWildfire.perimeter_lambert))
            .where(NbacWildfire.gid == "1980_9"))


@needs_ogr2ogr
def test_the_country_and_the_zone_are_resolved_from_the_perimeter(archives,
                                                                  with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    with Session(engine) as session:
        parent = session.scalar(
            select(Wildfire).join(NbacWildfire, NbacWildfire.id == Wildfire.id)
            .where(NbacWildfire.gid == "1980_1"))
        assert parent.admin_boundary is not None
        assert parent.admin_boundary.name_en == "Canada"
        assert parent.time_zone == "America/Edmonton"


@needs_ogr2ogr
def test_a_fire_outside_every_boundary_keeps_its_date_and_geometry(archives,
                                                                   with_boundaries):
    """The one in the Pacific: no country, still a fire."""
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")

    fire = by_gid(engine)["1980_11"]
    with Session(engine) as session:
        parent = session.get(Wildfire, fire.id)
        assert parent.admin_boundary_id is None
        assert parent.perimeter is not None


@needs_ogr2ogr
def test_the_import_works_without_any_boundaries(archives, database):
    """The perimeters and the dates are worth having; the boundaries can come later."""
    engine, url = database
    assert run(url, archives / "NBAC_2023_20260513.shp") == 0

    with Session(engine) as session:
        parent = session.scalar(select(Wildfire))
        assert parent.admin_boundary_id is None
        assert parent.time_zone is None, "and the fallback zone dated it"


# --------------------------------------------------------------------------
# The flags and the attributes
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_published_flags_are_read(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fires = by_gid(engine)
    assert fires["2023_1"].area_adjusted is True
    assert fires["2023_1"].area_ha_adjusted == pytest.approx(13000.0)
    assert fires["2023_3"].prescribed is True
    assert fires["2023_2"].prescribed is False, "an unset flag is not a true one"


@needs_ogr2ogr
def test_the_provenance_attributes_are_stored(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fire = by_gid(engine)["2023_1"]
    assert (fire.ba_source, fire.detection_source) == ("MAFiMS", "Landsat")
    assert fire.mapping_method == "Processed imagery"
    assert fire.version == "20260513"


@needs_ogr2ogr
def test_a_park_fire_carries_its_division(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_2023_20260513.shp")

    fire = by_gid(engine)["2023_4"]
    assert (fire.admin_name, fire.admin_div) == ("PC", "WB")


# --------------------------------------------------------------------------
# Replacing a year
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_replaces_the_year(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")
    first = count(engine, "nbac_wildfire")

    assert run(url, archives / "NBAC_1980_20260513.shp") == 0
    assert count(engine, "nbac_wildfire") == first
    assert count(engine, "wildfire") == first, "the parent rows went with them"


@needs_ogr2ogr
def test_replacing_a_year_leaves_the_others_alone(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "NBAC_1980_20260513.shp")
    run(url, archives / "NBAC_2023_20260513.shp")
    both = count(engine, "nbac_wildfire")

    run(url, archives / "NBAC_1980_20260513.shp")
    assert count(engine, "nbac_wildfire") == both
    assert {row.year for row in stored(engine)} == {1980, 2023}


@needs_ogr2ogr
def test_only_the_year_asked_for_is_imported(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "NBAC_1980_20260513.shp",
               extra=["--year", "2023"]) == 0

    assert count(engine, "nbac_wildfire") == 0


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "NBAC_1980_20260513.shp", extra=["--dry-run"]) == 0

    assert count(engine, "nbac_wildfire") == 0


@needs_ogr2ogr
def test_a_directory_imports_every_archive(archives, with_boundaries, tmp_path):
    """The real set is 53 zips read in name order, which for this archive is year order."""
    import zipfile

    zipped = tmp_path / "zips"
    zipped.mkdir()
    for layer, _ in LAYERS:
        with zipfile.ZipFile(zipped / f"{layer}.zip", "w") as archive:
            for suffix in (".shp", ".shx", ".dbf", ".prj"):
                archive.write(archives / f"{layer}{suffix}", f"{layer}{suffix}")

    engine, url = with_boundaries
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(zipped), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 0
    assert {row.year for row in stored(engine)} == {1980, 2023}


# --------------------------------------------------------------------------
# The units
# --------------------------------------------------------------------------

def test_the_year_column_is_converted_rather_than_accepted():
    """``YEAR`` is published as Real and goes into ``make_date``, which has no overload.

    Stated as a test because the sibling imports' compatibility table *does* accept a
    double as an integer, and copying it here cost a debugging session.
    """
    assert "double precision" not in app.COMPATIBLE_TYPES["integer"]
    assert app.STAGING_COLUMNS["year"] == "integer"
    assert app.STAGING_COLUMNS["nfireid"] == "integer"


def test_the_year_summary_compresses_to_ranges():
    assert app.summarise_years([1973, 1974, 1975, 1980]) == "1973-1975, 1980"
    assert app.summarise_years([2023]) == "2023"
    assert app.summarise_years([]) == "no year"


def test_an_empty_directory_is_refused(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    arguments = app.parse_arguments(["-d", str(empty), "--db-name", "x", "--db-user", "y"])

    with pytest.raises(RuntimeError, match="no .zip archive"):
        app.find_archives(arguments)


def test_a_missing_path_is_reported_rather_than_raised(tmp_path):
    assert app.main(["-s", str(tmp_path / "nowhere.zip"),
                     "--db-name", "x", "--db-user", "y"]) == 1
