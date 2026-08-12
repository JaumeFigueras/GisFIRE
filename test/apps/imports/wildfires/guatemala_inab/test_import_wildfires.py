#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Guatemalan INAB fire report import.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on GeoJSON built in the shape the downloader writes. What is being
tested is what this source makes hard:

* that the **year** is the unit of work and the unit replaced, and that a record the
  server and the importer disagree about the year of moves rather than vanishing;
* that ``""`` and ``null`` are both read as *unfilled* — the trap that once reported
  3,080 fires inside a protected area called ``""``;
* that the four personal fields never reach the database under any name;
* that a false alarm is stored and a record with no date is not;
* that both written forms of the published instant are read, epoch and ISO.
"""

import datetime
import json
import logging

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.wildfires.guatemala_inab import import_wildfires as app
from src.data_model import Base
from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.data_model.ignition import Ignition
from src.data_model.wildfire import Wildfire
from src.providers import guatemala_inab
from src.providers import ocha
from src.providers.guatemala_inab.ignition import InabIgnition
from src.providers.guatemala_inab.wildfire import InabWildfire

UTC = datetime.timezone.utc

#: A square around Guatemala, standing in for the OCHA country outline.
GUATEMALA_OUTLINE = ("SRID=4326;MULTIPOLYGON(((-92.5 13.5, -88.0 13.5, -88.0 18.0, "
                     "-92.5 18.0, -92.5 13.5)))")

#: 2025-03-14 20:30 UTC — 14:30 in Guatemala, in the afternoon peak.
AN_INSTANT = 1741984200000


# --------------------------------------------------------------------------
# Fixtures: the file the downloader writes
# --------------------------------------------------------------------------

def a_report(**overrides) -> dict:
    """One feature shaped like the published ``datos_generales`` layer.

    Carries all four personal fields, because the point of dropping them is that
    they are *there* — a fixture without them would test nothing.
    """
    properties = {
        "objectid": 13,
        "globalid": "{49585C0C-4FE2-45A3-A50C-405E6C4EF418}",
        "ob_id": 941,
        "fecha_hora_incendio": AN_INSTANT,
        "created_date": 1742000000000,
        "last_edited_date": 1742100000000,
        "estado_aviso": guatemala_inab.STATUS_CLOSED,
        "forma_comunicacion": "telefono",
        "institucion": "conred",
        "institucion_otra": "",
        "tipo_incendio": guatemala_inab.LOCATION_IN_FOREST,
        "departamento": "zacapa",
        "municipio": "rio_hondo_1903",
        "aldea_lugar": "La Nueva ",
        "finca": "",
        "region_inab": "iii",
        "subregion_inab": "iii-1",
        "nombre_ap_1": "",
        "nombre_ap_2": "",
        "coordenada_x": 512345.0,
        "coordenada_y": 1678901.0,
        "sistema_proyeccion": guatemala_inab.CRS_GTM,
        "zona": None,
        "altitud": 320.0,
        # Never imported. See src.providers.guatemala_inab.PERSONAL_FIELDS.
        "reportado_por": "Sergio Batun",
        "telefono": "55512345",
        "created_user": "inab_sig",
        "last_edited_user": "inab_sig",
        # Known, deliberately unstored.
        "punto_dentro_ap": "Si",
        "link_googlemaps": "https://maps.google.com/?q=15.0,-89.5",
        "logoinab": None,
        "con_aviso": "Si",
        "informes_count": "1",
    }
    geometry = {"type": "Point", "coordinates": [-89.5, 15.0]}

    if "geometry" in overrides:
        geometry = overrides.pop("geometry")
    properties.update(overrides)
    return {"type": "Feature", "id": properties.get("objectid"),
            "geometry": geometry, "properties": properties}


def write_download(path: Path, *features: dict) -> Path:
    """Write a FeatureCollection the way the download application does."""
    path.write_text(json.dumps({"type": "FeatureCollection",
                                "features": list(features)}, ensure_ascii=False),
                    encoding="utf-8")
    return path


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
    """The OCHA provider and a Guatemala-shaped level 0 boundary."""
    engine, _ = database
    with Session(engine) as session:
        provider = DataProvider(name=ocha.PROVIDER_NAME, product=ocha.PROVIDER_PRODUCT,
                                full_name=ocha.PROVIDER_FULL_NAME, url=ocha.PROVIDER_URL)
        session.add(provider)
        session.flush()
        session.add(AdminBoundary(data_provider=provider, source_id="GTM",
                                  name="Guatemala", name_en="Guatemala",
                                  level=0, geometry=GUATEMALA_OUTLINE))
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


def stored(engine, model=InabWildfire):
    """Every row of a model, ordered by id."""
    with Session(engine) as session:
        return session.scalars(select(model).order_by(model.id)).all()


def count(engine, table: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT count(*) FROM {table}"))


# --------------------------------------------------------------------------
# A report round trips
# --------------------------------------------------------------------------

def test_a_report_is_stored_with_its_point(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_download(tmp_path / "guatemala_inab_fire-reports_2025.geojson",
                          a_report())

    assert run(url, path) == 0

    fire, = stored(engine)
    assert fire.global_id == "{49585C0C-4FE2-45A3-A50C-405E6C4EF418}"
    assert fire.object_id == 13
    assert fire.source_id == 941
    assert fire.report_status == guatemala_inab.STATUS_CLOSED
    assert fire.report_channel == "telefono"
    assert fire.institution == "conred"
    assert fire.fire_location == guatemala_inab.LOCATION_IN_FOREST
    assert fire.department_name == "zacapa"
    assert fire.inab_region == "iii"
    assert fire.ignition_id is not None

    point, = stored(engine, InabIgnition)
    assert point.global_id == fire.global_id, "the key is on both, so no join is needed"
    assert point.reported_x == 512345.0
    assert point.reported_crs == guatemala_inab.CRS_GTM
    assert point.altitude_m == 320.0
    assert point.utm_zone is None


def test_the_published_point_is_stored_unreprojected(tmp_path, with_boundaries):
    """EPSG:4326 in, EPSG:4326 out: the geometry *is* the published pair."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    with Session(engine) as session:
        longitude, latitude, srid = session.execute(select(
            func.ST_X(Ignition.geometry), func.ST_Y(Ignition.geometry),
            func.ST_SRID(Ignition.geometry),
        )).one()
    assert (longitude, latitude) == pytest.approx((-89.5, 15.0))
    assert srid == 4326


