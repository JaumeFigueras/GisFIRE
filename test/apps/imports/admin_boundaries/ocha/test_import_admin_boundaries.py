#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the OCHA administrative boundary import application.

The integration tests run the real ``ogr2ogr`` against a real (ephemeral)
PostgreSQL and a small GeoPackage cut from the published dataset, so the whole
path is exercised — the subprocess, the staging table and the SQL mapping. That
is the point of them: a mocked ``ogr2ogr`` would test nothing that matters here.
"""

import argparse
import logging
import shutil

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.admin_boundaries.ocha import import_admin_boundaries as app
from src.data_model import Base
from src.settings import ROOT_DIR
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers.ocha.admin_boundary import OchaAdminBoundary

#: Six features cut from the published layer and simplified, chosen to cover the
#: shapes the dataset actually takes: two ordinary states (Andorra, Monaco); two
#: French Southern Territories islands sharing ``iso_3`` but not ``adm0_id``
#: (Kerguelen, Crozet); a disputed area with neither ``adm0_name`` nor ``iso_2``
#: (Spratly Islands); and a territory that has a name but no ``iso_2`` (Akrotiri).
#: Anchored on the repository root rather than counted back from this file, so
#: moving the test module around cannot silently break the path.
SAMPLE_GEOPACKAGE = ROOT_DIR / "test" / "fixtures" / "data" / "ocha_adm0_sample.gpkg"

needs_ogr2ogr = pytest.mark.skipif(shutil.which("ogr2ogr") is None,
                                   reason="ogr2ogr (GDAL) is not installed")

logger = logging.getLogger("test-ocha-import")


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
def args(database):
    """Command-line arguments pointing at the ephemeral database and the sample file."""
    _, info = database
    return app.parse_arguments([
        "--geopackage", str(SAMPLE_GEOPACKAGE),
        "--db-host", info.host, "--db-port", str(info.port),
        "--db-name", info.dbname, "--db-user", info.user,
        "--db-password", info.password or "",
    ])


# --------------------------------------------------------------------------
# Argument and settings resolution (no database, no ogr2ogr)
# --------------------------------------------------------------------------

def test_geopackage_is_required():
    with pytest.raises(SystemExit):
        app.parse_arguments([])


def test_defaults_are_applied():
    parsed = app.parse_arguments(["-g", "boundaries.gpkg"])
    assert parsed.geopackage == Path("boundaries.gpkg")
    assert parsed.layer == app.DEFAULT_LAYER
    assert parsed.staging_schema == app.DEFAULT_STAGING_SCHEMA
    assert parsed.keep_staging is False


def test_environment_supplies_the_database_settings(monkeypatch):
    monkeypatch.setenv("GISFIRE_DB_HOST", "db.example.org")
    monkeypatch.setenv("GISFIRE_DB_PORT", "5555")
    monkeypatch.setenv("GISFIRE_DB_NAME", "from_env")
    monkeypatch.setenv("GISFIRE_DB_USER", "env_user")
    monkeypatch.setenv("GISFIRE_DB_PASSWORD", "env_password")

    settings = app.resolve_database_settings(app.parse_arguments(["-g", "boundaries.gpkg"]))
    assert settings == {"host": "db.example.org", "port": "5555", "name": "from_env",
                        "user": "env_user", "password": "env_password"}


def test_arguments_override_the_environment(monkeypatch):
    monkeypatch.setenv("GISFIRE_DB_NAME", "from_env")
    monkeypatch.setenv("GISFIRE_DB_USER", "env_user")

    settings = app.resolve_database_settings(app.parse_arguments(
        ["-g", "boundaries.gpkg", "--db-name", "from_args", "--db-user", "args_user"]
    ))
    assert settings["name"] == "from_args"
    assert settings["user"] == "args_user"


@pytest.mark.parametrize("missing", ["GISFIRE_DB_NAME", "GISFIRE_DB_USER"])
def test_a_missing_required_setting_is_refused(monkeypatch, missing):
    """Connecting somewhere unintended is worse than failing loudly."""
    monkeypatch.setenv("GISFIRE_DB_NAME", "gisfire")
    monkeypatch.setenv("GISFIRE_DB_USER", "gisfire")
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(RuntimeError, match="Pass --db-"):
        app.resolve_database_settings(app.parse_arguments(["-g", "boundaries.gpkg"]))


def test_an_empty_password_is_allowed(monkeypatch):
    """Peer and trust authentication are legitimate; an empty password is not an error."""
    monkeypatch.setenv("GISFIRE_DB_NAME", "gisfire")
    monkeypatch.setenv("GISFIRE_DB_USER", "gisfire")
    monkeypatch.delenv("GISFIRE_DB_PASSWORD", raising=False)

    assert app.resolve_database_settings(app.parse_arguments(["-g", "x.gpkg"]))["password"] == ""


def test_the_password_never_reaches_the_ogr2ogr_command_line():
    """It goes through PGPASSWORD instead, so it cannot be read out of ``ps``."""
    settings = {"host": "localhost", "port": "5432", "name": "gisfire",
                "user": "gisfire", "password": "s3cret"}
    assert "s3cret" not in app.ogr_connection_string(settings)
    assert "password" not in app.ogr_connection_string(settings)


def test_special_characters_in_the_password_are_escaped():
    settings = {"host": "localhost", "port": "5432", "name": "gisfire",
                "user": "gisfire", "password": "p@ss:word/with?specials"}
    assert app.database_url(settings).password == "p@ss:word/with?specials"


def test_main_reports_a_missing_geopackage(caplog):
    assert app.main(["-g", "/nonexistent/boundaries.gpkg", "--db-name", "x", "--db-user", "y"]) == 1
    assert "not found" in caplog.text


def test_main_reports_missing_database_settings(monkeypatch, caplog):
    monkeypatch.delenv("GISFIRE_DB_NAME", raising=False)
    monkeypatch.delenv("GISFIRE_DB_USER", raising=False)

    assert app.main(["-g", str(SAMPLE_GEOPACKAGE)]) == 1
    assert "No database" in caplog.text


def test_main_reports_a_missing_ogr2ogr(caplog):
    exit_code = app.main(["-g", str(SAMPLE_GEOPACKAGE), "--db-name", "x", "--db-user", "y",
                          "--ogr2ogr", "/nonexistent/ogr2ogr"])
    assert exit_code == 1
    assert "GDAL" in caplog.text


# --------------------------------------------------------------------------
# The import itself (real ogr2ogr, real PostGIS, real GeoPackage)
# --------------------------------------------------------------------------

@needs_ogr2ogr
def test_the_sample_is_imported(database, args):
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == 6

    with Session(engine) as session:
        names = session.scalars(select(AdminBoundary.name).order_by(AdminBoundary.name)).all()
        assert names == ["Akrotiri (UK)", "Andorra", "Crozet Archipelago (Fr.)",
                         "Kerguelen Islands (Fr.)", "Monaco", "Spratly Islands"]
        assert session.scalars(select(AdminBoundary.level)).all() == [0] * 6


@needs_ogr2ogr
def test_a_disputed_area_is_named_from_the_iso_name(database, args):
    """``adm0_name`` is empty for all 32 disputed areas; the import falls back to ``adm0_name1``.

    Without the fallback these features cannot be imported at all — ``name`` is
    NOT NULL — so this is what keeps Aksai Chin, the Spratly Islands and the rest
    of them in the dataset rather than silently dropped.
    """
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        spratly = session.scalar(select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "XSI"))
        assert spratly.name == "Spratly Islands"
        assert spratly.iso_name == "Spratly Islands"
        assert spratly.status_name == "Sovereignty unsettled"


@needs_ogr2ogr
def test_a_boundary_without_an_iso_2_code_is_imported(database, args):
    """36 features have no alpha-2 code, though every one of them has an alpha-3."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        akrotiri = session.scalar(select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "XUK"))
        assert akrotiri.iso_2 is None
        assert akrotiri.iso_3 == "XUK"
        # This one does have its own name, unlike the disputed areas.
        assert akrotiri.name == "Akrotiri (UK)"
        assert akrotiri.iso_name == "Akrotiri and Dekelia"


