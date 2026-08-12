#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF seasonal report import (Chile).

The integration tests run the real ``ogr2ogr`` against a real (ephemeral) PostgreSQL
and real shapefiles, so the whole path is exercised — the subprocess, the ``.prj``,
the reprojection, the staging table and the one big ``TRANSFORM_SQL``. A mocked
``ogr2ogr`` would test none of the things that actually go wrong with this archive.

The fixture layers are built from GeoJSON rather than checked in as binaries, and
they are built the way CONAF publishes them:

* coordinates in UTM metres, with a ``.prj`` holding **the published ESRI string**
  verbatim — the 19S one for the mainland, the 12S one for Rapa Nui, and the bare
  geographic one that ``if_temporada_2024_2025`` really ships;
* ``NUMERO_REG`` as a **Real** field, and ``UTM_E`` as the string ``'317709 E'``,
  because those are the shapes that break a naive reader;
* column names under the spellings that season uses — ``INICIO_IN`` in one layer and
  ``FH_INICIO`` in another, ``PINO_0_10`` against ``PINO_00_10`` — and whole columns
  simply absent, which is the normal state of this archive rather than an error;
* the dirt: a bare cause code with no name, a zeroed coordinate pair, a season cell
  reading ``'2023-2025'``, subtotals that do not add up, and a record with binary in
  its text.

Three layers, chosen for what each carries. 2016-2017 is the awkward one: no dates
at all, bare cause codes, zeroed coordinates. 2023-2024 is the modern one: real
instants, the suffixed coordinate text, the post-2023 cause numbering, a región code
published as a float. And the Easter Island layer is there because the second grid
has to survive the trip.
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

from src.apps.imports.wildfires.chile_conaf import archives as archive_readers
from src.apps.imports.wildfires.chile_conaf import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import chile_conaf
from src.providers import ocha
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire

UTC = datetime.timezone.utc

#: Chile, near enough for a fixture: a box that contains the mainland and Rapa Nui.
CHILE = "MULTIPOLYGON(((-110 -56, -66 -56, -66 -17, -110 -17, -110 -56)))"

#: The published ``.prj`` of a mainland layer, verbatim from
#: ``if_temporada_2023_2024.prj``. An ESRI dialect naming ``WGS_1984_UTM_Zone_19S``
#: with **no authority code**, which is what :func:`archives.archive_grid` has to
#: recognise by its name rather than by an EPSG number.
PRJ_19S = (
    'PROJCS["WGS_1984_UTM_Zone_19S",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],'
    'UNIT["Degree",0.017453292519943295]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-69],'
    'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",10000000],UNIT["Meter",1]]'
)

#: The published ``.prj`` of an Easter Island layer, verbatim from
#: ``if_isla_pascua_2023_2024.prj``.
PRJ_12S = PRJ_19S.replace("Zone_19S", "Zone_12S").replace(
    '"central_meridian",-69', '"central_meridian",-111')

#: The published ``.prj`` of ``if_temporada_2024_2025``, which carries **no
#: projection at all** — a mainland season shipped in bare geographic WGS 84.
PRJ_GEOGRAPHIC = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
    '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-conaf-import")


# --------------------------------------------------------------------------
# The fixture archives
# --------------------------------------------------------------------------

def point(x: float, y: float) -> list:
    return [x, y]