def test_the_provider_row_is_created(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    with Session(engine) as session:
        provider = session.scalar(select(DataProvider).where(
            DataProvider.name == guatemala_inab.PROVIDER_NAME))
    assert provider is not None
    assert provider.product == guatemala_inab.PROVIDER_PRODUCT


def test_the_country_is_resolved_from_the_point(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    with Session(engine) as session:
        parent = session.scalar(select(Wildfire))
        assert parent.admin_boundary is not None
        assert parent.admin_boundary.name_en == "Guatemala"
        assert session.scalar(select(Ignition)).admin_boundary_id is not None


def test_the_import_runs_without_boundaries(tmp_path, database):
    """The fires are worth having before the boundaries are imported."""
    engine, url = database
    assert run(url, write_download(tmp_path / "a.geojson", a_report())) == 0

    with Session(engine) as session:
        assert session.scalar(select(Wildfire)).admin_boundary_id is None


# --------------------------------------------------------------------------
# The instant
# --------------------------------------------------------------------------

def test_the_epoch_is_read_as_the_instant_it_is(tmp_path, with_boundaries):
    """ArcGIS milliseconds are UTC by definition, so there is nothing to convert."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    parent, = stored(engine, Wildfire)
    assert parent.start_date_time == datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC)
    assert parent.time_zone == guatemala_inab.DEFAULT_TIME_ZONE
    assert parent.end_date_time is None, "the end times are in the informes layer"
    assert parent.perimeter is None, "INAB publishes no shape and no area"


def test_the_stored_instant_reads_back_in_the_afternoon_peak(tmp_path, with_boundaries):
    """20:30 UTC is 14:30 in Guatemala — the hour these reports actually cluster in."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    with Session(engine) as session:
        local = session.scalar(text(
            "SELECT start_date_time AT TIME ZONE time_zone FROM wildfire"))
    assert local == datetime.datetime(2025, 3, 14, 14, 30)


def test_an_iso_date_is_read_too(tmp_path, with_boundaries):
    """``--iso-dates`` rewrites the download, and the import has to read that too."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson",
                            a_report(fecha_hora_incendio="2025-03-14T20:30:00+00:00")))

    parent, = stored(engine, Wildfire)
    assert parent.start_date_time == datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC)


def test_the_bookkeeping_dates_are_stored(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    fire, = stored(engine)
    assert fire.published_at == datetime.datetime(2025, 3, 15, 0, 53, 20, tzinfo=UTC)
    assert fire.edited_at is not None


def test_an_unreadable_date_is_a_problem_not_a_crash(tmp_path, with_boundaries, caplog):
    """A bad *bookkeeping* date leaves the fire storable; only the fire's own is fatal."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report(created_date="not a date")))

    fire, = stored(engine)
    assert fire.published_at is None
    assert "not a readable date" in caplog.text


# --------------------------------------------------------------------------
# The ``""`` trap, and the municipality code
# --------------------------------------------------------------------------

def test_an_empty_string_is_read_as_unfilled(tmp_path, with_boundaries):
    """The trap that once reported 3,080 fires inside a protected area named ``""``."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    fire, = stored(engine)
    assert fire.protected_area_name is None
    assert fire.protected_area_name_secondary is None
    assert fire.estate_name is None
    assert fire.institution_other is None


def test_a_filled_protected_area_survives_the_fold(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson",
                            a_report(nombre_ap_1="Reserva de la Biosfera Maya")))

    fire, = stored(engine)
    assert fire.protected_area_name == "Reserva de la Biosfera Maya"


def test_surrounding_whitespace_is_stripped(tmp_path, with_boundaries):
    """``'Josefinos '`` and ``'Josefinos'`` are one locality, not two."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    fire, = stored(engine)
    assert fire.locality_name == "La Nueva"


def test_the_municipality_code_is_parsed_out_of_the_slug(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    fire, = stored(engine)
    assert fire.municipality_name == "rio_hondo_1903", "the slug is stored whole"
    assert fire.municipality_code == 1903


def test_a_truncated_code_is_refused_rather_than_guessed(tmp_path, with_boundaries):
    """``..._132`` says department 01, and the record says Huehuetenango."""
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report(
        departamento="huehuetenango", municipio="san_sebastian_huehuetenango_132")))

    fire, = stored(engine)
    assert fire.municipality_name == "san_sebastian_huehuetenango_132"
    assert fire.municipality_code is None
    assert fire.department_name == "huehuetenango", "the department is still known"


# --------------------------------------------------------------------------
# Personal data
# --------------------------------------------------------------------------

def test_no_personal_value_reaches_the_database(tmp_path, with_boundaries):
    """The fixture publishes all four; none of them may be anywhere in either table.

    Asserted over every text column of both tables rather than over the ones the
    mapping happens to write, so that adding a column and quietly filling it from
    ``reportado_por`` fails here.
    """
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))

    with Session(engine) as session:
        rows = session.execute(text(
            "SELECT n.*, g.* FROM inab_wildfire n "
            "LEFT JOIN inab_ignition g ON g.id = n.ignition_id")).mappings().all()
    published = {"Sergio Batun", "55512345", "inab_sig"}
    for row in rows:
        for value in row.values():
            assert value not in published


