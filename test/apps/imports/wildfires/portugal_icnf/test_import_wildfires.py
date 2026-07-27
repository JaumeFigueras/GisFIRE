#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ICNF burnt area import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and real shapefiles, so the whole path is exercised — the subprocess,
the character set, the reprojection, the staging table and the SQL mapping. A
mocked ``ogr2ogr`` would test none of the things that actually go wrong with this
dataset.

The fixture archives are built from the GeoJSON below rather than checked in as
binaries, and they are built the way the ICNF publishes them: coordinates in
EPSG:3763, an ISO-8859-1 DBF, and **no** ``.cpg`` file, which is what makes the
character set something the importer has to know rather than something GDAL can
read off the disk.

Two layers, because the dataset has two eras: ``ardida_2024`` publishes
twenty-two attributes and ``ardida_1975_1989`` publishes two.
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

from src.apps.imports.wildfires.portugal_icnf import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.time_zone import TimeZone
from src.data_model.wildfire import Wildfire
from src.providers import icnf
from src.providers import ocha
from src.providers.icnf.fire_cause import IcnfFireCause
from src.providers.icnf.wildfire import IcnfWildfire
from src.providers.ocha.admin_boundary import OchaAdminBoundary

UTC = datetime.timezone.utc

#: Mainland Portugal, near enough for a fixture: it contains every fire below
#: except the Atlantic one, which is the point of that one.
PORTUGAL = "MULTIPOLYGON(((-10 36, -6 36, -6 43, -10 43, -10 36)))"

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-icnf-import")


def square(x: float, y: float, side: float = 1000.0) -> list:
    """A square in EPSG:3763 metres, as GeoJSON Polygon coordinates."""
    return [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]]


def attributes(**overrides) -> dict:
    """One modern feature's attributes, named exactly as the ICNF names them.

    Everything defaults to ``None`` so that a test can name only what it cares
    about — and so that the unmatched-perimeter case, which is a real 901 features
    of the published data, is the default rather than a special construction.
    """
    values = {
        "Cod_SGIF": None, "Cod_ANEPC": None, "Ano": 2024,
        "DH_Inicio": None, "DH_1Interv": None, "DH_Fim": None, "Duracao_m": None,
        "PI_DICOFRE": None, "PI_NUTS3": None, "PI_Distrit": None, "PI_Conc": None,
        "PI_Freg": None, "PI_Local": None,
        "Causa_Cod": None, "Causa_Tipo": None, "Causa_Desc": None,
        "AreaHaSIG": 2.76886994, "AreaHaSGIF": None, "AreaHaPov": None,
        "AreaHaMato": None, "AreaHaAgri": None, "Edicao": None,
    }
    values.update(overrides)
    return values


#: Six features of ``ardida_2024``. Every one is placed deliberately:
#:
#: * ``20240125102`` in January — Europe/Lisbon is UTC+0 then. Carries the
#:   accented names that prove the character set survived, and a cause.
#: * ``20240715001`` in July — Europe/Lisbon is UTC+1 (WEST) then, so a fixed
#:   offset instead of a per-date one would be caught. Its duration crosses
#:   midnight, which is the case the truncated dates cannot express.
#: * one feature with no attributes at all beyond the year and the area: the
#:   perimeter the ICNF could not match to a fire record.
#: * ``20240900001`` is a self-intersecting bowtie, invalid as published.
#: * ``20240800001`` carries a cause the translation tables have never seen.
#: * ``20240600001`` is in the middle of the Atlantic: no country, no zone.
MODERN_FEATURES = [
    (attributes(Cod_SGIF="20240125102", Cod_ANEPC="20240125102",
                DH_Inicio="2024-01-29", DH_1Interv="2024-01-29", DH_Fim="2024-01-29",
                Duracao_m=144, PI_DICOFRE="181620", PI_NUTS3="Viseu Dão Lafões",
                PI_Distrit="Viseu", PI_Conc="São Pedro do Sul",
                PI_Freg="União das freguesias de Carvalhais e Candal",
                PI_Local="Serra da Coelheira",
                Causa_Cod="122", Causa_Tipo="Negligente",
                Causa_Desc="Queimadas de sobrantes florestais ou agrícolas",
                AreaHaSIG=2.76886994, AreaHaSGIF=2.76886994, AreaHaPov=0.95900685,
                AreaHaMato=1.80986309, AreaHaAgri=0.0, Edicao="2025-03-03"),
     square(0, 0)),
    (attributes(Cod_SGIF="20240715001", Cod_ANEPC="2024010004987",
                DH_Inicio="2024-07-15", DH_1Interv="2024-07-16", DH_Fim="2024-07-16",
                Duracao_m=97, PI_Distrit="Vila Real", PI_Conc="Montalegre",
                Causa_Cod="125", Causa_Tipo="Negligente",
                Causa_Desc="Queimadas para gestão de pasto para gado",
                AreaHaSIG=53.29158801),
     square(50000, 100000)),
    (attributes(AreaHaSIG=0.05212912), square(-20000, -50000)),
    (attributes(Cod_SGIF="20240900001", DH_Inicio="2024-09-10", DH_Fim="2024-09-10",
                AreaHaSIG=1.5),
     [[[30000.0, 30000.0], [31000.0, 31000.0], [31000.0, 30000.0],
       [30000.0, 31000.0], [30000.0, 30000.0]]]),
    (attributes(Cod_SGIF="20240800001", DH_Inicio="2024-08-01", DH_Fim="2024-08-01",
                Causa_Cod="998", Causa_Tipo="Categoria inventada",
                Causa_Desc="Descrição que ainda não existe", AreaHaSIG=4.0),
     square(10000, -20000)),
    (attributes(Cod_SGIF="20240600001", DH_Inicio="2024-06-01", DH_Fim="2024-06-01",
                AreaHaSIG=7.0),
     square(-500000, 0)),
]