#: ``if_temporada_2016_2017``: the awkward season.
#:
#: Publishes the cause as a **bare code** and no name, no start or end date at all,
#: and a zeroed ``UTM_E``/``UTM_N`` on every row. Its ``NUMERO_REG`` is a Real, its
#: ``NOM_INCEN`` is spelled ``NOMBRE``, and its pine column is ``PINO_0_10``.
FEATURES_2016 = [
    # An ordinary fire, whose bare '01.07' has to resolve through the *pre*-2023
    # numbering to Tránsito de personas.
    ({"TEMPORADA": "2016-2017", "NUMERO_RE": 402.0, "NOMBRE": "SAN GUILLERMO",
      "AMBITO": "Conaf", "COMUNA": "TOME", "CODREG": "08", "CODPROV": "081",
      "CODCOM": "08111", "UTM_E": "0", "UTM_N": "0", "HUSO": None,
      "INICIO_C": "Camino principal", "COMBUS_I": "Pastizal",
      "CAUSA_GENE": "01.07", "CAUSA_ESPE": "1.7.1.",
      "PINO_0_10": 1.0, "PINO_11_17": 2.0, "PINO18_MAS": 3.0, "EUCALIPTO": 4.0,
      "OTRAS_PLAN": 5.0, "TOTAL_PLAN": 15.0, "ARBOLADO": 6.0, "MATORRAL": 7.0,
      "PASTIZAL": 8.0, "TOTAL_VEG": 21.0, "AGRICOLA": 9.0, "DESECHOS": 10.0,
      "TOTAL_OTRA": 19.0, "SUPERFICIE": 55.0},
     point(670000, 5920000)),
    # '04.01' — *incendios de causa desconocida* in this decade, *faenas forestales*
    # in the next one. The whole reason the scheme is settled before the cause.
    ({"TEMPORADA": "2016-2017", "NUMERO_RE": 0.0, "NOMBRE": "EL MANZANO",
      "AMBITO": "Empresa", "COMUNA": "TOME", "CODREG": "08", "CODPROV": "081",
      "CODCOM": "08111", "UTM_E": "0", "UTM_N": "0", "HUSO": None,
      "INICIO_C": "Sendero", "COMBUS_I": "Matorral",
      "CAUSA_GENE": "04.01", "CAUSA_ESPE": None,
      "PINO_0_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 0.0, "ARBOLADO": 0.0, "MATORRAL": 2.5,
      "PASTIZAL": 0.0, "TOTAL_VEG": 2.5, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 2.5},
     point(671000, 5921000)),
    # Subtotals that do not sum to the published total: 5,703 rows are like this.
    ({"TEMPORADA": "2016-2017", "NUMERO_RE": 12.0, "NOMBRE": "LA POLVORA",
      "AMBITO": "Conaf", "COMUNA": "TOME", "CODREG": "08", "CODPROV": "081",
      "CODCOM": "08111", "UTM_E": "0", "UTM_N": "0", "HUSO": None,
      "INICIO_C": None, "COMBUS_I": None,
      "CAUSA_GENE": "02.01", "CAUSA_ESPE": "2.1.11.",
      "PINO_0_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 1.0, "ARBOLADO": 0.0, "MATORRAL": 0.0,
      "PASTIZAL": 1.0, "TOTAL_VEG": 1.0, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 99.0},
     point(672000, 5922000)),
    # A corrupt DBF read: three records of if_temporada_2010_2011 are like this, and
    # one of them carries a plausible-looking cause that must not reach the catalogue.
    ({"TEMPORADA": "2016-2017", "NUMERO_RE": 3.0, "NOMBRE": "?2\x0bI??k\x15??",
      "AMBITO": "Conaf", "COMUNA": "?\x0by\x10?g", "CODREG": "08", "CODPROV": "081",
      "CODCOM": "08111", "UTM_E": "0", "UTM_N": "0", "HUSO": None,
      "INICIO_C": None, "COMBUS_I": None,
      "CAUSA_GENE": "PASTIZAL", "CAUSA_ESPE": None,
      "PINO_0_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 0.0, "ARBOLADO": 0.0, "MATORRAL": 0.0,
      "PASTIZAL": 0.0, "TOTAL_VEG": 0.0, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 0.0},
     point(673000, 5923000)),
]