def test_the_personal_fields_are_not_among_the_imported_ones():
    """A cheaper statement of the same rule, and one that reads at the definition."""
    assert not (app.IMPORTED_FIELDS & set(guatemala_inab.PERSONAL_FIELDS))
    assert set(guatemala_inab.PERSONAL_FIELDS) <= app.KNOWN_FIELDS, \
        "known, so they are not reported as unknown every run"


def test_the_deliberately_unstored_fields_are_not_imported():
    assert not (app.IMPORTED_FIELDS & set(app.IGNORED_FIELDS))
    assert "link_googlemaps" in app.IGNORED_FIELDS


# --------------------------------------------------------------------------
# What is storable
# --------------------------------------------------------------------------

def test_a_report_with_no_date_is_skipped(tmp_path, with_boundaries, caplog):
    """Four of the 4,615: an identifier and a map tap, and nothing to date them by."""
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(),
                          a_report(globalid="{B}", objectid=14,
                                   fecha_hora_incendio=None))

    assert run(url, path) == 0
    assert count(engine, "inab_wildfire") == 1
    assert "no fecha_hora_incendio" in caplog.text


def test_a_report_with_no_key_is_skipped(tmp_path, with_boundaries, caplog):
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(),
                          a_report(globalid="", objectid=14))

    assert run(url, path) == 0
    assert count(engine, "inab_wildfire") == 1
    assert "no globalid" in caplog.text


