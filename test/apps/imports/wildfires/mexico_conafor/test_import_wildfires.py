#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAFOR burnt area import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and real shapefiles, so the whole path is exercised — the subprocess,
the staging table, the column renaming, the two Python normalisation passes and
the SQL mapping. A mocked ``ogr2ogr`` would test none of the things that actually
go wrong with this dataset, and what goes wrong with this one is almost entirely
*what the file turns out to contain*.

The fixture archives are built from the GeoJSON below rather than checked in as
binaries, and they are built the way CONAFOR publishes them: EPSG:4326
coordinates, a UTF-8 DBF, and — crucially — **a different set of field names in
every layer**, because that is the whole difficulty of the source.

Four layers, covering the four shapes the schema takes:

``incendios_2019``
    The richest: every attribute the series ever publishes, ``CAUSAESP`` and all
    six burnt-area strata included.
``incendios_2012``
    The odd one out: ``CLAVE`` for the key, ``TOTAL`` for the area, ``ARB_ADUL``
    and friends for the strata, ``TIP_VEG``/``TIPO_INC``/``CAUSA_ESPE``, and no
    ``ANP``, ``TIPIMPAC`` or ``CLAVEMUN`` at all.
``incendios_2021``
    The one with the five duplicate features.
``incendios_2023``
    The newest: ``POLIGONO``, no ``PREDIO``, and none of the six strata.
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

from src.apps.imports.wildfires.mexico_conafor import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import mexico_conafor
from src.providers import ocha
from src.providers.mexico_conafor.fire_cause import ConaforFireCause
from src.providers.mexico_conafor.wildfire import ConaforWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

UTC = datetime.timezone.utc

#: Mexico, near enough for a fixture: it contains every fire below except the
#: Pacific one, which is the point of that one.
MEXICO = "MULTIPOLYGON(((-118 14, -86 14, -86 33, -118 33, -118 14)))"

#: The two zones the fires are placed in. Mexico spans four, and these two are
#: two hours apart — which is what makes a per-fire lookup distinguishable from a
#: national default. ``America/Tijuana`` covers the north-west corner only.
CENTRAL_ZONE = "MULTIPOLYGON(((-114 14, -86 14, -86 33, -114 33, -114 14)))"
PACIFIC_ZONE = "MULTIPOLYGON(((-118 28, -114 28, -114 33, -118 33, -118 28)))"

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-conafor-import")


def square(longitude: float, latitude: float, side: float = 0.01) -> list:
    """A small square in EPSG:4326 degrees, as GeoJSON Polygon coordinates."""
    return [[[longitude, latitude], [longitude + side, latitude],
             [longitude + side, latitude + side], [longitude, latitude + side],
             [longitude, latitude]]]


def modern(**overrides) -> dict:
    """One 2019 feature's attributes, named exactly as CONAFOR names them.

    Everything defaults to something plausible so a test can name only what it
    cares about.
    """
    values = {
        "ID": 1, "CLAVEINC": "19-01-0102", "ESTADO": "Aguascalientes",
        "CLAVEMUN": 2, "MUNICIPIO": "Asientos", "PREDIO": "Tanque Juarez",
        "CAUSA": "Fogatas", "CAUSAESP": "Fogatas de paseantes",
        "FECHAINIC": "2019-06-07", "FECHALIQ": "2019-06-08",
        "TIPOINC": "Superficial", "ANP": "N/A", "ANP_HA": 0.0,
        "TIPVEG": "Bosque de Pino-Encino - BPQ", "TIPIMPAC": "Impacto Minimo",
        "ARBOR_HA": 0.0, "RENUEV_HA": 0.0, "ARBUSTI_HA": 1.28,
        "HERBAC_HA": 7.25, "HOJAR_HA": 0.0, "SUELORG_HA": 0.0, "AREA_HA": 8.53,
    }
    values.update(overrides)
    return values