#: ``if_temporada_2023_2024``: the modern season.
#:
#: Real instants in the Spanish-abbreviation format, ``UTM_E`` as the suffixed text
#: ``'317709 E'``, a ``CODREG`` published as a float, and the post-2023 cause
#: numbering — including the ``'4.1'`` that means the opposite of 2016-2017's.
FEATURES_2023 = [
    ({"TEMPORADA": "2023-2024", "NUMERO_REG": 1101.0, "NOM_INCEN": "LOS MAITENES",
      "N_MBITO": "Conaf", "REGION": "Biobío", "PROVINCIA": "Concepción",
      "COMUNA": "Tomé", "CODREG": "6.00000000000", "CODPROV": "081",
      "CODCOM": "08111", "UTM_E": "317709 E", "UTM_N": "6350587 S", "HUSO": "19H",
      "INICIO_C": "Camino secundario", "COMBUS_I": "Matorral",
      "CAUSA_GENE": "4.1 - Faenas forestales",
      "CAUSA_ESPE": "4.1.1 - Uso de fuego en faena forestal",
      "FH_INICIO": "18-ene-2024 15:50", "FH_EXTINCI": "20-ene-2024 09:00",
      "PINO_00_10": 1.5, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 1.5, "ARBOLADO": 0.0, "MATORRAL": 3.5,
      "PASTIZAL": 0.0, "TOTAL_VEG": 3.5, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 5.0},
     point(317709, 6350587)),
    # A date with no time of day, which the day precision is for.
    ({"TEMPORADA": "2023-2024", "NUMERO_REG": 1102.0, "NOM_INCEN": "CERRO VIEJO",
      "N_MBITO": "Empresa", "REGION": "Biobío", "PROVINCIA": "Concepción",
      "COMUNA": "Tomé", "CODREG": "08", "CODPROV": "081", "CODCOM": "08111",
      "UTM_E": "318000 E", "UTM_N": "6351000 S", "HUSO": "19",
      "INICIO_C": None, "COMBUS_I": "Pastizal",
      "CAUSA_GENE": "2.1 - Incendios intencionales", "CAUSA_ESPE": None,
      "FH_INICIO": "2024/02/07", "FH_EXTINCI": None,
      "PINO_00_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 0.0, "ARBOLADO": 0.0, "MATORRAL": 0.0,
      "PASTIZAL": 4.0, "TOTAL_VEG": 4.0, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 4.0},
     point(318000, 6351000)),
    # A season cell that is not a season: one perimeter really publishes '2023-2025'.
    ({"TEMPORADA": "2023-2025", "NUMERO_REG": 1103.0, "NOM_INCEN": "QUEBRADILLA",
      "N_MBITO": "Conaf", "REGION": "Biobío", "PROVINCIA": "Concepción",
      "COMUNA": "Tomé", "CODREG": "08", "CODPROV": "081", "CODCOM": "08111",
      "UTM_E": "319000 E", "UTM_N": "6352000 S", "HUSO": "19H",
      "INICIO_C": None, "COMBUS_I": None,
      "CAUSA_GENE": None, "CAUSA_ESPE": None,
      "FH_INICIO": "6-abr-2024  11:51", "FH_EXTINCI": "5-abr-2024 08:00",
      "PINO_00_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 0.0, "ARBOLADO": 1.0, "MATORRAL": 0.0,
      "PASTIZAL": 0.0, "TOTAL_VEG": 1.0, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 1.0},
     point(319000, 6352000)),
]

#: ``if_isla_pascua_2023_2024``: Rapa Nui, on the other grid.
#:
#: Publishes no ``REGION``, ``PROVINCIA``, ``COMUNA`` or ``HUSO`` at all — which is
#: normal for these archives and must not stop the import — and a day-month-year
#: date, which is the fourth published format.
FEATURES_EASTER = [
    ({"TEMPORADA": "2023-2024", "NUMERO_REG": 4.0, "NOM_INCEN": "VAITEA",
      "AMBITO": "Conaf", "CODREG": "05", "UTM_E": "654520", "UTM_N": "6994384",
      "INICIO_C": None, "COMBUS_I": "Pastizal",
      "CAUSA_GENE": "1.7. Tránsito de personas, vehículos o aeronaves",
      "CAUSA_ESPE": "1.7.1. Uso de fuego por transeúntes",
      "FH_INICIO": "08-09-2023 12:10", "FH_EXTINCI": None,
      "PINO_00_10": 0.0, "PINO_11_17": 0.0, "PINO18_MAS": 0.0, "EUCALIPTO": 0.0,
      "OTRAS_PLAN": 0.0, "TOTAL_PLAN": 0.0, "ARBOLADO": 0.0, "MATORRAL": 0.0,
      "PASTIZAL": 12.0, "TOTAL_VEG": 12.0, "AGRICOLA": 0.0, "DESECHOS": 0.0,
      "TOTAL_OTRA": 0.0, "SUPERFICIE": 12.0},
     point(654520, 6994384)),
]