def test_a_report_with_no_point_is_stored_without_one(tmp_path, with_boundaries):
    """Degraded rather than refused: the report still says when and where in words."""
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(globalid="{B}", geometry=None))

    assert run(url, path) == 0
    fire, = stored(engine)
    assert fire.ignition_id is None
    assert count(engine, "ignition") == 0
    assert count(engine, "inab_wildfire") == 1


def test_a_false_alarm_is_stored_and_counted(tmp_path, with_boundaries, caplog):
    """A record saying *this was not a fire* can be filtered; a dropped one cannot."""
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(estado_aviso=guatemala_inab.STATUS_FALSE))

    assert run(url, path) == 0
    fire, = stored(engine)
    assert fire.report_status == guatemala_inab.STATUS_FALSE
    assert "1 false alarm(s)" in caplog.text


def test_a_point_outside_guatemala_is_stored_and_reported(tmp_path, with_boundaries,
                                                          caplog):
    """The two sign-flipped longitudes: the provider's data, not this import's guess."""
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson", a_report(
        estado_aviso=guatemala_inab.STATUS_FALSE,
        geometry={"type": "Point", "coordinates": [90.47, 14.2]}))

    assert run(url, path) == 0
    with Session(engine) as session:
        longitude = session.scalar(select(func.ST_X(Ignition.geometry)))
    assert longitude == pytest.approx(90.47), "stored as published"
    assert "outside Guatemala" in caplog.text


def test_a_polygon_where_a_point_belongs_is_refused(tmp_path, with_boundaries, caplog):
    """This layer publishes points; anything else means the wrong layer."""
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson", a_report(
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}))

    assert run(url, path) == 0
    assert "not a Point" in caplog.text
    fire, = stored(engine)
    assert fire.ignition_id is None, "the fire is kept, the geometry is not"


# --------------------------------------------------------------------------
# The year is the unit of work
# --------------------------------------------------------------------------

def a_2024_report(**overrides) -> dict:
    """A report in the previous year: 2024-04-01 18:00 UTC, midday in Guatemala."""
    values = {"globalid": "{2024-A}", "objectid": 20,
              "fecha_hora_incendio": 1711994400000}
    values.update(overrides)
    return a_report(**values)


def test_each_year_is_written_in_its_own_transaction(tmp_path, with_boundaries, caplog):
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    path = write_download(tmp_path / "all.geojson", a_report(), a_2024_report())

    assert run(url, path) == 0
    assert count(engine, "inab_wildfire") == 2
    assert "2 year(s) to write: 2024, 2025" in caplog.text
    assert "2024: 1 fire(s) written" in caplog.text
    assert "2025: 1 fire(s) written" in caplog.text


def test_the_year_is_the_guatemalan_one(tmp_path, with_boundaries, caplog):
    """2025-01-01 03:00 UTC is 2024-12-31 21:00 in Guatemala, so it is a 2024 fire."""
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(fecha_hora_incendio=1735700400000))

    assert run(url, path) == 0
    assert "1 year(s) to write: 2024" in caplog.text


