#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the DARPA burnt area import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and real shapefiles, so the whole path is exercised — the subprocess,
the character set, the reprojection, the staging table and the SQL mapping. A
mocked ``ogr2ogr`` would test none of the things that actually go wrong with this
dataset.

The fixture layers are built from the GeoJSON below rather than checked in as
binaries, and they are built the way the department publishes them:

* coordinates in EPSG:25831, the Catalan grid, in metres;
* **no** ``.cpg`` file, which the real archives do not have either;
* and the DBF **language-driver byte** set to the value the real file of that era
  carries — ``0x57`` on a Latin-1 layer, ``0x00`` on a UTF-8 one. That byte is the
  only thing that says which encoding a layer is in, it is exactly correlated with
  the content across all forty published files, and the import's decision to pass
  no ``ENCODING`` option rests entirely on GDAL reading it. A fixture that did not
  reproduce it would test a different program.

Three layers, chosen for what each one breaks: ``incendis1994`` is the shattered
era (fragments to dissolve, Latin-1, two-digit dates), ``incendis2022`` is the
modern one (UTF-8, four-digit dates, and the code that names two fires), and
``incendis10`` is 2010 under the department's two-digit name.
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

from src.apps.imports.wildfires.catalonia_darpa import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import catalonia_darpa
from src.providers import ocha
from src.providers import spain_egif
from src.providers.catalonia_darpa.wildfire import DarpaWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

#: Spain, near enough for a fixture: it contains every fire below except the one
#: in the Mediterranean, which is the point of that one.
SPAIN = "MULTIPOLYGON(((-9.5 36, 3.4 36, 3.4 43.8, -9.5 43.8, -9.5 36)))"

#: The DBF language-driver byte of each era's files. See the module docstring:
#: this is what GDAL reads, and it is the whole basis of the import's encoding
#: decision.
LDID_LATIN1 = 0x57
LDID_UTF8 = 0x00

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-darpa-import")


