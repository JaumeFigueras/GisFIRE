#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the REDIAM burnt area import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and real shapefiles, so the whole path is exercised — the subprocess, the ``.prj``,
the reprojection, the staging table and the SQL mapping. A mocked ``ogr2ogr`` would
test none of the things that actually go wrong with this dataset.

The fixture layers are built from the GeoJSON below rather than checked in as
binaries, and they are built the way the service publishes them:

* coordinates in ETRS89 / UTM 30N metres;
* a ``.prj`` holding **the published ESRI string**, which carries no EPSG code and
  which GDAL resolves to EPSG:3042 — the same projection declared northing-easting.
  That is the one thing unique to this source, and a fixture that wrote a tidy
  ``EPSG:25830`` ``.prj`` would test a different program: the whole question is
  whether the load keeps easting-northing coordinates where they were;
* ``FECHA_INC`` as a real DBF **date** field, which is what every published layer
  has and why this import needs none of the Catalan date machinery.

Three layers, chosen for what each one carries: the combined layer is where the
perimeters come from and holds the duplicates, the invalid ring and the fire in the
sea; ``PERIMETROS_COR_2022`` is a yearly layer **with** ``X_INIC``/``Y_INIC``; and
``PERIMETROS_COR_2015`` is a yearly layer without them, which fourteen of the eighteen
published ones are.
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

from src.apps.imports.wildfires.andalusia_rediam import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.time_zone import TimeZone
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import andalusia_rediam
from src.providers import ocha
from src.providers import spain_egif
from src.providers.andalusia_rediam.ignition import RediamIgnition
from src.providers.andalusia_rediam.wildfire import RediamWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

#: Spain, near enough for a fixture: it contains every fire below except the one in
#: the Atlantic, which is the point of that one.
SPAIN = "MULTIPOLYGON(((-9.5 36, 3.4 36, 3.4 43.8, -9.5 43.8, -9.5 36)))"

#: The published ``.prj``, verbatim from ``PERIMETROS_COR_2008_2025.prj``.
#:
#: An ESRI dialect with no authority code. GDAL resolves it to EPSG:3042, whose axis
#: order is northing-easting while the coordinates in the file are easting-northing —
#: the trap this import exists to step around, and therefore the thing the fixture has
#: to reproduce.
PUBLISHED_PRJ = (
    'PROJCS["ETRS_1989_ETRS-TM30",GEOGCS["GCS_ETRS_1989",DATUM["D_ETRS_1989",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",-3.0],PARAMETER["Scale_Factor",0.9996],'
    'PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]'
)

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-rediam-import")