#: Two features of ``ardida_1975_1989``, which publishes ``Ano`` and ``AreaHaSIG``
#: and nothing else — not even the field. This is what
#: :func:`~src.apps.imports.wildfires.portugal_icnf.import_wildfires.normalise_staging_columns`
#: exists for.
HISTORICAL_FEATURES = [
    ({"Ano": 1975, "AreaHaSIG": 65.91566807}, square(5000, 5000)),
    ({"Ano": 1989, "AreaHaSIG": 60.94752592}, square(15000, 5000)),
]


def instant(text_value: str) -> datetime.datetime:
    """Parse an ISO instant into an aware UTC datetime, for comparing against the model."""
    return datetime.datetime.fromisoformat(text_value).astimezone(UTC)


def write_archive(directory: Path, layer: str, features: list) -> Path:
    """Build one layer's zipped shapefile, the way the ICNF publishes it.

    Three details are the published ones and all three matter:

    * ``-a_srs EPSG:3763`` — the coordinates are national grid metres, not
      degrees. GeoJSON is nominally EPSG:4326, so the SRS is *assigned*, not
      reprojected.
    * ``-lco ENCODING=ISO-8859-1`` — the DBF holds the Portuguese names in
      Latin-1.
    * the ``.cpg`` is deleted afterwards. The real archives carry a ``.cst``
      instead, which is a GeoServer convention GDAL does not read, so the encoding
      is undiscoverable from the files and the importer has to supply it.
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

    unpacked = directory / layer
    subprocess.run(["ogr2ogr", "-f", "ESRI Shapefile", str(unpacked), str(source),
                    "-nln", layer, "-a_srs", "EPSG:3763",
                    "-lco", "ENCODING=ISO-8859-1"],
                   check=True, capture_output=True)
    source.unlink()
    for stray in unpacked.glob("*.cpg"):
        stray.unlink()

    archive = shutil.make_archive(str(directory / layer), "zip", root_dir=str(unpacked))
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
    """Portugal, as an OCHA boundary under an OCHA provider row."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(OchaAdminBoundary(
            data_provider_id=provider.id, source_id="PRT", level=0, name="Portugal",
            geometry=f"SRID=4326;{PORTUGAL}", source="PRT", iso_code=620, iso_2="PT",
            iso_3="PRT", iso_name="Portugal", iso_3_group="PRT",
            region1_code=1, region1_name="r1", region2_code=2, region2_name="r2",
            region3_code=3, region3_name="r3", status_code=1, status_name="State",
            valid_date=datetime.date(2025, 1, 1), update_date=datetime.date(2025, 1, 1),
            land_source="osm", view="intl",
        ))
        session.commit()


@pytest.fixture
def time_zones(database):
    """Europe/Lisbon over mainland Portugal, and nothing else.

    Inserted directly rather than through the time zone importer: what these tests
    need is one zone that is UTC+0 in winter and UTC+1 in summer, which is exactly
    the thing that distinguishes a real zone lookup from hard-coded UTC.
    """
    engine, _ = database
    with Session(engine) as session:
        session.add(TimeZone(name="Europe/Lisbon", geometry=f"SRID=4326;{PORTUGAL}"))
        session.commit()