def square(x: float, y: float, side: float = 1000.0) -> list:
    """A square in EPSG:25831 metres, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def feature(code, date, municipality, geometry, grid_code=2) -> tuple:
    """One published feature, named exactly as the department names its fields."""
    return ({"CODI_FINAL": code, "DATA_INCEN": date, "MUNICIPI": municipality,
             "GRID_CODE": grid_code}, geometry)


#: ``incendis1994``: the shattered era. Latin-1, two-digit dates.
#:
#: * ``894496`` is published as **three touching fragments**, which is what this
#:   dataset does to a fire and what the import has to dissolve. Its municipality
#:   is accented, so a mangled Latin-1 read shows up here.
#: * ``894221`` is one polygon, so a run that dissolved everything into one row
#:   would be caught.
#: * two background features carry ``GRID_CODE`` 0 — one with nothing filled in,
#:   as 152 of the published ones are, and one with the float that was written
#:   into the date column.
#: * ``894999`` is a self-intersecting bowtie, invalid as published.
FEATURES_1994 = [
    feature("894496", "11/08/94", "Sant Cugat del Vallès", square(420000, 4590000)),
    feature("894496", "11/08/94", "Sant Cugat del Vallès", square(421000, 4590000)),
    feature("894496", "11/08/94", "Sant Cugat del Vallès", square(422000, 4590000)),
    feature("894221", "02/07/94", "Subirats", square(400000, 4570000)),
    feature(None, None, None, square(450000, 4600000), grid_code=0),
    feature("894496", "2,152543589*", "Sant Cugat del Vallès",
            square(423000, 4590000), grid_code=0),
    feature("894999", "15/09/94", "Navàs",
            [[[430000.0, 4600000.0], [431000.0, 4601000.0], [431000.0, 4600000.0],
              [430000.0, 4601000.0], [430000.0, 4600000.0]]]),
]

#: ``incendis2022``: the modern era. UTF-8, four-digit dates.
#:
#: * ``2022170027`` is the ten-digit form — year, INE province, sequence — that is
#:   shaped exactly like an EGIF ``report_number``.
#: * ``303/22N`` appears **twice on different dates**, which is two fires and not
#:   one: Lleida on 19 June and Figueres on 7 July. Grouping on the code alone
#:   would union them into a polygon spanning half of Catalonia.
#: * ``2022430099`` is out in the Mediterranean: no country.
#: * ``2022250044`` has a literal CRLF at the end of **both** its date and its
#:   municipality, which six published values really do. Untrimmed it is not a
#:   date, and the fire vanishes with nothing to say it did.
FEATURES_2022 = [
    feature("2022170027", "23/02/2022", "SETCASES", square(430000, 4690000)),
    feature("303/22N", "19/06/2022", "LLEIDA", square(300000, 4610000)),
    feature("303/22N", "07/07/2022", "FIGUERES", square(490000, 4680000)),
    feature("2022430099", "01/08/2022", "SERÒS", square(900000, 4500000)),
    feature("2022250044", "12/08/2022\r\n", "LA POBLA DE MASSALUCA\r\n",
            square(280000, 4560000)),
]

#: ``incendis10``: 2010, under the department's own two-digit layer name.
FEATURES_2010 = [
    feature("2010250090", "15/03/10", "Bausen", square(320000, 4740000)),
]

#: The layers the fixture directory holds, with the language-driver byte the real
#: files of that era carry.
LAYERS = [
    ("incendis1994", FEATURES_1994, "ISO-8859-1", LDID_LATIN1),
    ("incendis2022", FEATURES_2022, "UTF-8", LDID_UTF8),
    ("incendis10", FEATURES_2010, "ISO-8859-1", LDID_LATIN1),
]


def write_layer(directory: Path, layer: str, features: list, encoding: str,
                ldid: int) -> Path:
    """Build one layer's shapefile, the way the department publishes it.

    ``-a_srs EPSG:25831`` *assigns* the CRS rather than reprojecting: the
    coordinates are already Catalan grid metres, and GeoJSON is nominally
    EPSG:4326.

    ``-oo DATE_AS_STRING=YES`` keeps ``DATA_INCEN`` a **text** field, which is what
    it is in every published layer (``String (12.0)``). Without it GDAL's GeoJSON
    reader recognises ``15/03/10`` as a date, writes a real Date field and stores
    it as 2015 — building a fixture that does not have the problem the import
    exists to solve. It only bites where a layer's values are uniform enough to be
    detected, which is why ``incendis1994`` survives it and ``incendis10`` does not.

    The ``.cpg`` is deleted and the language-driver byte written by hand, because
    together those two are what the published files look like and what the
    import's encoding decision depends on. See the module docstring.
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

    subprocess.run(["ogr2ogr", "-f", "ESRI Shapefile", str(directory),
                    "-oo", "DATE_AS_STRING=YES", str(source),
                    "-nln", layer, "-a_srs", "EPSG:25831",
                    "-lco", f"ENCODING={encoding}"],
                   check=True, capture_output=True)
    source.unlink()
    (directory / f"{layer}.cpg").unlink(missing_ok=True)

    dbf = directory / f"{layer}.dbf"
    raw = bytearray(dbf.read_bytes())
    raw[29] = ldid
    dbf.write_bytes(raw)
    return directory / f"{layer}.shp"


@pytest.fixture
def published(tmp_path) -> Path:
    """A directory of published layers, including the duplicate and a stray file."""
    directory = tmp_path / "catalunya"
    directory.mkdir()
    for layer, features, encoding, ldid in LAYERS:
        write_layer(directory, layer, features, encoding, ldid)

    # incendis.shp is byte-identical to incendis2022.shp in the published set.
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        source = directory / f"incendis2022{suffix}"
        if source.exists():
            shutil.copy(source, directory / f"incendis{suffix}")
    # And something that is not a published layer at all.
    write_layer(directory, "comarques", FEATURES_2010, "UTF-8", LDID_UTF8)
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
    """Europe/Madrid over Catalonia, and nothing else."""
    engine, _ = database
    with Session(engine) as session:
        session.add(TimeZone(
            name=catalonia_darpa.DEFAULT_TIME_ZONE,
            geometry=f"SRID=4326;{SPAIN}"))
        session.commit()