def square(x: float, y: float, side: float = 1000.0) -> list:
    """A square in EPSG:25830 metres, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def feature(code, date, municipality, province, geometry,
            wooded=0.0, scrub=1.6, grassland=26.9, x=None, y=None) -> tuple:
    """One published feature, named exactly as the service names its fields."""
    values = {"CODIGO": code, "FECHA_INC": date, "Municipio": municipality,
              "Provincia": province, "SUP_ARBOLA": wooded, "SUP_MATORR": scrub,
              "SUP_PASTIZ": grassland}
    if x is not None:
        values.update({"X_INIC": x, "Y_INIC": y})
    return values, geometry


#: The combined layer, and everything the mapping has to deal with:
#:
#: * ``2008410097`` is an ordinary fire, ten digits, one polygon.
#: * ``2019180023`` is written with a **nine-digit** code, as six published ones are.
#: * ``2022040091`` and ``2022110022`` are the two fires the yearly layer publishes a
#:   point for; the second one's point lands outside its perimeter, as most do.
#: * ``IIFF2025040059`` is the 2025 form, and is published **twice** with the same
#:   footprint and the same areas — 53 real fires are.
#: * ``IIFF2025210122`` is published twice with **different** geometry and different
#:   areas, which one real fire is: 1 ha of scrub against 2 ha, and two squares that
#:   dissolve into a bigger one.
#: * ``2011230044`` is a self-intersecting bowtie, invalid as published, as 71 are.
#: * ``2012410099`` is out in the Atlantic: no country.
FEATURES_COMBINED = [
    feature("2008410097", "2008-09-11", "AZNALCAZAR", "Sevilla", square(215000, 4117000)),
    feature("2019180023", "2019-07-15", "ALGARINEJO", "Granada", square(400000, 4130000)),
    feature("2022040091", "2022-08-01", "DALIAS", "Almería", square(500000, 4100000)),
    feature("2022110022", "2022-08-02", "TARIFA", "Cádiz", square(250000, 4000000)),
    feature("IIFF2025040059", "2025-08-28", "LUBRIN", "ALMERÍA", square(560000, 4110000)),
    feature("IIFF2025040059", "2025-08-28", "Lubrín", "Almería", square(560000, 4110000)),
    feature("IIFF2025210122", "2025-07-03", "ALMONTE", "Huelva", square(180000, 4110000),
            scrub=1.0),
    feature("IIFF2025210122", "2025-07-03", "Almonte", "HUELVA",
            square(180500, 4110000), scrub=2.0),
    feature("2011230044", "2011-06-01", "ANDUJAR", "Jaén",
            [[[430000.0, 4200000.0], [431000.0, 4201000.0], [431000.0, 4200000.0],
              [430000.0, 4201000.0], [430000.0, 4200000.0]]]),
    feature("2012410099", "2012-08-01", "HUELVA", "Huelva", square(-100000, 4100000)),
]

#: ``PERIMETROS_COR_2022``: a yearly layer with the ignition point.
#:
#: The first two match fires in the combined layer; ``2022290077`` matches nothing,
#: which is what the import has to notice rather than store.
FEATURES_2022 = [
    feature("2022040091", "2022-08-01", "DALIAS", "Almería", square(500000, 4100000),
            x=500500.0, y=4100500.0),
    feature("2022110022", "2022-08-02", "TARIFA", "Cádiz", square(250000, 4000000),
            x=260000.0, y=4010000.0),
    feature("2022290077", "2022-09-09", "RONDA", "Málaga", square(300000, 4050000),
            x=300500.0, y=4050500.0),
]

#: ``PERIMETROS_COR_2015``: a yearly layer with no ignition point, as fourteen of the
#: eighteen published ones are.
FEATURES_2015 = [
    feature("2015290011", "2015-07-07", "RONDA", "Málaga", square(310000, 4060000)),
]

#: The layers the fixture directory holds.
LAYERS = [
    ("PERIMETROS_COR_2008_2025", FEATURES_COMBINED),
    ("PERIMETROS_COR_2022", FEATURES_2022),
    ("PERIMETROS_COR_2015", FEATURES_2015),
]


def write_layer(directory: Path, layer: str, features: list) -> Path:
    """Build one layer's shapefile, the way the service publishes it.

    ``-a_srs EPSG:25830`` *assigns* the CRS rather than reprojecting: the coordinates
    are already UTM 30N metres, and GeoJSON is nominally EPSG:4326. The ``.prj`` GDAL
    writes for it is then **overwritten with the published ESRI string**, which is the
    whole point of the fixture — see the module docstring.

    ``FECHA_INC`` is left to GDAL's date detection, which is what makes it a real DBF
    date field, exactly as in the published layers.
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

    subprocess.run(["ogr2ogr", "-f", "ESRI Shapefile", str(directory), str(source),
                    "-nln", layer, "-a_srs", "EPSG:25830",
                    "-lco", "ENCODING=UTF-8"],
                   check=True, capture_output=True)
    source.unlink()
    (directory / f"{layer}.prj").write_text(PUBLISHED_PRJ, encoding="ascii")
    return directory / f"{layer}.shp"


@pytest.fixture
def published(tmp_path) -> Path:
    """A directory of published layers, plus a file that is neither kind."""
    directory = tmp_path / "Shapes"
    directory.mkdir()
    for layer, features in LAYERS:
        write_layer(directory, layer, features)
    write_layer(directory, "MUNICIPIOS", FEATURES_2015)
    return directory