@pytest.fixture
def archives(tmp_path):
    """A directory holding both eras, as the download lays them out."""
    write_archive(tmp_path, "ardida_2024", MODERN_FEATURES)
    write_archive(tmp_path, "ardida_1975_1989", HISTORICAL_FEATURES)
    return tmp_path


@pytest.fixture
def modern_only(tmp_path):
    write_archive(tmp_path, "ardida_2024", MODERN_FEATURES)
    return tmp_path


@pytest.fixture
def args(archives, connection_arguments):
    return app.parse_arguments(["--directory", str(archives), *connection_arguments])


@pytest.fixture
def imported(database, boundaries, time_zones, args):
    """Both layers imported into a world that has both a country and a zone."""
    engine, _ = database
    count = app.import_wildfires(args, engine, logger)
    return engine, count


def fire(session: Session, sgif_code: str) -> IcnfWildfire:
    return session.scalar(select(IcnfWildfire).where(IcnfWildfire.sgif_code == sgif_code))


# --------------------------------------------------------------------------
# Arguments (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_a_directory_and_an_archive_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", "dir", "-s", "ardida_2024.zip"])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-s", "ardida_2024.zip"])
    assert parsed.staging_table == app.DEFAULT_STAGING_TABLE
    assert parsed.keep_staging is False
    assert parsed.replace is False


def test_the_archives_of_a_directory_are_found_in_published_order(tmp_path):
    """Sorting puts the three multi-year layers before the yearly ones."""
    for layer in ("ardida_2009", "ardida_2000_2008", "ardida_1975_1989", "ardida_1990_1999"):
        (tmp_path / f"{layer}.zip").touch()
    (tmp_path / "notes.txt").touch()

    found = app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))
    assert [path.name for path in found] == [
        "ardida_1975_1989.zip", "ardida_1990_1999.zip",
        "ardida_2000_2008.zip", "ardida_2009.zip",
    ]


def test_an_empty_directory_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="no .zip"):
        app.find_archives(app.parse_arguments(["-d", str(tmp_path)]))


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent", "--db-name", "x", "--db-user", "y"]) == 1
    assert "Not found" in caplog.text


def test_every_attribute_the_mapping_reads_is_declared():
    """STAGING_COLUMNS is what normalise_staging_columns fills in; a gap is a NULL.

    The two cause texts are read by the cause upsert rather than by the transform,
    which is why both statements are searched.
    """
    declared = [name for name, _ in app.STAGING_COLUMNS]
    assert len(set(declared)) == len(declared) == 22

    statements = app.TRANSFORM_SQL + app.CAUSES_SQL
    for name in declared:
        assert name in statements, f"{name} is declared but never read"


# --------------------------------------------------------------------------
# Both eras, through one mapping
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_both_eras_import_through_the_same_mapping(imported):
    engine, count = imported
    assert count == len(MODERN_FEATURES) + len(HISTORICAL_FEATURES) == 8

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 8
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8


@needs_ogr2ogr
def test_a_layer_that_publishes_two_attributes_imports(imported):
    """1975-1989 has Ano and AreaHaSIG and no other field at all."""
    engine, _ = imported
    with Session(engine) as session:
        old = session.scalars(
            select(IcnfWildfire).where(IcnfWildfire.source_layer == "ardida_1975_1989")
        ).all()
        assert len(old) == 2
        assert {row.year for row in old} == {1975, 1989}
        assert all(row.sgif_code is None and row.cause_id is None for row in old)
        assert all(row.duration_minutes is None and row.dicofre_code is None for row in old)


@needs_ogr2ogr
def test_the_missing_attributes_are_added_to_the_staging_table(database, boundaries,
                                                              time_zones, tmp_path,
                                                              connection_arguments, caplog):
    """The normalisation is what lets one mapping read a two-attribute layer."""
    write_archive(tmp_path, "ardida_1975_1989", HISTORICAL_FEATURES)
    args = app.parse_arguments(["-d", str(tmp_path), "--keep-staging", *connection_arguments])

    engine, _ = database
    with caplog.at_level(logging.INFO):
        app.import_wildfires(args, engine, logger)

    assert "does not publish 20 of the 22 known attributes" in caplog.text
    with Session(engine) as session:
        columns = set(session.scalars(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'staging' AND table_name = 'icnf_burnt_areas'"
        )).all())
    assert {name for name, _ in app.STAGING_COLUMNS} <= columns


