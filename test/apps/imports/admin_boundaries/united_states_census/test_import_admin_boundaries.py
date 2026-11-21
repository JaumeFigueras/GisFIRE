"""Tests for the US Census Bureau administrative boundary import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and the two published zips cut to four states (see the sample's
README), so the whole path is exercised: the zips read in place, the staging
tables, the territory filter and the SQL mapping.
"""

import logging
import shutil
import zipfile

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.admin_boundaries.united_states_census import import_admin_boundaries as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import united_states_census as census
from src.providers.united_states_census.admin_boundary import CensusAdminBoundary
from src.settings import ROOT_DIR

#: Delaware, DC and Rhode Island with their counties, and Guam with its one.
SAMPLE_DIRECTORY = ROOT_DIR / "test" / "fixtures" / "data" / "census_sample"

#: 3 states + 9 counties; Guam and its county are left out.
SAMPLE_BOUNDARIES = 12

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-census-import")


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
def database_args(database):
    """The ``--db-*`` arguments pointing at the ephemeral database."""
    _, info = database
    return ["--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user,
            "--db-password", info.password or ""]


@pytest.fixture
def args(database_args):
    """Command-line arguments pointing at the ephemeral database and the sample directory."""
    return app.parse_arguments(["--directory", str(SAMPLE_DIRECTORY), *database_args])


def add_usa(engine, source_id: str = "USA-20250729", name: str = "United States of America",
            provider: int | None = None) -> int:
    """Insert an OCHA country row for the United States; its ``admin_boundary`` id."""
    with Session(engine) as session:
        if provider is None:
            provider = session.execute(text(
                "INSERT INTO data_provider (name, product, full_name) "
                "VALUES ('OCHA', 'Global International Boundaries - OSM', 'OCHA') RETURNING id"
            )).scalar()
        boundary = session.execute(text(
            "INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry) "
            "VALUES ('ocha_admin_boundary', :provider, :source_id, 0, :name, "
            "ST_GeomFromText('MULTIPOLYGON(((-125 24, -125 50, -66 50, -66 24, -125 24)))', 4326)) "
            "RETURNING id"
        ), {"provider": provider, "source_id": source_id, "name": name}).scalar()
        session.execute(text(
            "INSERT INTO ocha_admin_boundary (id, source, iso_code, iso_3, iso_name, iso_3_group, "
            "region1_code, region1_name, region2_code, region2_name, region3_code, region3_name, "
            "status_code, status_name, valid_date, update_date, land_source, view) "
            "VALUES (:id, 'USA', 840, 'USA', 'United States of America', 'USA', 19, 'Americas', "
            "21, 'Northern America', 0, '', 1, 'State', '2025-02-24', '2025-07-29', 'osm', 'intl')"
        ), {"id": boundary})
        session.commit()
    return boundary


def boundary(session: Session, geoid: str) -> CensusAdminBoundary:
    """The imported boundary of one GEOID."""
    return session.scalar(select(CensusAdminBoundary).where(CensusAdminBoundary.source_id == geoid))


# --------------------------------------------------------------------------
# Arguments and file discovery (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_directory_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-d", "census/"])
    assert parsed.directory == Path("census/")
    assert parsed.edition == census.DEFAULT_EDITION == "2025"
    assert parsed.staging_schema == app.DEFAULT_STAGING_SCHEMA


def test_the_files_are_named_after_the_edition():
    assert census.file_name("2025", census.KIND_STATE) == "cb_2025_us_state_500k"
    assert census.file_name("2024", census.KIND_COUNTY) == "cb_2024_us_county_500k"
    assert census.provider_product("2025") == "Cartographic Boundary Files 2025, 1:500,000"


def test_the_zips_are_found():
    assert app.find_files(SAMPLE_DIRECTORY, "2025") == {
        census.KIND_STATE: SAMPLE_DIRECTORY / "cb_2025_us_state_500k.zip",
        census.KIND_COUNTY: SAMPLE_DIRECTORY / "cb_2025_us_county_500k.zip",
    }


def test_an_unpacked_shapefile_is_found_and_a_zip_preferred(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "cb_2025_us_state_500k.shp").touch()
    (tmp_path / "cb_2025_us_county_500k.shp").touch()
    (tmp_path / "cb_2025_us_county_500k.zip").touch()

    assert app.find_files(tmp_path, "2025") == {
        census.KIND_STATE: tmp_path / "state" / "cb_2025_us_state_500k.shp",
        census.KIND_COUNTY: tmp_path / "cb_2025_us_county_500k.zip",
    }


def test_another_edition_is_not_picked_up():
    """The file names carry the year, so a wrong ``--edition`` finds nothing."""
    with pytest.raises(RuntimeError, match="Is --edition 2024 the edition downloaded"):
        app.find_files(SAMPLE_DIRECTORY, "2024")