LAYERS = [
    ("if_temporada_2016_2017", FEATURES_2016, 32719, PRJ_19S),
    ("if_temporada_2023_2024", FEATURES_2023, 32719, PRJ_19S),
    ("if_isla_pascua_2023_2024", FEATURES_EASTER, 32712, PRJ_12S),
]


def write_layer(directory: Path, layer: str, features: list, srid: int,
                projection: str) -> Path:
    """Build one archive's shapefile, the way CONAF publishes it.

    ``-a_srs`` *assigns* the CRS rather than reprojecting — the coordinates are
    already UTM metres — and the ``.prj`` GDAL writes is then **overwritten with the
    published ESRI string**, which is what the import has to read the grid out of.
    """
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": values,
             "geometry": {"type": "Point", "coordinates": coordinates}}
            for values, coordinates in features
        ],
    }
    source = directory / f"source_{layer}.geojson"
    source.write_text(json.dumps(collection), encoding="utf-8")

    target = directory / f"{layer}.shp"
    subprocess.run(
        ["ogr2ogr", "-f", "ESRI Shapefile", str(target), str(source),
         "-a_srs", f"EPSG:{srid}", "-nln", layer, "-lco", "ENCODING=UTF-8"],
        check=True, capture_output=True,
    )
    (directory / f"{layer}.prj").write_text(projection, encoding="utf-8")
    source.unlink()
    return target


@pytest.fixture
def archives(tmp_path) -> Path:
    """A directory holding the three fixture archives, unpacked."""
    directory = tmp_path / "xile"
    directory.mkdir()
    for layer, features, srid, projection in LAYERS:
        write_layer(directory, layer, features, srid, projection)
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
    """The OCHA provider, a Chile-shaped boundary and a zone to resolve against."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="CHL",
                                  name="Chile", name_en="Chile", level=0,
                                  geometry=f"SRID=4326;{CHILE}"))
        session.add(TimeZone(name=chile_conaf.DEFAULT_TIME_ZONE,
                             geometry=f"SRID=4326;{CHILE}"))
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


def stored(engine, model=ConafWildfire):
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def by_name(engine) -> dict:
    return {row.name: row for row in stored(engine)}


def cause_of(engine, name: str) -> ConafFireCause:
    """The classification of the fire called ``name``, loaded inside a session."""
    with Session(engine) as session:
        fire = session.scalar(select(ConafWildfire).where(ConafWildfire.name == name))
        return fire.cause


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# Reading the grid out of the .prj
# --------------------------------------------------------------------------

def test_a_mainland_prj_is_read_as_the_mainland_grid(tmp_path):
    shapefile = tmp_path / "if_temporada_2023_2024.shp"
    shapefile.with_suffix(".prj").write_text(PRJ_19S, encoding="utf-8")

    assert archive_readers.archive_grid(shapefile, logger) \
        == chile_conaf.SOURCE_SRID_MAINLAND


def test_an_easter_island_prj_is_read_as_the_other_grid(tmp_path):
    """By its ``WGS_1984_UTM_Zone_12S`` name: the published ``.prj`` has no EPSG code."""
    shapefile = tmp_path / "if_isla_pascua_2023_2024.shp"
    shapefile.with_suffix(".prj").write_text(PRJ_12S, encoding="utf-8")

    assert archive_readers.archive_grid(shapefile, logger) \
        == chile_conaf.SOURCE_SRID_EASTER


def test_a_layer_with_no_projection_at_all_is_staged_on_the_mainland_grid(tmp_path):
    """``if_temporada_2024_2025`` ships bare geographic WGS 84 and 6,262 mainland fires.

    Defaulting the other way would put a whole season on the Rapa Nui grid, where the
    extent check would reject it — a good failure, but a worse one than getting it
    right.
    """
    shapefile = tmp_path / "if_temporada_2024_2025.shp"
    shapefile.with_suffix(".prj").write_text(PRJ_GEOGRAPHIC, encoding="utf-8")

    assert archive_readers.archive_grid(shapefile, logger) \
        == chile_conaf.SOURCE_SRID_MAINLAND


def test_a_missing_prj_does_not_stop_the_import(tmp_path):
    shapefile = tmp_path / "if_temporada_2015_2016.shp"

    assert archive_readers.archive_grid(shapefile, logger) \
        == chile_conaf.SOURCE_SRID_MAINLAND


# --------------------------------------------------------------------------
# The season
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stem, expected", [
    ("if_temporada_2010_2011", 2010),
    ("if_magnitud_islapascua_2024_2025", 2024),
    ("if_ip_temporada_2021_2022", 2021),
    ("if_temporada", None),
    ("if_temporada_2010_2012", None),
])
def test_the_archive_name_names_a_season(stem, expected):
    """Used only where a *row's* ``TEMPORADA`` is unreadable, and counted when it is."""
    assert app.archive_season(Path(f"/tmp/{stem}.rar")) == expected