@needs_ogr2ogr
def test_a_date_field_ogr2ogr_could_not_recognise_is_converted(database, boundaries,
                                                               time_zones, tmp_path,
                                                               connection_arguments):
    """A date column whose every value is empty arrives as text, not as a date.

    Nothing but a ``date`` can sit beside ``make_date`` in the ``COALESCE`` that
    produces the start instant, so the column is converted rather than cast.
    """
    write_archive(tmp_path, "ardida_2024",
                  [(attributes(Cod_SGIF="undated", AreaHaSIG=1.0), square(0, 0))])
    args = app.parse_arguments(["-d", str(tmp_path), "--keep-staging",
                                *connection_arguments])

    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 1

    with Session(engine) as session:
        types = dict(session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'staging' AND table_name = 'icnf_burnt_areas'"
        )).all())
        assert types["dh_inicio"] == "date"
        # numeric(9,0) as landed by ogr2ogr; make_date has no numeric overload.
        assert types["ano"] == "integer"

        undated = fire(session, "undated")
        assert undated.date_time_precision == icnf.PRECISION_YEAR
        assert undated.start_date_time == instant("2024-01-01T00:00:00+00:00")


@needs_ogr2ogr
def test_the_source_layer_is_recorded_on_every_row(imported):
    """The only provenance the identifier-less years have, and the re-import key."""
    engine, _ = imported
    with Session(engine) as session:
        layers = session.execute(
            select(IcnfWildfire.source_layer, func.count())
            .group_by(IcnfWildfire.source_layer)
        ).all()
    assert dict(layers) == {"ardida_2024": 6, "ardida_1975_1989": 2}


# --------------------------------------------------------------------------
# Dates, and how much of them the archives actually have
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_published_date_becomes_local_midnight_and_is_marked_day(imported):
    """Europe/Lisbon is UTC+0 in January, so this one is midnight UTC too."""
    engine, _ = imported
    with Session(engine) as session:
        winter = fire(session, "20240125102")
        assert winter.start_date_time == instant("2024-01-29T00:00:00+00:00")
        assert winter.time_zone == "Europe/Lisbon"
        assert winter.date_time_precision == icnf.PRECISION_DAY


@needs_ogr2ogr
def test_daylight_saving_is_resolved_from_the_date(imported):
    """Europe/Lisbon is UTC+1 in July: a fixed offset would put this an hour out."""
    engine, _ = imported
    with Session(engine) as session:
        summer = fire(session, "20240715001")
        assert summer.start_date_time == instant("2024-07-15T00:00:00+01:00")
        assert summer.start_date_time == instant("2024-07-14T23:00:00+00:00")


@needs_ogr2ogr
def test_a_layer_with_no_dates_falls_back_to_the_first_of_january(imported):
    """A placeholder for a NOT NULL column, and marked as one."""
    engine, _ = imported
    with Session(engine) as session:
        old = session.scalar(
            select(IcnfWildfire).where(IcnfWildfire.year == 1975))
        assert old.date_time_precision == icnf.PRECISION_YEAR
        assert old.start_date_time == instant("1975-01-01T00:00:00+01:00")
        assert old.end_date_time is None


@needs_ogr2ogr
def test_an_unmatched_perimeter_in_a_modern_layer_is_also_year_only(imported):
    """901 of the published 2014-2024 features have no record behind them."""
    engine, _ = imported
    with Session(engine) as session:
        unmatched = session.scalar(
            select(IcnfWildfire).where(IcnfWildfire.source_layer == "ardida_2024",
                                       IcnfWildfire.sgif_code.is_(None)))
        assert unmatched.year == 2024
        assert unmatched.date_time_precision == icnf.PRECISION_YEAR
        assert unmatched.start_date_time == instant("2024-01-01T00:00:00+00:00")
        assert unmatched.area_ha_gis == pytest.approx(0.05212912)