#: Eight features of ``incendios_2019``. Every one is placed deliberately:
#:
#: * ``19-01-0102`` in Aguascalientes, the ordinary case, with a vegetation code
#:   and a cause that has both halves.
#: * ``19-02-0001`` in Baja California — ``America/Tijuana``, two hours from the
#:   others, so a national default instead of a per-fire lookup would be caught.
#: * ``19-20-0140`` writes its cause ``'fogatas'`` and its impact
#:   ``'Impacto minimo'``: the same classifications in different clothes.
#: * ``19-08-0001`` writes ``'Tormenta Electrica'``, the 2011 wording for what
#:   later layers call *Naturales*.
#: * ``19-14-0001`` carries a cause no reconciliation table has ever seen.
#: * ``19-16-0001`` is a self-intersecting bowtie, invalid as published.
#: * ``19-30-0001`` writes ``'Bosque de Encino - Pino'``, whose trailing word is
#:   the other half of the name and not an INEGI code.
#: * ``19-26-0001`` is in the Pacific, outside every boundary and every zone.
MODERN_FEATURES = [
    (modern(), square(-102.30, 21.88)),
    (modern(ID=2, CLAVEINC="19-02-0001", ESTADO="Baja California", CLAVEMUN=1,
            MUNICIPIO="Ensenada", PREDIO="Santo Tomas", CAUSA="Intencional",
            CAUSAESP="Vandalismo", FECHAINIC="2019-06-07", FECHALIQ="2019-06-07",
            TIPVEG="Chaparral", ANP="Sierra de San Pedro Martir", ANP_HA=12.5,
            AREA_HA=526.0, ARBUSTI_HA=516.0, HERBAC_HA=10.0),
     square(-116.50, 31.50)),
    (modern(ID=3, CLAVEINC="19-20-0140", ESTADO="Oaxaca", CLAVEMUN=175,
            MUNICIPIO="San Juan Bautista Atatlahuca", CAUSA="fogatas",
            CAUSAESP="Fogatas de Paseantes", TIPIMPAC="Impacto minimo",
            AREA_HA=2715.178),
     square(-96.80, 17.60)),
    (modern(ID=4, CLAVEINC="19-08-0001", ESTADO="Chihuahua", CLAVEMUN=17,
            MUNICIPIO="Chihuahua", CAUSA="Tormenta Electrica", CAUSAESP="Rayos",
            AREA_HA=40.0),
     square(-106.10, 28.60)),
    (modern(ID=5, CLAVEINC="19-14-0001", ESTADO="Jalisco", CLAVEMUN=98,
            MUNICIPIO="Tomatlan", CAUSA="Drones recreativos",
            CAUSAESP="Categoria que no existe", AREA_HA=3.0),
     square(-105.20, 19.90)),
    (modern(ID=6, CLAVEINC="19-16-0001", ESTADO="Michoacan", CLAVEMUN=53,
            MUNICIPIO="Morelia", AREA_HA=1.5),
     [[[-101.20, 19.70], [-101.19, 19.71], [-101.19, 19.70],
       [-101.20, 19.71], [-101.20, 19.70]]]),
    (modern(ID=7, CLAVEINC="19-30-0001", ESTADO="Veracruz", CLAVEMUN=87,
            MUNICIPIO="Jalacingo", TIPVEG="Bosque de Encino - Pino", AREA_HA=6.0),
     square(-97.30, 19.80)),
    (modern(ID=8, CLAVEINC="19-26-0001", ESTADO="Sonora", CLAVEMUN=30,
            MUNICIPIO="Hermosillo", AREA_HA=9.0),
     square(-125.00, 25.00)),
]

#: Four features of ``incendios_2012``, which names almost nothing the way the
#: other layers do and publishes neither ``ANP``, ``TIPIMPAC`` nor ``CLAVEMUN``.
#: The fourth has **no geometry at all**, which nine of the real 224 do.
HISTORICAL_FEATURES = [
    ({"ID": 1, "CLAVE": "12-01-0012", "ESTADO": "Aguascalientes",
      "MUNICIPIO": "Aguascalientes", "PREDIO": "Cerro de los Gallos",
      "PARAJE": "0", "TIP_PRO": "0", "NUM_INC": "12",
      "FECHAINIC": "2012-06-09", "FECHALIQ": "2012-06-14", "HR_LIQ": "0",
      "CAUSA": "Fogatas", "CAUSA_ESPE": "Fogatas de paseantes",
      "TIP_VEG": "Bosque de Encino", "TIPO_INC": "Mixto", "RELEVANTE": "0",
      "ARB_ADUL": "0.64", "RENUEV": "0", "ARBUST": "16", "PASTO": "25.6",
      "HOJARASCA": "19.2", "SUELO_ORG": "2.56", "TOTAL": "64"},
     square(-102.35, 21.85)),
    ({"ID": 2, "CLAVE": "12-02-0011", "ESTADO": "Baja California",
      "MUNICIPIO": "Ensenada", "PREDIO": "Leyes de Reforma", "PARAJE": "0",
      "TIP_PRO": "0", "NUM_INC": "11", "FECHAINIC": "2012-05-10",
      "FECHALIQ": "2012-05-10", "HR_LIQ": "0", "CAUSA": "Intencional",
      "CAUSA_ESPE": "Rencillas", "TIP_VEG": "Chaparral",
      "TIPO_INC": "Superficial", "RELEVANTE": "0", "ARB_ADUL": "0.5",
      "RENUEV": "0", "ARBUST": "0", "PASTO": "15.8", "HOJARASCA": "0",
      "SUELO_ORG": "0", "TOTAL": "16.3"},
     square(-116.55, 31.80)),
    ({"ID": 3, "CLAVE": "12-12-0001", "ESTADO": "Guerrero",
      "MUNICIPIO": "Atoyac de Alvarez", "PREDIO": "Ejido Mexcaltepec",
      "PARAJE": "0", "TIP_PRO": "0", "NUM_INC": "1", "FECHAINIC": "2012-05-06",
      "FECHALIQ": "2012-05-01", "HR_LIQ": "0", "CAUSA": "Desconocidas",
      "CAUSA_ESPE": "Desconocidas", "TIP_VEG": "0", "TIPO_INC": "Superficial",
      "RELEVANTE": "0", "ARB_ADUL": "0", "RENUEV": "0", "ARBUST": "2",
      "PASTO": "1", "HOJARASCA": "0", "SUELO_ORG": "0", "TOTAL": "3"},
     square(-100.40, 17.27)),
    ({"ID": 4, "CLAVE": "12-14-0001", "ESTADO": "Jalisco",
      "MUNICIPIO": "Bolanos", "PREDIO": "Sin nombre", "PARAJE": "0",
      "TIP_PRO": "0", "NUM_INC": "1", "FECHAINIC": "2012-04-02",
      "FECHALIQ": "2012-04-03", "HR_LIQ": "0", "CAUSA": "Fogatas",
      "CAUSA_ESPE": "0", "TIP_VEG": "Bosque de Pino", "TIPO_INC": "Superficial",
      "RELEVANTE": "0", "ARB_ADUL": "0", "RENUEV": "0", "ARBUST": "1",
      "PASTO": "1", "HOJARASCA": "0", "SUELO_ORG": "0", "TOTAL": "2"},
     None),
]


