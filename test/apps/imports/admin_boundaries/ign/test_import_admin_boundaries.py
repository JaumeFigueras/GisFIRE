#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the IGN administrative boundary import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and six small shapefiles cut from the published dataset, so the whole
path is exercised — the subprocess, the staging tables, the two datums and the SQL
mapping.
"""

import logging
import shutil

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.admin_boundaries.ign import import_admin_boundaries as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import ign
from src.providers.ign.admin_boundary import IgnAdminBoundary
from src.settings import ROOT_DIR

#: Both published datums, cut to what one file cannot show on its own.
#:
#: ``SHP_ETRS89`` (EPSG:4258) holds La Rioja — one *comunidad autónoma*, one
#: *provincia*, 25 *municipios*, several with accented names — plus the whole
#: excluded branch: the pseudo *comunidad*, the pseudo *provincia* and all seven
#: ``Territorio`` areas, Gibraltar among them.
#:
#: ``SHP_REGCAN95`` (EPSG:4081) holds the Canaries clipped to the western islands:
#: one *comunidad*, the *provincia* of Santa Cruz de Tenerife, and 10 *municipios*
#: spread over **three** NUTS 3 regions — which is what makes the point that NUTS 3
#: refines a Spanish province rather than cutting across it.
SAMPLE_DIRECTORY = ROOT_DIR / "test" / "fixtures" / "data" / "ign_sample"

#: 2 comunidades + 2 provincias + 35 municipios, territories excluded.
SAMPLE_BOUNDARIES = 39

#: The nine rows of the excluded branch: 1 pseudo comunidad, 1 pseudo provincia,
#: 7 territorios.
SAMPLE_TERRITORIES = 9

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-ign-import")


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


def add_spain(engine) -> int:
    """Insert the OCHA country row the comunidades autónomas are meant to hang off."""
    with Session(engine) as session:
        provider = session.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('OCHA', 'Global International Boundaries - OSM', 'OCHA') RETURNING id"
        )).scalar()
        boundary = session.execute(text(
            "INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry) "
            "VALUES ('ocha_admin_boundary', :provider, 'ESP-20250729', 0, 'Spain', "
            "ST_GeomFromText('MULTIPOLYGON(((-19 27, -19 44, -1 44, -1 27, -19 27)))', 4326)) "
            "RETURNING id"
        ), {"provider": provider}).scalar()
        session.execute(text(
            "INSERT INTO ocha_admin_boundary (id, source, iso_code, iso_3, iso_name, iso_3_group, "
            "region1_code, region1_name, region2_code, region2_name, region3_code, region3_name, "
            "status_code, status_name, valid_date, update_date, land_source, view) "
            "VALUES (:id, 'ESP', 724, 'ESP', 'Spain', 'ESP', 150, 'Europe', 39, "
            "'Southern Europe', 0, '', 1, 'State', '2025-02-24', '2025-07-29', 'osm', 'intl')"
        ), {"id": boundary})
        session.commit()
    return boundary


# --------------------------------------------------------------------------
# Arguments and file discovery (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_directory_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-d", "bddae/"])
    assert parsed.directory == Path("bddae/")
    assert parsed.edition == ign.DEFAULT_EDITION == "2026"
    assert parsed.include_territories is False
    assert parsed.staging_schema == app.DEFAULT_STAGING_SCHEMA


def test_the_shapefiles_are_found_in_both_datums():
    found = app.find_shapefiles(SAMPLE_DIRECTORY)
    assert set(found) == set(app.FILENAME_MARKERS)
    for kind, paths in found.items():
        assert len(paths) == 2, f"{kind} should be published once per datum"
    # The peninsular file sorts before the Canary one, and both are the same level.
    assert [path.name for path in found[ign.KIND_MUNICIPIO]] == [
        "recintos_municipales_inspire_peninbal_etrs89.shp",
        "recintos_municipales_inspire_canarias_regcan95.shp",
    ]


def test_the_line_layers_are_not_picked_up(tmp_path):
    """``ll_*`` holds the boundary lines; only the ``recintos`` are areas."""
    (tmp_path / "ll_municipales_inspire_peninbal_etrs89.shp").touch()
    (tmp_path / "ll_provinciales_inspire_peninbal_etrs89.shp").touch()
    (tmp_path / "recintos_municipales_inspire_peninbal_etrs89.shp").touch()

    found = app.find_shapefiles(tmp_path)
    assert [path.name for path in found[ign.KIND_MUNICIPIO]] == [
        "recintos_municipales_inspire_peninbal_etrs89.shp"
    ]
    assert found[ign.KIND_PROVINCIA] == []


def test_a_directory_with_no_recintos_is_reported(tmp_path):
    (tmp_path / "ll_municipales_inspire_peninbal_etrs89.shp").touch()
    with pytest.raises(RuntimeError, match="No recintos shapefile"):
        app.find_shapefiles(tmp_path)


def test_the_model_says_what_it_is():
    boundary = IgnAdminBoundary(kind=ign.KIND_MUNICIPIO, source_id="34172626145", name="Sotés")
    assert repr(boundary) == ("IgnAdminBoundary(kind='municipio', "
                              "source_id='34172626145', name='Sotés')")


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent/bddae", "--db-name", "x", "--db-user", "y"]) == 1
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
# The import itself (real ogr2ogr, real PostGIS, real shapefiles)
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
        counts = dict(session.execute(text(
            "SELECT kind, count(*) FROM ign_admin_boundary GROUP BY kind"
        )).all())
        assert counts == {"comunidad_autonoma": 2, "provincia": 2, "municipio": 35}

        levels = dict(session.execute(text(
            "SELECT i.kind, min(b.level) FROM ign_admin_boundary i "
            "JOIN admin_boundary b ON b.id = i.id GROUP BY i.kind"
        )).all())
        assert levels == {"comunidad_autonoma": 1, "provincia": 2, "municipio": 3}


@needs_ogr2ogr
def test_gibraltar_is_not_imported(database, args):
    """The IGN maps it; it is not a Spanish administrative division."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(
            select(func.count()).select_from(AdminBoundary).where(AdminBoundary.name == "Gibraltar")
        ) == 0
        # Nor the pseudo comunidad and provincia that exist only to hold it.
        assert session.scalars(
            select(AdminBoundary.source_id).where(AdminBoundary.source_id.startswith("3420"))
        ).all() == []