@needs_ogr2ogr
def test_the_end_is_the_last_second_of_its_day(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240125102").end_date_time == \
            instant("2024-01-29T23:59:59+00:00")


@needs_ogr2ogr
def test_the_first_response_time_is_stored(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240125102").first_response_date_time == \
            instant("2024-01-29T00:00:00+00:00")


@needs_ogr2ogr
def test_the_duration_survives_although_the_time_of_day_did_not(imported):
    """The one trace of the times the shapefile export threw away.

    This fire's stored dates are a day apart and its duration is 97 minutes:
    it burnt for an hour and a half across midnight, which is a thing only
    ``duration_minutes`` can still say.
    """
    engine, _ = imported
    with Session(engine) as session:
        crossing = fire(session, "20240715001")
        assert crossing.duration_minutes == 97
        assert (crossing.end_date_time - crossing.start_date_time).days == 1


@needs_ogr2ogr
def test_the_edition_date_is_stored(imported):
    """Provider bookkeeping, and the sign that a published year is still moving."""
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240125102").edition_date_time == \
            instant("2025-03-03T00:00:00+00:00")


@needs_ogr2ogr
def test_no_row_claims_more_precision_than_the_archives_have(imported):
    """Nothing read from a zip can be 'minute': only the WFS has the times."""
    engine, _ = imported
    with Session(engine) as session:
        precisions = set(session.scalars(select(IcnfWildfire.date_time_precision)))
    assert precisions == {icnf.PRECISION_YEAR, icnf.PRECISION_DAY}


# --------------------------------------------------------------------------
# The character set
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_portuguese_names_survive_the_import(imported):
    """No .cpg in the archive, so this is the importer's ENCODING doing the work."""
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "20240125102")
        assert stored.nuts3_name == "Viseu Dão Lafões"
        assert stored.municipality_name == "São Pedro do Sul"
        assert stored.parish_name == "União das freguesias de Carvalhais e Candal"
        assert stored.place_name == "Serra da Coelheira"
        assert "�" not in (stored.nuts3_name + stored.municipality_name)


@needs_ogr2ogr
def test_the_dicofre_code_keeps_its_leading_zeros(database, boundaries, time_zones,
                                                  tmp_path, connection_arguments):
    """A six-digit code read as a number would come back as five digits."""
    write_archive(tmp_path, "ardida_2024",
                  [(attributes(Cod_SGIF="x", PI_DICOFRE="030415"), square(0, 0))])
    args = app.parse_arguments(["-d", str(tmp_path), *connection_arguments])

    engine, _ = database
    app.import_wildfires(args, engine, logger)
    with Session(engine) as session:
        assert fire(session, "x").dicofre_code == "030415"


# --------------------------------------------------------------------------
# The geometry, stored twice
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_published_geometry_is_kept_in_the_national_grid(imported):
    engine, _ = imported
    with Session(engine) as session:
        srids = set(session.scalars(
            select(func.ST_SRID(IcnfWildfire.perimeter_etrs89_tm06))))
        types = set(session.scalars(
            select(func.GeometryType(IcnfWildfire.perimeter_etrs89_tm06))))
    assert srids == {3763}
    assert types == {"MULTIPOLYGON"}


@needs_ogr2ogr
def test_the_generic_perimeter_is_the_same_geometry_in_4326(imported):
    """Derived from the stored 3763 one in SQL, so the two cannot drift apart."""
    engine, _ = imported
    with Session(engine) as session:
        srids = set(session.scalars(select(func.ST_SRID(Wildfire.perimeter))))
        assert srids == {4326}

        # Joined inheritance already joins the two tables; naming Wildfire again
        # would be a second reference to the same one.
        mismatched = session.scalar(
            select(func.count())
            .select_from(IcnfWildfire)
            .where(~func.ST_Equals(
                func.ST_Transform(IcnfWildfire.perimeter_etrs89_tm06, 4326),
                Wildfire.perimeter))
        )
        assert mismatched == 0


@needs_ogr2ogr
def test_the_national_grid_measures_hectares_without_a_geodesic_function(imported):
    """The reason for keeping EPSG:3763: it is in metres, so ST_Area is an area."""
    engine, _ = imported
    with Session(engine) as session:
        area = session.scalar(
            select(func.ST_Area(IcnfWildfire.perimeter_etrs89_tm06))
            .where(IcnfWildfire.sgif_code == "20240125102"))
    # A 1000 m square is 100 ha.
    assert area / 10_000 == pytest.approx(100.0)


@needs_ogr2ogr
def test_an_invalid_perimeter_is_repaired(imported):
    """A bowtie is invalid as published; ST_MakeValid splits it into two triangles."""
    engine, _ = imported
    with Session(engine) as session:
        bowtie = fire(session, "20240900001")
        valid, parts = session.execute(
            select(func.ST_IsValid(IcnfWildfire.perimeter_etrs89_tm06),
                   func.ST_NumGeometries(IcnfWildfire.perimeter_etrs89_tm06))
            .where(IcnfWildfire.id == bowtie.id)
        ).one()
        assert valid is True
        assert parts == 2


@needs_ogr2ogr
def test_a_polygon_repaired_to_nothing_is_dropped_and_reported(database, boundaries,
                                                               time_zones, tmp_path,
                                                               connection_arguments, caplog):
    """A collinear ring has no area; ST_MakeValid leaves a line, not a polygon.

    Storing an empty multipolygon would satisfy the column and mean less than
    leaving the feature out, so it is left out — and said out loud, because a
    silent difference between features staged and fires imported is the kind of
    thing nobody notices for a year.
    """
    write_archive(tmp_path, "ardida_2024", [
        (attributes(Cod_SGIF="sound"), square(0, 0)),
        (attributes(Cod_SGIF="degenerate"),
         [[[30000.0, 30000.0], [31000.0, 30000.0], [32000.0, 30000.0], [30000.0, 30000.0]]]),
    ])
    args = app.parse_arguments(["-d", str(tmp_path), *connection_arguments])

    engine, _ = database
    with caplog.at_level(logging.WARNING):
        assert app.import_wildfires(args, engine, logger) == 1

    with Session(engine) as session:
        assert {row.sgif_code for row in session.scalars(select(IcnfWildfire))} == {"sound"}
    assert "1 of 2 feature(s) were not imported" in caplog.text


@needs_ogr2ogr
def test_every_stored_geometry_is_valid(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert all(session.scalars(select(func.ST_IsValid(Wildfire.perimeter))))
        assert all(session.scalars(
            select(func.ST_IsValid(IcnfWildfire.perimeter_etrs89_tm06))))


# --------------------------------------------------------------------------
# Country and zone
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_each_fire_gets_the_country_its_perimeter_falls_in(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240125102").admin_boundary.name == "Portugal"


@needs_ogr2ogr
def test_a_fire_outside_every_country_and_zone_still_imports(imported):
    """Both lookups are LEFT JOINs: the polygon and the dates are worth having."""
    engine, _ = imported
    with Session(engine) as session:
        atlantic = fire(session, "20240600001")
        assert atlantic.admin_boundary_id is None
        assert atlantic.time_zone is None
        # Falls back to the zone declared for the dataset rather than to nothing.
        assert atlantic.start_date_time == instant("2024-06-01T00:00:00+01:00")


@needs_ogr2ogr
def test_the_no_zones_warning_names_the_zone_this_dataset_falls_in(database, boundaries,
                                                                   args, caplog):
    """Not UTC: every layer is mainland Portugal, so the fallback is Europe/Lisbon."""
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        assert app.import_wildfires(args, engine, logger) == 8

    assert "dated in Europe/Lisbon" in caplog.text
    with Session(engine) as session:
        # No zone was resolved, but the instants are still Lisbon local midnight.
        assert fire(session, "20240715001").time_zone is None
        assert fire(session, "20240715001").start_date_time == \
            instant("2024-07-15T00:00:00+01:00")


@needs_ogr2ogr
def test_fires_import_without_any_boundaries(database, time_zones, args, caplog):
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 8
    assert "no country" in caplog.text

    with Session(engine) as session:
        assert all(row.admin_boundary_id is None for row in session.scalars(select(Wildfire)))


# --------------------------------------------------------------------------
# The cause lookup
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_causes_used_by_a_layer_are_stored_once(imported):
    engine, _ = imported
    with Session(engine) as session:
        codes = set(session.scalars(select(IcnfFireCause.code)))
    assert codes == {"122", "125", "998"}


@needs_ogr2ogr
def test_a_cause_carries_the_published_portuguese_and_the_english(imported):
    engine, _ = imported
    with Session(engine) as session:
        cause = session.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "125"))
        assert cause.type == "Negligente"
        assert cause.type_en == "Negligent"
        assert cause.description == "Queimadas para gestão de pasto para gado"
        assert cause.description_en == "Burning for livestock pasture management"


@needs_ogr2ogr
def test_the_fire_links_to_its_cause(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240125102").cause.code == "122"
        assert fire(session, "20240125102").cause.type_en == "Negligent"


@needs_ogr2ogr
def test_an_unclassified_fire_has_no_cause(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert fire(session, "20240900001").cause_id is None


@needs_ogr2ogr
def test_an_unknown_cause_is_stored_untranslated_and_reported(database, boundaries,
                                                              time_zones, args, caplog):
    """A category a later release invents must not be dropped, or guessed at."""
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        invented = session.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "998"))
        assert invented.type == "Categoria inventada"
        assert invented.type_en is None
        assert invented.description_en is None
        # It is still linked, so no fire loses its classification.
        assert fire(session, "20240800001").cause_id == invented.id

    assert "No English for 2 cause term(s)" in caplog.text
    assert "Categoria inventada" in caplog.text


@needs_ogr2ogr
def test_a_code_reused_across_layers_keeps_both_meanings(database, boundaries, time_zones,
                                                         tmp_path, connection_arguments,
                                                         caplog):
    """The real 126-129 case: same code, one meaning to 2024 and another in 2025.

    Conflicting on the code alone would drop the newer meaning and leave every
    2025 fire pointing at a description that stopped applying to it, which is why
    the key is the whole triple.
    """
    old = "Queimadas de sobrantes florestais ou agrícolas"
    new = "Queimadas extensivas - Limpeza de caminhos, acessos e instalações_"
    write_archive(tmp_path, "ardida_2024",
                  [(attributes(Cod_SGIF="before", Causa_Cod="127",
                               Causa_Tipo="Negligente", Causa_Desc=old), square(0, 0))])
    write_archive(tmp_path, "ardida_2025",
                  [(attributes(Ano=2025, Cod_SGIF="after", Causa_Cod="127",
                               Causa_Tipo="Negligente", Causa_Desc=new), square(10000, 0))])
    args = app.parse_arguments(["-d", str(tmp_path), *connection_arguments])

    engine, _ = database
    with caplog.at_level(logging.WARNING):
        assert app.import_wildfires(args, engine, logger) == 2

    with Session(engine) as session:
        causes = session.scalars(
            select(IcnfFireCause).where(IcnfFireCause.code == "127")).all()
        assert len(causes) == 2

        before, after = fire(session, "before"), fire(session, "after")
        assert before.cause_id != after.cause_id
        assert before.cause.description == old
        assert after.cause.description == new
        # Both are translated, so the reuse is not an excuse to lose the English.
        assert after.cause.description_en.startswith("Extensive burning")

    assert "name more than one classification" in caplog.text
    assert "127 x2" in caplog.text


@needs_ogr2ogr
def test_reimporting_does_not_rewrite_an_existing_cause(database, boundaries, time_zones,
                                                        modern_only, connection_arguments):
    """A translation added to the database by hand survives the next import."""
    engine, _ = database
    args = app.parse_arguments(["-d", str(modern_only), *connection_arguments])
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        invented = session.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "998"))
        invented.type_en = "Invented category"
        session.commit()

    args.replace = True
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        invented = session.scalar(select(IcnfFireCause).where(IcnfFireCause.code == "998"))
        assert invented.type_en == "Invented category"