def duplicated(**overrides) -> dict:
    values = {
        "ID": 195, "CLAVEINC": "21-12-0195", "ESTADO": "Guerrero", "CLAVEMUN": 11,
        "MUNICIPIO": "Atoyac de Alvarez", "PREDIO": "Ejido Mexcaltepec",
        "CAUSA": "Actividades Agricolas", "FECHAINIC": "2021-04-20",
        "FECHALIQ": "2021-04-20", "TIPOINC": "Superficial", "ANP": "N/A",
        "ANP_HA": 0.0, "TIPVEG": "Selva Baja Caducifolia",
        "TIPIMPAC": "Impacto Minimo", "ARBOR_HA": 0.0, "RENUEV_HA": 0.0,
        "ARBUSTI_HA": 1.6, "HERBAC_HA": 0.9, "HOJAR_HA": 0.5, "AREA_HA": 3.0,
    }
    values.update(overrides)
    return values


#: Six features of ``incendios_2021``, four of them the two duplicate pairs the
#: published archive really has — the second copy of each with its dates blanked,
#: which is exactly the shape of the four Guerrero rows. Plus the two rows whose
#: end dates cannot be read at all.
DUPLICATE_FEATURES = [
    (duplicated(), square(-100.39, 17.27)),
    (duplicated(FECHAINIC="", FECHALIQ=""), square(-100.39, 17.27)),
    (duplicated(ID=140, CLAVEINC="21-20-0140", ESTADO="Oaxaca", CLAVEMUN=175,
                MUNICIPIO="San Juan Bautista Atatlahuca", CAUSA="Naturales",
                FECHAINIC="2021-04-23", FECHALIQ="2021-05-02", AREA_HA=2715.178),
     square(-96.79, 17.62)),
    (duplicated(ID=140, CLAVEINC="21-20-0140", ESTADO="Oaxaca", CLAVEMUN=175,
                MUNICIPIO="San Juan Bautista Atatlahuca", CAUSA="Naturales",
                FECHAINIC="2021-04-23", FECHALIQ="2021-05-02", AREA_HA=2715.178),
     square(-96.79, 17.62)),
    (duplicated(ID=51, CLAVEINC="21-19-0051", ESTADO="Nuevo Leon", CLAVEMUN=48,
                MUNICIPIO="Santiago", CAUSA="Fumadores",
                FECHAINIC="2021-12-21", FECHALIQ="22/12/202", AREA_HA=5.0),
     square(-100.15, 25.42)),
    (duplicated(ID=82, CLAVEINC="21-21-0082", ESTADO="Puebla", CLAVEMUN=132,
                MUNICIPIO="Tlatlauquitepec", CAUSA="Intencional",
                FECHAINIC="2021-02-22", FECHALIQ="22/20/2021", AREA_HA=7.0),
     square(-97.50, 19.85)),
]

