#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CONAF *incendios de magnitud* perimeter import (Chile).

Real ``ogr2ogr``, real shapefiles, real (ephemeral) PostgreSQL, for the reason the
report import's tests give: the things that go wrong with this archive are the
``.prj``, the 3D geometry, the invalid ring and the dissolve, and none of them
survives being mocked.

What is pinned here is mostly the **dissolve**, because it is the one place this
import invents structure the file does not have. There is no ``GID``: a fire mapped
in pieces is published as several features sharing a season and a name, and the
import unions them. Which means the key it dissolves on decides how many fires
exist — and dissolving on the name alone really did merge four pairs of genuinely
different fires, which is why the number is in the key.

Beside it: that ``SUPERFICIE`` is the *polygon's own area* and not a reported burnt
area, so the two are stored as two numbers; that the ``'402 - '`` prefix is split
into a number and a name, because that is the strongest signal the binder has; and
that Rapa Nui's one perimeter lands on the other grid.
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

from src.apps.imports.wildfires.chile_conaf_magnitud import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import chile_conaf
from src.providers import chile_conaf_magnitud
from src.providers import ocha
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf_magnitud.wildfire import ConafMagnitudWildfire

UTC = datetime.timezone.utc

#: Chile, near enough for a fixture: a box that contains the mainland and Rapa Nui.
CHILE = "MULTIPOLYGON(((-110 -56, -66 -56, -66 -17, -110 -17, -110 -56)))"

#: The published ``.prj`` of a mainland layer, verbatim from
#: ``if_magnitud_2023_2024.prj`` — an ESRI dialect naming ``WGS_1984_UTM_Zone_19S``
#: with no authority code, which is what the import reads the grid out of.
PRJ_19S = (
    'PROJCS["WGS_1984_UTM_Zone_19S",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],'
    'UNIT["Degree",0.017453292519943295]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-69],'
    'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",10000000],UNIT["Meter",1]]'
)

#: The published ``.prj`` of the Easter Island layer.
PRJ_12S = PRJ_19S.replace("Zone_19S", "Zone_12S").replace(
    '"central_meridian",-69', '"central_meridian",-111')

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-conaf-magnitud-import")


# --------------------------------------------------------------------------
# The fixture archives
# --------------------------------------------------------------------------