@pytest.fixture
def database(postgresql):
    """An ephemeral PostGIS database with the model schema, plus its connection info."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
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
    """Spain, as an OCHA boundary under an OCHA provider row."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(OchaAdminBoundary(
            data_provider_id=provider.id, source_id="ESP", level=0, name="Spain",
            geometry=f"SRID=4326;{SPAIN}", source="ESP", iso_code=724, iso_2="ES",
            iso_3="ESP", iso_name="Spain", iso_3_group="ESP",
            region1_code=1, region1_name="r1", region2_code=2, region2_name="r2",
            region3_code=3, region3_name="r3", status_code=1, status_name="State",
            valid_date=datetime.date(2025, 1, 1), update_date=datetime.date(2025, 1, 1),
            land_source="osm", view="intl",
        ))
        session.commit()


@pytest.fixture
def time_zones(database):
    """Europe/Madrid over Andalusia, and nothing else."""
    engine, _ = database
    with Session(engine) as session:
        session.add(TimeZone(name=andalusia_rediam.DEFAULT_TIME_ZONE,
                             geometry=f"SRID=4326;{SPAIN}"))
        session.commit()


def run_import(connection_arguments, extra: list[str], level: str = "WARNING") -> int:
    """Run the application's ``main`` and return its exit code."""
    return app.main([*extra, *connection_arguments, "--log-level", level])


def fires(engine) -> list[RediamWildfire]:
    with Session(engine) as session:
        return list(session.scalars(
            select(RediamWildfire).order_by(RediamWildfire.code, RediamWildfire.fire_date)))


def find(engine, code: str) -> RediamWildfire:
    matches = [fire for fire in fires(engine) if fire.code == code]
    assert len(matches) == 1, f"expected one fire {code}, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Arguments and layer selection
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_the_two_sources_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", str(tmp_path), "-s", str(tmp_path / "a.shp")])


def test_the_combined_layer_is_what_perimeters_come_from(published):
    args = app.parse_arguments(["-d", str(published)])
    perimeters, _ = app.find_layers(args)

    assert perimeters.stem == "PERIMETROS_COR_2008_2025"


def test_the_yearly_layers_are_listed_in_year_order(published):
    args = app.parse_arguments(["-d", str(published)])
    _, yearly = app.find_layers(args)

    assert [path.stem for path in yearly] == ["PERIMETROS_COR_2015", "PERIMETROS_COR_2022"]


def test_the_combined_layer_is_found_whatever_range_it_names(published):
    """The range grows every publication; an import keyed on the name would stop."""
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        source = published / f"PERIMETROS_COR_2008_2025{suffix}"
        if source.exists():
            source.rename(published / f"PERIMETROS_COR_2008_2031{suffix}")

    args = app.parse_arguments(["-d", str(published)])
    perimeters, _ = app.find_layers(args)
    assert perimeters.stem == "PERIMETROS_COR_2008_2031"


def test_two_combined_layers_are_refused(published):
    """Importing both would import the overlapping years twice."""
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        source = published / f"PERIMETROS_COR_2008_2025{suffix}"
        if source.exists():
            shutil.copy(source, published / f"PERIMETROS_COR_2008_2024{suffix}")

    args = app.parse_arguments(["-d", str(published)])
    with pytest.raises(RuntimeError, match="combined layers"):
        app.find_layers(args)


def test_a_directory_with_no_combined_layer_is_an_error(tmp_path):
    directory = tmp_path / "yearly-only"
    directory.mkdir()
    write_layer(directory, "PERIMETROS_COR_2015", FEATURES_2015)

    args = app.parse_arguments(["-d", str(directory)])
    with pytest.raises(RuntimeError, match="no combined layer"):
        app.find_layers(args)


def test_an_empty_directory_is_an_error(tmp_path):
    args = app.parse_arguments(["-d", str(tmp_path)])
    with pytest.raises(RuntimeError, match="no .zip or .shp"):
        app.find_layers(args)


def test_a_file_that_is_neither_kind_is_reported(published):
    args = app.parse_arguments(["-d", str(published)])

    assert [path.stem for path in app.skipped_layers(args)] == ["MUNICIPIOS"]