#: Three features of ``incendios_2023``: ``POLIGONO``, no ``PREDIO``, none of the
#: six strata, and one row whose start date is the archive's single month-first
#: value.
NEWEST_FEATURES = [
    ({"ID": 1, "CLAVEINC": "23-01-0001", "ESTADO": "Aguascalientes",
      "CLAVEMUN": 1, "MUNICIPIO": "Aguascalientes", "CAUSA": "Intencional",
      "FECHAINIC": "2023-01-10", "FECHALIQ": "2023-01-10",
      "TIPOINC": "Superficial", "ANP": "Cobos", "ANP_HA": 0.13,
      "TIPVEG": "Pastizal Natural", "TIPIMPAC": "Impacto Minimo",
      "AREA_HA": 3.41, "POLIGONO": "IMAGEN"},
     square(-102.31, 21.87)),
    ({"ID": 2, "CLAVEINC": "23-29-0003", "ESTADO": "Tlaxcala", "CLAVEMUN": 10,
      "MUNICIPIO": "Chiautempan", "CAUSA": "Fogatas\n",
      "FECHAINIC": "01/15/2023", "FECHALIQ": "01/15/2023",
      "TIPOINC": "Superficial", "ANP": "0", "ANP_HA": 0.0,
      "TIPVEG": "Bosque de Pino", "TIPIMPAC": "Impacto Minimo",
      "AREA_HA": 12.0, "POLIGONO": "COORD"},
     square(-98.10, 19.30)),
    ({"ID": 3, "CLAVEINC": "23-31-0001", "ESTADO": "Yucatan", "CLAVEMUN": 50,
      "MUNICIPIO": "Merida", "CAUSA": "Desconocidas", "FECHAINIC": "",
      "FECHALIQ": "", "TIPOINC": "Superficial", "ANP": "N/A", "ANP_HA": 0.0,
      "TIPVEG": "Selva Baja Caducifolia", "TIPIMPAC": "Impacto Minimo",
      "AREA_HA": 20.0, "POLIGONO": ""},
     square(-89.60, 20.98)),
    # The shape of 21-24-0078: everything published except the burnt area.
    ({"ID": 4, "CLAVEINC": "23-24-0078", "ESTADO": "San Luis Potosi",
      "CLAVEMUN": 28, "MUNICIPIO": "San Luis Potosi", "CAUSA": "Desconocidas",
      "FECHAINIC": "2023-12-21", "FECHALIQ": "2023-12-22",
      "TIPOINC": "Superficial", "ANP": "0", "ANP_HA": 6.41,
      "TIPVEG": "Palmar Natural", "TIPIMPAC": "Impacto Minimo",
      "AREA_HA": None, "POLIGONO": "COORD"},
     square(-100.98, 22.15)),
]