def square(x: float, y: float, side: float = 1000.0) -> list:
    """A square in UTM metres, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def feature(temporada, nom_incen, geometry, causa="2.1.11. Otros intencionales no "
                                                 "clasificados",
            superficie=100.0, codreg="08", fecha_ini=None, fecha_ter=None,
            numero_reg=None) -> tuple:
    values = {"TEMPORADA": temporada, "NOM_INCEN": nom_incen, "CAUSA": causa,
              "SUPERFICIE": superficie, "CODREG": codreg, "REGION": "Biobío",
              "PROVINCIA": "Concepción", "COMUNA": "Tomé",
              "FECHA_INI": fecha_ini, "FECHA_TER": fecha_ter}
    if numero_reg is not None:
        values["NUMERO_REG"] = numero_reg
    return values, geometry


#: ``if_magnitud_2016_2017``: the season the dissolve was worked out on.
#:
#: * ``402 - SAN GUILLERMO`` is one fire in one piece, carrying the number prefix.
#: * ``37 - TIL TIL`` is **one fire published as three overlapping features**, each
#:   declaring the same ``SUPERFICIE`` — which is why the mapped area comes from the
#:   union and the published one is a sum kept beside it.
#: * ``120 - LOS MAITENES`` and ``388 - LOS MAITENES`` are **two different fires with
#:   one name**, three weeks apart. Dissolving on the name alone made them one.
FEATURES_2016 = [
    feature("2016-2017", "402 - SAN GUILLERMO", square(670000, 5920000),
            superficie=100.0, fecha_ini="18-ene-2017 15:50",
            fecha_ter="20-ene-2017 09:00"),
    feature("2016-2017", "37 - TIL TIL", square(680000, 5930000), superficie=327.5,
            fecha_ini="02-feb-2017 08:00"),
    feature("2016-2017", "37 - TIL TIL", square(680200, 5930000), superficie=327.5,
            fecha_ini="02-feb-2017 08:00"),
    feature("2016-2017", "37 - TIL TIL", square(680400, 5930000), superficie=327.5,
            fecha_ini="02-feb-2017 08:00"),
    feature("2016-2017", "120 - LOS MAITENES", square(690000, 5940000),
            superficie=210.0, fecha_ini="27-nov-2016 10:00"),
    feature("2016-2017", "388 - LOS MAITENES", square(695000, 5945000),
            superficie=250.0, fecha_ini="14-dic-2016 10:00"),
]

#: ``if_magnitud_2023_2024``: the modern season.
#:
#: Publishes the number as a **column** rather than as a prefix, spells its dates
#: ``FH_INICIO``/``FH_EXTINC``, and carries an uncoded ``CAUSA`` that is a *causa
#: específica* written without its number — 40 of the 781 features are like that.
FEATURES_2023 = [
    ({"TEMPORADA": "2023-2024", "NOM_INCEN": "QUEBRADILLA", "NUMERO_REG": 1101.0,
      "CAUSA": "Uso de fuego por transeúntes", "SUPERFICIE": 400.0, "CODREG": "08",
      "REGION": "Biobío", "PROVINCIA": "Concepción", "COMUNA": "Tomé",
      "FH_INICIO": "2024/02/07", "FH_EXTINC": None},
     square(700000, 5950000)),
    # No date at all: three of the thirteen archives publish none.
    ({"TEMPORADA": "2023-2024", "NOM_INCEN": "EL PERAL", "NUMERO_REG": 0.0,
      "CAUSA": "0", "SUPERFICIE": 220.0, "CODREG": "08", "REGION": "Biobío",
      "PROVINCIA": "Concepción", "COMUNA": "Tomé",
      "FH_INICIO": None, "FH_EXTINC": None},
     square(705000, 5955000)),
]

#: ``if_magnitud_islapascua_2024_2025``: the one Easter Island perimeter.
FEATURES_EASTER = [
    feature("2024-2025", "VAITEA", square(660000, 6997000), superficie=300.0,
            codreg="05", causa="Incendio Intencional",
            fecha_ini="10-ene-2025 14:00"),
]

LAYERS = [
    ("if_magnitud_2016_2017", FEATURES_2016, 32719, PRJ_19S),
    ("if_magnitud_2023_2024", FEATURES_2023, 32719, PRJ_19S),
    ("if_magnitud_islapascua_2024_2025", FEATURES_EASTER, 32712, PRJ_12S),
]


def write_layer(directory: Path, layer: str, features: list, srid: int,
                projection: str) -> Path:
    """Build one archive's shapefile, the way CONAF publishes it."""
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
         "-a_srs", f"EPSG:{srid}", "-nln", layer, "-lco", "ENCODING=UTF-8"],
        check=True, capture_output=True,
    )
    (directory / f"{layer}.prj").write_text(projection, encoding="utf-8")
    source.unlink()
    return target


@pytest.fixture
def archives(tmp_path) -> Path:
    directory = tmp_path / "perimetres"
    directory.mkdir()
    for layer, features, srid, projection in LAYERS:
        write_layer(directory, layer, features, srid, projection)
    return directory


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
        session.add(AdminBoundary(data_provider=provider, source_id="CHL",
                                  name="Chile", name_en="Chile", level=0,
                                  geometry=f"SRID=4326;{CHILE}"))
        session.add(TimeZone(name=chile_conaf.DEFAULT_TIME_ZONE,
                             geometry=f"SRID=4326;{CHILE}"))
        session.commit()
    return database


def run(url: str, *paths: Path, extra: list[str] | None = None) -> int:
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


def stored(engine):
    with Session(engine) as session:
        return session.scalars(select(ConafMagnitudWildfire)
                               .order_by(ConafMagnitudWildfire.id)).all()


def by_name(engine) -> dict:
    return {row.name: row for row in stored(engine)}


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# The dissolve
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_fire_mapped_in_pieces_becomes_one_row(archives, with_boundaries):
    """``668 - CANIHUAL VII`` of 2018-2019 is thirteen features of one fire.

    There is no ``GID`` to group them by; the season and the name are what the
    published pieces share.
    """
    engine, url = with_boundaries
    assert run(url, archives / "if_magnitud_2016_2017.shp") == 0

    fire = by_name(engine)["TIL TIL"]
    assert fire.part_count == 3


@needs_ogr2ogr
def test_two_fires_with_one_name_stay_two_fires(archives, with_boundaries):
    """``120_LOS MAITENES`` and ``388_LOS MAITENES``, three weeks apart in 2016-2017.

    Dissolving on the season and the name alone merged four such pairs and turned
    743 fires into 739. The office's number is the third part of the key for exactly
    this.
    """
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    maitenes = [fire for fire in stored(engine) if fire.name == "LOS MAITENES"]
    assert len(maitenes) == 2
    assert {fire.number for fire in maitenes} == {120, 388}
    assert all(fire.part_count == 1 for fire in maitenes)