@needs_ogr2ogr
def test_a_row_whose_season_cell_is_not_a_season_falls_back_to_the_archive(
        archives, with_boundaries):
    """``'2023-2025'`` is a typing error, not a two-year fire season.

    Reading its first half would file the fire under 2023-2024 anyway — but silently.
    Falling back to the archive's own season reaches the same row and counts the
    repair.
    """
    engine, url = with_boundaries
    assert run(url, archives / "if_temporada_2023_2024.shp") == 0

    fire = by_name(engine)["QUEBRADILLA"]
    assert fire.season_start_year == 2023
    assert fire.season == "2023-2025", "the published cell is kept as published"


@needs_ogr2ogr
def test_only_the_named_season_is_imported(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "if_temporada_2016_2017.shp",
               archives / "if_temporada_2023_2024.shp", extra=["-y", "2023"]) == 0

    assert {fire.season_start_year for fire in stored(engine)} == {2023}


# --------------------------------------------------------------------------
# The published coordinate
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_mainland_point_lands_on_the_mainland_grid(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    with Session(engine) as session:
        srid, x, y = session.execute(select(
            func.ST_SRID(ConafIgnition.geometry_utm19s),
            func.ST_X(ConafIgnition.geometry_utm19s),
            func.ST_Y(ConafIgnition.geometry_utm19s),
        ).where(ConafIgnition.number == 1101)).one()
    assert srid == chile_conaf.SOURCE_SRID_MAINLAND
    assert (x, y) == pytest.approx((317709.0, 6350587.0))


@needs_ogr2ogr
def test_an_easter_island_point_lands_on_the_other_grid(archives, with_boundaries):
    """243 fires in the real archive, and the reason the second column exists."""
    engine, url = with_boundaries
    run(url, archives / "if_isla_pascua_2023_2024.shp")

    with Session(engine) as session:
        ignition = session.scalar(select(ConafIgnition))
        srid = session.scalar(select(func.ST_SRID(ConafIgnition.geometry_utm12s)))
    assert ignition.geometry_utm19s is None
    assert srid == chile_conaf.SOURCE_SRID_EASTER


@needs_ogr2ogr
def test_every_point_is_reprojected_to_4326_as_well(archives, with_boundaries):
    """The parent's point is what a cross-provider query uses; the grid ones are the
    originals."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp",
        archives / "if_isla_pascua_2023_2024.shp")

    with Session(engine) as session:
        srids = set(session.scalars(select(func.ST_SRID(ConafIgnition.geometry))).all())
    assert srids == {4326}


@needs_ogr2ogr
def test_the_suffixed_coordinate_text_is_read_as_numbers(archives, with_boundaries):
    """2023-2024 publishes ``UTM_E`` as ``'317709 E'``, which is not a number yet.

    Casting the column would have lost the row rather than the suffix, which is why
    the staging type is ``text`` and the reading is done in SQL.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    with Session(engine) as session:
        ignition = session.scalar(
            select(ConafIgnition).where(ConafIgnition.number == 1101))
    assert float(ignition.utm_easting) == pytest.approx(317709.0)
    assert float(ignition.utm_northing) == pytest.approx(6350587.0)
    assert (ignition.utm_zone, ignition.utm_band) == (19, "H")


@needs_ogr2ogr
def test_a_zeroed_coordinate_pair_is_unpublished_rather_than_a_point(
        archives, with_boundaries):
    """2013-2014 writes ``(0, 0)`` on all 6,297 of its rows.

    Easting zero is 500 km west of the zone's central meridian, in the Pacific.
    Reading it as a number would put a whole season's provenance columns out to sea —
    and the geometry, which is the reliable coordinate, is still stored.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    with Session(engine) as session:
        ignition = session.scalar(
            select(ConafIgnition).where(ConafIgnition.number == 402))
    assert ignition.utm_easting is None and ignition.utm_northing is None
    assert ignition.utm_zone is None
    assert ignition.geometry_utm19s is not None


# --------------------------------------------------------------------------
# The dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_published_instant_is_stored_to_the_minute(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    fire = by_name(engine)["LOS MAITENES"]
    assert fire.date_time_precision == chile_conaf.PRECISION_MINUTE
    assert fire.start_date_time.astimezone(UTC) == datetime.datetime(
        2024, 1, 18, 18, 50, tzinfo=UTC), "15:50 in America/Santiago, in summer"
    assert fire.end_date_time is not None


@needs_ogr2ogr
def test_a_published_day_claims_no_time_of_day(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    fire = by_name(engine)["CERRO VIEJO"]
    assert fire.date_time_precision == chile_conaf.PRECISION_DAY
    assert fire.end_date_time is None


@needs_ogr2ogr
def test_the_fourth_date_format_is_read_too(archives, with_boundaries):
    """``08-09-2023 12:10`` is day-month-year: 8 September, not 9 August."""
    engine, url = with_boundaries
    run(url, archives / "if_isla_pascua_2023_2024.shp")

    fire = by_name(engine)["VAITEA"]
    assert fire.date_time_precision == chile_conaf.PRECISION_MINUTE
    assert fire.start_date_time.astimezone(UTC).date() == datetime.date(2023, 9, 8)


@needs_ogr2ogr
def test_a_season_with_no_dates_is_dated_to_1_july_and_says_so(archives,
                                                               with_boundaries):
    """Eight of the fifteen mainland seasons publish no start at all — 49,470 fires.

    Their start is a placeholder. The precision column is the only thing that says
    so, which is why it is ``NOT NULL`` and indexed.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    for fire in stored(engine):
        assert fire.date_time_precision == chile_conaf.PRECISION_SEASON
        started = fire.start_date_time.astimezone(UTC)
        assert (started.year, started.month) == (2016, 7)


@needs_ogr2ogr
def test_an_end_before_its_start_is_stored_as_published(archives, with_boundaries):
    """Swapping them would be inventing a fire that ran the other way."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    fire = by_name(engine)["QUEBRADILLA"]
    assert fire.end_date_time < fire.start_date_time


# --------------------------------------------------------------------------
# The cause
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_bare_code_resolves_in_the_scheme_of_its_own_decade(archives,
                                                              with_boundaries):
    """2016-2017's ``'04.01'`` is *causa desconocida*, nine seasons before the break.

    Resolving it through the post-2023 numbering would file 220 unknown-cause fires
    as forestry work, and would look right.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    cause = cause_of(engine, "EL MANZANO")
    assert cause.cause == "04.01"
    assert cause.cause_code == "4.1"
    assert cause.cause_normalised == "Incendios de causa desconocida"
    assert cause.scheme == "pre_2023"


@needs_ogr2ogr
def test_the_same_code_in_the_later_layer_means_the_other_thing(archives,
                                                                with_boundaries):
    """``4.1`` beside *Faenas forestales* is the post-2023 numbering, and says so."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    cause = cause_of(engine, "LOS MAITENES")
    assert cause.cause_code == "4.1"
    assert cause.cause_normalised == "Faenas forestales"
    assert cause.scheme == "post_2023"


@needs_ogr2ogr
def test_the_two_meanings_of_one_code_are_two_catalogue_rows(archives,
                                                             with_boundaries):
    """Which is the whole argument for storing the published string and the scheme."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp",
        archives / "if_temporada_2023_2024.shp")

    with Session(engine) as session:
        rows = session.scalars(select(ConafFireCause)
                               .where(ConafFireCause.cause_code == "4.1")).all()
    assert {row.cause_normalised for row in rows} \
        == {"Incendios de causa desconocida", "Faenas forestales"}
    assert {row.scheme for row in rows} == {"pre_2023", "post_2023"}