def test_two_copies_of_a_file_are_refused(tmp_path):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "cb_2025_us_state_500k.zip").touch()
    with pytest.raises(RuntimeError, match="2 files named cb_2025_us_state_500k.zip"):
        app.find_files(tmp_path, "2025")


def test_the_model_says_what_it_is():
    county = CensusAdminBoundary(kind=census.KIND_COUNTY, source_id="02020", name="Anchorage")
    assert repr(county) == ("CensusAdminBoundary(kind='county', source_id='02020', "
                            "name='Anchorage')")


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent/census", "--db-name", "x", "--db-user", "y"]) == 1
    assert "not found" in caplog.text


def test_main_reports_missing_database_settings(monkeypatch, caplog):
    monkeypatch.delenv("GISFIRE_DB_NAME", raising=False)
    monkeypatch.delenv("GISFIRE_DB_USER", raising=False)

    assert app.main(["-d", str(SAMPLE_DIRECTORY)]) == 1
    assert "No database" in caplog.text


def test_main_reports_a_missing_ogr2ogr(caplog):
    exit_code = app.main(["-d", str(SAMPLE_DIRECTORY), "--db-name", "x", "--db-user", "y",
                          "--ogr2ogr", "/nonexistent/ogr2ogr"])
    assert exit_code == 1
    assert "GDAL" in caplog.text


# --------------------------------------------------------------------------
# The import itself (real ogr2ogr, real PostGIS, real files)
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_sample_is_imported(database, args):
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == SAMPLE_BOUNDARIES