def write_archive(directory: Path, layer: str, features: list) -> Path:
    """Build one layer's zipped shapefile, the way CONAFOR publishes them.

    EPSG:4326 and a UTF-8 ``.cpg``, which is what the real archives carry —
    unlike the ICNF ones, GDAL can work the character set out for itself here, so
    the importer passes no ``-oo ENCODING``.

    A feature whose geometry is ``None`` is written with a null shape, which nine
    of the real 2012 features have.
    """
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": values,
             "geometry": None if coordinates is None
                         else {"type": "Polygon", "coordinates": coordinates}}
            for values, coordinates in features
        ],
    }
    source = directory / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")

    unpacked = directory / layer
    subprocess.run(["ogr2ogr", "-f", "ESRI Shapefile", str(unpacked), str(source),
                    "-nln", layer, "-a_srs", "EPSG:4326", "-lco", "ENCODING=UTF-8"],
                   check=True, capture_output=True)
    source.unlink()

    archive = shutil.make_archive(str(directory / f"{layer}_shp"), "zip",
                                  root_dir=str(unpacked))
    shutil.rmtree(unpacked)
    return Path(archive)


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
    """Mexico, as an OCHA boundary under an OCHA provider row."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(OchaAdminBoundary(
            data_provider_id=provider.id, source_id="MEX", level=0, name="Mexico",
            geometry=f"SRID=4326;{MEXICO}", source="MEX", iso_code=484, iso_2="MX",
            iso_3="MEX", iso_name="Mexico", iso_3_group="MEX",
            region1_code=1, region1_name="r1", region2_code=2, region2_name="r2",
            region3_code=3, region3_name="r3", status_code=1, status_name="State",
            valid_date=datetime.date(2025, 1, 1), update_date=datetime.date(2025, 1, 1),
            land_source="osm", view="intl",
        ))
        session.commit()


@pytest.fixture
def time_zones(database):
    """Two of Mexico's four zones, two hours apart.

    Inserted directly rather than through the time zone importer: what these tests
    need is two zones with different offsets covering different fires, which is
    exactly the thing that distinguishes a real lookup from a national default.
    """
    engine, _ = database
    with Session(engine) as session:
        session.add(TimeZone(name="America/Mexico_City", geometry=f"SRID=4326;{CENTRAL_ZONE}"))
        session.add(TimeZone(name="America/Tijuana", geometry=f"SRID=4326;{PACIFIC_ZONE}"))
        session.commit()


@pytest.fixture
def archives(tmp_path):
    """A directory holding all four layers, as the download lays them out."""
    write_archive(tmp_path, "incendios_2012", HISTORICAL_FEATURES)
    write_archive(tmp_path, "incendios_2019", MODERN_FEATURES)
    write_archive(tmp_path, "incendios_2021", DUPLICATE_FEATURES)
    write_archive(tmp_path, "incendios_2023", NEWEST_FEATURES)
    return tmp_path


@pytest.fixture
def modern_only(tmp_path):
    write_archive(tmp_path, "incendios_2019", MODERN_FEATURES)
    return tmp_path


@pytest.fixture
def args(archives, connection_arguments):
    return app.parse_arguments(["--directory", str(archives), *connection_arguments])


@pytest.fixture
def imported(database, boundaries, time_zones, args):
    """All four layers imported into a world that has both a country and zones."""
    engine, _ = database
    count = app.import_wildfires(args, engine, logger)
    return engine, count


def fire(session: Session, fire_code: str) -> ConaforWildfire:
    return session.scalar(
        select(ConaforWildfire).where(ConaforWildfire.fire_code == fire_code))


# --------------------------------------------------------------------------
# Arguments (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_a_directory_and_an_archive_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", "dir", "-s", "incendios_2023_shp.zip"])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-s", "incendios_2023_shp.zip"])
    assert parsed.staging_table == app.DEFAULT_STAGING_TABLE
    assert parsed.keep_staging is False
    assert parsed.replace is False


def test_the_archives_of_a_directory_are_found_in_year_order(tmp_path):
    for layer in ("incendios_2021", "incendios_2010", "incendios_2023", "incendios_2016"):
        (tmp_path / f"{layer}_shp.zip").touch()
    (tmp_path / "estadisticas.csv").touch()

    found = app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))
    assert [path.name for path in found] == [
        "incendios_2010_shp.zip", "incendios_2016_shp.zip",
        "incendios_2021_shp.zip", "incendios_2023_shp.zip",
    ]
    assert not any("csv" in path.name for path in found)


def test_an_empty_directory_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="no .zip or .shp"):
        app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))


# --------------------------------------------------------------------------
# The year, which comes from the file name
# --------------------------------------------------------------------------

@pytest.mark.parametrize("layer,expected", [
    ("incendios_2023", 2023), ("incendios_2010", 2010), ("Incendios_2016", 2016),
])
def test_the_year_is_read_from_the_layer_name(layer, expected):
    assert app.layer_year(layer) == expected


def test_a_layer_with_no_year_in_its_name_is_refused():
    """Only three of the thirteen layers publish ANO, so the name is all there is."""
    with pytest.raises(RuntimeError, match="no four-digit year"):
        app.layer_year("incendios")


def test_a_layer_with_two_years_in_its_name_is_refused():
    with pytest.raises(RuntimeError, match="cannot tell which"):
        app.layer_year("incendios_2019_2020")


# --------------------------------------------------------------------------
# The vocabulary tables the SQL depends on
# --------------------------------------------------------------------------

def test_every_null_token_is_unaccented_ascii():
    """The SQL fold is lower+trim only, so an accented token would never match.

    This is the assertion the comment on MISSING_VALUES_SQL leans on: if one is
    ever added with an accent, the import stops silently storing it as data here
    rather than in production.
    """
    for token in mexico_conafor.MISSING_VALUES:
        assert token.isascii(), token
        assert mexico_conafor.normalise(token) == token, token


# --------------------------------------------------------------------------
# Integration: what came out
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_all_four_layers_import(imported):
    engine, count = imported
    # 8 modern + 4 historical + 4 of the 6 duplicated + 4 newest.
    assert count == 20
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConaforWildfire)) == 20
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 20


@needs_ogr2ogr
def test_the_ordinary_fire_arrives_whole(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-01-0102")
        assert stored.year == 2019
        assert stored.source_layer == "incendios_2019"
        assert stored.state_code == 1
        assert stored.state_name == "Aguascalientes"
        assert stored.municipality_code == 2
        assert stored.municipality_name == "Asientos"
        assert stored.property_name == "Tanque Juarez"
        assert stored.fire_type == "Superficial"
        assert stored.impact_level == "Impacto Minimo"
        assert stored.vegetation_type == "Bosque de Pino-Encino - BPQ"
        assert stored.vegetation_type_code == "BPQ"
        assert stored.area_ha == pytest.approx(8.53)
        assert stored.area_ha_herbaceous == pytest.approx(7.25)
        assert stored.date_time_precision == mexico_conafor.PRECISION_DAY


@needs_ogr2ogr
def test_the_state_code_comes_from_the_key_not_the_name(imported):
    """It agrees with the published name in all but one of 45,914 rows; the names
    themselves do not agree with each other."""
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "19-02-0001").state_code == 2
        assert fire(session, "19-20-0140").state_code == 20
        assert fire(session, "23-31-0001").state_code == 31


@needs_ogr2ogr
def test_the_zone_is_resolved_per_fire(imported):
    """Two zones two hours apart, so a national default would be caught here."""
    engine, _ = imported
    with Session(engine) as session:
        central = fire(session, "19-01-0102")
        pacific = fire(session, "19-02-0001")
        assert central.time_zone == "America/Mexico_City"
        assert pacific.time_zone == "America/Tijuana"
        # The same published date, two hours apart as instants.
        assert central.start_date_time == datetime.datetime(2019, 6, 7, 5, tzinfo=UTC)
        assert pacific.start_date_time == datetime.datetime(2019, 6, 7, 7, tzinfo=UTC)


@needs_ogr2ogr
def test_the_local_reading_is_midnight_whatever_the_zone(imported):
    """No layer publishes a time, so every fire starts at local midnight."""
    engine, _ = imported
    with Session(engine) as session:
        locals_ = session.execute(
            select(ConaforWildfire.fire_code,
                   func.timezone(Wildfire.time_zone, Wildfire.start_date_time))
            .where(Wildfire.time_zone.is_not(None))).all()
        assert locals_
        assert all(local.time() == datetime.time(0, 0) for _, local in locals_)


@needs_ogr2ogr
def test_the_end_is_the_last_second_of_its_day(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-01-0102")
        local_end = session.scalar(
            select(func.timezone(Wildfire.time_zone, Wildfire.end_date_time))
            .where(Wildfire.id == stored.id))
        assert local_end == datetime.datetime(2019, 6, 8, 23, 59, 59)


@needs_ogr2ogr
def test_the_country_is_resolved_from_the_perimeter(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "19-01-0102").admin_boundary.name == "Mexico"


@needs_ogr2ogr
def test_a_fire_outside_every_boundary_keeps_everything_else(imported):
    """The Pacific one: no country, no zone, and still a fire."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-26-0001")
        assert stored.admin_boundary_id is None
        assert stored.time_zone is None
        assert stored.perimeter is not None
        # Dated against the fallback zone rather than not dated at all.
        assert stored.start_date_time == datetime.datetime(2019, 6, 7, 5, tzinfo=UTC)