@needs_ogr2ogr
def test_six_published_features_are_four_fires(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    assert count(engine, "conaf_magnitud_wildfire") == 4


@needs_ogr2ogr
def test_the_dissolved_geometry_covers_every_piece(archives, with_boundaries):
    """The union, measured on the grid it was published on.

    Three overlapping 1 km squares offset by 200 m: 1.4 km² of ground, not 3.
    """
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    with Session(engine) as session:
        area = session.scalar(
            select(func.ST_Area(ConafMagnitudWildfire.perimeter_utm19s))
            .where(ConafMagnitudWildfire.name == "TIL TIL"))
    assert area == pytest.approx(1_400_000.0)


# --------------------------------------------------------------------------
# The two areas
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_mapped_area_comes_from_the_union_and_the_published_one_from_the_column(
        archives, with_boundaries):
    """``SUPERFICIE`` is each *feature's* own polygon area, so summing it double-counts.

    ``37_TIL TIL`` really is six features each declaring 327.50 ha of one 327.8 ha
    fire. Storing both numbers is what keeps the disagreement visible instead of
    making a reader choose between two wrong answers.
    """
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    fire = by_name(engine)["TIL TIL"]
    assert float(fire.area_ha_mapped) == pytest.approx(140.0, rel=1e-3)
    assert float(fire.area_ha_published) == pytest.approx(982.5), "3 x 327.5"


@needs_ogr2ogr
def test_a_single_piece_fire_agrees_with_itself(archives, with_boundaries):
    """724 of the 743 are one feature, and for those the two areas are one number."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    fire = by_name(engine)["SAN GUILLERMO"]
    assert float(fire.area_ha_published) == pytest.approx(100.0)
    assert float(fire.area_ha_mapped) == pytest.approx(100.0, rel=1e-3)


# --------------------------------------------------------------------------
# The number prefix
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_number_prefix_is_split_off_the_name(archives, with_boundaries):
    """``'402 - SAN GUILLERMO'`` here and ``'SAN GUILLERMO'`` in the report archive.

    Splitting it is what makes the binder work: the number is the strongest signal
    there is for finding the fire's report.
    """
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    fire = by_name(engine)["SAN GUILLERMO"]
    assert fire.number == 402
    assert fire.name == "SAN GUILLERMO"


@needs_ogr2ogr
def test_a_published_number_column_is_used_where_there_is_one(archives,
                                                              with_boundaries):
    """2022-2023 and 2023-2024 publish it as a column; the other eleven do not."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    assert by_name(engine)["QUEBRADILLA"].number == 1101


@needs_ogr2ogr
def test_a_zero_number_is_no_number(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    assert by_name(engine)["EL PERAL"].number is None


# --------------------------------------------------------------------------
# The two grids
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_mainland_perimeter_keeps_its_own_grid(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    with Session(engine) as session:
        srids = set(session.scalars(select(
            func.ST_SRID(ConafMagnitudWildfire.perimeter_utm19s))).all())
    assert srids == {chile_conaf.SOURCE_SRID_MAINLAND}


@needs_ogr2ogr
def test_the_easter_island_perimeter_lands_on_the_other_grid(archives,
                                                             with_boundaries):
    """One fire in 781 features, and the reason the ``_32712`` view exists."""
    engine, url = with_boundaries
    assert run(url, archives / "if_magnitud_islapascua_2024_2025.shp") == 0

    fire = by_name(engine)["VAITEA"]
    assert fire.perimeter_utm19s is None
    with Session(engine) as session:
        assert session.scalar(select(
            func.ST_SRID(ConafMagnitudWildfire.perimeter_utm12s))) \
            == chile_conaf.SOURCE_SRID_EASTER


@needs_ogr2ogr
def test_the_perimeter_is_reprojected_to_4326_as_a_multipolygon(archives,
                                                                with_boundaries):
    """The parent's perimeter is what a cross-provider query uses."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    with Session(engine) as session:
        types = set(session.scalars(
            select(func.ST_GeometryType(Wildfire.perimeter))).all())
        srids = set(session.scalars(
            select(func.ST_SRID(Wildfire.perimeter))).all())
    assert types == {"ST_MultiPolygon"}
    assert srids == {4326}


# --------------------------------------------------------------------------
# The single CAUSA column
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_coded_cause_is_filed_as_the_half_of_the_taxonomy_it_is(archives,
                                                                  with_boundaries):
    """Three code components is a *causa específica*; two is a *causa general*."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    with Session(engine) as session:
        fire = session.scalar(select(ConafMagnitudWildfire)
                              .where(ConafMagnitudWildfire.name == "SAN GUILLERMO"))
        cause = fire.cause
        assert fire.cause_published == "2.1.11. Otros intencionales no clasificados"
    assert cause.cause is None
    assert cause.specific_cause_code == "2.1.11"


@needs_ogr2ogr
def test_an_uncoded_specific_cause_is_not_filed_as_a_general_one(archives,
                                                                 with_boundaries):
    """``'Uso de fuego por transeúntes'`` is *causa específica* 1.7.1, in CONAF's
    own words, 19,276 times in the report archive.

    Forty of the 781 perimeters write a specific cause without its number. Reading
    them as general causes put forty sentences in the column a query groups the
    twenty-three general causes by.
    """
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    with Session(engine) as session:
        fire = session.scalar(select(ConafMagnitudWildfire)
                              .where(ConafMagnitudWildfire.name == "QUEBRADILLA"))
        cause = fire.cause
    assert cause.cause is None
    assert cause.specific_cause == "Uso de fuego por transeúntes"


@needs_ogr2ogr
def test_an_uncoded_general_cause_still_reconciles(archives, with_boundaries):
    """``'Incendio Intencional'`` — singular, hand-written, and a general cause."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_islapascua_2024_2025.shp")

    with Session(engine) as session:
        cause = session.scalar(select(ConafFireCause))
    assert cause.cause == "Incendio Intencional"
    assert cause.cause_normalised == "Incendios intencionales"


@needs_ogr2ogr
def test_the_null_token_is_no_cause_at_all(archives, with_boundaries):
    """Thirteen perimeters publish ``'0'``: a spreadsheet's empty cell, not a cause."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    assert by_name(engine)["EL PERAL"].cause_id is None


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_published_instant_is_stored_to_the_minute(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    fire = by_name(engine)["SAN GUILLERMO"]
    assert fire.date_time_precision == chile_conaf.PRECISION_MINUTE
    assert fire.start_date_time.astimezone(UTC).date() == datetime.date(2017, 1, 18)
    assert fire.end_date_time is not None


@needs_ogr2ogr
def test_a_perimeter_with_no_published_start_is_dated_to_its_season(archives,
                                                                    with_boundaries):
    """116 of the 781 features. Their start is a placeholder, and the column says so."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    fire = by_name(engine)["EL PERAL"]
    assert fire.date_time_precision == chile_conaf.PRECISION_SEASON
    started = fire.start_date_time.astimezone(UTC)
    assert (started.year, started.month) == (2023, 7)


@needs_ogr2ogr
def test_the_later_seasons_date_columns_are_read_too(archives, with_boundaries):
    """``FECHA_INI`` becomes ``FH_INICIO`` in 2023-2024, and ``FECHA_TER``
    ``FH_EXTINC``."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2023_2024.shp")

    fire = by_name(engine)["QUEBRADILLA"]
    assert fire.date_time_precision == chile_conaf.PRECISION_DAY
    assert fire.start_date_time.astimezone(UTC).date() == datetime.date(2024, 2, 7)


# --------------------------------------------------------------------------
# The rows when the run is done
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_perimeter_starts_life_unbound(archives, with_boundaries):
    """The link is the binder's to make, and an unbound perimeter is still a fire."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    for fire in stored(engine):
        assert fire.conaf_wildfire_id is None
        assert fire.match_method is None


@needs_ogr2ogr
def test_the_perimeter_product_is_its_own_data_provider(archives, with_boundaries):
    """Same agency name, different product — so a row is checkable against its file."""
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider).where(
            DataProvider.product == chile_conaf_magnitud.PROVIDER_PRODUCT))
    assert provider is not None
    assert provider.name == chile_conaf.PROVIDER_NAME


@needs_ogr2ogr
def test_only_the_named_season_is_imported(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "if_magnitud_2016_2017.shp",
               archives / "if_magnitud_2023_2024.shp", extra=["-y", "2023"]) == 0

    assert {fire.season_start_year for fire in stored(engine)} == {2023}


@needs_ogr2ogr
def test_importing_a_season_twice_replaces_it(archives, with_boundaries):
    engine, url = with_boundaries
    run(url, archives / "if_magnitud_2016_2017.shp")
    run(url, archives / "if_magnitud_2016_2017.shp")

    assert count(engine, "conaf_magnitud_wildfire") == 4


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(archives, with_boundaries):
    engine, url = with_boundaries
    assert run(url, archives / "if_magnitud_2016_2017.shp", extra=["--dry-run"]) == 0

    assert count(engine, "conaf_magnitud_wildfire") == 0