# --------------------------------------------------------------------------
# The published attributes
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_areas_are_stored_as_published(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "20240125102")
        assert stored.area_ha_gis == pytest.approx(2.76886994)
        assert stored.area_ha_sgif == pytest.approx(2.76886994)
        assert stored.area_ha_forest_stand == pytest.approx(0.95900685)
        assert stored.area_ha_shrubland == pytest.approx(1.80986309)
        assert stored.area_ha_agricultural == pytest.approx(0.0)
        # The three land types add up to the SGIF area, as they do in the source.
        assert (stored.area_ha_forest_stand + stored.area_ha_shrubland
                + stored.area_ha_agricultural) == pytest.approx(stored.area_ha_sgif)


@needs_ogr2ogr
def test_both_identifiers_are_stored(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "20240715001")
        assert stored.sgif_code == "20240715001"
        assert stored.anepc_code == "2024010004987"


@needs_ogr2ogr
def test_the_administrative_location_is_stored(imported):
    engine, _ = imported
    with Session(engine) as session:
        stored = fire(session, "20240125102")
        assert stored.district_name == "Viseu"
        assert stored.dicofre_code == "181620"


# --------------------------------------------------------------------------
# Re-running an import
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_a_layer_already_imported_is_skipped(database, boundaries, time_zones, args, caplog):
    """No row-level key for 48,861 features, so the layer is the unit."""
    engine, _ = database
    assert app.import_wildfires(args, engine, logger) == 8

    with caplog.at_level(logging.INFO):
        assert app.import_wildfires(args, engine, logger) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 8
    assert "already imported" in caplog.text