@needs_ogr2ogr
def test_the_fields_are_mapped(database, args):
    """Andorra, checked field by field against the published record."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        andorra = session.scalar(select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "AND"))
        assert andorra.source_id == "AND-20250729"
        assert andorra.name == "Andorra"
        assert andorra.level == 0
        assert andorra.source == "AND"
        assert (andorra.iso_code, andorra.iso_2, andorra.iso_3) == (20, "AD", "AND")
        assert andorra.iso_3_group == "AND"
        assert (andorra.region1_code, andorra.region1_name) == (150, "Europe")
        assert (andorra.region2_code, andorra.region2_name) == (39, "Southern Europe")
        assert (andorra.status_code, andorra.status_name) == (1, "State")
        assert andorra.land_source == "osm"
        assert andorra.view == "intl"
        assert andorra.valid_date.isoformat() == "2025-02-24"
        assert andorra.update_date.isoformat() == "2025-07-29"
        assert andorra.name_alt is None  # adm0_name2 is empty throughout the dataset


@needs_ogr2ogr
def test_iso_name_keeps_the_iso_entity_name_apart_from_the_feature_name(database, args):
    """``adm0_name1`` is the ISO entity's name, not the feature's — the ATF islands prove it."""
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        islands = session.scalars(
            select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "ATF")
            .order_by(OchaAdminBoundary.name)
        ).all()
        assert [island.name for island in islands] == ["Crozet Archipelago (Fr.)",
                                                       "Kerguelen Islands (Fr.)"]
        # Both carry the same ISO name, which is neither island's own name.
        assert {island.iso_name for island in islands} == {"French Southern Territories"}
        # Distinct rows, distinct source ids, shared (non-unique) iso_3.
        assert {island.source_id for island in islands} == {"ATF_1-20250729", "ATF_2-20250729"}


@needs_ogr2ogr
def test_the_geometries_arrive_as_multipolygons_in_4326(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        srids = session.scalars(select(func.ST_SRID(AdminBoundary.geometry))).all()
        types = session.scalars(select(func.GeometryType(AdminBoundary.geometry))).all()
        assert set(srids) == {4326}
        assert set(types) == {"MULTIPOLYGON"}
        assert session.scalar(select(func.ST_IsValid(AdminBoundary.geometry)).limit(1)) is True


@needs_ogr2ogr
def test_the_data_provider_is_created_on_first_import(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider))
        assert provider.name == "OCHA"
        assert provider.product == "Global International Boundaries - OSM"
        assert provider.full_name == ("United Nations Office for the Coordination "
                                      "of Humanitarian Affairs")
        assert provider.url.startswith("https://data.humdata.org/")


@needs_ogr2ogr
def test_re_importing_is_idempotent(database, args):
    """Re-running must not duplicate the boundaries, nor create a second provider row."""
    engine, _ = database
    assert app.import_boundaries(args, engine, logger) == 6
    assert app.import_boundaries(args, engine, logger) == 0

    with Session(engine) as session:
        assert len(session.scalars(select(AdminBoundary)).all()) == 6
        assert len(session.scalars(select(DataProvider)).all()) == 1


@needs_ogr2ogr
def test_the_staging_table_is_dropped(database, args):
    engine, _ = database
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text(
            "SELECT to_regclass('staging.ocha_adm0_polygons')"
        )) is None


@needs_ogr2ogr
def test_the_staging_table_can_be_kept(database, args):
    engine, _ = database
    args.keep_staging = True
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        assert session.scalar(text("SELECT COUNT(*) FROM staging.ocha_adm0_polygons")) == 6


@needs_ogr2ogr
def test_the_staging_schema_is_not_public(database, args):
    """A staging table in ``public`` would be dropped by the next Alembic autogenerate."""
    engine, _ = database
    args.keep_staging = True
    app.import_boundaries(args, engine, logger)

    with Session(engine) as session:
        schemas = session.scalars(text(
            "SELECT table_schema FROM information_schema.tables WHERE table_name = 'ocha_adm0_polygons'"
        )).all()
        assert schemas == ["staging"]


@needs_ogr2ogr
def test_a_broken_geopackage_is_reported(database, args, tmp_path):
    """ogr2ogr's diagnostics are the only clue to what went wrong, so they must surface."""
    broken = tmp_path / "broken.gpkg"
    broken.write_text("this is not a GeoPackage")
    args.geopackage = broken

    engine, _ = database
    with pytest.raises(RuntimeError, match="ogr2ogr failed"):
        app.import_boundaries(args, engine, logger)


@needs_ogr2ogr
def test_a_missing_layer_is_reported(database, args):
    args.layer = "no_such_layer"
    engine, _ = database
    with pytest.raises(RuntimeError, match="ogr2ogr failed"):
        app.import_boundaries(args, engine, logger)


@needs_ogr2ogr
def test_main_runs_the_whole_import(database):
    """The single command a user actually types."""
    engine, info = database
    exit_code = app.main([
        "-g", str(SAMPLE_GEOPACKAGE),
        "--db-host", info.host, "--db-port", str(info.port),
        "--db-name", info.dbname, "--db-user", info.user,
        "--db-password", info.password or "",
    ])
    assert exit_code == 0

    with Session(engine) as session:
        assert len(session.scalars(select(OchaAdminBoundary)).all()) == 6


@needs_ogr2ogr
def test_main_returns_non_zero_when_the_import_fails(database, caplog):
    engine, info = database
    exit_code = app.main([
        "-g", str(SAMPLE_GEOPACKAGE), "--layer", "no_such_layer",
        "--db-host", info.host, "--db-port", str(info.port),
        "--db-name", info.dbname, "--db-user", info.user,
        "--db-password", info.password or "",
    ])
    assert exit_code == 1
    assert "Import failed" in caplog.text
