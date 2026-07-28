#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the CAOP administrative boundary import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and two small GeoPackages cut from the published dataset, so the whole
path is exercised — the subprocess, the staging tables, the reprojection and the
SQL mapping. That is the point of them: a mocked ``ogr2ogr`` would test nothing
that matters here, least of all that two source CRSs come out as one.
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

from src.apps.imports.admin_boundaries.caop import import_admin_boundaries as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers import caop
from src.providers.caop.admin_boundary import CaopAdminBoundary
from src.settings import ROOT_DIR

#: Two territories cut from the published CAOP, chosen to exercise what one file
#: cannot: the mainland (EPSG:3763) as *distrito* Aveiro with the *município* of
#: Águeda and its fifteen *freguesias* — four of them 2013 mergers, whose
#: ``designacao_simplificada`` differs from their name — and the western Azores
#: (EPSG:5014) as the island of Corvo, one *município*, one *freguesia*. Two
#: files, two CRSs, all three levels in each.
SAMPLE_DIRECTORY = ROOT_DIR / "test" / "fixtures" / "data" / "caop_sample"
SAMPLE_CONTINENTE = SAMPLE_DIRECTORY / "Continente_CAOP2025.gpkg"
SAMPLE_ACORES = SAMPLE_DIRECTORY / "ArqAcores_GOcidental_CAOP2025.gpkg"

#: 2 distritos + 2 municípios + 16 freguesias.
SAMPLE_BOUNDARIES = 20

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-caop-import")


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
    """The ``--db-*`` arguments pointing at the ephemeral database.

    Separate from :func:`args` because several tests build a command line of their
    own — a different edition, a single file — and only the connection is shared.
    """
    _, info = database
    return ["--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user,
            "--db-password", info.password or ""]


@pytest.fixture
def args(database_args):
    """Command-line arguments pointing at the ephemeral database and the sample directory."""
    return app.parse_arguments(["--directory", str(SAMPLE_DIRECTORY), *database_args])


def add_portugal(engine) -> int:
    """Insert the OCHA country row the distritos are meant to hang off.

    Written straight in SQL rather than through the OCHA importer: what is being
    tested is that the CAOP import finds a level 0 boundary for ``PRT``, not how
    that boundary got there.
    """
    with Session(engine) as session:
        provider = session.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES ('OCHA', 'Global International Boundaries - OSM', 'OCHA') RETURNING id"
        )).scalar()
        boundary = session.execute(text(
            "INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry) "
            "VALUES ('ocha_admin_boundary', :provider, 'PRT-20250729', 0, 'Portugal', "
            "ST_GeomFromText('MULTIPOLYGON(((-9 37, -9 42, -6 42, -6 37, -9 37)))', 4326)) "
            "RETURNING id"
        ), {"provider": provider}).scalar()
        session.execute(text(
            "INSERT INTO ocha_admin_boundary (id, source, iso_code, iso_3, iso_name, iso_3_group, "
            "region1_code, region1_name, region2_code, region2_name, region3_code, region3_name, "
            "status_code, status_name, valid_date, update_date, land_source, view) "
            "VALUES (:id, 'PRT', 620, 'PRT', 'Portugal', 'PRT', 150, 'Europe', 39, "
            "'Southern Europe', 0, '', 1, 'State', '2025-02-24', '2025-07-29', 'osm', 'intl')"
        ), {"id": boundary})
        session.commit()
    return boundary


# --------------------------------------------------------------------------
# Arguments and file discovery (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_a_source_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_the_two_sources_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        app.parse_arguments(["-d", "caop/", "-g", "Continente.gpkg"])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-d", "caop/"])
    assert parsed.directory == Path("caop/")
    assert parsed.edition == caop.DEFAULT_EDITION
    assert parsed.staging_schema == app.DEFAULT_STAGING_SCHEMA
    assert parsed.keep_staging is False


def test_a_directory_yields_every_geopackage_sorted():
    found = app.find_geopackages(app.parse_arguments(["-d", str(SAMPLE_DIRECTORY)]))
    assert found == sorted([SAMPLE_ACORES, SAMPLE_CONTINENTE])


def test_a_single_geopackage_is_imported_on_its_own():
    found = app.find_geopackages(app.parse_arguments(["-g", str(SAMPLE_CONTINENTE)]))
    assert found == [SAMPLE_CONTINENTE]


def test_an_empty_directory_is_reported(tmp_path):
    with pytest.raises(RuntimeError, match="No GeoPackage"):
        app.find_geopackages(app.parse_arguments(["-d", str(tmp_path)]))