def run_import(connection_arguments, extra: list[str]) -> int:
    """Run the application's ``main`` and return its exit code."""
    return app.main([*extra, *connection_arguments, "--log-level", "WARNING"])


def fires(engine) -> list[DarpaWildfire]:
    with Session(engine) as session:
        return list(session.scalars(
            select(DarpaWildfire).order_by(DarpaWildfire.code, DarpaWildfire.fire_date)))


def find(engine, code: str, date: datetime.date | None = None) -> DarpaWildfire:
    matches = [fire for fire in fires(engine)
               if fire.code == code and (date is None or fire.fire_date == date)]
    assert len(matches) == 1, f"expected one fire {code}/{date}, got {len(matches)}"
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


def test_the_layers_are_ordered_by_year_not_by_name(published):
    """``incendis10`` is 2010 and sorts there, not between 1 and 1986."""
    args = app.parse_arguments(["-d", str(published)])

    assert [path.stem for path in app.find_archives(args)] == [
        "incendis1994", "incendis10", "incendis2022"]


def test_the_duplicate_layer_is_left_out(published):
    """``incendis.shp`` is a byte-identical copy of ``incendis2022.shp``."""
    args = app.parse_arguments(["-d", str(published)])

    assert "incendis" not in {path.stem for path in app.find_archives(args)}
    duplicates, _ = app.skipped_archives(args)
    assert [path.stem for path in duplicates] == ["incendis"]


def test_a_file_whose_name_carries_no_year_is_left_out(published):
    args = app.parse_arguments(["-d", str(published)])

    assert "comarques" not in {path.stem for path in app.find_archives(args)}
    _, unnamed = app.skipped_archives(args)
    assert "comarques" in {path.stem for path in unnamed}


def test_a_year_can_be_selected(published):
    args = app.parse_arguments(["-d", str(published), "--year", "2022"])

    assert [path.stem for path in app.find_archives(args)] == ["incendis2022"]


def test_several_years_can_be_selected(published):
    args = app.parse_arguments(["-d", str(published), "--year", "2010", "--year", "1994"])

    assert [path.stem for path in app.find_archives(args)] == ["incendis1994", "incendis10"]


def test_a_year_that_is_not_there_is_an_error(published):
    args = app.parse_arguments(["-d", str(published), "--year", "1999"])

    with pytest.raises(RuntimeError, match="no layer to import"):
        app.find_archives(args)


def test_an_empty_directory_is_an_error(tmp_path):
    args = app.parse_arguments(["-d", str(tmp_path)])

    with pytest.raises(RuntimeError, match="no .zip or .shp"):
        app.find_archives(args)


def test_a_single_file_is_imported_as_given(published):
    args = app.parse_arguments(["-s", str(published / "incendis2022.shp")])

    assert app.find_archives(args) == [published / "incendis2022.shp"]
    assert app.skipped_archives(args) == ([], [])


# --------------------------------------------------------------------------
# The import itself
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_whole_directory_imports(published, database, connection_arguments,
                                     boundaries, time_zones):
    engine, _ = database

    assert run_import(connection_arguments, ["-d", str(published)]) == 0

    # 1994: 894496 (3 fragments), 894221, 894999. 2022: five. 2010: one.
    assert len(fires(engine)) == 9