@needs_ogr2ogr
def test_each_level_lands_at_its_own_depth(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        levels = session.execute(text(
            "SELECT c.kind, b.level, count(*) FROM census_admin_boundary c "
            "JOIN admin_boundary b ON b.id = c.id GROUP BY c.kind, b.level"
        )).all()
        assert sorted(levels) == [("county", 2, 9), ("state", 1, 3)]


@needs_ogr2ogr
def test_the_territories_are_not_imported(database, args):
    """Guam is a country of its own in OCHA's boundaries."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalars(select(AdminBoundary.name).where(
            AdminBoundary.source_id.in_(["66", "66010"])
        )).all() == []
        assert set(session.scalars(select(AdminBoundary.source_id).where(
            AdminBoundary.level == 1
        )).all()) == {"10", "11", "44"}


@needs_ogr2ogr
def test_a_county_hangs_off_its_state_by_code(database, args):
    """Delaware and Rhode Island both have a Kent County; the code tells them apart."""
    engine, _ = database
    usa = add_usa(engine)
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        for geoid, state in (("10001", "Delaware"), ("44003", "Rhode Island")):
            county = boundary(session, geoid)
            assert county.name == "Kent"
            assert county.parent.name == state
            assert county.parent.source_id == geoid[:2]
            # And above the Census, the country, which comes from another provider.
            assert county.parent.parent_id == usa
            assert county.parent.parent.level == 0


@needs_ogr2ogr
def test_the_fields_are_mapped(database, args):
    """A county and a state, checked field by field against the published records."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        county = boundary(session, "44007")
        assert (county.name, county.name_en) == ("Providence", "Providence")
        assert (county.kind, county.level, county.lsad) == (census.KIND_COUNTY, 2, "06")
        assert county.edition == "2025"

        state = boundary(session, "11")
        assert (state.name, state.name_en) == ("District of Columbia", "District of Columbia")
        assert (state.kind, state.level, state.lsad) == (census.KIND_STATE, 1, "00")
        # DC's one county equivalent has no other description either.
        assert boundary(session, "11001").lsad == "00"


@needs_ogr2ogr
def test_the_geometries_arrive_as_multipolygons_in_4326(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert set(session.scalars(select(func.ST_SRID(AdminBoundary.geometry))).all()) == {4326}
        assert set(session.scalars(select(func.GeometryType(AdminBoundary.geometry))).all()) == {
            "MULTIPOLYGON"}
        assert set(session.scalars(select(func.ST_IsValid(AdminBoundary.geometry))).all()) == {True}


@needs_ogr2ogr
def test_the_boundaries_land_in_the_right_place(database, args):
    """NAD83 to WGS 84 moves nothing that matters: Rhode Island is where it should be."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        geometry = select(AdminBoundary.geometry).where(AdminBoundary.source_id == "44")
        x, y = session.execute(select(func.ST_X(func.ST_Centroid(geometry.scalar_subquery())),
                                      func.ST_Y(func.ST_Centroid(geometry.scalar_subquery())))).one()
        assert (x, y) == (pytest.approx(-71.5, abs=0.2), pytest.approx(41.6, abs=0.2))
        # The counties tile their state.
        area = session.scalar(text(
            "SELECT abs(ST_Area(s.geometry::geography) "
            "           - (SELECT sum(ST_Area(c.geometry::geography)) FROM admin_boundary c "
            "              WHERE c.parent_id = s.id)) / ST_Area(s.geometry::geography) "
            "FROM admin_boundary s WHERE s.source_id = '44' AND s.level = 1"
        ))
        assert area < 0.001


@needs_ogr2ogr
def test_the_data_provider_names_the_edition(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider))
        assert provider.name == "US Census Bureau"
        assert provider.product == "Cartographic Boundary Files 2025, 1:500,000"
        assert provider.full_name == "United States Census Bureau"


@needs_ogr2ogr
def test_two_editions_live_side_by_side(database, database_args, tmp_path):
    """Counties change (Connecticut's in 2022), so each year is a provider of its own."""
    engine, _ = database
    for kind in census.KINDS:
        name = census.file_name("2025", kind)
        with zipfile.ZipFile(SAMPLE_DIRECTORY / f"{name}.zip") as source, \
                zipfile.ZipFile(tmp_path / f"{census.file_name('2024', kind)}.zip", "w") as copy:
            for member in source.namelist():
                copy.writestr(member.replace(name, census.file_name("2024", kind)),
                              source.read(member))

    for directory, edition in ((SAMPLE_DIRECTORY, "2025"), (tmp_path, "2024")):
        parsed = app.parse_arguments(["-d", str(directory), "--edition", edition, *database_args])
        assert app.import_boundaries(parsed, engine, logger) == SAMPLE_BOUNDARIES

    with Session(engine) as session:
        assert len(session.scalars(select(DataProvider)).all()) == 2
        assert set(session.scalars(select(CensusAdminBoundary.edition).where(
            CensusAdminBoundary.source_id == "10001")).all()) == {"2024", "2025"}


@needs_ogr2ogr
def test_the_states_are_rooted_when_no_country_is_imported(database, args, caplog):
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        roots = session.scalars(
            select(AdminBoundary.source_id).where(AdminBoundary.parent_id.is_(None))
        ).all()
        assert set(roots) == {"10", "11", "44"}
    assert "No OCHA boundary for USA" in caplog.text


@needs_ogr2ogr
def test_re_running_links_the_states_to_a_country_imported_later(database, args):
    """``ON CONFLICT DO NOTHING`` cannot fix a parent, so the import relinks explicitly."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)
    usa = add_usa(engine)

    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        assert set(session.scalars(select(AdminBoundary.parent_id).where(
            AdminBoundary.level == 1)).all()) == {usa}


@needs_ogr2ogr
def test_a_country_published_as_several_features_is_resolved_deterministically(database, args,
                                                                               caplog):
    engine, _ = database
    first = add_usa(engine)
    with Session(engine) as session:
        provider = session.scalar(select(AdminBoundary.data_provider_id).where(
            AdminBoundary.id == first))
    add_usa(engine, source_id="USA_2-20250729", name="United States (Alaska)", provider=provider)

    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    assert "2 OCHA boundaries carry iso_3 = USA" in caplog.text
    with Session(engine) as session:
        # 'USA-20250729' sorts before 'USA_2-20250729'.
        assert set(session.scalars(select(AdminBoundary.parent_id).where(
            AdminBoundary.level == 1)).all()) == {first}


@needs_ogr2ogr
def test_re_importing_is_idempotent(database, args):
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == SAMPLE_BOUNDARIES
    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminBoundary)) == SAMPLE_BOUNDARIES
        assert len(session.scalars(select(DataProvider)).all()) == 1


@needs_ogr2ogr
def test_the_staging_tables_are_dropped(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        for table in app.STAGING_TABLES.values():
            assert session.scalar(text("SELECT to_regclass(:table)"),
                                  {"table": f"staging.{table}"}) is None


@needs_ogr2ogr
def test_the_staging_tables_hold_the_territories_too(database, args):
    """The territories are staged, and left out when mapped."""
    engine, _ = database
    args.keep_staging = True
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT count(*) FROM staging.census_states")) == 4
        assert session.scalar(text("SELECT count(*) FROM staging.census_counties")) == 10


@needs_ogr2ogr
def test_a_broken_file_is_reported(database, args, tmp_path):
    for kind in census.KINDS:
        (tmp_path / f"{census.file_name('2025', kind)}.shp").write_text("this is not a shapefile")
    args.directory = tmp_path

    engine, _ = database
    with pytest.raises(RuntimeError, match="ogr2ogr failed"):
        app.import_boundaries(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database, database_args):
    """The single command a user actually types."""
    engine, _ = database
    assert app.main(["-d", str(SAMPLE_DIRECTORY), *database_args]) == 0

    with Session(engine) as session:
        assert len(session.scalars(select(CensusAdminBoundary)).all()) == SAMPLE_BOUNDARIES


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, database_args, tmp_path):
    assert app.main(["-d", str(tmp_path), *database_args]) == 1