@needs_ogr2ogr
def test_replace_reloads_a_revised_layer_without_duplicating_it(database, boundaries,
                                                                time_zones, args):
    """What to run when the ICNF revises a published year, which it does."""
    engine, _ = database
    app.import_wildfires(args, engine, logger)

    args.replace = True
    assert app.import_wildfires(args, engine, logger) == 8

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8
        # The parent rows went with the children: no orphans left behind.
        assert session.scalar(select(func.count()).select_from(Wildfire)) == 8


@needs_ogr2ogr
def test_replace_leaves_the_other_layers_alone(database, boundaries, time_zones,
                                               archives, connection_arguments):
    engine, _ = database
    app.import_wildfires(
        app.parse_arguments(["-d", str(archives), *connection_arguments]), engine, logger)

    one_layer = app.parse_arguments(
        ["-s", str(archives / "ardida_2024.zip"), "--replace", *connection_arguments])
    assert app.import_wildfires(one_layer, engine, logger) == 6

    with Session(engine) as session:
        assert session.scalar(
            select(func.count()).select_from(IcnfWildfire)
            .where(IcnfWildfire.source_layer == "ardida_1975_1989")) == 2
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8


@needs_ogr2ogr
def test_a_second_layer_adds_to_the_first(database, boundaries, time_zones,
                                          modern_only, connection_arguments):
    """The normal way to use it: a newly published year on top of the ones held."""
    engine, _ = database
    args = app.parse_arguments(["-d", str(modern_only), *connection_arguments])
    assert app.import_wildfires(args, engine, logger) == 6

    write_archive(modern_only, "ardida_1975_1989", HISTORICAL_FEATURES)
    assert app.import_wildfires(args, engine, logger) == 2

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8