@needs_ogr2ogr
def test_the_fragments_of_one_fire_become_one_row(published, database,
                                                  connection_arguments, time_zones):
    """The property the whole import is shaped around: 1994 publishes fragments."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    fire = find(engine, "894496")
    assert fire.part_count == 3
    with Session(engine) as session:
        parts = session.scalar(select(func.ST_NumGeometries(
            DarpaWildfire.perimeter_etrs89_utm31n)).where(DarpaWildfire.id == fire.id))
        area = session.scalar(select(func.ST_Area(
            DarpaWildfire.perimeter_etrs89_utm31n)).where(DarpaWildfire.id == fire.id))
    # The three squares touch along their edges, so the union is one ring of 3 km².
    assert parts == 1
    assert area == pytest.approx(3_000_000.0)


@needs_ogr2ogr
def test_a_fire_published_as_one_polygon_keeps_a_part_count_of_one(
        published, database, connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    assert find(engine, "894221").part_count == 1


@needs_ogr2ogr
def test_one_code_on_two_dates_stays_two_fires(published, database,
                                               connection_arguments, time_zones):
    """``303/22N``: Lleida on 19 June and Figueres on 7 July, 190 km apart."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    lleida = find(engine, "303/22N", datetime.date(2022, 6, 19))
    figueres = find(engine, "303/22N", datetime.date(2022, 7, 7))
    assert lleida.municipality_name == "LLEIDA"
    assert figueres.municipality_name == "FIGUERES"
    assert (lleida.part_count, figueres.part_count) == (1, 1)


@needs_ogr2ogr
def test_the_background_polygons_are_not_imported(published, database,
                                                  connection_arguments, time_zones):
    """``GRID_CODE`` 0 is the raster's background class, not a fire.

    Both of the fixture's background features would otherwise be a problem: one has
    no attributes at all, and the other carries the float that was written into the
    date column.
    """
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    assert len(fires(engine)) == 3, "894496, 894221 and 894999 — nothing else"
    # And the background fragment did not join the fire whose code it shares.
    assert find(engine, "894496").part_count == 3


@needs_ogr2ogr
def test_an_invalid_polygon_is_repaired_rather_than_dropped(
        published, database, connection_arguments, time_zones):
    """A self-intersecting bowtie is ~1% of a published perimeter set."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    fire = find(engine, "894999")
    with Session(engine) as session:
        valid = session.scalar(select(func.ST_IsValid(
            DarpaWildfire.perimeter_etrs89_utm31n)).where(DarpaWildfire.id == fire.id))
    assert valid is True


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_four_digit_year_is_parsed(published, database, connection_arguments,
                                     time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    assert find(engine, "2022170027").fire_date == datetime.date(2022, 2, 23)


@needs_ogr2ogr
def test_a_two_digit_year_takes_its_century_from_the_layer(
        published, database, connection_arguments, time_zones):
    """``11/08/94`` in ``incendis1994`` is 1994, and ``15/03/10`` in ``incendis10`` is 2010.

    The two would need opposite answers from any fixed pivot that is not between
    10 and 94, which is the reason the century is resolved against the layer.
    """
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published), "--year", "1994",
                                      "--year", "2010"])

    assert find(engine, "894496").fire_date == datetime.date(1994, 8, 11)
    assert find(engine, "2010250090").fire_date == datetime.date(2010, 3, 15)


@needs_ogr2ogr
def test_the_year_column_is_the_layers(published, database, connection_arguments,
                                       time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    for fire in fires(engine):
        assert fire.year == fire.fire_date.year, fire.code
    assert {fire.year for fire in fires(engine)} == {1994, 2010, 2022}


@needs_ogr2ogr
def test_the_start_is_local_midnight_on_the_published_date(
        published, database, connection_arguments, time_zones):
    """Europe/Madrid is UTC+2 in August, so local midnight is 22:00 UTC the day before."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    fire = find(engine, "894496")
    assert fire.time_zone == "Europe/Madrid"
    assert fire.start_date_time == datetime.datetime(1994, 8, 10, 22, 0, tzinfo=UTC)