def test_the_layers_are_discovered_by_suffix():
    """The DGT prefixes layers with the territory, so only the suffix identifies a level."""
    assert app.discover_layers(SAMPLE_CONTINENTE) == {
        caop.KIND_DISTRITO: "cont_distritos",
        caop.KIND_MUNICIPIO: "cont_municipios",
        caop.KIND_FREGUESIA: "cont_freguesias",
    }
    # A different file, the same three levels, a different prefix throughout.
    assert app.discover_layers(SAMPLE_ACORES)[caop.KIND_FREGUESIA] == "raa_oci_freguesias"


def test_a_file_that_is_not_a_geopackage_is_reported(tmp_path):
    broken = tmp_path / "broken.gpkg"
    broken.write_text("this is not a GeoPackage")
    with pytest.raises(RuntimeError, match="cannot be read as a GeoPackage"):
        app.discover_layers(broken)


def test_a_geopackage_missing_a_level_is_refused(tmp_path):
    """Two of the three levels would build a tree with a rung missing from the middle."""
    import sqlite3

    incomplete = tmp_path / "incomplete.gpkg"
    shutil.copy(SAMPLE_CONTINENTE, incomplete)
    connection = sqlite3.connect(incomplete)
    connection.execute("DELETE FROM gpkg_contents WHERE table_name = 'cont_municipios'")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="_municipios"):
        app.discover_layers(incomplete)


def test_a_file_named_for_another_edition_is_flagged(caplog):
    """Importing 2024's files as 2025 would merge two versions of Portugal into one."""
    with caplog.at_level(logging.WARNING):
        app.check_edition([Path("Continente_CAOP2024.gpkg")], "2025", logger)
    assert "--edition 2024" in caplog.text


def test_the_edition_in_the_file_name_is_not_flagged_when_it_agrees(caplog):
    with caplog.at_level(logging.WARNING):
        app.check_edition([SAMPLE_CONTINENTE, SAMPLE_ACORES], "2025", logger)
    assert caplog.text == ""


def test_the_model_says_what_it_is(database, args):
    boundary = CaopAdminBoundary(kind=caop.KIND_FREGUESIA, source_id="010103",
                                 name="Aguada de Cima")
    assert repr(boundary) == ("CaopAdminBoundary(kind='freguesia', source_id='010103', "
                              "name='Aguada de Cima')")


def test_main_reports_missing_database_settings(monkeypatch, caplog):
    monkeypatch.delenv("GISFIRE_DB_NAME", raising=False)
    monkeypatch.delenv("GISFIRE_DB_USER", raising=False)

    assert app.main(["-d", str(SAMPLE_DIRECTORY)]) == 1
    assert "No database" in caplog.text


def test_main_reports_a_missing_directory(caplog):
    assert app.main(["-d", "/nonexistent/caop", "--db-name", "x", "--db-user", "y"]) == 1
    assert "not found" in caplog.text


def test_main_reports_a_missing_ogr2ogr(caplog):
    exit_code = app.main(["-d", str(SAMPLE_DIRECTORY), "--db-name", "x", "--db-user", "y",
                          "--ogr2ogr", "/nonexistent/ogr2ogr"])
    assert exit_code == 1
    assert "GDAL" in caplog.text


# --------------------------------------------------------------------------
# The import itself (real ogr2ogr, real PostGIS, real GeoPackages)
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
            "SELECT kind, count(*) FROM caop_admin_boundary GROUP BY kind"
        )).all())
        assert counts == {"distrito": 2, "municipio": 2, "freguesia": 16}

        levels = dict(session.execute(text(
            "SELECT c.kind, min(b.level) FROM caop_admin_boundary c "
            "JOIN admin_boundary b ON b.id = c.id GROUP BY c.kind"
        )).all())
        assert levels == {"distrito": 1, "municipio": 2, "freguesia": 3}


@needs_ogr2ogr
def test_the_tree_is_built_from_the_codes(database, args):
    """A parish's parent is the município its code starts with, and so on up."""
    engine, _ = database
    add_portugal(engine)
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        parish = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "010103")
        )
        assert parish.name == "Aguada de Cima"
        assert parish.parent.source_id == "0101"
        assert parish.parent.name == "Águeda"
        assert parish.parent.parent.source_id == "01"
        assert parish.parent.parent.name == "Aveiro"
        # And above the CAOP, the country, which comes from another provider.
        assert parish.parent.parent.parent.name == "Portugal"
        assert parish.parent.parent.parent.level == 0