# --------------------------------------------------------------------------
# The schema that changes every year
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_2012_layer_reads_through_its_own_field_names(imported):
    """CLAVE, TOTAL, ARB_ADUL, TIP_VEG, TIPO_INC, CAUSA_ESPE — none of them shared."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "12-01-0012")
        assert stored.year == 2012
        assert stored.area_ha == pytest.approx(64.0)
        assert stored.area_ha_tree == pytest.approx(0.64)
        assert stored.area_ha_herbaceous == pytest.approx(25.6)
        assert stored.area_ha_organic_soil == pytest.approx(2.56)
        assert stored.vegetation_type == "Bosque de Encino"
        assert stored.fire_type == "Mixto"
        assert stored.cause.specific_cause == "Fogatas de paseantes"


@needs_ogr2ogr
def test_what_the_2012_layer_does_not_publish_is_null(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "12-01-0012")
        assert stored.impact_level is None
        assert stored.protected_area_name is None
        assert stored.area_ha_protected is None
        assert stored.municipality_code is None
        assert stored.perimeter_source is None


@needs_ogr2ogr
def test_the_2023_layer_has_a_total_and_no_strata(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "23-01-0001")
        assert stored.area_ha == pytest.approx(3.41)
        assert stored.area_ha_tree is None
        assert stored.area_ha_shrub is None
        assert stored.area_ha_organic_soil is None
        assert stored.property_name is None


@needs_ogr2ogr
def test_only_the_2023_layer_says_how_its_perimeter_was_drawn(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "23-01-0001").perimeter_source == "IMAGEN"
        assert fire(session, "23-29-0003").perimeter_source == "COORD"
        assert fire(session, "19-01-0102").perimeter_source is None
        # An empty POLIGONO is a null token, not the string ''.
        assert fire(session, "23-31-0001").perimeter_source is None


# --------------------------------------------------------------------------
# The null tokens
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_null_tokens_become_null(imported):
    """'N/A', '0', 'Sin nombre' and '' all mean nothing here, in different years."""
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "19-01-0102").protected_area_name is None   # 'N/A'
        assert fire(session, "23-29-0003").protected_area_name is None   # '0'
        assert fire(session, "12-12-0001").vegetation_type is None       # '0'
        assert fire(session, "12-14-0001").cause.specific_cause is None  # '0'


@needs_ogr2ogr
def test_a_real_protected_area_survives(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-02-0001")
        assert stored.protected_area_name == "Sierra de San Pedro Martir"
        assert stored.area_ha_protected == pytest.approx(12.5)


@needs_ogr2ogr
def test_a_zero_hectare_measurement_is_not_a_null_token(imported):
    """'0' means nothing-here in a name column and zero hectares in a number one."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-01-0102")
        assert stored.protected_area_name is None
        assert stored.area_ha_protected == 0.0
        assert stored.area_ha_tree == 0.0


# --------------------------------------------------------------------------
# The causes
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_cause_is_reconciled_and_translated(imported):
    engine, _ = imported
    with Session(engine) as session:
        cause = fire(session, "19-01-0102").cause
        assert cause.cause == "Fogatas"
        assert cause.cause_normalised == "Fogatas"
        assert cause.cause_en == "Campfires"
        assert cause.specific_cause_en == "Campfires of day trippers"


@needs_ogr2ogr
def test_two_spellings_of_one_cause_share_a_canonical_form(imported):
    """'Fogatas' and 'fogatas' are two catalogue rows and one cause."""
    engine, _ = imported
    with Session(engine) as session:
        published = {fire(session, "19-01-0102").cause.cause,
                     fire(session, "19-20-0140").cause.cause}
        canonical = {fire(session, "19-01-0102").cause.cause_normalised,
                     fire(session, "19-20-0140").cause.cause_normalised}
        assert published == {"Fogatas", "fogatas"}
        assert canonical == {"Fogatas"}