def test_a_year_narrows_the_yearly_layers(published):
    args = app.parse_arguments(["-d", str(published), "--year", "2022"])
    perimeters, yearly = app.find_layers(args)

    # The combined layer is still the source of the perimeters: it holds every year
    # in one file, and the filter is applied in SQL.
    assert perimeters.stem == "PERIMETROS_COR_2008_2025"
    assert [path.stem for path in yearly] == ["PERIMETROS_COR_2022"]


def test_the_years_a_run_touched_are_summarised_for_the_log():
    assert app.summarise_years([2008, 2009, 2010]) == "2008-2010"
    assert app.summarise_years([2021, 2023]) == "2021, 2023"
    assert app.summarise_years([2024]) == "2024"


# --------------------------------------------------------------------------
# The import itself
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_whole_directory_imports(published, database, connection_arguments,
                                     boundaries, time_zones):
    engine, _ = database
    assert run_import(connection_arguments, ["-d", str(published)]) == 0

    # Ten published features, eight fires: two pairs share a code and a date.
    assert len(fires(engine)) == 8


@needs_ogr2ogr
def test_a_duplicated_fire_becomes_one_row(published, database, connection_arguments,
                                           time_zones):
    """53 real 2025 fires are published twice with the same footprint."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "IIFF2025040059")
    assert fire.part_count == 2
    with Session(engine) as session:
        area = session.scalar(select(func.ST_Area(RediamWildfire.perimeter_etrs89_utm30n))
                              .where(RediamWildfire.code == "IIFF2025040059"))
    # The same square either row already had: nothing was merged that was not already
    # the same polygon.
    assert area == pytest.approx(1_000_000.0)


@needs_ogr2ogr
def test_a_fire_published_as_two_different_polygons_is_unioned(
        published, database, connection_arguments, time_zones):
    """One real fire is: 363.8 ha and 517.4 ha, dissolving to 527.5 ha."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "IIFF2025210122")
    assert fire.part_count == 2
    with Session(engine) as session:
        area = session.scalar(select(func.ST_Area(RediamWildfire.perimeter_etrs89_utm30n))
                              .where(RediamWildfire.code == "IIFF2025210122"))
    # Two 1 km squares overlapping by half: 1.5 km².
    assert area == pytest.approx(1_500_000.0)


@needs_ogr2ogr
def test_disagreeing_areas_are_reported_not_hidden(published, database,
                                                   connection_arguments, time_zones,
                                                   caplog):
    """Two real fires are published twice with different burnt areas."""
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        run_import(connection_arguments, ["-d", str(published)])

    assert "published twice with different burnt areas" in caplog.text
    # The larger of the two, and the one that is reported.
    assert find(engine, "IIFF2025210122").area_ha_scrub == pytest.approx(2.0)


@needs_ogr2ogr
def test_an_invalid_polygon_is_repaired_rather_than_dropped(
        published, database, connection_arguments, time_zones):
    """71 of the 962 published features have a self-intersecting ring."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        valid = session.scalar(select(func.ST_IsValid(
            RediamWildfire.perimeter_etrs89_utm30n))
            .where(RediamWildfire.code == "2011230044"))
    assert valid is True


@needs_ogr2ogr
def test_the_perimeter_is_stored_in_both_crs(published, database, connection_arguments,
                                             time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        srids = session.execute(select(
            func.ST_SRID(RediamWildfire.perimeter_etrs89_utm30n),
            func.ST_SRID(RediamWildfire.perimeter),
        ).where(RediamWildfire.code == "2008410097")).one()
    assert tuple(srids) == (andalusia_rediam.SOURCE_SRID, 4326)


@needs_ogr2ogr
def test_the_published_prj_does_not_swap_the_axes(published, database,
                                                  connection_arguments, time_zones):
    """The ``.prj`` resolves to EPSG:3042, whose axis order the file does not follow.

    The fixture writes the published ESRI string, so this is the real question: does
    the loaded easting stay an easting? A swap would put the fire at 4,117,000 m east
    and 215,000 m north — off the grid, and in the sea if it landed anywhere.
    """
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        box = session.execute(select(
            func.ST_XMin(RediamWildfire.perimeter_etrs89_utm30n),
            func.ST_YMin(RediamWildfire.perimeter_etrs89_utm30n),
        ).where(RediamWildfire.code == "2008410097")).one()
    assert box[0] == pytest.approx(215000.0)
    assert box[1] == pytest.approx(4117000.0)


@needs_ogr2ogr
def test_the_two_geometries_are_the_same_one(published, database, connection_arguments,
                                             time_zones):
    """The 4326 perimeter is derived from the stored one, so they cannot disagree."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        same = session.scalar(select(func.ST_Equals(
            func.ST_Transform(RediamWildfire.perimeter_etrs89_utm30n, 4326),
            RediamWildfire.perimeter,
        )).where(RediamWildfire.code == "2008410097"))
    assert same is True