@needs_ogr2ogr
def test_a_winter_date_gets_the_winter_offset(published, database,
                                              connection_arguments, time_zones):
    """UTC+1 in February, not the summer offset — the zone is applied per date."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    assert find(engine, "2022170027").start_date_time == \
        datetime.datetime(2022, 2, 22, 23, 0, tzinfo=UTC)


@needs_ogr2ogr
def test_a_value_ending_in_a_line_ending_is_still_read(
        published, database, connection_arguments, time_zones):
    """Six published values carry a literal CRLF inside the DBF field.

    GDAL strips a character field's space padding but not those, so untrimmed
    ``12/08/2022\\r\\n`` fails every date shape and the fire is silently absent —
    which is what happened to five real fires before the trim went in. The
    municipality has to come back clean too, not merely non-empty.
    """
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    fire = find(engine, "2022250044")
    assert fire.fire_date == datetime.date(2022, 8, 12)
    assert fire.municipality_name == "LA POBLA DE MASSALUCA"


@needs_ogr2ogr
def test_no_end_date_is_invented(published, database, connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    assert all(fire.end_date_time is None for fire in fires(engine))


# --------------------------------------------------------------------------
# Geometry and location
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_perimeter_is_stored_in_both_crs(published, database,
                                             connection_arguments, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        for source_srid, target_srid in session.execute(select(
                func.ST_SRID(DarpaWildfire.perimeter_etrs89_utm31n),
                func.ST_SRID(DarpaWildfire.perimeter))):
            assert (source_srid, target_srid) == (25831, 4326)


@needs_ogr2ogr
def test_the_two_geometries_are_the_same_one(published, database,
                                             connection_arguments, time_zones):
    """The 4326 copy is derived from the stored 25831 one, so they cannot disagree."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DarpaWildfire).where(
            ~func.ST_Equals(
                func.ST_Transform(DarpaWildfire.perimeter_etrs89_utm31n, 4326),
                DarpaWildfire.perimeter))) == 0


@needs_ogr2ogr
def test_the_stored_geometry_is_a_multipolygon(published, database,
                                               connection_arguments, time_zones):
    """The column says MULTIPOLYGON, and a union of one square returns a POLYGON."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        types = set(session.scalars(
            select(func.ST_GeometryType(DarpaWildfire.perimeter_etrs89_utm31n))))
    assert types == {"ST_MultiPolygon"}


@needs_ogr2ogr
def test_a_fire_is_attributed_to_its_country(published, database, connection_arguments,
                                             boundaries, time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        name = session.scalar(
            select(OchaAdminBoundary.name)
            .select_from(DarpaWildfire)
            .join(OchaAdminBoundary,
                  OchaAdminBoundary.id == DarpaWildfire.admin_boundary_id)
            .where(DarpaWildfire.code == "2022170027"))
    assert name == "Spain"


@needs_ogr2ogr
def test_a_fire_outside_every_boundary_keeps_its_perimeter(
        published, database, connection_arguments, boundaries, time_zones):
    """A polygon in the Mediterranean is still a row, just one with no country."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    fire = find(engine, "2022430099")
    assert fire.admin_boundary_id is None
    assert fire.perimeter is not None


@needs_ogr2ogr
def test_the_import_works_without_boundaries_or_time_zones(
        published, database, connection_arguments):
    """Both are optional: the perimeters and the dates are worth having alone."""
    engine, _ = database

    assert run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")]) == 0
    assert len(fires(engine)) == 5
    # No zones imported, so the fallback dates them — Europe/Madrid, not UTC.
    assert find(engine, "2022170027").start_date_time == \
        datetime.datetime(2022, 2, 22, 23, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# The character set
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_latin1_layer_keeps_its_accents(published, database, connection_arguments,
                                          time_zones):
    """1994 is ISO-8859-1 and says so in its language-driver byte."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp")])

    assert find(engine, "894496").municipality_name == "Sant Cugat del Vallès"
    assert find(engine, "894999").municipality_name == "Navàs"


@needs_ogr2ogr
def test_a_utf8_layer_keeps_its_accents_too(published, database,
                                            connection_arguments, time_zones):
    """2022 is UTF-8. Forcing one encoding for the whole archive breaks one of the two."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    assert find(engine, "2022430099").municipality_name == "SERÒS"


@needs_ogr2ogr
def test_the_two_encodings_import_together_without_an_option(
        published, database, connection_arguments, time_zones):
    """The whole point: one run, two character sets, no ENCODING passed."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    names = {fire.municipality_name for fire in fires(engine)}
    assert {"Sant Cugat del Vallès", "SERÒS"} <= names
    # And neither signature of a mangled read is anywhere in the table.
    assert not any("Ã" in name or "�" in name for name in names)


@needs_ogr2ogr
def test_a_mangled_name_is_reported(published, database, connection_arguments,
                                    time_zones, caplog):
    """The check that goes with letting GDAL decide.

    Forcing the wrong encoding is exactly what the import must not do, so this
    reaches into the staging table and mangles a name directly — the point is that
    :func:`check_encoding` would notice, not how the mangling got there.
    """
    engine, _ = database
    staging = "staging.darpa_burnt_areas"
    run_import(connection_arguments, ["-s", str(published / "incendis1994.shp"),
                                      "--keep-staging"])

    with Session(engine) as session:
        session.execute(text(f"UPDATE {staging} SET municipi = 'AlfarrÃ s'"))
        with caplog.at_level(logging.WARNING):
            suspect = app.check_encoding(session, staging, logger)

    assert suspect > 0
    assert "character set read wrongly" in caplog.text


# --------------------------------------------------------------------------
# Re-importing
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_re_importing_a_layer_replaces_it(published, database, connection_arguments,
                                          time_zones):
    """The department republishes years, so the second run has to win."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])
    before = {fire.id for fire in fires(engine)}

    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])
    after = fires(engine)

    assert len(after) == 5, "replaced, not doubled"
    assert {fire.id for fire in after}.isdisjoint(before), "the rows really are new"