def test_only_the_years_asked_for_are_read(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_download(tmp_path / "all.geojson", a_report(), a_2024_report())

    assert run(url, path, extra=["--year", "2024"]) == 0
    fire, = stored(engine)
    assert fire.global_id == "{2024-A}"


def test_re_importing_replaces_the_year(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson", a_report(), a_2024_report())

    run(url, path)
    run(url, path)

    assert count(engine, "inab_wildfire") == 2
    assert count(engine, "wildfire") == 2
    assert count(engine, "inab_ignition") == 2
    assert count(engine, "ignition") == 2


def test_a_withdrawn_report_goes_when_its_year_is_re_imported(tmp_path, with_boundaries):
    """Replacing the year is the only operation that removes what INAB retracted."""
    engine, url = with_boundaries
    first = write_download(tmp_path / "first.geojson", a_report(),
                           a_report(globalid="{B}", objectid=14))
    run(url, first)
    assert count(engine, "inab_wildfire") == 2

    second = write_download(tmp_path / "second.geojson", a_report())
    run(url, second)

    fire, = stored(engine)
    assert fire.global_id == "{49585C0C-4FE2-45A3-A50C-405E6C4EF418}"


def test_a_report_that_changes_year_moves_rather_than_vanishing(tmp_path,
                                                                with_boundaries):
    """The reason the delete keys on ``global_id`` as well as on the year.

    The record is imported as a 2024 fire, then re-published with a corrected
    instant that puts it in 2025. Importing only the 2025 file has to leave one row,
    in 2025 — a year-only delete would insert the new row and leave the 2024 one
    behind, and ``global_id`` is unique, so it would not even manage that.
    """
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "2024.geojson", a_2024_report()))
    assert count(engine, "inab_wildfire") == 1

    corrected = a_2024_report(fecha_hora_incendio=AN_INSTANT)
    assert run(url, write_download(tmp_path / "2025.geojson", corrected)) == 0

    fire, = stored(engine)
    assert fire.global_id == "{2024-A}"
    parent, = stored(engine, Wildfire)
    assert parent.start_date_time == datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC)
    assert count(engine, "ignition") == 1, "the old point went with the old fire"


def test_another_years_fires_are_not_touched(tmp_path, with_boundaries):
    engine, url = with_boundaries
    run(url, write_download(tmp_path / "all.geojson", a_report(), a_2024_report()))
    before = {row.global_id: row.id for row in stored(engine)}

    run(url, write_download(tmp_path / "2025.geojson", a_report()))
    after = {row.global_id: row.id for row in stored(engine)}

    assert after["{2024-A}"] == before["{2024-A}"], "the 2024 row was left alone"
    assert len(after) == 2


# --------------------------------------------------------------------------
# Reading several files
# --------------------------------------------------------------------------

def test_a_directory_of_downloads_is_read(tmp_path, with_boundaries):
    engine, url = with_boundaries
    write_download(tmp_path / "guatemala_inab_fire-reports_2025.geojson", a_report())
    write_download(tmp_path / "guatemala_inab_fire-reports_2024.geojson",
                   a_2024_report())
    (tmp_path / "guatemala_inab_fire-reports_2025.meta.json").write_text("{}")

    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 0
    assert count(engine, "inab_wildfire") == 2, "and the .meta.json sidecar was not read"


def test_a_record_published_in_two_files_is_written_once(tmp_path, with_boundaries,
                                                         caplog):
    """Asking for the ``all`` file and a year gives the same record twice."""
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    everything = write_download(tmp_path / "all.geojson", a_report(), a_2024_report())
    one_year = write_download(tmp_path / "2025.geojson", a_report())

    assert run(url, everything, one_year) == 0
    assert count(engine, "inab_wildfire") == 2
    assert "is already in this run" in caplog.text
    assert "1 duplicate(s)" in caplog.text