@needs_ogr2ogr
def test_the_island_is_parented_the_same_way(database, args):
    """The Azores file is a different prefix and a different CRS, and nests identically."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        parish = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "490101")
        )
        assert parish.name == "Corvo"
        assert parish.parent.source_id == "4901"
        assert parish.parent.parent.name == "Ilha do Corvo"


@needs_ogr2ogr
def test_the_distritos_are_rooted_when_no_country_is_imported(database, args, caplog):
    """The divisions are worth having on their own; the country can come later."""
    engine, _ = database
    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        roots = session.scalars(
            select(AdminBoundary).where(AdminBoundary.parent_id.is_(None))
        ).all()
        assert {root.source_id for root in roots} == {"01", "49"}
    assert "No OCHA boundary for PRT" in caplog.text


@needs_ogr2ogr
def test_re_running_links_distritos_to_a_country_imported_later(database, args):
    """``ON CONFLICT DO NOTHING`` cannot fix a parent, so the import relinks explicitly."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)
    portugal = add_portugal(engine)

    # Nothing new to insert, but the 29 rooted distritos now have somewhere to hang.
    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        distritos = session.scalars(
            select(AdminBoundary).where(AdminBoundary.level == 1)
        ).all()
        assert {distrito.parent_id for distrito in distritos} == {portugal}


@needs_ogr2ogr
def test_one_territory_can_be_imported_on_its_own(database, database_args):
    """Each published file holds all three of its own levels, so ``-g`` is self-contained."""
    engine, _ = database
    single = app.parse_arguments(["-g", str(SAMPLE_ACORES), *database_args])
    assert app.import_boundaries(single, engine, logger) == 3

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminBoundary)) == 3
        parish = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.kind == caop.KIND_FREGUESIA)
        )
        assert parish.parent.parent.source_id == "49"


@needs_ogr2ogr
def test_a_country_published_as_several_features_is_resolved_deterministically(database, args,
                                                                               caplog):
    """OCHA splits some countries into several level 0 rows sharing an ``iso_3``.

    Portugal is one feature today, but the French Southern Territories are two, so
    the case is real for the dataset. Picking the first by ``source_id`` means two
    runs of the import cannot disagree about which one the distritos hang off.
    """
    engine, _ = database
    first = add_portugal(engine)
    with Session(engine) as session:
        second = session.execute(text(
            "INSERT INTO admin_boundary (type, data_provider_id, source_id, level, name, geometry) "
            "SELECT 'ocha_admin_boundary', data_provider_id, 'PRT_2-20250729', 0, "
            "'Portugal (Azores)', geometry FROM admin_boundary WHERE id = :id RETURNING id"
        ), {"id": first}).scalar()
        session.execute(text(
            "INSERT INTO ocha_admin_boundary (id, source, iso_code, iso_3, iso_name, iso_3_group, "
            "region1_code, region1_name, region2_code, region2_name, region3_code, region3_name, "
            "status_code, status_name, valid_date, update_date, land_source, view) "
            "VALUES (:id, 'PRT', 620, 'PRT', 'Portugal', 'PRT', 150, 'Europe', 39, "
            "'Southern Europe', 0, '', 1, 'State', '2025-02-24', '2025-07-29', 'osm', 'intl')"
        ), {"id": second})
        session.commit()

    with caplog.at_level(logging.WARNING):
        app.import_boundaries(args, engine, logger)

    assert "2 OCHA boundaries carry iso_3 = PRT" in caplog.text
    with Session(engine) as session:
        distritos = session.scalars(select(AdminBoundary).where(AdminBoundary.level == 1)).all()
        # 'PRT-20250729' sorts before 'PRT_2-20250729'.
        assert {distrito.parent_id for distrito in distritos} == {first}


@needs_ogr2ogr
def test_the_fields_are_mapped(database, args):
    """A freguesia, checked field by field against the published record."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        parish = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "010103")
        )
        assert parish.name == "Aguada de Cima"
        assert parish.level == 3
        assert parish.kind == caop.KIND_FREGUESIA
        assert parish.edition == "2025"
        assert parish.name_simplified == "Aguada de Cima"
        assert (parish.nuts3_code, parish.nuts3_name) == ("191", "Região de Aveiro")
        assert parish.nuts2_name == "Centro"
        assert parish.nuts1_name == "Continente"
        assert parish.nuts1_code is None  # published on the distritos layer only
        assert parish.area_ha == pytest.approx(2839.31)
        assert parish.perimeter_km == 24
        assert parish.name_en is None  # the CAOP publishes no English names


@needs_ogr2ogr
def test_a_2013_merger_keeps_both_forms_of_its_name(database, args):
    """The full name and the short one differ for 635 parishes; both are worth having."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        merged = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "010124")
        )
        assert merged.name == "União das freguesias de Recardães e Espinhel"
        assert merged.name_simplified == "Recardães e Espinhel"