@needs_ogr2ogr
def test_re_importing_leaves_no_orphan_parent_rows(published, database,
                                                   connection_arguments, time_zones):
    """``darpa_wildfire.id`` references ``wildfire.id``; the delete has to do both."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 5


@needs_ogr2ogr
def test_re_importing_warns_that_an_egif_binding_is_going(
        published, database, connection_arguments, time_zones, caplog):
    """Replacing a layer deletes the rows, and the link goes with them."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                     product=spain_egif.PROVIDER_PRODUCT,
                                     full_name=spain_egif.PROVIDER_FULL_NAME)
        session.add(egif_provider)
        session.flush()
        parte = EgifWildfire(
            data_provider_id=egif_provider.id, report_number="2022170027", campaign=2022,
            province_ine_code="17",
            start_date_time=datetime.datetime(2022, 2, 23, 10, 0, tzinfo=UTC),
            time_zone=spain_egif.DEFAULT_TIME_ZONE)
        session.add(parte)
        session.flush()
        # The method goes with the link: a check constraint makes them
        # all-or-nothing, which is what stops an unattributable binding existing.
        session.execute(text(
            "UPDATE darpa_wildfire SET egif_wildfire_id = :parte, match_method = 'code', "
            "match_confidence = 1.0, matched_at = now() WHERE code = '2022170027'"
        ), {"parte": parte.id})
        session.commit()

    with caplog.at_level(logging.WARNING):
        run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    assert "bound to an EGIF parte" in caplog.text
    assert all(fire.egif_wildfire_id is None for fire in fires(engine))