@needs_ogr2ogr
def test_the_territories_can_be_asked_for(database, database_args):
    """Excluded by default, but the data is there for whoever wants it."""
    engine, _ = database
    with_territories = app.parse_arguments(
        ["-d", str(SAMPLE_DIRECTORY), "--include-territories", *database_args]
    )
    assert app.import_boundaries(with_territories, engine, logger) == (
        SAMPLE_BOUNDARIES + SAMPLE_TERRITORIES
    )

    with Session(engine) as session:
        gibraltar = session.scalar(
            select(IgnAdminBoundary).where(IgnAdminBoundary.name == "Gibraltar")
        )
        # Stored at municipal depth, but not called a municipality.
        assert gibraltar.kind == ign.KIND_TERRITORIO
        assert gibraltar.level == 3
        assert session.scalar(select(func.count()).select_from(IgnAdminBoundary).where(
            IgnAdminBoundary.kind == ign.KIND_TERRITORIO
        )) == 7


@needs_ogr2ogr
def test_the_tree_is_built_from_the_padded_codes(database, args):
    """A municipality's parent is its code with the last five digits zeroed, and so on up."""
    engine, _ = database
    add_spain(engine)
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        municipality = session.scalar(
            select(IgnAdminBoundary).where(IgnAdminBoundary.source_id == "34172626145")
        )
        assert municipality.name == "Sotés"
        assert municipality.parent.source_id == "34172600000"
        assert municipality.parent.name == "La Rioja"
        assert municipality.parent.parent.source_id == "34170000000"
        assert municipality.parent.parent.name == "La Rioja"
        # And above the IGN, the country, which comes from another provider.
        assert municipality.parent.parent.parent.name == "Spain"
        assert municipality.parent.parent.parent.level == 0