@needs_ogr2ogr
def test_a_distrito_carries_the_nuts1_code_and_no_finer_region(database, args):
    """NUTS 3 crosses distrito boundaries, so a distrito cannot be assigned one."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        aveiro = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "01")
        )
        assert aveiro.kind == caop.KIND_DISTRITO
        assert (aveiro.nuts1_code, aveiro.nuts1_name) == ("1", "Continente")
        assert aveiro.nuts2_name is None
        assert aveiro.nuts3_code is None
        assert aveiro.nuts3_name is None
        assert aveiro.name_simplified is None  # freguesias only


@needs_ogr2ogr
def test_a_municipio_carries_the_whole_nuts_chain(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        agueda = session.scalar(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "0101")
        )
        assert agueda.kind == caop.KIND_MUNICIPIO
        assert (agueda.nuts3_code, agueda.nuts3_name) == ("191", "Região de Aveiro")
        assert (agueda.nuts2_name, agueda.nuts1_name) == ("Centro", "Continente")
        assert agueda.nuts1_code is None


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
def test_the_two_source_crss_both_land_in_the_right_place(database, args):
    """3763 and 5014 are different projections; getting one wrong misplaces a territory.

    Águeda is on the mainland near 8.4°W, Corvo 2 000 km west in the Atlantic near
    31.1°W. A file reprojected from the wrong CRS would put one of them somewhere
    else entirely, which no count or type check would notice.
    """
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        for source_id, longitude, latitude in (("0101", -8.4, 40.6), ("4901", -31.1, 39.7)):
            boundary = session.scalar(
                select(AdminBoundary).where(AdminBoundary.source_id == source_id)
            )
            point = session.execute(
                select(func.ST_X(func.ST_Centroid(boundary.geometry)),
                       func.ST_Y(func.ST_Centroid(boundary.geometry)))
            ).one()
            assert point[0] == pytest.approx(longitude, abs=0.2)
            assert point[1] == pytest.approx(latitude, abs=0.2)


@needs_ogr2ogr
def test_the_data_provider_names_the_edition(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider))
        assert provider.name == "DGT"
        assert provider.product == "Carta Administrativa Oficial de Portugal 2025"
        assert provider.full_name == "Direção-Geral do Território"


@needs_ogr2ogr
def test_two_editions_live_side_by_side(database, args, database_args):
    """The codes repeat between editions; the provider is what keeps them apart.

    Without this, importing CAOP 2024 after CAOP 2025 would silently import
    nothing at all — every code would collide on
    ``uq_admin_boundary_provider_source`` and be skipped.
    """
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == SAMPLE_BOUNDARIES

    older = app.parse_arguments(["-d", str(SAMPLE_DIRECTORY), "--edition", "2024",
                                 *database_args])
    assert app.import_boundaries(older, engine, logger) == SAMPLE_BOUNDARIES

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminBoundary)) == 2 * SAMPLE_BOUNDARIES
        assert len(session.scalars(select(DataProvider)).all()) == 2
        # Both editions hold the same parish, each under its own provider.
        parishes = session.scalars(
            select(CaopAdminBoundary).where(CaopAdminBoundary.source_id == "010103")
        ).all()
        assert {parish.edition for parish in parishes} == {"2024", "2025"}


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
def test_the_staging_tables_can_be_kept(database, args):
    """One table per level, gathering every territory — 16 parishes from two files."""
    engine, _ = database
    args.keep_staging = True
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT count(*) FROM staging.caop_freguesias")) == 16
        assert session.scalar(text("SELECT count(*) FROM staging.caop_distritos")) == 2


@needs_ogr2ogr
def test_a_broken_geopackage_is_reported(database, args, tmp_path):
    broken = tmp_path / "broken.gpkg"
    broken.write_text("this is not a GeoPackage")
    args.directory = tmp_path
    args.geopackage = None

    engine, _ = database
    with pytest.raises(RuntimeError, match="cannot be read as a GeoPackage"):
        app.import_boundaries(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database, database_args):
    """The single command a user actually types."""
    engine, _ = database
    assert app.main(["-d", str(SAMPLE_DIRECTORY), *database_args]) == 0

    with Session(engine) as session:
        assert len(session.scalars(select(CaopAdminBoundary)).all()) == SAMPLE_BOUNDARIES


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, database_args, tmp_path):
    assert app.main(["-d", str(tmp_path), *database_args]) == 1