# --------------------------------------------------------------------------
# Refusals and dry runs
# --------------------------------------------------------------------------

def test_a_dry_run_writes_nothing(tmp_path, with_boundaries, caplog):
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson", a_report(), a_2024_report())

    assert run(url, path, extra=["--dry-run"]) == 0
    assert count(engine, "inab_wildfire") == 0
    assert count(engine, "wildfire") == 0
    assert count(engine, "ignition") == 0
    assert "ROLLED BACK" in caplog.text


def test_a_dry_run_does_not_replace_a_stored_year(tmp_path, with_boundaries):
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson", a_report())
    run(url, path)

    assert run(url, path, extra=["--dry-run"]) == 0
    assert count(engine, "inab_wildfire") == 1


def test_a_file_that_is_not_a_feature_collection_is_refused(tmp_path, with_boundaries,
                                                            caplog):
    engine, url = with_boundaries
    path = tmp_path / "a.geojson"
    path.write_text(json.dumps({"count": 4615}), encoding="utf-8")

    assert run(url, path) == 1
    assert "not a GeoJSON FeatureCollection" in caplog.text
    assert count(engine, "inab_wildfire") == 0


def test_a_file_that_is_not_json_is_refused(tmp_path, with_boundaries, caplog):
    _, url = with_boundaries
    path = tmp_path / "a.geojson"
    path.write_text("<html>404</html>", encoding="utf-8")

    assert run(url, path) == 1
    assert "not readable JSON" in caplog.text


def test_a_missing_file_is_reported(tmp_path, with_boundaries, caplog):
    _, url = with_boundaries
    assert run(url, tmp_path / "nowhere.geojson") == 1
    assert "Not found" in caplog.text


def test_an_empty_directory_is_reported(tmp_path, with_boundaries, caplog):
    _, url = with_boundaries
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]

    assert app.main(argv) == 1
    assert "holds no *.geojson file" in caplog.text


def test_a_file_that_is_not_a_download_is_refused(tmp_path):
    path = tmp_path / "wildfires.shp"
    path.write_text("")
    with pytest.raises(RuntimeError, match="not a downloaded INAB file"):
        app.find_files(app.parse_arguments(["-s", str(path), "--db-name", "x",
                                            "--db-user", "y"]))