@needs_ogr2ogr
def test_the_code_is_stored_exactly_as_published(published, database,
                                                 connection_arguments, time_zones):
    """The IIFF prefix and all: decoding it is the binding application's business."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    codes = {fire.code for fire in fires(engine)}
    assert "IIFF2025040059" in codes
    assert "2019180023" in codes, "a nine-digit code is stored as it was published"
    # And it decodes, which is what makes the binding possible later.
    assert andalusia_rediam.egif_report_number("2019180023") == "2019180023"


@needs_ogr2ogr
def test_the_year_comes_from_the_published_date(published, database,
                                                connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert find(engine, "2008410097").year == 2008
    assert find(engine, "IIFF2025040059").year == 2025


@needs_ogr2ogr
def test_the_start_is_local_midnight_on_the_published_date(
        published, database, connection_arguments, time_zones):
    """The dataset publishes no time of day, so the instant is local midnight."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "2008410097")
    assert fire.fire_date == datetime.date(2008, 9, 11)
    # Europe/Madrid is UTC+2 in September.
    assert fire.start_date_time == datetime.datetime(2008, 9, 10, 22, 0, tzinfo=UTC)
    assert fire.time_zone == andalusia_rediam.DEFAULT_TIME_ZONE


@needs_ogr2ogr
def test_no_end_date_is_invented(published, database, connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert all(fire.end_date_time is None for fire in fires(engine))


@needs_ogr2ogr
def test_the_areas_are_stored_as_published(published, database, connection_arguments,
                                           time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "2008410097")
    assert (fire.area_ha_wooded, fire.area_ha_scrub, fire.area_ha_grassland) == \
        pytest.approx((0.0, 1.6, 26.9))


@needs_ogr2ogr
def test_the_province_is_stored_as_published(published, database, connection_arguments,
                                             time_zones):
    """Case and accents are the source's, and vary within one layer."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert find(engine, "2008410097").province_name == "Sevilla"


@needs_ogr2ogr
def test_a_fire_is_attributed_to_its_country(published, database, connection_arguments,
                                             boundaries, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        # Against the tables rather than the mapped classes: joining a subclass to
        # its own parent makes SQLAlchemy alias one of them.
        wildfire, rediam = Wildfire.__table__, RediamWildfire.__table__
        country = session.scalar(
            select(OchaAdminBoundary.name)
            .select_from(rediam)
            .join(wildfire, wildfire.c.id == rediam.c.id)
            .join(OchaAdminBoundary, OchaAdminBoundary.id == wildfire.c.admin_boundary_id)
            .where(rediam.c.code == "2008410097"))
    assert country == "Spain"


@needs_ogr2ogr
def test_a_fire_outside_every_boundary_keeps_its_perimeter(
        published, database, connection_arguments, boundaries, time_zones):
    """The Atlantic one. No country is not a reason to drop a published fire."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "2012410099")
    assert fire.admin_boundary_id is None
    assert fire.perimeter is not None


@needs_ogr2ogr
def test_the_import_works_without_boundaries_or_time_zones(
        published, database, connection_arguments):
    """Neither is required; a fire simply has no country and falls back on the zone."""
    engine, _ = database
    assert run_import(connection_arguments, ["-d", str(published)]) == 0

    assert len(fires(engine)) == 8
    assert all(fire.admin_boundary_id is None for fire in fires(engine))


# --------------------------------------------------------------------------
# The ignition points
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_points_are_read_from_the_yearly_layer(published, database,
                                                   connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        points = list(session.scalars(select(RediamIgnition).order_by(RediamIgnition.code)))
    assert [point.code for point in points] == ["2022040091", "2022110022"]
    assert points[0].utm_x == pytest.approx(500500.0)
    assert points[0].source_layer == "PERIMETROS_COR_2022"


@needs_ogr2ogr
def test_a_point_is_linked_to_its_fire(published, database, connection_arguments,
                                       time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    # Inside a session, because the link is a relationship and reading it is a query.
    with Session(engine) as session:
        fire = session.scalar(select(RediamWildfire)
                              .where(RediamWildfire.code == "2022040091"))
        assert fire.ignition is not None
        assert fire.ignition.code == fire.code
        assert fire.ignition.fire_date == fire.fire_date


@needs_ogr2ogr
def test_a_fire_of_a_year_with_no_points_has_none(published, database,
                                                  connection_arguments, time_zones):
    """Four fires in five: the service published no coordinate before 2021."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert find(engine, "2008410097").ignition_id is None


@needs_ogr2ogr
def test_the_point_is_the_published_one_reprojected(published, database,
                                                    connection_arguments, time_zones):
    """The published easting and northing are kept, and the point derived from them."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        same = session.scalar(select(func.ST_Equals(
            func.ST_Transform(
                func.ST_SetSRID(func.ST_MakePoint(RediamIgnition.utm_x,
                                                  RediamIgnition.utm_y),
                                andalusia_rediam.SOURCE_SRID), 4326),
            RediamIgnition.geometry,
        )).where(RediamIgnition.code == "2022040091"))
    assert same is True