@needs_ogr2ogr
def test_the_2011_wording_reconciles_to_the_later_one(imported):
    """'Tormenta Electrica' is what later layers call 'Naturales'."""
    engine, _ = imported
    with Session(engine) as session:
        electrical = fire(session, "19-08-0001").cause
        natural = fire(session, "21-20-0140").cause
        assert electrical.cause == "Tormenta Electrica"
        assert electrical.cause_normalised == natural.cause_normalised == "Naturales"
        assert electrical.cause_en == "Natural"


@needs_ogr2ogr
def test_a_cause_no_table_has_seen_is_stored_unreconciled(imported):
    """Refusing it would drop a fire; storing it unreconciled is recoverable."""
    engine, _ = imported
    with Session(engine) as session:
        cause = fire(session, "19-14-0001").cause
        assert cause.cause == "Drones recreativos"
        assert cause.cause_normalised is None
        assert cause.cause_en is None


@needs_ogr2ogr
def test_a_cause_with_no_specific_cause_is_one_catalogue_row(imported):
    """The 2021 and 2023 layers publish no CAUSAESP at all."""
    engine, _ = imported
    with Session(engine) as session:
        cause = fire(session, "23-01-0001").cause
        assert cause.cause == "Intencional"
        assert cause.specific_cause is None


@needs_ogr2ogr
def test_the_catalogue_is_not_duplicated_across_layers(imported):
    """The same (cause, specific_cause) pair in two layers is one row.

    And the NULL half really is deduplicated, which a plain UNIQUE could not do:
    'Intencional' with no specific cause arrives from both 2021 and 2023.
    """
    engine, _ = imported
    with Session(engine) as session:
        rows = session.scalars(
            select(ConaforFireCause)
            .where(ConaforFireCause.cause == "Intencional")).all()
        by_specific = [row.specific_cause for row in rows]
        assert len(by_specific) == len(set(by_specific))
        assert None in by_specific


@needs_ogr2ogr
def test_a_published_trailing_newline_survives_into_the_catalogue(imported):
    """It is in the file. The canonical form beside it is what a query groups by."""
    engine, _ = imported
    with Session(engine) as session:
        cause = fire(session, "23-29-0003").cause
        assert cause.cause == "Fogatas\n"
        assert cause.cause_normalised == "Fogatas"


# --------------------------------------------------------------------------
# The dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_an_unreadable_end_date_becomes_null(imported):
    """'22/12/202' is a three-digit year and '22/20/2021' a twentieth month.

    Both are in the published 2021 archive, and both are the reason the parse
    happens in Python: to_date would have returned a plausible wrong answer.
    """
    engine, _ = imported
    with Session(engine) as session:
        for code in ("21-19-0051", "21-21-0082"):
            stored = fire(session, code)
            assert stored.end_date_time is None
            assert stored.start_date_time is not None
            assert stored.date_time_precision == mexico_conafor.PRECISION_DAY


@needs_ogr2ogr
def test_a_month_first_date_is_still_read(imported):
    """'01/15/2023': no day-first reading exists, so the fallback is unambiguous."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "23-29-0003")
        local = session.scalar(
            select(func.timezone(Wildfire.time_zone, Wildfire.start_date_time))
            .where(Wildfire.id == stored.id))
        assert local == datetime.datetime(2023, 1, 15, 0, 0)


@needs_ogr2ogr
def test_a_fire_with_no_readable_start_is_dated_to_its_year(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "23-31-0001")
        assert stored.date_time_precision == mexico_conafor.PRECISION_YEAR
        local = session.scalar(
            select(func.timezone(Wildfire.time_zone, Wildfire.start_date_time))
            .where(Wildfire.id == stored.id))
        assert local == datetime.datetime(2023, 1, 1, 0, 0)


@needs_ogr2ogr
def test_an_end_before_its_start_is_stored_as_published(imported):
    """Sixteen published rows have one; it is the provider's data, not an error."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "12-12-0001")
        assert stored.end_date_time < stored.start_date_time