# --------------------------------------------------------------------------
# Provider, staging, failure
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_data_provider_is_created_on_first_import(imported):
    engine, _ = imported
    with Session(engine) as session:
        provider = session.scalar(
            select(DataProvider).where(DataProvider.name == icnf.PROVIDER_NAME))
        assert provider.product == icnf.PROVIDER_PRODUCT
        assert provider.full_name == icnf.PROVIDER_FULL_NAME
        assert all(row.data_provider_id == provider.id
                   for row in session.scalars(select(Wildfire)))


@needs_ogr2ogr
def test_the_staging_table_is_dropped(imported):
    engine, _ = imported
    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.icnf_burnt_areas')")) is None


@needs_ogr2ogr
def test_the_staging_table_can_be_kept(database, boundaries, time_zones, args):
    args.keep_staging = True
    engine, _ = database
    app.import_wildfires(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT to_regclass('staging.icnf_burnt_areas')")) is not None


@needs_ogr2ogr
def test_an_unmigrated_database_is_reported_before_the_staging_load(database, args):
    engine, _ = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE icnf_wildfire"))

    with pytest.raises(RuntimeError, match="make migrate"):
        app.import_wildfires(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database, boundaries, time_zones,
                                    archives, connection_arguments):
    """The single command a user actually types."""
    engine, _ = database
    assert app.main(["-d", str(archives), *connection_arguments]) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IcnfWildfire)) == 8


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, archives,
                                                     connection_arguments, caplog):
    engine, _ = database
    (archives / "ardida_2020.zip").write_text("not an archive")
    exit_code = app.main(["-d", str(archives), *connection_arguments])
    assert exit_code == 1
    assert "Import failed" in caplog.text


def test_main_reports_a_missing_ogr2ogr(archives, connection_arguments, caplog):
    """A system dependency, so it is checked before anything slow happens."""
    exit_code = app.main(["-d", str(archives), "--ogr2ogr", "/nonexistent/ogr2ogr",
                          *connection_arguments])
    assert exit_code == 1
    assert "ogr2ogr not found" in caplog.text


def test_main_reports_missing_database_settings(archives, monkeypatch, caplog):
    """Neither the command line nor the environment says where to connect."""
    for variable in ("GISFIRE_DB_NAME", "GISFIRE_DB_USER"):
        monkeypatch.delenv(variable, raising=False)

    assert app.main(["-d", str(archives)]) == 1
    assert "No database" in caplog.text