@needs_ogr2ogr
def test_the_canary_datum_nests_the_same_way(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        municipality = session.scalar(
            select(IgnAdminBoundary).where(IgnAdminBoundary.source_id == "34053838002")
        )
        assert municipality.name == "Agulo"
        assert municipality.parent.name == "Santa Cruz de Tenerife"
        assert municipality.parent.parent.name == "Canarias"


@needs_ogr2ogr
def test_the_fields_are_mapped(database, args):
    """A municipality, checked field by field against the published record."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        municipality = session.scalar(
            select(IgnAdminBoundary).where(IgnAdminBoundary.source_id == "34172626145")
        )
        assert municipality.name == "Sotés"
        assert municipality.level == 3
        assert municipality.kind == ign.KIND_MUNICIPIO
        assert municipality.edition == "2026"
        assert municipality.ine_code == "26145"
        assert (municipality.nuts1_code, municipality.nuts2_code, municipality.nuts3_code) == (
            "ES2", "ES23", "ES230"
        )
        assert municipality.name_en is None  # the IGN publishes no English names


@needs_ogr2ogr
def test_the_ine_code_is_the_tail_of_the_natcode_and_only_at_municipal_level(database, args):
    """Above a municipality those five digits are padding, not a code."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        for source_id, expected in (("34172626145", "26145"), ("34053838002", "38002")):
            assert session.scalar(select(IgnAdminBoundary.ine_code).where(
                IgnAdminBoundary.source_id == source_id
            )) == expected
        # Leading zeros survive: stored as text, not as a number.
        assert session.scalar(select(func.count()).select_from(IgnAdminBoundary).where(
            IgnAdminBoundary.ine_code == "00000"
        )) == 0
        assert session.scalars(select(IgnAdminBoundary.ine_code).where(
            IgnAdminBoundary.kind != ign.KIND_MUNICIPIO
        )).all() == [None] * 4


@needs_ogr2ogr
def test_nuts3_is_published_on_municipalities_only(database, args):
    """The IGN leaves it empty on provinces and comunidades, so it is NULL rather than derived."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        province = session.scalar(
            select(IgnAdminBoundary).where(IgnAdminBoundary.source_id == "34172600000")
        )
        assert (province.nuts1_code, province.nuts2_code) == ("ES2", "ES23")
        assert province.nuts3_code is None


@needs_ogr2ogr
def test_nuts3_refines_a_province_rather_than_crossing_it(database, args):
    """The property that let the NUTS codes be plain columns instead of a second tree.

    Santa Cruz de Tenerife is one province holding several NUTS 3 regions, one per
    island — and no NUTS 3 region reaches outside it. Portugal's is the other way
    round, which is why the CAOP import had to choose a hierarchy.
    """
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        regions = session.scalars(
            select(IgnAdminBoundary.nuts3_code)
            .where(IgnAdminBoundary.source_id.startswith("340538"),
                   IgnAdminBoundary.kind == ign.KIND_MUNICIPIO)
            .distinct()
        ).all()
        assert set(regions) == {"ES703", "ES706", "ES709"}

        # And every one of those regions stays inside the one province.
        crossing = session.execute(text(
            "SELECT nuts3_code FROM ign_admin_boundary i JOIN admin_boundary b ON b.id = i.id "
            "WHERE i.nuts3_code IS NOT NULL GROUP BY nuts3_code "
            "HAVING count(DISTINCT left(b.source_id, 6)) > 1"
        )).all()
        assert crossing == []


@needs_ogr2ogr
def test_the_nuts_placeholders_become_null(database, database_args):
    """A DBF has no NULL: an unfilled field arrives as ``''`` and a placeholder as ``'0'``.

    The excluded branch carries both — ``'0'`` on the pseudo comunidad, empty on the
    pseudo provincia — and neither should be sorted alongside real region codes.
    """
    engine, _ = database
    with_territories = app.parse_arguments(
        ["-d", str(SAMPLE_DIRECTORY), "--include-territories", *database_args]
    )
    app.import_boundaries(with_territories, engine, logger)

    with Session(engine) as session:
        for source_id in ("34200000000", "34205400000"):
            pseudo = session.scalar(
                select(IgnAdminBoundary).where(IgnAdminBoundary.source_id == source_id)
            )
            assert (pseudo.nuts1_code, pseudo.nuts2_code, pseudo.nuts3_code) == (None, None, None)


@needs_ogr2ogr
def test_accented_names_survive(database, args):
    """The shapefiles carry a UTF-8 ``.cpg``; read wrong, every accent is mangled silently."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        names = set(session.scalars(select(AdminBoundary.name)).all())
        assert {"Ábalos", "Cirueña", "Cordovín", "Alajeró"} <= names


@needs_ogr2ogr
def test_the_geometries_arrive_as_multipolygons_in_4326(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        srids = session.scalars(select(func.ST_SRID(AdminBoundary.geometry))).all()
        types = session.scalars(select(func.GeometryType(AdminBoundary.geometry))).all()
        assert set(srids) == {4326}
        assert set(types) == {"MULTIPOLYGON"}
        assert set(session.scalars(select(func.ST_IsValid(AdminBoundary.geometry))).all()) == {True}


@needs_ogr2ogr
def test_both_datums_land_in_the_right_place(database, args):
    """ETRS89 and REGCAN95 are different datums; La Rioja and La Gomera are 1 500 km apart."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        for source_id, longitude, latitude in (("34172600000", -2.5, 42.3),
                                               ("34053838002", -17.2, 28.2)):
            geometry = session.scalar(
                select(AdminBoundary.geometry).where(AdminBoundary.source_id == source_id)
            )
            point = session.execute(select(func.ST_X(func.ST_Centroid(geometry)),
                                           func.ST_Y(func.ST_Centroid(geometry)))).one()
            assert point[0] == pytest.approx(longitude, abs=0.3)
            assert point[1] == pytest.approx(latitude, abs=0.3)


@needs_ogr2ogr
def test_the_data_provider_names_the_edition(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider))
        assert provider.name == "IGN"
        assert provider.product == "Base de Datos de Divisiones Administrativas de España 2026"
        assert provider.full_name == "Instituto Geográfico Nacional"


@needs_ogr2ogr
def test_two_editions_live_side_by_side(database, args, database_args):
    """Spanish municipalities merge and split; the codes alone would collide."""
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == SAMPLE_BOUNDARIES

    older = app.parse_arguments(["-d", str(SAMPLE_DIRECTORY), "--edition", "2019", *database_args])
    assert app.import_boundaries(older, engine, logger) == SAMPLE_BOUNDARIES

    with Session(engine) as session:
        assert session.scalar(
            select(func.count()).select_from(AdminBoundary)
        ) == 2 * SAMPLE_BOUNDARIES
        assert len(session.scalars(select(DataProvider)).all()) == 2
        editions = session.scalars(select(IgnAdminBoundary.edition).where(
            IgnAdminBoundary.source_id == "34172626145"
        )).all()
        assert set(editions) == {"2019", "2026"}


@needs_ogr2ogr
def test_the_comunidades_are_rooted_when_no_country_is_imported(database, args, caplog):
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        roots = session.scalars(
            select(AdminBoundary.source_id).where(AdminBoundary.parent_id.is_(None))
        ).all()
        assert set(roots) == {"34170000000", "34050000000"}
    assert "No OCHA boundary for ESP" in caplog.text


@needs_ogr2ogr
def test_re_running_links_comunidades_to_a_country_imported_later(database, args):
    """``ON CONFLICT DO NOTHING`` cannot fix a parent, so the import relinks explicitly."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)
    spain = add_spain(engine)

    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        comunidades = session.scalars(
            select(AdminBoundary).where(AdminBoundary.level == 1)
        ).all()
        assert {comunidad.parent_id for comunidad in comunidades} == {spain}


@needs_ogr2ogr
def test_a_country_published_as_several_features_is_resolved_deterministically(database, args,
                                                                               caplog):
    """OCHA splits some countries into several level 0 rows sharing an ``iso_3``."""
    engine, _ = database
    first = add_spain(engine)
    with Session(engine) as session:
        second = session.execute(text(
            "INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry) "
            "SELECT 'ocha_admin_boundary', data_provider_id, 'ESP_2-20250729', 0, "
            "'Spain (Canaries)', geometry FROM admin_boundary WHERE id = :id RETURNING id"
        ), {"id": first}).scalar()
        session.execute(text(
            "INSERT INTO ocha_admin_boundary (id, source, iso_code, iso_3, iso_name, iso_3_group, "
            "region1_code, region1_name, region2_code, region2_name, region3_code, region3_name, "
            "status_code, status_name, valid_date, update_date, land_source, view) "
            "VALUES (:id, 'ESP', 724, 'ESP', 'Spain', 'ESP', 150, 'Europe', 39, "
            "'Southern Europe', 0, '', 1, 'State', '2025-02-24', '2025-07-29', 'osm', 'intl')"
        ), {"id": second})
        session.commit()

    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    assert "2 OCHA boundaries carry iso_3 = ESP" in caplog.text
    with Session(engine) as session:
        comunidades = session.scalars(select(AdminBoundary).where(AdminBoundary.level == 1)).all()
        # 'ESP-20250729' sorts before 'ESP_2-20250729'.
        assert {comunidad.parent_id for comunidad in comunidades} == {first}


@needs_ogr2ogr
def test_re_importing_is_idempotent(database, args):
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == SAMPLE_BOUNDARIES
    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        assert session.scalar(
            select(func.count()).select_from(AdminBoundary)
        ) == SAMPLE_BOUNDARIES
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
def test_the_staging_tables_gather_both_datums(database, args):
    """One table per level, holding what both publications contributed."""
    engine, _ = database
    args.keep_staging = True
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        # 32 peninsular rows (25 municipios + 7 territorios) plus 10 Canary ones,
        # staged before the exclusion is applied.
        assert session.scalar(text("SELECT count(*) FROM staging.ign_municipales")) == 42
        assert session.scalar(text("SELECT count(*) FROM staging.ign_autonomicas")) == 3


@needs_ogr2ogr
def test_a_broken_shapefile_is_reported(database, args, tmp_path):
    broken = tmp_path / "recintos_municipales_broken.shp"
    broken.write_text("this is not a shapefile")
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
        assert len(session.scalars(select(IgnAdminBoundary)).all()) == SAMPLE_BOUNDARIES


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, database_args, tmp_path):
    assert app.main(["-d", str(tmp_path), *database_args]) == 1