@needs_ogr2ogr
def test_the_catalogue_holds_one_row_per_published_pair(archives, with_boundaries):
    """A lookup table, not a per-fire row."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    # Three surviving fires, three distinct (CAUSA_GENE, CAUSA_ESPE) pairs.
    assert count(engine, "conaf_fire_cause") == 3


@needs_ogr2ogr
def test_a_fire_publishing_neither_half_carries_no_classification(archives,
                                                                  with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    assert by_name(engine)["QUEBRADILLA"].cause_id is None


# --------------------------------------------------------------------------
# The dirt
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_corrupt_record_is_dropped_and_kept_out_of_the_cause_catalogue(
        archives, with_boundaries):
    """Its DBF has come apart, so nothing in it can be trusted.

    Including the parts that still look readable — this one's ``CAUSA_GENE`` is
    ``'PASTIZAL'``, which is a fuel and not a cause, and which would otherwise become
    a permanent entry of garbage in the classification.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    assert count(engine, "conaf_wildfire") == 3, "four features, one corrupt"
    with Session(engine) as session:
        causes = set(session.scalars(select(ConafFireCause.cause)).all())
    assert "PASTIZAL" not in causes


@needs_ogr2ogr
def test_subtotals_that_do_not_add_up_are_stored_and_flagged(archives,
                                                             with_boundaries):
    """Every column is stored as published, drift included.

    ``SUPERFICIE`` is the office's own figure for the fire, and where it disagrees
    with its own components the disagreement is the datum.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    fires = by_name(engine)
    assert fires["LA POLVORA"].area_totals_agree is False
    assert float(fires["LA POLVORA"].area_ha_total) == pytest.approx(99.0)
    assert fires["SAN GUILLERMO"].area_totals_agree is True


@needs_ogr2ogr
def test_the_administrative_code_published_as_a_float_is_padded(archives,
                                                                with_boundaries):
    """2024-2025 publishes its región code as ``'6.00000000000'``.

    Región 06 is O'Higgins, and there is no región 6: the codes are codes and not
    quantities, and unpadded they stop joining to anything.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    assert by_name(engine)["LOS MAITENES"].region_code == "06"