@needs_ogr2ogr
def test_the_import_never_fills_the_egif_link(published, database,
                                              connection_arguments, time_zones):
    """Even where the code is exactly an EGIF report number, which 2022170027 is."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert all(fire.egif_wildfire_id is None for fire in fires(engine))


@needs_ogr2ogr
def test_a_dry_run_writes_nothing(published, database, connection_arguments, time_zones):
    engine, _ = database

    assert run_import(connection_arguments, ["-d", str(published), "--dry-run"]) == 0
    assert fires(engine) == []


@needs_ogr2ogr
def test_a_dry_run_does_not_replace_what_is_already_there(
        published, database, connection_arguments, time_zones):
    """The delete has to be rolled back with everything else, or it is not dry."""
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])
    before = {fire.id for fire in fires(engine)}

    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp"),
                                      "--dry-run"])

    assert {fire.id for fire in fires(engine)} == before


@needs_ogr2ogr
def test_the_staging_table_is_dropped(published, database, connection_arguments,
                                      time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])

    with Session(engine) as session:
        assert session.scalar(text(
            "SELECT to_regclass('staging.darpa_burnt_areas')")) is None


@needs_ogr2ogr
def test_the_provider_row_is_created_once(published, database, connection_arguments,
                                          time_zones):
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])
    run_import(connection_arguments, ["-d", str(published)])

    with Session(engine) as session:
        providers = list(session.scalars(select(DataProvider).where(
            DataProvider.name == catalonia_darpa.PROVIDER_NAME)))
    assert len(providers) == 1
    assert providers[0].product == catalonia_darpa.PROVIDER_PRODUCT


@needs_ogr2ogr
def test_the_source_layer_is_recorded(published, database, connection_arguments,
                                      time_zones):
    """Provenance of a row in a table that gathers thirty-nine files."""
    engine, _ = database
    run_import(connection_arguments, ["-d", str(published)])

    assert {fire.source_layer for fire in fires(engine)} == {
        "incendis1994", "incendis2010", "incendis2022"}


# --------------------------------------------------------------------------
# Failures
# --------------------------------------------------------------------------

def test_a_missing_source_is_reported(connection_arguments, tmp_path):
    assert run_import(connection_arguments, ["-d", str(tmp_path / "nowhere")]) == 1


def test_a_missing_ogr2ogr_is_reported(published, connection_arguments):
    assert run_import(connection_arguments,
                      ["-d", str(published), "--ogr2ogr", "definitely-not-a-binary"]) == 1


# --------------------------------------------------------------------------
# The year comes from the file, not from the layer inside it
# --------------------------------------------------------------------------

@pytest.fixture
def zipped(published, tmp_path) -> Path:
    """The published years as the department ships them: two-digit zip names.

    ``incendis22.zip`` holds a shapefile called plainly ``incendis``, exactly as the
    real one does — it is where the loose duplicate ``incendis.shp`` comes from —
    so the layer GDAL reports for it carries no year at all.
    """
    directory = tmp_path / "zips"
    directory.mkdir()
    for layer, short, inner in [("incendis1994", "incendis94", "incendis1994"),
                                ("incendis2022", "incendis22", "incendis"),
                                ("incendis10", "incendis10", "incendis10")]:
        unpacked = directory / short
        unpacked.mkdir()
        for path in published.glob(f"{layer}.*"):
            shutil.copy(path, unpacked / f"{inner}{path.suffix}")
        shutil.make_archive(str(directory / short), "zip", root_dir=str(unpacked))
        shutil.rmtree(unpacked)
    return directory


def test_a_two_digit_zip_name_carries_its_year(zipped):
    args = app.parse_arguments(["-d", str(zipped)])

    assert [path.stem for path in app.find_archives(args)] == [
        "incendis94", "incendis10", "incendis22"]


@needs_ogr2ogr
def test_a_zip_whose_inner_layer_has_no_year_still_imports(zipped, database,
                                                           connection_arguments,
                                                           time_zones):
    """``incendis22.zip`` holds a layer called ``incendis``.

    Taking the year from the GDAL layer rather than from the file stopped the whole
    run dead here — and silently, because every earlier year had already committed.
    """
    engine, _ = database

    assert run_import(connection_arguments, ["-d", str(zipped)]) == 0
    assert {fire.year for fire in fires(engine)} == {1994, 2010, 2022}
    assert find(engine, "2022170027").source_layer == "incendis2022"


@needs_ogr2ogr
def test_the_zip_and_the_shapefile_are_the_same_layer(zipped, published, database,
                                                      connection_arguments, time_zones):
    """So importing one after the other replaces the year instead of doubling it.

    The department ships 2022 as ``incendis2022.shp`` and as ``incendis22.zip``, and
    2010 as ``incendis10`` in both forms. A ``source_layer`` taken as found would
    give each copy its own value and the replace rule would never fire.
    """
    engine, _ = database
    run_import(connection_arguments, ["-s", str(published / "incendis2022.shp")])
    from_shapefile = {fire.source_layer for fire in fires(engine)}

    run_import(connection_arguments, ["-s", str(zipped / "incendis22.zip")])

    assert from_shapefile == {"incendis2022"}
    assert len(fires(engine)) == 5, "replaced, not doubled"
    assert {fire.source_layer for fire in fires(engine)} == {"incendis2022"}