# --------------------------------------------------------------------------
# The geometry
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_perimeter_is_stored_as_a_multipolygon_in_4326(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-01-0102")
        kind, srid = session.execute(
            select(func.ST_GeometryType(Wildfire.perimeter), func.ST_SRID(Wildfire.perimeter))
            .where(Wildfire.id == stored.id)).one()
        assert kind == "ST_MultiPolygon"
        assert srid == 4326


@needs_ogr2ogr
def test_an_invalid_polygon_is_repaired_rather_than_dropped(imported):
    """145 of the 45,914 published polygons self-intersect."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "19-16-0001")
        assert stored is not None
        valid, area = session.execute(
            select(func.ST_IsValid(Wildfire.perimeter), func.ST_Area(Wildfire.perimeter))
            .where(Wildfire.id == stored.id)).one()
        assert valid is True
        assert area > 0


@needs_ogr2ogr
def test_a_feature_with_no_burnt_area_is_still_imported(imported):
    """The shape of 21-24-0078, the one published fire with an empty AREA_HA.

    Everything else is there, polygon included, so dropping it over one empty
    field would lose a real fire. The area is recoverable from the geometry; the
    column means *what CONAFOR reported*, and CONAFOR reported nothing.
    """
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "23-24-0078")
        assert stored is not None
        assert stored.area_ha is None
        assert stored.perimeter is not None
        assert stored.municipality_name == "San Luis Potosi"
        assert stored.area_ha_protected == pytest.approx(6.41)


@needs_ogr2ogr
def test_a_feature_with_no_geometry_is_still_imported(imported):
    """Nine of the real 2012 features carry attributes and an empty shape.

    A fire with a key, a date and an area is still a fire, which is what the
    model's nullable perimeter is for. It simply resolves no zone and no country.
    """
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "12-14-0001")
        assert stored is not None
        assert stored.perimeter is None
        assert stored.admin_boundary_id is None
        assert stored.time_zone is None
        assert stored.area_ha == pytest.approx(2.0)


# --------------------------------------------------------------------------
# The duplicates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_duplicate_features_are_dropped(imported):
    """Six features, four fires: two pairs are exact duplicates."""
    engine, _ = imported
    with Session(engine) as session:
        stored = session.scalars(
            select(ConaforWildfire)
            .where(ConaforWildfire.source_layer == "incendios_2021")).all()
        assert len(stored) == 4
        assert len({row.fire_code for row in stored}) == 4


@needs_ogr2ogr
def test_the_copy_that_kept_its_dates_is_the_one_stored(imported):
    """The second copy of each Guerrero row has its dates blanked; it must lose."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "21-12-0195")
        assert stored.date_time_precision == mexico_conafor.PRECISION_DAY
        local = session.scalar(
            select(func.timezone(Wildfire.time_zone, Wildfire.start_date_time))
            .where(Wildfire.id == stored.id))
        assert local == datetime.datetime(2021, 4, 20, 0, 0)


# --------------------------------------------------------------------------
# Re-running
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_skips_a_layer_already_in(database, boundaries, time_zones, args):
    engine, _ = database
    first = app.import_wildfires(args, engine, logger)
    second = app.import_wildfires(args, engine, logger)

    assert first == 20
    assert second == 0
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConaforWildfire)) == 20


@needs_ogr2ogr
def test_replace_reloads_a_layer_without_doubling_it(database, boundaries, time_zones,
                                                     archives, connection_arguments):
    engine, _ = database
    first = app.parse_arguments(["--directory", str(archives), *connection_arguments])
    app.import_wildfires(first, engine, logger)

    again = app.parse_arguments(["--directory", str(archives), "--replace",
                                 *connection_arguments])
    app.import_wildfires(again, engine, logger)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConaforWildfire)) == 20
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 20


@needs_ogr2ogr
def test_a_single_archive_may_be_imported_on_its_own(database, boundaries, time_zones,
                                                     modern_only, connection_arguments):
    engine, _ = database
    archive = modern_only / "incendios_2019_shp.zip"
    parsed = app.parse_arguments(["-s", str(archive), *connection_arguments])

    assert app.import_wildfires(parsed, engine, logger) == 8


@needs_ogr2ogr
def test_the_staging_table_is_dropped_afterwards(imported, args):
    engine, _ = imported
    with Session(engine) as session:
        exists = session.scalar(text(
            "SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"{args.staging_schema}.{args.staging_table}"})
    assert exists is False


# --------------------------------------------------------------------------
# The year check
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_misnamed_archive_is_refused_before_anything_is_written(
        database, boundaries, time_zones, tmp_path, connection_arguments):
    """The year is what an import replaces, so a wrong one replaces the wrong fires.

    The layer is named 2020 and its keys all begin ``19-``, which is what a
    mis-downloaded or re-labelled archive looks like.
    """
    engine, _ = database
    write_archive(tmp_path, "incendios_2020", MODERN_FEATURES)
    parsed = app.parse_arguments(["-d", str(tmp_path), *connection_arguments])

    with pytest.raises(RuntimeError, match="Refusing to import"):
        app.import_wildfires(parsed, engine, logger)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConaforWildfire)) == 0


@needs_ogr2ogr
def test_a_failing_layer_does_not_lose_the_layers_before_it(
        database, boundaries, time_zones, tmp_path, connection_arguments):
    """One transaction per archive, so an interrupted run keeps what it finished.

    2019 imports; the second archive is labelled 2022 and holds 2021's keys, so it
    is refused — and the eight fires of the first are still there.
    """
    engine, _ = database
    write_archive(tmp_path, "incendios_2019", MODERN_FEATURES)
    write_archive(tmp_path, "incendios_2022", DUPLICATE_FEATURES)
    parsed = app.parse_arguments(["-d", str(tmp_path), *connection_arguments])

    with pytest.raises(RuntimeError):
        app.import_wildfires(parsed, engine, logger)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConaforWildfire)) == 8


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------

def test_a_missing_source_is_reported_not_raised(tmp_path):
    assert app.main(["-d", str(tmp_path / "nowhere")]) == 1


def test_a_missing_ogr2ogr_is_reported_not_raised(tmp_path):
    assert app.main(["-d", str(tmp_path), "--ogr2ogr", "definitely-not-a-binary"]) == 1