@needs_ogr2ogr
def test_a_layer_that_publishes_no_region_columns_still_imports(archives,
                                                                with_boundaries):
    """``if_isla_pascua_2013_2014`` publishes no REGION, PROVINCIA, COMUNA or HUSO.

    Only the seven signature columns are required; everything else is genuinely
    optional, because CONAF really does publish layers without it.
    """
    engine, url = with_boundaries
    assert run(url, archives / "if_isla_pascua_2023_2024.shp") == 0

    fire = by_name(engine)["VAITEA"]
    assert fire.region is None and fire.province is None
    assert fire.region_code == "05"


@needs_ogr2ogr
def test_the_column_spellings_of_every_season_are_read(archives, with_boundaries):
    """``NOMBRE`` against ``NOM_INCEN``, ``PINO_0_10`` against ``PINO_00_10``.

    The 23 published layers name the same attribute up to four ways; a season the
    alias map misses would import as a season of nulls.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp",
        archives / "if_temporada_2023_2024.shp")

    fires = by_name(engine)
    assert fires["SAN GUILLERMO"].number == 402, "NUMERO_RE, published as a Real"
    assert float(fires["SAN GUILLERMO"].area_ha_pine_0_10) == pytest.approx(1.0)
    assert float(fires["LOS MAITENES"].area_ha_pine_0_10) == pytest.approx(1.5)
    assert fires["SAN GUILLERMO"].reporter == "Conaf", "AMBITO"
    assert fires["CERRO VIEJO"].reporter == "Empresa", "N_MBITO"


@needs_ogr2ogr
def test_a_published_zero_number_is_no_number(archives, with_boundaries):
    """``NUMERO_REG`` is all zeros in 2010-2011 and 2013-2014."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2016_2017.shp")

    assert by_name(engine)["EL MANZANO"].number is None