def test_the_tables_have_to_exist(tmp_path, postgresql, caplog):
    """A database that has not been migrated is caught before anything is read."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    engine.dispose()

    assert run(url, write_download(tmp_path / "a.geojson", a_report())) == 1
    assert "not found in the database" in caplog.text


# --------------------------------------------------------------------------
# Reading a published record, without a database
# --------------------------------------------------------------------------

def test_an_unknown_attribute_is_reported(tmp_path, with_boundaries, caplog):
    """INAB adding a thirty-fourth attribute is not an error, but it is news."""
    _, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report(superficie_ha=12.5)))
    assert "superficie_ha" in caplog.text
    assert "does not know and will not store" in caplog.text


def test_the_known_attributes_are_not_reported_as_unknown(tmp_path, with_boundaries,
                                                          caplog):
    _, url = with_boundaries
    run(url, write_download(tmp_path / "a.geojson", a_report()))
    assert "does not know and will not store" not in caplog.text


@pytest.mark.parametrize("published, expected", [
    ({"objectid": 13}, 13),
    ({"objectid": 13.0}, 13),
    ({"objectid": "13"}, 13),
    ({"objectid": None}, None),
    ({}, None),
])
def test_a_json_number_is_read_as_an_integer(published, expected):
    """JSON has one number type, so ``13`` is as likely to arrive as ``13.0``."""
    assert app.read_integer(published, "objectid", []) == expected


def test_a_fractional_integer_is_a_problem():
    problems = []
    assert app.read_integer({"zona": 15.5}, "zona", problems) is None
    assert "not a whole number" in problems[0]


def test_the_property_keys_are_folded_to_lower_case():
    """The same fields are ``OBJECTID``/``GlobalID`` on a differently published view."""
    published = app.properties({"properties": {"GlobalID": "{A}", "OBJECTID": 13}})
    assert published == {"globalid": "{A}", "objectid": 13}


def test_a_feature_with_no_properties_reads_as_an_empty_record():
    report = app.read_report({"type": "Feature", "geometry": None}, "a.geojson", 1)
    assert report.global_id is None
    assert report.start is None
    assert report.year is None


def test_the_year_bounds_are_the_local_ones():
    """Guatemala is UTC-6 all year, so 1 January starts at 06:00 UTC."""
    start, end = app.year_bounds(2025)
    assert start == datetime.datetime(2025, 1, 1, 6, 0, tzinfo=UTC)
    assert end == datetime.datetime(2026, 1, 1, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", "   ", None])
def test_a_blank_number_is_not_a_problem(value):
    """JSON has no empty number, but a value typed into a form and published as
    text does arrive blank, and blank is *unfilled* rather than unreadable."""
    problems = []
    assert app.read_number({"altitud": value}, "altitud", problems) is None
    assert problems == []


def test_a_number_that_is_not_one_is_a_problem():
    problems = []
    assert app.read_number({"altitud": "muy alto"}, "altitud", problems) is None
    assert "not a number" in problems[0]


def test_an_epoch_out_of_range_is_a_problem():
    problems = []
    assert app.read_instant({"created_date": 1e30}, "created_date", problems) is None
    assert "not a readable epoch" in problems[0]


def test_a_blank_date_is_unfilled_rather_than_unreadable():
    problems = []
    assert app.read_instant({"created_date": ""}, "created_date", problems) is None
    assert problems == []


def test_a_naive_iso_reading_is_taken_as_utc():
    """Only reachable from a hand-edited file; UTC is what the field means."""
    assert app.read_instant({"d": "2025-03-14T20:30:00"}, "d", []) == \
        datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC)


@pytest.mark.parametrize("coordinates, message", [
    ([-89.5], "no usable coordinates"),
    (None, "no usable coordinates"),
    (["oeste", "norte"], "not numbers"),
])
def test_an_unusable_coordinate_is_a_problem(coordinates, message):
    problems = []
    feature = {"geometry": {"type": "Point", "coordinates": coordinates}}
    assert app.read_point(feature, problems) == (None, None)
    assert message in problems[0]


def test_the_object_id_falls_back_to_the_feature_key():
    """ArcGIS writes it in both places; an export could carry only the outer one."""
    report = app.read_report({"id": 4798, "properties": {"globalid": "{A}"}},
                             "a.geojson", 1)
    assert report.object_id == 4798


def test_a_string_feature_key_is_not_read_as_the_object_id():
    report = app.read_report({"id": "datos_generales.13", "properties": {}},
                             "a.geojson", 1)
    assert report.object_id is None


def test_a_collection_with_no_features_list_is_refused(tmp_path):
    path = tmp_path / "a.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no list of features"):
        app.read_file(path, logging.getLogger("test"))


def test_a_feature_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / "a.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": ["nope"]}),
                    encoding="utf-8")
    with pytest.raises(RuntimeError, match="feature 1 is not an object"):
        app.read_file(path, logging.getLogger("test"))


def test_an_unverified_report_is_counted_apart_from_a_false_alarm(tmp_path,
                                                                  with_boundaries,
                                                                  caplog):
    """*Nobody went to look* is not *there was no fire*; 90 records against 140."""
    caplog.set_level(logging.INFO)
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(estado_aviso=guatemala_inab.STATUS_UNVERIFIED))

    assert run(url, path) == 0
    assert "0 false alarm(s), 1 unverified" in caplog.text


def test_a_file_of_nothing_storable_writes_nothing(tmp_path, with_boundaries, caplog):
    engine, url = with_boundaries
    path = write_download(tmp_path / "a.geojson",
                          a_report(fecha_hora_incendio=None))

    assert run(url, path) == 0
    assert "No storable fire report found" in caplog.text
    assert count(engine, "inab_wildfire") == 0