@needs_ogr2ogr
def test_a_point_outside_its_own_perimeter_is_stored_anyway(
        published, database, connection_arguments, time_zones):
    """113 of the 201 published points are outside, and none of them is corrected."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    fire = find(engine, "2022110022")
    with Session(engine) as session:
        inside = session.scalar(select(func.ST_Contains(
            RediamWildfire.perimeter_etrs89_utm30n,
            func.ST_SetSRID(func.ST_MakePoint(RediamIgnition.utm_x, RediamIgnition.utm_y),
                            andalusia_rediam.SOURCE_SRID),
        )).where(RediamWildfire.id == fire.id)
            .where(RediamIgnition.id == RediamWildfire.ignition_id))
    assert inside is False


@needs_ogr2ogr
def test_a_point_belonging_to_no_imported_fire_is_reported(
        published, database, connection_arguments, time_zones, caplog):
    """The yearly layer and the combined one disagreeing is worth saying out loud."""
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        run_import(connection_arguments, ["-d", str(published)])

    assert "belong to no imported fire" in caplog.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RediamIgnition.__table__)) == 2


@needs_ogr2ogr
def test_a_yearly_layer_with_no_coordinates_is_skipped(published, database,
                                                       connection_arguments, time_zones,
                                                       caplog):
    engine, _ = database
    with caplog.at_level(logging.INFO):
        run_import(connection_arguments, ["-d", str(published)], level="INFO")

    assert "Publishes no ignition coordinate" in caplog.text
    # And it did not import 2015's fire as a second copy of anything.
    assert len(fires(engine)) == 8


@needs_ogr2ogr
def test_the_points_can_be_left_alone(published, database, connection_arguments,
                                      time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published), "--skip-ignitions"])

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Ignition.__table__)) == 0
    assert len(fires(engine)) == 8


# --------------------------------------------------------------------------
# Re-importing
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_replaces_rather_than_doubles(published, database,
                                                   connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    run_import(connection_arguments, ["-d", str(published)])

    assert len(fires(engine)) == 8
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 8
        assert session.scalar(select(func.count()).select_from(Ignition.__table__)) == 2


@needs_ogr2ogr
def test_a_layer_renamed_for_a_longer_range_still_replaces(
        published, database, connection_arguments, time_zones):
    """The whole reason the import replaces years rather than the layer it read.

    Next year's file is ``PERIMETROS_COR_2008_2026``. An import keyed on the layer
    name would treat it as a new dataset and store every fire a second time, with the
    same codes and the same polygons and nothing downstream to notice.
    """
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        source = published / f"PERIMETROS_COR_2008_2025{suffix}"
        if source.exists():
            source.rename(published / f"PERIMETROS_COR_2008_2026{suffix}")

    run_import(connection_arguments, ["-d", str(published)])

    assert len(fires(engine)) == 8
    assert {fire.source_layer for fire in fires(engine)} == {"PERIMETROS_COR_2008_2026"}


@needs_ogr2ogr
def test_re_importing_one_year_leaves_the_others(published, database,
                                                 connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    run_import(connection_arguments, ["-d", str(published), "--year", "2022"])

    assert len(fires(engine)) == 8


@needs_ogr2ogr
def test_re_importing_leaves_no_orphan_parent_rows(published, database,
                                                   connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        orphans = session.scalar(text(
            "SELECT count(*) FROM wildfire w "
            "LEFT JOIN rediam_wildfire s ON s.id = w.id WHERE s.id IS NULL"))
        stray_points = session.scalar(text(
            "SELECT count(*) FROM ignition i "
            "LEFT JOIN rediam_ignition s ON s.id = i.id WHERE s.id IS NULL"))
    assert (orphans, stray_points) == (0, 0)


@needs_ogr2ogr
def test_re_importing_warns_that_an_egif_binding_is_going(
        published, database, connection_arguments, time_zones, caplog):
    """Nothing here writes that column, so a filled one is another application's work."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                     product=spain_egif.PROVIDER_PRODUCT,
                                     full_name=spain_egif.PROVIDER_FULL_NAME)
        session.add(egif_provider)
        session.flush()
        parte = EgifWildfire(
            data_provider_id=egif_provider.id, report_number="2008410097",
            campaign=2008, province_ine_code="41",
            start_date_time=datetime.datetime(2008, 9, 11, 12, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE)
        session.add(parte)
        session.flush()
        fire = session.scalar(select(RediamWildfire)
                              .where(RediamWildfire.code == "2008410097"))
        fire.egif_wildfire_id = parte.id
        fire.match_method = "code"
        fire.match_confidence = 1.0
        fire.matched_at = datetime.datetime(2026, 8, 3, tzinfo=UTC)
        session.commit()

    with caplog.at_level(logging.WARNING):
        run_import(connection_arguments, ["-d", str(published)])

    assert "bound to an EGIF parte" in caplog.text
    assert find(engine, "2008410097").egif_wildfire_id is None


@needs_ogr2ogr
def test_the_import_never_fills_the_egif_link(published, database, connection_arguments,
                                              time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert all(fire.egif_wildfire_id is None for fire in fires(engine))
    assert all(fire.match_method is None for fire in fires(engine))


# --------------------------------------------------------------------------
# Dry runs and housekeeping
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_dry_run_writes_nothing(published, database, connection_arguments, time_zones):
    engine, _ = database
    assert run_import(connection_arguments, ["-d", str(published), "--dry-run"]) == 0

    assert fires(engine) == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Ignition.__table__)) == 0


@needs_ogr2ogr
def test_a_dry_run_does_not_replace_what_is_already_there(
        published, database, connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    run_import(connection_arguments, ["-d", str(published), "--dry-run"])

    assert len(fires(engine)) == 8


@needs_ogr2ogr
def test_the_staging_table_is_dropped(published, database, connection_arguments,
                                      time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        remaining = session.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'staging'"))
    assert remaining == 0


@needs_ogr2ogr
def test_a_single_file_is_imported_as_given(published, database, connection_arguments,
                                            time_zones):
    """A yearly layer on its own: its fires and, if it has them, its points."""
    engine, _ = database
    assert run_import(connection_arguments,
                      ["-s", str(published / "PERIMETROS_COR_2022.shp")]) == 0

    assert {fire.code for fire in fires(engine)} == {"2022040091", "2022110022",
                                                     "2022290077"}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RediamIgnition.__table__)) == 3


@needs_ogr2ogr
def test_a_missing_source_is_reported_rather_than_traced(tmp_path, connection_arguments):
    assert run_import(connection_arguments, ["-d", str(tmp_path / "nowhere")]) == 1