# --------------------------------------------------------------------------
# What the rows look like when the run is done
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_every_report_gets_a_point_and_never_a_perimeter(archives, with_boundaries):
    """One ``conaf_ignition`` per report, and the polygons are a different product."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    assert count(engine, "conaf_ignition") == count(engine, "conaf_wildfire") == 3
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire.__table__)
                              .where(Wildfire.perimeter.isnot(None))) == 0


@needs_ogr2ogr
def test_a_fire_is_placed_in_its_country_and_time_zone(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    fire = by_name(engine)["LOS MAITENES"]
    assert fire.time_zone == chile_conaf.DEFAULT_TIME_ZONE
    assert fire.admin_boundary_id is not None


@needs_ogr2ogr
def test_the_import_runs_without_boundaries_at_all(archives, database):
    """A country and a zone are an improvement, not a prerequisite.

    Refusing to import without them would make the fire data hostage to a different
    dataset's availability.

    Nothing is invented in the ``time_zone`` column either: it stays ``NULL``, which
    says *no zone was resolved* rather than claiming Santiago. The **instant** is
    still computed against :data:`~src.providers.chile_conaf.DEFAULT_TIME_ZONE`,
    because a timestamp has to be in some zone and Santiago is where all but 243 of
    these fires are.
    """
    engine, url = database
    assert run(url, archives / "if_temporada_2023_2024.shp") == 0

    fire = by_name(engine)["LOS MAITENES"]
    assert fire.admin_boundary_id is None
    assert fire.time_zone is None
    assert fire.start_date_time.astimezone(UTC) == datetime.datetime(
        2024, 1, 18, 18, 50, tzinfo=UTC), "15:50 read in the fallback zone"


# --------------------------------------------------------------------------
# Running it twice
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_importing_a_season_twice_replaces_it(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")
    run(url, archives / "if_temporada_2023_2024.shp")

    assert count(engine, "conaf_wildfire") == 3
    assert count(engine, "conaf_ignition") == 3


@needs_ogr2ogr
def test_reimporting_the_mainland_leaves_easter_island_alone(archives,
                                                             with_boundaries):
    """The two territories are separate archives **for the same season**.

    Deleting by season alone wiped the other territory's half of it — 234 Rapa Nui
    fires and 6,262 mainland ones went missing that way. The delete is scoped to the
    season *and* the grid.
    """
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp",
        archives / "if_isla_pascua_2023_2024.shp")
    assert count(engine, "conaf_wildfire") == 4

    run(url, archives / "if_temporada_2023_2024.shp")
    assert count(engine, "conaf_wildfire") == 4, "Rapa Nui's fire is still there"
    with Session(engine) as session:
        easter = session.scalar(select(func.count()).select_from(
            ConafIgnition.__table__).where(
            ConafIgnition.geometry_utm12s.isnot(None)))
    assert easter == 1


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "if_temporada_2023_2024.shp", extra=["--dry-run"]) == 0

    assert count(engine, "conaf_wildfire") == 0
    assert count(engine, "conaf_ignition") == 0


@needs_ogr2ogr
def test_the_staging_table_is_dropped_when_the_run_ends(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    with Session(engine) as session:
        remaining = session.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'staging' AND table_name = 'conaf_reports'"))
    assert remaining == 0


@needs_ogr2ogr
def test_the_subdivided_lookup_tables_go_with_it(archives, with_boundaries):
    """The pieces the country lookup is made of are staging, and are dropped as such."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp")

    with Session(engine) as session:
        remaining = session.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'staging' AND table_name LIKE '%_parts'"))
    assert remaining == 0


@needs_ogr2ogr
def test_keeping_the_staging_table_keeps_the_lookup_tables_too(archives, with_boundaries):
    """``--keep-staging`` is for looking at what a run did, lookups included."""
    engine, url = with_boundaries
    run(url, archives / "if_temporada_2023_2024.shp", extra=["--keep-staging"])

    assert count(engine, "staging.conaf_reports_boundary_parts") > 0
    assert count(engine, "staging.conaf_reports_time_zone_parts") > 0
